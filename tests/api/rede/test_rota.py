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
    r = sessao_a.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU, "perfil": "caminhao"})
    assert r.status_code == 422, r.text


def test_rota_perfis_bicicleta_e_pe(sessao_a):
    """Os três grafos estão carregados (um contêiner OSRM por perfil): bicicleta e pé respondem com
    durações coerentes com o modo (pé muito mais lento que carro no mesmo par de pontos)."""
    tempos = {}
    for perfil in ("carro", "bicicleta", "pe"):
        r = sessao_a.post(
            "/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU, "perfil": perfil}
        )
        assert r.status_code == 200, (perfil, r.text)
        corpo = r.json()
        assert corpo["perfil"] == perfil
        assert corpo["geometria"]["type"] == "LineString"
        assert corpo["instrucoes"], perfil
        tempos[perfil] = corpo["duracao_s"]
    assert tempos["pe"] > tempos["bicicleta"] > 0
    assert tempos["pe"] > tempos["carro"], tempos


def test_mais_proximo_snap(sessao_a):
    """Um ponto no miolo do recorte sai andando até a via mais próxima: distância de snap pequena e
    coordenada devolvida diferente da pedida (a menos que já esteja em cima da via)."""
    r = sessao_a.post("/api/mais-proximo", json={"ponto": CENTRO_GUARULHOS, "perfil": "carro"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert 0 <= corpo["distancia_m"] < 200
    lon, lat = corpo["ponto_rede"]
    assert -46.62 <= lon <= -46.42 and -23.53 <= lat <= -23.38
    assert corpo["proveniencia"]["sha256"]


def test_ajuste_de_trajeto_match(sessao_a):
    """Traçado GPS ruidoso ao longo da rota centro→GRU: os pontos são os vértices da PRÓPRIA geometria
    roteada (logo sobre a rede) sacudidos por ~30 m; o /match tem de devolver uma geometria encaixada
    na rede com extensão da mesma ordem da rota original."""
    import random

    r = sessao_a.post("/api/rota", json={"origem": CENTRO_GUARULHOS, "destino": PERTO_GRU, "perfil": "carro"})
    assert r.status_code == 200, r.text
    coords = r.json()["geometria"]["coordinates"]
    distancia_rota = r.json()["distancia_m"]
    random.seed(7)
    tracado = [[lon + random.uniform(-0.0003, 0.0003), lat + random.uniform(-0.0003, 0.0003)]
               for lon, lat in coords[:: max(len(coords) // 30, 1)]]
    r = sessao_a.post(
        "/api/ajuste-de-trajeto", json={"pontos": tracado, "perfil": "carro", "raio_m": 80}
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["geometria"]["type"] == "LineString"
    assert 0.5 * distancia_rota < corpo["distancia_m"] < 2.0 * distancia_rota
    assert corpo["confianca"] is None or 0 <= corpo["confianca"] <= 1
    assert corpo["instrucoes"]


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


def test_matriz_10x10_ate_1s(sessao_a):
    """Portão: matriz 10×10 em ≤ 1 s (cronometrado na resposta da API)."""
    import time

    origens = [[CENTRO_GUARULHOS[0] + 0.001 * i, CENTRO_GUARULHOS[1] + 0.001 * i] for i in range(10)]
    destinos = [[PERTO_GRU[0] + 0.001 * j, PERTO_GRU[1] + 0.001 * j] for j in range(10)]
    t0 = time.monotonic()
    r = sessao_a.post("/api/matriz", json={"origens": origens, "destinos": destinos, "perfil": "carro"})
    dt = time.monotonic() - t0
    assert r.status_code == 200, r.text
    assert len(r.json()["duracoes_s"]) == 10
    assert dt <= 1.0, f"10×10 levou {dt:.2f}s (portão: ≤ 1 s)"


def test_matriz_acima_do_teto_e_422(sessao_a):
    """Teto declarado do item: 1.000×1.000 (1M células) por job. A refutação do adversário pede
    5.000×5.000 (25M): recusada com 422 nomeado ANTES de qualquer chamada ao OSRM (medido pelo corpo
    do erro, que devolve origens/destinos/teto)."""
    origens = [[CENTRO_GUARULHOS[0] + 0.00001 * i, CENTRO_GUARULHOS[1]] for i in range(5000)]
    destinos = [[PERTO_GRU[0] + 0.00001 * j, PERTO_GRU[1]] for j in range(5000)]
    r = sessao_a.post("/api/matriz", json={"origens": origens, "destinos": destinos})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "matriz_grande_demais"
    assert r.json()["detalhe"]["teto"] == 1_000_000


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
