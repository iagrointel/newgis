"""Portão do item L1-07-mosaico-por-colecao-e-pegadas, cláusula por cláusula (ver
laco/estado.json e docs/adr/20260910T2330-mosaico-busca-registrada.md).

Semeia uma GRADE de 6 quadrantes ADJACENTES e SINTÉTICOS (`apoio_mosaico.semear_grade`, mesma
disciplina de dado sintético de `apoio_raster.py` — nenhum dado de cliente na suíte) e mede: registro
idempotente, listagem/detalhe, ladrilho na JUNTA de dois quadrantes com pixel dos DOIS lados
(compositor real, `tiles.ladrilho_composto`, não "escolhe uma cena e deixa o resto em branco"),
pegadas com a contagem certa e popup-worthy (data/nuvem), isolamento cruzado por inquilino e escopo
de token FINO (mosaico sim, item avulso não)."""

from __future__ import annotations

import pytest

from tests.api.conftest import PREFIXO_TESTE

Z_JUNTA_PADRAO = 13


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def grade_a(tenant_id_a):
    from tests.api.imagens.apoio_mosaico import apagar_grade, semear_grade

    grade = semear_grade(tenant_id_a, "demo", n_col=3, n_lin=2)
    yield grade
    apagar_grade(tenant_id_a, grade)


@pytest.fixture(scope="module")
def grade_b(tenant_id_b):
    from tests.api.imagens.apoio_mosaico import apagar_grade, semear_grade

    grade = semear_grade(tenant_id_b, "demo2", n_col=1, n_lin=1)
    yield grade
    apagar_grade(tenant_id_b, grade)


def _tile_da_junta(z: int = Z_JUNTA_PADRAO) -> tuple[int, int, int]:
    """Ladrilho WebMercator que cruza a fronteira entre o quadrante (col=0,lin=0) e o (col=1,lin=0) da
    grade — computado de verdade a partir da geometria da grade (`apoio_mosaico`), nunca chutado: pega
    o ponto médio da aresta compartilhada em 3857, converte para 4326 e localiza o tile em `tiles.TMS`,
    subindo o zoom até a fronteira cair fora das bordas do tile (para o ladrilho mostrar os DOIS lados,
    não só um pixel de canto)."""
    import pyproj

    from app.imagens import tiles
    from tests.api.imagens.apoio_mosaico import CANTO_LAT, CANTO_LON, LADO_PX, RESOLUCAO

    lado_m = LADO_PX * RESOLUCAO
    x0, y0 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(
        CANTO_LON, CANTO_LAT)
    fronteira_x = x0 + lado_m  # aresta entre col=0 e col=1
    meio_y = y0 - lado_m / 2
    lon, lat = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(
        fronteira_x, meio_y)
    for z in range(10, 17):
        t = tiles.TMS.tile(lon, lat, z)
        oeste, sul, leste, norte = tiles.TMS.bounds(t)
        frac = (lon - oeste) / (leste - oeste)
        if 0.25 <= frac <= 0.75:  # a fronteira cai no miolo do tile — os dois lados ficam com área de sobra
            return z, t.x, t.y
    t = tiles.TMS.tile(lon, lat, 14)
    return 14, t.x, t.y


# ---------------------------------------------------------------- cláusula: registro é busca STAC + idempotência
def test_registrar_devolve_uuid_e_e_idempotente(token_stac_a, grade_a):
    c, tok = _cliente(), token_stac_a["token"]
    corpo = {"nome": f"{PREFIXO_TESTE} grade de teste", "collections": [grade_a["colecao"]]}
    r1 = c.post(f"/svc/{tok}/stac/mosaicos", json=corpo)
    assert r1.status_code == 201, r1.text
    m1 = r1.json()
    import uuid as _uuid
    _uuid.UUID(m1["id"])  # o id é um uuid de verdade, não o hash md5 do pgstac
    assert m1["colecoes"] == [grade_a["colecao"]]

    # a MESMA busca, registrada de novo com um NOME DIFERENTE: o nome não entra no hash (ADR §2), então
    # o id devolvido tem de ser o MESMO — "a mesma busca registrada duas vezes devolve o mesmo id".
    r2 = c.post(f"/svc/{tok}/stac/mosaicos", json={**corpo, "nome": f"{PREFIXO_TESTE} outro nome"})
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] == m1["id"]
    assert r2.json()["nome"] == m1["nome"]  # o nome do PRIMEIRO registro fica

    # critério DIFERENTE (bbox) tem de dar um id DIFERENTE — a idempotência não é "sempre a mesma coisa"
    r3 = c.post(f"/svc/{tok}/stac/mosaicos", json={**corpo, "bbox": [-48, -16, -47, -15]})
    assert r3.status_code == 201, r3.text
    assert r3.json()["id"] != m1["id"]
    c.delete(f"/svc/{tok}/stac/mosaicos/{r3.json()['id']}")
    # `m1` (sem bbox/limite) NÃO é apagado aqui: `limite` não entra no hash (só afeta como o TILE é
    # servido, nunca o registro), então `m1` e `mosaico_a` (abaixo, mesmas coleções, só `limite`
    # diferente) são a MESMA linha — quem apaga é a teardown de `mosaico_a`, módulo inteiro depois.


def test_colecao_de_outro_inquilino_e_filtrada_fora_no_registro(token_stac_a, grade_b):
    """Adversário: pedir a coleção do INQUILINO B no registro do token do inquilino A. `parametros_busca`
    (app/imagens/pgstac.py) restringe SEMPRE à interseção com as coleções do próprio inquilino — sem
    nenhuma coleção sobrando, o registro é recusado (nunca aceita "coleção" alheia calada)."""
    c, tok = _cliente(), token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/mosaicos", json={"nome": "x", "collections": [grade_b["colecao"]]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "colecoes_inexistentes"


def test_filtro_cql2_malformado_nao_vira_500(token_stac_a, grade_a):
    c, tok = _cliente(), token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/mosaicos", json={
        "nome": "x", "collections": [grade_a["colecao"]],
        "filter": {"op": "isto-nao-e-um-operador-cql2", "args": [{"property": "datetime"}, "2020"]},
    })
    assert r.status_code == 422, r.text  # nunca 500 por entrada do cliente


# ---------------------------------------------------------------- cláusula: listar/detalhe
@pytest.fixture(scope="module")
def mosaico_a(token_stac_a, grade_a):
    c, tok = _cliente(), token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/mosaicos", json={
        "nome": f"{PREFIXO_TESTE} grade principal", "collections": [grade_a["colecao"]], "limite": 12,
    })
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    c.delete(f"/svc/{tok}/stac/mosaicos/{dados['id']}")


def test_listar_mostra_o_mosaico_registrado(token_stac_a, mosaico_a):
    c, tok = _cliente(), token_stac_a["token"]
    r = c.get(f"/svc/{tok}/stac/mosaicos")
    assert r.status_code == 200, r.text
    ids = [m["id"] for m in r.json()["mosaicos"]]
    assert mosaico_a["id"] in ids


def test_detalhe_do_mosaico(token_stac_a, mosaico_a):
    c, tok = _cliente(), token_stac_a["token"]
    r = c.get(f"/svc/{tok}/stac/mosaicos/{mosaico_a['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == mosaico_a["nome"]


def test_detalhe_de_mosaico_inexistente_404(token_stac_a):
    c, tok = _cliente(), token_stac_a["token"]
    r = c.get(f"/svc/{tok}/stac/mosaicos/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------- cláusula: ladrilho da JUNTA — pixel dos dois lados
@pytest.fixture(scope="module")
def token_tiles_mosaico_a(sessao_a, mosaico_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tiles-mosaico",
                                           "escopos": [f"tiles:ler:{mosaico_a['id']}"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def test_tile_da_junta_tem_pixel_dos_dois_lados(token_tiles_mosaico_a, mosaico_a):
    import io

    from PIL import Image

    z, x, y = _tile_da_junta()
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/{z}/{x}/{y}.png")
    assert r.status_code == 200, r.text
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # X-Plat-Cenas-Candidatas > 1: a MEDIÇÃO de que mais de uma cena foi lida para este ladrilho (não
    # é "escolheu uma cena inteira") — a prova de verdade (metade esquerda != metade direita) é feita
    # na instância viva pelo script `scratchpad/prova_l107_mosaico.py` (relatório do turno).
    assert int(r.headers.get("x-plat-cenas-candidatas", "0")) >= 2, dict(r.headers)
    img = Image.open(io.BytesIO(r.content)).convert("L")
    largura, altura = img.size
    esquerda = list(img.crop((0, altura // 2 - 5, largura // 4, altura // 2 + 5)).getdata())
    direita = list(img.crop((3 * largura // 4, altura // 2 - 5, largura, altura // 2 + 5)).getdata())
    media_esq = sum(esquerda) / len(esquerda)
    media_dir = sum(direita) / len(direita)
    # os dois quadrantes têm DN constante e DIFERENTE (100 e 140): depois do realce por min/max do
    # próprio ladrilho as duas metades ficam em extremos opostos (perto de 0 e perto de 255) — a
    # medição que prova pixel real dos dois lados, não um artefato de compressão.
    assert abs(media_esq - media_dir) > 80, (media_esq, media_dir)


def test_tile_do_mosaico_fora_da_grade_devolve_204(token_tiles_mosaico_a, mosaico_a):
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/2/0/0.png")
    assert r.status_code == 204 and not r.content


def test_tilejson_e_wmts_do_mosaico(token_tiles_mosaico_a, mosaico_a):
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    tj = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/tilejson.json")
    assert tj.status_code == 200, tj.text
    corpo = tj.json()
    assert corpo["tilejson"] == "3.0.0"
    assert f"/svc/{tok}/mosaico/{mosaico_a['id']}/" in corpo["tiles"][0]
    assert len(corpo["bounds"]) == 4

    cap = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/wmts/1.0.0/WMTSCapabilities.xml")
    assert cap.status_code == 200 and cap.headers["content-type"].startswith("application/xml")
    assert mosaico_a["id"] in cap.text


# ---------------------------------------------------------------- cláusula: pegadas com data/nuvem
def test_pegadas_tem_a_contagem_certa_com_data_e_nuvem(token_tiles_mosaico_a, mosaico_a, grade_a):
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/pegadas")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/geo+json")
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == len(grade_a["itens"])  # a contagem CERTA — nem uma cena a mais/menos
    ids_grade = {it["item_id"] for it in grade_a["itens"]}
    for f in fc["features"]:
        assert f["id"] in ids_grade
        assert f["geometry"]["type"] == "Polygon"
        assert f["properties"]["datetime"] is not None  # o que o popup mostra
        assert f["properties"]["eo:cloud_cover"] is not None


# ---------------------------------------------------------------- cláusula: isolamento por inquilino
@pytest.fixture(scope="module")
def token_tiles_b(sessao_b):
    r = sessao_b.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tiles-mosaico-b", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


def test_mosaico_de_outro_inquilino_e_invisivel(token_stac_b, mosaico_a):
    c, tok_b = _cliente(), token_stac_b["token"]
    assert c.get(f"/svc/{tok_b}/stac/mosaicos/{mosaico_a['id']}").status_code == 404


def test_tile_tilejson_e_pegadas_de_outro_inquilino_dao_403(token_tiles_b, mosaico_a):
    c, tok_b = _cliente(), token_tiles_b["token"]
    z, x, y = _tile_da_junta()
    assert c.get(f"/svc/{tok_b}/mosaico/{mosaico_a['id']}/{z}/{x}/{y}.png").status_code == 403
    assert c.get(f"/svc/{tok_b}/mosaico/{mosaico_a['id']}/tilejson.json").status_code == 403
    assert c.get(f"/svc/{tok_b}/mosaico/{mosaico_a['id']}/pegadas").status_code == 403


# ---------------------------------------------------------------- cláusula: escopo FINO (mosaico sim, item avulso não)
def test_token_com_escopo_so_no_mosaico_nao_ve_item_avulso(token_tiles_mosaico_a, mosaico_a, grade_a):
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    z, x, y = _tile_da_junta()
    ok = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/{z}/{x}/{y}.png")
    assert ok.status_code == 200, ok.text

    item_avulso = grade_a["itens"][0]["item_id"]
    recusado = c.get(f"/svc/{tok}/raster/{item_avulso}/{z}/{x}/{y}.png")
    assert recusado.status_code == 403, recusado.text
    assert recusado.json()["erro"] == "escopo_insuficiente"
