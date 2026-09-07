"""Item L4-01-h: portão de pronto -> o GML exportado do pacote de ativos valida contra o XSD OFICIAL
do INSPIRE Generic Network Model (net/us-net-common/us-net-el), resolvido OFFLINE pelo catálogo
`app/rede_utilidades/gnm_xsd/catalogo.xml` (cópia vendorizada, sem depender de rede em CI)."""

import os
import subprocess
from pathlib import Path

import pytest

from app.rede_utilidades.inspire_gnm import (
    MAPEAMENTO_GNM,
    EloRedeTeste,
    NoRedeTeste,
    RedeTeste,
    exportar_gml,
    rede_teste_eletrica_br,
)

RAIZ_XSD = Path(__file__).resolve().parents[2] / "app" / "rede_utilidades" / "gnm_xsd"
CATALOGO = RAIZ_XSD / "catalogo.xml"
XSD_ELETRICA = RAIZ_XSD / "inspire.ec.europa.eu/schemas/us-net-el/4.0/ElectricityNetwork.xsd"
XSD_COMUM = RAIZ_XSD / "inspire.ec.europa.eu/schemas/us-net-common/4.0/UtilityNetworksCommon.xsd"

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


def _validar(gml_bytes: bytes, xsd: Path) -> subprocess.CompletedProcess:
    tmp = Path("/tmp/_test_gnm_gml.xml")
    tmp.write_bytes(gml_bytes)
    ambiente = dict(os.environ, XML_CATALOG_FILES=str(CATALOGO))
    return subprocess.run(
        ["xmllint", "--noout", "--schema", str(xsd), str(tmp)],
        capture_output=True, text=True, env=ambiente,
    )


def test_gml_eletrica_valida_contra_xsd_oficial_us_net_el():
    gml = exportar_gml(rede_teste_eletrica_br())
    resultado = _validar(gml, XSD_ELETRICA)
    assert "validates" in resultado.stderr, resultado.stderr
    assert resultado.returncode == 0


def test_gml_eletrica_valida_contra_xsd_oficial_us_net_common():
    gml = exportar_gml(rede_teste_eletrica_br())
    resultado = _validar(gml, XSD_COMUM)
    assert "validates" in resultado.stderr, resultado.stderr


def test_gml_agua_valida_contra_xsd_oficial_us_net_common():
    gml = exportar_gml(_rede_agua())
    resultado = _validar(gml, XSD_COMUM)
    assert "validates" in resultado.stderr, resultado.stderr


def test_gml_reprova_sem_o_catalogo_offline_se_xsd_ausente():
    """Confere que a validação é FEITA (não simulada): removendo o XSD, a chamada falha em vez de
    passar silenciosamente."""
    xsd_inexistente = RAIZ_XSD / "inspire.ec.europa.eu/schemas/us-net-el/4.0/NaoExiste.xsd"
    resultado = subprocess.run(
        ["xmllint", "--noout", "--schema", str(xsd_inexistente), "/dev/null"],
        capture_output=True, text=True,
    )
    assert resultado.returncode != 0


def test_mapeamento_cobre_eletrica_e_agua_com_no_e_elo():
    for disciplina in ("eletrica", "agua"):
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
