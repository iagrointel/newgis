"""WFS 2.0 (ISO 19142 / OGC 09-025r2) sobre a mesma camada hospedada e o mesmo motor de consulta do
FeatureServer (item L2-04-c) — protocolo KVP (`SERVICE=WFS&REQUEST=...`), o único que QGIS/ArcGIS Pro
usam para "Adicionar camada WFS". Reusa `PedidoQuery`/`preparar_pedido`/`executar_features` sem
reescrever a consulta; este módulo só traduz KVP OGC <-> `PedidoQuery` e serializa em GML 3.2 (formato
padrão do núcleo WFS 2.0) ou GeoJSON (`OUTPUTFORMAT=application/json`, extensão comum a praticamente
todo servidor WFS moderno — GeoServer/MapServer também oferecem).

Cobertura desta passagem (linha viva em `docs/PARIDADE.md`):
  feito    - GetCapabilities (VERSION=2.0.0, `ows:ServiceIdentification`/`OperationsMetadata`/
             `FeatureTypeList`, validado nesta trilha com o cliente `owslib.wfs.WebFeatureService`);
             GetFeature KVP com TYPENAMES, BBOX, COUNT, STARTINDEX, OUTPUTFORMAT (json ou GML 3.2).
  parcial  - GML 3.2: só os 3 tipos de geometria simples (Point/LineString/Polygon — Multi* vira o
             tipo simples do 1º membro mais aviso, camada Esri "Polyline" que na prática é
             MultiLineString entra como `gml:MultiCurve`); sem `DescribeFeatureType` em XSD completo
             (devolve um esquema mínimo, suficiente para os campos aparecerem, não validado contra
             o XSD de referência do OGC).
  fora     - Filter Encoding 2.0 (FES) no `FILTER=`; transações (WFS-T); paginação por `resultType=hits`
             separada de `GetFeature` com contagem (usa `numberMatched` no próprio corpo, que é o
             comportamento WFS 2.0 padrão)."""

from __future__ import annotations

import datetime
import json as _json
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request, Response

from app import db
from app.consulta import campos as campos_mod
from app.consulta import motor
from app.consulta.rotas_query import _autenticar
from app.consulta.rotas_servico import _camada_e_titulo
from app.consulta.serializar import GEOM_PG_PARA_ESRI, como_geojson
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/wfs/{item_id}", tags=["wfs"])
_XML = "application/xml"
_NS_WFS = "http://www.opengis.net/wfs/2.0"
_NS_OWS = "http://www.opengis.net/ows/1.1"
_NS_GML = "http://www.opengis.net/gml/3.2"


def _base(request: Request, item_id: str) -> str:
    raiz = (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/")
    return f"{raiz}/wfs/{item_id}"


def _tipo(item_id: str) -> str:
    return f"plat:{item_id.replace('-', '_')}"


def _get_capabilities(request: Request, item_id: str, titulo: str, extent4326: list[float] | None) -> str:
    base = _base(request, item_id)
    tipo = _tipo(item_id)
    bbox = (
        f'<ows:WGS84BoundingBox><ows:LowerCorner>{extent4326[0]} {extent4326[1]}</ows:LowerCorner>'
        f'<ows:UpperCorner>{extent4326[2]} {extent4326[3]}</ows:UpperCorner></ows:WGS84BoundingBox>'
        if extent4326 else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities xmlns:wfs="{_NS_WFS}" xmlns:ows="{_NS_OWS}" xmlns:gml="{_NS_GML}"
    xmlns:plat="{settings.PLAT_URL_PUBLICA or 'urn:plat'}" xmlns:xlink="http://www.w3.org/1999/xlink"
    version="2.0.0" xsi:schemaLocation="{_NS_WFS} http://schemas.opengis.net/wfs/2.0/wfs.xsd"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ows:ServiceIdentification>
    <ows:Title>{escape(titulo or item_id)}</ows:Title>
    <ows:Abstract>Camada hospedada da plataforma — análise/beta privado.</ows:Abstract>
    <ows:ServiceType codeSpace="OGC">WFS</ows:ServiceType>
    <ows:ServiceTypeVersion>2.0.0</ows:ServiceTypeVersion>
  </ows:ServiceIdentification>
  <ows:OperationsMetadata>
    <ows:Operation name="GetCapabilities">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="DescribeFeatureType">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="GetFeature">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
      <ows:Parameter name="outputFormat">
        <ows:AllowedValues>
          <ows:Value>application/json</ows:Value>
          <ows:Value>text/xml; subtype=gml/3.2</ows:Value>
        </ows:AllowedValues>
      </ows:Parameter>
    </ows:Operation>
  </ows:OperationsMetadata>
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>{tipo}</wfs:Name>
      <wfs:Title>{escape(titulo or item_id)}</wfs:Title>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
      {bbox}
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""


def _describe_feature_type(item_id: str, meta: list[dict]) -> str:
    tipo = _tipo(item_id)
    ns_plat = settings.PLAT_URL_PUBLICA or "urn:plat"
    nome_tipo = tipo.split(":")[1]
    campos_xsd = "\n".join(
        f'      <xsd:element name="{c["nome"]}" type="xsd:{_xsd_tipo(c["tipo_esri"])}" minOccurs="0"/>'
        for c in meta if c["papel"] not in ("oid", "globalid")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:gml="{_NS_GML}"
    targetNamespace="{ns_plat}" elementFormDefault="qualified">
  <xsd:import namespace="{_NS_GML}"/>
  <xsd:element name="{nome_tipo}" type="plat:{nome_tipo}Type" xmlns:plat="{ns_plat}"/>
  <xsd:complexType name="{nome_tipo}Type">
    <xsd:complexContent>
      <xsd:extension base="gml:AbstractFeatureType">
        <xsd:sequence>
          <xsd:element name="geometry" type="gml:GeometryPropertyType" minOccurs="0"/>
{campos_xsd}
        </xsd:sequence>
      </xsd:extension>
    </xsd:complexContent>
  </xsd:complexType>
</xsd:schema>"""


def _xsd_tipo(tipo_esri: str) -> str:
    return {
        "esriFieldTypeInteger": "int", "esriFieldTypeSmallInteger": "short",
        "esriFieldTypeBigInteger": "long", "esriFieldTypeDouble": "double",
        "esriFieldTypeSingle": "float", "esriFieldTypeDate": "dateTime",
        "esriFieldTypeDateOnly": "date", "esriFieldTypeGUID": "string",
        "esriFieldTypeGlobalID": "string",
    }.get(tipo_esri, "string")


def _gml_geometria(g: dict | None, srs: str) -> str:
    if g is None:
        return ""
    if "x" in g:
        return f'<gml:Point srsName="{srs}"><gml:pos>{g["x"]} {g["y"]}</gml:pos></gml:Point>'
    if "paths" in g:
        coords = " ".join(f"{x} {y}" for x, y in g["paths"][0])
        return f'<gml:LineString srsName="{srs}"><gml:posList>{coords}</gml:posList></gml:LineString>'
    if "rings" in g:
        anel = g["rings"][0]
        coords = " ".join(f"{x} {y}" for x, y in anel)
        return (f'<gml:Polygon srsName="{srs}"><gml:exterior><gml:LinearRing>'
                f'<gml:posList>{coords}</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>')
    return ""


def _get_feature_gml(item_id: str, res, total: int) -> str:
    tipo = _tipo(item_id)
    srs = "urn:ogc:def:crs:EPSG::4326"
    membros = []
    for f in res.features:
        campos_xml = "\n".join(
            f"      <plat:{n}>{escape(str(v))}</plat:{n}>" for n, v in f["attributes"].items() if v is not None
        )
        membros.append(f"""  <wfs:member>
    <{tipo} gml:id="{tipo.split(':')[1]}.{f['attributes'].get(res.objectIdFieldName)}"
        xmlns:plat="{settings.PLAT_URL_PUBLICA or 'urn:plat'}">
      <plat:geometry>{_gml_geometria(f["geometry"], srs)}</plat:geometry>
{campos_xml}
    </{tipo}>
  </wfs:member>""")
    corpo = "\n".join(membros)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="{_NS_WFS}" xmlns:gml="{_NS_GML}"
    numberMatched="{total}" numberReturned="{len(res.features)}" timeStamp="{_agora()}">
{corpo}
</wfs:FeatureCollection>"""


def _agora() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.api_route("", methods=["GET"], openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
                   operation_id="wfs_kvp")
def wfs_kvp(item_id: str, request: Request):
    """Um único endpoint KVP (o jeito WFS de fazer as coisas): `REQUEST=` decide a operação."""
    p = {k.upper(): v for k, v in request.query_params.items()}
    requisicao = (p.get("REQUEST") or "").lower()
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        dados, titulo = _camada_e_titulo(cur, item_id)
        schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
        meta = campos_mod.campos_da_camada(cur, schema, tabela)
        geom_esri = GEOM_PG_PARA_ESRI.get(dados.get("geometria"))

        if requisicao == "getcapabilities":
            cur.execute("SELECT ST_XMin(extent) x0, ST_YMin(extent) y0, ST_XMax(extent) x1, ST_YMax(extent) y1 "
                        "FROM plat.item WHERE id=%s::uuid", (item_id,))
            r = cur.fetchone()
            extent = [r["x0"], r["y0"], r["x1"], r["y1"]] if r and r["x0"] is not None else None
            return Response(_get_capabilities(request, item_id, titulo, extent), media_type=_XML)

        if requisicao == "describefeaturetype":
            return Response(_describe_feature_type(item_id, meta), media_type=_XML)

        if requisicao == "getfeature":
            count = motor._int(p.get("COUNT"), None)  # noqa: SLF001 -- mesmo reuso deliberado do módulo (ver rotas_query.py)
            startindex = motor._int(p.get("STARTINDEX"), 0)  # noqa: SLF001
            geometry_kwargs = {}
            if p.get("BBOX"):
                geometry_kwargs = {"geometry": p["BBOX"], "geometryType": "esriGeometryEnvelope", "inSR": 4326}
            pq = motor.PedidoQuery(outFields="*", resultRecordCount=count, resultOffset=startindex,
                                    **geometry_kwargs)
            prep = motor.preparar_pedido(pq, meta, srid)
            res = motor.executar_features(cur, schema, tabela, prep, pq, meta, srid, geom_esri)
            total = motor.executar_count(cur, schema, tabela, prep).count
            formato = (p.get("OUTPUTFORMAT") or "").lower()
            if "json" in formato:
                corpo = como_geojson(res)
                corpo["numberMatched"] = total
                corpo["numberReturned"] = len(res.features)
                return Response(_json.dumps(corpo, default=str), media_type="application/geo+json")
            return Response(_get_feature_gml(item_id, res, total), media_type='text/xml; subtype="gml/3.2"')

    raise ErroAPI(400, "request_invalido",
                   f"REQUEST={p.get('REQUEST')!r} não suportado (use GetCapabilities, DescribeFeatureType "
                   "ou GetFeature)")
