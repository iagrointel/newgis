"""Paridade entre o que se ESCREVE no metadado e o que se LÊ pelo catálogo — item L0-09-metadado-catalogo.

As outras cláusulas do portão já têm arquivo próprio: `test_csw.py` (GetCapabilities, GetRecords,
GetRecordById e ISO 19139 contra o XSD cacheado), `test_metadado_19115_3.py` (o perfil 19115-3, também
contra o XSD cacheado, inclusive por CSW) e `test_metadado_editor.py` (a escrita pelo editor). Falta
juntar as duas pontas, que é a cláusula "paridade escrita": o que o editor grava tem de ser exatamente o
que a descoberta externa devolve — nos dois esquemas de saída e nas duas operações — senão o catálogo
publica uma ficha diferente da que o dono preencheu.

Par positivo/negativo em cada asserção de isolamento: o inquilino A lê a própria ficha na mesma rodada
em que B recebe 404 dela.
"""

import secrets

import pytest
from lxml import etree

from app.catalogo import csw as mod_csw

NS = {"csw": mod_csw.CSW, "ows": mod_csw.OWS, "dc": mod_csw.DC, "gmd": mod_csw.GMD}
ITEM = "L0-09-metadado-catalogo"

ORGANIZACAO = "iAgroSat paridade"
EMAIL = "paridade@exemplo.org"
LICENCA = "CC BY-SA 4.0"
CRS = "31983"


def _escrito(sessao, itens, marca: str) -> dict:
    """Item com metadado preenchido PELO EDITOR (as rotas que web/js/catalogo/item_metadado.js chama)."""
    it = itens.criar(
        "camada_vetorial",
        resumo=f"resumo de paridade {marca}",
        tags=[marca, "paridade"],
        extent=[-48.5, -16.2, -47.1, -15.3],
    )
    r = sessao.put(
        f"/api/itens/{it['id']}/metadado",
        json={"metadado": {
            "contato": {"organizacao": ORGANIZACAO, "email": EMAIL, "papel": "pointOfContact"},
            "restricoes": {"licenca": LICENCA},
            "sistema_referencia": {"codigo": CRS, "codespace": "EPSG"},
        }},
    )
    assert r.status_code == 200, r.text
    return it


def _texto(doc) -> str:
    return " ".join(t.strip() for t in doc.itertext() if t and t.strip())


def _get(sessao, params):
    r = sessao.get("/csw", params=params)
    assert r.status_code == 200, r.text
    return etree.fromstring(r.content)


MOTIVO = (
    "DEFEITO MEDIDO 17/09 (trilha provalocal, sha e9e2b1e3b): o que o EDITOR de metadado grava "
    "(PUT /api/itens/{id}/metadado -> contato.organizacao, restricoes.licenca, sistema_referencia.codigo) "
    "persiste e volta no GET /api/itens/{id}/metadado, mas NÃO chega a nenhuma exportação ISO: nem "
    "/api/itens/{id}/metadado.xml (19139), nem ?formato=19115-3, nem o CSW. "
    "`app/catalogo/metadado.py::montar_md_metadata` monta o XML só das COLUNAS do item — põe o nome do "
    "inquilino em gmd:contact, o dono em pointOfContact e escreve EPSG:4326 fixo (linhas 172-190) — e "
    "nunca lê o `metadado_iso` do editor. Medido: escrevi ORGDIG/LICDIG/31983 e as três saídas ISO "
    "devolveram False para os três valores. Não foi consertado aqui porque o conserto não é pequeno: "
    "mexe no gerador 19139, no 19115-3, no perfil MGB, no CSW e na tabela de paridade de "
    "`metadado.py::paridade_esperada` (que hoje DECLARA como esperado o contato do inquilino/dono e o "
    "4326 fixo) — é decisão de produto sobre qual fonte manda, não conserto de teste."
)


@pytest.mark.xfail(strict=True, reason=MOTIVO)
def test_o_que_o_editor_gravou_volta_no_getrecordbyid_iso(sessao_a, itens_a):
    marca = "ztpar" + secrets.token_hex(5)
    it = _escrito(sessao_a, itens_a, marca)
    doc = _get(sessao_a, {"REQUEST": "GetRecordById", "ID": it["id"], "OUTPUTSCHEMA": mod_csw.GMD})
    md = doc.find(".//gmd:MD_Metadata", NS)
    assert md is not None, etree.tostring(doc)[:500]
    texto = _texto(md)
    for escrito in (it["titulo"], f"resumo de paridade {marca}", ORGANIZACAO, EMAIL, LICENCA, CRS):
        assert escrito in texto, f"o catálogo não devolveu o que o editor gravou: {escrito!r}"


def test_a_mesma_ficha_sai_igual_no_getrecords_e_no_getrecordbyid(sessao_a, itens_a):
    """Duas operações, uma ficha só: se o GetRecords montasse o ISO por outro caminho, a descoberta em
    lote mostraria um metadado e a ficha individual outro."""
    marca = "ztpar" + secrets.token_hex(5)
    it = _escrito(sessao_a, itens_a, marca)
    lote = _get(sessao_a, {"REQUEST": "GetRecords", "OUTPUTSCHEMA": mod_csw.GMD,
                           "CONSTRAINT": f"AnyText LIKE '%{marca}%'"})
    registros = lote.findall(".//gmd:MD_Metadata", NS)
    assert len(registros) == 1, len(registros)
    unico = _get(sessao_a, {"REQUEST": "GetRecordById", "ID": it["id"], "OUTPUTSCHEMA": mod_csw.GMD})
    assert _texto(registros[0]) == _texto(unico.find(".//gmd:MD_Metadata", NS))


def test_paridade_no_dublin_core_titulo_resumo_e_palavras_chave(sessao_a, itens_a):
    marca = "ztpar" + secrets.token_hex(5)
    it = _escrito(sessao_a, itens_a, marca)
    doc = _get(sessao_a, {"REQUEST": "GetRecordById", "ID": it["id"]})
    texto = _texto(doc)
    assert doc.find(".//dc:identifier", NS).text == it["id"]
    for escrito in (it["titulo"], f"resumo de paridade {marca}", marca):
        assert escrito in texto, f"Dublin Core sem o que foi escrito: {escrito!r}"


@pytest.mark.xfail(strict=True, reason=MOTIVO)
def test_edicao_posterior_aparece_no_catalogo_e_a_anterior_some(sessao_a, itens_a):
    """Paridade não é só do primeiro salvamento: trocar a licença tem de trocar o que a descoberta serve."""
    marca = "ztpar" + secrets.token_hex(5)
    it = _escrito(sessao_a, itens_a, marca)
    nova = "ODbL 1.0"
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": {"restricoes": {"licenca": nova}}})
    assert r.status_code == 200, r.text
    texto = _texto(_get(sessao_a, {"REQUEST": "GetRecordById", "ID": it["id"], "OUTPUTSCHEMA": mod_csw.GMD}))
    assert nova in texto
    assert LICENCA not in texto, "o catálogo continuou servindo a licença antiga"


def test_ficha_escrita_em_a_nunca_sai_para_b(sessao_a, sessao_b, itens_a):
    marca = "ztpar" + secrets.token_hex(5)
    it = _escrito(sessao_a, itens_a, marca)
    # par positivo, na mesma rodada: A lê a própria ficha
    assert sessao_a.get(f"/csw?REQUEST=GetRecordById&ID={it['id']}").status_code == 200
    assert sessao_b.get(f"/csw?REQUEST=GetRecordById&ID={it['id']}").status_code == 404
    doc_b = _get(sessao_b, {"REQUEST": "GetRecords", "CONSTRAINT": f"AnyText LIKE '%{marca}%'"})
    assert doc_b.find(".//csw:SearchResults", NS).get("numberOfRecordsMatched") == "0"


def test_medida_paridade(sessao_a, itens_a, medida):
    """Quantos valores escritos pelo editor voltam em cada saída do catálogo. Enquanto o defeito acima
    não for decidido, este número é 0 de 3 nas saídas ISO — e é assim que ele fica registrado."""
    marca = "ztpar" + secrets.token_hex(5)
    it = _escrito(sessao_a, itens_a, marca)
    escritos = {"contato.organizacao": ORGANIZACAO, "restricoes.licenca": LICENCA,
                "sistema_referencia.codigo": CRS}
    lido = sessao_a.get(f"/api/itens/{it['id']}/metadado").json()["campos"]
    de_volta_no_editor = sum([
        lido["contato"].get("organizacao") == ORGANIZACAO,
        lido["restricoes"].get("licenca") == LICENCA,
        lido["sistema_referencia"].get("codigo") == CRS,
    ])
    saidas = {
        "metadado_xml_19139": sessao_a.get(f"/api/itens/{it['id']}/metadado.xml").text,
        "metadado_xml_19115_3": sessao_a.get(f"/api/itens/{it['id']}/metadado.xml?formato=19115-3").text,
        "csw_getrecordbyid_iso": sessao_a.get(
            f"/csw?REQUEST=GetRecordById&ID={it['id']}&OUTPUTSCHEMA={mod_csw.GMD}").text,
    }
    placar = {nome: sum(1 for v in escritos.values() if v in texto) for nome, texto in saidas.items()}
    assert de_volta_no_editor == 3, lido
    medida(ITEM)(
        "paridade_editor_para_saidas_iso",
        {"valores_escritos": len(escritos), "de_volta_no_editor": de_volta_no_editor, "nas_saidas": placar},
        "valores do editor encontrados em cada saída do catálogo (de 3)",
        "pytest tests/api/catalogo/test_csw_paridade.py::test_medida_paridade -q",
    )
