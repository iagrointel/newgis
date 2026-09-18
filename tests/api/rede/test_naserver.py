"""Camada Esri-compatível NAServer (item L2-11-c-rota-matriz-isocrona): solve (rota),
solveServiceArea (área de serviço), solveClosestFacility e solveODCostMatrix síncronos, no envelope
de feature set que JS (ArcGIS API) e QGIS/Pro consomem (stops/facilities/incidents como
{"features": [{"geometry": {"x", "y"}}]}, resposta com routes/directions/saPolygons/odCostMatrix).
O motor é o mesmo do /api/rota|matriz|isocrona — o teste confere coerência cruzada com eles."""

CENTRO_GUARULHOS = [-46.5330, -23.4628]
PERTO_GRU = [-46.4730, -23.4356]


def _fs(pontos):
    return {"features": [{"geometry": {"x": p[0], "y": p[1]}} for p in pontos]}


def test_naserver_route_solve(sessao_a):
    r = sessao_a.post(
        "/api/naserver/NAServer/Route/solve",
        json={"stops": _fs([CENTRO_GUARULHOS, PERTO_GRU]), "returnDirections": True},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    rota = corpo["routes"]["features"][0]
    assert rota["geometry"]["paths"][0][0] != rota["geometry"]["paths"][0][-1] or len(rota["geometry"]["paths"][0]) > 2
    assert rota["attributes"]["Total_Length"] > 0
    assert rota["attributes"]["Total_Time"] > 0
    direcoes = corpo["directions"][0]["features"]
    assert direcoes and any(d["attributes"]["text"] for d in direcoes)
    # coerência com a API nativa: mesma distância (mesmo motor)
    r2 = sessao_a.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU, "perfil": "carro"})
    assert abs(r2.json()["distancia_m"] - rota["attributes"]["Total_Length"]) < 1e-6


def test_naserver_service_area(sessao_a):
    r = sessao_a.post(
        "/api/naserver/NAServer/ServiceArea/solveServiceArea",
        json={"facilities": _fs([CENTRO_GUARULHOS]), "defaultBreaks": [10]},
    )
    assert r.status_code == 200, r.text
    poligonos = r.json()["saPolygons"]["features"]
    assert len(poligonos) == 1
    assert poligonos[0]["attributes"]["ToBreak"] == 10
    anel = poligonos[0]["geometry"]["rings"][0]
    assert len(anel) >= 4 and anel[0] == anel[-1]  # anel fechado válido


def test_naserver_closest_facility(sessao_a):
    facilidades = [CENTRO_GUARULHOS, PERTO_GRU]
    incidente = [PERTO_GRU[0] - 0.003, PERTO_GRU[1] - 0.002]
    r = sessao_a.post(
        "/api/naserver/NAServer/ClosestFacility/solveClosestFacility",
        json={"facilities": _fs(facilidades), "incidents": _fs([incidente]), "defaultTargetFacilityCount": 1},
    )
    assert r.status_code == 200, r.text
    rotas = r.json()["routes"]["features"]
    assert len(rotas) == 1
    # a facilidade escolhida tem de ser a do GRU (id 2), ao lado do incidente
    assert rotas[0]["attributes"]["FacilityID"] == 2
    assert rotas[0]["attributes"]["FacilityRank"] == 1
    assert rotas[0]["attributes"]["Total_Time"] > 0


def test_naserver_od_cost_matrix(sessao_a):
    origens = [CENTRO_GUARULHOS, [CENTRO_GUARULHOS[0] + 0.01, CENTRO_GUARULHOS[1]]]
    destinos = [PERTO_GRU, [PERTO_GRU[0] - 0.01, PERTO_GRU[1] + 0.005]]
    r = sessao_a.post(
        "/api/naserver/NAServer/ODCostMatrix/solveODCostMatrix",
        json={"origins": _fs(origens), "destinations": _fs(destinos)},
    )
    assert r.status_code == 200, r.text
    linhas = r.json()["odCostMatrix"]["features"]
    assert len(linhas) == 4
    pares = {(l["attributes"]["OriginID"], l["attributes"]["DestinationID"]) for l in linhas}
    assert pares == {(1, 1), (1, 2), (2, 1), (2, 2)}
    assert all(l["attributes"]["Total_Time"] >= 0 for l in linhas)


def test_naserver_exige_autenticacao(cliente):
    r = cliente.post("/api/naserver/NAServer/Route/solve", json={"stops": _fs([CENTRO_GUARULHOS, PERTO_GRU])})
    assert r.status_code == 401, r.text
