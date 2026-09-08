"""Cláusula INEGOCIÁVEL do item L1-01-a: busca com token do inquilino A nunca devolve item/coleção do
inquilino B — testado em search, collections, items e queryables (a lista exata da refutação do item),
com A tentando enxergar B pelo path, pela query string e pelo corpo do POST /search."""

import secrets

import pytest

from tests.api.imagens.conftest import item_stac


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def cenario(token_stac_a, token_stac_b):
    ta, tb = token_stac_a["token"], token_stac_b["token"]
    c = _cliente()
    slug = f"isola-{secrets.token_hex(4)}"  # sufixo aleatório: a base da trilha persiste entre reexecuções
    ca = c.post(f"/svc/{ta}/stac/collections", params={"slug": slug}, json={"title": "Coleção secreta de A"})
    assert ca.status_code == 201, ca.text
    colecao_a = ca.json()["id"]
    cb = c.post(f"/svc/{tb}/stac/collections", params={"slug": slug}, json={"title": "Coleção secreta de B"})
    assert cb.status_code == 201, cb.text
    colecao_b = cb.json()["id"]
    assert colecao_a != colecao_b  # o slug é igual nos dois; o prefixo <tenant_id>- é que distingue

    ia = c.post(f"/svc/{ta}/stac/collections/{colecao_a}/items", json=item_stac("item-a-1", colecao_a))
    assert ia.status_code == 201, ia.text
    ib = c.post(
        f"/svc/{tb}/stac/collections/{colecao_b}/items", json=item_stac("item-b-1", colecao_b, lon=-43.2, lat=-22.9)
    )
    assert ib.status_code == 201, ib.text
    return {"cliente": c, "ta": ta, "tb": tb, "colecao_a": colecao_a, "colecao_b": colecao_b}


def test_colecoes_de_a_nunca_lista_a_de_b(cenario):
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/collections")
    assert r.status_code == 200
    ids = [col["id"] for col in r.json()["collections"]]
    assert cenario["colecao_a"] in ids
    assert cenario["colecao_b"] not in ids


def test_colecao_de_b_pelo_token_de_a_e_404_nunca_403(cenario):
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/collections/{cenario['colecao_b']}")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "colecao_inexistente"


def test_item_de_b_pelo_token_de_a_via_url_e_404(cenario):
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/collections/{cenario['colecao_b']}/items/item-b-1")
    assert r.status_code == 404, r.text


def test_items_de_b_listados_pelo_token_de_a_e_404(cenario):
    """A não pode nem listar os itens da coleção de B (o 404 da própria coleção já barra, mas confere de novo
    o endpoint .../items especificamente — é um dos 4 endpoints citados na refutação do item)."""
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/collections/{cenario['colecao_b']}/items")
    assert r.status_code == 404, r.text


def test_search_com_collections_de_b_no_pedido_de_a_nao_vaza(cenario):
    """A pede EXPLICITAMENTE a coleção de B em `collections` — o servidor tem de ignorar, nunca aceitar."""
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/search", params={"collections": cenario["colecao_b"]})
    assert r.status_code == 200
    assert r.json()["features"] == []
    assert r.json().get("numberMatched", 0) == 0

    r2 = c.post(f"/svc/{ta}/stac/search", json={"collections": [cenario["colecao_b"]]})
    assert r2.status_code == 200
    assert r2.json()["features"] == []


def test_search_sem_collections_de_a_nunca_devolve_item_de_b(cenario):
    """Busca ABERTA (sem `collections` no pedido) tem de voltar só o que é de A — a chave `collections` some
    de propósito na hora de montar o `_search` interno se isto falhar (ver app/imagens/pgstac.py)."""
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/search", params={"limit": 100})
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()["features"]]
    colecoes = [f["collection"] for f in r.json()["features"]]
    assert "item-b-1" not in ids
    assert cenario["colecao_b"] not in colecoes


def test_search_por_ids_de_b_no_token_de_a_nao_vaza(cenario):
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.post(f"/svc/{ta}/stac/search", json={"ids": ["item-b-1"]})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_queryables_de_colecao_de_b_pelo_token_de_a_e_404(cenario):
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/collections/{cenario['colecao_b']}/queryables")
    assert r.status_code == 404, r.text


def test_queryables_globais_nao_recusam_mas_nao_sao_dado_de_ninguem(cenario):
    """`/queryables` (sem coleção) é um esquema genérico de campos, igual para todo mundo — confere que
    responde 200 (não é uma via de vazamento: não lista coleção nem item)."""
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.get(f"/svc/{ta}/stac/queryables")
    assert r.status_code == 200
    assert "properties" in r.json()


def test_criar_item_em_colecao_de_b_com_token_de_a_e_404(cenario):
    """A não escreve em coleção de B mesmo tendo o escopo imagens:escrever — a coleção nem existe do
    ponto de vista do token de A."""
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.post(
        f"/svc/{ta}/stac/collections/{cenario['colecao_b']}/items",
        json=item_stac("invasao", cenario["colecao_b"]),
    )
    assert r.status_code == 404, r.text


def test_token_sem_escopo_imagens_e_403(sessao_a, token_stac_a):
    """Escopo insuficiente é 403 (não 404): aqui existe permissão de o DONO ver, só o TOKEN que não pode."""
    c = _cliente()
    r = sessao_a.post("/api/tokens", json={"nome": "zt-stac-so-catalogo", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        resp = c.get(f"/svc/{tok['token']}/stac/collections")
        assert resp.status_code == 403
        assert resp.json()["erro"] == "escopo_insuficiente"
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_token_invalido_e_401(cenario):
    c = cenario["cliente"]
    r = c.get("/svc/plat_token-que-nao-existe-em-lugar-nenhum-xyz/stac/collections")
    assert r.status_code == 401


def test_filtro_cql2_com_colecao_de_b_nao_vaza(cenario):
    """Teste cruzado escrito na entrega (não veio do Kimi): o adversário do item manda `collections`
    vazio/próprio e tenta reabrir a coleção de B por dentro do FILTRO CQL2 (`filter`/`filter-lang`), que
    é escrito direto em `saida["filter"]` por `pgstac.parametros_busca` sem passar pela interseção de
    `collections_do_tenant`. Se o pgstac tratasse `filter` como alternativa a `collections` (em vez de um
    predicado ANDADO por cima da lista já restrita), isto vazaria o item de B para o token de A."""
    c, ta = cenario["cliente"], cenario["ta"]
    filtro_cql2 = {"op": "=", "args": [{"property": "collection"}, cenario["colecao_b"]]}

    r = c.post(f"/svc/{ta}/stac/search", json={"filter": filtro_cql2, "filter-lang": "cql2-json"})
    assert r.status_code == 200, r.text
    assert r.json()["features"] == [], r.json()

    r2 = c.get(
        f"/svc/{ta}/stac/search",
        params={"filter": __import__("json").dumps(filtro_cql2), "filter-lang": "cql2-json"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["features"] == [], r2.json()

    # mesma tentativa, agora filtrando pelo id do item de B em vez da coleção
    filtro_por_id = {"op": "=", "args": [{"property": "id"}, "item-b-1"]}
    r3 = c.post(f"/svc/{ta}/stac/search", json={"filter": filtro_por_id, "filter-lang": "cql2-json"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["features"] == [], r3.json()


def test_collections_e_ids_de_b_juntos_no_mesmo_pedido_nao_vazam(cenario):
    """Segundo teste cruzado escrito na entrega: A pede a própria coleção E a de B na mesma lista
    `collections`, junto com o `id` exato do item de B em `ids` — o pedido mistura o que é seu com o
    que não é, exatamente o formato que um cliente GIS real (QGIS/ArcGIS) montaria clicando em dois
    catálogos ao mesmo tempo por engano."""
    c, ta = cenario["cliente"], cenario["ta"]
    r = c.post(
        f"/svc/{ta}/stac/search",
        json={"collections": [cenario["colecao_a"], cenario["colecao_b"]], "ids": ["item-a-1", "item-b-1"]},
    )
    assert r.status_code == 200, r.text
    ids = [f["id"] for f in r.json()["features"]]
    colecoes = [f["collection"] for f in r.json()["features"]]
    assert "item-b-1" not in ids
    assert cenario["colecao_b"] not in colecoes
    assert ids == ["item-a-1"]
