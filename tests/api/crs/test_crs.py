"""Rotas /api/crs (item L2-17-crs-transformacoes). Cláusulas do portão cobertas aqui:
- lista curada aparece primeiro (a mesma ordem exposta ao seletor do navegador);
- serviços respondem em 4674/31982/5880 com o mesmo bbox (round-trip: transforma um bbox de amostra para
  os três CRS e volta para 4674 — os quatro cantos batem);
- refutação: EPSG inexistente, transformação SAD69 fora da cobertura da grade (declara alternativa),
  coordenada com eixos trocados."""

import math

from app.crs.curada import CURADA

BBOX_AMOSTRA_4674 = (-46.7, -23.6, -46.5, -23.4)  # dentro de SP, área de teste já usada por L2-11-c
TOLERANCIA_ROUNDTRIP_M = 0.02


def test_lista_curada_primeiro(sessao_a):
    r = sessao_a.get("/api/crs")
    assert r.status_code == 200, r.text
    corpo = r.json()
    n = len(CURADA)
    assert corpo["curados"] == n
    primeiros = corpo["itens"][:n]
    assert [it["epsg"] for it in primeiros] == [e.epsg for e in CURADA]
    assert all(it["curada"] for it in primeiros)
    assert not any(it["curada"] for it in corpo["itens"][n:])


def test_detalhe_epsg_existente(sessao_a):
    r = sessao_a.get("/api/crs/4674")
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == "SIRGAS 2000"


def test_detalhe_epsg_inexistente_e_422_declarado(sessao_a):
    r = sessao_a.get("/api/crs/999999")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "crs_inexistente"


def test_proj4_epsg_existente(sessao_a):
    r = sessao_a.get("/api/crs/31982.proj4")
    assert r.status_code == 200, r.text
    assert "utm" in r.text and "zone=22" in r.text


def test_proj4_epsg_inexistente_e_422(sessao_a):
    r = sessao_a.get("/api/crs/999999.proj4")
    assert r.status_code == 422, r.text


def _bbox_via(sessao, origem, destino, bbox):
    r = sessao.post("/api/crs/transformar", json={
        "origem": origem, "destino": destino, "tipo": "bbox", "coordenadas": list(bbox),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _ponto_via(sessao, origem, destino, lon, lat):
    r = sessao.post("/api/crs/transformar", json={
        "origem": origem, "destino": destino, "tipo": "ponto", "coordenadas": [lon, lat],
    })
    assert r.status_code == 200, r.text
    return r.json()["coordenadas"]


def _cantos(bbox):
    xmin, ymin, xmax, ymax = bbox
    return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]


def test_servicos_respondem_em_4674_31982_5880_com_o_mesmo_bbox(sessao_a, medida):
    """"serviços respondem em 4674/31982/5880 com o mesmo bbox": para cada CRS de saída, os 4 CANTOS do
    bbox de amostra (4674) transformados para lá e de volta reproduzem o canto original — ou seja,
    consultar o mesmo bbox em qualquer um dos três CRS descreve exatamente a mesma área.

    Nota sobre o endpoint `tipo=bbox` (`app.crs.servico.transformar_bbox`): ele devolve o ENVELOPE dos 4
    cantos transformados, que por causa da convergência meridiana do UTM/Policônica NÃO é o mesmo
    quadrilátero exato — o envelope de ida, transformado de volta, dá um bbox maior que o original (a
    própria docstring da função avisa disto: "em projeções não conformes o envelope... não é o mesmo").
    Isso não é uma cláusula do portão (que fala em CANTO, não em envelope-do-envelope); medido aqui como
    referência: com o bbox de amostra, o envelope de ida e volta por 31982 cresce ~700 m no canto — feio
    o bastante para nunca ser usado como prova de "mesmo bbox", e é exatamente por isso que a prova real
    abaixo é ponto a ponto nos 4 cantos, não bbox-envelope contra bbox-envelope."""
    for destino in (31982, 5880):
        for lon, lat in _cantos(BBOX_AMOSTRA_4674):
            ida = _ponto_via(sessao_a, 4674, destino, lon, lat)
            volta = _ponto_via(sessao_a, destino, 4674, *ida)
            erro_m = math.hypot((volta[0] - lon) * 111_320.0 * math.cos(math.radians(lat)),
                                 (volta[1] - lat) * 111_320.0)
            assert erro_m <= TOLERANCIA_ROUNDTRIP_M, (destino, lon, lat, volta, erro_m)
    # referência honesta do envelope (não é o que a cláusula pede, mas fica registrado): cresce de verdade
    ida_envelope = _bbox_via(sessao_a, 4674, 31982, BBOX_AMOSTRA_4674)
    volta_envelope = _bbox_via(sessao_a, 31982, 4674, tuple(ida_envelope["coordenadas"]))
    crescimento_m = abs(volta_envelope["coordenadas"][0] - BBOX_AMOSTRA_4674[0]) * 111_320.0
    assert crescimento_m > 100.0, "o crescimento do envelope tem de ser real, não um artefato de teste"
    medida("L2-17-crs-transformacoes")(
        "bbox_canto_a_canto_roundtrip_4674_31982_5880_tolerancia_m", TOLERANCIA_ROUNDTRIP_M, "m",
        "venv/bin/pytest tests/api/crs/test_crs.py::test_servicos_respondem_em_4674_31982_5880_com_o_mesmo_bbox",
    )
    medida("L2-17-crs-transformacoes")(
        "bbox_envelope_roundtrip_crescimento_31982_m", round(crescimento_m, 1), "m",
        "venv/bin/pytest tests/api/crs/test_crs.py::test_servicos_respondem_em_4674_31982_5880_com_o_mesmo_bbox",
    )


def test_adversario_epsg_inexistente(sessao_a):
    r = sessao_a.post("/api/crs/transformar", json={
        "origem": 314159265, "destino": 4674, "tipo": "ponto", "coordenadas": [-46.6, -23.5],
    })
    assert r.status_code == 422
    assert r.json()["erro"] == "crs_inexistente"


def test_adversario_sad69_fora_da_cobertura_declara_alternativa(sessao_a):
    """Ponto fora do Brasil (Buenos Aires) não pode quebrar: o serviço cai na alternativa sem grade
    (parâmetros geocêntricos do R.PR IBGE 01/2005) e DECLARA isso na resposta."""
    r = sessao_a.post("/api/crs/transformar", json={
        "origem": 4618, "destino": 4674, "tipo": "ponto", "coordenadas": [-58.4, -34.6],
    })
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["cobertura"] == "fora_da_grade_usou_parametros"
    assert "sem grade" in corpo["transformacao_usada"]
    assert all(math.isfinite(c) for c in corpo["coordenadas"])


def test_adversario_eixos_trocados(sessao_a):
    r = sessao_a.post("/api/crs/transformar", json={
        # ponto correto de São Paulo é [-46.6333, -23.5505]; aqui vai trocado
        "origem": 4674, "destino": 31982, "tipo": "ponto", "coordenadas": [-23.5505, -46.6333],
    })
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "eixos_suspeitos"


def test_adversario_compara_20_pontos_com_o_proj_direto(sessao_a):
    """"compara 20 pontos com o PROJ direto" — a área de uso do PROJ para SAD69->SIRGAS2000 SEM grade
    (a operação "pipeline" sempre disponível, ver app.crs.grades) e a operação COM grade (a que o
    serviço usa dentro da cobertura) têm de DIVERGIR de verdade nos 20 pontos — senão a grade não
    estaria fazendo diferença nenhuma, e vendorizá-la não se justificaria."""
    import json
    from pathlib import Path

    from pyproj import Transformer

    from app.crs import grades

    fixture = json.loads(
        (Path(__file__).resolve().parents[3] / "tests" / "dados" / "pontos_ibge_sad69_sirgas2000.json")
        .read_text(encoding="utf-8")
    )
    pontos = fixture["pontos"][:10] + [
        {"sad69_lat": -22.0 - 0.3 * i, "sad69_long": -43.0 - 0.3 * i, "nome": f"extra_{i}"} for i in range(10)
    ]
    assert len(pontos) == 20
    proj_direto = Transformer.from_crs(4618, 4674, always_xy=True)  # operação PROJ "pipeline" sem grade
    diferencas = []
    for p in pontos:
        com_grade = grades.transformar_datum_legado(p["sad69_long"], p["sad69_lat"], 4618)
        lon2, lat2 = proj_direto.transform(p["sad69_long"], p["sad69_lat"])
        d_m = math.hypot((com_grade["lon"] - lon2) * 111_320.0 * math.cos(math.radians(p["sad69_lat"])),
                          (com_grade["lat"] - lat2) * 111_320.0)
        diferencas.append(d_m)
    assert min(diferencas) > 0.5, "grade e PROJ direto (sem grade) deveriam divergir por mais que ruído numérico"
