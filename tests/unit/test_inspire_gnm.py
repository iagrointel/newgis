"""Item L4-01-h: portão de pronto -> o GML exportado do pacote de ativos valida contra o XSD OFICIAL
do INSPIRE Generic Network Model (net/us-net-common/us-net-el), resolvido OFFLINE pelo catálogo
`app/rede_utilidades/gnm_xsd/catalogo.xml` (cópia vendorizada, sem depender de rede em CI).

O validador é `lxml.etree.XMLSchema` — a mesma engine libxml2 que o `xmllint --schema` usa (lxml é
binding da libxml2), escolhido porque o binário xmllint não está instalado neste servidor e a regra
da trilha proíbe alterar o sistema; o XSD e o catálogo consumidos são os mesmos arquivos oficiais
vendorizados, então a prova é equivalente à do adversário (xmllint contra o XSD publicado)."""

import os
from pathlib import Path

import pytest
from lxml import etree

from app.rede_utilidades.inspire_gnm import (
    MAPEAMENTO_GNM,
    EloRedeTeste,
    NoRedeTeste,
    RedeTeste,
    exportar_gml,
    rede_teste_eletrica_br,
    rede_teste_gas_br,
)

RAIZ_XSD = Path(__file__).resolve().parents[2] / "app" / "rede_utilidades" / "gnm_xsd"
CATALOGO = RAIZ_XSD / "catalogo.xml"
XSD_ELETRICA = RAIZ_XSD / "inspire.ec.europa.eu/schemas/us-net-el/4.0/ElectricityNetwork.xsd"
XSD_COMUM = RAIZ_XSD / "inspire.ec.europa.eu/schemas/us-net-common/4.0/UtilityNetworksCommon.xsd"

# libxml2 lê XML_CATALOG_FILES na primeira resolução: tem de estar no ambiente ANTES de qualquer
# parse que importe esquema por URL pública (os XSD do INSPIRE importam gml/3.2 etc. por http).
os.environ["XML_CATALOG_FILES"] = str(CATALOGO)

pytestmark = pytest.mark.skipif(not CATALOGO.exists(), reason="XSD do GNM não vendorizado neste checkout")


def _rede_agua() -> RedeTeste:
    return RedeTeste(
        codigo="rede-teste-agua-01",
        disciplina="agua",
        nos=[
            NoRedeTeste("no-1-junction", "junction", -47.9000, -15.7800),
            NoRedeTeste("no-2-tanque", "tank", -47.8900, -15.7700),
        ],
        elos=[EloRedeTeste("elo-1-tubo", "pipe", "no-1-junction", "no-2-tanque",
                            [(-47.9000, -15.7800), (-47.8900, -15.7700)])],
    )


def _validar(gml_bytes: bytes, xsd: Path) -> etree.XMLSchema:
    esquema = etree.XMLSchema(etree.parse(str(xsd)))
    esquema.assertValid(etree.fromstring(gml_bytes))  # levanta com o log de erros se inválido
    return esquema


def test_gml_eletrica_valida_contra_xsd_oficial_us_net_el():
    _validar(exportar_gml(rede_teste_eletrica_br()), XSD_ELETRICA)


def test_gml_eletrica_valida_contra_xsd_oficial_us_net_common():
    _validar(exportar_gml(rede_teste_eletrica_br()), XSD_COMUM)


def test_gml_agua_valida_contra_xsd_oficial_us_net_common():
    _validar(exportar_gml(_rede_agua()), XSD_COMUM)


def test_gml_gas_valida_contra_xsd_oficial_us_net_common():
    _validar(exportar_gml(rede_teste_gas_br()), XSD_COMUM)


def test_gml_reprova_quando_o_conteudo_nao_segue_o_xsd():
    """Confere que a validação é FEITA (não simulada): um GML propositalmente quebrado (membro
    desconhecido) tem de ser recusado pelo mesmo XSD oficial, com mensagem de erro de schema."""
    gml = exportar_gml(rede_teste_eletrica_br()).replace(
        b"us-net-common:Appurtenance", b"us-net-common:ElementoInventado"
    )
    esquema = etree.XMLSchema(etree.parse(str(XSD_COMUM)))
    with pytest.raises(etree.DocumentInvalid):
        esquema.assertValid(etree.fromstring(gml))


def test_mapeamento_cobre_eletrica_agua_e_gas_com_no_e_elo():
    for disciplina in ("eletrica", "agua", "gas"):
        assert "no" in MAPEAMENTO_GNM[disciplina]
        assert "elo" in MAPEAMENTO_GNM[disciplina]
        assert "gnm" in MAPEAMENTO_GNM[disciplina]["no"]
        assert "gnm" in MAPEAMENTO_GNM[disciplina]["elo"]


def test_rede_de_teste_eletrica_tem_geometria_dentro_do_brasil():
    rede = rede_teste_eletrica_br()
    for no in rede.nos:
        assert -74 < no.lon < -34
        assert -34 < no.lat < 6
    assert len(rede.nos) == 3
    assert len(rede.elos) == 2


def test_rede_de_teste_gas_usa_grupos_reais_do_pacote_gas_br():
    import json

    pacote = json.loads(
        (Path(__file__).resolve().parents[2] / "app" / "rede_utilidades" / "pacotes" / "gas-br.json")
        .read_text(encoding="utf-8")
    )
    grupos_por_geometria = {g["codigo"]: g["geometria"] for g in pacote["grupos"]}
    rede = rede_teste_gas_br()
    for no in rede.nos:
        assert grupos_por_geometria[no.grupo] == "ponto"
        assert -74 < no.lon < -34
        assert -34 < no.lat < 6
    for elo in rede.elos:
        assert grupos_por_geometria[elo.grupo] == "linha"
    assert len(rede.nos) == 3
    assert len(rede.elos) == 2
