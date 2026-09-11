"""Portão do item L1-02-i-ogc-api-tiles-e-maps, cláusula por cláusula (ver `laco/estado.json` e
`docs/adr/20260910T2056-ogc-api-tiles-e-maps.md`).

O que este arquivo mede em processo (TestClient): landing/conformance com as classes REALMENTE
cumpridas (nunca uma a mais — testado por ausência), `/tileMatrixSets` e a definição de
`WebMercatorQuad` batendo com o `TMS.model_dump()` de verdade, `/collections` e o detalhe da coleção,
o `tileset` (metadados + `tileMatrixSetLimits`), o ladrilho BYTE-A-BYTE igual ao XYZ equivalente (item,
mosaico registrado e mosaico ad-hoc por nome de coleção), `/map` BYTE-A-BYTE igual ao `GetMap` do WMS
no mesmo bbox/crs/tamanho, grade inválida sempre recusada com mensagem (nunca silêncio), item de outro
inquilino invisível e token sem escopo recusado."""

from __future__ import annotations

import pytest

Z, X, Y = 12, 1503, 2230  # mesmo ladrilho de test_tiles_token.py — cobre o raster de teste (Brasília)


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def raster_demo_b(tenant_id_b, sessao_b):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_b, "demo2")


@pytest.fixture(scope="module")
def token_ogc(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-ogc-tiles", "escopos": ["tiles:ler", "imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_ogc_sem_escopo(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-ogc-sem-escopo", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_ogc_b(sessao_b):
    r = sessao_b.post("/api/tokens", json={"nome": "zt-ogc-b", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def mosaico_registrado(sessao_a, raster_demo, token_ogc):
    """Mosaico REGISTRADO (item L1-07) sobre a mesma coleção do `raster_demo` — cobre a segunda forma
    de `{item}` no caminho, além do modo ad-hoc (nome de coleção completo)."""
    r_tok = sessao_a.post("/api/tokens", json={"nome": "zt-ogc-stac", "escopos": ["imagens:escrever"]})
    assert r_tok.status_code == 201, r_tok.text
    tok_stac = r_tok.json()["token"]
    c = _cliente()
    r = c.post(f"/svc/{tok_stac}/stac/mosaicos",
              json={"nome": "zt-ogc mosaico registrado", "collections": [raster_demo["colecao"]]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    c.delete(f"/svc/{tok_stac}/stac/mosaicos/{dados['id']}")
    sessao_a.delete(f"/api/tokens/{r_tok.json()['id']}")


# ---------------------------------------------------------------- cláusula: landing e conformance
def test_landing_aponta_para_conformance_collections_e_grades(token_ogc):
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles")
    assert r.status_code == 200, r.text
    corpo = r.json()
    rels = {lk["rel"]: lk["href"] for lk in corpo["links"]}
    assert rels["self"].endswith(f"/svc/{tok}/ogc/tiles/")
    assert rels["conformance"].endswith("/conformance")
    assert rels["data"].endswith("/collections")
    # barra final também responde (mesma URL, mesmo conteúdo)
    r2 = c.get(f"/svc/{tok}/ogc/tiles/")
    assert r2.status_code == 200 and r2.json() == corpo


def test_conformance_declara_so_o_que_esta_implementado(token_ogc):
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles/conformance")
    assert r.status_code == 200, r.text
    classes = set(r.json()["conformsTo"])
    exigidas = {
        "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
        "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/tileset",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/geodata-tilesets",
    }
    assert exigidas <= classes
    # nunca declarar o que não foi construído nesta passagem (ADR §7)
    nao_implementadas = {
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/collections-selection",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/dataset-tilesets",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/mvt",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/tiff",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/netcdf",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/oas30",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/html",
        "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/datetime",
    }
    assert not (nao_implementadas & classes)


# ---------------------------------------------------------------- cláusula: tileMatrixSets (definição real)
def test_tile_matrix_sets_lista_e_definicao_batem_com_o_motor_de_verdade(token_ogc):
    from app.imagens.tiles import TMS

    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles/tileMatrixSets")
    assert r.status_code == 200, r.text
    lista = r.json()["tileMatrixSets"]
    assert len(lista) == 1 and lista[0]["id"] == "WebMercatorQuad"

    r2 = c.get(f"/svc/{tok}/ogc/tiles/tileMatrixSets/WebMercatorQuad")
    assert r2.status_code == 200, r2.text
    definicao = r2.json()
    # não é um resumo escrito à mão: é O MESMO objeto que gera o ladrilho de verdade
    esperado = TMS.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert definicao == esperado
    assert len(definicao["tileMatrices"]) == len(TMS.tileMatrices)


def test_tile_matrix_set_desconhecida_e_404_honesto(token_ogc):
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles/tileMatrixSets/EuroExtremo")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "tileMatrixSet_invalido"


# ---------------------------------------------------------------- cláusula: collections
def test_collections_lista_o_item_visivel(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections")
    assert r.status_code == 200, r.text
    ids = {col["id"] for col in r.json()["collections"]}
    assert item in ids


def test_colecao_detalhe_do_item_tem_links_de_map_e_tileset(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["id"] == item
    rels = {lk["rel"] for lk in corpo["links"]}
    assert "http://www.opengis.net/def/rel/ogc/1.0/map" in rels
    assert "http://www.opengis.net/def/rel/ogc/1.0/map-tileset" in rels
    bbox = corpo["extent"]["spatial"]["bbox"][0]
    assert len(bbox) == 4 and bbox[0] < bbox[2] and bbox[1] < bbox[3]


# ---------------------------------------------------------------- cláusula: tileset metadata
def test_tileset_metadata_do_item(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["dataType"] == "map"
    assert corpo["tileMatrixSetURI"].endswith("WebMercatorQuad")
    limites = {li["tileMatrix"]: li for li in corpo["tileMatrixSetLimits"]}
    assert str(Z) in limites
    lim = limites[str(Z)]
    assert lim["minTileCol"] <= X <= lim["maxTileCol"]
    assert lim["minTileRow"] <= Y <= lim["maxTileRow"]
    rels = {lk["rel"]: lk for lk in corpo["links"]}
    assert rels["item"]["templated"] is True
    assert "{tileMatrix}/{tileRow}/{tileCol}" in rels["item"]["href"]


def test_tileset_grade_invalida_e_404(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/NaoExiste")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "tileMatrixSet_invalido"


# ---------------------------------------------------------------- cláusula: ladrilho byte-a-byte == XYZ
def test_ladrilho_do_item_e_byte_a_byte_igual_ao_xyz(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    xyz = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
    assert xyz.status_code == 200, xyz.text
    ogc = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}.png")
    assert ogc.status_code == 200, ogc.text
    assert ogc.content == xyz.content
    assert ogc.headers["content-type"] == xyz.headers["content-type"] == "image/png"
    # forma sem extensão (f=) tem de bater também
    ogc_sem_ext = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}")
    assert ogc_sem_ext.status_code == 200 and ogc_sem_ext.content == xyz.content
    # jpg também
    xyz_jpg = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.jpg")
    ogc_jpg = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}.jpg")
    assert ogc_jpg.status_code == 200 and ogc_jpg.content == xyz_jpg.content


def test_ladrilho_fora_da_cobertura_devolve_204(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad/{Z}/0/0.png")
    assert r.status_code == 204 and not r.content


def test_ladrilho_grade_invalida_e_404(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/NaoExiste/{Z}/{Y}/{X}")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "tileMatrixSet_invalido"


def test_ladrilho_formato_desconhecido_no_caminho_e_404(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}.bmp")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "formato_desconhecido"


# ---------------------------------------------------------------- cláusula: {item} vale para mosaico
def test_ladrilho_mosaico_ad_hoc_e_byte_a_byte_igual_ao_xyz_do_mosaico(token_ogc, raster_demo):
    c, tok, colecao = _cliente(), token_ogc["token"], raster_demo["colecao"]
    xyz = c.get(f"/svc/{tok}/mosaico/{colecao}/{Z}/{X}/{Y}.png")
    assert xyz.status_code == 200, xyz.text
    ogc = c.get(f"/svc/{tok}/ogc/tiles/collections/{colecao}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}.png")
    assert ogc.status_code == 200, ogc.text
    assert ogc.content == xyz.content


def test_tileset_de_colecao_ad_hoc_e_honesto_sobre_a_lacuna(token_ogc, raster_demo):
    """Mosaico ad-hoc (nome de coleção completo, sem registro) nunca teve documento de capacidades no
    resto do módulo (`mosaico_tilejson`/`mosaico_wmts_rest` só existem para uuid registrado — ADR §4);
    o tileset metadata segue a MESMA lacuna, com erro que diz exatamente o que fazer, nunca 500/200
    fingido."""
    c, tok, colecao = _cliente(), token_ogc["token"], raster_demo["colecao"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{colecao}/map/tiles/WebMercatorQuad")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "sem_metadados"


def test_ladrilho_e_tileset_do_mosaico_registrado(token_ogc, mosaico_registrado):
    c, tok, alvo = _cliente(), token_ogc["token"], mosaico_registrado["id"]
    xyz = c.get(f"/svc/{tok}/mosaico/{alvo}/{Z}/{X}/{Y}.png")
    assert xyz.status_code == 200, xyz.text
    ogc = c.get(f"/svc/{tok}/ogc/tiles/collections/{alvo}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}.png")
    assert ogc.status_code == 200, ogc.text
    assert ogc.content == xyz.content

    meta = c.get(f"/svc/{tok}/ogc/tiles/collections/{alvo}/map/tiles/WebMercatorQuad")
    assert meta.status_code == 200, meta.text
    assert meta.json()["dataType"] == "map"


# ---------------------------------------------------------------- cláusula: /map == GetMap do WMS
def test_mapa_bate_byte_a_byte_com_o_getmap_do_wms(token_ogc, raster_demo):
    import pyproj

    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r_info = c.get(f"/svc/{tok}/raster/{item}/info.json")
    assert r_info.status_code == 200, r_info.text
    oeste, sul, leste, norte = r_info.json()["bounds"]
    tf = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = tf.transform(oeste, sul)
    x1, y1 = tf.transform(leste, norte)
    bbox = f"{x0},{y0},{x1},{y1}"

    ogc = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map",
               params={"bbox": bbox, "crs": "EPSG:3857", "width": 300, "height": 300, "f": "png"})
    assert ogc.status_code == 200, ogc.text
    assert ogc.headers["content-type"] == "image/png"
    assert ogc.headers["content-crs"] == "<http://www.opengis.net/def/crs/EPSG/0/3857>"

    wms = c.get(f"/svc/{tok}/wms", params={
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": item,
        "CRS": "EPSG:3857", "BBOX": bbox, "WIDTH": 300, "HEIGHT": 300, "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
    })
    assert wms.status_code == 200, wms.text
    assert ogc.content == wms.content


def test_mapa_bbox_ausente_e_invertido_sao_recusados_com_mensagem(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    sem = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map")
    assert sem.status_code == 400 and sem.json()["erro"] == "bbox_ausente"
    invertido = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map",
                      params={"bbox": "10,10,-10,-10"})
    assert invertido.status_code == 400 and invertido.json()["erro"] == "bbox_invalido"


def test_mapa_bbox_nao_finito_e_recusado_400_nunca_502(token_ogc, raster_demo):
    """Achado do adversário independente (turno 9): `float("nan")`/`float("inf")` não levantam
    `ValueError` — "nan,nan,nan,nan" e "-inf,-inf,inf,inf" passavam da checagem de invertido (NaN nunca
    compara >=; -inf < inf é sempre verdadeiro) e só quebravam DENTRO de `tiles.recorte()`, saindo como
    502 `leitura_falhou` — categoria errada (é entrada do cliente, não falha de armazenamento)."""
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    for bbox in ("nan,nan,nan,nan", "-inf,-inf,inf,inf", "1,2,inf,4"):
        r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map", params={"bbox": bbox})
        assert r.status_code == 400, (bbox, r.status_code, r.text)
        assert r.json()["erro"] == "bbox_invalido", (bbox, r.text)


def test_mapa_crs_com_lixo_apos_epsg_e_recusado_400_nunca_502(token_ogc, raster_demo):
    """Achado do adversário independente (turno 9): `crs=EPSG:4326; DROP TABLE ...` passava o teste
    `startswith("EPSG:")` inteiro (inclusive o texto depois do número) e só quebrava dentro de
    `CRS.from_user_input`, saindo como 502 com o texto da exceção ecoado no corpo."""
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    for crs in ("EPSG:4326; DROP TABLE x", "EPSG:", "EPSG:abc", "EPSG:4326abc"):
        r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map",
                 params={"bbox": "-48,-16,-47,-15", "crs": crs})
        assert r.status_code == 400, (crs, r.status_code, r.text)
        assert r.json()["erro"] == "crs_invalido", (crs, r.text)


def test_mapa_recusa_mosaico_sem_fingir_suporte(token_ogc, raster_demo):
    c, tok, colecao = _cliente(), token_ogc["token"], raster_demo["colecao"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{colecao}/map", params={"bbox": "-48,-16,-47,-15"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "mapa_nao_suportado"


def test_mapa_dimensao_acima_do_teto_e_recusada(token_ogc, raster_demo):
    """A checagem tem de disparar ANTES do render (senão um pedido no canto do teto — medido em 142 s
    nesta bancada antes do conserto — passaria direto para `tiles.recorte`); por isso o teste usa uma
    largura ACIMA do teto (nunca o próprio teto, que é permitido) e confere que a resposta é rápida."""
    import time

    from app import limites

    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    inicio = time.perf_counter()
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map",
             params={"bbox": "-48,-16,-47,-15", "width": limites.WMS_LARGURA_MAX + 1, "height": 10})
    duracao = time.perf_counter() - inicio
    assert r.status_code == 400, r.text
    assert r.json()["erro"] == "dimensao_excessiva"
    assert duracao < 5.0, f"recusa deveria ser instantânea (rodou antes do render); levou {duracao:.1f}s"

    # o teto em si (4096x4096, produto == WMS_PIXELS_MAX) é PERMITIDO — só o que passa dele é recusado;
    # aqui só confere o código de erro do canto oposto (width dentro do teto, height acima)
    r2 = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map",
              params={"bbox": "-48,-16,-47,-15", "width": 10, "height": limites.WMS_ALTURA_MAX + 1})
    assert r2.status_code == 400 and r2.json()["erro"] == "dimensao_excessiva"


# ---------------------------------------------------------------- cláusula: isolamento e escopo
def test_item_de_outro_inquilino_e_invisivel(token_ogc, raster_demo_b):
    """Mesma regra do resto do L1-02: 403 em toda superfície, nunca 404 (não confirma existência
    alheia) — /collections/{item}, tileset e ladrilho."""
    c, tok, item_b = _cliente(), token_ogc["token"], raster_demo_b["item_id"]
    for url in (
        f"/svc/{tok}/ogc/tiles/collections/{item_b}",
        f"/svc/{tok}/ogc/tiles/collections/{item_b}/map/tiles/WebMercatorQuad",
        f"/svc/{tok}/ogc/tiles/collections/{item_b}/map/tiles/WebMercatorQuad/{Z}/{Y}/{X}.png",
        f"/svc/{tok}/ogc/tiles/collections/{item_b}/map?bbox=-48,-16,-47,-15",
    ):
        r = c.get(url)
        assert r.status_code == 403, (url, r.text)
        # item_indisponivel (não é raster item nem mosaico) ou mosaico_indisponivel (o id do item de
        # outro inquilino também é um uuid sintaticamente válido, então `_resolver_colecao` tenta o
        # ramo de mosaico registrado antes de desistir) — as duas são 403 honesto, nunca 404
        assert r.json()["erro"] in ("item_indisponivel", "mosaico_indisponivel")


def test_item_de_outro_inquilino_nao_aparece_na_listagem(token_ogc_b, raster_demo):
    c, tok_b, item_a = _cliente(), token_ogc_b["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok_b}/ogc/tiles/collections")
    assert r.status_code == 200, r.text
    ids = {col["id"] for col in r.json()["collections"]}
    assert item_a not in ids


def test_token_sem_escopo_e_recusado(token_ogc_sem_escopo, raster_demo):
    c, tok = _cliente(), token_ogc_sem_escopo["token"]
    for url in (
        f"/svc/{tok}/ogc/tiles",
        f"/svc/{tok}/ogc/tiles/conformance",
        f"/svc/{tok}/ogc/tiles/collections",
        f"/svc/{tok}/ogc/tiles/collections/{raster_demo['item_id']}",
    ):
        r = c.get(url)
        assert r.status_code == 403, (url, r.text)
