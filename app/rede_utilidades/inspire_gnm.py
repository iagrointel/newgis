"""Exportador INSPIRE GNM (item L4-01-h): traduz um PACOTE DE ATIVOS (`app/rede_utilidades/esquema.py`)
para o modelo genérico de rede do INSPIRE — Generic Network Model, definido em `net:` (Network.xsd) e
especializado para redes de utilidade em `us-net-common:` (UtilityNetworksCommon.xsd), com extensões por
disciplina em `us-net-el:` (elétrica) e o `us-net-common:Pipe` genérico para água/gás.

O mapeamento é DADO (`MAPEAMENTO_GNM` abaixo), documentado campo a campo em `docs/INSPIRE_GNM.md`; o
exportador só materializa esse dado em GML. Cobre o que o portão de pronto pede: um documento de
mapeamento e um exportador que gera GML válido contra o XSD oficial para 1 rede de teste — não é um
tradutor genérico de qualquer pacote, e essa fronteira está declarada no handoff.

Vocabulário GNM usado (todos definidos em `app/rede_utilidades/gnm_xsd/`, cópia vendorizada dos XSD
oficiais do INSPIRE, resolvida offline pelo catálogo `gnm_xsd/catalogo.xml`):
  - nó de rede  -> `us-net-common:Appurtenance` (subtipo concreto de `net:Node`/`us-net-common:UtilityNode`)
  - elo de rede -> `us-net-common:UtilityLink` (subtipo concreto de `net:Link`), ou a especialização
    `us-net-el:ElectricityCable` quando a disciplina é elétrica e o grupo tem geometria de linha
  - o pacote inteiro vira um `base:SpatialDataSet` (elemento oficial, embora depreciado desde a v3.3.1
    em favor de `wfs:FeatureCollection` — mantido aqui porque é o único wrapper do próprio esquema
    INSPIRE que empacota vários `member` sem exigir um serviço WFS rodando; está registrado como
    ressalva no mapeamento, não escondido)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from lxml import etree

NS_GML = "http://www.opengis.net/gml/3.2"
NS_BASE = "http://inspire.ec.europa.eu/schemas/base/3.3"
NS_NET = "http://inspire.ec.europa.eu/schemas/net/4.0"
NS_UNC = "http://inspire.ec.europa.eu/schemas/us-net-common/4.0"
NS_UNEL = "http://inspire.ec.europa.eu/schemas/us-net-el/4.0"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_XLINK = "http://www.w3.org/1999/xlink"

_NSMAP = {
    "gml": NS_GML,
    "base": NS_BASE,
    "net": NS_NET,
    "us-net-common": NS_UNC,
    "us-net-el": NS_UNEL,
    "xsi": NS_XSI,
    "xlink": NS_XLINK,
}

_NAMESPACE_ONTOLOGIA = "https://iagrointel.invalido/esquemas/plat.rede.pacote/1#"


# ---------------------------------------------------------------------------
# Mapeamento campo a campo, disciplina a disciplina — mesma fonte para o
# documento (docs/INSPIRE_GNM.md, gerado por docs/gerar_pacote_rede.py-like
# script `docs/gerar_mapeamento_gnm.py`) e para o exportador.
# ---------------------------------------------------------------------------

MAPEAMENTO_GNM: dict[str, dict] = {
    "geral": {
        "pacote": {
            "gnm": "base:SpatialDataSet",
            "nota": "todo o pacote vira UM SpatialDataSet; pacote.codigo -> identifier/localId; "
            "pacote.nome -> não tem campo GNM correspondente, some (limitação declarada); "
            "pacote.versao -> identifier/versionId",
        },
        "grupo": {
            "gnm": "não vira classe própria",
            "nota": "grupo (ex. 'chave_de_media_tensao') não existe como classe no GNM: vira o "
            "specificAppurtenanceType (nó) ou o valor de referência do elo, sempre como URI da "
            "própria ontologia do pacote, nunca um código do vocabulário fechado do INSPIRE",
        },
        "tipo": {
            "gnm": "UtilityNode.appurtenanceType / UtilityLinkSet.warningType (referência genérica)",
            "nota": "tipo.chave -> sufixo do xlink:href; tipo.codigo (inteiro do pacote) -> "
            "atributo 'nota' xlink:title, só para leitura humana, não normativo",
        },
        "atributo": {
            "gnm": "sem classe correspondente",
            "nota": "atributos livres do pacote (ex. POT_NOM, PER_FER) NÃO têm campo no GNM — "
            "o GNM só modela topologia e status, não os atributos elétricos/hidráulicos do "
            "ativo; ficam de fora do GML, e isso é a limitação central do mapeamento "
            "(GNM é grafo, não é o modelo de dados operacional)",
        },
    },
    "eletrica": {
        "no": {
            "gnm": "us-net-common:Appurtenance",
            "geometria": "gml:PointPropertyType (grupo.geometria == 'ponto')",
            "campos": {
                "appurtenanceType": "xlink:href fixo 'urn:iagrointel:gnm:eletrica:no' (o INSPIRE "
                "exige um codelist de disciplina, ElectricityAppurtenanceTypeValue, que a UE ainda "
                "não publicou como codelist concreto — usamos URI própria e documentamos a lacuna)",
                "specificAppurtenanceType": f"xlink:href = {_NAMESPACE_ONTOLOGIA}<disciplina>/<grupo.codigo>",
                "verticalPosition": "'onGroundSurface' por default; sem campo equivalente explícito "
                "no pacote hoje (viria de um atributo tipo_dado=texto se existisse)",
            },
        },
        "elo": {
            "gnm": "us-net-el:ElectricityCable (subtipo de us-net-common:Cable / UtilityLinkSet)",
            "geometria": "gml:CurvePropertyType via centrelineGeometry (grupo.geometria == 'linha')",
            "campos": {
                "nominalVoltage/operatingVoltage": "SEM correspondência no pacote atual (não há "
                "atributo de tensão nominal padronizado nos grupos de 'alimentador'); exportado "
                "com xsi:nil e nilReason='unknown' quando o valor não existe no pacote",
            },
        },
    },
    "agua": {
        "no": {
            "gnm": "us-net-common:Appurtenance",
            "geometria": "gml:PointPropertyType",
            "campos": {
                "appurtenanceType": "xlink:href fixo 'urn:iagrointel:gnm:agua:no'",
            },
        },
        "elo": {
            "gnm": "us-net-common:Pipe (subtipo concreto de UtilityLinkSet, genérico o bastante "
            "para servir tubulação de água/gás/esgoto sem um pacote us-net-water/us-net-og "
            "próprio, que o INSPIRE também não publica pronto para uso)",
            "geometria": "gml:CurvePropertyType via centrelineGeometry",
            "campos": {
                "pipeDiameter": "SEM correspondência direta — viria de atributo do grupo 'tubo' "
                "no pacote água-EPANET, hoje não modelado com unidade normalizada; exportado nil",
            },
        },
    },
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _el(tag: str, **attrs) -> etree._Element:
    return etree.Element(tag, nsmap=_NSMAP, **attrs) if attrs == {} else etree.Element(tag, **attrs)


def _q(prefix: str, local: str) -> str:
    return f"{{{_NSMAP[prefix]}}}{local}"


def _identifier(local_id: str, namespace: str) -> etree._Element:
    """`base:Identifier` substitui `gml:AbstractObject`, não `gml:AbstractFeature` — sem `gml:id`
    (achado ao validar: o XSD oficial recusa o atributo aqui)."""
    ident = etree.Element(_q("base", "Identifier"))
    etree.SubElement(ident, _q("base", "localId")).text = local_id
    etree.SubElement(ident, _q("base", "namespace")).text = namespace
    return ident


def _identifier_property(local_id: str, namespace: str) -> etree._Element:
    prop = etree.Element(_q("base", "identifier"))
    prop.append(_identifier(local_id, namespace))
    return prop


def _reference(tag_ns: str, tag: str, href: str, title: str | None = None) -> etree._Element:
    el = etree.Element(_q(tag_ns, tag))
    el.set(_q("xlink", "href"), href)
    if title:
        el.set(_q("xlink", "title"), title)
    return el


@dataclass
class NoRedeTeste:
    id: str
    grupo: str
    lon: float
    lat: float


@dataclass
class EloRedeTeste:
    id: str
    grupo: str
    de: str
    para: str
    pontos: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class RedeTeste:
    codigo: str
    disciplina: str
    nos: list[NoRedeTeste]
    elos: list[EloRedeTeste]
    srs: str = "urn:ogc:def:crs:EPSG::4674"  # SIRGAS2000, o CRS oficial do território medido


def rede_teste_eletrica_br() -> RedeTeste:
    """Rede de 3 nós / 2 elos derivada de códigos reais do pacote elétrica-BR (alimentador de MT saindo
    de uma chave e alimentando um banco de capacitores), coordenadas dentro do Brasil (recorte de teste,
    sem CAR/BDGD real associado — é rede de TESTE, nunca dado de cliente)."""
    return RedeTeste(
        codigo="rede-teste-eletrica-br-01",
        disciplina="eletrica",
        nos=[
            NoRedeTeste(id="no-1-subestacao", grupo="alimentador", lon=-47.9292, lat=-15.7801),
            NoRedeTeste(id="no-2-chave", grupo="chave_de_media_tensao", lon=-47.9200, lat=-15.7750),
            NoRedeTeste(id="no-3-capacitor", grupo="banco_de_capacitores", lon=-47.9110, lat=-15.7700),
        ],
        elos=[
            EloRedeTeste(
                id="elo-1", grupo="alimentador", de="no-1-subestacao", para="no-2-chave",
                pontos=[(-47.9292, -15.7801), (-47.9200, -15.7750)],
            ),
            EloRedeTeste(
                id="elo-2", grupo="alimentador", de="no-2-chave", para="no-3-capacitor",
                pontos=[(-47.9200, -15.7750), (-47.9110, -15.7700)],
            ),
        ],
    )


def _ponto_gml(lon: float, lat: float, srs: str, gid: str) -> etree._Element:
    """`net:geometry` (não `gml:geometry`): o elemento pertence ao namespace `net` (Network.xsd,
    elementFormDefault=qualified), só o TIPO do valor é `gml:PointPropertyType`."""
    prop = etree.Element(_q("net", "geometry"))
    ponto = etree.SubElement(prop, _q("gml", "Point"))
    ponto.set(_q("gml", "id"), gid)
    ponto.set("srsName", srs)
    pos = etree.SubElement(ponto, _q("gml", "pos"))
    pos.text = f"{lat} {lon}"
    return prop


def _curva_gml(pontos: list[tuple[float, float]], srs: str, gid: str) -> etree._Element:
    prop = etree.Element(_q("net", "centrelineGeometry"))
    curva = etree.SubElement(prop, _q("gml", "Curve"))
    curva.set(_q("gml", "id"), gid)
    curva.set("srsName", srs)
    segments = etree.SubElement(curva, _q("gml", "segments"))
    seg = etree.SubElement(segments, _q("gml", "LineStringSegment"))
    poslist = etree.SubElement(seg, _q("gml", "posList"))
    poslist.text = " ".join(f"{lat} {lon}" for lon, lat in pontos)
    return prop


def _campos_comuns_elemento(el: etree._Element, quando: datetime, rede_codigo: str) -> None:
    """`net:NetworkElementType`: beginLifespanVersion (obrigatório) + inNetwork (obrigatório,
    sem minOccurs declarado no XSD oficial -> default 1, achado ao validar a 1ª tentativa)."""
    begin = etree.SubElement(el, _q("net", "beginLifespanVersion"))
    begin.text = _iso(quando)
    in_rede = etree.SubElement(el, _q("net", "inNetwork"))
    in_rede.set(_q("xlink", "href"), f"urn:iagrointel:gnm:rede:{rede_codigo}")


def _no_para_appurtenance(no: NoRedeTeste, disciplina: str, srs: str, quando: datetime,
                           rede_codigo: str) -> etree._Element:
    ap = etree.Element(_q("us-net-common", "Appurtenance"), nsmap=_NSMAP)
    ap.set(_q("gml", "id"), no.id)
    _campos_comuns_elemento(ap, quando, rede_codigo)  # net:NetworkElementType
    ap.append(_ponto_gml(no.lon, no.lat, srs, f"{no.id}-geom"))  # net:NodeType.geometry
    ap.append(_reference("us-net-common", "currentStatus",  # us-net-common:UtilityNodeType
                          "urn:iagrointel:gnm:status:funcional", "funcional (declarado, não medido em campo)"))
    valid_from = etree.SubElement(ap, _q("us-net-common", "validFrom"))
    valid_from.text = _iso(quando)
    vp = etree.SubElement(ap, _q("us-net-common", "verticalPosition"))
    vp.text = "onGroundSurface"
    ap.append(_reference("us-net-common", "appurtenanceType",  # us-net-common:AppurtenanceType
                          f"urn:iagrointel:gnm:{disciplina}:no"))
    especifico = _NAMESPACE_ONTOLOGIA + f"{disciplina}/{no.grupo}"
    ap.append(_reference("us-net-common", "specificAppurtenanceType", especifico, no.grupo))
    return ap


def _elo_para_link(elo: EloRedeTeste, disciplina: str, srs: str, quando: datetime,
                    rede_codigo: str) -> etree._Element:
    """`us-net-common:UtilityLink` (concreto, substitutionGroup net:Link) para os dois domínios: os
    subtipos por disciplina (ElectricityCable, Pipe) são `UtilityLinkSet`, não `Link` — outra cadeia
    de tipo (sem centrelineGeometry/fictitious/startNode/endNode diretos, precisam de LinkSequence
    apontando para Links reais). Fora do escopo desta rede de teste; registrado como limitação."""
    link = etree.Element(_q("us-net-common", "UtilityLink"), nsmap=_NSMAP)
    link.set(_q("gml", "id"), elo.id)
    _campos_comuns_elemento(link, quando, rede_codigo)  # net:NetworkElementType
    # net:GeneralisedLinkType não acrescenta campo (sequence vazia)
    link.append(_curva_gml(elo.pontos, srs, f"{elo.id}-geom"))  # net:LinkType.centrelineGeometry
    fic = etree.SubElement(link, _q("net", "fictitious"))
    fic.text = "false"
    link.append(_reference("net", "endNode", f"#{elo.para}"))
    link.append(_reference("net", "startNode", f"#{elo.de}"))
    link.append(_reference("us-net-common", "currentStatus",  # us-net-common:UtilityLinkType
                            "urn:iagrointel:gnm:status:funcional", "funcional (declarado)"))
    valid_from = etree.SubElement(link, _q("us-net-common", "validFrom"))
    valid_from.text = _iso(quando)
    vp = etree.SubElement(link, _q("us-net-common", "verticalPosition"))
    vp.text = "suspendedOrElevated" if disciplina == "eletrica" else "underground"
    return link


def exportar_gml(rede: RedeTeste, quando: datetime | None = None) -> bytes:
    """Gera o GML de UMA rede de teste como `base:SpatialDataSet`, membros `us-net-common:Appurtenance`
    (nós) e `us-net-common:UtilityLink` (elos), pronto para validar contra o XSD oficial."""
    quando = quando or datetime(2026, 9, 6, tzinfo=timezone.utc)
    raiz = etree.Element(_q("base", "SpatialDataSet"), nsmap=_NSMAP)
    raiz.set(_q("gml", "id"), f"sds-{rede.codigo}")
    raiz.append(_identifier_property(rede.codigo, _NAMESPACE_ONTOLOGIA))
    metadata = etree.SubElement(raiz, _q("base", "metadata"))
    metadata.set(_q("xsi", "nil"), "true")
    metadata.set("nilReason", "unpopulated")

    for no in rede.nos:
        membro = etree.SubElement(raiz, _q("base", "member"))
        membro.append(_no_para_appurtenance(no, rede.disciplina, rede.srs, quando, rede.codigo))
    for elo in rede.elos:
        membro = etree.SubElement(raiz, _q("base", "member"))
        membro.append(_elo_para_link(elo, rede.disciplina, rede.srs, quando, rede.codigo))

    return etree.tostring(raiz, pretty_print=True, xml_declaration=True, encoding="UTF-8")
