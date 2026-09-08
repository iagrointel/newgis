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

import dataclasses
import datetime
import functools
from pathlib import Path

from lxml import etree

from app import limites

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
MD_PROGRESSO_INVERSO = {v: k for k, v in MD_PROGRESSO.items()}
# listas de códigos da ISO 19115 (gmxCodelists.xml) usadas na LEITURA: valor fora da lista não entra no jsonb —
# vai para o relatório do que não coube, porque gravar código inválido é pior que não gravar (D17).
CI_ROLE_CODE = (
    "resourceProvider", "custodian", "owner", "user", "distributor", "originator",
    "pointOfContact", "principalInvestigator", "processor", "publisher", "author",
)
MD_MAINTENANCE_FREQUENCY_CODE = (
    "continual", "daily", "weekly", "fortnightly", "monthly", "quarterly", "biannually",
    "annually", "asNeeded", "irregular", "notPlanned", "unknown",
)
# vocabulário de `dados.procedencia` (item L0-09-a) e o rótulo com que ele entra e sai do `LI_Lineage/statement`:
# a MESMA tabela serve à exportação e à importação, para que a ida e volta feche sem uma segunda lista.
PROCEDENCIA_ROTULOS = (
    ("fonte", "fonte"),
    ("url", "endereço"),
    ("licenca", "licença"),
    ("data_do_dado", "data do dado"),
    ("data_de_acesso", "data de acesso"),
    ("metodo", "método"),
    ("confianca", "confiança"),
    ("frescor", "frescor"),
)
PROCEDENCIA_POR_ROTULO = {rotulo: chave for chave, rotulo in PROCEDENCIA_ROTULOS}


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
        for chave, rotulo in PROCEDENCIA_ROTULOS:
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


# ------------------------------------------------------------------ importação (item L0-09-c-xml-iso-validacao)
# O analisador é o MESMO módulo da exportação de propósito: a tabela de rótulos de procedência, o mapa de
# `MD_ProgressCode` e o XSD em cache são únicos, e é isso que faz a ida e volta (exportar → importar) fechar sem
# perda. Três decisões que a leitura de metadado real impôs (medidas no registro aberto da INDE deste item):
#
# 1. XSD é PARECER, não porteiro. O registro real da INDE não valida contra o XSD oficial do ISO/TC 211 (ordem
#    de elementos e extensões do Perfil MGB); recusar o que o catálogo nacional publica seria recusar o dado
#    aberto do país. Então: XML malformado ou com raiz errada = 422 com linha e coluna; XML bem formado que não
#    valida = importa e devolve os erros do XSD com linha/coluna em `avisos_xsd` — e `?estrito=1` transforma
#    esses mesmos avisos em 422, para quem quer o rigor.
# 2. Entidade externa nunca é resolvida (`resolve_entities=False`, `no_network=True`, sem DTD): o corpo é
#    documento de terceiro por definição.
# 3. O que não tem onde ser guardado NÃO é inventado: vira relatório (`nao_coube`), com caminho, quantas vezes
#    apareceu, um exemplo e a linha do XML. Guardar contato/manutenção/formato é o item L0-09-b (coluna
#    `plat.item.metadado_iso`), que ainda não entrou em master — enquanto não entra, esses campos saem no
#    relatório em vez de irem para um armazém improvisado.

PARSER_SEGURO = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
)
NS = {"gmd": GMD, "gco": GCO}
RAIZ_ESPERADA = f"{{{GMD}}}MD_Metadata"


class ErroXMLIlegivel(ValueError):
    """XML malformado, grande demais ou com raiz que não é gmd:MD_Metadata: erro do PEDIDO (422), com posição."""

    def __init__(self, mensagem: str, linha: int = 0, coluna: int = 0):
        self.mensagem, self.linha, self.coluna = mensagem, int(linha or 0), int(coluna or 0)
        super().__init__(f"{mensagem} (linha {self.linha}, coluna {self.coluna})")


@dataclasses.dataclass
class Analise:
    """Resultado da leitura de um XML ISO 19139: o que vai para o item, o que vai para `dados.procedencia`,
    o que não coube em lugar nenhum e o que o XSD achou."""

    campos: dict = dataclasses.field(default_factory=dict)
    procedencia: dict = dataclasses.field(default_factory=dict)
    metadado_iso: dict = dataclasses.field(default_factory=dict)
    identificador_arquivo: str | None = None
    nao_coube: list = dataclasses.field(default_factory=list)
    avisos_xsd: list = dataclasses.field(default_factory=list)

    @property
    def preenchidos(self) -> list[str]:
        """Nome pontilhado de cada campo que a leitura preencheu — é o que a cláusula '≥ 15 campos' conta.
        Folha é o que tem valor final: `contato.email` conta um; `contato` não conta."""
        nomes = sorted(self.campos) + sorted(f"procedencia.{k}" for k in self.procedencia)
        for grupo, valor in sorted(self.metadado_iso.items()):
            nomes.extend(_folhas(f"metadado_iso.{grupo}", valor))
        return nomes


def _folhas(prefixo: str, valor) -> list[str]:
    if isinstance(valor, dict):
        saida = []
        for chave, v in sorted(valor.items()):
            saida.extend(_folhas(f"{prefixo}.{chave}", v))
        return saida
    return [prefixo]


def ler_documento(dados: bytes) -> etree._Element:
    if len(dados) > limites.METADADO_XML_BYTES_MAX:
        raise ErroXMLIlegivel(
            f"XML acima do teto de {limites.METADADO_XML_BYTES_MAX} bytes ({len(dados)} enviados)"
        )
    try:
        doc = etree.fromstring(dados, parser=PARSER_SEGURO)
    except etree.XMLSyntaxError as e:
        linha, coluna = (e.position or (0, 0)) if hasattr(e, "position") else (0, 0)
        raise ErroXMLIlegivel(str(e).split(", line")[0], linha, coluna) from e
    if doc.tag != RAIZ_ESPERADA:
        raise ErroXMLIlegivel(
            f"raiz {doc.tag} não é {RAIZ_ESPERADA} (o corpo precisa ser um metadado ISO 19139/GMD)",
            doc.sourceline or 0,
        )
    return doc


def erros_xsd(doc: etree._Element) -> list[dict]:
    """[{linha, coluna, mensagem}] do XSD oficial em cache. Lista vazia = documento válido."""
    if _schema().validate(doc.getroottree()):
        return []
    return [
        {"linha": int(e.line or 0), "coluna": int(e.column or 0), "mensagem": e.message}
        for e in _schema().error_log
    ]


class _Leitor:
    """Percorre o documento marcando o que foi lido; o que sobra com texto vira o relatório do que não coube."""

    def __init__(self, doc: etree._Element):
        self.doc = doc
        self.lidos: set = set()

    def _marcar(self, el):
        self.lidos.add(el)
        return el

    def texto(self, pai, caminho: str) -> str | None:
        """Texto de um gco:CharacterString (ou gco:Date/DateTime/Decimal) sob `caminho`, marcando-o como lido."""
        if pai is None:
            return None
        for el in pai.iterfind(caminho, NS):
            for filho in el:
                if filho.tag in (
                    f"{{{GMD}}}URL",  # gmd:linkage guarda o endereço num gmd:URL, não num gco:CharacterString
                    f"{{{GCO}}}CharacterString",
                    f"{{{GCO}}}Date",
                    f"{{{GCO}}}DateTime",
                    f"{{{GCO}}}Decimal",
                    f"{{{GCO}}}Integer",
                    f"{{{GCO}}}Boolean",
                ):
                    v = (filho.text or "").strip()
                    if v:
                        self._marcar(filho)
                        return v
        return None

    def textos(self, pai, caminho: str) -> list[str]:
        saida = []
        if pai is None:
            return saida
        for el in pai.iterfind(caminho, NS):
            for filho in el:
                v = (filho.text or "").strip()
                if filho.tag == f"{{{GCO}}}CharacterString" and v:
                    self._marcar(filho)
                    saida.append(v)
        return saida

    def codigo(self, pai, caminho: str) -> str | None:
        """codeListValue de um elemento de lista de códigos (MD_ScopeCode, CI_RoleCode, ...)."""
        if pai is None:
            return None
        for el in pai.iterfind(caminho, NS):
            v = (el.get("codeListValue") or "").strip()
            if v:
                self._marcar(el)
                return v
            texto = (el.text or "").strip()
            if texto:
                self._marcar(el)
                return texto
        return None

    def acha(self, pai, caminho: str):
        return None if pai is None else pai.find(caminho, NS)

    def relatorio(self) -> list[dict]:
        """Elementos com valor que nenhuma regra leu, agrupados por caminho (nomes locais), na ordem do XML."""
        por_caminho: dict[str, dict] = {}
        for n, el in enumerate(self.doc.iter()):
            if n > limites.METADADO_XML_ELEMENTOS_MAX:
                break
            if not isinstance(el.tag, str) or el in self.lidos:
                continue
            valor = (el.text or "").strip() or (el.get("codeListValue") or "").strip()
            if not valor:
                continue
            partes = []
            no = el
            while no is not None and no is not self.doc:
                partes.append(etree.QName(no).localname)
                no = no.getparent()
            caminho = "/".join(reversed(partes))
            entrada = por_caminho.get(caminho)
            if entrada is None:
                if len(por_caminho) >= limites.METADADO_NAO_COUBE_MAX:
                    continue
                por_caminho[caminho] = {
                    "caminho": caminho,
                    "vezes": 1,
                    "exemplo": valor[:200],
                    "linha": int(el.sourceline or 0),
                }
            else:
                entrada["vezes"] += 1
        return list(por_caminho.values())


def _procedencia_do_statement(statement: str) -> dict:
    """`LI_Lineage/statement` de volta ao vocabulário de `dados.procedencia`. Só decompõe quando TODAS as partes
    do texto casam com os rótulos que a exportação escreve (ida e volta fechada); linhagem de terceiro, que é
    prosa livre, entra inteira como `metodo` — o que a plataforma sabe é que aquilo descreve como o dado foi
    feito, e inventar chave para prosa livre seria procedência errada (D17)."""
    partes = [p.strip() for p in statement.split(";") if p.strip()]
    saida = {}
    for parte in partes:
        rotulo, sep, valor = parte.partition(":")
        chave = PROCEDENCIA_POR_ROTULO.get(rotulo.strip())
        if not sep or chave is None or not valor.strip():
            return {"metodo": statement.strip()}
        saida[chave] = valor.strip()
    return saida or {"metodo": statement.strip()}


def analisar(dados: bytes) -> Analise:
    """XML ISO 19139 (bytes) → campos do item + `dados.procedencia` + relatório do que não coube + avisos do XSD."""
    doc = ler_documento(dados)
    lt = _Leitor(doc)
    a = Analise(avisos_xsd=erros_xsd(doc))

    ident = lt.acha(doc, "gmd:identificationInfo/gmd:MD_DataIdentification")
    if ident is None:  # serviço (SV_ServiceIdentification) ou perfil que troca o nome do bloco
        info = lt.acha(doc, "gmd:identificationInfo")
        ident = info[0] if info is not None and len(info) else None
    citacao = lt.acha(ident, "gmd:citation/gmd:CI_Citation")

    titulo = lt.texto(citacao, "gmd:title")
    if titulo:
        a.campos["titulo"] = titulo[: limites.ITEM_TITULO_MAX]
    resumo = lt.texto(ident, "gmd:abstract")
    if resumo:
        a.campos["resumo"] = resumo[: limites.ITEM_RESUMO_MAX]
    proposito = lt.texto(ident, "gmd:purpose")
    if proposito:
        a.campos["descricao"] = proposito[: limites.ITEM_DESCRICAO_MAX]
    creditos = lt.texto(ident, "gmd:credit")
    if creditos:
        a.campos["creditos"] = creditos[: limites.ITEM_CREDITOS_MAX]

    tags = []
    for kw in (ident.iterfind("gmd:descriptiveKeywords/gmd:MD_Keywords", NS) if ident is not None else ()):
        tags.extend(lt.textos(kw, "gmd:keyword"))
    vistas = set()
    tags = [t for t in tags if len(t) <= limites.TAG_MAX and not (t.lower() in vistas or vistas.add(t.lower()))]
    if tags:
        a.campos["tags"] = tags[: limites.ITEM_TAGS_MAX]

    usos = lt.textos(ident, "gmd:resourceConstraints/gmd:MD_LegalConstraints/gmd:useLimitation")
    usos += lt.textos(ident, "gmd:resourceConstraints/gmd:MD_Constraints/gmd:useLimitation")
    if usos:
        a.campos["termos_de_uso"] = "; ".join(usos)[: limites.ITEM_DESCRICAO_MAX]

    progresso = lt.codigo(ident, "gmd:status/gmd:MD_ProgressCode")
    if progresso in MD_PROGRESSO_INVERSO:
        a.campos["status"] = MD_PROGRESSO_INVERSO[progresso]

    bbox = lt.acha(ident, "gmd:extent/gmd:EX_Extent/gmd:geographicElement/gmd:EX_GeographicBoundingBox")
    if bbox is not None:
        cantos = [
            lt.texto(bbox, "gmd:westBoundLongitude"),
            lt.texto(bbox, "gmd:southBoundLatitude"),
            lt.texto(bbox, "gmd:eastBoundLongitude"),
            lt.texto(bbox, "gmd:northBoundLatitude"),
        ]
        if all(c is not None for c in cantos):
            try:
                a.campos["extent"] = [float(c) for c in cantos]
            except ValueError:
                pass  # canto ilegível: cai no relatório do que não coube, como qualquer outro valor não lido

    # ---- dados.procedencia (item L0-09-a): o bloco que a exportação escreve como linhagem, de volta
    linhagem = lt.texto(doc, "gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:lineage/gmd:LI_Lineage/gmd:statement")
    if linhagem:
        a.procedencia.update(_procedencia_do_statement(linhagem))
    if "fonte" not in a.procedencia:
        fonte = lt.texto(
            ident, "gmd:pointOfContact/gmd:CI_ResponsibleParty/gmd:organisationName"
        ) or lt.texto(doc, "gmd:contact/gmd:CI_ResponsibleParty/gmd:organisationName")
        if fonte:
            a.procedencia["fonte"] = fonte
    if "url" not in a.procedencia:
        recurso = lt.acha(
            doc,
            "gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/"
            "gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource",
        )
        url = lt.texto(recurso, "gmd:linkage")
        if url:
            a.procedencia["url"] = url
    if "licenca" not in a.procedencia:
        licenca = lt.textos(ident, "gmd:resourceConstraints/gmd:MD_LegalConstraints/gmd:otherConstraints")
        if licenca:
            a.procedencia["licenca"] = "; ".join(licenca)
    if "data_de_acesso" not in a.procedencia:
        carimbo = lt.texto(doc, "gmd:dateStamp")
        if carimbo:
            a.procedencia["data_de_acesso"] = carimbo[:10]
    if "data_do_dado" not in a.procedencia and citacao is not None:
        for ci in citacao.iterfind("gmd:date/gmd:CI_Date", NS):
            tipo = lt.codigo(ci, "gmd:dateType/gmd:CI_DateTypeCode")
            data = lt.texto(ci, "gmd:date")
            if data and tipo in ("creation", "publication"):
                a.procedencia["data_do_dado"] = data[:10]
                break
    if "frescor" not in a.procedencia:
        frequencia = lt.codigo(
            ident,
            "gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/"
            "gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode",
        )
        if frequencia:
            a.procedencia["frescor"] = frequencia

    # ---- metadado_iso (coluna jsonb do item; forma do Perfil MGB 2.0 desenhada no item irmão L0-09-b): o que a
    # ISO traz e não tem coluna própria no item — contato, sistema de referência, formato de distribuição e a
    # extensão espacial DECLARADA (que pode divergir do extent do dado, e é por isso que fica separada).
    contato_el = lt.acha(ident, "gmd:pointOfContact/gmd:CI_ResponsibleParty")
    if contato_el is None:
        contato_el = lt.acha(doc, "gmd:contact/gmd:CI_ResponsibleParty")
    contato = {}
    if contato_el is not None:
        for chave, caminho, teto in (
            ("organizacao", "gmd:organisationName", 250),
            ("individuo", "gmd:individualName", 250),
            ("email", "gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress", 250),
        ):
            v = lt.texto(contato_el, caminho)
            if v:
                contato[chave] = v[:teto]
        papel = lt.codigo(contato_el, "gmd:role/gmd:CI_RoleCode")
        if papel in CI_ROLE_CODE:
            contato["papel"] = papel
    if contato:
        a.metadado_iso["contato"] = contato

    rs = lt.acha(doc, "gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier")
    sistema = {}
    for chave, caminho in (("codigo", "gmd:code"), ("codespace", "gmd:codeSpace")):
        v = lt.texto(rs, caminho)
        if v:
            sistema[chave] = v[:20]
    if sistema:
        a.metadado_iso["sistema_referencia"] = sistema

    formato = lt.texto(
        doc, "gmd:distributionInfo/gmd:MD_Distribution/gmd:distributionFormat/gmd:MD_Format/gmd:name"
    ) or lt.texto(
        doc, "gmd:distributionInfo/gmd:MD_Distribution/gmd:distributionFormat/gmd:MD_Format/gmd:nameFormat"
    )
    if formato:
        a.metadado_iso["distribuicao"] = {"formato": formato[:100]}

    frequencia = lt.codigo(
        ident,
        "gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/"
        "gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode",
    )
    if frequencia in MD_MAINTENANCE_FREQUENCY_CODE:
        a.metadado_iso["manutencao"] = {"frequencia": frequencia}

    if "extent" in a.campos:
        x0, y0, x1, y1 = a.campos["extent"]
        a.metadado_iso["extensao"] = {"espacial": {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}}

    a.identificador_arquivo = lt.texto(doc, "gmd:fileIdentifier")
    a.nao_coube = lt.relatorio()
    return a


def perfil_do_item(row: dict, tenant_nome: str, base_url: str) -> Analise:
    """O que uma leitura do XML exportado do MESMO item TEM de devolver — montado da linha do banco, não do XML.
    É o lado esperado da cláusula de ida e volta: `analisar(gerar_xml(row))` tem de bater com isto, campo a
    campo. Fora do perfil ficam, de propósito, os elementos que a exportação escreve para quem LÊ o metadado e
    que não são campo editável do item (dono, miniatura, endereços da própria API, idioma/conjunto de caracteres
    fixos, nome e versão do padrão): reimportá-los seria reinventar identidade da plataforma a partir do texto."""
    esperado = Analise()
    for chave in ("titulo", "resumo", "creditos", "termos_de_uso"):
        if row.get(chave):
            esperado.campos[chave] = row[chave]
    if row.get("tags"):
        esperado.campos["tags"] = list(row["tags"])
    if row.get("status") in MD_PROGRESSO:
        esperado.campos["status"] = row["status"]
    if row.get("xmin") is not None:
        esperado.campos["extent"] = [float(row["xmin"]), float(row["ymin"]), float(row["xmax"]), float(row["ymax"])]
        esperado.metadado_iso["extensao"] = {
            "espacial": {
                "xmin": float(row["xmin"]),
                "ymin": float(row["ymin"]),
                "xmax": float(row["xmax"]),
                "ymax": float(row["ymax"]),
            }
        }
    dados = row.get("dados") or {}
    procedencia = dados.get("procedencia") if isinstance(dados, dict) else None
    if procedencia:
        esperado.procedencia = {
            chave: str(procedencia[chave])
            for chave, _rotulo in PROCEDENCIA_ROTULOS
            if procedencia.get(chave)
        }
    # o que a exportação escreve fora do bloco de procedência e a leitura recolhe de volta para ele: a
    # organização do inquilino (gmd:contact), o endereço do próprio item (distributionInfo) e as duas datas
    # do item. Quando o item JÁ tem esses valores em `dados.procedencia`, o do item manda — é ele que a
    # exportação escreveu na linhagem.
    esperado.procedencia.setdefault("fonte", tenant_nome)
    esperado.procedencia.setdefault("url", f"{base_url.rstrip('/')}/api/itens/{row['id']}")
    esperado.procedencia.setdefault(
        "data_de_acesso",
        (row["modificado_em"].date() if hasattr(row["modificado_em"], "date") else row["modificado_em"]).isoformat(),
    )
    esperado.procedencia.setdefault(
        "data_do_dado",
        (row["criado_em"].date() if hasattr(row["criado_em"], "date") else row["criado_em"]).isoformat(),
    )
    # contato: a exportação põe o DONO como pointOfContact do recurso (papel owner) e o inquilino como
    # contato do metadado; a leitura prefere o do recurso, que é o mais específico.
    if row.get("dono_nome"):
        esperado.metadado_iso["contato"] = {"individuo": row["dono_nome"], "papel": "owner"}
    else:
        esperado.metadado_iso["contato"] = {"organizacao": tenant_nome, "papel": "pointOfContact"}
    esperado.metadado_iso["sistema_referencia"] = {"codigo": "4326", "codespace": "EPSG"}
    esperado.identificador_arquivo = str(row["id"])
    return esperado


def diferencas(esperado: Analise, lido: Analise) -> list[dict]:
    """[{campo, esperado, lido}] entre duas análises — vazio é a cláusula 'ida e volta sem perda (diff = 0)'."""
    saida = []
    for grupo in ("campos", "procedencia", "metadado_iso"):
        a, b = getattr(esperado, grupo), getattr(lido, grupo)
        for chave in sorted(set(a) | set(b)):
            if a.get(chave) != b.get(chave):
                saida.append({"campo": f"{grupo}.{chave}", "esperado": a.get(chave), "lido": b.get(chave)})
    if esperado.identificador_arquivo != lido.identificador_arquivo:
        saida.append(
            {
                "campo": "identificador_arquivo",
                "esperado": esperado.identificador_arquivo,
                "lido": lido.identificador_arquivo,
            }
        )
    return saida
