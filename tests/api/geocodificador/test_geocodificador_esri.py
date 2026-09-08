"""GeocodeServer compatível Esri (item L2-11-b-geocodificador-brasil, ADR 0013 seção 5): findAddressCandidates,
reverseGeocode, suggest, geocodeAddresses, autenticados por `?token=` (protocolo Esri) sobre o mesmo motor da
API própria. QGIS como localizador real não roda nesta suíte (sem GUI/X na máquina de teste — SKILL.md pede
documentar como pendência, não como feito; ver docs/PARIDADE.md e o handoff do item)."""

import pytest

PREFIXO = "/rest/services/Geocodificador/GeocodeServer"


@pytest.fixture(scope="module")
def token_geocodificar(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-geocodificador-esri", "escopos": ["geocodificar:usar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_descritor_servico_sem_autenticacao(cliente):
    r = cliente.get(PREFIXO)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["capabilities"] == "Geocode,ReverseGeocode,Suggest"
    assert corpo["spatialReference"]["wkid"] == 4326


def test_find_address_candidates_exige_token(cliente):
    r = cliente.get(f"{PREFIXO}/findAddressCandidates", params={"SingleLine": "Rua A, Boa Vista - RR", "f": "json"})
    assert r.status_code == 401, r.text


def test_find_address_candidates_singleline_por_querystring_token(cliente, token_geocodificar):
    r = cliente.get(
        f"{PREFIXO}/findAddressCandidates",
        params={"SingleLine": "Rua A, Boa Vista - RR", "f": "json", "token": token_geocodificar, "maxLocations": 5},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["spatialReference"] == {"wkid": 4326}
    assert len(corpo["candidates"]) >= 1
    c = corpo["candidates"][0]
    assert "location" in c and "x" in c["location"] and "y" in c["location"]
    assert 0 <= c["score"] <= 100
    assert c["attributes"]["Addr_type"] in ("PointAddress", "StreetAddress", "StreetName", "Locality", "PostalExt")


def test_find_address_candidates_multifield(cliente, token_geocodificar):
    r = cliente.get(
        f"{PREFIXO}/findAddressCandidates",
        params={"address": "Rua A", "city": "Boa Vista", "region": "RR", "f": "json", "token": token_geocodificar},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["candidates"]) >= 1


def test_reverse_geocode(cliente, token_geocodificar, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT lat, lon FROM plat.geo_endereco WHERE cod_uf = 14 AND numero IS NOT NULL LIMIT 1"
        )
        r = cur.fetchone()
    resp = cliente.get(
        f"{PREFIXO}/reverseGeocode",
        params={"location": f"{r['lon']},{r['lat']}", "f": "json", "token": token_geocodificar},
    )
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["address"]["Match_addr"]
    assert corpo["location"]["x"] == pytest.approx(r["lon"], abs=1e-6)
    assert corpo["location"]["y"] == pytest.approx(r["lat"], abs=1e-6)


def test_reverse_geocode_location_json(cliente, token_geocodificar, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT lat, lon FROM plat.geo_endereco WHERE cod_uf = 14 LIMIT 1")
        r = cur.fetchone()
    import json as _json

    resp = cliente.get(
        f"{PREFIXO}/reverseGeocode",
        params={"location": _json.dumps({"x": r["lon"], "y": r["lat"]}), "f": "json", "token": token_geocodificar},
    )
    assert resp.status_code == 200, resp.text


def test_suggest(cliente, token_geocodificar):
    resp = cliente.get(f"{PREFIXO}/suggest", params={"text": "RUA A", "f": "json", "token": token_geocodificar})
    assert resp.status_code == 200, resp.text
    sugestoes = resp.json()["suggestions"]
    assert sugestoes
    assert "magicKey" in sugestoes[0] and "text" in sugestoes[0]


def test_geocode_addresses_lote(cliente, token_geocodificar):
    corpo = {
        "addresses": {
            "records": [
                {"attributes": {"OBJECTID": 1, "SingleLine": "Rua A, Boa Vista - RR"}},
                {"attributes": {"OBJECTID": 2, "SingleLine": "Endereço Que Não Existe De Jeito Nenhum, 999999"}},
            ]
        }
    }
    resp = cliente.post(f"{PREFIXO}/geocodeAddresses", params={"token": token_geocodificar, "f": "json"}, json=corpo)
    assert resp.status_code == 200, resp.text
    locais = resp.json()["locations"]
    assert len(locais) == 2
    assert locais[0]["attributes"]["Status"] == "M"
    assert locais[1]["attributes"]["Status"] == "U"


def test_geocode_addresses_lote_vazio_e_422(cliente, token_geocodificar):
    resp = cliente.post(f"{PREFIXO}/geocodeAddresses", params={"token": token_geocodificar},
                         json={"addresses": {"records": []}})
    assert resp.status_code == 422, resp.text


def test_escopo_errado_e_403(sessao_a, cliente):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-geocodificador-sem-escopo", "escopos": ["rota:usar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        resp = cliente.get(f"{PREFIXO}/suggest", params={"text": "Rua A", "token": tok["token"]})
        assert resp.status_code == 403, resp.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")
