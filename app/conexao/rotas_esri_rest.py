"""Rotas do conector ArcGIS REST externo (item L6-02-d-arcgis-rest-externo; ADR 0020). Todas penduradas em
`/api/conexoes/{id}/esri/...`, sobre uma conexão já registrada com `tipo = "esri_rest"` (item L6-02-a) — a URL
já passou pela validação de SSRF na criação (`app.conexao.rotas._url_ok`); toda chamada ao serviço externo
daqui em diante usa `app.conexao.esri_rest`, que por sua vez usa só `app.conexao.seguranca.buscar_seguro`.

Convenção de registro: `plat.conexao.url` guarda a URL RAIZ do serviço (`.../FeatureServer`, `.../MapServer`
ou `.../ImageServer`, sem barra final) — o mesmo padrão de "uma conexão, N camadas" do WMS (uma capabilities,
N `camada=` por operação). O tipo do serviço (Feature/Map/Image) é lido do último segmento da própria URL,
nunca adivinhado pelo corpo da resposta.

Cobertura:
  GET /api/conexoes/{id}/esri/descricao                — raiz `?f=json`: tipo do serviço, sub-camadas/tabelas
  GET /api/conexoes/{id}/esri/camadas/{camada}          — descrição da camada (geometria, maxRecordCount,
                                                           campos, simbologia simples, capacidades)
  GET /api/conexoes/{id}/esri/camadas/{camada}/contagem — `returnCountOnly=true` (nunca baixa feição para contar)
  GET /api/conexoes/{id}/esri/camadas/{camada}/feicoes  — query paginado (resultOffset/resultRecordCount
                                                           clampado ao maxRecordCount do servidor), GeoJSON
  GET /api/conexoes/{id}/esri/mapa                      — MapServer `/export` (imagem dinâmica, proxy)
  GET /api/conexoes/{id}/esri/imagem                    — ImageServer `/exportImage` (raster referenciado, proxy)

Credencial: decifrada em memória só aqui (`_token_da_conexao`), passada como parâmetro `token=` na
querystring da requisição final ao serviço externo (convenção clássica do ArcGIS Server — diferente do
cabeçalho `Authorization: Bearer` do teste de saúde genérico) — nunca volta na resposta desta API nem em log
(`app/log.py` não recebe este módulo). Serviço que exige token sem tê-lo devolve erro claro (502 com o motivo
do serviço), nunca um laço de nova tentativa."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Response

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import uuid_ok
from app.conexao import credencial as credencial_mod
from app.conexao import esri_rest
from app.conexao.rotas import _carregar
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/api/conexoes/{id}", tags=["esri_rest"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}

_TIPOS_SERVICO = ("FeatureServer", "MapServer", "ImageServer")
_RE_TIPO_SERVICO = re.compile(r"/(FeatureServer|MapServer|ImageServer)/?$", re.IGNORECASE)


def _conexao(id: str, auth: Auth) -> dict:
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
    if r["tipo"] != "esri_rest":
        raise ErroAPI(
            422, "tipo_de_conexao_errado", f"conexão é do tipo {r['tipo']!r}, esperado 'esri_rest'",
            {"esperado": "esri_rest", "recebido": r["tipo"]},
        )
    return r


def _tipo_servico(url: str) -> str | None:
    m = _RE_TIPO_SERVICO.search(url)
    if not m:
        return None
    # normaliza a capitalização oficial (a URL pode vir com qualquer caixa)
    achado = m.group(1)
    return next((t for t in _TIPOS_SERVICO if t.lower() == achado.lower()), None)


def _exigir_tipo(url: str, *esperados: str) -> str:
    tipo = _tipo_servico(url)
    if tipo not in esperados:
        raise ErroAPI(
            422, "operacao_nao_suportada_pelo_servico",
            f"a URL da conexão não termina em {esperados!r} (detectado: {tipo!r}); "
            "registre a URL raiz do serviço (.../FeatureServer, .../MapServer ou .../ImageServer)",
            {"esperado": list(esperados), "detectado": tipo},
        )
    return tipo


def _token_da_conexao(r: dict, auth: Auth) -> str | None:
    if not r["tem_credencial"]:
        return None
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (r["id"],))
        bruta = cur.fetchone()["credencial_cifrada"]
    try:
        return credencial_mod.decifrar(bruta, settings.PLAT_SECRET)
    except ValueError:
        return None  # PLAT_SECRET trocado ou dado corrompido: segue sem credencial, nunca quebra a rota


def _url_camada(r: dict, camada: str) -> str:
    return f"{r['url'].rstrip('/')}/{camada}"


def _bbox_de_query(bbox: str) -> tuple[float, float, float, float]:
    partes = bbox.split(",")
    if len(partes) != 4:
        raise ErroAPI(422, "bbox_invalido", "bbox precisa de 4 números separados por vírgula (minx,miny,maxx,maxy)")
    try:
        minx, miny, maxx, maxy = (float(p) for p in partes)
    except ValueError as e:
        raise ErroAPI(422, "bbox_invalido", "bbox com valor não numérico") from e
    if minx >= maxx or miny >= maxy:
        raise ErroAPI(422, "bbox_invalido", "bbox degenerado (min >= max)")
    return (minx, miny, maxx, maxy)


def _simbologia_json(s: esri_rest.Simbologia | None) -> dict | None:
    if s is None:
        return None
    return {
        "geometria": s.geometria,
        "preenchimento_rgba": list(s.preenchimento_rgba) if s.preenchimento_rgba else None,
        "contorno_rgba": list(s.contorno_rgba) if s.contorno_rgba else None,
        "contorno_largura": s.contorno_largura,
    }


@router.get("/esri/descricao", openapi_extra=LER)
def descricao(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Raiz do serviço: tipo detectado da URL e a lista de sub-camadas/tabelas que ele declara (`?f=json` da
    raiz sempre tem `layers`/`tables` para FeatureServer/MapServer; ImageServer não tem sub-camada — é ele
    mesmo o recurso de imagem)."""
    r = _conexao(id, auth)
    tipo = _tipo_servico(r["url"])
    if tipo is None:
        raise ErroAPI(
            422, "url_sem_tipo_reconhecido",
            "a URL da conexão não termina em FeatureServer/MapServer/ImageServer",
        )
    token = _token_da_conexao(r, auth)
    try:
        doc = esri_rest.descrever_servico(r["url"], token)
    except esri_rest.ErroConector as e:
        raise ErroAPI(502, "esri_descricao_falhou", str(e)) from e
    camadas = [
        {"id": c.get("id"), "nome": c.get("name"), "tipo_geometria": c.get("geometryType")}
        for c in (doc.get("layers") or []) if isinstance(c, dict)
    ]
    tabelas = [
        {"id": t.get("id"), "nome": t.get("name")} for t in (doc.get("tables") or []) if isinstance(t, dict)
    ]
    return {
        "tipo_servico": tipo,
        "nome_servico": doc.get("mapName") or doc.get("name") or doc.get("serviceDescription"),
        "descricao": doc.get("serviceDescription") or doc.get("description"),
        "copyright_texto": doc.get("copyrightText") or None,
        "current_version": doc.get("currentVersion"),
        "camadas": camadas,
        "tabelas": tabelas,
    }


@router.get("/esri/camadas/{camada}", openapi_extra=LER)
def camada_descricao(id: str, camada: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    r = _conexao(id, auth)
    _exigir_tipo(r["url"], "FeatureServer", "MapServer")
    token = _token_da_conexao(r, auth)
    try:
        d = esri_rest.descrever_camada(_url_camada(r, camada), token)
    except esri_rest.ErroConector as e:
        raise ErroAPI(502, "esri_camada_descricao_falhou", str(e)) from e
    return {
        "nome": d.nome,
        "tipo_geometria": d.tipo_geometria,
        "max_record_count": d.max_record_count,
        "campos": [{"nome": c.nome, "tipo": c.tipo, "alias": c.alias} for c in d.campos],
        "simbologia": _simbologia_json(d.simbologia),
        "copyright_texto": d.copyright_texto,
        "descricao_servico": d.descricao_servico,
        "capacidades": list(d.capacidades),
    }


@router.get("/esri/camadas/{camada}/contagem", openapi_extra=LER)
def camada_contagem(
    id: str, camada: str, where: str = "1=1", auth: Auth = autenticado(escopo_token="catalogo:ler")
):
    r = _conexao(id, auth)
    _exigir_tipo(r["url"], "FeatureServer", "MapServer")
    token = _token_da_conexao(r, auth)
    resultado = esri_rest.contar(_url_camada(r, camada), where=where, token=token)
    if not resultado.ok:
        raise ErroAPI(502, "esri_contagem_falhou", resultado.mensagem)
    return {"total": resultado.total, "where": where}


@router.get("/esri/camadas/{camada}/feicoes", openapi_extra=LER)
def camada_feicoes(
    id: str, camada: str, where: str = "1=1", campos: str = "*", out_sr: int = Query(4326, alias="outSR"),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    r = _conexao(id, auth)
    _exigir_tipo(r["url"], "FeatureServer", "MapServer")
    token = _token_da_conexao(r, auth)
    try:
        descricao_camada = esri_rest.descrever_camada(_url_camada(r, camada), token)
        max_record_count = descricao_camada.max_record_count
    except esri_rest.ErroConector:
        max_record_count = None  # segue com o padrão da casa (limites.ESRI_REST_MAX_RECORD_COUNT_PADRAO)
    resultado = esri_rest.consultar_tudo(
        _url_camada(r, camada), where=where, out_fields=campos, out_sr=out_sr, token=token,
        max_record_count_servico=max_record_count,
    )
    if not resultado.ok:
        raise ErroAPI(502, "esri_feicoes_falhou", resultado.mensagem)
    return {
        "type": "FeatureCollection", "features": resultado.feicoes,
        "plat_paginas_lidas": resultado.paginas_lidas, "plat_truncado": resultado.truncado,
        "plat_avisos": resultado.avisos,
    }


@router.get("/esri/mapa", openapi_extra=LER)
def mapa(
    id: str, bbox: str = Query(...), largura: int = Query(512, ge=1), altura: int = Query(512, ge=1),
    out_sr: int = Query(4326, alias="outSR"), formato: str = "png32", camadas: str | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """MapServer `/export`: imagem dinâmica renderizada pelo servidor, no modo referenciado (proxy — o
    navegador nunca vê a URL original nem a credencial)."""
    r = _conexao(id, auth)
    _exigir_tipo(r["url"], "MapServer")
    token = _token_da_conexao(r, auth)
    resultado = esri_rest.exportar_mapa(
        r["url"], bbox=_bbox_de_query(bbox), largura=largura, altura=altura, out_sr=out_sr, formato=formato,
        token=token, camadas=camadas,
    )
    if not resultado.ok:
        raise ErroAPI(502, "esri_mapa_falhou", resultado.mensagem)
    return Response(content=resultado.corpo, media_type=resultado.content_type)


@router.get("/esri/imagem", openapi_extra=LER)
def imagem(
    id: str, bbox: str = Query(...), largura: int = Query(512, ge=1), altura: int = Query(512, ge=1),
    out_sr: int = Query(4326, alias="outSR"), formato: str = "png",
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """ImageServer `/exportImage`: raster referenciado, no modo referenciado (proxy)."""
    r = _conexao(id, auth)
    _exigir_tipo(r["url"], "ImageServer")
    token = _token_da_conexao(r, auth)
    resultado = esri_rest.exportar_imagem_raster(
        r["url"], bbox=_bbox_de_query(bbox), largura=largura, altura=altura, out_sr=out_sr, formato=formato,
        token=token,
    )
    if not resultado.ok:
        raise ErroAPI(502, "esri_imagem_falhou", resultado.mensagem)
    return Response(content=resultado.corpo, media_type=resultado.content_type)
