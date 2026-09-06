"""Item L0-09-metadado-catalogo: exportação de metadado ISO 19139 (`GET /api/itens/{id}/metadado.xml`, validado
contra o XSD oficial cacheado em docs/xsd/cache/) e catálogo externo OGC API Records (`/ogc/records`), autenticado
por token de serviço (`catalogo:ler`, ADR 0002 seção 8) — nunca aberto. A prova que importa é a refutação do
item: token/sessão de um inquilino nunca lê o metadado nem o registro OGC de item de outro."""

import json
from pathlib import Path

from lxml import etree

from app.catalogo import metadado
from tests.api.conftest import novo_cliente

_RAIZ_XSD = Path(__file__).resolve().parents[3] / "docs" / "xsd" / "cache"


def _token_catalogo_ler(sessao):
    r = sessao.post("/api/tokens", json={"nome": "zt-l0-09", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_metadado_xml_valida_contra_xsd_oficial(sessao_a, itens_a):
    it = itens_a.criar(
        "mapa",
        resumo="Resumo do item de teste",
        descricao="Descrição mais longa, com **markdown**",
        tags=["agro", "teste-zt"],
        creditos="iAgroSat",
        termos_de_uso="Uso interno",
        extent=[-50.0, -20.0, -40.0, -10.0],
    )
    r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    doc = etree.fromstring(r.content)
    assert doc.tag == "{http://www.isotc211.org/2005/gmd}MD_Metadata"
    # a mesma rotina de validação que a rota usa: aqui é prova, não confiança na rota
    metadado.validar(r.content)
    fid = doc.find(".//{http://www.isotc211.org/2005/gco}CharacterString")
    assert fid is not None


def test_metadado_xml_item_minimo_tambem_valida(sessao_a, itens_a):
    """Item sem resumo, sem tags, sem extent, sem termos de uso: só os campos obrigatórios do tipo."""
    it = itens_a.criar("estilo")
    r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml")
    assert r.status_code == 200
    metadado.validar(r.content)


def test_metadado_xml_404_item_inexistente_e_de_outro_inquilino(sessao_a, sessao_b, itens_b):
    import uuid

    assert sessao_a.get(f"/api/itens/{uuid.uuid4()}/metadado.xml").status_code == 404
    de_b = itens_b.criar("mapa")
    r = sessao_a.get(f"/api/itens/{de_b['id']}/metadado.xml")
    assert r.status_code == 404
    assert sessao_b.get(f"/api/itens/{de_b['id']}/metadado.xml").status_code == 200


def test_metadado_xml_por_token_de_servico_catalogo_ler(sessao_a, sessao_b, itens_a, itens_b):
    it = itens_a.criar("mapa")
    de_b = itens_b.criar("mapa")
    tok = _token_catalogo_ler(sessao_a)
    c = novo_cliente()
    h = {"Authorization": f"Bearer {tok}"}
    r = c.get(f"/api/itens/{it['id']}/metadado.xml", headers=h)
    assert r.status_code == 200
    metadado.validar(r.content)
    # o token é do inquilino A: item de B nunca aparece, mesmo sabendo o uuid certo
    assert c.get(f"/api/itens/{de_b['id']}/metadado.xml", headers=h).status_code == 404


def test_ogc_records_nunca_aberto(sessao_a):
    c = novo_cliente()
    for caminho in ("/ogc/records", "/ogc/records/conformance", "/ogc/records/collections",
                    "/ogc/records/collections/catalogo/items"):
        assert c.get(caminho).status_code == 401, caminho


def test_ogc_records_pouso_e_conformidade(sessao_a):
    r = sessao_a.get("/ogc/records")
    assert r.status_code == 200
    corpo = r.json()
    assert {"self", "conformance", "data"} <= {link["rel"] for link in corpo["links"]}
    r = sessao_a.get("/ogc/records/conformance")
    assert r.status_code == 200
    conforma = r.json()["conformsTo"]
    assert any("ogcapi-records" in c for c in conforma)


def test_ogc_records_colecao_catalogo(sessao_a):
    r = sessao_a.get("/ogc/records/collections")
    assert r.status_code == 200
    colecoes = r.json()["collections"]
    assert [c["id"] for c in colecoes] == ["catalogo"]
    assert sessao_a.get("/ogc/records/collections/catalogo").status_code == 200
    assert sessao_a.get("/ogc/records/collections/inexistente").status_code == 404


def test_ogc_records_items_isolamento_por_inquilino(sessao_a, sessao_b, itens_a, itens_b):
    """A refutação do item: GetRecords/OGC API Records nunca devolve item de outro inquilino."""
    de_a = itens_a.criar("mapa", tags=["zt-ogc-a"])
    de_b = itens_b.criar("mapa", tags=["zt-ogc-b"])
    tok_a = _token_catalogo_ler(sessao_a)
    c = novo_cliente()
    h = {"Authorization": f"Bearer {tok_a}"}
    r = c.get(f"/ogc/records/collections/catalogo/items?q=id:{de_a['id']}", headers=h)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection"
    ids = {f["id"] for f in corpo["features"]}
    assert de_a["id"] in ids
    assert de_b["id"] not in ids
    # o mesmo id, pelo item único: 200 do próprio inquilino, 404 do outro
    assert c.get(f"/ogc/records/collections/catalogo/items/{de_a['id']}", headers=h).status_code == 200
    assert c.get(f"/ogc/records/collections/catalogo/items/{de_b['id']}", headers=h).status_code == 404
    # sessão do inquilino B nunca vê o item do A pela mesma rota
    r_b = sessao_b.get(f"/ogc/records/collections/catalogo/items?q=id:{de_a['id']}")
    assert de_a["id"] not in {f["id"] for f in r_b.json()["features"]}


def test_ogc_records_item_tem_link_para_metadado_xml(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = sessao_a.get(f"/ogc/records/collections/catalogo/items/{it['id']}")
    assert r.status_code == 200
    registro = r.json()
    hrefs = {link["href"] for link in registro["links"]}
    assert any(href.endswith(f"/api/itens/{it['id']}/metadado.xml") for href in hrefs)


def test_medidas_l0_09(sessao_a, itens_a, medida):
    import statistics
    import time

    it = itens_a.criar(
        "mapa", resumo="r", tags=["a", "b"], creditos="c", termos_de_uso="t", extent=[-50, -20, -40, -10]
    )
    tempos = []
    for _ in range(5):
        ini = time.perf_counter()
        r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml")
        tempos.append((time.perf_counter() - ini) * 1000)
        assert r.status_code == 200
    grava = medida("L0-09-metadado-catalogo")
    grava(
        "mediana_5_metadado_xml_ms",
        round(statistics.median(tempos), 1),
        "ms",
        "mediana de 5x GET /api/itens/{id}/metadado.xml (gera + valida contra o XSD)",
    )
    manifesto = json.loads((_RAIZ_XSD / "MANIFESTO.json").read_text(encoding="utf-8"))
    grava(
        "xsd_cache_arquivos",
        len(manifesto["arquivos"]),
        "arquivos",
        "len(docs/xsd/cache/MANIFESTO.json['arquivos']) — árvore ISO 19139 baixada 1x, offline depois",
    )
    grava(
        "xsd_cache_bytes",
        sum(a["bytes"] for a in manifesto["arquivos"]),
        "bytes",
        "soma de bytes de docs/xsd/cache/MANIFESTO.json['arquivos']",
    )
