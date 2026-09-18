"""Ladrilho raster servido por token de escopo POR ITEM (`tiles:ler:<uuid>`) — item L1-02-tiles-token.

`tests/api/imagens/test_tiles_token.py` prova o serviço com o escopo AMPLO (`tiles:ler`, todo o inquilino)
e a recusa ao token de OUTRO INQUILINO. O que ficava sem prova é o escopo estreito que a publicação emite
(`app/catalogo/publicacao.py` gera `tiles:ler:<uuid>` por camada) e que a hipótese do item promete: um
token amarrado a UM item serve aquele item e recusa um SEGUNDO item do MESMO inquilino, que o dono do
token enxerga perfeitamente pela sessão. Sem esse par, `cobre()` poderia ignorar o sufixo e ninguém veria.

Dois rasters no mesmo inquilino A; o token vale só para o primeiro.
"""

import pytest

from tests.api.imagens.test_tiles_token import X, Y, Z, _cliente

ITEM = "L1-02-tiles-token"


@pytest.fixture(scope="module")
def dois_rasters(tenant_id_a, sessao_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo"), semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def token_do_primeiro(sessao_a, dois_rasters):
    alvo = dois_rasters[0]["item_id"]
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles-por-item", "escopos": [f"tiles:ler:{alvo}"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    assert dados["escopos"] == [f"tiles:ler:{alvo}"], dados
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def test_token_por_item_serve_o_item_a_que_pertence(token_do_primeiro, dois_rasters):
    """Par positivo: o escopo estreito continua servindo ladrilho, TileJSON e WMTS do seu item."""
    c, tok, item = _cliente(), token_do_primeiro["token"], dois_rasters[0]["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert c.get(f"/svc/{tok}/raster/{item}/tilejson.json").status_code == 200
    assert c.get(f"/svc/{tok}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml").status_code == 200


def test_mesmo_token_da_403_no_outro_item_do_mesmo_inquilino(token_do_primeiro, dois_rasters, sessao_a):
    """Par negativo: o SEGUNDO raster é do mesmo dono e do mesmo inquilino (a sessão o lê sem problema),
    mas o token amarrado ao primeiro não o alcança — a recusa é do sufixo do escopo, não de posse."""
    c, tok = _cliente(), token_do_primeiro["token"]
    outro = dois_rasters[1]["item_id"]
    assert sessao_a.get(f"/api/itens/{outro}").status_code == 200, "o outro item não é do inquilino A"
    for url in (f"/svc/{tok}/raster/{outro}/{Z}/{X}/{Y}.png",
                f"/svc/{tok}/raster/{outro}/tilejson.json",
                f"/svc/{tok}/raster/{outro}/wmts/1.0.0/WMTSCapabilities.xml"):
        r = c.get(url)
        assert r.status_code == 403, (url, r.status_code, r.text)
        assert r.json()["erro"] == "escopo_insuficiente", (url, r.json())


def test_autorizacao_do_nginx_segue_o_mesmo_recorte_por_item(token_do_primeiro, dois_rasters):
    """A subrequisição `auth_request` é o único ponto que roda com o ladrilho já no cache do nginx (a chave
    de cache não tem o token): se ela ignorasse o sufixo, o recorte por item valeria só na primeira leitura."""
    c, tok = _cliente(), token_do_primeiro["token"]
    def autorizar(item):
        return c.get("/api/tiles/autorizar",
                     headers={"X-Plat-Token": tok, "X-Plat-Item": item, "X-Plat-Tipo": "raster"})
    assert autorizar(dois_rasters[0]["item_id"]).status_code == 204
    assert autorizar(dois_rasters[1]["item_id"]).status_code == 403


def test_escopo_por_item_de_uuid_inexistente_e_recusado_na_emissao(sessao_a):
    """O vocabulário exige item existente e legível pelo dono do token (app/catalogo/comum.py::item_legivel):
    não se emite escopo para um uuid que não é item do inquilino."""
    import uuid as _uuid

    r = sessao_a.post("/api/tokens",
                      json={"nome": "zt-tiles-item-fantasma", "escopos": [f"tiles:ler:{_uuid.uuid4()}"]})
    assert r.status_code == 422, r.text
    if r.status_code == 201:  # pragma: no cover — só para não vazar token se um dia passar
        sessao_a.delete(f"/api/tokens/{r.json()['id']}")


def test_medida_recorte_por_item(token_do_primeiro, dois_rasters, medida):
    """Medida do recorte: quantas superfícies de leitura respeitam o sufixo do escopo (as mesmas URLs,
    o item do token contra o item vizinho do MESMO inquilino)."""
    c, tok = _cliente(), token_do_primeiro["token"]
    meu, vizinho = dois_rasters[0]["item_id"], dois_rasters[1]["item_id"]
    caminhos = ("{z}/{x}/{y}.png".format(z=Z, x=X, y=Y), "tilejson.json", "wmts/1.0.0/WMTSCapabilities.xml")
    servidas = sum(1 for p in caminhos if c.get(f"/svc/{tok}/raster/{meu}/{p}").status_code == 200)
    recusadas = sum(1 for p in caminhos if c.get(f"/svc/{tok}/raster/{vizinho}/{p}").status_code == 403)
    assert servidas == len(caminhos) and recusadas == len(caminhos), (servidas, recusadas)
    medida(ITEM)(
        "recorte_por_item_do_escopo",
        {"superficies": len(caminhos), "servidas_no_item_do_token": servidas,
         "recusadas_no_item_vizinho": recusadas, "escopo": "tiles:ler:<uuid>"},
        "superfícies de leitura (XYZ, TileJSON, WMTS) por token de item",
        "pytest tests/api/imagens/test_tiles_raster_token.py -q",
    )
