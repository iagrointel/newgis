"""Rotas de consumidores e endereços da rede (item L4-20-consumidores-e-enderecos):
POST /api/rede/consumidores/enderecos-sem-rede (gera a camada), GET da mesma lista,
GET /api/rede/consumidores/uc/{id} (ficha sem campo identificável), GET
/api/rede/consumidores/trecho/{id} (com clientes a jusante e consumo agregado) e POST
/api/rede/consumidores/jusante/calcular. Todo acesso exige sessão ou token com o privilégio
nomeado (rede.tracar para leitura, rede.editar para gerar/calcular); RLS isola por inquilino."""

import uuid

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede import consumidores

router = APIRouter(prefix="/api/rede/consumidores", tags=["rede"])
# leitura: qualquer leitor autenticado (RLS isola o inquilino); escrita: privilégio rede.editar
LEITURA = {"x-auth": "S/T", "x-privilegio": "proprio"}
ESCRITA = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


class PedidoGerar(BaseModel):
    raio_rede_m: float = Field(default=limites.REDE_RAIO_PADRAO_M, gt=0, le=limites.REDE_RAIO_REDE_MAX_M)
    raio_bt_m: float = Field(default=limites.REDE_RAIO_BT_PADRAO_M, gt=0, le=limites.REDE_RAIO_REDE_MAX_M)


class PedidoJusante(BaseModel):
    """o cálculo cobre todo o inquilino; o corpo é opcional e ignorado."""


def _uuid_ou_422(id_: str) -> str:
    try:
        uuid.UUID(id_)
    except (ValueError, AttributeError):
        raise ErroAPI(422, "id_invalido", "identificador não é um uuid") from None
    return id_


@router.post("/enderecos-sem-rede", openapi_extra=ESCRITA)
def gerar_enderecos_sem_rede(pedido: PedidoGerar, request: Request, auth: Auth = autenticado("rede.editar")):
    """Gera (recria) a camada de endereços com rede de média tensão a até raio_rede_m e sem rede
    de baixa tensão a até raio_bt_m para o inquilino da sessão."""
    with db.db(auth.contexto()) as cur:
        resumo = consumidores.gerar_enderecos_sem_rede(cur, pedido.raio_rede_m, pedido.raio_bt_m)
        registrar_evento(
            cur,
            request,
            "rede/enderecos_sem_rede",
            "camada",
            None,
            {"raio_rede_m": pedido.raio_rede_m, "raio_bt_m": pedido.raio_bt_m, **resumo},
        )
    return resumo


@router.get("/enderecos-sem-rede", openapi_extra=LEITURA)
def listar_enderecos_sem_rede(
    request: Request,
    limite_pagina: int = Query(default=50, alias="limite", ge=1, le=limites.PAGINA_MAX),
    deslocamento: int = Query(default=0, ge=0),
    situacao: str | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    if situacao is not None and situacao not in consumidores.SITUACOES:
        raise ErroAPI(422, "situacao_invalida", "situação deve ser candidato_ligacao ou cadastro_faltante")
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.rede_endereco_sem_rede"
            " WHERE tenant_id = plat.tenant_atual() AND (%s::text IS NULL OR situacao = %s)",
            (situacao, situacao),
        )
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT id::text AS id, endereco_id, ST_AsGeoJSON(geometria)::json AS geometria,"
            "       dist_rede_m, situacao, gerado_em"
            "  FROM plat.rede_endereco_sem_rede"
            " WHERE tenant_id = plat.tenant_atual() AND (%s::text IS NULL OR situacao = %s)"
            " ORDER BY dist_rede_m, endereco_id LIMIT %s OFFSET %s",
            (situacao, situacao, limite_pagina, deslocamento),
        )
        linhas = cur.fetchall()
    return {"total": total, "itens": [_linha_endereco(r) for r in linhas]}


def _linha_endereco(r: dict) -> dict:
    return {
        "id": r["id"],
        "endereco_id": r["endereco_id"],
        "geometria": r["geometria"],
        "dist_rede_m": r["dist_rede_m"],
        "situacao": r["situacao"],
        "gerado_em": r["gerado_em"].isoformat(),
    }


@router.get("/uc/{id}", openapi_extra=LEITURA)
def ficha_uc(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Ficha da unidade consumidora: só campos de rede; consumo exclusivamente agregado."""
    ficha = None
    with db.db(auth.contexto()) as cur:
        ficha = consumidores.ficha_uc(cur, _uuid_ou_422(id))
    if ficha is None:
        raise ErroAPI(404, "uc_inexistente", "unidade consumidora inexistente neste inquilino")
    return ficha


@router.get("/trecho/{id}", openapi_extra=LEITURA)
def ficha_trecho(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Ficha do trecho de média tensão: número de consumidores a jusante e consumo agregado
    (só com pelo menos REDE_AGREGACAO_MIN_UCS unidades)."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id::text AS id, codigo, ctmt, nivel, comprimento_m, clientes_jusante"
            "  FROM plat.rede_trecho WHERE id = %s",
            (_uuid_ou_422(id),),
        )
        r = cur.fetchone()
        if r is None or r["nivel"] != "mt":
            raise ErroAPI(404, "trecho_inexistente", "trecho de média tensão inexistente neste inquilino")
        cur.execute(
            "SELECT count(*) AS ucs, sum(c.ene_kwh) AS ene_kwh, max(c.ano) AS ano"
            "  FROM plat.rede_uc_consumo c JOIN plat.rede_uc u ON u.id = c.uc_id"
            " WHERE c.tenant_id = plat.tenant_atual() AND u.ctmt = %s",
            (r["ctmt"],),
        )
        agregado = cur.fetchone()
    resposta = {k: r[k] for k in ("id", "codigo", "ctmt", "nivel", "comprimento_m", "clientes_jusante")}
    resposta["consumo"] = _consumo_do_trecho(r["ctmt"], agregado)
    return resposta


def _consumo_do_trecho(ctmt: str, agregado: dict) -> dict | None:
    if agregado is None or agregado["ucs"] is None or agregado["ucs"] < limites.REDE_AGREGACAO_MIN_UCS:
        return None
    return {"ucs": agregado["ucs"], "ene_kwh": round(agregado["ene_kwh"], 3), "ano": agregado["ano"]}


@router.post("/jusante/calcular", openapi_extra=ESCRITA)
def calcular_jusante(request: Request, pedido: PedidoJusante | None = None, auth: Auth = autenticado("rede.editar")):
    """Calcula e grava o número de consumidores a jusante de cada trecho de média tensão."""
    with db.db(auth.contexto()) as cur:
        resumo = consumidores.calcular_jusante(cur)
        registrar_evento(cur, request, "rede/jusante_calcular", "rede", None, resumo)
    return resumo
