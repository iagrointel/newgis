"""WFS 2.0.0 (ISO 19142 / OGC 09-025r2) e WFS 1.1.0 por compatibilidade, sobre a MESMA camada
hospedada e o MESMO motor de consulta do FeatureServer (item L2-04-c) — protocolo KVP
(`SERVICE=WFS&REQUEST=...`) e POST XML, que é como QGIS, ArcGIS Pro, AGOL/Portal e GDAL falam
"WFS" a partir de uma URL. Este módulo só traduz WFS <-> `PedidoQuery`: nenhuma consulta nova,
nenhum segundo gerador de SQL (o filtro FES é compilado pelo compilador do CQL2, `app.consulta.fes`)
e nenhuma segunda porta de escrita (a Transaction chama `app.edicao.servico.aplicar_edicoes`, a
mesma de `POST /api/camadas/{id}/edicoes`).

Operações: GetCapabilities, DescribeFeatureType, GetFeature, GetPropertyValue, ListStoredQueries,
DescribeStoredQueries, Transaction (Insert/Update/Delete). Consulta armazenada implementada:
`urn:ogc:def:query:OGC-WFS::GetFeatureById`.

Parâmetros de GetFeature: TYPENAMES/TYPENAME, COUNT (2.0) e MAXFEATURES (1.1), STARTINDEX, BBOX
(com CRS opcional no 5º termo), SRSNAME, PROPERTYNAME, SORTBY, RESULTTYPE=hits, FILTER (FES 2.0),
RESOURCEID, OUTPUTFORMAT (GML 3.2 padrão, `application/json` para GeoJSON).

Ordem dos eixos: em WFS 2.0 o CRS padrão é `urn:ogc:def:crs:EPSG::4326`, cuja ordem de autoridade é
LATITUDE, LONGITUDE — tanto na saída quanto no BBOX de entrada. A regra mora em `fes._ordem_lat_lon`
e é aplicada nos dois sentidos aqui.

Fora desta passagem (linha viva em `docs/PARIDADE.md`): GML 3.1.1 de saída no 1.1.0 (o 1.1.0
responde GML 3.2 ou GeoJSON, declarado no próprio Capabilities), junção (`Join`), consulta
armazenada definida pelo cliente (`CreateStoredQuery`) e bloqueio (`LockFeature`/`GetFeatureWithLock`)."""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Request, Response

from app import db
from app.auth import escopos as esc
from app.consulta import campos as campos_mod
from app.consulta import fes as fes_mod
from app.consulta import gml as gml_mod
from app.consulta import motor
from app.consulta.rotas_query import _autenticar
from app.consulta.rotas_servico import _camada_e_titulo
from app.consulta.serializar import GEOM_PG_PARA_ESRI, como_geojson
from app.edicao import modelos as edicao_modelos
from app.edicao import servico as edicao_servico
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/wfs/{item_id}", tags=["wfs"])

_XML = "text/xml; charset=utf-8"
_GML = 'text/xml; subtype="gml/3.2"; charset=utf-8'
VERSOES = ("2.0.0", "1.1.0")
VERSAO_PADRAO = "2.0.0"
CONSULTA_POR_ID = "urn:ogc:def:query:OGC-WFS::GetFeatureById"
TETO_COUNT = 10_000
FORMATOS_GML = ("text/xml; subtype=gml/3.2", "application/gml+xml; version=3.2", "gml32", "gml3")
FORMATOS_JSON = ("application/json", "application/geo+json", "geojson", "json")


def _base(request: Request, item_id: str) -> str:
    raiz = (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/")
    return f"{raiz}/wfs/{item_id}"


def _erro_ows(codigo: str, texto: str, locator: str | None, status: int, versao: str) -> Response:
    return Response(gml_mod.excecao(codigo, texto, locator, versao), media_type=_XML, status_code=status)


def _versao(p: dict) -> str:
    """`ACCEPTVERSIONS` (2.0) e `VERSION`: devolve a maior versão pedida que a casa fala."""
    aceitas = [v.strip() for v in (p.get("ACCEPTVERSIONS") or "").split(",") if v.strip()]
    if aceitas:
        for v in sorted(aceitas, reverse=True):
            if v in VERSOES:
                return v
        raise ErroAPI(400, "versao_nao_suportada", f"versões aceitas: {', '.join(VERSOES)}",
                       {"pedido": aceitas})
    v = (p.get("VERSION") or "").strip()
    if not v:
        return VERSAO_PADRAO
    if v in VERSOES:
        return v
    if v.startswith("2."):
        return "2.0.0"
    if v.startswith("1.1"):
        return "1.1.0"
    raise ErroAPI(400, "versao_nao_suportada", f"versões aceitas: {', '.join(VERSOES)}", {"pedido": v})


def _crs_saida(p: dict, versao: str) -> tuple[int, str, bool]:
    """(srid, srsName devolvido no documento, eixos em lat/lon). Sem SRSNAME vale o padrão da
    versão: URN 4326 (lat/lon) no 2.0, EPSG:4326 (lon/lat) no 1.1."""
    bruto = (p.get("SRSNAME") or p.get("SRSNAME2") or "").strip()
    if not bruto:
        bruto = gml_mod.CRS_PADRAO if versao == "2.0.0" else "EPSG:4326"
    srid = fes_mod.srid_de_srsname(bruto) or 4326
    return srid, bruto, fes_mod._ordem_lat_lon(bruto)  # noqa: SLF001 - a regra de eixo mora num lugar só


def _bbox_para_kwargs(bruto: str) -> dict:
    """BBOX do WFS: 4 números e um CRS opcional no 5º termo. Se o CRS estiver em forma de
    autoridade (URN/URL) e for geográfico, os números vêm em latitude, longitude."""
    partes = [x.strip() for x in bruto.split(",") if x.strip()]
    if len(partes) < 4:
        raise ErroAPI(400, "bbox_invalido", "BBOX precisa de 4 números (e um CRS opcional no 5º termo)")
    crs = partes[4] if len(partes) >= 5 else None
    try:
        a0, b0, a1, b1 = (float(x) for x in partes[:4])
    except ValueError as e:
        raise ErroAPI(400, "bbox_invalido", "BBOX com valor não numérico") from e
    if crs and fes_mod._ordem_lat_lon(crs):  # noqa: SLF001
        a0, b0, a1, b1 = b0, a0, b1, a1
    srid = fes_mod.srid_de_srsname(crs) if crs else 4326
    if a0 > a1 or b0 > b1:
        raise ErroAPI(400, "bbox_invalido", "BBOX invertido: mínimos precisam ser <= máximos", {"bbox": bruto})
    return {"geometry": f"{a0},{b0},{a1},{b1}", "geometryType": "esriGeometryEnvelope", "inSR": srid or 4326}


def _sortby(bruto: str | None) -> str | None:
    """`campo ASC,outro DESC` (2.0) e `campo A,outro D` (1.1) -> `orderByFields` do motor."""
    if not bruto:
        return None
    saida = []
    for termo in bruto.split(","):
        partes = termo.replace("+", " ").strip().split()
        if not partes:
            continue
        campo = partes[0]
        direcao = (partes[1].upper() if len(partes) > 1 else "ASC")
        direcao = "DESC" if direcao in ("D", "DESC", "DESCENDING") else "ASC"
        saida.append(f"{campo} {direcao}")
    return ",".join(saida) or None


def _formato(bruto: str | None) -> str:
    f = (bruto or "").strip().lower()
    if not f:
        return "gml"
    if any(j in f for j in FORMATOS_JSON):
        return "json"
    if "gml" in f or "xml" in f:
        return "gml"
    raise ErroAPI(400, "outputformat_invalido",
                   f"OUTPUTFORMAT não suportado: {bruto!r} (use GML 3.2 ou application/json)")


def _campo_oid(meta: list[dict]) -> str:
    for c in meta:
        if c["papel"] == "oid":
            return c["nome"]
    return "fid"


def _propertyname(bruto: str | None, meta: list[dict]) -> tuple[str, list[str] | None]:
    """PROPERTYNAME -> (`outFields` do motor, lista para o escritor GML). `geometria` é nome de
    propriedade no documento, mas não é coluna: nunca vai para o `outFields`."""
    if not bruto or bruto.strip() in ("*", ""):
        return "*", None
    nomes = []
    for n in bruto.split(","):
        n = n.strip()
        if ":" in n:
            n = n.rsplit(":", 1)[1]
        if n:
            nomes.append(n)
    validos = {c["nome"] for c in meta} | {"geometria"}
    for n in nomes:
        if n not in validos:
            raise ErroAPI(400, "propertyname_invalido", f"propriedade inexistente: {n!r}", {"campo": n})
    colunas = [n for n in nomes if n != "geometria"]
    return (",".join(colunas) if colunas else _campo_oid(meta)), nomes


def _ids_para_objectids(ids: list[str], nome: str) -> str:
    """`rid` da forma `tipo.123` -> `123` (o OID que o motor entende)."""
    saida = []
    for rid in ids:
        cru = rid.split(".")[-1] if rid.startswith(f"{nome}.") or "." in rid else rid
        if not cru.lstrip("-").isdigit():
            raise ErroAPI(400, "resourceid_invalido",
                           f"identificador de feição precisa terminar no OID inteiro: {rid!r}")
        saida.append(cru)
    return ",".join(saida)


# ------------------------------------------------------------------------------------ documentos
def _capabilities(request: Request, item_id: str, titulo: str, extent: list | None, versao: str) -> str:
    base = _base(request, item_id)
    tipo = gml_mod.tipo_qualificado(item_id)
    ns_wfs = gml_mod.NS_WFS if versao == "2.0.0" else "http://www.opengis.net/wfs"
    ns_ows = gml_mod.NS_OWS if versao == "2.0.0" else "http://www.opengis.net/ows"
    caixa = ""
    if extent:
        caixa = (f"<ows:WGS84BoundingBox><ows:LowerCorner>{extent[0]} {extent[1]}</ows:LowerCorner>"
                 f"<ows:UpperCorner>{extent[2]} {extent[3]}</ows:UpperCorner></ows:WGS84BoundingBox>")
    from xml.sax.saxutils import escape as _e

    formatos = "".join(f"<ows:Value>{f}</ows:Value>" for f in (
        "application/gml+xml; version=3.2", "text/xml; subtype=gml/3.2", "application/json"))
    if versao == "1.1.0":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities xmlns:wfs="{ns_wfs}" xmlns:ows="{ns_ows}" xmlns:gml="http://www.opengis.net/gml"
    xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="{gml_mod.NS_XLINK}"
    xmlns:{gml_mod.PREFIXO_PLAT}="{gml_mod.NS_PLAT}" version="1.1.0">
  <ows:ServiceIdentification>
    <ows:Title>{_e(titulo or item_id)}</ows:Title>
    <ows:Abstract>Camada hospedada da plataforma — análise/beta privado.</ows:Abstract>
    <ows:ServiceType>WFS</ows:ServiceType>
    <ows:ServiceTypeVersion>1.1.0</ows:ServiceTypeVersion>
    <ows:Fees>NONE</ows:Fees>
    <ows:AccessConstraints>NONE</ows:AccessConstraints>
  </ows:ServiceIdentification>
  <ows:OperationsMetadata>
    <ows:Operation name="GetCapabilities">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="DescribeFeatureType">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="GetFeature">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/><ows:Post xlink:href="{base}"/></ows:HTTP></ows:DCP>
      <ows:Parameter name="outputFormat"><ows:Value>text/xml; subtype=gml/3.2</ows:Value>
        <ows:Value>application/json</ows:Value></ows:Parameter>
    </ows:Operation>
  </ows:OperationsMetadata>
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>{tipo}</wfs:Name>
      <wfs:Title>{_e(titulo or item_id)}</wfs:Title>
      <wfs:DefaultSRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultSRS>
      <wfs:OtherSRS>EPSG:4326</wfs:OtherSRS>
      <wfs:OutputFormats><wfs:Format>text/xml; subtype=gml/3.2</wfs:Format>
        <wfs:Format>application/json</wfs:Format></wfs:OutputFormats>
      {caixa}
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>
"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities xmlns:wfs="{ns_wfs}" xmlns:ows="{ns_ows}" xmlns:gml="{gml_mod.NS_GML}"
    xmlns:fes="{gml_mod.NS_FES}" xmlns:xlink="{gml_mod.NS_XLINK}"
    xmlns:{gml_mod.PREFIXO_PLAT}="{gml_mod.NS_PLAT}" version="2.0.0">
  <ows:ServiceIdentification>
    <ows:Title>{_e(titulo or item_id)}</ows:Title>
    <ows:Abstract>Camada hospedada da plataforma — análise/beta privado.</ows:Abstract>
    <ows:ServiceType codeSpace="OGC">WFS</ows:ServiceType>
    <ows:ServiceTypeVersion>2.0.0</ows:ServiceTypeVersion>
    <ows:ServiceTypeVersion>1.1.0</ows:ServiceTypeVersion>
    <ows:Fees>NONE</ows:Fees>
    <ows:AccessConstraints>NONE</ows:AccessConstraints>
  </ows:ServiceIdentification>
  <ows:OperationsMetadata>
    <ows:Operation name="GetCapabilities">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
      <ows:Parameter name="AcceptVersions"><ows:AllowedValues>
        <ows:Value>2.0.0</ows:Value><ows:Value>1.1.0</ows:Value></ows:AllowedValues></ows:Parameter>
    </ows:Operation>
    <ows:Operation name="DescribeFeatureType">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="GetFeature">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/><ows:Post xlink:href="{base}"/></ows:HTTP></ows:DCP>
      <ows:Parameter name="outputFormat"><ows:AllowedValues>{formatos}</ows:AllowedValues></ows:Parameter>
      <ows:Parameter name="resultType"><ows:AllowedValues>
        <ows:Value>results</ows:Value><ows:Value>hits</ows:Value></ows:AllowedValues></ows:Parameter>
    </ows:Operation>
    <ows:Operation name="GetPropertyValue">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="ListStoredQueries">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="DescribeStoredQueries">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="Transaction">
      <ows:DCP><ows:HTTP><ows:Post xlink:href="{base}"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Constraint name="ImplementsBasicWFS"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsTransactionalWFS"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsLockingWFS"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="KVPEncoding"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="XMLEncoding"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="SOAPEncoding"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsInheritance"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsRemoteResolve"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsResultPaging"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsStandardJoins"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsSpatialJoins"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsTemporalJoins"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ImplementsFeatureVersioning"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="ManageStoredQueries"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="CountDefault"><ows:NoValues/><ows:DefaultValue>1000</ows:DefaultValue></ows:Constraint>
    <ows:Constraint name="QueryExpressions"><ows:AllowedValues>
      <ows:Value>wfs:Query</ows:Value><ows:Value>wfs:StoredQuery</ows:Value></ows:AllowedValues></ows:Constraint>
  </ows:OperationsMetadata>
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>{tipo}</wfs:Name>
      <wfs:Title>{_e(titulo or item_id)}</wfs:Title>
      <wfs:Abstract>Camada vetorial hospedada; triagem: sinal, não prova.</wfs:Abstract>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
      <wfs:OtherCRS>http://www.opengis.net/def/crs/OGC/1.3/CRS84</wfs:OtherCRS>
      <wfs:OutputFormats><wfs:Format>application/gml+xml; version=3.2</wfs:Format>
        <wfs:Format>text/xml; subtype=gml/3.2</wfs:Format>
        <wfs:Format>application/json</wfs:Format></wfs:OutputFormats>
      {caixa}
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
  <fes:Filter_Capabilities>
    <fes:Conformance>
      <fes:Constraint name="ImplementsQuery"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsAdHocQuery"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsFunctions"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsResourceId"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsMinStandardFilter"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsStandardFilter"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsMinSpatialFilter"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsSpatialFilter"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsMinTemporalFilter"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsTemporalFilter"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsVersionNav"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsSorting"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></fes:Constraint>
      <fes:Constraint name="ImplementsExtendedOperators"><ows:NoValues/><ows:DefaultValue>FALSE</ows:DefaultValue></fes:Constraint>
    </fes:Conformance>
    <fes:Id_Capabilities><fes:ResourceIdentifier name="fes:ResourceId"/></fes:Id_Capabilities>
    <fes:Scalar_Capabilities>
      <fes:LogicalOperators/>
      <fes:ComparisonOperators>
        <fes:ComparisonOperator name="PropertyIsEqualTo"/>
        <fes:ComparisonOperator name="PropertyIsNotEqualTo"/>
        <fes:ComparisonOperator name="PropertyIsLessThan"/>
        <fes:ComparisonOperator name="PropertyIsGreaterThan"/>
        <fes:ComparisonOperator name="PropertyIsLessThanOrEqualTo"/>
        <fes:ComparisonOperator name="PropertyIsGreaterThanOrEqualTo"/>
        <fes:ComparisonOperator name="PropertyIsLike"/>
        <fes:ComparisonOperator name="PropertyIsBetween"/>
        <fes:ComparisonOperator name="PropertyIsNull"/>
      </fes:ComparisonOperators>
    </fes:Scalar_Capabilities>
    <fes:Spatial_Capabilities>
      <fes:GeometryOperands>
        <fes:GeometryOperand name="gml:Envelope"/>
        <fes:GeometryOperand name="gml:Point"/>
        <fes:GeometryOperand name="gml:LineString"/>
        <fes:GeometryOperand name="gml:Polygon"/>
      </fes:GeometryOperands>
      <fes:SpatialOperators>
        <fes:SpatialOperator name="BBOX"/>
        <fes:SpatialOperator name="Intersects"/>
        <fes:SpatialOperator name="Within"/>
        <fes:SpatialOperator name="DWithin"/>
      </fes:SpatialOperators>
    </fes:Spatial_Capabilities>
    <fes:Temporal_Capabilities>
      <fes:TemporalOperands>
        <fes:TemporalOperand name="gml:TimeInstant"/>
        <fes:TemporalOperand name="gml:TimePeriod"/>
      </fes:TemporalOperands>
      <fes:TemporalOperators>
        <fes:TemporalOperator name="After"/>
        <fes:TemporalOperator name="Before"/>
        <fes:TemporalOperator name="During"/>
      </fes:TemporalOperators>
    </fes:Temporal_Capabilities>
  </fes:Filter_Capabilities>
</wfs:WFS_Capabilities>
"""


def _lista_consultas(base: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:ListStoredQueriesResponse xmlns:wfs="{gml_mod.NS_WFS}" xmlns:{gml_mod.PREFIXO_PLAT}="{gml_mod.NS_PLAT}">
  <wfs:StoredQuery id="{CONSULTA_POR_ID}">
    <wfs:Title>Feição por identificador</wfs:Title>
  </wfs:StoredQuery>
</wfs:ListStoredQueriesResponse>
"""


def _descreve_consultas(item_id: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:DescribeStoredQueriesResponse xmlns:wfs="{gml_mod.NS_WFS}" xmlns:{gml_mod.PREFIXO_PLAT}="{gml_mod.NS_PLAT}">
  <wfs:StoredQueryDescription id="{CONSULTA_POR_ID}">
    <wfs:Title>Feição por identificador</wfs:Title>
    <wfs:Abstract>Devolve uma feição pelo seu gml:id (tipo.OID).</wfs:Abstract>
    <wfs:Parameter name="id" type="xsd:string"/>
    <wfs:QueryExpressionText isPrivate="false" language="urn:ogc:def:queryLanguage:OGC-WFS::WFSQueryExpression"
        returnFeatureTypes="{gml_mod.tipo_qualificado(item_id)}"/>
  </wfs:StoredQueryDescription>
</wfs:DescribeStoredQueriesResponse>
"""


def _resposta_transacao(n_add: int, n_upd: int, n_del: int, ids: list[str], nome: str) -> str:
    inseridos = "".join(
        f'    <wfs:Feature><fes:ResourceId rid="{nome}.{i}"/></wfs:Feature>\n' for i in ids
    )
    bloco = f"  <wfs:InsertResults>\n{inseridos}  </wfs:InsertResults>\n" if ids else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:TransactionResponse xmlns:wfs="{gml_mod.NS_WFS}" xmlns:fes="{gml_mod.NS_FES}" version="2.0.0">
  <wfs:TransactionSummary>
    <wfs:totalInserted>{n_add}</wfs:totalInserted>
    <wfs:totalUpdated>{n_upd}</wfs:totalUpdated>
    <wfs:totalDeleted>{n_del}</wfs:totalDeleted>
  </wfs:TransactionSummary>
{bloco}</wfs:TransactionResponse>
"""


# ------------------------------------------------------------------------------------ GetFeature
def _pedido_get_feature(p: dict, meta: list[dict], versao: str, item_id: str, srid_nativo: int):
    """Monta o `PedidoQuery` e o filtro FES; devolve (pedido, campos_saida, sql_extra, params_extra)."""
    nome = gml_mod.nome_tipo(item_id)
    count = motor._int(p.get("COUNT") or p.get("MAXFEATURES"), None)  # noqa: SLF001 - mesmo reuso de rotas_query
    if count is not None:
        if count < 0:
            raise ErroAPI(400, "count_invalido", "COUNT precisa ser >= 0")
        count = min(count, TETO_COUNT)
    inicio = motor._int(p.get("STARTINDEX"), 0)  # noqa: SLF001
    if inicio < 0:
        raise ErroAPI(400, "startindex_invalido", "STARTINDEX precisa ser >= 0")
    kwargs = {}
    if p.get("BBOX"):
        kwargs = _bbox_para_kwargs(p["BBOX"])
    out_fields, campos_saida = _propertyname(p.get("PROPERTYNAME"), meta)
    srid_saida, _srs, _lat_lon = _crs_saida(p, versao)
    ids = [x.strip() for x in (p.get("RESOURCEID") or "").split(",") if x.strip()]
    sql_extra, params_extra = None, []
    if p.get("FILTER"):
        colunas_sql = campos_mod.lista_branca(meta)
        colunas_sql.setdefault("geometria", "geom")
        colunas_sql.setdefault("geometry", "geom")
        try:
            sql_extra, params_extra, ids_filtro = fes_mod.compilar_fes(
                p["FILTER"], colunas_sql, srid_nativo)
        except fes_mod.ErroFes as e:
            raise ErroAPI(400, e.codigo, e.mensagem, e.detalhe) from e
        ids += ids_filtro
    pedido = motor.PedidoQuery(
        outFields=out_fields, resultRecordCount=count, resultOffset=inicio, outSR=srid_saida,
        orderByFields=_sortby(p.get("SORTBY")),
        objectIds=_ids_para_objectids(ids, nome) if ids else None, **kwargs)
    return pedido, campos_saida, sql_extra, params_extra


def _executar_get_feature(cur, item_id: str, p: dict, versao: str, base: str, valores: bool = False):
    dados, _titulo = _camada_e_titulo(cur, item_id)
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    meta = campos_mod.campos_da_camada(cur, schema, tabela)
    geom_esri = GEOM_PG_PARA_ESRI.get(dados.get("geometria"))
    pedido, campos_saida, sql_extra, params_extra = _pedido_get_feature(p, meta, versao, item_id, srid)
    prep = motor.preparar_pedido(pedido, meta, srid)
    if sql_extra:
        prep["where_sql"] = f"({prep['where_sql']}) AND ({sql_extra})"
        prep["where_params"] = [*prep["where_params"], *params_extra]
    total = motor.executar_count(cur, schema, tabela, prep).count
    srid_saida, srs, lat_lon = _crs_saida(p, versao)
    formato = _formato(p.get("OUTPUTFORMAT"))
    if (p.get("RESULTTYPE") or "").lower() == "hits" and not valores:
        if formato == "json":
            return Response(_json.dumps({"type": "FeatureCollection", "features": [],
                                          "numberMatched": total, "numberReturned": 0}),
                             media_type="application/geo+json")
        return Response(gml_mod.colecao_hits(total), media_type=_GML)
    res = motor.executar_features(cur, schema, tabela, prep, pedido, meta, srid, geom_esri)
    corpo = como_geojson(res)
    campo_oid = _campo_oid(meta)
    if valores:
        alvo = (p.get("VALUEREFERENCE") or p.get("PROPERTYNAME") or "").strip()
        if ":" in alvo:
            alvo = alvo.rsplit(":", 1)[1]
        if not alvo:
            raise ErroAPI(400, "valuereference_ausente", "GetPropertyValue exige VALUEREFERENCE")
        if alvo not in {c["nome"] for c in meta} | {"geometria"}:
            raise ErroAPI(400, "valuereference_invalida", f"propriedade inexistente: {alvo!r}")
        return Response(gml_mod.colecao_valores(item_id, corpo, meta, srs, lat_lon, campo_oid, alvo, total),
                         media_type=_GML)
    if formato == "json":
        corpo["numberMatched"] = total
        corpo["numberReturned"] = len(res.features)
        corpo["timeStamp"] = gml_mod.agora()
        return Response(_json.dumps(corpo, default=str), media_type="application/geo+json")
    url_esquema = (f"{base}?SERVICE=WFS&VERSION={versao}&REQUEST=DescribeFeatureType"
                    f"&TYPENAMES={gml_mod.tipo_qualificado(item_id)}")
    if campos_saida is not None:
        meta_saida = [c for c in meta if c["nome"] in campos_saida or c["papel"] == "oid"]
    else:
        meta_saida = meta
    return Response(
        gml_mod.colecao_feicoes(item_id, corpo, meta_saida, srs, lat_lon, campo_oid, total, url_esquema),
        media_type=_GML)


# ------------------------------------------------------------------------------------ Transaction
def _feicao_de_elemento(elem, meta: list[dict]) -> dict:
    """Elemento de feição do documento (namespace da plataforma) -> `{atributos, geometria}` da
    porta de escrita da casa."""
    nomes = {c["nome"] for c in meta}
    atributos: dict = {}
    geometria = None
    for filho in elem:
        nome = fes_mod._local(filho.tag)  # noqa: SLF001
        if nome == "geometria":
            for g in filho:
                geometria = fes_mod.geometria_para_geojson(g)
                break
        elif nome in nomes:
            atributos[nome] = (filho.text or "").strip()
    return {"atributos": atributos, "geometria": geometria}


def _transacao(cur, request: Request, auth, item_id: str, raiz, meta: list[dict]):
    adicionar, atualizar, apagar = [], [], []
    for acao in raiz:
        nome = fes_mod._local(acao.tag)  # noqa: SLF001
        if nome == "Insert":
            for feicao in acao:
                adicionar.append(_feicao_de_elemento(feicao, meta))
        elif nome == "Update":
            alvo, valores = None, {}
            for filho in acao:
                marca = fes_mod._local(filho.tag)  # noqa: SLF001
                if marca == "Property":
                    ref = val = None
                    for parte in filho:
                        pm = fes_mod._local(parte.tag)  # noqa: SLF001
                        if pm in ("ValueReference", "Name"):
                            ref = (parte.text or "").strip().rsplit(":", 1)[-1]
                        elif pm == "Value":
                            val = (parte.text or "").strip()
                    if ref:
                        valores[ref] = val
                elif marca == "Filter":
                    ids = fes_mod.ids_de(filho)
                    alvo = ids[0] if ids else None
            if not alvo:
                raise ErroAPI(400, "transacao_sem_alvo",
                               "wfs:Update precisa de fes:Filter com fes:ResourceId (a casa não "
                               "atualiza em massa por predicado nesta passagem)")
            atualizar.append({"id_wfs": alvo, "atributos": valores})
        elif nome == "Delete":
            for filho in acao:
                if fes_mod._local(filho.tag) == "Filter":  # noqa: SLF001
                    for rid in fes_mod.ids_de(filho):
                        apagar.append(rid)
    return adicionar, atualizar, apagar


def _identidade_de_oid(cur, schema: str, tabela: str, oid: str) -> tuple[str, int]:
    """(globalid, versao) da feição pelo OID. O WFS não carrega versão de linha; a porta de escrita
    da casa exige uma (concorrência otimista, L2-03-a), então ela é lida na MESMA transação da
    escrita — a trava da própria porta continua valendo, nada é ignorado."""
    cur.execute(f'SELECT globalid, versao FROM "{schema}"."{tabela}" WHERE fid = %s', (int(oid),))  # noqa: S608 - schema/tabela vêm de plat.item
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "feicao_nao_encontrada", f"nenhuma feição com id {oid!r}")
    return str(r["globalid"]), int(r["versao"])


# ------------------------------------------------------------------------------------ rotas
def _parametros(request: Request, corpo: bytes | None = None) -> dict:
    p = {k.upper(): v for k, v in request.query_params.items()}
    if corpo:
        raiz = fes_mod.ler_xml(corpo)
        p["_XML"] = raiz
        p["REQUEST"] = fes_mod._local(raiz.tag)  # noqa: SLF001
        for chave in ("version", "outputFormat", "resultType", "count", "startIndex", "srsName"):
            if raiz.get(chave):
                p[chave.upper()] = raiz.get(chave)
    return p


def _consulta_do_xml(raiz, p: dict) -> dict:
    """`wfs:GetFeature` em XML -> os mesmos nomes de parâmetro do KVP (um caminho de execução só)."""
    for filho in raiz:
        nome = fes_mod._local(filho.tag)  # noqa: SLF001
        if nome == "Query":
            if filho.get("typeNames") or filho.get("typeName"):
                p["TYPENAMES"] = filho.get("typeNames") or filho.get("typeName")
            if filho.get("srsName"):
                p["SRSNAME"] = filho.get("srsName")
            for parte in filho:
                marca = fes_mod._local(parte.tag)  # noqa: SLF001
                if marca == "Filter":
                    from defusedxml.ElementTree import tostring as _tostring

                    p["FILTER"] = _tostring(parte)
                elif marca in ("PropertyName", "ValueReference"):
                    anterior = p.get("PROPERTYNAME")
                    valor = (parte.text or "").strip()
                    p["PROPERTYNAME"] = f"{anterior},{valor}" if anterior else valor
                elif marca == "SortBy":
                    termos = []
                    for prop in parte:
                        campo = direcao = None
                        for x in prop:
                            xm = fes_mod._local(x.tag)  # noqa: SLF001
                            if xm in ("ValueReference", "PropertyName"):
                                campo = (x.text or "").strip()
                            elif xm == "SortOrder":
                                direcao = (x.text or "").strip()
                        if campo:
                            termos.append(f"{campo} {direcao or 'ASC'}")
                    if termos:
                        p["SORTBY"] = ",".join(termos)
        elif nome == "StoredQuery":
            p["STOREDQUERY_ID"] = filho.get("id")
            for parte in filho:
                if fes_mod._local(parte.tag) == "Parameter":  # noqa: SLF001
                    p[(parte.get("name") or "").upper()] = "".join(parte.itertext()).strip()
    return p


def _despachar(request: Request, item_id: str, p: dict, corpo_xml) -> Response:
    versao = _versao(p)
    requisicao = (p.get("REQUEST") or "").lower()
    servico = (p.get("SERVICE") or "WFS").upper()
    if servico != "WFS":
        raise ErroAPI(400, "servico_invalido", f"SERVICE precisa ser WFS, veio {servico!r}")
    base = _base(request, item_id)
    auth = _autenticar(request, item_id)
    escrita = requisicao == "transaction"
    if escrita:
        esc.exigir_escopo(auth, "camada:editar", item_id)
        if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
            raise ErroAPI(403, "sem_privilegio",
                           "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
                           {"exigido": "feicoes.editar|feicoes.editar_total"})
    with db.db(auth.contexto()) as cur:
        if requisicao == "getcapabilities":
            dados, titulo = _camada_e_titulo(cur, item_id)
            cur.execute("SELECT ST_XMin(extent) x0, ST_YMin(extent) y0, ST_XMax(extent) x1, "
                        "ST_YMax(extent) y1 FROM plat.item WHERE id=%s::uuid", (item_id,))
            r = cur.fetchone()
            extent = [r["x0"], r["y0"], r["x1"], r["y1"]] if r and r["x0"] is not None else None
            return Response(_capabilities(request, item_id, titulo, extent, versao), media_type=_XML)

        if requisicao == "describefeaturetype":
            dados, _t = _camada_e_titulo(cur, item_id)
            meta = campos_mod.campos_da_camada(cur, dados["schema"], dados["tabela"])
            return Response(gml_mod.descrever_tipo(item_id, meta, dados.get("geometria")),
                             media_type="application/gml+xml; version=3.2")

        if requisicao == "liststoredqueries":
            return Response(_lista_consultas(base), media_type=_XML)

        if requisicao == "describestoredqueries":
            return Response(_descreve_consultas(item_id), media_type=_XML)

        if requisicao in ("getfeature", "getpropertyvalue"):
            if corpo_xml is not None:
                p = _consulta_do_xml(corpo_xml, p)
            consulta = (p.get("STOREDQUERY_ID") or "").strip()
            if consulta:
                if consulta != CONSULTA_POR_ID:
                    raise ErroAPI(400, "storedquery_desconhecida",
                                   f"única consulta armazenada implementada: {CONSULTA_POR_ID}")
                if not p.get("ID"):
                    raise ErroAPI(400, "storedquery_sem_id", "GetFeatureById exige o parâmetro ID")
                p["RESOURCEID"] = p["ID"]
            return _executar_get_feature(cur, item_id, p, versao, base,
                                          valores=requisicao == "getpropertyvalue")

        if requisicao == "transaction":
            dados, _t = _camada_e_titulo(cur, item_id)
            schema, tabela = dados["schema"], dados["tabela"]
            meta = campos_mod.campos_da_camada(cur, schema, tabela)
            adicionar, atualizar, apagar = _transacao(cur, request, auth, item_id, corpo_xml, meta)
            nome = gml_mod.nome_tipo(item_id)
            atualizar_modelos = []
            for u in atualizar:
                gid, versao_linha = _identidade_de_oid(
                    cur, schema, tabela, _ids_para_objectids([u["id_wfs"]], nome))
                atualizar_modelos.append(edicao_modelos.FeicaoAtualizar(
                    id=gid, versao=versao_linha, atributos=u["atributos"] or None,
                    geometria=u.get("geometria")))
            apagar_modelos = [
                edicao_modelos.FeicaoApagar(
                    id=_identidade_de_oid(cur, schema, tabela, _ids_para_objectids([rid], nome))[0])
                for rid in apagar
            ]
            entrada = edicao_modelos.EdicoesEntrada(
                crs=edicao_modelos.Crs(srid=4326),  # a geometria do documento WFS chega em WGS84 (fes)
                adicionar=[edicao_modelos.FeicaoAdicionar(**f) for f in adicionar],
                atualizar=atualizar_modelos,
                apagar=apagar_modelos,
            )
            saida = edicao_servico.aplicar_edicoes(cur, request, auth, item_id, entrada, origem="wfs")
            ids = []
            for r in saida.adicionar:
                if r.sucesso and r.fid is not None:
                    ids.append(str(r.fid))
            return Response(
                _resposta_transacao(len([r for r in saida.adicionar if r.sucesso]),
                                     len([r for r in saida.atualizar if r.sucesso]),
                                     len([r for r in saida.apagar if r.sucesso]), ids, nome),
                media_type=_XML)

    raise ErroAPI(400, "request_invalido",
                   f"REQUEST={p.get('REQUEST')!r} não suportado (GetCapabilities, DescribeFeatureType, "
                   "GetFeature, GetPropertyValue, ListStoredQueries, DescribeStoredQueries, Transaction)")


@router.api_route("", methods=["GET"], openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
                   operation_id="wfs_kvp")
def wfs_kvp(item_id: str, request: Request):
    """Um endpoint KVP só (o jeito WFS de fazer as coisas): `REQUEST=` decide a operação."""
    return _despachar(request, item_id, _parametros(request), None)


@router.api_route("", methods=["POST"], openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
                   operation_id="wfs_xml")
async def wfs_xml(item_id: str, request: Request):
    """POST XML: `wfs:GetFeature`, `wfs:GetPropertyValue` e `wfs:Transaction` — o caminho que o
    ArcGIS Pro e o QGIS usam para editar e para consulta com filtro grande."""
    corpo = await request.body()
    if not corpo:
        return _despachar(request, item_id, _parametros(request), None)
    try:
        p = _parametros(request, corpo)
    except fes_mod.ErroFes as e:
        raise ErroAPI(400, e.codigo, e.mensagem, e.detalhe) from e
    return _despachar(request, item_id, p, p.pop("_XML"))
