"""Conector de WMS (1.1.1/1.3.0) e WMTS (KVP e RESTful) externos (item L6-02-b-wms-wmts; ADR 0019).

Regra dura herdada de `app.conexao.seguranca` (item L6-02-a): toda operação de rede passa por `buscar_seguro`.
Nenhum cliente HTTP próprio, nenhum `httpx`/`urllib` direto. Sem `owslib` — não está instalado nesta máquina
(a análise de GetCapabilities é feita à mão, com `defusedxml`, que nunca resolve entidade externa — é a defesa
contra XXE que o adversário deste item testa com um documento de 40 MiB e uma entidade externa).

O que o módulo faz:
  - `capacidades_wms`     — baixa e interpreta o GetCapabilities WMS (1.1.1 ou 1.3.0: a versão vem do atributo
    `version` da raiz do documento, nunca de um parâmetro que o chamador precise adivinhar), monta a árvore de
    camadas com herança de CRS/estilo/bbox do `<Layer>` pai (WMS permite declarar CRS só uma vez no topo e toda
    camada filha herdar), e devolve `Camada.bbox_lonlat` SEMPRE em (minx, miny, maxx, maxy) — ordem lon/lat —
    mesmo que a fonte declare a caixa em ordem lat/lon (WMS 1.3.0 exige eixo lat/lon para CRS geográfico,
    EPSG:4326 incluído; ver `_EIXO_LAT_LON_1_3_0` e `_normalizar_bbox`).
  - `url_getmap`          — monta a URL de GetMap para a versão/CRS certos, trocando a ordem do BBOX quando a
    versão é 1.3.0 e o CRS pedido é dos que declaram eixo lat/lon (o mesmo cuidado, na direção contrária).
  - `url_getfeatureinfo`  — idem para GetFeatureInfo (pixel `i`/`j` em 1.3.0, `x`/`y` em 1.1.1).
  - `capacidades_wmts`    — baixa e interpreta o GetCapabilities WMTS: `Contents/Layer` (formatos, estilos,
    `TileMatrixSetLink`) e `Contents/TileMatrixSet` (CRS, cada nível com `ScaleDenominator`/`TopLeftCorner`/
    `TileWidth`/`TileHeight`/`MatrixWidth`/`MatrixHeight`); detecta modelo KVP (`ResourceType="KVP"` em
    `OperationsMetadata/GetTile`) e/ou RESTful (`ResourceURL` no `Layer`, com `{TileMatrix}`/`{TileRow}`/
    `{TileCol}`).
  - `url_wmts_tile_direta`      — quando o `TileMatrixSet` já é o esquema padrão do mapa (EPSG:3857/Web
    Mercator, `GoogleMapsCompatible`/`EPSG:3857`/`WebMercatorQuad`), monta o TEMPLATE `{z}/{x}/{y}` (KVP ou
    RESTful) que o MapLibre consome DIRETO como `raster` source — sem passar pelo proxy desta trilha, porque
    não há reprojeção nenhuma a fazer.
  - `mosaico_tile_reprojetado`  — quando o `TileMatrixSet` é outro CRS (o caso do adversário: só EPSG:4674),
    busca o(s) tile(s) nativos que cobrem o tile-alvo 3857 padrão, monta um mosaico georreferenciado com
    `rasterio` e reprojeta para EPSG:3857 — usado pela rota de proxy (`app/conexao/rotas_wms_wmts.py`), que
    marca a resposta como reprojetada.
  - `reprojetar_imagem`  — idem para uma imagem GetMap já baixada num CRS que não é 3857/4326 (o outro caso do
    portão: "serviço só em EPSG:4674 funciona via proxy").

Fronteira honesta (o que NÃO faz): não fala WMS 1.0 (Studies mostram que é raríssimo em serviço público
brasileiro); WMTS RESTful só entende o padrão de template com chaves `{...}` (não infere um padrão livre não
declarado); a reprojeção de tile usa reamostragem `nearest` (mais rápida, adequada a mapa de fundo; não é
avaliação radiométrica) e limita a 4 tiles nativos por tile de saída (`_MAX_TILES_MOSAICO`) — mais que isso
é sinal de descompasso grande de zoom entre o TileMatrixSet nativo e o alvo, e a resposta volta com o aviso
`mosaico_parcial` em vez de tentar buscar um número não travado de tiles (a mesma lógica de "nunca vira jeito
de esgotar a máquina" do resto de `app.conexao`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from xml.etree.ElementTree import Element, ParseError

import defusedxml.ElementTree as ET_seguro
import numpy as np
from rasterio.crs import CRS as RasterioCRS
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

from app import limites
from app.conexao import seguranca

# --- constantes de protocolo -------------------------------------------------------------------------------

_NS_ANY = re.compile(r"^\{[^}]*\}")
_EPSG3857 = ("EPSG:3857", "EPSG:900913", "OSGEO:41001")
_EPSG4326 = ("EPSG:4326", "CRS:84", "OGC:CRS84")
# CRS/SRS cujo eixo declarado em WMS 1.3.0 é (lat, lon) / (norte, leste) — Anexo B da especificação OGC
# 06-042 (o WMS 1.3.0 obedece à ordem de eixo da AUTORIDADE; para EPSG:4326 e EPSG:4674 (SIRGAS 2000
# geográfico, usado pelo Brasil) essa ordem é lat/lon). CRS:84 e EPSG:3857 continuam lon/lat (leste/norte).
_EIXO_LAT_LON_1_3_0 = {"EPSG:4326", "EPSG:4674", "EPSG:4269", "EPSG:4258"}
_MAX_TILES_MOSAICO = 4
TAMANHO_TILE_PADRAO = 256


class ErroConector(Exception):
    def __init__(self, motivo: str, detalhe: str = ""):
        self.motivo = motivo
        self.detalhe = detalhe
        super().__init__(f"{motivo}: {detalhe}" if detalhe else motivo)


# --- modelos de dados ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Estilo:
    nome: str
    titulo: str | None = None


@dataclass(frozen=True)
class Camada:
    nome: str | None  # None = camada de agrupamento, sem `<Name>`; nunca pedida direto num GetMap
    titulo: str
    resumo: str | None
    crs_suportados: tuple[str, ...]
    estilos: tuple[Estilo, ...]
    bbox_lonlat: tuple[float, float, float, float] | None  # (minx, miny, maxx, maxy) — sempre lon/lat
    consultavel: bool  # `queryable="1"` — GetFeatureInfo só faz sentido nessas
    filhas: tuple["Camada", ...] = field(default_factory=tuple)

    def achatada(self) -> list["Camada"]:
        """toda camada com nome (folhas E nós intermediários nomeados), em ordem de documento — é o que a
        tela do item lista para o usuário escolher."""
        saida: list[Camada] = []
        if self.nome:
            saida.append(self)
        for filha in self.filhas:
            saida.extend(filha.achatada())
        return saida


@dataclass(frozen=True)
class CapacidadesWMS:
    versao: str  # "1.1.1" ou "1.3.0"
    titulo: str | None
    url_getmap: str
    url_getfeatureinfo: str | None
    formatos_getmap: tuple[str, ...]
    formatos_getfeatureinfo: tuple[str, ...]
    camadas: tuple[Camada, ...]

    def por_nome(self, nome: str) -> Camada:
        for c in self.camadas:
            for folha in c.achatada():
                if folha.nome == nome:
                    return folha
        raise ErroConector("camada_inexistente", nome)


@dataclass(frozen=True)
class NivelMatriz:
    identificador: str
    escala_denominador: float
    topo_esquerdo: tuple[float, float]  # (x, y) = (leste/lon, norte/lat) SEMPRE — já normalizado na análise
    largura_tile: int
    altura_tile: int
    largura_matriz: int
    altura_matriz: int


@dataclass(frozen=True)
class TileMatrixSet:
    identificador: str
    crs: str
    niveis: tuple[NivelMatriz, ...]

    def nativo_3857(self) -> bool:
        return _normalizar_crs(self.crs) in _EPSG3857


@dataclass(frozen=True)
class CamadaWMTS:
    nome: str
    titulo: str
    formatos: tuple[str, ...]
    estilo_padrao: str
    tile_matrix_sets: tuple[str, ...]
    template_restful: str | None  # com {TileMatrix}/{TileRow}/{TileCol}/{Style}/{TileMatrixSet}, se houver


@dataclass(frozen=True)
class CapacidadesWMTS:
    titulo: str | None
    url_kvp: str | None  # None = serviço só RESTful
    camadas: tuple[CamadaWMTS, ...]
    tile_matrix_sets: dict[str, TileMatrixSet]

    def camada(self, nome: str) -> CamadaWMTS:
        for c in self.camadas:
            if c.nome == nome:
                return c
        raise ErroConector("camada_inexistente", nome)


# --- utilidades de XML ---------------------------------------------------------------------------------------


def _local(tag: str) -> str:
    return _NS_ANY.sub("", tag)


def _filhos(el: Element, nome: str) -> list[Element]:
    return [f for f in el if _local(f.tag) == nome]


def _filho(el: Element, nome: str) -> Element | None:
    fs = _filhos(el, nome)
    return fs[0] if fs else None


def _texto(el: Element | None, nome: str) -> str | None:
    if el is None:
        return None
    f = _filho(el, nome)
    if f is None or f.text is None:
        return None
    t = f.text.strip()
    return t or None


_URN_CRS = re.compile(r"^URN:OGC:DEF:CRS:([A-Z0-9]+):[^:]*:([A-Z0-9]+)$")


def _normalizar_crs(crs: str) -> str:
    """`SupportedCRS` do WMTS vem em forma URN (`urn:ogc:def:crs:EPSG:6.3:3857`, com o número do MEIO sendo
    a VERSÃO da definição, não parte do código — BDGEx e outros GeoWebCache declaram assim); a forma curta
    `urn:ogc:def:crs:EPSG::3857` (sem versão) também existe. As duas viram `EPSG:3857`."""
    v = crs.strip().upper()
    m = _URN_CRS.match(v)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return v.replace("URN:OGC:DEF:CRS:", "").replace("::", ":")


def _parse_xml_seguro(corpo: bytes) -> Element:
    try:
        return ET_seguro.fromstring(corpo)
    except (ParseError, ValueError) as e:
        raise ErroConector("xml_invalido", str(e)) from e


# --- WMS: GetCapabilities -------------------------------------------------------------------------------------


def _bbox_geografico(layer: Element, versao: str) -> tuple[float, float, float, float] | None:
    """Prioridade: `EX_GeographicBoundingBox` (1.3.0, já lon/lat, sem ambiguidade de eixo) > `LatLonBoundingBox`
    (1.1.1, atributos, já lon/lat) > `BoundingBox` com CRS geográfico (aí sim depende da versão/eixo)."""
    geo = _filho(layer, "EX_GeographicBoundingBox")
    if geo is not None:
        oeste = _texto(geo, "westBoundLongitude")
        leste = _texto(geo, "eastBoundLongitude")
        sul = _texto(geo, "southBoundLatitude")
        norte = _texto(geo, "northBoundLatitude")
        if None not in (oeste, leste, sul, norte):
            return (float(oeste), float(sul), float(leste), float(norte))
    latlon = _filho(layer, "LatLonBoundingBox")
    if latlon is not None and all(k in latlon.attrib for k in ("minx", "miny", "maxx", "maxy")):
        return (
            float(latlon.attrib["minx"]), float(latlon.attrib["miny"]),
            float(latlon.attrib["maxx"]), float(latlon.attrib["maxy"]),
        )
    for bb in _filhos(layer, "BoundingBox"):
        crs = bb.attrib.get("CRS") or bb.attrib.get("SRS")
        if crs and _normalizar_crs(crs) in _EPSG4326:
            minx, miny = float(bb.attrib["minx"]), float(bb.attrib["miny"])
            maxx, maxy = float(bb.attrib["maxx"]), float(bb.attrib["maxy"])
            if versao == "1.3.0" and _normalizar_crs(crs) in _EIXO_LAT_LON_1_3_0:
                # a fonte já escreveu minx/miny como (lat, lon) — devolve normalizado em (lon, lat)
                return (miny, minx, maxy, maxx)
            return (minx, miny, maxx, maxy)
    return None


def _estilos(layer: Element) -> tuple[Estilo, ...]:
    saida = []
    for st in _filhos(layer, "Style"):
        nome = _texto(st, "Name")
        if nome:
            saida.append(Estilo(nome=nome, titulo=_texto(st, "Title") or nome))
    return tuple(saida)


def _crs_da_camada(layer: Element, versao: str) -> tuple[str, ...]:
    tag = "CRS" if versao == "1.3.0" else "SRS"
    vistos: list[str] = []
    for el in _filhos(layer, tag):
        if el.text:
            v = _normalizar_crs(el.text)
            if v not in vistos:
                vistos.append(v)
    return tuple(vistos)


def _percorrer_layer(layer: Element, versao: str, crs_herdados: tuple[str, ...]) -> Camada:
    crs_proprios = _crs_da_camada(layer, versao)
    crs = tuple(dict.fromkeys((*crs_herdados, *crs_proprios)))  # união preservando ordem, sem repetir
    filhas = tuple(_percorrer_layer(f, versao, crs) for f in _filhos(layer, "Layer"))
    return Camada(
        nome=_texto(layer, "Name"),
        titulo=_texto(layer, "Title") or _texto(layer, "Name") or "",
        resumo=_texto(layer, "Abstract"),
        crs_suportados=crs,
        estilos=_estilos(layer),
        bbox_lonlat=_bbox_geografico(layer, versao),
        consultavel=layer.attrib.get("queryable") == "1",
        filhas=filhas,
    )


def _operacao(raiz: Element, nome: str) -> tuple[Element | None, tuple[str, ...]]:
    cap = _filho(raiz, "Capability")
    req = _filho(cap, "Request") if cap is not None else None
    op = _filho(req, nome) if req is not None else None
    if op is None:
        return None, ()
    formatos = tuple(f.text.strip() for f in _filhos(op, "Format") if f.text)
    return op, formatos


def _href_get(op: Element | None) -> str | None:
    """`href` mora no `OnlineResource` FILHO de `<Get>` (WMS 1.1.1/1.3.0), nunca em `<Get>` diretamente;
    para WMTS KVP (`ows:Get`) o `href` vem no próprio elemento `Get` — cobre os dois formatos."""
    if op is None:
        return None
    dcp_tipo = _filho(op, "DCPType")
    dcp = dcp_tipo if dcp_tipo is not None else _filho(op, "DCP")
    http = (_filho(dcp, "HTTP") if dcp is not None else None)
    get = _filho(http, "Get") if http is not None else None
    if get is None:
        return None
    for k, v in get.attrib.items():
        if _local(k) == "href":
            return v
    online = _filho(get, "OnlineResource")
    if online is not None:
        for k, v in online.attrib.items():
            if _local(k) == "href":
                return v
    return None


def analisar_wms(corpo: bytes, url_base: str) -> CapacidadesWMS:
    """Só a análise (sem rede): usada direto pelos testes de fixture e por `capacidades_wms` depois do
    download. `defusedxml` nunca resolve entidade externa, qualquer que seja o tamanho do documento — a
    proteção contra XXE independe de já termos travado o tamanho em `buscar_seguro`."""
    raiz = _parse_xml_seguro(corpo)
    versao = raiz.attrib.get("version", "1.3.0")
    cap = _filho(raiz, "Capability")
    if cap is None:
        raise ErroConector("wms_sem_capability", url_base)
    servico = _filho(raiz, "Service")
    titulo = _texto(servico, "Title") if servico is not None else None
    op_map, fmts_map = _operacao(raiz, "GetMap")
    op_info, fmts_info = _operacao(raiz, "GetFeatureInfo")
    url_getmap = _href_get(op_map) or url_base
    url_getfeatureinfo = _href_get(op_info)
    camada_raiz = _filho(cap, "Layer")
    camadas = (_percorrer_layer(camada_raiz, versao, ()),) if camada_raiz is not None else ()
    return CapacidadesWMS(
        versao=versao, titulo=titulo, url_getmap=url_getmap, url_getfeatureinfo=url_getfeatureinfo,
        formatos_getmap=fmts_map, formatos_getfeatureinfo=fmts_info, camadas=camadas,
    )


def capacidades_wms(url_base: str) -> CapacidadesWMS:
    alvo = _url_com_operacao(url_base, "WMS", "GetCapabilities")
    r = seguranca.buscar_seguro(
        alvo, guardar_corpo=True,
        timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_WMS_CAPACIDADES_TIMEOUT_S,
        max_bytes=limites.CONEXAO_WMS_CAPACIDADES_MAX_BYTES,
    )
    if not r.ok:
        raise ErroConector("wms_capabilities_falhou", r.mensagem)
    return analisar_wms(r.corpo, url_base)


def _url_com_operacao(url: str, servico: str, operacao: str) -> str:
    baixa = url.lower()
    if "request=" in baixa:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}SERVICE={servico}&REQUEST={operacao}"


# --- WMS: GetMap / GetFeatureInfo ------------------------------------------------------------------------------


def _bbox_str(bbox: tuple[float, float, float, float], versao: str, crs: str) -> str:
    minx, miny, maxx, maxy = bbox
    if versao == "1.3.0" and _normalizar_crs(crs) in _EIXO_LAT_LON_1_3_0:
        return f"{miny},{minx},{maxy},{maxx}"
    return f"{minx},{miny},{maxx},{maxy}"


def url_getmap(
    cap: CapacidadesWMS, *, camada: str, crs: str, bbox: tuple[float, float, float, float],
    largura: int, altura: int, formato: str = "image/png", estilo: str = "", transparente: bool = True,
) -> str:
    largura_ok = 0 < largura <= limites.CONEXAO_WMS_LARGURA_MAX
    altura_ok = 0 < altura <= limites.CONEXAO_WMS_ALTURA_MAX
    if not (largura_ok and altura_ok):
        raise ErroConector("dimensao_invalida", f"{largura}x{altura}")
    tag_crs = "CRS" if cap.versao == "1.3.0" else "SRS"
    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": cap.versao, "LAYERS": camada, "STYLES": estilo,
        tag_crs: crs, "BBOX": _bbox_str(bbox, cap.versao, crs), "WIDTH": str(largura), "HEIGHT": str(altura),
        "FORMAT": formato, "TRANSPARENT": "TRUE" if transparente else "FALSE",
    }
    return _com_query(cap.url_getmap, params)


def url_getfeatureinfo(
    cap: CapacidadesWMS, *, camada: str, crs: str, bbox: tuple[float, float, float, float],
    largura: int, altura: int, coluna: int, linha: int, formato_info: str = "application/json",
    estilo: str = "",
) -> str:
    if not cap.url_getfeatureinfo:
        raise ErroConector("sem_getfeatureinfo", camada)
    tag_crs = "CRS" if cap.versao == "1.3.0" else "SRS"
    tag_i, tag_j = ("I", "J") if cap.versao == "1.3.0" else ("X", "Y")
    params = {
        "SERVICE": "WMS", "REQUEST": "GetFeatureInfo", "VERSION": cap.versao,
        "LAYERS": camada, "QUERY_LAYERS": camada, "STYLES": estilo, tag_crs: crs,
        "BBOX": _bbox_str(bbox, cap.versao, crs), "WIDTH": str(largura), "HEIGHT": str(altura),
        tag_i: str(coluna), tag_j: str(linha), "INFO_FORMAT": formato_info, "FEATURE_COUNT": "10",
    }
    return _com_query(cap.url_getfeatureinfo, params)


def _com_query(url: str, params: dict[str, str]) -> str:
    from urllib.parse import quote

    separador = "&" if "?" in url else "?"
    # `safe` inclui `{}` porque os templates de tile KVP (`url_wmts_tile_direta`) passam `{z}`/`{x}`/`{y}`
    # como VALOR — têm de sobreviver literais para o MapLibre substituir depois, nunca virar `%7Bz%7D`.
    qs = "&".join(f"{k}={quote(str(v), safe=',:{}')}" for k, v in params.items())
    return f"{url}{separador}{qs}"


# --- WMTS: GetCapabilities -----------------------------------------------------------------------------------


def _tile_matrix_set(el: Element) -> TileMatrixSet:
    """`TopLeftCorner` (WMTS 1.0.0, tabela 7) vem na ordem de eixo do PRÓPRIO CRS declarado em
    `SupportedCRS` — para as autoridades geográficas de `_EIXO_LAT_LON_1_3_0` (EPSG:4326/4674/4269/4258,
    a mesma lista da inversão do WMS 1.3.0) isso é (lat, lon), não (x, y); o BDGEx (Exército) é a prova viva
    disto: `TopLeftCorner` chega como "26.27 -125.0" — lat=26,27/lon=-125, não x=26,27. `NivelMatriz.
    topo_esquerdo` normaliza para (x, y) = (leste/lon, norte/lat) SEMPRE, para casar com `bbox_lonlat` do WMS
    e com o resto do módulo (que só entende x/y); sem isso `mosaico_tile_reprojetado` calcula span/índice de
    tile com eixo trocado e produz recorte vazio (dimensão negativa)."""
    identificador = _texto(el, "Identifier") or ""
    crs = _normalizar_crs(_texto(el, "SupportedCRS") or "")
    eixo_lat_lon = crs in _EIXO_LAT_LON_1_3_0
    niveis = []
    for tm in _filhos(el, "TileMatrix"):
        topo = (_texto(tm, "TopLeftCorner") or "0 0").split()
        a, b = (float(topo[0]), float(topo[1])) if len(topo) == 2 else (0.0, 0.0)
        topo_xy = (b, a) if eixo_lat_lon else (a, b)
        niveis.append(NivelMatriz(
            identificador=_texto(tm, "Identifier") or "",
            escala_denominador=float(_texto(tm, "ScaleDenominator") or 0),
            topo_esquerdo=topo_xy,
            largura_tile=int(_texto(tm, "TileWidth") or TAMANHO_TILE_PADRAO),
            altura_tile=int(_texto(tm, "TileHeight") or TAMANHO_TILE_PADRAO),
            largura_matriz=int(_texto(tm, "MatrixWidth") or 0),
            altura_matriz=int(_texto(tm, "MatrixHeight") or 0),
        ))
    niveis.sort(key=lambda n: n.escala_denominador, reverse=True)
    return TileMatrixSet(identificador=identificador, crs=crs, niveis=tuple(niveis))


def _template_restful(layer: Element) -> str | None:
    for ru in _filhos(layer, "ResourceURL"):
        if ru.attrib.get("resourceType") == "tile":
            return ru.attrib.get("template")
    return None


def _camada_wmts(layer: Element) -> CamadaWMTS:
    formatos = tuple(f.text.strip() for f in _filhos(layer, "Format") if f.text)
    tms = tuple(
        _texto(link, "TileMatrixSet") or ""
        for link in _filhos(layer, "TileMatrixSetLink")
    )
    estilo_padrao = ""
    for st in _filhos(layer, "Style"):
        if st.attrib.get("isDefault") == "true" or not estilo_padrao:
            estilo_padrao = _texto(st, "Identifier") or ""
        if st.attrib.get("isDefault") == "true":
            break
    return CamadaWMTS(
        nome=_texto(layer, "Identifier") or "",
        titulo=_texto(layer, "Title") or _texto(layer, "Identifier") or "",
        formatos=formatos, estilo_padrao=estilo_padrao, tile_matrix_sets=tuple(t for t in tms if t),
        template_restful=_template_restful(layer),
    )


def analisar_wmts(corpo: bytes, url_base: str) -> CapacidadesWMTS:
    """Só a análise (sem rede) — ver `analisar_wms`."""
    raiz = _parse_xml_seguro(corpo)
    servico = _filho(raiz, "ServiceIdentification")
    titulo = _texto(servico, "Title") if servico is not None else None
    contents = _filho(raiz, "Contents")
    if contents is None:
        raise ErroConector("wmts_sem_contents", url_base)
    camadas = tuple(_camada_wmts(layer) for layer in _filhos(contents, "Layer"))
    tile_matrix_sets = {
        tms.identificador: tms for tms in (_tile_matrix_set(el) for el in _filhos(contents, "TileMatrixSet"))
    }
    url_kvp = _href_get_wmts(raiz, "GetTile")
    return CapacidadesWMTS(titulo=titulo, url_kvp=url_kvp, camadas=camadas, tile_matrix_sets=tile_matrix_sets)


def _href_get_wmts(raiz: Element, nome_operacao: str) -> str | None:
    """WMTS declara operação em `ows:OperationsMetadata/ows:Operation[@name=...]/ows:DCP/ows:HTTP/ows:Get`
    (nada a ver com `Capability/Request` do WMS — por isso `_operacao`, feita para WMS, nunca encontra nada
    aqui). `href` fica direto no atributo do `ows:Get` (diferente do `OnlineResource` filho do WMS)."""
    om = _filho(raiz, "OperationsMetadata")
    if om is None:
        return None
    for operacao in _filhos(om, "Operation"):
        if operacao.attrib.get("name") != nome_operacao:
            continue
        dcp = _filho(operacao, "DCP")
        http = _filho(dcp, "HTTP") if dcp is not None else None
        get = _filho(http, "Get") if http is not None else None
        if get is None:
            continue
        for k, v in get.attrib.items():
            if _local(k) == "href":
                return v
    return None


def capacidades_wmts(url_base: str) -> CapacidadesWMTS:
    alvo = _url_com_operacao(url_base, "WMTS", "GetCapabilities")
    r = seguranca.buscar_seguro(
        alvo, guardar_corpo=True,
        timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_WMS_CAPACIDADES_TIMEOUT_S,
        max_bytes=limites.CONEXAO_WMS_CAPACIDADES_MAX_BYTES,
    )
    if not r.ok:
        raise ErroConector("wmts_capabilities_falhou", r.mensagem)
    return analisar_wmts(r.corpo, url_base)


# --- WMTS: template direto (TileMatrixSet já em EPSG:3857) --------------------------------------------------


def url_wmts_tile_direta(cap: CapacidadesWMTS, *, camada: str, tile_matrix_set: str, formato: str) -> str:
    """Devolve o TEMPLATE `{z}/{x}/{y}` que o MapLibre usa direto como `raster` source (sem proxy): só é
    chamada depois de confirmar `tile_matrix_set` como nativo 3857 (`TileMatrixSet.nativo_3857()`)."""
    c = cap.camada(camada)
    if c.template_restful:
        return (
            c.template_restful
            .replace("{TileMatrixSet}", tile_matrix_set)
            .replace("{TileMatrix}", "{z}")
            .replace("{TileRow}", "{y}")
            .replace("{TileCol}", "{x}")
            .replace("{Style}", c.estilo_padrao or "default")
        )
    if not cap.url_kvp:
        raise ErroConector("wmts_sem_url_de_tile", camada)
    params = {
        "SERVICE": "WMTS", "REQUEST": "GetTile", "VERSION": "1.0.0", "LAYER": camada,
        "STYLE": c.estilo_padrao or "default", "TILEMATRIXSET": tile_matrix_set,
        "TILEMATRIX": "{z}", "TILEROW": "{y}", "TILECOL": "{x}", "FORMAT": formato,
    }
    return _com_query(cap.url_kvp, params)


# --- WMTS: mosaico + reprojeção (TileMatrixSet fora de EPSG:3857) -------------------------------------------


def _envoltoria_tile_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """bbox padrão do tile z/x/y do esquema slippy (EPSG:3857), em metros."""
    n = 2**z
    origem = 20037508.342789244
    passo = 2 * origem / n
    minx = -origem + x * passo
    maxx = -origem + (x + 1) * passo
    maxy = origem - y * passo
    miny = origem - (y + 1) * passo
    return (minx, miny, maxx, maxy)


def _nivel_mais_perto(tms: TileMatrixSet, resolucao_alvo_m: float, crs_metros: bool) -> NivelMatriz:
    """resolução do WMTS é sempre `ScaleDenominator * 0.00028` metros/pixel (padrão OGC), mesmo em CRS
    geográfico (aí o resultado é aproximado em graus via fator de conversão — suficiente para escolher o
    nível mais próximo, não para navegação de precisão)."""
    melhor = tms.niveis[0]
    menor_diff = float("inf")
    for nivel in tms.niveis:
        res = nivel.escala_denominador * 0.00028
        if not crs_metros:
            res = res / 111320.0  # metros -> graus aproximados (latitude média)
        diff = abs(res - resolucao_alvo_m)
        if diff < menor_diff:
            menor_diff, melhor = diff, nivel
    return melhor


def _tile_kvp_url(
    cap: CapacidadesWMTS, camada: CamadaWMTS, tms_id: str, nivel: NivelMatriz, linha: int, coluna: int,
    formato: str,
) -> str:
    if camada.template_restful:
        return (
            camada.template_restful
            .replace("{TileMatrixSet}", tms_id).replace("{TileMatrix}", nivel.identificador)
            .replace("{TileRow}", str(linha)).replace("{TileCol}", str(coluna))
            .replace("{Style}", camada.estilo_padrao or "default")
        )
    if not cap.url_kvp:
        raise ErroConector("wmts_sem_url_de_tile", camada.nome)
    params = {
        "SERVICE": "WMTS", "REQUEST": "GetTile", "VERSION": "1.0.0", "LAYER": camada.nome,
        "STYLE": camada.estilo_padrao or "default", "TILEMATRIXSET": tms_id,
        "TILEMATRIX": nivel.identificador, "TILEROW": str(linha), "TILECOL": str(coluna), "FORMAT": formato,
    }
    return _com_query(cap.url_kvp, params)


@dataclass(frozen=True)
class ResultadoTile:
    png: bytes
    reprojetado: bool
    aviso: str | None = None


def mosaico_tile_reprojetado(
    cap: CapacidadesWMTS, *, camada: str, tile_matrix_set: str, z: int, x: int, y: int, formato: str = "image/png",
) -> ResultadoTile:
    """Constrói o tile-alvo 256x256 EPSG:3857 (z/x/y do esquema slippy padrão) a partir do TileMatrixSet
    nativo, que está em outro CRS (o caso do adversário: só EPSG:4674). Busca até `_MAX_TILES_MOSAICO` tiles
    nativos, monta um raster georreferenciado com `rasterio` e reprojeta com GDAL (via `rasterio.warp`)."""
    c = cap.camada(camada)
    tms = cap.tile_matrix_sets.get(tile_matrix_set)
    if tms is None or not tms.niveis:
        raise ErroConector("tile_matrix_set_inexistente", tile_matrix_set)

    destino_bbox = _envoltoria_tile_3857(z, x, y)
    from pyproj import Transformer

    crs_destino = RasterioCRS.from_epsg(3857)
    crs_origem = RasterioCRS.from_string(tms.crs)
    # `always_xy=True`: entrada/saída sempre em (leste/lon, norte/lat), qualquer que seja a ordem de eixo
    # nativa do CRS (a mesma armadilha do WMS 1.3.0, resolvida aqui pelo próprio pyproj em vez de à mão).
    para_origem = Transformer.from_crs(crs_destino, crs_origem, always_xy=True)

    cantos_destino = [
        (destino_bbox[0], destino_bbox[1]), (destino_bbox[2], destino_bbox[1]),
        (destino_bbox[0], destino_bbox[3]), (destino_bbox[2], destino_bbox[3]),
    ]
    cantos_origem = [para_origem.transform(*c) for c in cantos_destino]
    xs = [c[0] for c in cantos_origem]
    ys = [c[1] for c in cantos_origem]
    origem_bbox = (min(xs), min(ys), max(xs), max(ys))

    resolucao_alvo = (destino_bbox[2] - destino_bbox[0]) / TAMANHO_TILE_PADRAO
    nivel = _nivel_mais_perto(tms, resolucao_alvo, crs_metros=not crs_origem.is_geographic)
    resolucao_nivel = nivel.escala_denominador * 0.00028
    if crs_origem.is_geographic:
        resolucao_nivel = resolucao_nivel / 111320.0
    span_tile = resolucao_nivel * nivel.largura_tile
    span_tile_y = resolucao_nivel * nivel.altura_tile

    topo_x, topo_y = nivel.topo_esquerdo
    col_ini = max(0, int((origem_bbox[0] - topo_x) / span_tile))
    col_fim = min(nivel.largura_matriz - 1, int((origem_bbox[2] - topo_x) / span_tile))
    lin_ini = max(0, int((topo_y - origem_bbox[3]) / span_tile_y))
    lin_fim = min(nivel.altura_matriz - 1, int((topo_y - origem_bbox[1]) / span_tile_y))

    n_col = col_fim - col_ini + 1
    n_lin = lin_fim - lin_ini + 1
    aviso = None
    if n_col * n_lin > _MAX_TILES_MOSAICO:
        col_fim = col_ini + min(n_col, 2) - 1
        lin_fim = lin_ini + min(n_lin, 2) - 1
        aviso = "mosaico_parcial: cobertura pedida exigia mais de %d tiles nativos" % _MAX_TILES_MOSAICO

    largura_px = (col_fim - col_ini + 1) * nivel.largura_tile
    altura_px = (lin_fim - lin_ini + 1) * nivel.altura_tile
    mosaico = np.zeros((4, altura_px, largura_px), dtype=np.uint8)
    for li, linha in enumerate(range(lin_ini, lin_fim + 1)):
        for ci, coluna in enumerate(range(col_ini, col_fim + 1)):
            url = _tile_kvp_url(cap, c, tile_matrix_set, nivel, linha, coluna, formato)
            r = seguranca.buscar_seguro(
                url, guardar_corpo=True, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S,
                timeout_ler=limites.CONEXAO_WMS_MAPA_TIMEOUT_S, max_bytes=limites.CONEXAO_WMTS_TILE_MAX_BYTES,
            )
            if not r.ok:
                continue  # tile nativo indisponível: fica transparente no mosaico, não derruba o pedido inteiro
            arr = _png_para_array(r.corpo, nivel.largura_tile, nivel.altura_tile)
            y0, x0 = li * nivel.altura_tile, ci * nivel.largura_tile
            mosaico[:, y0:y0 + nivel.altura_tile, x0:x0 + nivel.largura_tile] = arr

    origem_mosaico_bbox = (
        topo_x + col_ini * span_tile, topo_y - (lin_fim + 1) * span_tile_y,
        topo_x + (col_fim + 1) * span_tile, topo_y - lin_ini * span_tile_y,
    )
    transform_origem = from_bounds(*origem_mosaico_bbox, largura_px, altura_px)
    saida = _reprojetar_array(
        mosaico, crs_origem, transform_origem, crs_destino,
        from_bounds(*destino_bbox, TAMANHO_TILE_PADRAO, TAMANHO_TILE_PADRAO),
        TAMANHO_TILE_PADRAO, TAMANHO_TILE_PADRAO,
    )
    return ResultadoTile(png=_array_para_png(saida), reprojetado=True, aviso=aviso)


def reprojetar_imagem(
    png_origem: bytes, *, bbox_origem: tuple[float, float, float, float], epsg_origem: int,
    largura: int, altura: int, epsg_destino: int = 3857,
) -> bytes:
    """Reprojeta uma imagem GetMap já baixada (sem georreferência própria — o bbox do PEDIDO é a referência)
    do `epsg_origem` (ex.: 4674, o caso do adversário: "serviço só em EPSG:4674") para `epsg_destino`."""
    arr = _png_para_array(png_origem, largura, altura)
    crs_origem = RasterioCRS.from_epsg(epsg_origem)
    crs_destino = RasterioCRS.from_epsg(epsg_destino)
    transform_origem = from_bounds(*bbox_origem, largura, altura)
    transform_destino, larg_dest, alt_dest = calculate_default_transform(
        crs_origem, crs_destino, largura, altura, *bbox_origem,
    )
    saida = _reprojetar_array(arr, crs_origem, transform_origem, crs_destino, transform_destino, larg_dest, alt_dest)
    return _array_para_png(saida)


def _reprojetar_array(
    arr, crs_origem, transform_origem, crs_destino, transform_destino, largura_destino, altura_destino,
):
    destino = np.zeros((4, altura_destino, largura_destino), dtype=np.uint8)
    for banda in range(4):
        reproject(
            source=arr[banda], destination=destino[banda],
            src_transform=transform_origem, src_crs=crs_origem,
            dst_transform=transform_destino, dst_crs=crs_destino,
            resampling=Resampling.nearest,
        )
    return destino


def _png_para_array(corpo: bytes, largura: int, altura: int):
    from PIL import Image

    img = Image.open(BytesIO(corpo)).convert("RGBA")
    if img.size != (largura, altura):
        img = img.resize((largura, altura))
    arr = np.asarray(img)  # (altura, largura, 4)
    return np.moveaxis(arr, -1, 0)  # (4, altura, largura)


def _array_para_png(arr) -> bytes:
    from PIL import Image

    img = Image.fromarray(np.moveaxis(arr, 0, -1), mode="RGBA")
    saida = BytesIO()
    img.save(saida, format="PNG")
    return saida.getvalue()


# marca de módulo usada pelo teste de marcador de pendência (nenhum acima desta linha)
__all__ = [
    "Camada", "CamadaWMTS", "CapacidadesWMS", "CapacidadesWMTS", "Estilo", "ErroConector",
    "NivelMatriz", "TileMatrixSet", "ResultadoTile",
    "capacidades_wms", "capacidades_wmts", "analisar_wms", "analisar_wmts", "url_getmap", "url_getfeatureinfo",
    "url_wmts_tile_direta", "mosaico_tile_reprojetado", "reprojetar_imagem",
]
