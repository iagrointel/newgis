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


@pytest.fixture(scope="session", autouse=True)
def limpeza_de_residuos():
    """As fixtures deste módulo removem seus próprios recursos. Não varrer o prefixo zt de
    outras rodadas concorrentes nem inicializar o 2FA do superadmin para testar mosaicos."""
    yield


@pytest.fixture(scope="session", autouse=True)
def trincos_em_tmp():
    """A execução deste arquivo não grava arquivos de apoio nem credenciais no repositório."""
    import contextlib
    import fcntl
    from pathlib import Path

    from tests.api import conftest as apoio

    @contextlib.contextmanager
    def trinco(nome):
        with (Path("/tmp") / f"plat-mosaico-{nome}").open("w") as arquivo:
            fcntl.flock(arquivo, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(arquivo, fcntl.LOCK_UN)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(apoio, "trinco", trinco)
        yield


@pytest.fixture(scope="session")
def sessao_plat(cred, trincos_em_tmp):
    from tests.api.conftest import entrar, novo_cliente, totp_guardado

    cliente = novo_cliente()
    login, senha = cred["plataforma"]
    resposta = entrar(cliente, "plataforma", login, senha, totp_guardado("plataforma"))
    assert resposta.status_code == 200, "login da plataforma falhou"
    assert "configurar_2fa" not in resposta.json()["usuario"]["pendencias"], "2FA precisa estar configurado"
    return cliente


@pytest.fixture(scope="session")
def inquilinos_mosaico(sessao_plat):
    from tests.api import conftest as apoio
    from tests.api.conftest import InquilinoTemporario

    criados = []
    try:
        # Outras rodadas varrem zt-* globalmente. Estes inquilinos têm teardown próprio e
        # prefixo exclusivo para não perder sessão/objetos durante testes concorrentes.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(apoio, "PREFIXO_TESTE", "l108")
            for _ in range(2):
                criados.append(InquilinoTemporario(sessao_plat))
        yield criados
    finally:
        for inquilino in reversed(criados):
            inquilino.apagar()


@pytest.fixture(scope="session")
def sessao_a(inquilinos_mosaico):
    return inquilinos_mosaico[0].admin


@pytest.fixture(scope="session")
def sessao_b(inquilinos_mosaico):
    return inquilinos_mosaico[1].admin


@pytest.fixture(scope="session")
def tenant_id_a(inquilinos_mosaico):
    return inquilinos_mosaico[0].id


@pytest.fixture(scope="session")
def tenant_id_b(inquilinos_mosaico):
    return inquilinos_mosaico[1].id


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def grade_a(tenant_id_a, inquilinos_mosaico):
    from tests.api.imagens.apoio_mosaico import apagar_grade, semear_grade

    grade = semear_grade(tenant_id_a, inquilinos_mosaico[0].slug, n_col=3, n_lin=2)
    yield grade
    apagar_grade(tenant_id_a, grade)


@pytest.fixture(scope="module")
def grade_b(tenant_id_b, inquilinos_mosaico):
    from tests.api.imagens.apoio_mosaico import apagar_grade, semear_grade

    grade = semear_grade(tenant_id_b, inquilinos_mosaico[1].slug, n_col=1, n_lin=1)
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
    # L1-08: limite também participa da identidade; não deixa o primeiro registro ocultar a regra.
    c.delete(f"/svc/{tok}/stac/mosaicos/{m1['id']}")


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


def test_filtro_cql2_semanticamente_quebrado_e_recusado_NO_REGISTRO(token_stac_a, grade_a):
    """Achado do adversário independente (10/09): `filter` como string crua ou `args` fora de lista é
    JSON sintaticamente válido, `pgstac.search_query` (só calcula hash/where) não recusava, e o
    registro dava 201 — o mosaico só quebrava depois, ao servir o primeiro tile/pegada. `registrar()`
    agora roda uma busca de teste (limit=1) na mesma transação: registro malformado nunca mais devolve
    201 "de mentira"."""
    c, tok = _cliente(), token_stac_a["token"]
    for filtro_ruim in (
        "isto não é um filtro",
        {"op": "=", "args": "nao é uma lista"},
        [{"op": "=", "args": [1, 1]}],
    ):
        r = c.post(f"/svc/{tok}/stac/mosaicos", json={
            "nome": "x", "collections": [grade_a["colecao"]], "filter": filtro_ruim,
        })
        assert r.status_code == 422, (filtro_ruim, r.status_code, r.text)


def test_collections_com_item_nao_texto_nunca_vira_500(token_stac_a, grade_a):
    """Achado do adversário independente (10/09): `collections: [123, null, {}]` batia em
    `[c for c in collections if c in permitidas]` (app/imagens/pgstac.py) com `TypeError: unhashable
    type` cru (500) — a validação de tipo agora vem ANTES dessa comparação."""
    c, tok = _cliente(), token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/mosaicos", json={
        "nome": "x", "collections": [123, None, {}],
    })
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "collections_invalido"


def test_z_x_y_absurdo_no_tile_do_mosaico_nunca_vira_500(token_tiles_mosaico_a, mosaico_a):
    """Achado do adversário independente (10/09): `z` negativo ou muito grande fazia `morecantile`
    (`_bbox_do_tile`) estourar `OverflowError` cru (500), byte a byte igual a `Internal Server Error`
    sem envelope de erro — em vez de 422. Cobre as duas rotas (com e sem extensão) e os dois lados
    (z fora da faixa, x/y fora da grade do zoom pedido)."""
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    for z, x, y in ((-1, 0, 0), (10000, 0, 0), (5, -1, 0), (5, 10_000_000, 0)):
        r = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/{z}/{x}/{y}.png")
        assert r.status_code == 422, (z, x, y, r.status_code, r.text)
        assert r.json()["erro"] == "tile_invalido", (z, x, y, r.text)


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


@pytest.mark.parametrize("formato,ext", [("image/png", "png"), ("image/jpeg", "jpg"), ("image/webp", "webp")])
def test_wmts_gettile_equivale_ao_xyz(token_tiles_mosaico_a, mosaico_a, formato, ext):
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    base = f"/svc/{tok}/mosaico/{mosaico_a['id']}"
    z, x, y = _tile_da_junta()
    wmts = c.get(f"{base}/wmts", params={
        "SERVICE": "WMTS", "REQUEST": "GetTile", "TILEMATRIX": f"WebMercatorQuad:{z}",
        "TILEROW": y, "TILECOL": x, "FORMAT": formato,
    })
    xyz = c.get(f"{base}/{z}/{x}/{y}.{ext}")
    sem_ext = c.get(f"{base}/{z}/{x}/{y}", params={"formato": ext})
    assert wmts.status_code == xyz.status_code == sem_ext.status_code == 200
    assert wmts.headers["content-type"] == formato
    assert wmts.content == xyz.content == sem_ext.content


@pytest.mark.parametrize("matriz", ["invalida", "WebMercatorQuad:abc", "-1", "10000"])
def test_wmts_matriz_invalida_devolve_422(token_tiles_mosaico_a, mosaico_a, matriz):
    c, tok = _cliente(), token_tiles_mosaico_a["token"]
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_a['id']}/wmts", params={
        "REQUEST": "GetTile", "TILEMATRIX": matriz, "TILEROW": 0, "TILECOL": 0,
    })
    assert r.status_code == 422
    assert r.json()["erro"] == "tile_invalido"


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


def test_pegadas_paginadas_preservam_geometria_do_catalogo(tenant_id_a, mosaico_a, grade_a):
    from app import db
    from app.imagens import mosaico as mo
    from app.imagens import pgstac as ps

    with db.db(db.Contexto(tenant_id=tenant_id_a, usuario_id=0, login="teste")) as cur:
        linha = mo.obter(cur, tenant_id_a, mosaico_a["id"])
        fc = mo.pegadas(cur, linha, limite=2)
        assert len(fc["features"]) == len(grade_a["itens"])
        assert {f["id"] for f in fc["features"]} == {it["item_id"] for it in grade_a["itens"]}
        for f in fc["features"]:
            stac = ps.item_obter(cur, tenant_id_a, grade_a["colecao"], f["id"])
            assert f["geometry"] == stac["geometry"]
            assert f["properties"]["datetime"] == stac["properties"]["datetime"]
            assert f["properties"]["eo:cloud_cover"] == stac["properties"]["eo:cloud_cover"]


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


# ---------------------------------------------------------------- item irmão L1-08 (mínimo): regras de seleção
# Valores ESCOLHIDOS para distinguir os 4 métodos entre si: item 0 (mais recente) = 20, item 1 = 90,
# item 2 (mais antigo) = 10 -> mediana=20, média=40, máxima=90, mínima=10 — todos diferentes.
VALORES_SOBREPOSTAS = [20, 90, 10]


def _tile_central(z: int = 15) -> tuple[int, int, int]:
    """Ladrilho que cobre o CENTRO da célula sobreposta (mesmo canto/lado de `apoio_mosaico`, sem
    deslocamento de grade — as 3 cenas de `semear_sobrepostas` estão todas no mesmo lugar). `z=15`
    (tile ≈1,2 km) fica bem DENTRO do quadrante de 4 km — em z=12 (tile ≈9,8 km) o ladrilho pega muito
    mais área que a célula tem dado, e a maior parte vem mascarada/preta, o que quase zerava a média."""
    import pyproj

    from app.imagens import tiles
    from tests.api.imagens.apoio_mosaico import CANTO_LAT, CANTO_LON, LADO_PX, RESOLUCAO

    lado_m = LADO_PX * RESOLUCAO
    x0, y0 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(
        CANTO_LON, CANTO_LAT)
    centro_x, centro_y = x0 + lado_m / 2, y0 - lado_m / 2
    lon, lat = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(
        centro_x, centro_y)
    t = tiles.TMS.tile(lon, lat, z)
    return z, t.x, t.y


@pytest.fixture(scope="module")
def sobrepostas_a(tenant_id_a, inquilinos_mosaico):
    from tests.api.imagens.apoio_mosaico import apagar_grade, semear_sobrepostas

    dados = semear_sobrepostas(tenant_id_a, inquilinos_mosaico[0].slug, VALORES_SOBREPOSTAS)
    yield dados
    apagar_grade(tenant_id_a, dados)


@pytest.fixture(scope="module")
def mosaico_sobreposto_a(token_stac_a, sobrepostas_a):
    c, tok = _cliente(), token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/mosaicos",
              json={"nome": f"{PREFIXO_TESTE} sobrepostas L1-08", "collections": [sobrepostas_a["colecao"]]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    c.delete(f"/svc/{tok}/stac/mosaicos/{dados['id']}")


@pytest.fixture(scope="module")
def token_tiles_sobreposto_a(sessao_a, mosaico_sobreposto_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tiles-sobreposto",
                                           "escopos": [f"tiles:ler:{mosaico_sobreposto_a['id']}"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def _pixel_medio(conteudo: bytes) -> float:
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(conteudo)).convert("L")
    dados = img.getdata()
    return sum(dados) / len(dados)


@pytest.mark.parametrize("metodo,valor_esperado", [
    ("mediana", 20), ("media", 40), ("maxima", 90), ("minima", 10),
])
def test_metodo_de_composicao_do_l1_08_minimo(token_tiles_sobreposto_a, mosaico_sobreposto_a, metodo, valor_esperado):
    """Item irmão L1-08 (mínimo, este turno): 3 cenas sintéticas SOBREPOSTAS de valores 20/90/10 — com
    `faixa=0,100` explícita (sem isso o realce por min/máx do próprio ladrilho apaga o sinal, já que
    todo pixel do tile tem o MESMO valor composto), `mediana` devolve 20, `media` 40, `máxima` 90,
    `mínima` 10 — a medição exata que o portão do L1-08 pede, não só "parece diferente"."""
    c, tok = _cliente(), token_tiles_sobreposto_a["token"]
    z, x, y = _tile_central()
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_sobreposto_a['id']}/{z}/{x}/{y}.png",
             params={"metodo": metodo, "faixa": "0,100"})
    assert r.status_code == 200, r.text
    pixel = _pixel_medio(r.content)
    esperado_pixel = round(valor_esperado / 100 * 255)
    assert abs(pixel - esperado_pixel) <= 5, (metodo, pixel, esperado_pixel)


def test_metodo_desconhecido_e_recusado_nunca_500(token_tiles_sobreposto_a, mosaico_sobreposto_a):
    c, tok = _cliente(), token_tiles_sobreposto_a["token"]
    z, x, y = _tile_central()
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_sobreposto_a['id']}/{z}/{x}/{y}.png",
             params={"metodo": "nao-existe"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "ladrilho_invalido"


def test_metodo_padrao_e_primeira_cena_mais_recente(token_tiles_sobreposto_a, mosaico_sobreposto_a):
    """Sem `metodo=`, o padrão continua sendo `primeira` (item L1-07): a cena MAIS RECENTE (valor 20,
    índice 0 de VALORES_SOBREPOSTAS) vence — mesma regra de antes do L1-08, comportamento não mudou."""
    c, tok = _cliente(), token_tiles_sobreposto_a["token"]
    z, x, y = _tile_central()
    r = c.get(f"/svc/{tok}/mosaico/{mosaico_sobreposto_a['id']}/{z}/{x}/{y}.png", params={"faixa": "0,100"})
    assert r.status_code == 200, r.text
    pixel = _pixel_medio(r.content)
    assert abs(pixel - round(20 / 100 * 255)) <= 5, pixel


@pytest.fixture(scope="module")
def cenas_regras(tenant_id_a, inquilinos_mosaico):
    from tests.api.imagens.apoio_mosaico import apagar_grade, semear_sobrepostas

    cenas = semear_sobrepostas(tenant_id_a, inquilinos_mosaico[0].slug, [10, 20, 30],
                              colecao_slug="mosaicoregras")
    yield cenas
    apagar_grade(tenant_id_a, cenas)


@pytest.fixture(scope="module")
def token_regras(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-regras",
                                          "escopos": ["imagens:escrever", "imagens:ler"]})
    assert r.status_code == 201
    dados = r.json()
    yield dados["token"]
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture
def registrar_regra(token_regras, cenas_regras):
    cliente = _cliente()
    ids = set()

    def registrar(**regra):
        resposta = cliente.post(f"/svc/{token_regras}/stac/mosaicos", json={
            "nome": "Regra de pixel sintético", "collections": [cenas_regras["colecao"]], **regra,
        })
        assert resposta.status_code == 201, resposta.status_code
        mosaico = resposta.json()
        ids.add(mosaico["id"])
        detalhe = cliente.get(f"/svc/{token_regras}/stac/mosaicos/{mosaico['id']}")
        assert detalhe.status_code == 200
        assert detalhe.json()["criterios"] == mosaico["criterios"]
        for chave, valor in regra.items():
            assert mosaico["criterios"][chave] == valor
        return mosaico

    yield registrar
    for mid in ids:
        cliente.delete(f"/svc/{token_regras}/stac/mosaicos/{mid}")


def _pixel_da_regra(token, mosaico, **params):
    import io

    import numpy as np
    from PIL import Image

    z, x, y = _tile_central()
    resposta = _cliente().get(f"/svc/{token}/mosaico/{mosaico['id']}/{z}/{x}/{y}.png",
                              params={"faixa": "0,255", "bandas": "1", **params})
    assert resposta.status_code == 200, resposta.status_code
    pixels = np.asarray(Image.open(io.BytesIO(resposta.content)).convert("RGBA"))
    assert np.all(pixels[:, :, 3] == 255), "o tile deve estar integralmente coberto"
    valores = np.unique(pixels[:, :, 0])
    assert len(valores) == 1, valores
    return int(valores[0])


@pytest.mark.parametrize("campo,direcao,esperado", [
    ("datetime", "desc", 10), ("datetime", "asc", 30),
    ("eo:cloud_cover", "asc", 30), ("plat:valor_teste", "desc", 30),
])
def test_pixel_first_por_ordem_persistida(registrar_regra, token_regras, campo, direcao, esperado):
    mosaico = registrar_regra(sortby=[{"field": campo, "direction": direcao}], pixel_selection="first")
    assert _pixel_da_regra(token_regras, mosaico) == esperado


@pytest.mark.parametrize("selecao,esperado", [
    ("first", 10), ("last", 30), ("lowest", 10), ("highest", 30),
    ("mean", 20), ("median", 20), ("stdev", 8),  # sqrt(200/3) = 8,1649; PNG trunca para uint8
])
def test_pixel_selecao_persistida(registrar_regra, token_regras, selecao, esperado):
    mosaico = registrar_regra(pixel_selection=selecao)
    assert _pixel_da_regra(token_regras, mosaico) == esperado


def test_pixel_lock_persistido(registrar_regra, token_regras, cenas_regras):
    cena = cenas_regras["itens"][1]["item_id"]
    mosaico = registrar_regra(lock=cena, limite=1)
    assert _pixel_da_regra(token_regras, mosaico) == 20
    # Mesmo com override de método e limite, nenhuma cena pode preencher pixels da cena travada.
    assert _pixel_da_regra(token_regras, mosaico, metodo="highest", limite=12) == 20
    pegadas = _cliente().get(f"/svc/{token_regras}/mosaico/{mosaico['id']}/pegadas").json()
    assert [f["id"] for f in pegadas["features"]] == [cena]


def test_regras_distintas_nao_reaproveitam_composicao(registrar_regra, token_regras):
    primeira = registrar_regra(pixel_selection="first")
    mediana = registrar_regra(pixel_selection="median")
    limitada = registrar_regra(pixel_selection="median", limite=1)
    assert len({primeira["id"], mediana["id"], limitada["id"]}) == 3
    assert registrar_regra(pixel_selection="median")["id"] == mediana["id"]
    assert _pixel_da_regra(token_regras, primeira) == 10
    assert _pixel_da_regra(token_regras, mediana) == 20
    assert _pixel_da_regra(token_regras, limitada) == 10


@pytest.mark.parametrize("regra", [
    {"pixel_selection": "blend"}, {"pixel_selection": []}, {"pixel_selection": None},
    {"lock": []}, {"lock": ""}, {"lock": True}, {"limite": True},
    {"sortby": "-datetime"}, {"sortby": []}, {"sortby": [None]},
    {"sortby": [{"field": "datetime", "direction": []}]},
    {"sortby": [{"field": "datetime", "direction": "up"}]},
])
def test_regra_invalida_recusada_no_registro(token_regras, cenas_regras, regra):
    resposta = _cliente().post(f"/svc/{token_regras}/stac/mosaicos", json={
        "nome": "Inválida", "collections": [cenas_regras["colecao"]], **regra,
    })
    assert resposta.status_code == 422


def test_lock_nao_aceita_cena_alheia_ou_fora_do_filtro(token_regras, cenas_regras, grade_b):
    for lock, filtros in [
        (grade_b["itens"][0]["item_id"], {}),
        ("cena-inexistente", {}),
        (cenas_regras["itens"][1]["item_id"], {"datetime": "2000-01-01T00:00:00Z"}),
    ]:
        resposta = _cliente().post(f"/svc/{token_regras}/stac/mosaicos", json={
            "nome": "Lock indisponível", "collections": [cenas_regras["colecao"]], "lock": lock, **filtros,
        })
        assert resposta.status_code == 422
        assert resposta.json()["erro"] == "lock_indisponivel"
