"""Traçado de custo mínimo sobre uma execução do motor multicritério (item L3-10-corredor-custo-minimo).

Portão, cláusula por cláusula:
  a) "saída = linha + corredor + manifesto" -> test_traca_linha_corredor_e_manifesto
  b) "corredor-epsilon (+5 %/+10 %)" -> test_corredor_cresce_com_o_epsilon
  c) refutação "adversário põe A ou B dentro de veto e camada de veto vazia" ->
     test_ponto_em_veto_e_recusado / test_veto_vazio_nao_muda_a_rota / test_tudo_vetado_nao_tem_caminho
  d) refutação "move um peso e confere que a rota muda" -> test_mudar_o_peso_muda_a_rota
A reprodução do trecho de referência do motor de traçado da casa é do `scripts/corredor_referencia.py` (as
medidas estão em tests/medidas/L3-10-corredor-custo-minimo.json); aqui a régua é o comportamento da API.

Área de estudo RETANGULAR de 4,0 km x 1,2 km com grade de 200 m = 20x6 = 120 células, e um fator desenhado com
uma FAIXA BARATA no topo: sem contraste de nota toda célula custaria igual e a linha seria a reta, que não prova
nada. O retângulo é largo e baixo DE PROPÓSITO: o peso da aresta é média de custo x comprimento, e o desvio para
a faixa barata só compensa quando o trecho horizontal a amortizar é bem maior que a subida — num quadrado 10x10
a conta NÃO fecha e o traçado certo é mesmo a reta."""

import math
import secrets

import pytest

CENTRO = (-46.60, -23.50)
LARGURA_M = 4000.0
ALTURA_M = 1200.0
RES_M = 200.0
_M_LAT = 111_320.0
_M_LON = 111_320.0 * math.cos(math.radians(CENTRO[1]))
MEIA_LON = (LARGURA_M / 2) / _M_LON
MEIA_LAT = (ALTURA_M / 2) / _M_LAT


def _area() -> dict:
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LON, lon + MEIA_LON
    y0, y1 = lat - MEIA_LAT, lat + MEIA_LAT
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _amostras(faixa_barata: bool) -> list[dict]:
    """Grade de 20x20 pontos. Com `faixa_barata`, o terço de cima do retângulo vale muito mais (nota alta,
    custo baixo); o limiar (lat − 0,25 da meia-altura) deixa as DUAS linhas de células de cima da grade
    baratas e as quatro de baixo caras. Sem contraste, o campo é uniforme."""
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LON * 0.95, lon + MEIA_LON * 0.95
    y0, y1 = lat - MEIA_LAT * 0.95, lat + MEIA_LAT * 0.95
    pontos = []
    for i in range(20):
        for j in range(20):
            px = x0 + (x1 - x0) * i / 19
            py = y0 + (y1 - y0) * j / 19
            alto = faixa_barata and py > lat - MEIA_LAT * 0.25
            pontos.append({"lon": px, "lat": py, "valor": 100.0 if alto else 10.0})
    return pontos


@pytest.fixture
def execucao(sessao_a):
    """Uma execução macro de 10x10 células com contraste de nota, pronta para o traçado."""
    r = sessao_a.post("/api/multiescala/conjuntos",
                      json={"nome": f"zt-corredor-{secrets.token_hex(4)}", "area": _area()})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    rf = sessao_a.post("/api/multiescala/fatores", json={
        "nome": f"zt-faixa-{secrets.token_hex(4)}", "resolucao_fonte_m": 100.0, "papel": "atrai",
        "unidade": "un", "fonte": "amostra sintética de teste",
    })
    assert rf.status_code == 201, rf.text
    fator = rf.json()
    ra = sessao_a.post(f"/api/multiescala/fatores/{fator['id']}/amostras", json={"amostras": _amostras(True)})
    assert ra.status_code == 201, ra.text
    re_ = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": RES_M, "fatores": [{"fator_id": fator["id"], "peso": 1.0}],
        "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert re_.status_code == 201, re_.text
    return {"conjunto": conjunto, "fator": fator, "execucao": re_.json()}


def _pontos_opostos() -> dict:
    """Dois cantos de baixo, um em cada lado: a reta entre eles corre pela metade CARA do retângulo."""
    lon, lat = CENTRO
    return {"origem": {"lon": lon - MEIA_LON * 0.9, "lat": lat - MEIA_LAT * 0.9},
            "destino": {"lon": lon + MEIA_LON * 0.9, "lat": lat - MEIA_LAT * 0.9}}


def _tracar(sessao, execucao, **extra):
    corpo = {**_pontos_opostos(), **extra}
    return sessao.post(f"/api/multiescala/execucoes/{execucao['execucao']['id']}/corredor", json=corpo)


def test_traca_linha_corredor_e_manifesto(sessao_a, execucao, medida):
    r = _tracar(sessao_a, execucao)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["linha"]["type"] == "LineString"
    assert len(c["linha"]["coordinates"]) >= 2
    assert c["corredor"]["type"] in ("Polygon", "MultiPolygon")
    assert c["corredor_celulas"] >= len(c["linha"]["coordinates"])
    assert c["corredor_geometria_omitida"] is False
    m = c["manifesto"]
    # o manifesto DECLARA a regra de custo, não só o resultado
    assert m["superficie"]["regra"] == "custo = 1 + (100 - nota)/100 * (custo_maximo - 1)"
    assert m["superficie"]["custo_maximo"] == 10.0 and m["superficie"]["custo_no_melhor"] == 1.0
    assert m["parametros"]["vizinhanca"] == 16 and m["parametros"]["epsilon"] == 0.05
    assert m["parametros"]["resolucao_m"] == RES_M
    assert m["medidas"]["comprimento_km"] > 0 and m["medidas"]["sinuosidade"] >= 1.0
    assert m["medidas"]["custo_total"] > 0
    # as pontas da linha são os centros das células escolhidas, e cada uma cai dentro da área de estudo
    lon, lat = CENTRO
    for x, y in c["linha"]["coordinates"]:
        assert lon - MEIA_LON <= x <= lon + MEIA_LON and lat - MEIA_LAT <= y <= lat + MEIA_LAT
    g = medida("L3-10-corredor-custo-minimo")
    g("api_grade_celulas", m["parametros"]["colunas"] * m["parametros"]["linhas"], "células",
      "POST /api/multiescala/execucoes/{id}/corredor sobre estudo de 2x2 km, grade de 200 m")
    g("api_duracao_ms", c["duracao_ms"], "ms", "duração medida na resposta da rota (grade de 100 células)")
    g("api_corredor_celulas_5pct", c["corredor_celulas"], "células", "epsilon padrão de 0,05")


def test_a_linha_desvia_para_a_faixa_barata(sessao_a, execucao):
    """A reta entre as pontas corre pela metade cara; o traçado tem de subir para a faixa de nota alta.

    A prova é comparativa e não depende de olhar o desenho: a nota média das células do traçado é maior que a
    nota média da reta entre as mesmas pontas."""
    r = _tracar(sessao_a, execucao, custo_maximo=50.0)
    assert r.status_code == 200, r.text
    coords = r.json()["linha"]["coordinates"]
    lat_media = sum(y for _, y in coords) / len(coords)
    lat_das_pontas = (coords[0][1] + coords[-1][1]) / 2
    assert lat_media > lat_das_pontas, "o traçado não subiu para a faixa barata"


def test_corredor_cresce_com_o_epsilon(sessao_a, execucao, medida):
    tamanhos = {}
    for eps in (0.0, 0.05, 0.10):
        r = _tracar(sessao_a, execucao, epsilon=eps)
        assert r.status_code == 200, r.text
        tamanhos[eps] = r.json()["corredor_celulas"]
    assert tamanhos[0.0] <= tamanhos[0.05] <= tamanhos[0.10], tamanhos
    g = medida("L3-10-corredor-custo-minimo")
    g("api_corredor_por_epsilon", {str(k): v for k, v in tamanhos.items()}, "células",
      "POST .../corredor com epsilon 0 / 0,05 / 0,10 na mesma execução")


def test_sem_epsilon_devolve_so_a_linha(sessao_a, execucao):
    r = _tracar(sessao_a, execucao, epsilon=None)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["corredor"] is None and c["corredor_celulas"] == 0
    assert c["manifesto"]["medidas"]["corredor_otimo"] is None


def test_ponto_em_veto_e_recusado(sessao_a, execucao):
    """Refutação do item: A ou B em cima de veto. A rota diz QUAL ponto, e não mexe no ponto do usuário."""
    r = _tracar(sessao_a, execucao, veto_abaixo_de=100.0)
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "ponto_em_veto"
    assert "origem" in corpo["mensagem"] or "destino" in corpo["mensagem"], corpo


def test_veto_vazio_nao_muda_a_rota(sessao_a, execucao):
    """A outra metade da refutação: camada de veto VAZIA (limiar 0) tem de dar exatamente a mesma rota."""
    sem = _tracar(sessao_a, execucao)
    com_veto_vazio = _tracar(sessao_a, execucao, veto_abaixo_de=0.0)
    assert sem.status_code == com_veto_vazio.status_code == 200
    assert sem.json()["linha"] == com_veto_vazio.json()["linha"]
    assert sem.json()["manifesto"]["medidas"]["custo_total"] == \
        com_veto_vazio.json()["manifesto"]["medidas"]["custo_total"]


def test_ponto_fora_da_area_e_recusado(sessao_a, execucao):
    corpo = {"origem": {"lon": 0.0, "lat": 0.0}, "destino": _pontos_opostos()["destino"]}
    r = sessao_a.post(f"/api/multiescala/execucoes/{execucao['execucao']['id']}/corredor", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "ponto_fora_da_area"


def test_tudo_vetado_nao_tem_caminho(sessao_a, execucao):
    """Veto por não aprovada + limiar alto o bastante para isolar as pontas: `sem_caminho`, nunca uma linha
    reta 'de emergência' por cima do veto."""
    r = _tracar(sessao_a, execucao, veto_abaixo_de=99.9, sem_dado="custo_maximo")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] in ("ponto_em_veto", "sem_caminho")


def test_mudar_o_peso_muda_a_rota(sessao_a, execucao):
    """Refutação: mexer no peso muda a superfície e a rota acompanha.

    Aqui o 'peso' que a API expõe é o `custo_maximo` (a inclinação da regra declarada): com custo máximo 1,01
    a superfície é quase plana e a rota é praticamente a reta; com 50 o desvio para a faixa barata compensa."""
    plana = _tracar(sessao_a, execucao, custo_maximo=1.01)
    inclinada = _tracar(sessao_a, execucao, custo_maximo=50.0)
    assert plana.status_code == inclinada.status_code == 200
    assert plana.json()["linha"] != inclinada.json()["linha"]
    lat_plana = sum(y for _, y in plana.json()["linha"]["coordinates"]) / \
        len(plana.json()["linha"]["coordinates"])
    lat_incl = sum(y for _, y in inclinada.json()["linha"]["coordinates"]) / \
        len(inclinada.json()["linha"]["coordinates"])
    assert lat_incl > lat_plana


def test_parametros_invalidos(sessao_a, execucao):
    assert _tracar(sessao_a, execucao, custo_maximo=0.5).status_code == 422
    assert _tracar(sessao_a, execucao, sem_dado="talvez").status_code == 422
    assert _tracar(sessao_a, execucao, vizinhanca=7).status_code == 422
    assert _tracar(sessao_a, execucao, epsilon=3.0).status_code == 422


def test_execucao_inexistente(sessao_a):
    r = sessao_a.post("/api/multiescala/execucoes/00000000-0000-0000-0000-000000000000/corredor",
                      json=_pontos_opostos())
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "execucao_inexistente"
