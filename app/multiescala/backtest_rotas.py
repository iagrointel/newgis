"""`POST /api/multiescala/execucoes/{id}/backtest` (item L3-09-backtest-decisao-real): compara o ranking de uma
execução do motor multicritério com as ESCOLHAS REAIS que alguém já fez — galpões construídos, linhas
existentes, agências abertas.

As escolhas entram de duas formas, as duas do próprio inquilino: por `item_id` de uma camada vetorial hospedada
(a geometria é reduzida ao ponto interno de cada feição) ou por uma lista de pontos. Cada escolha cai na célula
que a contém; a que não cai em nenhuma vira a contagem `n_fora`, que aparece no relatório (refutação do item).

A conta vive em `app/amc/backtest.py` (módulo puro). Esta rota faz o que só o banco faz: achar a célula de cada
escolha, montar a favorabilidade por célula e, quando pedido, os valores de cada fator por célula para a
preferência revelada. Nada é gravado: o backtest é uma pergunta sobre a execução."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app import db, limites
from app.amc import backtest as motor
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/multiescala", tags=["multiescala"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCOPO = "multiescala:usar"


class Ponto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class BacktestEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    escolhas_item_id: str | None = None
    pontos: list[Ponto] | None = Field(default=None, max_length=limites.BACKTEST_PONTOS_MAX)
    n_permutacoes: int = Field(default=motor.PERMUTACOES_PADRAO, ge=1, le=limites.BACKTEST_PERMUTACOES_MAX)
    semente: int = Field(default=0, ge=0, le=2**31 - 1)
    data_decisao: str | None = Field(default=None, max_length=32)
    data_camada: str | None = Field(default=None, max_length=32)
    preferencia_revelada: bool = True


def _execucao_e_grade(cur, eid: str) -> tuple[dict, dict]:
    cur.execute("SELECT * FROM plat.escala_execucao WHERE id = %s::uuid", (eid,))
    execucao = cur.fetchone()
    if execucao is None:
        raise ErroAPI(404, "execucao_inexistente", "execução inexistente")
    cur.execute("SELECT * FROM plat.escala_grade WHERE id = %s", (execucao["grade_id"],))
    grade = cur.fetchone()
    if grade is None:
        raise ErroAPI(404, "grade_inexistente", "grade da execução inexistente")
    return execucao, grade


def _celulas_com_nota(cur, eid: str) -> tuple[list[int], np.ndarray]:
    cur.execute(
        "SELECT r.celula_id, r.nota FROM plat.escala_resultado r "
        "WHERE r.execucao_id = %s::uuid AND r.nota IS NOT NULL ORDER BY r.celula_id", (eid,),
    )
    linhas = cur.fetchall()
    if not linhas:
        raise ErroAPI(422, "execucao_sem_nota", "a execução não tem célula com nota")
    return [int(x["celula_id"]) for x in linhas], np.array([float(x["nota"]) for x in linhas], dtype=float)


def _pontos_do_item(cur, item_id: str) -> list[tuple[float, float]]:
    """Ponto interno de cada feição da camada hospedada do inquilino (RLS de `plat.item` isola)."""
    cur.execute("SELECT tipo, dados FROM plat.item WHERE id = %s::uuid AND apagado_em IS NULL", (item_id,))
    item = cur.fetchone()
    if item is None or item["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "camada_inexistente", "camada de escolhas inexistente")
    dados = item["dados"] or {}
    if dados.get("fonte") != "hospedada" or not dados.get("schema") or not dados.get("tabela"):
        raise ErroAPI(422, "camada_nao_hospedada",
                      "as escolhas têm de estar numa camada vetorial hospedada desta instalação")
    schema, tabela = str(dados["schema"]), str(dados["tabela"])
    if not schema.replace("_", "").isalnum() or not tabela.replace("_", "").isalnum():
        raise ErroAPI(422, "camada_invalida", "nome de schema ou tabela fora do padrão")
    cur.execute(
        f'SELECT ST_X(p) AS lon, ST_Y(p) AS lat FROM (SELECT ST_PointOnSurface(ST_Transform(geom, 4326)) AS p '
        f'FROM "{schema}"."{tabela}" LIMIT %s) q',
        (limites.BACKTEST_PONTOS_MAX,),
    )
    return [(float(r["lon"]), float(r["lat"])) for r in cur.fetchall()]


def _celulas_das_escolhas(cur, grade: dict, pontos: list[tuple[float, float]]) -> tuple[set[int], int]:
    """Célula que contém cada escolha; o que não cai em célula nenhuma é contado como `fora`."""
    if not pontos:
        return set(), 0
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    cur.execute(
        "WITH p AS (SELECT unnest(%s::double precision[]) AS lon, unnest(%s::double precision[]) AS lat) "
        "SELECT c.id AS celula_id, count(*) AS n FROM p "
        "JOIN plat.escala_celula c ON c.grade_id = %s "
        "AND ST_Contains(c.geom, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)) "
        "GROUP BY c.id", (lons, lats, grade["id"]),
    )
    linhas = cur.fetchall()
    dentro = {int(r["celula_id"]) for r in linhas}
    n_dentro = sum(int(r["n"]) for r in linhas)
    return dentro, max(0, len(pontos) - n_dentro)


def _fatores_por_celula(cur, eid: str, ids: list[int]) -> dict[str, np.ndarray]:
    cur.execute(
        "SELECT f.nome, fc.celula_id, fc.favorabilidade FROM plat.escala_fator_celula fc "
        "JOIN plat.escala_fator f ON f.id = fc.fator_id WHERE fc.execucao_id = %s::uuid", (eid,),
    )
    posicao = {cid: k for k, cid in enumerate(ids)}
    saida: dict[str, np.ndarray] = {}
    for linha in cur.fetchall():
        k = posicao.get(int(linha["celula_id"]))
        if k is None:
            continue
        vetor = saida.setdefault(str(linha["nome"]), np.full(len(ids), np.nan))
        vetor[k] = np.nan if linha["favorabilidade"] is None else float(linha["favorabilidade"])
    return saida


@router.post("/execucoes/{id}/backtest", openapi_extra=LER)
def backtest(id: str, corpo: BacktestEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    if bool(corpo.escolhas_item_id) == bool(corpo.pontos):
        raise ErroAPI(422, "escolhas_ausentes",
                      "informe as escolhas por `escolhas_item_id` OU por `pontos`, nunca os dois nem nenhum")
    with db.db(auth.contexto()) as cur:
        _, grade = _execucao_e_grade(cur, eid)
        ids, fav = _celulas_com_nota(cur, eid)
        if corpo.escolhas_item_id:
            item_id = uuid_ok(corpo.escolhas_item_id, "camada_inexistente", "camada de escolhas inexistente")
            pontos = _pontos_do_item(cur, item_id)
        else:
            pontos = [(p.lon, p.lat) for p in corpo.pontos or []]
        if not pontos:
            raise ErroAPI(422, "escolhas_vazias", "a camada ou a lista de escolhas está vazia")
        dentro, n_fora = _celulas_das_escolhas(cur, grade, pontos)
        fatores = _fatores_por_celula(cur, eid, ids) if corpo.preferencia_revelada else None
        escolhida = np.array([cid in dentro for cid in ids], dtype=bool)
        try:
            resultado = motor.avaliar(
                fav, escolhida, fatores=fatores, n_fora=n_fora,
                pedido=motor.Pedido(n_permutacoes=corpo.n_permutacoes, semente=corpo.semente,
                                    data_decisao=corpo.data_decisao, data_camada=corpo.data_camada),
            )
        except motor.ErroBacktest as e:
            raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
        registrar_evento(
            cur, request, "multiescala/backtest", "item", None,
            {"execucao_id": eid, "escolhas": len(pontos), "n_fora": n_fora, "auc": resultado.auc,
             "permutacoes": resultado.permutacoes, "anacronica": resultado.anacronica},
        )
    saida = resultado.como_dicionario()
    saida["execucao_id"] = eid
    saida["escolhas_recebidas"] = len(pontos)
    saida["grade"] = {"id": str(grade["id"]), "resolucao_m": float(grade["resolucao_m"]),
                      "colunas": int(grade["colunas"]), "linhas": int(grade["linhas"])}
    saida["aviso_pesos"] = ("o backtest não escolhe peso nenhum: mede a concordância do modelo do usuário com a "
                            "decisão real")
    return saida
