"""Rotas da série temporal da rede (item L4-15-serie-temporal-da-rede).

`/api/rede-serie` cria e lista as séries do inquilino; `POST /api/rede-serie/{serie_id}/safras` anexa uma
rede já importada como a safra de um ano; `POST /api/rede-serie/{serie_id}/calcular` recalcula linhagem,
carregamento e crescimento. As leituras entregam o que o mapa e a exportação consomem: as safras (o controle
deslizante), a linhagem por classe, a tendência por transformador (JSON ou CSV) e o crescimento por
alimentador.

Prefixo próprio (`/api/rede-serie`, não `/api/rede/series`): `/api/rede/{rede_id}` já captura qualquer
segmento depois de `/api/rede/`, e uma rota de coleção nova ali dentro passaria a depender da ORDEM de
registro dos roteadores para não ser engolida. Caminho separado, sem ambiguidade."""

import csv
import io
import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import serie as serie_mod

router = APIRouter(prefix="/api/rede-serie", tags=["rede de utilidades — série temporal"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


class SerieEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=2000)


class SafraEntrada(BaseModel):
    rede_id: str = Field(min_length=1, max_length=64, description="rede já importada com a safra daquele ano")
    ano: int = Field(ge=1990, le=2100)


def _uuid_ok(valor: str, codigo: str = "serie_inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, codigo, "série inexistente") from e


def _carregar(cur, serie_id: str) -> dict:
    cur.execute(
        "SELECT s.id, s.nome, s.descricao, s.calculado_em, s.metodo, s.criado_em, s.atualizado_em, "
        "s.dono_id, u.login AS dono_login FROM plat.rede_serie s "
        "JOIN plat.usuario u ON u.id = s.dono_id WHERE s.id = %s::uuid",
        (serie_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "serie_inexistente", "série inexistente")
    return r


def _json(cur, r: dict) -> dict:
    lista = serie_mod.safras(cur, str(r["id"]))
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "descricao": r["descricao"],
        "calculado_em": iso(r["calculado_em"]),
        "metodo": r["metodo"],
        "safras": [
            {"id": str(s["id"]), "ano": s["ano"], "rede_id": str(s["rede_id"]), "rede_nome": s["rede_nome"],
             "pot_nom_confiavel": s["pot_nom_confiavel"], "pot_nom_motivo": s["pot_nom_motivo"]}
            for s in lista
        ],
        "dono": {"id": r["dono_id"], "login": r["dono_login"]},
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


@router.get("", openapi_extra=LER)
def listar(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """As séries do inquilino, com as safras de cada uma (é o que alimenta o controle de tempo do mapa)."""
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT s.id, s.nome, s.descricao, s.calculado_em, s.metodo, s.criado_em, "
                    "s.atualizado_em, s.dono_id, u.login AS dono_login FROM plat.rede_serie s "
                    "JOIN plat.usuario u ON u.id = s.dono_id ORDER BY lower(s.nome)")
        linhas = cur.fetchall()
        itens = [_json(cur, r) for r in linhas]
    return {"total": len(itens), "itens": itens}


@router.post("", status_code=201, openapi_extra=EDITAR)
def criar(corpo: SerieEntrada, request: Request, auth: Auth = autenticado("rede.editar")):
    """Cria a série. As safras entram depois, uma a uma, por `POST /api/rede-serie/{id}/safras`."""
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.rede_serie(tenant_id, nome, descricao, dono_id) VALUES (%s, %s, %s, %s) "
                "RETURNING id",
                (auth.tenant_id, " ".join(corpo.nome.split()), corpo.descricao, auth.usuario_id),
            )
            serie_id = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma série com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/serie_criar", "rede_serie", serie_id, {"nome": corpo.nome})
        return _json(cur, _carregar(cur, serie_id))


@router.get("/{serie_id}", openapi_extra=LER)
def ver(serie_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return _json(cur, _carregar(cur, _uuid_ok(serie_id)))


@router.delete("/{serie_id}", status_code=204, openapi_extra=EDITAR)
def apagar(serie_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    sid = _uuid_ok(serie_id)
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, sid)
        cur.execute("DELETE FROM plat.rede_serie WHERE id = %s::uuid", (sid,))
        registrar_evento(cur, request, "redes/serie_apagar", "rede_serie", sid, {"nome": r["nome"]})
    return Response(status_code=204)


@router.post("/{serie_id}/safras", status_code=201, openapi_extra=EDITAR)
def anexar_safra(serie_id: str, corpo: SafraEntrada, request: Request,
                 auth: Auth = autenticado("rede.editar")):
    """Anexa uma rede já importada como a safra de um ano. A rede tem de ser do inquilino (a RLS garante),
    o ano é único na série e uma rede só participa de uma série — safra é a rede inteira daquele ano."""
    sid = _uuid_ok(serie_id)
    rid = _uuid_ok(corpo.rede_id, "rede_inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
        try:
            cur.execute(
                "INSERT INTO plat.rede_serie_safra(tenant_id, serie_id, rede_id, ano) "
                "VALUES (%s, %s::uuid, %s::uuid, %s) RETURNING id",
                (auth.tenant_id, sid, rid, corpo.ano),
            )
            safra_id = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "safra_existente",
                          "esta série já tem esse ano, ou essa rede já é safra de alguma série") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/serie_safra_anexar", "rede_serie", sid,
                         {"ano": corpo.ano, "rede_id": rid, "safra_id": safra_id})
        return _json(cur, _carregar(cur, sid))


@router.delete("/{serie_id}/safras/{ano}", status_code=204, openapi_extra=EDITAR)
def remover_safra(serie_id: str, ano: int, request: Request, auth: Auth = autenticado("rede.editar")):
    """Tira o ano da série. O que foi calculado com ele continua no banco até o próximo cálculo — por isso
    a resposta do cálculo carrega a lista de safras que ela usou."""
    sid = _uuid_ok(serie_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        cur.execute("DELETE FROM plat.rede_serie_safra WHERE serie_id = %s::uuid AND ano = %s", (sid, ano))
        if cur.rowcount == 0:
            raise ErroAPI(404, "safra_inexistente", "a série não tem esse ano")
        registrar_evento(cur, request, "redes/serie_safra_remover", "rede_serie", sid, {"ano": ano})
    return Response(status_code=204)


def _calcular_sincrono(sid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        try:
            resumo = serie_mod.calcular(cur, auth.tenant_id, sid)
        except serie_mod.ErroSerie as e:
            raise ErroAPI(422, "serie_sem_safras", str(e)) from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/serie_calcular", "rede_serie", sid,
                         {"safras": resumo["safras"], "linhagem": resumo["linhagem"],
                          "duracao_ms": resumo["duracao_ms"]})
    return resumo


@router.post("/{serie_id}/calcular", openapi_extra=EDITAR)
async def calcular(serie_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Recalcula linhagem por COD_ID, carregamento por transformador e crescimento por alimentador. O
    trabalho é de banco (consultas de conjunto) e vai para o threadpool, para não segurar o laço de
    eventos da API."""
    sid = _uuid_ok(serie_id)
    return await run_in_threadpool(_calcular_sincrono, sid, auth, request)


@router.get("/{serie_id}/linhagem", openapi_extra=LER)
def linhagem(serie_id: str, entidade: str = "trafo", classe: str | None = None,
             limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Contagens por classe (sempre) e uma amostra das linhas, filtrável por entidade e classe."""
    if entidade not in ("trafo", "uc"):
        raise ErroAPI(422, "entidade_invalida", "entidade só pode ser 'trafo' ou 'uc'")
    if classe is not None and classe not in ("persistente", "recodificado", "novo", "extinto"):
        raise ErroAPI(422, "classe_invalida",
                      "classe só pode ser persistente, recodificado, novo ou extinto")
    limite = max(1, min(int(limite), 1000))
    sid = _uuid_ok(serie_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        contagens = serie_mod.contagem_linhagem(cur, sid)
        cur.execute(
            "SELECT ano_base, ano_alvo, codigo_base, codigo_alvo, classe, confianca, evidencia "
            "FROM plat.rede_linhagem WHERE serie_id = %s::uuid AND entidade = %s "
            "AND (%s::text IS NULL OR classe = %s) ORDER BY ano_base, classe, codigo_base NULLS LAST, "
            "codigo_alvo LIMIT %s",
            (sid, entidade, classe, classe, limite),
        )
        itens = [dict(r) for r in cur.fetchall()]
    return {"entidade": entidade, "classe": classe, "contagens": contagens,
            "total_listado": len(itens), "limite": limite, "itens": itens}


def _csv_tendencia(itens: list[dict], anos: list[int]) -> bytes:
    saida = io.StringIO()
    w = csv.writer(saida, lineterminator="\n")
    w.writerow(["codigo", "alimentador", *[f"carga_pct_{a}" for a in anos], "ano_inicial", "ano_final",
                "carga_inicial_pct", "carga_final_pct", "variacao_pp", "variacao_pp_ano",
                "virou_sobrecarga", "pot_nom_confiavel"])
    for it in itens:
        por_ano = it["por_ano"] or {}
        w.writerow([
            it["codigo"], it["alimentador"] or "",
            *[(por_ano.get(str(a)) or {}).get("carga_pct", "") for a in anos],
            it["ano_inicial"], it["ano_final"],
            "" if it["carga_inicial_pct"] is None else it["carga_inicial_pct"],
            "" if it["carga_final_pct"] is None else it["carga_final_pct"],
            "" if it["variacao_pp"] is None else it["variacao_pp"],
            "" if it["variacao_pp_ano"] is None else it["variacao_pp_ano"],
            "sim" if it["virou_sobrecarga"] else "nao",
            "sim" if it["pot_nom_confiavel"] else "nao",
        ])
    return saida.getvalue().encode("utf-8")


@router.get("/{serie_id}/tendencia", openapi_extra=LER)
def tendencia(serie_id: str, formato: str = "json", so_sobrecarga: bool = False,
              auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Tendência de carregamento por transformador ao longo das safras. `formato=csv` devolve o arquivo
    exportável; `so_sobrecarga=true` deixa só os que passaram de abaixo de 80 % a acima de 100 %.

    O carregamento é PROXY de triagem (energia declarada na fonte com fator de carga e fator de potência
    fixos), e a coluna `pot_nom_confiavel` diz quando a potência nominal de alguma safra do transformador
    não serve como placa."""
    if formato not in ("json", "csv"):
        raise ErroAPI(422, "formato_invalido", "formato só pode ser json ou csv")
    sid = _uuid_ok(serie_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        anos = [s["ano"] for s in serie_mod.safras(cur, sid)]
        itens = serie_mod.tendencia(cur, sid, so_viraram_sobrecarga=so_sobrecarga)
    if formato == "csv":
        return Response(
            content=_csv_tendencia(itens, anos),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="tendencia-trafo.csv"',
                     "Cache-Control": "no-store"},
        )
    return {"anos": anos, "total": len(itens),
            "viraram_sobrecarga": sum(1 for i in itens if i["virou_sobrecarga"]),
            "metodo": serie_mod.metodo()["carga"], "itens": itens}


@router.get("/{serie_id}/alimentadores", openapi_extra=LER)
def alimentadores(serie_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Crescimento de rede por alimentador: km de trecho, unidades consumidoras e transformadores por safra,
    com a variação entre a primeira e a última safra em que o alimentador aparece."""
    sid = _uuid_ok(serie_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        anos = [s["ano"] for s in serie_mod.safras(cur, sid)]
        itens = serie_mod.crescimento(cur, sid)
    return {"anos": anos, "total": len(itens), "itens": itens}


@router.get("/{serie_id}/mapa", openapi_extra=LER)
def mapa(serie_id: str, ano: int, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Os transformadores de UMA safra como GeoJSON, com o carregamento e a classe de linhagem em relação
    à safra anterior. É a camada que o controle deslizante de safra do mapa troca a cada ano."""
    sid = _uuid_ok(serie_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, sid)
        cur.execute("SELECT rede_id, pot_nom_confiavel FROM plat.rede_serie_safra "
                    "WHERE serie_id = %s::uuid AND ano = %s", (sid, ano))
        safra = cur.fetchone()
        if safra is None:
            raise ErroAPI(404, "safra_inexistente", "a série não tem esse ano")
        cur.execute(
            "SELECT n.codigo_externo AS codigo, ST_X(n.geom) AS lon, ST_Y(n.geom) AS lat, "
            "  ts.carga_pct, ts.pot_nom_kva, ts.n_uc, ts.alimentador, l.classe "
            "FROM plat.rede_no n "
            "JOIN plat.rede_tipo t ON t.id = n.tipo_id "
            "JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "LEFT JOIN plat.rede_trafo_safra ts ON ts.serie_id = %(serie)s::uuid AND ts.ano = %(ano)s "
            "  AND ts.codigo = n.codigo_externo "
            "LEFT JOIN plat.rede_linhagem l ON l.serie_id = %(serie)s::uuid AND l.entidade = 'trafo' "
            "  AND l.ano_alvo = %(ano)s AND l.codigo_alvo = n.codigo_externo "
            "WHERE n.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s AND n.geom IS NOT NULL "
            "ORDER BY n.codigo_externo",
            {"serie": sid, "ano": ano, "rede": safra["rede_id"], "grupo": serie_mod.GRUPO_TRAFO},
        )
        feicoes = [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
             "properties": {"codigo": r["codigo"], "alimentador": r["alimentador"],
                            "carga_pct": None if r["carga_pct"] is None else round(r["carga_pct"], 2),
                            "pot_nom_kva": r["pot_nom_kva"], "n_uc": r["n_uc"],
                            "classe": r["classe"]}}
            for r in cur.fetchall()
        ]
    return {"type": "FeatureCollection", "ano": ano,
            "pot_nom_confiavel": safra["pot_nom_confiavel"], "features": feicoes}
