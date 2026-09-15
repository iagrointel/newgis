"""Item L0-09-metadado-catalogo, cláusula 1 (refutação G4): CSW 2.0.2 (`/csw`, KVP) — GetCapabilities,
GetRecords (Dublin Core e ISO 19139) e GetRecordById, sempre autenticado (`catalogo:ler`), nunca aberto,
mesmo isolamento por inquilino de `/ogc/records` (`tests/api/catalogo/test_metadado_ogc.py`). Não existe
`CSW-discovery.xsd`/`record.xsd` em `docs/xsd/cache/` nesta máquina (só a árvore ISO 19139), então
GetCapabilities é conferido por bom-formação (lxml) e pelas operações/parâmetros esperados — GetRecordById
em ISO É validado contra o XSD oficial cacheado, reaproveitando `app.catalogo.metadado.validar` (a mesma
validação de `GET /api/itens/{id}/metadado.xml`)."""

import secrets

from lxml import etree

from app.catalogo import csw as mod_csw
from app.catalogo import metadado
from tests.api.conftest import novo_cliente

NS = {"csw": mod_csw.CSW, "ows": mod_csw.OWS, "dc": mod_csw.DC, "gmd": mod_csw.GMD}


def _token_catalogo_ler(sessao):
    r = sessao.post("/api/tokens", json={"nome": "zt-l0-09-csw", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def _get(sessao_ou_cliente, params, headers=None):
    r = sessao_ou_cliente.get("/csw", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return etree.fromstring(r.content)


def test_csw_nunca_aberto():
    c = novo_cliente()
    for qs in ("REQUEST=GetCapabilities", "REQUEST=GetRecords", "REQUEST=GetRecordById&ID=x"):
        assert c.get(f"/csw?{qs}").status_code == 401, qs


def test_get_capabilities_bem_formado_com_as_tres_operacoes(sessao_a):
    r = sessao_a.get("/csw?SERVICE=CSW&VERSION=2.0.2&REQUEST=GetCapabilities")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")
    doc = etree.fromstring(r.content)
    assert doc.tag == f"{{{mod_csw.CSW}}}Capabilities"
    operacoes = {el.get("name") for el in doc.findall(".//ows:Operation", NS)}
    assert {"GetCapabilities", "GetRecords", "GetRecordById"} <= operacoes


def test_get_records_dublin_core_devolve_do_proprio_inquilino_e_zero_do_outro(sessao_a, sessao_b, itens_a, itens_b):
    marca = "ztcsw" + secrets.token_hex(6)
    de_a = itens_a.criar("mapa", tags=[marca])
    de_b = itens_b.criar("mapa", tags=[marca])
    tok_a = _token_catalogo_ler(sessao_a)
    c = novo_cliente()
    h = {"Authorization": f"Bearer {tok_a}"}
    doc = _get(c, {"REQUEST": "GetRecords", "CONSTRAINT": f"AnyText LIKE '%{marca}%'"}, h)
    assert doc.tag == f"{{{mod_csw.CSW}}}GetRecordsResponse"
    ids = {el.text for el in doc.findall(".//dc:identifier", NS)}
    assert de_a["id"] in ids
    assert de_b["id"] not in ids
    resultados = doc.find(".//csw:SearchResults", NS)
    assert resultados.get("numberOfRecordsMatched") == "1"
    assert resultados.get("numberOfRecordsReturned") == "1"


def test_get_records_startposition_maxrecords_pagina(sessao_a, itens_a):
    marca = "ztcswpagina" + secrets.token_hex(6)
    criados = [itens_a.criar("mapa", tags=[marca]) for _ in range(3)]
    constraint = f"AnyText LIKE '%{marca}%'"
    doc1 = _get(
        sessao_a,
        {"REQUEST": "GetRecords", "CONSTRAINT": constraint, "MAXRECORDS": "2", "STARTPOSITION": "1"},
    )
    res1 = doc1.find(".//csw:SearchResults", NS)
    assert res1.get("numberOfRecordsMatched") == str(len(criados))
    assert res1.get("numberOfRecordsReturned") == "2"
    assert res1.get("nextRecord") == "3"
    doc2 = _get(
        sessao_a,
        {"REQUEST": "GetRecords", "CONSTRAINT": constraint, "MAXRECORDS": "2", "STARTPOSITION": "3"},
    )
    res2 = doc2.find(".//csw:SearchResults", NS)
    assert res2.get("numberOfRecordsReturned") == "1"
    assert res2.get("nextRecord") == "0"


def test_get_records_outputschema_iso_reaproveita_o_gerador_e_valida(sessao_a, itens_a):
    marca = "ztcswiso" + secrets.token_hex(6)
    itens_a.criar("mapa", resumo="resumo csw iso", tags=[marca], extent=[-50.0, -20.0, -40.0, -10.0])
    doc = _get(
        sessao_a,
        {"REQUEST": "GetRecords", "OUTPUTSCHEMA": mod_csw.GMD, "CONSTRAINT": f"AnyText LIKE '%{marca}%'"},
    )
    registros = doc.findall(".//gmd:MD_Metadata", NS)
    assert len(registros) == 1
    metadado.validar(etree.tostring(registros[0]))


def test_get_record_by_id_dublin_core_e_iso(sessao_a, itens_a, sessao_b, itens_b):
    it = itens_a.criar("mapa", resumo="r", extent=[-50.0, -20.0, -40.0, -10.0])
    de_b = itens_b.criar("mapa")
    doc = _get(sessao_a, {"REQUEST": "GetRecordById", "ID": it["id"]})
    assert doc.tag == f"{{{mod_csw.CSW}}}GetRecordByIdResponse"
    assert doc.find(".//dc:identifier", NS).text == it["id"]
    doc_iso = _get(sessao_a, {"REQUEST": "GetRecordById", "ID": it["id"], "OUTPUTSCHEMA": mod_csw.GMD})
    md = doc_iso.find(".//gmd:MD_Metadata", NS)
    assert md is not None
    metadado.validar(etree.tostring(md))  # a refutação "GetRecordById em ISO valida"
    # isolamento: sessão do inquilino A nunca lê o registro do item de B
    assert sessao_a.get(f"/csw?REQUEST=GetRecordById&ID={de_b['id']}").status_code == 404


def test_cql_nao_suportado_e_400_nomeado(sessao_a):
    r = sessao_a.get("/csw", params={"REQUEST": "GetRecords", "CONSTRAINT": "title = 'x'"})
    assert r.status_code == 400, r.text
    assert r.json()["erro"] == "cql_nao_suportado"


def test_request_desconhecido_e_400(sessao_a):
    assert sessao_a.get("/csw?REQUEST=DescribeRecord").status_code == 400
