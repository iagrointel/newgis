"""Conectores de feição externa: WFS 2.0 e OGC API - Features (item L6-02-c-wfs-ogcapi; ADR 0018).

Regra dura deste módulo: **todo I/O de rede passa por `app.conexao.seguranca.buscar_seguro`** (item
L6-02-a). Não existe cliente HTTP próprio, nem `httpx`/`urllib` direto, nem `ogr2ogr WFS:<url>` — o driver
WFS/OAPIF do GDAL faria a requisição por fora da validação e a defesa contra requisição forjada pelo servidor
(SSRF) deixaria de valer justamente no caminho que mais recebe URL de terceiro. O GDAL entra só depois, em
`app/conexao/copia.py`, e sempre sobre ARQUIVO LOCAL já baixado por aqui.

O que o módulo faz:
  - `listar_colecoes`  — WFS: `GetCapabilities` → `wfs:FeatureTypeList`; OGC API: `GET /collections`.
  - `descrever_campos` — WFS: `DescribeFeatureType` (XSD, tipo DECLARADO); OGC API: `/queryables` quando
    existe, senão inferência a partir da primeira página (marcada como `inferido`, nunca como declarado).
  - `contar`           — WFS: `GetFeature&RESULTTYPE=hits` → atributo `numberMatched`; OGC API: `numberMatched`
    do documento de itens com `limit=1`. Pode ser `None`: nem todo serviço declara, e inventar um total é pior
    que não ter (a cópia então só sabe quantas leu, e diz isso).
  - `Paginador`        — percorre as páginas (WFS `STARTINDEX`/`COUNT`; OGC API `limit` + link `rel=next`),
    com bbox e datetime, PARANDO no limite declarado. Detecta e denuncia o serviço que ignora a paginação
    (devolve mais do que foi pedido, ou repete a mesma página) em vez de girar para sempre.

O que ele NÃO faz (fronteira honesta): não escreve no banco (isso é `copia.py`), não desenha no mapa (L6-02-b),
não agenda nada (L6-02-k) e não fala WFS 1.0/1.1 — só 2.0.0, que é o que traz `STARTINDEX`/`numberMatched`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode, urlsplit, urlunsplit
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET_seguro

from app import limites
from app.conexao import seguranca

TIPOS_SUPORTADOS = ("wfs", "ogc_api")
VERSAO_WFS = "2.0.0"

# tipo XSD/JSON declarado pelo serviço -> tipo de coluna no PostgreSQL. Só o que é padronizado; o que não
# estiver aqui vira `text` E fica registrado em `tipo_declarado`, para a ficha dizer o que o serviço disse.
_TIPOS_XSD = {
    "string": "text", "normalizedstring": "text", "token": "text", "anyuri": "text",
    "int": "integer", "integer": "integer", "short": "integer", "byte": "integer",
    "negativeinteger": "integer", "nonnegativeinteger": "integer", "positiveinteger": "integer",
    "nonpositiveinteger": "integer", "unsignedshort": "integer", "unsignedbyte": "integer",
    "long": "bigint", "unsignedint": "bigint", "unsignedlong": "bigint",
    "double": "double precision", "float": "double precision", "decimal": "double precision",
    "boolean": "boolean", "date": "date", "datetime": "timestamptz", "time": "time",
}
_TIPOS_JSON = {
    "string": "text", "integer": "bigint", "number": "double precision", "boolean": "boolean",
}
_TIPOS_GEOMETRIA_XSD = (
    "geometrypropertytype", "pointpropertytype", "multipointpropertytype", "curvepropertytype",
    "linestringpropertytype", "multicurvepropertytype", "multilinestringpropertytype",
    "surfacepropertytype", "polygonpropertytype", "multisurfacepropertytype", "multipolygonpropertytype",
    "geometrycollectionpropertytype", "multigeometrypropertytype",
)
_FORMATOS_JSON = ("application/json", "application/geo+json", "geojson", "json")


class ErroConector(Exception):
    """Falha ao falar com o serviço externo. `motivo` é um código estável (vira `erro` da resposta HTTP)."""

    def __init__(self, motivo: str, detalhe: str = ""):
        self.motivo = motivo
        self.detalhe = detalhe
        super().__init__(f"{motivo}: {detalhe}" if detalhe else motivo)


@dataclass(frozen=True)
class Conector:
    tipo: str                                   # "wfs" | "ogc_api"
    url: str                                    # URL base da conexão (plat.conexao.url)
    cabecalhos: dict[str, str] | None = None    # Authorization montado por quem chama; nunca logado aqui


@dataclass(frozen=True)
class Colecao:
    nome: str                       # typeName (WFS) ou id da coleção (OGC API)
    titulo: str | None
    crs_nativo: str | None          # como o serviço DECLAROU ("EPSG:4674"); None quando não declara
    srid_nativo: int | None         # o mesmo em número, quando dá para extrair; nunca um palpite
    srid_entregue: int              # CRS em que as feições chegam (WFS: o nativo; OGC API: 4326/CRS84)
    extent_4326: list[float] | None
    formatos: tuple[str, ...] = ()  # outputFormats declarados (WFS); vazio no OGC API (sempre GeoJSON)


@dataclass(frozen=True)
class Campo:
    nome: str
    tipo: str            # tipo de coluna PostgreSQL
    tipo_declarado: str  # o que o serviço disse, verbatim
    origem: str          # "describefeaturetype" | "queryables" | "amostra"


@dataclass
class Relatorio:
    """O que a paginação viu. `avisos` nunca é decorativo: cada linha vira `procedencia.limites` da camada."""

    numero_matched: int | None = None
    paginas: int = 0
    feicoes: int = 0
    bytes: int = 0
    limite_atingido: bool = False
    ignora_paginacao: bool = False
    repetiu_pagina: bool = False
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- utilidades de URL e HTTP


def _com_parametros(url: str, params: dict[str, str]) -> str:
    partes = urlsplit(url)
    consulta = partes.query
    ja = {p.split("=", 1)[0].lower() for p in consulta.split("&") if p}
    novos = {k: v for k, v in params.items() if k.lower() not in ja}
    extra = urlencode(novos)
    if extra:
        consulta = f"{consulta}&{extra}" if consulta else extra
    return urlunsplit((partes.scheme, partes.netloc, partes.path, consulta, partes.fragment))


def _junta_caminho(url: str, sufixo: str) -> str:
    partes = urlsplit(url)
    caminho = partes.path.rstrip("/") + "/" + sufixo.lstrip("/")
    return urlunsplit((partes.scheme, partes.netloc, caminho, partes.query, partes.fragment))


# cabeçalhos que carregam segredo e nunca podem atravessar um link ESCOLHIDO PELO SERVIDOR (`rel=next` etc.)
# que mude de origem — mesmo conjunto de `app.conexao.seguranca._CABECALHOS_CREDENCIAL` (achado do adversário,
# item L6-02-c, turno 3: conserto do L6-02-c-CONSERTO).
_CABECALHOS_CREDENCIAL_LINK = frozenset({"authorization", "cookie", "proxy-authorization"})


def _origem(url: str) -> tuple[str, str, int]:
    """esquema+host+porta em minúsculas, com a porta padrão do esquema quando omitida — a mesma noção de
    origem usada por `app.conexao.seguranca` para o mesmo problema em redirecionamento."""
    partes = urlsplit(url)
    porta = partes.port or (443 if partes.scheme.lower() == "https" else 80)
    return (partes.scheme.lower(), (partes.hostname or "").lower(), porta)


def _conector_para_link(conector: Conector, url: str) -> Conector:
    """Um link vindo do documento do servidor (`rel=next`, e qualquer outro href que este módulo vier a seguir
    — `rel=items`, `rel=data`, link de coleção) é escolhido pelo SERVIDOR, não por nós. `buscar_seguro`
    continua validando a URL contra SSRF (IP bloqueado, rebinding etc.); isto aqui protege o SEGREDO: a
    credencial da conexão só atravessa se o link continuar na MESMA ORIGEM (esquema+host+porta) da URL
    original da conexão (`conector.url`). Achado do adversário (L6-02-c, turno 3): sem isso, um `rel=next`
    apontando para outro host — hostil, comprometido, ou só um coletor de terceiro — recebe de graça o
    Bearer/Cookie da casa. `buscar_seguro` já faz o mesmo para redirecionamento (item L6-02-a); aqui é o
    CHAMADOR que decide, porque o link não passa por dentro de `buscar_seguro`."""
    if not conector.cabecalhos or _origem(url) == _origem(conector.url):
        return conector
    limpos = {k: v for k, v in conector.cabecalhos.items() if k.lower() not in _CABECALHOS_CREDENCIAL_LINK}
    if len(limpos) == len(conector.cabecalhos):
        return conector
    return replace(conector, cabecalhos=limpos or None)


def _buscar(conector: Conector, url: str, *, max_bytes: int) -> bytes:
    r = seguranca.buscar_seguro(
        url, metodo="GET", timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S,
        timeout_ler=limites.CONEXAO_VETOR_LER_TIMEOUT_S, max_bytes=max_bytes,
        cabecalhos=conector.cabecalhos, guardar_corpo=True,
    )
    if not r.ok:
        raise ErroConector("servico_externo_falhou", f"{r.mensagem} ({url})")
    if not r.corpo:
        raise ErroConector("resposta_vazia", url)
    return r.corpo


def _xml(corpo: bytes):
    try:
        return ET_seguro.fromstring(corpo)  # defusedxml: nunca resolve entidade externa
    except (ParseError, ValueError) as e:
        raise ErroConector("xml_invalido", str(e)[:200]) from e


def _json(corpo: bytes) -> dict:
    try:
        doc = json.loads(corpo.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErroConector("json_invalido", str(e)[:200]) from e
    if not isinstance(doc, dict):
        raise ErroConector("json_invalido", "o documento não é um objeto")
    return doc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _filhos(el, nome: str):
    return [f for f in el if _local(f.tag) == nome]


def _texto(el, nome: str) -> str | None:
    for f in el.iter():
        if _local(f.tag) == nome and f.text and f.text.strip():
            return " ".join(f.text.split())
    return None


_RE_SRID = re.compile(r"(?:EPSG:{1,2}|/EPSG/\d+/)(\d{4,6})\b", re.I)


def srid_de(crs: str | None) -> int | None:
    """`urn:ogc:def:crs:EPSG::4674`, `http://www.opengis.net/def/crs/EPSG/0/4674` e `EPSG:4674` -> 4674.
    `CRS84` -> 4326 (mesma elipsoide, eixo lon/lat — que é a ordem do GeoJSON). Qualquer outra coisa -> None
    (nunca chutar um SRID: uma reprojeção com CRS errado põe a camada no oceano sem avisar)."""
    if not crs:
        return None
    if "crs84" in crs.lower():
        return 4326
    m = _RE_SRID.search(crs)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- WFS 2.0


def _capacidades_wfs(conector: Conector):
    url = _com_parametros(conector.url, {"SERVICE": "WFS", "VERSION": VERSAO_WFS, "REQUEST": "GetCapabilities"})
    return _xml(_buscar(conector, url, max_bytes=limites.CONEXAO_VETOR_METADADO_MAX_BYTES))


def _formatos_getfeature(raiz) -> tuple[str, ...]:
    for op in raiz.iter():
        if _local(op.tag) != "Operation" or op.get("name") != "GetFeature":
            continue
        for par in _filhos(op, "Parameter"):
            if (par.get("name") or "").lower() != "outputformat":
                continue
            return tuple(
                " ".join(v.text.split()) for v in par.iter()
                if _local(v.tag) == "Value" and v.text and v.text.strip()
            )
    return ()


def _colecoes_wfs(conector: Conector) -> list[Colecao]:
    raiz = _capacidades_wfs(conector)
    formatos = _formatos_getfeature(raiz)
    saida: list[Colecao] = []
    for lista in raiz.iter():
        if _local(lista.tag) != "FeatureTypeList":
            continue
        for ft in _filhos(lista, "FeatureType"):
            nome = _texto(ft, "Name")
            if not nome:
                continue
            crs = _texto(ft, "DefaultCRS") or _texto(ft, "DefaultSRS")
            srid = srid_de(crs)
            extent = None
            for bb in ft:
                if _local(bb.tag) != "WGS84BoundingBox":
                    continue
                inf = _texto(bb, "LowerCorner")
                sup = _texto(bb, "UpperCorner")
                if inf and sup:
                    try:
                        x0, y0 = (float(v) for v in inf.split()[:2])
                        x1, y1 = (float(v) for v in sup.split()[:2])
                        extent = [x0, y0, x1, y1]
                    except ValueError:
                        extent = None
            saida.append(Colecao(
                nome=nome, titulo=_texto(ft, "Title"), crs_nativo=crs, srid_nativo=srid,
                srid_entregue=srid or 4326, extent_4326=extent, formatos=formatos,
            ))
    return saida


def _formato_json_wfs(colecao: Colecao) -> str | None:
    """Escolhe o outputFormat JSON DECLARADO pelo serviço; None quando ele só oferece GML (aí a cópia usa GML
    e a consulta referenciada recusa com `formato_json_indisponivel`, em vez de pedir um formato que o
    servidor não anunciou e receber uma página de erro em XML como se fosse dado)."""
    for f in colecao.formatos:
        if f.lower() in _FORMATOS_JSON or "geo+json" in f.lower():
            return f
    return None


def _campos_wfs(conector: Conector, colecao: str) -> tuple[list[Campo], bytes]:
    url = _com_parametros(conector.url, {
        "SERVICE": "WFS", "VERSION": VERSAO_WFS, "REQUEST": "DescribeFeatureType", "TYPENAMES": colecao,
    })
    corpo = _buscar(conector, url, max_bytes=limites.CONEXAO_VETOR_METADADO_MAX_BYTES)
    raiz = _xml(corpo)
    campos: list[Campo] = []
    for el in raiz.iter():
        if _local(el.tag) != "element":
            continue
        nome = el.get("name")
        declarado = el.get("type") or ""
        if not nome or not declarado:
            continue
        curto = declarado.rsplit(":", 1)[-1].lower()
        if curto in _TIPOS_GEOMETRIA_XSD or curto.endswith("propertytype"):
            continue  # a geometria não é atributo: vira a coluna geom
        if curto not in _TIPOS_XSD and not declarado.lower().startswith(("xsd:", "xs:")):
            continue  # elemento estrutural do XSD (o próprio tipo da feição), não um campo
        campos.append(Campo(
            nome=nome, tipo=_TIPOS_XSD.get(curto, "text"), tipo_declarado=declarado,
            origem="describefeaturetype",
        ))
    return campos, corpo


def _url_getfeature(conector: Conector, colecao: Colecao, *, formato: str | None, count: int,
                    start: int, bbox: str | None, hits: bool) -> str:
    params = {
        "SERVICE": "WFS", "VERSION": VERSAO_WFS, "REQUEST": "GetFeature", "TYPENAMES": colecao.nome,
        "RESULTTYPE": "hits" if hits else "results",
    }
    if not hits:
        params["COUNT"] = str(count)
        params["STARTINDEX"] = str(start)
        if formato:
            params["OUTPUTFORMAT"] = formato
    if bbox:
        params["BBOX"] = bbox
    return _com_parametros(conector.url, params)


def _contar_wfs(conector: Conector, colecao: Colecao, bbox: str | None) -> int | None:
    url = _url_getfeature(conector, colecao, formato=None, count=0, start=0, bbox=bbox, hits=True)
    raiz = _xml(_buscar(conector, url, max_bytes=limites.CONEXAO_VETOR_METADADO_MAX_BYTES))
    valor = raiz.get("numberMatched")
    if valor in (None, "unknown"):
        return None
    try:
        return int(valor)
    except ValueError:
        return None


# --------------------------------------------------------------------------- OGC API - Features


def _colecoes_ogc(conector: Conector) -> list[Colecao]:
    url = conector.url if urlsplit(conector.url).path.rstrip("/").endswith("/collections") \
        else _junta_caminho(conector.url, "collections")
    doc = _json(_buscar(conector, url, max_bytes=limites.CONEXAO_VETOR_METADADO_MAX_BYTES))
    saida = []
    for c in doc.get("collections") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        bbox = (((c.get("extent") or {}).get("spatial") or {}).get("bbox") or [None])[0]
        extent = [float(v) for v in bbox[:4]] if isinstance(bbox, list) and len(bbox) >= 4 else None
        crs = c.get("storageCrs") or (c.get("crs") or [None])[0]
        saida.append(Colecao(
            nome=str(c["id"]), titulo=c.get("title") or None, crs_nativo=crs, srid_nativo=srid_de(crs),
            # OGC API - Features Parte 1: o padrão de `/items` é sempre CRS84 (lon/lat). Só a Parte 2 negocia
            # outro CRS, e nem todo serviço a implementa — pedir `crs=` sem checar traria dado no CRS errado.
            srid_entregue=4326, extent_4326=extent,
        ))
    return saida


def _url_itens(conector: Conector, colecao: Colecao) -> str:
    base = conector.url
    if urlsplit(base).path.rstrip("/").endswith("/collections"):
        base = urlunsplit((lambda p: (p.scheme, p.netloc, p.path.rstrip("/"), p.query, p.fragment))(urlsplit(base)))
        return _junta_caminho(base, f"{colecao.nome}/items")
    return _junta_caminho(base, f"collections/{colecao.nome}/items")


def _campos_ogc(conector: Conector, colecao: Colecao) -> tuple[list[Campo], bytes]:
    """`/queryables` (JSON Schema) quando o serviço tem; senão infere da primeira página e MARCA como inferido."""
    alvo = _url_itens(conector, colecao).removesuffix("/items") + "/queryables"
    try:
        doc = _json(_buscar(conector, alvo, max_bytes=limites.CONEXAO_VETOR_METADADO_MAX_BYTES))
        props = doc.get("properties") or {}
        if isinstance(props, dict) and props:
            campos = []
            for nome, esq in props.items():
                if not isinstance(esq, dict):
                    continue
                if (esq.get("format") or "").lower() in ("geometry", "geometry-point", "geometry-polygon"):
                    continue
                tipo_json = esq.get("type") or ""
                declarado = tipo_json + (f"/{esq['format']}" if esq.get("format") else "")
                pg = _TIPOS_JSON.get(str(tipo_json).lower(), "text")
                if (esq.get("format") or "").lower() == "date":
                    pg = "date"
                elif (esq.get("format") or "").lower() in ("date-time", "datetime"):
                    pg = "timestamptz"
                campos.append(Campo(nome=str(nome), tipo=pg, tipo_declarado=declarado or "desconhecido",
                                    origem="queryables"))
            if campos:
                return campos, json.dumps(doc, ensure_ascii=False).encode("utf-8")
    except ErroConector:
        pass  # `/queryables` é opcional na Parte 1; a ausência não é erro, só falta de declaração

    pagina = _pagina_ogc(conector, _com_parametros(_url_itens(conector, colecao), {"limit": "1"}))
    campos = []
    for nome, valor in ((pagina.feicoes[0].get("properties") or {}) if pagina.feicoes else {}).items():
        if isinstance(valor, bool):
            pg, decl = "boolean", "boolean (inferido)"
        elif isinstance(valor, int):
            pg, decl = "bigint", "integer (inferido)"
        elif isinstance(valor, float):
            pg, decl = "double precision", "number (inferido)"
        else:
            pg, decl = "text", "string (inferido)"
        campos.append(Campo(nome=str(nome), tipo=pg, tipo_declarado=decl, origem="amostra"))
    return campos, b""


@dataclass
class _PaginaBruta:
    feicoes: list[dict]
    numero_matched: int | None
    proximo: str | None
    bytes: int


def _pagina_ogc(conector: Conector, url: str) -> _PaginaBruta:
    corpo = _buscar(conector, url, max_bytes=limites.CONEXAO_VETOR_PAGINA_MAX_BYTES)
    doc = _json(corpo)
    feicoes = [f for f in (doc.get("features") or []) if isinstance(f, dict)]
    proximo = None
    for link in doc.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "next" and link.get("href"):
            proximo = str(link["href"])
            break
    nm = doc.get("numberMatched")
    return _PaginaBruta(feicoes, int(nm) if isinstance(nm, int) else None, proximo, len(corpo))


# --------------------------------------------------------------------------- interface pública


def listar_colecoes(conector: Conector) -> list[Colecao]:
    if conector.tipo == "wfs":
        return _colecoes_wfs(conector)
    if conector.tipo == "ogc_api":
        return _colecoes_ogc(conector)
    raise ErroConector("tipo_nao_suportado", conector.tipo)


def colecao_ou_erro(conector: Conector, nome: str) -> Colecao:
    for c in listar_colecoes(conector):
        if c.nome == nome or c.nome.rsplit(":", 1)[-1] == nome:
            return c
    raise ErroConector("colecao_inexistente", nome)


def descrever_campos(conector: Conector, colecao: Colecao) -> tuple[list[Campo], bytes]:
    if conector.tipo == "wfs":
        return _campos_wfs(conector, colecao.nome)
    if conector.tipo == "ogc_api":
        return _campos_ogc(conector, colecao)
    raise ErroConector("tipo_nao_suportado", conector.tipo)


def contar(conector: Conector, colecao: Colecao, *, bbox: list[float] | None = None,
           datahora: str | None = None) -> int | None:
    if conector.tipo == "wfs":
        return _contar_wfs(conector, colecao, _bbox_wfs(bbox, colecao))
    params = {"limit": "1"}
    if bbox:
        params["bbox"] = ",".join(f"{v:g}" for v in bbox)
    if datahora:
        params["datetime"] = datahora
    return _pagina_ogc(conector, _com_parametros(_url_itens(conector, colecao), params)).numero_matched


def _bbox_wfs(bbox: list[float] | None, colecao: Colecao) -> str | None:
    """BBOX do WFS 2.0 sempre com o CRS escrito por extenso (`urn:ogc:def:crs:OGC:1.3:CRS84`): sem ele o
    servidor assume o CRS nativo da camada e um bbox em graus vira um retângulo de metros no lugar errado."""
    if not bbox:
        return None
    return ",".join(f"{v:g}" for v in bbox[:4]) + ",urn:ogc:def:crs:OGC:1.3:CRS84"


class Paginador:
    """Percorre as feições da coleção página a página, parando SEMPRE em `limite`.

    Refutação do item (adversário): um WFS que declara 5 milhões de feições e IGNORA `COUNT`/`STARTINDEX`.
    Três travas independentes, qualquer uma delas basta para o laço acabar:
      1. `limite` — teto de feições que a cópia aceita, decidido por quem chama, nunca pelo serviço;
      2. página maior do que a pedida (`len > tam_pagina`) marca `ignora_paginacao` e para na página seguinte;
      3. página que repete a primeira feição da anterior marca `repetiu_pagina` e para na hora.
    Some-se a isso o teto de bytes por página (`buscar_seguro`) e o de páginas (`CONEXAO_VETOR_PAGINAS_MAX`).
    Nenhuma delas deixa o worker preso: o pior caso é `PAGINAS_MAX` requisições com timeout de leitura curto.
    """

    def __init__(self, conector: Conector, colecao: Colecao, *, bbox: list[float] | None = None,
                 datahora: str | None = None, tam_pagina: int, limite: int, formato_json: str | None = None):
        self.conector = conector
        self.colecao = colecao
        self.bbox = bbox
        self.datahora = datahora
        self.tam_pagina = max(1, min(tam_pagina, limites.CONEXAO_VETOR_PAGINA_MAX))
        self.limite = max(1, limite)
        self.formato_json = formato_json
        self.relatorio = Relatorio()

    def _primeira_pagina_wfs(self) -> str:
        return _url_getfeature(self.conector, self.colecao, formato=self.formato_json,
                               count=self.tam_pagina, start=0, bbox=_bbox_wfs(self.bbox, self.colecao), hits=False)

    def _primeira_pagina_ogc(self) -> str:
        params = {"limit": str(self.tam_pagina)}
        if self.bbox:
            params["bbox"] = ",".join(f"{v:g}" for v in self.bbox[:4])
        if self.datahora:
            params["datetime"] = self.datahora
        return _com_parametros(_url_itens(self.conector, self.colecao), params)

    def _buscar_pagina(self, url: str, conector: Conector | None = None) -> _PaginaBruta:
        conector = conector or self.conector
        if conector.tipo == "ogc_api":
            return _pagina_ogc(conector, url)
        corpo = _buscar(conector, url, max_bytes=limites.CONEXAO_VETOR_PAGINA_MAX_BYTES)
        if self.formato_json:
            doc = _json(corpo)
            feicoes = [f for f in (doc.get("features") or []) if isinstance(f, dict)]
            nm = doc.get("numberMatched")
            return _PaginaBruta(feicoes, int(nm) if isinstance(nm, int) else None, None, len(corpo))
        return _PaginaBruta([], _numero_matched_gml(corpo), None, len(corpo))

    def _fechar_no_limite(self, lidas: int) -> None:
        """Chegar ao teto NÃO é o mesmo que truncar. Quando o serviço declara exatamente as feições que foram
        lidas, a coleção veio inteira e `limite_atingido` fica falso — marcar verdadeiro aí faria toda camada
        copiada com o tamanho exato do limite parecer um pedaço. Marca-se verdadeiro quando sobrou coisa
        (`numberMatched` maior do que o lido), quando o serviço ignora a paginação, e também quando ele NÃO
        declara total nenhum: aí não dá para saber se sobrou, e dizer que não sobrou seria inventar."""
        matched = self.relatorio.numero_matched
        if matched is not None and matched <= lidas and not self.relatorio.ignora_paginacao:
            self.relatorio.limite_atingido = False
            return
        self.relatorio.limite_atingido = True
        if matched is None:
            self.relatorio.avisos.append(
                f"a cópia parou no limite de {self.limite} feições e o serviço não declara o total "
                f"(numberMatched): não dá para saber se a coleção acabou aqui"
            )
        elif matched > lidas:
            self.relatorio.avisos.append(
                f"o serviço declara {matched} feições e o limite desta cópia é {self.limite}: a camada tem as "
                f"{lidas} primeiras, NÃO a coleção inteira"
            )
        if self.relatorio.ignora_paginacao:
            self.relatorio.avisos.append(
                f"o serviço devolveu mais feições do que as {self.tam_pagina} pedidas: ignora a paginação"
            )

    def paginas_brutas(self) -> Iterator[tuple[bytes, int]]:
        """(corpo da página, feições contadas nela) — usado pela cópia quando o serviço só fala GML: o corpo vai
        para disco e o GDAL local lê. Contagem vem do `numberReturned` do próprio documento."""
        alvo = self._primeira_pagina_wfs() if self.conector.tipo == "wfs" else self._primeira_pagina_ogc()
        lidas = 0
        for _ in range(limites.CONEXAO_VETOR_PAGINAS_MAX):
            corpo = _buscar(self.conector, alvo, max_bytes=limites.CONEXAO_VETOR_PAGINA_MAX_BYTES)
            n, matched = _contagens_gml(corpo)
            self.relatorio.paginas += 1
            self.relatorio.bytes += len(corpo)
            if self.relatorio.numero_matched is None and matched is not None:
                self.relatorio.numero_matched = matched
            if n == 0:
                return
            if n > self.tam_pagina:
                self.relatorio.ignora_paginacao = True
            corte = min(n, self.limite - lidas)
            lidas += corte
            self.relatorio.feicoes = lidas
            yield corpo, corte
            if lidas >= self.limite:
                self._fechar_no_limite(lidas)
                return
            if self.relatorio.ignora_paginacao:
                self.relatorio.avisos.append(
                    f"o serviço devolveu {n} feições para COUNT={self.tam_pagina}: ignora a paginação; "
                    f"a cópia parou em {lidas}"
                )
                self.relatorio.limite_atingido = True
                return
            alvo = _url_getfeature(self.conector, self.colecao, formato=None, count=self.tam_pagina,
                                   start=lidas, bbox=_bbox_wfs(self.bbox, self.colecao), hits=False)
        self.relatorio.avisos.append(f"teto de {limites.CONEXAO_VETOR_PAGINAS_MAX} páginas atingido")
        self.relatorio.limite_atingido = True

    def paginas_json(self) -> Iterator[list[dict]]:
        """Páginas já como lista de feições GeoJSON, respeitando `limite` na última."""
        alvo = self._primeira_pagina_wfs() if self.conector.tipo == "wfs" else self._primeira_pagina_ogc()
        conector_pagina = self.conector  # o link `rel=next` pode trocar de origem; ver `_conector_para_link`
        lidas = 0
        assinatura_anterior: str | None = None
        for _ in range(limites.CONEXAO_VETOR_PAGINAS_MAX):
            pagina = self._buscar_pagina(alvo, conector_pagina)
            self.relatorio.paginas += 1
            self.relatorio.bytes += pagina.bytes
            if self.relatorio.numero_matched is None and pagina.numero_matched is not None:
                self.relatorio.numero_matched = pagina.numero_matched
            if not pagina.feicoes:
                return
            assinatura = _assinatura(pagina.feicoes[0])
            if assinatura_anterior is not None and assinatura == assinatura_anterior:
                self.relatorio.repetiu_pagina = True
                self.relatorio.avisos.append(
                    f"o serviço repetiu a mesma página (primeira feição {assinatura!r}): a paginação não avança; "
                    f"a cópia parou em {lidas}"
                )
                self.relatorio.limite_atingido = True
                return
            assinatura_anterior = assinatura
            if len(pagina.feicoes) > self.tam_pagina:
                self.relatorio.ignora_paginacao = True
            corte = pagina.feicoes[: max(0, self.limite - lidas)]
            lidas += len(corte)
            self.relatorio.feicoes = lidas
            if corte:
                yield corte
            if lidas >= self.limite:
                self._fechar_no_limite(lidas)
                return
            if self.relatorio.ignora_paginacao:
                self.relatorio.avisos.append(
                    f"o serviço devolveu mais feições do que as {self.tam_pagina} pedidas: ignora a paginação; "
                    f"a cópia parou em {lidas}"
                )
                self.relatorio.limite_atingido = True
                return
            if self.conector.tipo == "ogc_api":
                if not pagina.proximo:
                    return
                alvo = pagina.proximo
                nova = _conector_para_link(self.conector, alvo)
                if nova.cabecalhos != conector_pagina.cabecalhos:
                    self.relatorio.avisos.append(
                        f"o link seguinte do serviço mudou de origem ({alvo}): a credencial da conexão não "
                        f"foi reenviada"
                    )
                conector_pagina = nova
            else:
                alvo = _url_getfeature(self.conector, self.colecao, formato=self.formato_json,
                                       count=self.tam_pagina, start=lidas,
                                       bbox=_bbox_wfs(self.bbox, self.colecao), hits=False)
        self.relatorio.avisos.append(f"teto de {limites.CONEXAO_VETOR_PAGINAS_MAX} páginas atingido")
        self.relatorio.limite_atingido = True


def _assinatura(feicao: dict) -> str:
    """Identidade da primeira feição de uma página, para pegar o serviço que devolve sempre a mesma página."""
    return str(feicao.get("id") or json.dumps(feicao.get("properties") or {}, sort_keys=True)[:200])


def _contagens_gml(corpo: bytes) -> tuple[int, int | None]:
    """(numberReturned, numberMatched) do `wfs:FeatureCollection`. Sem `numberReturned` (servidor antigo), conta
    os `wfs:member`/`gml:featureMember` de verdade — nunca assume que a página veio cheia."""
    raiz = _xml(corpo)
    matched = raiz.get("numberMatched")
    matched_n = None
    if matched not in (None, "unknown"):
        try:
            matched_n = int(matched)
        except ValueError:
            matched_n = None
    devolvidas = raiz.get("numberReturned")
    if devolvidas not in (None, "unknown"):
        try:
            return int(devolvidas), matched_n
        except ValueError:
            pass
    return sum(1 for el in raiz.iter() if _local(el.tag) in ("member", "featureMember", "featureMembers")), matched_n


def _numero_matched_gml(corpo: bytes) -> int | None:
    return _contagens_gml(corpo)[1]
