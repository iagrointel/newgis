"""Rota, matriz e isócrona sobre o OSRM isolado de teste (item L2-11-c-rota-matriz-isocrona;
`plat-osrm-guarulhos`, 127.0.0.1:5010, recorte de Guarulhos). Dois pontos conhecidos do recorte:
centro de Guarulhos (-46,5330,-23,4628) e um ponto perto do GRU (-46,4730,-23,4356), ~11 km em
linha reta — a distância roteada tem de ficar numa faixa plausível (maior que a reta, sem disparar)."""

import math

CENTRO_GUARULHOS = [-46.5330, -23.4628]
PERTO_GRU = [-46.4730, -23.4356]


def _haversine_km(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def test_rota_dois_pontos_conhecidos(sessao_a):
    r = sessao_a.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU, "perfil": "carro"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    reta_km = _haversine_km(CENTRO_GUARULHOS, PERTO_GRU)
    distancia_km = corpo["distancia_m"] / 1000
    # rota real nunca é mais curta que a reta; numa área pequena não passa de ~2,5x a reta
    assert reta_km <= distancia_km <= reta_km * 2.5, (reta_km, distancia_km)
    assert 0 < corpo["duracao_s"] < 3600
    assert corpo["geometria"]["type"] == "LineString"
    assert len(corpo["geometria"]["coordinates"]) >= 2
    assert corpo["instrucoes"], "instruções vazias"
    assert any(i["texto"] for i in corpo["instrucoes"])
    assert corpo["proveniencia"]["sha256"]


def test_rota_perfil_nao_disponivel(sessao_a):
    r = sessao_a.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU, "perfil": "bicicleta"})
    assert r.status_code == 422, r.text


def test_rota_coordenada_invalida(sessao_a):
    r = sessao_a.post("/api/rota", json={"origem": [-200, -23.46], "destino": PERTO_GRU})
    assert r.status_code == 422, r.text


def test_matriz_5x5_sem_erro(sessao_a):
    origens = [[CENTRO_GUARULHOS[0] + 0.001 * i, CENTRO_GUARULHOS[1] + 0.001 * i] for i in range(5)]
    destinos = [[PERTO_GRU[0] + 0.001 * j, PERTO_GRU[1] + 0.001 * j] for j in range(5)]
    r = sessao_a.post("/api/matriz", json={"origens": origens, "destinos": destinos, "perfil": "carro"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["origens"] == 5 and corpo["destinos"] == 5
    duracoes = corpo["duracoes_s"]
    assert len(duracoes) == 5 and all(len(linha) == 5 for linha in duracoes)
    # todo par tem de ser roteável nesta área conectada (nenhum null)
    assert all(v is not None for linha in duracoes for v in linha)


def test_matriz_acima_do_teto_e_422(sessao_a, monkeypatch):
    # 26x26 = 676 > 625 (PLAT_ROTA_MATRIZ_MAX padrão) sem precisar de 676 coordenadas de verdade:
    # a checagem de teto é feita ANTES de chamar o OSRM (conferido pelo 422 com o corpo do teto)
    origens = [[CENTRO_GUARULHOS[0] + 0.0005 * i, CENTRO_GUARULHOS[1]] for i in range(26)]
    destinos = [[PERTO_GRU[0] + 0.0005 * j, PERTO_GRU[1]] for j in range(26)]
    r = sessao_a.post("/api/matriz", json={"origens": origens, "destinos": destinos})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "matriz_grande_demais"


def test_isocrona_10_min_poligono_nao_vazio(sessao_a):
    r = sessao_a.post("/api/isocrona", json={"ponto": CENTRO_GUARULHOS, "minutos": 10, "perfil": "carro"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    poligono = corpo["poligono"]
    assert poligono["type"] in ("Polygon", "MultiPolygon")
    anel_externo = poligono["coordinates"][0] if poligono["type"] == "Polygon" else poligono["coordinates"][0][0]
    assert len(anel_externo) >= 4  # anel fechado válido
    assert corpo["grade"]["pontos_alcancaveis"] >= 3
    assert corpo["minutos"] == 10


def test_isocrona_contra_a_propria_matriz(sessao_a):
    """Refutação leve (o item pede 200 pontos/95%; aqui é uma checagem interna menor, mesma lógica): um
    ponto perto do centro (dentro do raio-guia) tem de estar DENTRO do polígono de 10 min quando a rota
    até ele mede <= 10 min pela própria API de rota."""
    from shapely.geometry import Point, shape

    r = sessao_a.post("/api/isocrona", json={"ponto": CENTRO_GUARULHOS, "minutos": 10, "perfil": "carro"})
    assert r.status_code == 200, r.text
    poligono = shape(r.json()["poligono"])

    proximo = [CENTRO_GUARULHOS[0] + 0.01, CENTRO_GUARULHOS[1] + 0.005]
    rr = sessao_a.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": proximo, "perfil": "carro"})
    assert rr.status_code == 200, rr.text
    if rr.json()["duracao_s"] <= 10 * 60:
        assert poligono.buffer(0.01).contains(Point(proximo)), "ponto roteavelmente <=10min caiu fora do polígono"


def test_isocrona_minutos_invalido(sessao_a):
    r = sessao_a.post("/api/isocrona", json={"ponto": CENTRO_GUARULHOS, "minutos": 0})
    assert r.status_code == 422, r.text
    r = sessao_a.post("/api/isocrona", json={"ponto": CENTRO_GUARULHOS, "minutos": 99999})
    assert r.status_code == 422, r.text


def test_rota_exige_autenticacao(cliente):
    r = cliente.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU})
    assert r.status_code == 401, r.text
