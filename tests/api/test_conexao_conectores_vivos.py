"""API dos conectores vivos (item L6-02-conectores-vivos): `POST /api/conexoes/{id}/descobrir`,
`GET /api/conexoes/{id}/camadas` e `GET /api/conexoes/{id}/tile`.

Toda criação de conexão passa por `app.conexao.seguranca.validar_url`, que RESOLVE DNS de verdade mesmo
para decidir se recusa (não dá para cadastrar contra um domínio inventado) — por isso os testes que
precisam de uma conexão de verdade usam os 3 serviços que responderam 200 desta máquina em 10/09
(GeoSampa, IBGE) e ficam marcados `pytest.mark.lento` (mesma convenção do item L6-02-c-wfs-ogcapi: rede
real, fora do driver padrão, `pytest -m "not lento"`). O único teste sem rede
(`test_proxy_recusa_fonte_nao_cadastrada`) prova a recusa por UUID aleatório, sem precisar existir nada."""

import uuid

import pytest

GEOSAMPA_WMS = "https://raster.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms"
IBGE_OWS = "https://geoservicos.ibge.gov.br/geoserver/ows"


def _criar(sessao, *, tipo: str, url: str, nome: str) -> str:
    r = sessao.post("/api/conexoes", json={"tipo": tipo, "nome": nome, "url": url})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _apagar(sessao, cid: str) -> None:
    sessao.delete(f"/api/conexoes/{cid}")


# ---------------------------------------------------------------------------- sem rede
def test_proxy_recusa_fonte_nao_cadastrada(sessao_a):
    r = sessao_a.get(f"/api/conexoes/{uuid.uuid4()}/tile", params={"REQUEST": "GetMap"})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "conexao_inexistente"


def test_camadas_de_fonte_nao_cadastrada_e_404(sessao_a):
    r = sessao_a.get(f"/api/conexoes/{uuid.uuid4()}/camadas")
    assert r.status_code == 404, r.text


def test_descobrir_fonte_nao_cadastrada_e_404(sessao_a):
    r = sessao_a.post(f"/api/conexoes/{uuid.uuid4()}/descobrir")
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------- com rede real (criação exige DNS)
@pytest.mark.lento
def test_camada_de_outro_inquilino_invisivel_em_camadas_e_tile(sessao_a, sessao_b):
    cid = _criar(sessao_a, tipo="wms", url=GEOSAMPA_WMS, nome=f"zt-conector-cruzado-{uuid.uuid4().hex[:8]}")
    try:
        # o dono enxerga (lista vazia: ainda não descobriu, mas a conexão existe e é dele)
        assert sessao_a.get(f"/api/conexoes/{cid}/camadas").status_code == 200
        # o outro inquilino nunca vê — RLS filtra antes de qualquer requisição de rede sair
        r_camadas = sessao_b.get(f"/api/conexoes/{cid}/camadas")
        assert r_camadas.status_code == 404, r_camadas.text
        r_tile = sessao_b.get(f"/api/conexoes/{cid}/tile", params={"REQUEST": "GetCapabilities"})
        assert r_tile.status_code == 404, r_tile.text
        r_descobrir = sessao_b.post(f"/api/conexoes/{cid}/descobrir")
        assert r_descobrir.status_code == 404, r_descobrir.text
    finally:
        _apagar(sessao_a, cid)


@pytest.mark.lento
def test_proxy_recusa_tipo_sem_operacao_de_tile(sessao_a):
    """wfs/ogc_api são API de feição (páginas de GeoJSON/GML), não raster — o proxy de tile é 422 nomeado,
    nunca uma tentativa de buscar algo que não existe no serviço."""
    cid = _criar(sessao_a, tipo="wfs", url=IBGE_OWS, nome=f"zt-conector-wfs-{uuid.uuid4().hex[:8]}")
    try:
        r = sessao_a.get(f"/api/conexoes/{cid}/tile", params={"REQUEST": "GetCapabilities"})
        assert r.status_code == 422, r.text
        assert r.json()["erro"] == "tipo_sem_proxy"
    finally:
        _apagar(sessao_a, cid)


@pytest.mark.lento
def test_request_nao_permitido_no_proxy_e_422(sessao_a):
    cid = _criar(sessao_a, tipo="wms", url=GEOSAMPA_WMS, nome=f"zt-conector-req-{uuid.uuid4().hex[:8]}")
    try:
        r = sessao_a.get(f"/api/conexoes/{cid}/tile", params={"REQUEST": "GetFeatureInfo"})
        assert r.status_code == 422, r.text
        assert r.json()["erro"] == "request_nao_permitido"
        r_sem = sessao_a.get(f"/api/conexoes/{cid}/tile")
        assert r_sem.status_code == 422, r_sem.text
    finally:
        _apagar(sessao_a, cid)


@pytest.mark.lento
def test_descobrir_camadas_de_verdade_contra_ibge(sessao_a):
    """Prova viva contra um GeoServer nacional de verdade (item L6-02-conectores-vivos, portão: "teste
    automatizado contra endpoints públicos"). O IBGE serve WMS pelo mesmo endpoint `ows`."""
    cid = _criar(sessao_a, tipo="wms", url=f"{IBGE_OWS}?SERVICE=WMS", nome=f"zt-conector-ibge-{uuid.uuid4().hex[:8]}")
    try:
        r = sessao_a.post(f"/api/conexoes/{cid}/descobrir")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is True
        assert corpo["total"] > 0, "o IBGE não declarou nenhuma camada — GetCapabilities mudou?"
        exemplo = corpo["itens"][0]
        assert exemplo["nome"]
        assert isinstance(exemplo["crs"], list)

        # a lista guardada bate com a devolvida na hora da descoberta
        r2 = sessao_a.get(f"/api/conexoes/{cid}/camadas")
        assert r2.status_code == 200, r2.text
        assert r2.json()["total"] == corpo["total"]
    finally:
        _apagar(sessao_a, cid)


@pytest.mark.lento
def test_tile_de_verdade_contra_geosampa(sessao_a):
    """A prova que o portão pede: "adicionar camada por URL ... e vê-la no mapa" — aqui, a metade de API:
    um GetMap real, de ponta a ponta, pela conexão cadastrada (não a allowlist fixa de proxy_wms.py)."""
    cid = _criar(sessao_a, tipo="wms", url=GEOSAMPA_WMS, nome=f"zt-conector-tile-{uuid.uuid4().hex[:8]}")
    try:
        r = sessao_a.get(f"/api/conexoes/{cid}/tile", params={
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
            "LAYERS": "geoportal:MOSAICO_ORTO_RGB_10CM_20CM", "STYLES": "", "CRS": "EPSG:3857",
            "BBOX": "-5192000,-2696000,-5191000,-2695000", "WIDTH": "256", "HEIGHT": "256",
            "FORMAT": "image/png", "TRANSPARENT": "true",
        })
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/")
        assert len(r.content) > 500, f"tile suspeito de vazio ({len(r.content)} bytes)"
        assert r.headers.get("x-plat-cache") == "miss"

        # segunda chamada idêntica: cache em processo (mesma checagem que o item pede — "cache")
        r2 = sessao_a.get(f"/api/conexoes/{cid}/tile", params={
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
            "LAYERS": "geoportal:MOSAICO_ORTO_RGB_10CM_20CM", "STYLES": "", "CRS": "EPSG:3857",
            "BBOX": "-5192000,-2696000,-5191000,-2695000", "WIDTH": "256", "HEIGHT": "256",
            "FORMAT": "image/png", "TRANSPARENT": "true",
        })
        assert r2.status_code == 200
        assert r2.headers.get("x-plat-cache") == "hit"
        assert r2.content == r.content
    finally:
        _apagar(sessao_a, cid)
