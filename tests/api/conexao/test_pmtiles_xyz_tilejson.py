"""Item L6-02-g-pmtiles-xyz-tilejson: as rotas de `plat.conexao` recusam pmtiles/xyz sem
`config.atribuicao`/`zoom_min`/`zoom_max` (e xyz sem `formato`/marcadores `{z}{x}{y}` na URL), recusam pmtiles
cujo servidor não confirma `Range`/206, e `GET /api/conexoes/{id}/tilejson` monta o TileJSON de uma conexão
xyz. A checagem de Range é feita contra um PMTiles público real (Tigris/protomaps, `accept-ranges: bytes`
conferido por HTTP em 07/09/2026) — marcado `lento` (rede real), como o resto do módulo."""

import pytest

from tests.api.conftest import PREFIXO_TESTE

URL_PMTILES_PUBLICA = "https://demo-bucket.protomaps.com/v4.pmtiles"


@pytest.fixture
def limpar_conexoes(sessao_a):
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def _criar(sessao, sufixo, tipo, url, config, **extra):
    corpo = {"tipo": tipo, "nome": f"{PREFIXO_TESTE}-tiles-{sufixo}", "url": url, "config": config, **extra}
    return sessao.post("/api/conexoes", json=corpo)


# --------------------------------------------------------------------- xyz: config obrigatório (sem rede)
def test_xyz_sem_atribuicao_e_recusado(sessao_a):
    r = _criar(sessao_a, "sem-atrib", "xyz", "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
               {"zoom_min": 0, "zoom_max": 14, "formato": "raster"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "atribuicao_obrigatoria"


def test_xyz_sem_zoom_e_recusado(sessao_a):
    r = _criar(sessao_a, "sem-zoom", "xyz", "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
               {"atribuicao": "Fonte", "formato": "raster"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "zoom_min_invalido"


def test_xyz_sem_marcadores_na_url_e_recusado(sessao_a):
    r = _criar(
        sessao_a, "sem-marcador", "xyz", "https://tile.openstreetmap.org/tiles.png",
        {"atribuicao": "Fonte", "zoom_min": 0, "zoom_max": 14, "formato": "raster"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "url_sem_marcadores_xyz"


def test_xyz_sem_formato_e_recusado(sessao_a):
    r = _criar(
        sessao_a, "sem-formato", "xyz", "https://tile.openstreetmap.org/{z}/{x}/{y}.pbf",
        {"atribuicao": "Fonte", "zoom_min": 0, "zoom_max": 14},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "formato_invalido"


def test_xyz_raster_completo_e_aceito_e_tilejson_reflete_o_config(sessao_a, limpar_conexoes):
    config = {"atribuicao": "  Fonte Teste  ", "zoom_min": 1, "zoom_max": 18, "formato": "raster"}
    r = _criar(sessao_a, "raster-ok", "xyz", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", config)
    assert r.status_code == 201, r.text
    item = r.json()
    limpar_conexoes.append(item["id"])
    assert item["config"]["atribuicao"] == "Fonte Teste"  # espaços colapsados na gravação

    r_tj = sessao_a.get(f"/api/conexoes/{item['id']}/tilejson")
    assert r_tj.status_code == 200, r_tj.text
    doc = r_tj.json()
    assert doc["tilejson"] == "3.0.0"
    assert doc["attribution"] == "Fonte Teste"
    assert doc["minzoom"] == 1 and doc["maxzoom"] == 18
    assert doc["format"] == "raster"
    assert doc["tiles"] == ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]


def test_tilejson_em_conexao_que_nao_e_xyz_e_recusado(sessao_a, limpar_conexoes):
    r = _criar(
        sessao_a, "nao-xyz", "pmtiles", URL_PMTILES_PUBLICA,
        {"atribuicao": "Protomaps", "zoom_min": 0, "zoom_max": 14},
    )
    assert r.status_code == 201, r.text
    item = r.json()
    limpar_conexoes.append(item["id"])
    r_tj = sessao_a.get(f"/api/conexoes/{item['id']}/tilejson")
    assert r_tj.status_code == 422, r_tj.text
    assert r_tj.json()["erro"] == "tipo_sem_tilejson"


def test_xyz_editar_url_perdendo_marcador_e_recusado(sessao_a, limpar_conexoes):
    config = {"atribuicao": "Fonte", "zoom_min": 0, "zoom_max": 14, "formato": "raster"}
    r = _criar(sessao_a, "editar-marcador", "xyz", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", config)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    r2 = sessao_a.patch(f"/api/conexoes/{cid}", json={"url": "https://tile.openstreetmap.org/sem-marcador.png"})
    assert r2.status_code == 422, r2.text
    assert r2.json()["erro"] == "url_sem_marcadores_xyz"
    # a URL antiga continua valendo
    assert sessao_a.get(f"/api/conexoes/{cid}").json()["url"] == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


# --------------------------------------------------------------------- pmtiles: Range/206 (rede real)
@pytest.mark.lento
def test_pmtiles_publico_com_range_e_aceito(sessao_a, limpar_conexoes):
    config = {"atribuicao": "Protomaps demo (Tigris)", "zoom_min": 0, "zoom_max": 14}
    r = _criar(sessao_a, "pmtiles-ok", "pmtiles", URL_PMTILES_PUBLICA, config)
    assert r.status_code == 201, r.text
    limpar_conexoes.append(r.json()["id"])


@pytest.mark.lento
def test_pmtiles_sem_range_e_recusado_com_mensagem(sessao_a):
    """servidor público de verdade que responde (200) mas nunca honra Range — refutação do item, provada
    aqui contra um endpoint HTML comum (a mesma URL pública federal usada no resto do módulo): devolve 200
    ao pedido com Range, corpo inteiro, exatamente o caso que `verificar_range_pmtiles` tem de recusar."""
    url_sem_range = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"
    config = {"atribuicao": "Fonte", "zoom_min": 0, "zoom_max": 14}
    r = _criar(sessao_a, "pmtiles-sem-range", "pmtiles", url_sem_range, config)
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "pmtiles_sem_range"
    assert "Range" in corpo["mensagem"] or "range" in corpo["mensagem"].lower()
    # nunca fica gravada
    r_lista = sessao_a.get("/api/conexoes")
    assert url_sem_range not in {i["url"] for i in r_lista.json()["itens"]}
