"""`POST /api/multiescala/execucoes/{id}/regioes` (item L3-05-localizar-regioes): roda o motor de localizar
regiões sobre a grade de favorabilidade de uma execução do motor multicritério e devolve as regiões com
geometria e estatísticas.

O que entra: a execução (item L3-19/L3-01-e) já calculada — a grade, a resolução e a nota por célula saem de
`plat.escala_grade`, `plat.escala_celula` e `plat.escala_resultado`. O que sai: um polígono por região (união
das células, em 4326), a área, as estatísticas de favorabilidade e a compacidade contra a forma-alvo.

A rota é SÍNCRONA e tem teto de células declarado (`REGIOES_CELULAS_MAX`): a grade de 1 milhão de células roda
em segundos (medido em `tests/medidas/L3-05-localizar-regioes.json`); acima do teto o pedido é recusado com o
número, em vez de prender a conexão. Nada é gravado: localizar regiões é uma PERGUNTA sobre a execução, não uma
mudança nela — quem quiser guardar a resposta cria um item com o GeoJSON devolvido."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app import db, limites
from app.amc import regioes as motor
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/multiescala", tags=["multiescala"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCOPO = "multiescala:usar"


class RegioesEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_regioes: int = Field(default=1, ge=1, le=limites.REGIOES_N_MAX)
    area_total_m2: float | None = Field(default=None, gt=0)
    area_min_m2: float | None = Field(default=None, gt=0)
    area_max_m2: float | None = Field(default=None, gt=0)
    distancia_min_m: float | None = Field(default=None, ge=0)
    distancia_max_m: float | None = Field(default=None, gt=0)
    compromisso: int = Field(default=50, ge=0, le=100)
    forma: str = Field(default="circulo", pattern="^(circulo|quadrado|hexagono)$")
    metodo: str = Field(default="maior_media", pattern="^(maior_media|maior_soma|mediana|maior_area_nucleo)$")
    selecao: str = Field(default="sequencial", pattern="^(sequencial|combinatoria)$")
    vizinhanca: int = Field(default=8)
    sem_ilhas: bool = True
    sementes: str = Field(default="auto", pattern="^(auto|poucas|medias|muitas|maximo)$")
    resolucao_crescimento: str = Field(default="auto", pattern="^(auto|baixa|media|alta|maxima)$")
    semente_aleatoria: int = Field(default=0, ge=0, le=2**31 - 1)
    so_aprovadas: bool = Field(default=False, description="usar só as células aprovadas pela execução")


class RegiaoSaida(BaseModel):
    model_config = ConfigDict(extra="allow")


def _grade_da_execucao(cur, eid: str) -> tuple[dict, dict]:
    cur.execute("SELECT * FROM plat.escala_execucao WHERE id = %s::uuid", (eid,))
    execucao = cur.fetchone()
    if execucao is None:
        raise ErroAPI(404, "execucao_inexistente", "execução inexistente")
    cur.execute("SELECT * FROM plat.escala_grade WHERE id = %s", (execucao["grade_id"],))
    grade = cur.fetchone()
    if grade is None:
        raise ErroAPI(404, "grade_inexistente", "grade da execução inexistente")
    return execucao, grade


def _matriz(cur, eid: str, grade: dict, so_aprovadas: bool) -> tuple[np.ndarray, dict[tuple[int, int], int]]:
    """Grade 2-D de favorabilidade (nan onde não há nota) e o índice (lin, col) -> id da célula, que devolve a
    geometria depois. As células são as que EXISTEM (a grade recortada pela área de estudo); o resto é nan."""
    colunas, linhas = int(grade["colunas"]), int(grade["linhas"])
    if colunas * linhas > limites.REGIOES_CELULAS_MAX:
        raise ErroAPI(
            422, "grade_grande_demais",
            f"a grade tem {colunas * linhas} células e o teto desta rota é {limites.REGIOES_CELULAS_MAX}",
            {"colunas": colunas, "linhas": linhas, "teto": limites.REGIOES_CELULAS_MAX},
        )
    filtro = " AND r.aprovada" if so_aprovadas else ""
    cur.execute(
        f"SELECT c.id, c.col, c.lin, r.nota FROM plat.escala_resultado r "
        f"JOIN plat.escala_celula c ON c.id = r.celula_id "
        f"WHERE r.execucao_id = %s::uuid AND r.nota IS NOT NULL{filtro}", (eid,),
    )
    fav = np.full((linhas, colunas), np.nan)
    indice: dict[tuple[int, int], int] = {}
    for linha in cur.fetchall():
        li, co = int(linha["lin"]), int(linha["col"])
        if 0 <= li < linhas and 0 <= co < colunas:
            fav[li, co] = float(linha["nota"])
            indice[(li, co)] = int(linha["id"])
    if not indice:
        raise ErroAPI(422, "execucao_sem_nota",
                      "a execução não tem célula com nota (rode a execução antes de localizar regiões)")
    return fav, indice


def _geometrias(cur, ids_por_regiao: dict[int, list[int]]) -> dict[int, dict]:
    """Um polígono por região: união das células (ST_Union) devolvida como GeoJSON em 4326."""
    saida: dict[int, dict] = {}
    for indice, ids in ids_por_regiao.items():
        cur.execute(
            "SELECT ST_AsGeoJSON(ST_UnaryUnion(ST_Collect(geom)))::json AS g, "
            "ST_AsGeoJSON(ST_PointOnSurface(ST_UnaryUnion(ST_Collect(geom))))::json AS ponto "
            "FROM plat.escala_celula WHERE id = ANY(%s)", (ids,),
        )
        linha = cur.fetchone()
        saida[indice] = {"geometria": linha["g"], "ponto_interno": linha["ponto"]}
    return saida


@router.post("/execucoes/{id}/regioes", openapi_extra=LER)
def localizar_regioes(id: str, corpo: RegioesEntrada, request: Request,
                      auth: Auth = autenticado(escopo_token=ESCOPO)):
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    with db.db(auth.contexto()) as cur:
        execucao, grade = _grade_da_execucao(cur, eid)
        fav, indice = _matriz(cur, eid, grade, corpo.so_aprovadas)
        lado = float(grade["resolucao_m"])
        pedido = motor.Pedido(
            n_regioes=corpo.n_regioes, area_total=corpo.area_total_m2, area_min=corpo.area_min_m2,
            area_max=corpo.area_max_m2, distancia_min=corpo.distancia_min_m,
            distancia_max=corpo.distancia_max_m, compromisso=corpo.compromisso, forma=corpo.forma,
            metodo=corpo.metodo, selecao=corpo.selecao, vizinhanca=corpo.vizinhanca,
            sem_ilhas=corpo.sem_ilhas, sementes=corpo.sementes,
            resolucao_crescimento=corpo.resolucao_crescimento, semente_aleatoria=corpo.semente_aleatoria,
            area_celula=lado * lado, lado_celula=lado,
        )
        try:
            resultado = motor.localizar(fav, pedido)
        except motor.ErroRegioes as e:
            raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
        ids_por_regiao: dict[int, list[int]] = {r.indice: [] for r in resultado.regioes}
        lins, cols = np.nonzero(resultado.rotulos)
        for li, co in zip(lins.tolist(), cols.tolist(), strict=True):
            r = int(resultado.rotulos[li, co])
            celula = indice.get((li, co))
            if celula is not None:
                ids_por_regiao[r].append(celula)
        geometrias = _geometrias(cur, ids_por_regiao)
        registrar_evento(
            cur, request, "multiescala/regioes", "item", None,
            {"execucao_id": eid, "n_regioes": len(resultado.regioes), "area_total_m2": resultado.area_total,
             "forma": corpo.forma, "metodo": corpo.metodo, "compromisso": corpo.compromisso},
        )
    saida = resultado.como_dicionario()
    for r in saida["regioes"]:
        g = geometrias.get(r["indice"], {})
        r["geometria"] = g.get("geometria")
        r["ponto_interno"] = g.get("ponto_interno")
        r["celulas_ids"] = len(ids_por_regiao.get(r["indice"], []))
    saida["execucao_id"] = eid
    saida["grade"] = {"id": str(grade["id"]), "nivel": grade["nivel"], "resolucao_m": lado,
                      "colunas": int(grade["colunas"]), "linhas": int(grade["linhas"])}
    saida["aviso_pesos"] = "regiões derivadas da favorabilidade; os pesos são escolhidos pelo usuário, não medidos"
    return saida
