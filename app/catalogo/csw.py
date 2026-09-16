"""CSW 2.0.2 (OGC 07-006r1) sobre o catálogo (item L0-09-metadado-catalogo, cláusula 1; refutação G4:
"portão não cumprido — sem CSW GetRecords, sem ISO 19115-3, sem editor de metadado na tela"). Complementa
`/ogc/records` (OGC API Records, a linha ativa do OGC — ver `app/catalogo/rotas_ogc.py`) com o protocolo
legado que cliente de catálogo mais antigo (GeoNetwork, pycsw, QGIS "Metadata Search", INDE) ainda fala:
GetCapabilities, GetRecords e GetRecordById, os três por KVP — o único jeito que esse cliente usa; POST XML
com corpo `csw:GetRecords` fica de fora nesta passagem (mesma decisão de custo que `rotas_ogc.py` já registrou
para o CSW inteiro: RAM no limite, nenhuma biblioteca CSW instalada, protocolo legado).

Saída em três `outputSchema`:
- Dublin Core (`csw:Record`, o padrão da Parte 1 do CSW) — sempre disponível, um resumo por item.
- ISO 19139 (`outputSchema=http://www.isotc211.org/2005/gmd`, alias curto `gmd`) — reaproveita
  `app.catalogo.metadado.montar_md_metadata`/`gerar_xml`/`validar`, o MESMO gerador de
  `GET /api/itens/{id}/metadado.xml`; nunca um segundo gerador ISO (D17: um lugar de verdade).
- ISO 19115-3 (`outputSchema=http://standards.iso.org/iso/19115/-3/mdb/2.0`, alias curto `mdb`/`iso19115-3` —
  item L0-09-metadado-catalogo, cláusula 2/D42) — reaproveita `metadado.montar_md_metadata_19115_3`/
  `gerar_xml_19115_3`/`validar_19115_3`, o MESMO gerador de `GET /api/itens/{id}/metadado.xml?formato=19115-3`.

Autenticação: sempre `catalogo:ler` (sessão OU token de serviço do L0-02) — nunca aberta, mesma regra do
`/ogc/records`. Isolamento por inquilino vem de graça da RLS de `plat.item`, pelos MESMOS `listar_ids`/
`carregar_varios`/`item_ou_404` que `/ogc/records` e `GET /api/itens` já usam — não de um filtro escrito
aqui (refutação do item: token/sessão de um inquilino nunca lê registro de outro).

Filtro: CQL mínimo (`AnyText LIKE '%termo%'`), a única cláusula que o portão pede — mapeado ao mesmo `q` de
busca textual que `GET /api/itens`/`/ogc/records` já usam. Qualquer outra sintaxe de CQL/Filter Encoding é
400 `cql_nao_suportado`, nomeado, nunca ignorado em silêncio."""

import datetime
from xml.sax.saxutils import escape

from lxml import etree

from app.catalogo import comum, metadado
from app.erros import ErroAPI

CSW = "http://www.opengis.net/cat/csw/2.0.2"
OWS = "http://www.opengis.net/ows"
OGC = "http://www.opengis.net/ogc"
XLINK = "http://www.w3.org/1999/xlink"
DC = "http://purl.org/dc/elements/1.1/"
DCT = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
GMD = metadado.GMD
GCO = metadado.GCO
MDB = metadado.MDB

# aliases aceitos em ?outputSchema= para pedir ISO 19139 (o cliente típico manda a URI completa; QGIS/pycsw
# aceitam o alias curto também)
OUTPUT_SCHEMA_ISO = (GMD, "gmd", "iso19139", "csw:IsoRecord")
# idem para ISO 19115-3/mdb (D42, cláusula 2 do item)
OUTPUT_SCHEMA_ISO_19115_3 = (MDB, "mdb", "iso19115-3")
NS_RECORDS = {"csw": CSW, "ows": OWS, "dc": DC, "dct": DCT, "xsi": XSI}
NS_ISO = {"csw": CSW, "gmd": GMD, "gco": GCO, "xsi": XSI}
NS_ISO_19115_3 = {"csw": CSW, **metadado.NSMAP_19115_3}


def _perfil_iso(output_schema: str) -> str | None:
    """`None` = Dublin Core; `"19139"`/`"19115-3"` = qual gerador ISO usar — nunca duas checagens soltas
    espalhadas pelas duas funções de resposta abaixo."""
    if output_schema in OUTPUT_SCHEMA_ISO_19115_3:
        return "19115-3"
    if output_schema in OUTPUT_SCHEMA_ISO:
        return "19139"
    return None


def _agora() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base(base_url: str) -> str:
    return base_url.rstrip("/") + "/csw"


def get_capabilities(base_url: str, titulo: str) -> bytes:
    """GetCapabilities estático + template (o mesmo padrão de `app/consulta/rotas_wfs.py::_get_capabilities`):
    sem biblioteca CSW, texto construído à mão porque o corpo não leva dado do usuário (só título do
    catálogo, escapado). Não há XSD `CSW-discovery.xsd` cacheado nesta máquina (`docs/xsd/cache/` tem as
    árvores ISO 19139, ISO 19115-3 e WFS/WMS/WMTS, não a do próprio CSW) — a prova de que o XML é bem formado
    fica para o teste (parse com lxml); validar contra o XSD oficial do CSW é pendência à parte, não ligada
    à cláusula 2 do item (essa já fechou: ver `metadado.validar_19115_3`)."""
    base = _base(base_url)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<csw:Capabilities xmlns:csw="{CSW}" xmlns:ows="{OWS}" xmlns:ogc="{OGC}" xmlns:xlink="{XLINK}"
    xmlns:xsi="{XSI}" version="2.0.2"
    xsi:schemaLocation="{CSW} http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd">
  <ows:ServiceIdentification>
    <ows:Title>{escape(titulo)}</ows:Title>
    <ows:Abstract>Catálogo da plataforma por CSW 2.0.2 — análise/beta privado.</ows:Abstract>
    <ows:ServiceType codeSpace="OGC">CSW</ows:ServiceType>
    <ows:ServiceTypeVersion>2.0.2</ows:ServiceTypeVersion>
  </ows:ServiceIdentification>
  <ows:OperationsMetadata>
    <ows:Operation name="GetCapabilities">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
    </ows:Operation>
    <ows:Operation name="GetRecords">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
      <ows:Parameter name="outputSchema">
        <ows:Value>{CSW}</ows:Value>
        <ows:Value>{GMD}</ows:Value>
        <ows:Value>{MDB}</ows:Value>
      </ows:Parameter>
      <ows:Parameter name="typeNames"><ows:Value>csw:Record</ows:Value></ows:Parameter>
      <ows:Constraint name="SupportedISOQueryables"><ows:Value>AnyText</ows:Value></ows:Constraint>
      <ows:Constraint name="SupportedCommonQueryables"><ows:Value>AnyText</ows:Value></ows:Constraint>
    </ows:Operation>
    <ows:Operation name="GetRecordById">
      <ows:DCP><ows:HTTP><ows:Get xlink:href="{base}?"/></ows:HTTP></ows:DCP>
      <ows:Parameter name="outputSchema">
        <ows:Value>{CSW}</ows:Value>
        <ows:Value>{GMD}</ows:Value>
        <ows:Value>{MDB}</ows:Value>
      </ows:Parameter>
    </ows:Operation>
  </ows:OperationsMetadata>
  <ogc:Filter_Capabilities>
    <ogc:Scalar_Capabilities>
      <ogc:ComparisonOperators>
        <ogc:ComparisonOperator>PropertyIsLike</ogc:ComparisonOperator>
      </ogc:ComparisonOperators>
    </ogc:Scalar_Capabilities>
  </ogc:Filter_Capabilities>
</csw:Capabilities>""".encode("utf-8")


def _dc(pai, tag: str, ns: str, texto) -> None:
    if texto in (None, ""):
        return
    el = etree.SubElement(pai, f"{{{ns}}}{tag}")
    el.text = str(texto)


def registro_dc(item: dict, base_api: str) -> etree._Element:
    """`csw:Record` (Dublin Core simples) a partir de um item já serializado por `comum.item_json`/
    `carregar_varios` — o mesmo dado que `/ogc/records` expõe, só que no vocabulário CSW."""
    rec = etree.Element(f"{{{CSW}}}Record", nsmap=NS_RECORDS)
    iid = str(item["id"])
    _dc(rec, "identifier", DC, iid)
    _dc(rec, "title", DC, item.get("titulo"))
    _dc(rec, "type", DC, item.get("tipo"))
    for tg in item.get("tags") or []:
        _dc(rec, "subject", DC, tg)
    _dc(rec, "abstract", DCT, item.get("resumo") or item.get("descricao"))
    _dc(rec, "creator", DC, item.get("creditos"))
    _dc(rec, "format", DC, "application/json")
    criado = item.get("criado_em")
    _dc(rec, "date", DC, (criado.isoformat() if hasattr(criado, "isoformat") else criado))
    _dc(rec, "relation", DCT, f"{base_api}/api/itens/{iid}/metadado.xml")
    extent = item.get("extent")
    if extent:
        xmin, ymin, xmax, ymax = extent
        bbox = etree.SubElement(rec, f"{{{OWS}}}BoundingBox")
        bbox.set("crs", "urn:ogc:def:crs:EPSG::4326")
        lc = etree.SubElement(bbox, f"{{{OWS}}}LowerCorner")
        lc.text = f"{xmin} {ymin}"
        uc = etree.SubElement(bbox, f"{{{OWS}}}UpperCorner")
        uc.text = f"{xmax} {ymax}"
    return rec


def _linhas_brutas(cur, ids: list[str]) -> dict[str, dict]:
    """As mesmas linhas cruas que `GET /api/itens/{id}/metadado.xml` usa (`comum.SQL_ITEM`) para os `ids` já
    filtrados por `listar_ids` — nunca uma segunda consulta com filtro próprio (a RLS já decidiu quem aparece)."""
    if not ids:
        return {}
    cur.execute(comum.SQL_ITEM + " WHERE i.id = ANY (%s::uuid[])", (ids,))
    return {str(r["id"]): r for r in cur.fetchall()}


def get_records_response(
    cur, auth, base_url: str, p: dict, start_position: int, output_schema: str, tenant_nome: str
) -> bytes:
    from app.catalogo.rotas_itens import carregar_varios, listar_ids

    perfil = _perfil_iso(output_schema)
    iso = perfil is not None
    total, ids, _proximo, _aprox = listar_ids(cur, auth, p)
    base_api = base_url.rstrip("/")
    nsmap = dict(NS_ISO_19115_3 if perfil == "19115-3" else (NS_ISO if iso else NS_RECORDS))
    root = etree.Element(f"{{{CSW}}}GetRecordsResponse", nsmap=nsmap)
    root.set("version", "2.0.2")
    etree.SubElement(root, f"{{{CSW}}}SearchStatus").set("timestamp", _agora())
    resultados = etree.SubElement(root, f"{{{CSW}}}SearchResults")
    esquema = MDB if perfil == "19115-3" else (GMD if iso else "http://www.opengis.net/cat/csw/2.0.2#Record")
    resultados.set("recordSchema", esquema)
    resultados.set("elementSet", "full")
    resultados.set("numberOfRecordsMatched", str(total))
    if iso:
        montar = metadado.montar_md_metadata_19115_3 if perfil == "19115-3" else metadado.montar_md_metadata
        brutas = _linhas_brutas(cur, ids)
        registros = [montar(brutas[i], tenant_nome, base_api) for i in ids if i in brutas]
    else:
        registros = [registro_dc(item, base_api) for item in carregar_varios(cur, ids, auth)]
    for el in registros:
        resultados.append(el)
    resultados.set("numberOfRecordsReturned", str(len(registros)))
    proxima = start_position + len(registros)
    resultados.set("nextRecord", str(proxima if proxima <= total else 0))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def get_record_by_id_response(row: dict, auth, base_url: str, output_schema: str, tenant_nome: str) -> bytes:
    """`row` já é o resultado de `comum.item_ou_404` (404 + RLS resolvidos por quem chama, mesmo padrão da
    rota `metadado_iso`)."""
    base_api = base_url.rstrip("/")
    perfil = _perfil_iso(output_schema)
    root_tag = f"{{{CSW}}}GetRecordByIdResponse"
    if perfil:
        nsmap = NS_ISO_19115_3 if perfil == "19115-3" else NS_ISO
        montar = metadado.montar_md_metadata_19115_3 if perfil == "19115-3" else metadado.montar_md_metadata
        validar = metadado.validar_19115_3 if perfil == "19115-3" else metadado.validar
        root = etree.Element(root_tag, nsmap=nsmap)
        md = montar(row, tenant_nome, base_api)
        try:
            validar(etree.tostring(md))  # mesma validação de GET .../metadado.xml, XSD cacheado
        except metadado.ErroXSDAusente as e:
            raise ErroAPI(503, "indisponivel", "cache do XSD ISO ausente nesta máquina") from e
        except metadado.ErroMetadadoInvalido as e:
            raise ErroAPI(500, "metadado_invalido", "metadado gerado não validou contra o XSD", e.erros) from e
        root.append(md)
    else:
        root = etree.Element(root_tag, nsmap=NS_RECORDS)
        item = comum.item_json(row, auth, completo=True)
        root.append(registro_dc(item, base_api))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
