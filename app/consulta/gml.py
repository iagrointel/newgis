"""GML 3.2 (ISO 19136) de saída e o XSD que o `DescribeFeatureType` publica — as duas metades da
mesma decisão, por isso no mesmo módulo: o esquema declara a ORDEM dos elementos e o escritor tem
de emitir naquela ordem, senão o documento não valida no cliente (GDAL e ArcGIS Pro leem o XSD
antes de ler as feições).

Regras que este módulo carrega sozinho:
  - toda geometria GML 3.2 precisa de `gml:id` (é o que separa 3.2 de 3.1 e o que faz o GDAL
    recusar o documento com "MissingID" quando falta);
  - ordem dos eixos: `urn:ogc:def:crs:EPSG::4326` é LATITUDE, LONGITUDE (ordem da autoridade), a
    forma curta `EPSG:4326` é longitude, latitude. A decisão vive em `app.consulta.fes`, aqui só
    se aplica — um lugar só para a regra;
  - a geometria de entrada é GeoJSON (a saída de `serializar.como_geojson`), nunca a forma Esri:
    assim MultiLineString e MultiPolygon saem como `gml:MultiCurve`/`gml:MultiSurface` em vez de
    virarem o primeiro membro.
"""

from __future__ import annotations

import datetime
from xml.sax.saxutils import escape, quoteattr

NS_WFS = "http://www.opengis.net/wfs/2.0"
NS_OWS = "http://www.opengis.net/ows/1.1"
NS_GML = "http://www.opengis.net/gml/3.2"
NS_FES = "http://www.opengis.net/fes/2.0"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_XLINK = "http://www.w3.org/1999/xlink"
# espaço de nomes do esquema de aplicação desta plataforma: constante, nunca a URL pública (que muda
# por instalação e faria o XSD publicado ontem não casar com o documento de hoje)
NS_PLAT = "urn:x-plat:wfs"
PREFIXO_PLAT = "plat"

CRS_PADRAO = "urn:ogc:def:crs:EPSG::4326"

_XSD_POR_ESRI = {
    "esriFieldTypeInteger": "int",
    "esriFieldTypeSmallInteger": "short",
    "esriFieldTypeBigInteger": "long",
    "esriFieldTypeOID": "long",
    "esriFieldTypeDouble": "double",
    "esriFieldTypeSingle": "float",
    "esriFieldTypeDate": "dateTime",
    "esriFieldTypeDateOnly": "date",
    "esriFieldTypeTimeOnly": "time",
    "esriFieldTypeGUID": "string",
    "esriFieldTypeGlobalID": "string",
    "esriFieldTypeBlob": "base64Binary",
}
# tipo de propriedade de geometria por tipo de camada (o XSD tem de casar com o que o escritor emite)
_PROP_GEOM = {
    "Point": "gml:PointPropertyType",
    "MultiPoint": "gml:MultiPointPropertyType",
    "LineString": "gml:CurvePropertyType",
    "MultiLineString": "gml:MultiCurvePropertyType",
    "Polygon": "gml:SurfacePropertyType",
    "MultiPolygon": "gml:MultiSurfacePropertyType",
}


def agora() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def nome_tipo(item_id: str) -> str:
    """`c_<uuid sem hífen>`: nome de tipo de feição precisa ser NCName (não pode começar com
    dígito nem conter hífen), e o id do item é um UUID."""
    return "c_" + str(item_id).replace("-", "")


def tipo_qualificado(item_id: str) -> str:
    return f"{PREFIXO_PLAT}:{nome_tipo(item_id)}"


def campos_publicaveis(meta: list[dict]) -> list[dict]:
    """Os campos que entram no XSD e no documento, na MESMA ordem nos dois."""
    return [c for c in meta if c["papel"] != "geometria"]


def xsd_tipo(tipo_esri: str) -> str:
    return _XSD_POR_ESRI.get(tipo_esri, "string")


def descrever_tipo(item_id: str, meta: list[dict], geometria: str | None) -> str:
    """`DescribeFeatureType`: XSD do tipo de feição, importando o GML 3.2 oficial. É este esquema
    que valida o `GetFeature` — o teste compila os dois juntos."""
    nome = nome_tipo(item_id)
    linhas = []
    for c in campos_publicaveis(meta):
        linhas.append(
            f'        <xsd:element name="{c["nome"]}" type="xsd:{xsd_tipo(c["tipo_esri"])}" '
            f'minOccurs="0" nillable="true"/>'
        )
    if geometria and geometria != "nenhuma":
        prop = _PROP_GEOM.get(geometria, "gml:GeometryPropertyType")
        linhas.append(f'        <xsd:element name="geometria" type="{prop}" minOccurs="0" nillable="true"/>')
    corpo = "\n".join(linhas)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:gml="{NS_GML}"
    xmlns:{PREFIXO_PLAT}="{NS_PLAT}" targetNamespace="{NS_PLAT}"
    elementFormDefault="qualified" attributeFormDefault="unqualified" version="1.0">
  <xsd:import namespace="{NS_GML}" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd"/>
  <xsd:element name="{nome}" type="{PREFIXO_PLAT}:{nome}Type" substitutionGroup="gml:AbstractFeature"/>
  <xsd:complexType name="{nome}Type">
    <xsd:complexContent>
      <xsd:extension base="gml:AbstractFeatureType">
        <xsd:sequence>
{corpo}
        </xsd:sequence>
      </xsd:extension>
    </xsd:complexContent>
  </xsd:complexType>
</xsd:schema>
"""


# ------------------------------------------------------------------------------------ geometria
def _c(par: list[float], lat_lon: bool) -> str:
    x, y = float(par[0]), float(par[1])
    return f"{y} {x}" if lat_lon else f"{x} {y}"


def _lista(coords, lat_lon: bool) -> str:
    return " ".join(_c(p, lat_lon) for p in coords)


def _anel(coords, lat_lon: bool) -> str:
    return f"<gml:LinearRing><gml:posList>{_lista(coords, lat_lon)}</gml:posList></gml:LinearRing>"


def _poligono(coords, lat_lon: bool, gid: str) -> str:
    partes = [f"<gml:exterior>{_anel(coords[0], lat_lon)}</gml:exterior>"]
    for anel in coords[1:]:
        partes.append(f"<gml:interior>{_anel(anel, lat_lon)}</gml:interior>")
    return f'<gml:Polygon gml:id="{gid}" srsName="{{srs}}">' + "".join(partes) + "</gml:Polygon>"


def geometria_gml(g: dict | None, srs: str, gid: str, lat_lon: bool) -> str:
    """GeoJSON -> GML 3.2, com `gml:id` em cada geometria (exigência do 3.2)."""
    if not g:
        return ""
    t = g.get("type")
    c = g.get("coordinates")
    if t == "Point":
        return f'<gml:Point gml:id="{gid}" srsName="{srs}"><gml:pos>{_c(c, lat_lon)}</gml:pos></gml:Point>'
    if t == "MultiPoint":
        membros = "".join(
            f'<gml:pointMember><gml:Point gml:id="{gid}.{i}" srsName="{srs}">'
            f"<gml:pos>{_c(p, lat_lon)}</gml:pos></gml:Point></gml:pointMember>"
            for i, p in enumerate(c)
        )
        return f'<gml:MultiPoint gml:id="{gid}" srsName="{srs}">{membros}</gml:MultiPoint>'
    if t == "LineString":
        return (f'<gml:LineString gml:id="{gid}" srsName="{srs}">'
                f"<gml:posList>{_lista(c, lat_lon)}</gml:posList></gml:LineString>")
    if t == "MultiLineString":
        membros = "".join(
            f'<gml:curveMember><gml:LineString gml:id="{gid}.{i}" srsName="{srs}">'
            f"<gml:posList>{_lista(linha, lat_lon)}</gml:posList></gml:LineString></gml:curveMember>"
            for i, linha in enumerate(c)
        )
        return f'<gml:MultiCurve gml:id="{gid}" srsName="{srs}">{membros}</gml:MultiCurve>'
    if t == "Polygon":
        return _poligono(c, lat_lon, gid).replace("{srs}", srs)
    if t == "MultiPolygon":
        membros = "".join(
            f"<gml:surfaceMember>{_poligono(pol, lat_lon, f'{gid}.{i}').replace('{srs}', srs)}</gml:surfaceMember>"
            for i, pol in enumerate(c)
        )
        return f'<gml:MultiSurface gml:id="{gid}" srsName="{srs}">{membros}</gml:MultiSurface>'
    raise ValueError(f"geometria GeoJSON sem tradução para GML: {t!r}")


# ------------------------------------------------------------------------------------ documentos
def _valor(v, tipo_esri: str | None = None) -> str:
    """Campo de data sai em ISO 8601, nunca no milissegundo de época que o protocolo Esri usa: o
    XSD publicado diz `xsd:dateTime`, e o cliente XML valida contra ele."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if tipo_esri in ("esriFieldTypeDate", "esriFieldTypeDateOnly") and isinstance(v, (int, float)):
        instante = datetime.datetime.fromtimestamp(v / 1000, datetime.UTC)
        if tipo_esri == "esriFieldTypeDateOnly":
            return instante.date().isoformat()
        return instante.strftime("%Y-%m-%dT%H:%M:%SZ")
    return escape(str(v))


def feicao_xml(item_id: str, feicao: dict, meta: list[dict], srs: str, lat_lon: bool,
               campo_oid: str, campos: list[str] | None = None) -> str:
    """Um elemento de feição (sem `wfs:member` em volta) — reusado pelo GetFeature e pelo
    GetPropertyValue."""
    nome = nome_tipo(item_id)
    props = feicao.get("properties") or {}
    fid = props.get(campo_oid)
    linhas = []
    for c in campos_publicaveis(meta):
        if campos is not None and c["nome"] not in campos:
            continue
        v = props.get(c["nome"])
        if v is None:
            continue
        linhas.append(f"      <{PREFIXO_PLAT}:{c['nome']}>{_valor(v, c.get('tipo_esri'))}"
                       f"</{PREFIXO_PLAT}:{c['nome']}>")
    if (campos is None or "geometria" in campos) and feicao.get("geometry"):
        g = geometria_gml(feicao["geometry"], srs, f"{nome}.{fid}.geom", lat_lon)
        linhas.append(f"      <{PREFIXO_PLAT}:geometria>{g}</{PREFIXO_PLAT}:geometria>")
    corpo = "\n".join(linhas)
    return (f'    <{PREFIXO_PLAT}:{nome} gml:id={quoteattr(f"{nome}.{fid}")}>\n{corpo}\n'
            f"    </{PREFIXO_PLAT}:{nome}>")


def _cabecalho_ns() -> str:
    return (f'xmlns:wfs="{NS_WFS}" xmlns:gml="{NS_GML}" xmlns:{PREFIXO_PLAT}="{NS_PLAT}" '
            f'xmlns:xsi="{NS_XSI}"')


def colecao_feicoes(item_id: str, geojson: dict, meta: list[dict], srs: str, lat_lon: bool,
                    campo_oid: str, numero_total: int, url_esquema: str,
                    campos: list[str] | None = None) -> str:
    membros = "\n".join(
        f"  <wfs:member>\n{feicao_xml(item_id, f, meta, srs, lat_lon, campo_oid, campos)}\n  </wfs:member>"
        for f in geojson.get("features", [])
    )
    n = len(geojson.get("features", []))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection {_cabecalho_ns()}
    xsi:schemaLocation={quoteattr(f"{NS_PLAT} {url_esquema} {NS_WFS} http://schemas.opengis.net/wfs/2.0/wfs.xsd")}
    numberMatched="{numero_total}" numberReturned="{n}" timeStamp="{agora()}">
{membros}
</wfs:FeatureCollection>
"""


def colecao_hits(numero_total: int) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<wfs:FeatureCollection {_cabecalho_ns()} '
            f'numberMatched="{numero_total}" numberReturned="0" timeStamp="{agora()}"/>\n')


def colecao_valores(item_id: str, geojson: dict, meta: list[dict], srs: str, lat_lon: bool,
                    campo_oid: str, campo: str, numero_total: int) -> str:
    """`GetPropertyValue`: `wfs:ValueCollection` com um `wfs:member` por valor da propriedade."""
    membros = []
    for f in geojson.get("features", []):
        if campo == "geometria":
            g = geometria_gml(f.get("geometry"), srs, f"g{f.get('properties', {}).get(campo_oid)}", lat_lon)
            membros.append(f"  <wfs:member>{g}</wfs:member>")
        else:
            v = (f.get("properties") or {}).get(campo)
            if v is None:
                continue
            tipo = next((c["tipo_esri"] for c in meta if c["nome"] == campo), None)
            membros.append(f"  <wfs:member><{PREFIXO_PLAT}:{campo}>{_valor(v, tipo)}"
                           f"</{PREFIXO_PLAT}:{campo}></wfs:member>")
    corpo = "\n".join(membros)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:ValueCollection {_cabecalho_ns()} numberMatched="{numero_total}" numberReturned="{len(membros)}"
    timeStamp="{agora()}">
{corpo}
</wfs:ValueCollection>
"""


def excecao(codigo: str, texto: str, locator: str | None = None, versao: str = "2.0.0") -> str:
    """`ows:ExceptionReport` — a forma OGC de erro; QGIS e GDAL mostram o texto ao usuário."""
    loc = f" locator={quoteattr(locator)}" if locator else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ows:ExceptionReport xmlns:ows="{NS_OWS}" version="{versao}" xml:lang="pt">
  <ows:Exception exceptionCode={quoteattr(codigo)}{loc}>
    <ows:ExceptionText>{escape(texto)}</ows:ExceptionText>
  </ows:Exception>
</ows:ExceptionReport>
"""
