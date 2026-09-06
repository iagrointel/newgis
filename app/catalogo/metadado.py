"""Exportação de metadado ISO 19139 (GMD) por item (item L0-09-metadado-catalogo; ADR 0004 D17 do L0_CONCEITO).

Gera `gmd:MD_Metadata` a partir da linha crua de `comum.carregar`/`comum.SQL_ITEM` (não de `item_json`: aqui
importam xmin/ymin/xmax/ymax, dono_nome e o `dados` bruto, que `item_json` já transforma). Valida contra o XSD
oficial ISO 19139 (perfil `schemas.opengis.net/iso/19139/20070417`, o mesmo que GeoNetwork/INDE chamam de
"iso19139"), cacheado OFFLINE em `docs/xsd/cache/` por `docs/xsd/baixar_iso19139.py` — nunca em tempo de
requisição (P5: reprodutível, sem dependência de rede na rota).

Decisões (a ADR completa de L0-09 fica pendente de um turno próprio; isto documenta só o que este módulo faz):
- Perfil: ISO 19139/gmd, não 19115-3/mdb — é o que o Perfil MGB 2.0 e o GeoNetwork da INDE consomem
  (metadados.inde.gov.br/geonetwork/, harvest por CSW), então exportar no formato que o catálogo de destino
  real já lê é o que tem valor imediato; 19115-3 fica registrado como pendência (docs/PARIDADE.md).
- `topicCategory` fica de fora nesta passagem: a lista fechada da ISO (19 valores, ex. "farming",
  "geoscientificInformation") não tem uma tradução única e correta a partir de `tipo`/`familia` da plataforma
  sem inventar — melhor omitir (o elemento é `minOccurs="0"`) do que digitar um valor sem base.
- `dataQualityInfo`/lineage só aparece quando `dados.procedencia` existe no item (D17: "procedência errada é
  pior que nenhuma" — sem bloco de procedência, sem lineage, não um texto genérico).
- `dono_id` vira `pointOfContact` com `role="owner"`; o inquilino (`tenant_nome`) vira o `contact` do
  `MD_Metadata` (o "quem responde por este catálogo"), com `role="pointOfContact"`, refletindo D17."""

import datetime
import functools
from pathlib import Path

from lxml import etree

GMD = "http://www.isotc211.org/2005/gmd"
GCO = "http://www.isotc211.org/2005/gco"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP = {"gmd": GMD, "gco": GCO, "xsi": XSI}
CODELIST_BASE = "http://www.isotc211.org/2005/resources/Codelist/gmxCodelists.xml"
XSD_ENTRADA = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "xsd"
    / "cache"
    / "schemas.opengis.net"
    / "iso"
    / "19139"
    / "20070417"
    / "gmd"
    / "gmd.xsd"
)

MD_PROGRESSO = {"autoritativo": "completed", "obsoleto": "obsolete"}


class ErroXSDAusente(RuntimeError):
    """docs/xsd/baixar_iso19139.py ainda não rodou nesta máquina."""


class ErroMetadadoInvalido(ValueError):
    def __init__(self, log):
        self.erros = [str(e) for e in log]
        super().__init__("; ".join(self.erros) or "metadado ISO 19139 inválido")


def _e(pai, tag: str, ns: str = GMD):
    return etree.SubElement(pai, f"{{{ns}}}{tag}")


def _texto(pai, tag: str, valor: str, ns: str = GMD):
    """<gmd:tag><gco:CharacterString>valor</gco:CharacterString></gmd:tag>"""
    el = _e(pai, tag, ns)
    cs = _e(el, "CharacterString", GCO)
    cs.text = valor
    return el


def _codigo(pai, tag: str, elemento: str, valor: str, rotulo: str | None = None):
    """<gmd:tag><gmd:Elemento codeList="..." codeListValue="valor">rotulo</gmd:Elemento></gmd:tag>"""
    el = _e(pai, tag)
    c = _e(el, elemento)
    c.set("codeList", f"{CODELIST_BASE}#{elemento}")
    c.set("codeListValue", valor)
    c.text = rotulo or valor
    return el


def _data_simples(pai, tag: str, data: datetime.date):
    el = _e(pai, tag)
    d = _e(el, "Date", GCO)
    d.text = data.isoformat()
    return el


def _ci_date(pai, data: datetime.date, tipo: str):
    ci = _e(pai, "date")
    ci_date = _e(ci, "CI_Date")
    _data_simples(ci_date, "date", data)
    _codigo(ci_date, "dateType", "CI_DateTypeCode", tipo)
    return ci


def _ci_citation(pai, tag: str, titulo: str, datas: list[tuple[datetime.date, str]], identificador: str | None = None):
    el = _e(pai, tag)
    cit = _e(el, "CI_Citation")
    _texto(cit, "title", titulo)
    for data, tipo in datas:
        _ci_date(cit, data, tipo)
    if identificador:
        ident = _e(cit, "identifier")
        md_id = _e(ident, "MD_Identifier")
        _texto(md_id, "code", identificador)
    return el


def _ci_responsible_party(
    pai, tag: str, papel: str, nome_individual: str | None = None, organizacao: str | None = None
):
    el = _e(pai, tag)
    crp = _e(el, "CI_ResponsibleParty")
    if nome_individual:
        _texto(crp, "individualName", nome_individual)
    if organizacao:
        _texto(crp, "organisationName", organizacao)
    _codigo(crp, "role", "CI_RoleCode", papel)
    return el


def _online_resource(pai, tag: str, url: str, nome: str, descricao: str | None = None):
    el = _e(pai, tag)
    onl = _e(el, "CI_OnlineResource")
    linkage = _e(onl, "linkage")
    u = _e(linkage, "URL")
    u.text = url
    _texto(onl, "name", nome)
    if descricao:
        _texto(onl, "description", descricao)
    return el


def montar_md_metadata(row: dict, tenant_nome: str, base_url: str) -> etree._Element:
    """`row` é a linha crua de `comum.carregar()`/`comum.SQL_ITEM` (com xmin/ymin/xmax/ymax e dono_nome)."""
    item_id = str(row["id"])
    md = etree.Element(f"{{{GMD}}}MD_Metadata", nsmap=NSMAP)
    md.set(
        f"{{{XSI}}}schemaLocation",
        f"{GMD} https://schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd",
    )

    _texto(md, "fileIdentifier", item_id)
    _codigo(md, "language", "LanguageCode", "por")
    _codigo(md, "characterSet", "MD_CharacterSetCode", "utf8")
    _codigo(md, "hierarchyLevel", "MD_ScopeCode", "dataset")

    _ci_responsible_party(md, "contact", "pointOfContact", organizacao=tenant_nome)

    modificado = row["modificado_em"]
    criado = row["criado_em"]
    modificado_data = modificado.date() if hasattr(modificado, "date") else modificado
    criado_data = criado.date() if hasattr(criado, "date") else criado
    _data_simples(md, "dateStamp", modificado_data)
    _texto(md, "metadataStandardName", "ISO 19115:2003/19139")
    _texto(md, "metadataStandardVersion", "1.0")

    ref = _e(md, "referenceSystemInfo")
    md_rs = _e(ref, "MD_ReferenceSystem")
    rs_id_prop = _e(md_rs, "referenceSystemIdentifier")
    rs_id = _e(rs_id_prop, "RS_Identifier")
    _texto(rs_id, "code", "4326")
    _texto(rs_id, "codeSpace", "EPSG")

    ident_prop = _e(md, "identificationInfo")
    ident = _e(ident_prop, "MD_DataIdentification")
    titulo = row["titulo"]
    _ci_citation(ident, "citation", titulo, [(criado_data, "creation"), (modificado_data, "revision")], item_id)
    resumo = row.get("resumo") or row.get("descricao") or titulo
    _texto(ident, "abstract", resumo)
    if row.get("creditos"):
        _texto(ident, "credit", row["creditos"])
    progresso = MD_PROGRESSO.get(row.get("status"))
    if progresso:
        _codigo(ident, "status", "MD_ProgressCode", progresso)
    dono_nome = row.get("dono_nome")
    if dono_nome:
        _ci_responsible_party(ident, "pointOfContact", "owner", nome_individual=dono_nome)
    if row.get("miniatura_chave"):
        graf = _e(ident, "graphicOverview")
        browse = _e(graf, "MD_BrowseGraphic")
        _texto(browse, "fileName", f"{base_url}/api/itens/{item_id}/miniatura")
    tags = row.get("tags") or []
    if tags:
        kw_prop = _e(ident, "descriptiveKeywords")
        kw = _e(kw_prop, "MD_Keywords")
        for t in tags:
            _texto(kw, "keyword", t)
        _codigo(kw, "type", "MD_KeywordTypeCode", "theme")
    if row.get("termos_de_uso"):
        rc_prop = _e(ident, "resourceConstraints")
        legal = _e(rc_prop, "MD_LegalConstraints")
        _texto(legal, "useLimitation", row["termos_de_uso"])
    _texto(ident, "language", "por")
    xmin, ymin, xmax, ymax = row.get("xmin"), row.get("ymin"), row.get("xmax"), row.get("ymax")
    if xmin is not None:
        ext_prop = _e(ident, "extent")
        ext = _e(ext_prop, "EX_Extent")
        geo_prop = _e(ext, "geographicElement")
        bbox = _e(geo_prop, "EX_GeographicBoundingBox")
        for tag, valor in (
            ("westBoundLongitude", xmin),
            ("eastBoundLongitude", xmax),
            ("southBoundLatitude", ymin),
            ("northBoundLatitude", ymax),
        ):
            el = _e(bbox, tag)
            dec = _e(el, "Decimal", GCO)
            dec.text = repr(float(valor))

    dist_prop = _e(md, "distributionInfo")
    dist = _e(dist_prop, "MD_Distribution")
    transfer_prop = _e(dist, "transferOptions")
    transfer = _e(transfer_prop, "MD_DigitalTransferOptions")
    _online_resource(transfer, "onLine", f"{base_url}/api/itens/{item_id}", titulo, "item na plataforma (JSON)")
    _online_resource(
        transfer,
        "onLine",
        f"{base_url}/api/itens/{item_id}/metadado.xml",
        f"{titulo} (metadado ISO 19139)",
    )

    dados = row.get("dados") or {}
    procedencia = dados.get("procedencia") if isinstance(dados, dict) else None
    if procedencia:
        dq_prop = _e(md, "dataQualityInfo")
        dq = _e(dq_prop, "DQ_DataQuality")
        scope = _e(dq, "scope")
        dq_scope = _e(scope, "DQ_Scope")
        _codigo(dq_scope, "level", "MD_ScopeCode", "dataset")
        lineage_prop = _e(dq, "lineage")
        lineage = _e(lineage_prop, "LI_Lineage")
        partes = []
        for chave, rotulo in (
            ("fonte", "fonte"),
            ("url", "endereço"),
            ("licenca", "licença"),
            ("data_do_dado", "data do dado"),
            ("data_de_acesso", "data de acesso"),
            ("metodo", "método"),
            ("confianca", "confiança"),
            ("frescor", "frescor"),
        ):
            v = procedencia.get(chave)
            if v:
                partes.append(f"{rotulo}: {v}")
        if partes:
            _texto(lineage, "statement", "; ".join(partes))

    return md


def gerar_xml(row: dict, tenant_nome: str, base_url: str) -> bytes:
    md = montar_md_metadata(row, tenant_nome, base_url)
    return etree.tostring(md, xml_declaration=True, encoding="UTF-8", pretty_print=True)


@functools.lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    if not XSD_ENTRADA.exists():
        raise ErroXSDAusente(
            f"{XSD_ENTRADA} ausente; rode: venv/bin/python docs/xsd/baixar_iso19139.py"
        )
    return etree.XMLSchema(etree.parse(str(XSD_ENTRADA)))


def validar(xml_bytes: bytes) -> None:
    """Levanta ErroMetadadoInvalido se o XML não validar contra o XSD ISO 19139 cacheado."""
    doc = etree.fromstring(xml_bytes)
    schema = _schema()
    if not schema.validate(doc):
        raise ErroMetadadoInvalido(schema.error_log)
