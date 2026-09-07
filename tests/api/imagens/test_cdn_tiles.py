"""Portão do item L7-26-cdn-tiles, a parte que se mede EM PROCESSO (TestClient): os cabeçalhos que a
CDN precisa ver para guardar o ladrilho para sempre, e a prova de que a rota de API/app nunca carrega
esse cabeçalho. O mecanismo de cache fim-a-fim (MISS/HIT, purge por prefixo, o relógio de revogação) é
medido com sockets de verdade por `scripts/prova_cdn.py` — os dois se completam, não se repetem, na
mesma lógica que já separa `test_tiles_token.py` de `scripts/bench_tiles.py` para o item L1-02."""

import pytest

Z, X, Y = 12, 1503, 2230  # ladrilho que cobre o raster de teste (Brasília), mesmo do L1-02


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "cdn")


@pytest.fixture(scope="module")
def token_tiles(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-cdn-tiles", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_tiles_b(sessao_b):
    r = sessao_b.post("/api/tokens", json={"nome": "zt-cdn-tiles-b", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


def _sha_atual(tenant_id, item):
    from app import db

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT sha256 FROM plat.raster_item WHERE tenant_id = %s AND item_id = %s", (tenant_id, item))
        return cur.fetchone()["sha256"]


# ---------------------------------------------------------------- cláusula 1/5: cabeçalho imutável
def test_ladrilho_versionado_tem_cache_control_imutavel(token_tiles, raster_demo, tenant_id_a):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    versao = _sha_atual(tenant_id_a, item)[:12]
    r = c.get(f"/svc/{tok}/raster/{item}@{versao}/{Z}/{X}/{Y}.png")
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["etag"].strip('"') == _sha_atual(tenant_id_a, item)


def test_ladrilho_sem_versao_continua_com_cache_curto(token_tiles, raster_demo):
    """A rota SEM `@versao` (a de sempre, item L1-02) não vira imutável — só quem sabe o sha256 do
    momento ganha o cache de 1 ano; o endereço "solto" continua podendo mudar de conteúdo."""
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=300"
    assert "immutable" not in r.headers["cache-control"]


def test_versao_errada_e_404_sem_ler_o_pixel(token_tiles, raster_demo):
    """Uma versão que não bate com o sha256 vigente nunca pode devolver 200: senão o endereço
    "imutável" de uma versão velha passaria a servir o pixel ATUAL — o cliente que confiou no cache de
    1 ano veria dado de outro raster sob o mesmo endereço, o oposto do que a imutabilidade promete."""
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}@000000000000/{Z}/{X}/{Y}.png")
    assert r.status_code == 404 and r.json()["erro"] == "versao_inexistente"


def test_versao_de_item_de_outro_inquilino_e_403_nunca_404(token_tiles_b, raster_demo, tenant_id_a):
    """Achado desta bancada: sem a ordem certa dentro de `_servir`, um token de outro inquilino pedindo
    `<item-alheio>@<versao>` recebia 404 (versão inexistente) em vez de 403 — o que revela, pela
    DIFERENÇA de código, que aquele item existe e tem aquele sha256 em algum inquilino. A regra do
    módulo (docstring de rotas_tiles.py) é: 403 sempre, nunca a distinção "não existe" x "é de outro"."""
    c, tok_b, item_de_a = _cliente(), token_tiles_b["token"], raster_demo["item_id"]
    versao = _sha_atual(tenant_id_a, item_de_a)[:12]
    r = c.get(f"/svc/{tok_b}/raster/{item_de_a}@{versao}/{Z}/{X}/{Y}.png")
    assert r.status_code == 403 and r.json()["erro"] == "item_indisponivel"


def test_tilejson_ja_entrega_o_endereco_versionado(token_tiles, raster_demo):
    """O contrato do item: o cliente de mapa nunca precisa saber que "versão" existe — ele só segue a
    URL que o TileJSON deu, e essa URL já é a elegível ao cache de 1 ano."""
    from urllib.parse import urlsplit

    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    tj = c.get(f"/svc/{tok}/raster/{item}/tilejson.json").json()
    assert f"/svc/{tok}/raster/{item}@" in tj["tiles"][0]
    modelo = tj["tiles"][0].format(z=Z, x=X, y=Y)
    caminho = urlsplit(modelo).path
    r = c.get(caminho)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


# ---------------------------------------------------------------- cláusula 4: API/app nunca tem cache de CDN
@pytest.mark.parametrize("caminho", [
    "/api/tiles/leituras",
])
def test_rota_de_api_nunca_tem_cache_control_de_cdn(sessao_a, caminho):
    r = sessao_a.get(caminho)
    assert r.status_code == 200, r.text
    cc = r.headers.get("cache-control", "")
    assert "max-age=31536000" not in cc and "immutable" not in cc
    assert "no-store" in cc


def test_rotas_nao_tile_do_svc_tambem_nunca_tem_cache_de_cdn(token_tiles, raster_demo):
    """`tilejson.json`, `info.json` e o GetCapabilities do WMTS vivem sob `/svc/...` mas NÃO são
    ladrilho: o mock de CDN (`scripts/cdn_simulada.py`) as deixa passar (BYPASS) porque, numa conta
    real, o hostname `tiles-<x>` só teria Cache Rule no PREFIXO do ladrilho — aqui confere-se a parte
    que independe da conta real: a aplicação nunca marca essas respostas como cacheáveis por 1 ano."""
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    for caminho in (f"/svc/{tok}/raster/{item}/tilejson.json", f"/svc/{tok}/raster/{item}/info.json"):
        r = c.get(caminho)
        assert r.status_code == 200, (caminho, r.text)
        assert r.headers["cache-control"] == "no-store, must-revalidate"


# ---------------------------------------------------------------- mock de CDN: escopo do cache (unidade)
def test_mock_de_cdn_so_cacheia_ladrilho_xyz_e_gettile():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from cdn_simulada import _e_ladrilho

    tok, item = "plat_abc123", "0f1e2d3c-0000-0000-0000-000000000000@a1b2c3d4e5f6"
    assert _e_ladrilho(f"/svc/{tok}/raster/{item}/12/1503/2230.png", "")
    assert _e_ladrilho(f"/svc/{tok}/raster/{item}/12/1503/2230", "")
    assert _e_ladrilho(f"/svc/{tok}/mosaico/1-imagens/12/1503/2230", "")
    assert _e_ladrilho(f"/svc/{tok}/raster/{item}/wmts", "SERVICE=WMTS&REQUEST=GetTile&TILEMATRIX=12")
    assert not _e_ladrilho(f"/svc/{tok}/raster/{item}/tilejson.json", "")
    assert not _e_ladrilho(f"/svc/{tok}/raster/{item}/info.json", "")
    assert not _e_ladrilho(f"/svc/{tok}/raster/{item}/wmts", "SERVICE=WMTS&REQUEST=GetCapabilities")
    assert not _e_ladrilho("/api/tiles/leituras", "")


def test_mock_de_cdn_purga_por_prefixo_de_caminho():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from cdn_simulada import Cache

    cache = Cache()
    cache.guardar("/svc/tok1/raster/item1/12/1/1.png", {"status": 200, "headers": {}, "body": b"a"})
    cache.guardar("/svc/tok1/raster/item1/12/1/2.png", {"status": 200, "headers": {}, "body": b"b"})
    cache.guardar("/svc/tok2/raster/item1/12/1/1.png", {"status": 200, "headers": {}, "body": b"c"})
    removidos = cache.purgar_prefixos(["/svc/tok1/"])
    assert removidos == 2
    assert cache.obter("/svc/tok1/raster/item1/12/1/1.png") is None
    assert cache.obter("/svc/tok2/raster/item1/12/1/1.png") is not None


def test_mock_de_cdn_nao_colide_renderizacoes_diferentes_do_mesmo_ladrilho():
    """Achado corrigido nesta bancada (docs/CDN.md, ADR 20260907T1522 §2): a hipótese original pedia
    chave de cache SEM query string, o que fazia RGB e NDVI do MESMO z/x/y colidirem no mesmo slot —
    um cliente recebia a imagem renderizada para o outro. A chave certa é caminho + query completa."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from cdn_simulada import Cache

    cache = Cache()
    base = "/svc/tok/raster/item@abc123/12/1/1.png"
    cache.guardar(f"{base}?bandas=3,2,1", {"status": 200, "headers": {}, "body": b"rgb"})
    cache.guardar(f"{base}?expressao=ndvi", {"status": 200, "headers": {}, "body": b"ndvi"})
    assert cache.obter(f"{base}?bandas=3,2,1")["body"] == b"rgb"
    assert cache.obter(f"{base}?expressao=ndvi")["body"] == b"ndvi"
    assert cache.obter(base) is None  # uma 3ª variação (sem query) não pega nem uma nem outra
