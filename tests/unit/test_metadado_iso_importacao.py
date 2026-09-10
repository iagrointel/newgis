"""Item L0-09-c-xml-iso-validacao: leitura de metadado ISO 19139 (`app.catalogo.metadado.analisar`).

Sem banco e sem rede: o XSD é o cache do repositório (docs/xsd/cache/, baixado por docs/xsd/baixar_iso19139.py)
e o metadado real é o registro aberto da INDE guardado em tests/dados/. Aqui ficam as provas do analisador —
XSD com zero erro no que a plataforma gera, ida e volta sem perda, e a refutação do item (entidade externa,
XML gigante, namespace errado)."""

import datetime
import uuid
from pathlib import Path

import pytest

from app import limites
from app.catalogo import metadado

RAIZ = Path(__file__).resolve().parents[2]
INDE = RAIZ / "tests" / "dados" / "inde_iso19139_carta_imagem.xml"


def linha(**campos) -> dict:
    """Linha crua de item, no formato de `comum.SQL_ITEM` (o que `gerar_xml` recebe)."""
    base = {
        "id": str(uuid.uuid4()),
        "titulo": "Carta de teste interno",
        "resumo": "Resumo do conjunto de dados de teste interno",
        "descricao": None,
        "creditos": None,
        "termos_de_uso": None,
        "tags": [],
        "status": "nenhum",
        "dono_nome": "Fulano de Teste",
        "miniatura_chave": None,
        "dados": {},
        "criado_em": datetime.datetime(2026, 1, 5, 10, 30),
        "modificado_em": datetime.datetime(2026, 3, 9, 8, 15),
        "xmin": None,
        "ymin": None,
        "xmax": None,
        "ymax": None,
    }
    base.update(campos)
    return base


TENANT = "SIG de teste interno"
BASE_URL = "https://exemplo.invalido"

TRES_ITENS = (
    linha(),
    linha(
        titulo="Camada de teste interno com tudo preenchido",
        resumo="Resumo longo do item, com acento e cedilha: informação de referência",
        creditos="Diretoria de teste interno",
        termos_de_uso="Uso interno; sem redistribuição",
        tags=["agro", "teste-zt", "solo"],
        status="autoritativo",
        xmin=-50.5,
        ymin=-20.25,
        xmax=-40.125,
        ymax=-10.0625,
        dados={
            "procedencia": {
                "fonte": "Instituto de teste interno",
                "url": "https://exemplo.invalido/fonte.zip",
                "licenca": "CC BY 4.0",
                "data_do_dado": "2025-06-30",
                "data_de_acesso": "2026-02-01",
                "metodo": "carga por script, conferida com contagem exata",
            }
        },
    ),
    linha(titulo="Item obsoleto de teste interno", status="obsoleto", tags=["zt-uma-etiqueta"]),
)


def _gerado(row: dict) -> bytes:
    return metadado.gerar_xml(row, TENANT, BASE_URL)


@pytest.mark.parametrize("row", TRES_ITENS, ids=("minimo", "completo", "obsoleto"))
def test_xml_gerado_valida_no_xsd_sem_nenhum_erro(row):
    """Cláusula 'XML gerado de 3 itens valida no XSD (0 erros)' — os três itens são os do parâmetro."""
    doc = metadado.ler_documento(_gerado(row))
    assert metadado.erros_xsd(doc) == []


@pytest.mark.parametrize("row", TRES_ITENS, ids=("minimo", "completo", "obsoleto"))
def test_ida_e_volta_nao_perde_campo_do_perfil(row):
    """Cláusula 'exportar → importar sem perda nos campos do perfil (diff = 0)'."""
    lido = metadado.analisar(_gerado(row))
    esperado = metadado.perfil_do_item(row, TENANT, BASE_URL)
    assert metadado.diferencas(esperado, lido) == []


def test_registro_real_da_inde_preenche_pelo_menos_quinze_campos():
    a = metadado.analisar(INDE.read_bytes())
    assert len(a.preenchidos) >= 15, a.preenchidos
    assert a.campos["titulo"].startswith("CARTA IMAGEM")
    assert a.procedencia["fonte"]
    assert a.metadado_iso["contato"]["email"] == "ibge@ibge.gov.br"


def test_registro_real_da_inde_nao_valida_no_xsd_e_isso_e_aviso_nao_recusa():
    """O catálogo nacional publica metadado que o XSD oficial reprova (ordem de elementos e extensões do Perfil
    MGB). A leitura segue e devolve os erros com linha — recusar seria recusar o dado aberto do país."""
    a = metadado.analisar(INDE.read_bytes())
    assert a.avisos_xsd, "o registro da INDE deveria acusar erro de XSD"
    assert all(av["linha"] > 0 for av in a.avisos_xsd)
    assert a.campos.get("titulo")


def test_relatorio_diz_o_que_nao_coube_com_caminho_linha_e_exemplo():
    a = metadado.analisar(INDE.read_bytes())
    caminhos = {e["caminho"]: e for e in a.nao_coube}
    assert "fileIdentifier/CharacterString" not in caminhos  # identificador é lido, não sobra
    telefone = caminhos.get(
        "contact/CI_ResponsibleParty/contactInfo/CI_Contact/phone/CI_Telephone/voice/CharacterString"
    )
    assert telefone and telefone["linha"] > 0 and telefone["exemplo"]
    assert len(a.nao_coube) <= limites.METADADO_NAO_COUBE_MAX


# ------------------------------------------------------------------------------------------ refutação do item
XXE = (
    b'<?xml version="1.0"?>\n'
    b'<!DOCTYPE raiz [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>\n'
    b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd" '
    b'xmlns:gco="http://www.isotc211.org/2005/gco">'
    b"<gmd:identificationInfo><gmd:MD_DataIdentification><gmd:citation><gmd:CI_Citation><gmd:title>"
    b"<gco:CharacterString>&xxe;</gco:CharacterString></gmd:title></gmd:CI_Citation></gmd:citation>"
    b"</gmd:MD_DataIdentification></gmd:identificationInfo></gmd:MD_Metadata>"
)


def test_entidade_externa_nunca_e_resolvida():
    try:
        a = metadado.analisar(XXE)
    except metadado.ErroXMLIlegivel:
        return  # recusar o documento também é resposta correta
    assert "root:" not in (a.campos.get("titulo") or "")
    assert "root:" not in repr(a.nao_coube)


def test_bomba_de_entidade_nao_expande():
    bomba = (
        b'<?xml version="1.0"?>\n<!DOCTYPE raiz [\n'
        b'<!ENTITY a "aaaaaaaaaa">\n<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">\n<!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">\n]>\n'
        b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd" '
        b'xmlns:gco="http://www.isotc211.org/2005/gco">'
        b"<gmd:identificationInfo><gmd:MD_DataIdentification><gmd:abstract>"
        b"<gco:CharacterString>&d;</gco:CharacterString></gmd:abstract>"
        b"</gmd:MD_DataIdentification></gmd:identificationInfo></gmd:MD_Metadata>"
    )
    try:
        a = metadado.analisar(bomba)
    except metadado.ErroXMLIlegivel:
        return
    assert len(a.campos.get("resumo") or "") < 1000


def test_xml_de_cinquenta_megabytes_e_recusado_antes_de_analisar():
    grande = b"<gmd:MD_Metadata>" + b"a" * (50 * 1024 * 1024)
    with pytest.raises(metadado.ErroXMLIlegivel) as exc:
        metadado.analisar(grande)
    assert str(limites.METADADO_XML_BYTES_MAX) in exc.value.mensagem


def test_namespace_errado_e_recusado_com_a_raiz_no_texto():
    outro = (
        b'<MD_Metadata xmlns="http://www.isotc211.org/2005/gmx">'
        b"<identificationInfo/></MD_Metadata>"
    )
    with pytest.raises(metadado.ErroXMLIlegivel) as exc:
        metadado.analisar(outro)
    assert "gmx" in exc.value.mensagem and "MD_Metadata" in exc.value.mensagem


def test_xml_malformado_diz_linha_e_coluna():
    with pytest.raises(metadado.ErroXMLIlegivel) as exc:
        metadado.analisar(b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">\n<gmd:oops>\n')
    assert exc.value.linha >= 2 and exc.value.coluna > 0


def test_linhagem_de_terceiro_entra_inteira_como_metodo_e_a_nossa_se_decompoe():
    prosa = "Mapeamento executado a partir de fotografias aéreas."
    assert metadado._procedencia_do_statement(prosa) == {"metodo": prosa}
    nosso = "fonte: Instituto de teste interno; licença: CC BY 4.0"
    assert metadado._procedencia_do_statement(nosso) == {
        "fonte": "Instituto de teste interno",
        "licenca": "CC BY 4.0",
    }
