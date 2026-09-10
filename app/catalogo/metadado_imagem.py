"""Exportação ISO 19115-2 (perfil de imagem) de um item raster com ficha (item L1-27).

ISO 19115-2 é, na codificação 19139, o namespace `gmi` (http://www.isotc211.org/2005/gmi): `gmi:MI_Metadata`
é uma EXTENSÃO de `gmd:MD_Metadata` que só acrescenta `acquisitionInformation` ao final da sequência, e traz
`gmi:MI_ImageDescription` (nuvem, ângulos do sol) e `gmi:MI_Platform`/`gmi:MI_Instrument`. Por isso este
módulo NÃO reescreve o gerador do L0-09: chama `metadado.montar_md_metadata`, troca a raiz por
`gmi:MI_Metadata` e insere os blocos de imagem nas posições que a sequência do XSD exige. O XML resultante
é validado contra o XSD `gmi.xsd` cacheado offline em `docs/xsd/cache/` (docs/xsd/baixar_iso19139.py).

A licença, a data de aquisição, a plataforma, o instrumento e a atribuição vêm da MESMA ficha que alimenta
as propriedades STAC (`app.imagens.ficha`): o XML e o item STAC não podem divergir porque não há segunda
cópia do dado — os dois são projeções de `plat.item.dados['ficha']`.
"""

from __future__ import annotations

import datetime
import functools
from pathlib import Path

from lxml import etree

from app.catalogo import metadado
from app.catalogo.metadado import GCO, GMD, XSI, ErroMetadadoInvalido, ErroXSDAusente, _codigo, _e, _texto
from app.imagens import ficha as fi

GMI = "http://www.isotc211.org/2005/gmi"
NSMAP = {"gmd": GMD, "gco": GCO, "gmi": GMI, "xsi": XSI}
XSD_ENTRADA = (
    Path(__file__).resolve().parents[2] / "docs" / "xsd" / "cache" / "www.isotc211.org" / "2005" / "gmi" / "gmi.xsd"
)

# ordem da sequência de gmd:MD_DataIdentification_Type (ISO 19139): quem entra depois tem de entrar ANTES
# do primeiro elemento desta lista que já exista no documento.
_DEPOIS_DE_IDENT = {
    "resourceConstraints": ("aggregationInfo", "spatialRepresentationType", "spatialResolution", "language",
                            "characterSet", "topicCategory", "environmentDescription", "extent",
                            "supplementalInformation"),
    "spatialResolution": ("language", "characterSet", "topicCategory", "environmentDescription", "extent",
                          "supplementalInformation"),
}


def _inserir_ordenado(pai: etree._Element, elemento: etree._Element, sucessores: tuple[str, ...]) -> None:
    """Insere `elemento` antes do primeiro sucessor presente; sem sucessor presente, ao final."""
    nomes = [f"{{{GMD}}}{n}" for n in sucessores]
    for i, filho in enumerate(pai):
        if filho.tag in nomes:
            pai.insert(i, elemento)
            return
    pai.append(elemento)


def _distancia(pai, valor: float, uom: str) -> None:
    res = etree.SubElement(pai, f"{{{GMD}}}spatialResolution")
    md_res = _e(res, "MD_Resolution")
    dist = _e(md_res, "distance")
    d = etree.SubElement(dist, f"{{{GCO}}}Distance")
    d.set("uom", uom)
    d.text = repr(float(valor))


def _restricoes_de_licenca(ident: etree._Element, f: fi.Ficha) -> None:
    lic = fi.POR_CODIGO[f.licenca]
    rc = etree.Element(f"{{{GMD}}}resourceConstraints")
    legal = _e(rc, "MD_LegalConstraints")
    _codigo(legal, "useConstraints", "MD_RestrictionCode", "licence" if lic.stac != "other" else "otherRestrictions")
    partes = [f"licença: {lic.rotulo}", f"identificador: {lic.stac}", f"código da casa: {lic.codigo}"]
    if lic.url:
        partes.append(f"texto da licença: {lic.url}")
    partes.append(f"redistribuição: {lic.redistribuicao}")
    if f.atribuicao:
        partes.append(f"atribuição obrigatória: {f.atribuicao}")
    if not lic.vendavel:
        partes.append("item auditável, não vendável (regra D17 da casa)")
    _texto(legal, "otherConstraints", "; ".join(partes))
    _inserir_ordenado(ident, rc, _DEPOIS_DE_IDENT["resourceConstraints"])


def _conteudo_de_imagem(md: etree._Element, f: fi.Ficha) -> None:
    """gmd:contentInfo/gmi:MI_ImageDescription — nuvem e ângulos do sol; vai antes de distributionInfo."""
    ci = etree.Element(f"{{{GMD}}}contentInfo")
    img = etree.SubElement(ci, f"{{{GMI}}}MI_ImageDescription")
    # attributeDescription é gco:RecordType (não CharacterString): o gerador genérico do L0-09 não serve aqui
    ad = _e(img, "attributeDescription")
    rt = etree.SubElement(ad, f"{{{GCO}}}RecordType")
    rt.text = f"bandas do sensor {', '.join(f.instrumentos)}"
    _codigo(img, "contentType", "MD_CoverageContentTypeCode", "image")
    if f.sol_elevacao is not None:
        el = _e(img, "illuminationElevationAngle")
        r = etree.SubElement(el, f"{{{GCO}}}Real")
        r.text = repr(f.sol_elevacao)
    if f.sol_azimute is not None:
        el = _e(img, "illuminationAzimuthAngle")
        r = etree.SubElement(el, f"{{{GCO}}}Real")
        r.text = repr(f.sol_azimute)
    if f.nuvem_pct is not None:
        el = _e(img, "cloudCoverPercentage")
        r = etree.SubElement(el, f"{{{GCO}}}Real")
        r.text = repr(f.nuvem_pct)
    _inserir_ordenado(md, ci, ("distributionInfo", "dataQualityInfo", "portrayalCatalogueInfo",
                               "metadataConstraints", "applicationSchemaInfo", "metadataMaintenance",
                               "series", "describes", "propertyType", "featureType", "featureAttribute"))


def _aquisicao(md: etree._Element, f: fi.Ficha) -> None:
    """gmi:acquisitionInformation — plataforma, instrumentos e a operação com a data de aquisição."""
    aq = etree.SubElement(md, f"{{{GMI}}}acquisitionInformation")
    info = etree.SubElement(aq, f"{{{GMI}}}MI_AcquisitionInformation")
    for nome in f.instrumentos:
        instr_prop = etree.SubElement(info, f"{{{GMI}}}instrument")
        instr = etree.SubElement(instr_prop, f"{{{GMI}}}MI_Instrument")
        ident = etree.SubElement(instr, f"{{{GMI}}}identifier")
        md_ident = _e(ident, "MD_Identifier")
        _texto(md_ident, "code", nome)
        tipo = etree.SubElement(instr, f"{{{GMI}}}type")
        cs = etree.SubElement(tipo, f"{{{GCO}}}CharacterString")
        cs.text = f.constelacao or f.plataforma
    plat_prop = etree.SubElement(info, f"{{{GMI}}}platform")
    plat = etree.SubElement(plat_prop, f"{{{GMI}}}MI_Platform")
    p_ident = etree.SubElement(plat, f"{{{GMI}}}identifier")
    p_md = _e(p_ident, "MD_Identifier")
    _texto(p_md, "code", f.plataforma)
    p_desc = etree.SubElement(plat, f"{{{GMI}}}description")
    p_cs = etree.SubElement(p_desc, f"{{{GCO}}}CharacterString")
    descricao = [f"fornecedor: {f.fornecedor}", f"origem do dado: {f.fonte}"]
    if f.orbita_estado:
        descricao.append(f"órbita: {f.orbita_estado}")
    if f.orbita_relativa is not None:
        descricao.append(f"órbita relativa: {f.orbita_relativa}")
    p_cs.text = "; ".join(descricao)
    for nome in f.instrumentos:
        p_instr = etree.SubElement(plat, f"{{{GMI}}}instrument")
        i2 = etree.SubElement(p_instr, f"{{{GMI}}}MI_Instrument")
        i2_ident = etree.SubElement(i2, f"{{{GMI}}}identifier")
        i2_md = _e(i2_ident, "MD_Identifier")
        _texto(i2_md, "code", nome)
        i2_tipo = etree.SubElement(i2, f"{{{GMI}}}type")
        i2_cs = etree.SubElement(i2_tipo, f"{{{GCO}}}CharacterString")
        i2_cs.text = f.constelacao or f.plataforma


def _data_de_aquisicao(md: etree._Element, f: fi.Ficha) -> None:
    """A data de aquisição entra na citação do recurso como `CI_DateTypeCode` 'creation' já existente? Não:
    a criação do item na plataforma não é a aquisição da imagem. Ela entra como uma data adicional da
    citação, com tipo 'creation' do RECURSO, e como extensão temporal do dado."""
    ident = md.find(f"{{{GMD}}}identificationInfo/{{{GMD}}}MD_DataIdentification")
    if ident is None:
        return
    citacao = ident.find(f"{{{GMD}}}citation/{{{GMD}}}CI_Citation")
    if citacao is not None:
        alvo = citacao.find(f"{{{GMD}}}identifier")
        el = etree.Element(f"{{{GMD}}}date")
        ci = _e(el, "CI_Date")
        d = _e(ci, "date")
        dt = etree.SubElement(d, f"{{{GCO}}}DateTime")
        dt.text = f.data_aquisicao.replace("Z", "")
        _codigo(ci, "dateType", "CI_DateTypeCode", "creation")
        if alvo is not None:
            citacao.insert(list(citacao).index(alvo), el)
        else:
            citacao.append(el)


def montar_mi_metadata(row: dict, f: fi.Ficha, tenant_nome: str, base_url: str) -> etree._Element:
    md = metadado.montar_md_metadata(row, tenant_nome, base_url)
    novo = etree.Element(f"{{{GMI}}}MI_Metadata", nsmap=NSMAP)
    novo.set(
        f"{{{XSI}}}schemaLocation",
        f"{GMI} https://www.isotc211.org/2005/gmi/gmi.xsd "
        f"{GMD} https://schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd",
    )
    for filho in list(md):
        novo.append(filho)
    # o padrão declarado deixa de ser só 19139: quem lê o XML tem de saber que há blocos de 19115-2
    for el in novo.findall(f"{{{GMD}}}metadataStandardName"):
        el.find(f"{{{GCO}}}CharacterString").text = "ISO 19115-2:2009/19139-2 (perfil de imagem)"
    ident = novo.find(f"{{{GMD}}}identificationInfo/{{{GMD}}}MD_DataIdentification")
    if ident is not None:
        _restricoes_de_licenca(ident, f)
        aux = etree.Element("aux")
        _distancia(aux, f.gsd, "m")
        _inserir_ordenado(ident, aux[0], _DEPOIS_DE_IDENT["spatialResolution"])
    _data_de_aquisicao(novo, f)
    _conteudo_de_imagem(novo, f)
    _aquisicao(novo, f)
    return novo


def gerar_xml(row: dict, f: fi.Ficha, tenant_nome: str, base_url: str) -> bytes:
    return etree.tostring(
        montar_mi_metadata(row, f, tenant_nome, base_url),
        xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


@functools.lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    if not XSD_ENTRADA.exists():
        raise ErroXSDAusente(f"{XSD_ENTRADA} ausente; rode: venv/bin/python docs/xsd/baixar_iso19139.py")
    return etree.XMLSchema(etree.parse(str(XSD_ENTRADA)))


def validar(xml_bytes: bytes) -> None:
    """Levanta ErroMetadadoInvalido se o XML não validar contra o XSD ISO 19115-2 (gmi) cacheado."""
    doc = etree.fromstring(xml_bytes)
    schema = _schema()
    if not schema.validate(doc):
        raise ErroMetadadoInvalido(schema.error_log)


def licenca_e_data_do_xml(xml_bytes: bytes) -> tuple[str | None, str | None, str | None]:
    """Lê de volta do XML (identificador STAC/SPDX da licença, código da casa, data de aquisição) — é o que a
    refutação do item confere contra o item STAC (`app.imagens.ficha.para_stac`). O código da casa vai junto
    porque `other` é o identificador STAC de mais de uma licença da tabela e sozinho não distingue."""
    doc = etree.fromstring(xml_bytes)
    restricao = doc.find(
        f"{{{GMD}}}identificationInfo/{{{GMD}}}MD_DataIdentification/{{{GMD}}}resourceConstraints/"
        f"{{{GMD}}}MD_LegalConstraints/{{{GMD}}}otherConstraints/{{{GCO}}}CharacterString"
    )
    identificador = codigo_casa = None
    if restricao is not None and restricao.text:
        for parte in restricao.text.split("; "):
            if parte.startswith("identificador: "):
                identificador = parte[len("identificador: "):]
            elif parte.startswith("código da casa: "):
                codigo_casa = parte[len("código da casa: "):]
    data = None
    for ci in doc.iterfind(
        f"{{{GMD}}}identificationInfo/{{{GMD}}}MD_DataIdentification/{{{GMD}}}citation/{{{GMD}}}CI_Citation/"
        f"{{{GMD}}}date/{{{GMD}}}CI_Date"
    ):
        dt = ci.find(f"{{{GMD}}}date/{{{GCO}}}DateTime")
        if dt is not None and dt.text:
            data = datetime.datetime.fromisoformat(dt.text).replace(
                tzinfo=datetime.UTC
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
    return identificador, codigo_casa, data
