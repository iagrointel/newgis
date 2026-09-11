"""Descoberta automática de camada de uma `plat.conexao` viva (item L6-02-conectores-vivos): busca o
documento que o próprio protocolo padroniza — `GetCapabilities` (WMS/WMTS/WFS), `/collections` (OGC API -
Features) ou `?f=json` (ArcGIS REST) — e devolve a lista de camadas com nome, título, CRS e extensão
geográfica. Generaliza `app/conexao/proveniencia.py` (que só lê licença/título do MESMO documento, para a
ficha de procedência ao publicar); aqui o interesse é o CATÁLOGO de camadas em si, para cadastrar a conexão
pelo navegador e escolher o que colocar no mapa.

Mesma regra da casa (proveniencia.py): "procedência errada é pior que nenhuma" — campo que o serviço não
declara fica `None`/lista vazia, nunca um palpite. Toda busca de rede passa por
`app.conexao.seguranca.buscar_seguro` (o mesmo caminho auditado contra SSRF do teste de saúde e da
proveniência); este módulo nunca importa `httpx`/`urllib` direto.

wfs/ogc_api entram na descoberta (a "camada" é a coleção/feature type) mas NÃO no proxy de tile/imagem
(`app/conexao/proxy.py`) — são API de feição, não raster; ver `limites.CONEXAO_PROXY_TIPOS`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError  # só o TIPO da exceção; o parse em si é sempre via defusedxml

import defusedxml.ElementTree as ET_seguro

from app import limites
from app.conexao import seguranca

_PROTOCOLOS_XML = ("wms", "wmts", "wfs")
_PROTOCOLOS_JSON = ("ogc_api", "esri_rest")
_PROTOCOLOS_DESCOBRIVEIS = _PROTOCOLOS_XML + _PROTOCOLOS_JSON


@dataclass(frozen=True)
class CamadaDescoberta:
    nome: str
    titulo: str | None
    crs: list[str]
    extensao: dict | None  # {"minx","miny","maxx","maxy","crs"} geográfico/nativo, ou None se não declarado


@dataclass(frozen=True)
class ResultadoDescoberta:
    ok: bool
    mensagem: str
    url_sondada: str | None
    camadas: list[CamadaDescoberta]


def _local(tag: str) -> str:
    """remove o namespace de uma tag `{ns}Nome` -> `Nome` (WMS 1.1.1 sem ns, 1.3.0/WMTS/WFS 2.0 com ns —
    os três casam sem precisar declarar o namespace de cada serviço, que varia de casa para casa)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _bbox(minx, miny, maxx, maxy, crs: str | None) -> dict:
    return {"minx": _num(minx), "miny": _num(miny), "maxx": _num(maxx), "maxy": _num(maxy), "crs": crs}


def _url_sonda(url: str, tipo: str) -> str:
    if tipo in _PROTOCOLOS_XML:
        if "getcapabilities" in url.lower():
            return url
        servico = {"wms": "WMS", "wmts": "WMTS", "wfs": "WFS"}[tipo]
        separador = "&" if "?" in url else "?"
        return f"{url}{separador}SERVICE={servico}&REQUEST=GetCapabilities"
    if tipo == "ogc_api":
        base = url.rstrip("/")
        return base if base.endswith("/collections") else f"{base}/collections"
    if tipo == "esri_rest":
        if "f=json" in url.lower():
            return url
        separador = "&" if "?" in url else "?"
        return f"{url}{separador}f=json"
    raise ValueError(f"protocolo {tipo!r} sem descoberta automática")


# ---------------------------------------------------------------------------- WMS 1.1.1 / 1.3.0
def _wms_camadas(raiz) -> list[CamadaDescoberta]:
    capacidade = next((el for el in raiz if _local(el.tag) == "Capability"), None)
    if capacidade is None:
        return []
    achadas: list[CamadaDescoberta] = []

    def andar(el, crs_herdado: set[str]):
        crs_aqui = set(crs_herdado)
        for filho in el:
            if _local(filho.tag) in ("CRS", "SRS") and filho.text:
                crs_aqui.add(filho.text.strip())
        nome = titulo = None
        extensao = None
        for filho in el:
            rotulo = _local(filho.tag)
            if rotulo == "Name" and filho.text and nome is None:
                nome = filho.text.strip()
            elif rotulo == "Title" and filho.text:
                titulo = " ".join(filho.text.split())
            elif rotulo == "EX_GeographicBoundingBox":
                campos_geo = ("westBoundLongitude", "eastBoundLongitude", "southBoundLatitude", "northBoundLatitude")
                v = {}
                for g in filho:
                    gl = _local(g.tag)
                    if gl in campos_geo and g.text:
                        v[gl] = g.text.strip()
                if len(v) == 4:
                    extensao = _bbox(
                        v["westBoundLongitude"], v["southBoundLatitude"],
                        v["eastBoundLongitude"], v["northBoundLatitude"], "EPSG:4326",
                    )
            elif rotulo == "LatLonBoundingBox" and extensao is None:
                a = filho.attrib
                if all(k in a for k in ("minx", "miny", "maxx", "maxy")):
                    extensao = _bbox(a["minx"], a["miny"], a["maxx"], a["maxy"], "EPSG:4326")
        if nome:
            achadas.append(CamadaDescoberta(nome=nome, titulo=titulo or nome, crs=sorted(crs_aqui), extensao=extensao))
        for filho in el:
            if _local(filho.tag) == "Layer":
                andar(filho, crs_aqui)

    for filho in capacidade:
        if _local(filho.tag) == "Layer":
            andar(filho, set())
    return achadas


# ---------------------------------------------------------------------------- WMTS 1.0.0
def _wmts_camadas(raiz) -> list[CamadaDescoberta]:
    # TileMatrixSet DEFINIDO (dentro de Contents, irmão dos Layer — não filho da raiz; por isso `.iter()`
    # em vez de percorrer só os filhos diretos), com ows:Identifier + ows:SupportedCRS: nome -> CRS. Os
    # <TileMatrixSetLink><TileMatrixSet> dentro de cada Layer só citam o NOME (sem filhos, só texto); sem
    # este mapa a coluna crs ficaria com o nome do conjunto de matrizes ("GoogleMapsCompatible"), não o
    # código de CRS de verdade — o filtro `ident and crs` abaixo já descarta essas referências sem filhos.
    tms_crs: dict[str, str] = {}
    for el in raiz.iter():
        if _local(el.tag) != "TileMatrixSet":
            continue
        ident = crs = None
        for f in el:
            rotulo = _local(f.tag)
            if rotulo == "Identifier" and f.text:
                ident = f.text.strip()
            elif rotulo == "SupportedCRS" and f.text:
                crs = f.text.strip()
        if ident and crs:
            tms_crs[ident] = crs

    conteudo = next((el for el in raiz if _local(el.tag) == "Contents"), None)
    if conteudo is None:
        return []
    achadas: list[CamadaDescoberta] = []
    for camada in conteudo:
        if _local(camada.tag) != "Layer":
            continue
        nome = titulo = None
        extensao = None
        crs_set: set[str] = set()
        for f in camada:
            rotulo = _local(f.tag)
            if rotulo == "Identifier" and f.text and nome is None:
                nome = f.text.strip()
            elif rotulo == "Title" and f.text:
                titulo = " ".join(f.text.split())
            elif rotulo == "WGS84BoundingBox":
                minimo = maximo = None
                for g in f:
                    gl = _local(g.tag)
                    if gl == "LowerCorner" and g.text:
                        minimo = g.text.split()
                    elif gl == "UpperCorner" and g.text:
                        maximo = g.text.split()
                if minimo and maximo and len(minimo) == 2 and len(maximo) == 2:
                    extensao = _bbox(minimo[0], minimo[1], maximo[0], maximo[1], "EPSG:4326")
            elif rotulo == "TileMatrixSetLink":
                for g in f:
                    if _local(g.tag) == "TileMatrixSet" and g.text:
                        nome_tms = g.text.strip()
                        crs_set.add(tms_crs.get(nome_tms, nome_tms))
        if nome:
            achadas.append(CamadaDescoberta(nome=nome, titulo=titulo or nome, crs=sorted(crs_set), extensao=extensao))
    return achadas


# ---------------------------------------------------------------------------- WFS 2.0
def _wfs_camadas(raiz) -> list[CamadaDescoberta]:
    lista = next((el for el in raiz if _local(el.tag) == "FeatureTypeList"), None)
    if lista is None:
        return []
    achadas: list[CamadaDescoberta] = []
    for tipo_feicao in lista:
        if _local(tipo_feicao.tag) != "FeatureType":
            continue
        nome = titulo = None
        extensao = None
        crs_set: set[str] = set()
        for f in tipo_feicao:
            rotulo = _local(f.tag)
            if rotulo == "Name" and f.text:
                nome = f.text.strip()
            elif rotulo == "Title" and f.text:
                titulo = " ".join(f.text.split())
            elif rotulo in ("DefaultCRS", "DefaultSRS", "OtherCRS", "OtherSRS") and f.text:
                crs_set.add(f.text.strip())
            elif rotulo == "WGS84BoundingBox":
                minimo = maximo = None
                for g in f:
                    gl = _local(g.tag)
                    if gl == "LowerCorner" and g.text:
                        minimo = g.text.split()
                    elif gl == "UpperCorner" and g.text:
                        maximo = g.text.split()
                if minimo and maximo and len(minimo) == 2 and len(maximo) == 2:
                    extensao = _bbox(minimo[0], minimo[1], maximo[0], maximo[1], "EPSG:4326")
        if nome:
            achadas.append(CamadaDescoberta(nome=nome, titulo=titulo or nome, crs=sorted(crs_set), extensao=extensao))
    return achadas


# ---------------------------------------------------------------------------- OGC API - Features
def _ogc_api_camadas(doc: dict) -> list[CamadaDescoberta]:
    achadas: list[CamadaDescoberta] = []
    for colecao in doc.get("collections") or []:
        if not isinstance(colecao, dict):
            continue
        nome = colecao.get("id")
        if not nome:
            continue
        titulo = colecao.get("title") or nome
        crs = colecao.get("crs") or ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"]
        if not isinstance(crs, list):
            crs = [str(crs)]
        extensao = None
        espacial = ((colecao.get("extent") or {}).get("spatial") or {})
        caixas = espacial.get("bbox")
        if isinstance(caixas, list) and caixas and isinstance(caixas[0], list) and len(caixas[0]) >= 4:
            v = caixas[0]
            extensao = _bbox(v[0], v[1], v[2], v[3], espacial.get("crs") or "CRS84")
        achadas.append(CamadaDescoberta(nome=str(nome), titulo=titulo, crs=[str(c) for c in crs], extensao=extensao))
    return achadas


# ------------------------------------------------------------------ ArcGIS REST (MapServer/FeatureServer/ImageServer)
def _esri_rest_camadas(doc: dict) -> list[CamadaDescoberta]:
    sr = doc.get("spatialReference") or {}
    wkid = sr.get("latestWkid") or sr.get("wkid")
    crs = [f"EPSG:{wkid}"] if wkid else []
    extensao = None
    extensao_bruta = doc.get("fullExtent") or doc.get("initialExtent") or {}
    if all(k in extensao_bruta for k in ("xmin", "ymin", "xmax", "ymax")):
        sr_extensao = extensao_bruta.get("spatialReference") or sr
        wkid_extensao = sr_extensao.get("latestWkid") or sr_extensao.get("wkid")
        extensao = _bbox(
            extensao_bruta["xmin"], extensao_bruta["ymin"], extensao_bruta["xmax"], extensao_bruta["ymax"],
            f"EPSG:{wkid_extensao}" if wkid_extensao else None,
        )
    camadas_doc = doc.get("layers")
    achadas: list[CamadaDescoberta] = []
    if isinstance(camadas_doc, list) and camadas_doc:
        # `layers` do serviço raiz do MapServer/FeatureServer não traz extensão por sub-camada (só a do
        # serviço inteiro, `fullExtent`, herdada aqui) nem CRS por sub-camada — limitação documentada, não
        # escondida (a ficha da camada mostra a mesma extensão/CRS do serviço para todas as sub-camadas).
        for camada in camadas_doc:
            if not isinstance(camada, dict):
                continue
            nome = camada.get("name")
            if not nome:
                continue
            identificador = camada.get("id")
            achadas.append(CamadaDescoberta(
                nome=str(identificador) if identificador is not None else str(nome),
                titulo=str(nome), crs=crs, extensao=extensao,
            ))
    else:
        nome = doc.get("name") or "camada"
        achadas.append(CamadaDescoberta(
            nome=str(nome), titulo=doc.get("description") or str(nome), crs=crs, extensao=extensao,
        ))
    return achadas


def descobrir_camadas(conexao: dict) -> ResultadoDescoberta:
    """`conexao` precisa de `tipo` e `url` (a linha de `plat.conexao` basta). Nunca levanta: qualquer falha de
    rede/parse/protocolo sem descoberta vira `ok=False` com o motivo em `mensagem` — quem chama decide se é
    422 (protocolo sem descoberta) ou 502 (serviço não respondeu/documento ilegível)."""
    tipo, url = conexao["tipo"], conexao["url"]
    if tipo not in _PROTOCOLOS_DESCOBRIVEIS:
        return ResultadoDescoberta(
            ok=False, mensagem=f"protocolo {tipo!r} não tem descoberta automática de camadas",
            url_sondada=None, camadas=[],
        )
    alvo = _url_sonda(url, tipo)
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_DESCOBERTA_TIMEOUT_S,
        max_bytes=limites.CONEXAO_DESCOBERTA_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok:
        return ResultadoDescoberta(ok=False, mensagem=r.mensagem, url_sondada=alvo, camadas=[])
    if not r.corpo:
        return ResultadoDescoberta(ok=False, mensagem="resposta_vazia", url_sondada=alvo, camadas=[])
    try:
        if tipo in _PROTOCOLOS_XML:
            raiz = ET_seguro.fromstring(r.corpo)  # nunca resolve entidade externa (defusedxml)
            camadas = {"wms": _wms_camadas, "wmts": _wmts_camadas, "wfs": _wfs_camadas}[tipo](raiz)
        else:
            doc = json.loads(r.corpo.decode("utf-8", errors="replace"))
            if not isinstance(doc, dict):
                return ResultadoDescoberta(
                    ok=False, mensagem="resposta_nao_e_objeto_json", url_sondada=alvo, camadas=[],
                )
            camadas = _ogc_api_camadas(doc) if tipo == "ogc_api" else _esri_rest_camadas(doc)
    except (ParseError, ValueError, UnicodeDecodeError, RecursionError) as e:
        return ResultadoDescoberta(
            ok=False, mensagem=f"erro_ao_interpretar:{type(e).__name__}", url_sondada=alvo, camadas=[],
        )
    if not camadas:
        return ResultadoDescoberta(
            ok=False, mensagem="nenhuma_camada_encontrada_no_documento", url_sondada=alvo, camadas=[],
        )
    camadas = camadas[: limites.CONEXAO_DESCOBERTA_CAMADAS_MAX]
    return ResultadoDescoberta(
        ok=True, mensagem=f"{len(camadas)} camada(s) em {alvo}", url_sondada=alvo, camadas=camadas,
    )
