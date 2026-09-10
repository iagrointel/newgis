"""`.geojson` das feições de rede (fatia "rede de utilidades" do mapa, item L2-01-mapa-web): o mapa precisa da
GEOMETRIA para desenhar a rede — `/feicoes/pontos|linhas` (rotas_topologia.py) devolve só atributos, sem geom.

Cláusulas do portão provadas aqui: FeatureCollection com a geometria certa e as propriedades resolvidas
(`tipo`/`disciplina` pelo join tipo→grupo→domínio, nunca só o uuid cru); `bbox` filtra sem quebrar quem não
manda; mesmo controle de acesso das outras rotas `/feicoes/*` — RLS por inquilino, nunca vaza rede de outro."""

import pytest

from tests.api.test_rede_topologia import _criar_rede, _importar_eletrica, _linha, _ponto


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def test_linhas_geojson_devolve_geometria_e_propriedades_resolvidas(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "geojson-linha", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _linha(sessao_a, rid, [[-47.9, -15.8], [-47.91, -15.81]])

    r = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas.geojson")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection"
    assert len(corpo["features"]) == 1
    feicao = corpo["features"][0]
    assert feicao["type"] == "Feature"
    assert feicao["geometry"]["type"] == "LineString"
    assert feicao["geometry"]["coordinates"] == [[-47.9, -15.8], [-47.91, -15.81]]
    prop = feicao["properties"]
    assert prop["tipo"] == "Trecho de média tensão"
    assert prop["disciplina"] == "eletrica"
    assert prop["fase_bitmask"] is None
    assert "id" in prop and "tipo_id" in prop


def test_pontos_geojson_devolve_geometria_e_propriedades_resolvidas(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "geojson-ponto", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _ponto(sessao_a, rid, -48.0, -16.998, "transformador_de_distribuicao", 1)

    r = sessao_a.get(f"/api/rede/{rid}/feicoes/pontos.geojson")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["features"]) == 1
    feicao = corpo["features"][0]
    assert feicao["geometry"]["type"] == "Point"
    assert feicao["geometry"]["coordinates"] == [-48.0, -16.998]
    assert feicao["properties"]["disciplina"] == "eletrica"


def test_bbox_filtra_sem_quebrar_quem_nao_manda(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "geojson-bbox", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _linha(sessao_a, rid, [[-47.9, -15.8], [-47.91, -15.81]])
    _linha(sessao_a, rid, [[10.0, 10.0], [10.01, 10.01]])  # bem longe da primeira

    sem_bbox = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas.geojson")
    assert len(sem_bbox.json()["features"]) == 2

    so_a_primeira = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas.geojson?bbox=-48,-16,-47,-15")
    assert so_a_primeira.status_code == 200, so_a_primeira.text
    assert len(so_a_primeira.json()["features"]) == 1

    fora_de_tudo = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas.geojson?bbox=-1,-1,0,0")
    assert fora_de_tudo.json()["features"] == []

    invalido = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas.geojson?bbox=nao-e-numero")
    assert invalido.status_code == 422
    assert invalido.json()["erro"] == "bbox_invalido"


def test_inquilino_b_nunca_le_geojson_de_a(sessao_a, sessao_b, limpar_redes):
    rid = _criar_rede(sessao_a, "geojson-isolamento", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _linha(sessao_a, rid, [[-47.9, -15.8], [-47.91, -15.81]])

    r_linhas = sessao_b.get(f"/api/rede/{rid}/feicoes/linhas.geojson")
    r_pontos = sessao_b.get(f"/api/rede/{rid}/feicoes/pontos.geojson")
    assert r_linhas.status_code == 404, r_linhas.text
    assert r_pontos.status_code == 404, r_pontos.text
    assert r_linhas.json()["erro"] == "rede_inexistente"
