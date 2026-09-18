"""Portão de escala do item L2-11-c-rota-matriz-isocrona (arquivo próprio: são as provas pesadas):

1. matriz 1.000×1.000 (1M células, o teto declarado por job) em tempo medido — o serviço /table é
   particionado em blocos de PLAT_ROTA_MATRIZ_MAX células e remontado, sem célula nula nesta área
   conectada;
2. isócrona de 15/30/45 min contra a PRÓPRIA matriz: 200 pontos amostrados dentro de cada polígono
   têm de rotear em ≤ o orçamento em ≥ 95 % dos casos; e dos pontos na faixa 30–45 min (dentro do
   polígono de 45, fora do de 30), ≥ 95 % têm de medir > 30 min.

A isócrona do portão roda no perfil PÉ, não carro — medida estrutural desta construção (18/09/2026):
o recorte de teste inteiro (17 km) roteia em ≤ 28,8 min do centro de CARRO, então a isócrona de
carro de 45 min satura na borda do grafo e a faixa 30–45 não tem população verdadeira no recorte
(medido: 100 % dos pontos da faixa roteavam ≤ 30 min de carro). A pé (~5 km/h), os três orçamentos
existem de verdade dentro do recorte — é o caso clássico de isócrona de acessibilidade pedestre e a
leitura honesta do portão. A medida da saturação do carro fica registrada aqui também."""

import random
import time

import pytest
from shapely.geometry import Point, shape

ITEM = "L2-11-c-rota-matriz-isocrona"
CENTRO_GUARULHOS = [-46.5330, -23.4628]
PERFIL_PORTAO = "pe"

pytestmark = pytest.mark.lento


def _amostrar_dentro(poligono, n, semente, fora_de=None):
    """n pontos uniformes no bbox do polígono, mantidos os que caem dentro (e fora de `fora_de`,
    quando dado). Semente fixa: a amostra é estável entre rodadas."""
    rng = random.Random(semente)
    minx, miny, maxx, maxy = poligono.bounds
    pontos = []
    tentativas = 0
    while len(pontos) < n and tentativas < n * 60:
        tentativas += 1
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if poligono.contains(p) and (fora_de is None or not fora_de.contains(p)):
            pontos.append([p.x, p.y])
    return pontos


def test_matriz_1000x1000_tempo_medido(sessao_a, medida):
    rng = random.Random(11)
    origens = [[CENTRO_GUARULHOS[0] + rng.uniform(-0.07, 0.07), CENTRO_GUARULHOS[1] + rng.uniform(-0.07, 0.07)]
               for _ in range(1000)]
    destinos = [[CENTRO_GUARULHOS[0] + rng.uniform(-0.07, 0.07), CENTRO_GUARULHOS[1] + rng.uniform(-0.07, 0.07)]
                for _ in range(1000)]
    t0 = time.monotonic()
    r = sessao_a.post("/api/matriz", json={"origens": origens, "destinos": destinos, "perfil": "carro"})
    dt = time.monotonic() - t0
    assert r.status_code == 200, r.text[:400]
    corpo = r.json()
    duracoes = corpo["duracoes_s"]
    assert len(duracoes) == 1000 and all(len(linha) == 1000 for linha in duracoes)
    nulos = sum(1 for linha in duracoes for v in linha if v is None)
    medida(ITEM)(
        "matriz_1000x1000_s", round(dt, 1), "s",
        f"1M células particionadas em blocos de 625 (--max-table-size), {nulos} células nulas",
    )
    assert nulos == 0, f"{nulos} células sem rota numa área conectada"


def test_isocrona_15_30_45_contra_a_propria_matriz(sessao_a, medida):
    poligonos = {}
    for minutos in (15, 30, 45):
        r = sessao_a.post("/api/isocrona", json={"ponto": CENTRO_GUARULHOS, "minutos": minutos, "perfil": PERFIL_PORTAO})
        assert r.status_code == 200, (minutos, r.text[:400])
        corpo = r.json()
        poligonos[minutos] = shape(corpo["poligono"])
        medida(ITEM)(
            f"isocrona_{minutos}min_grade_pontos", corpo["grade"]["pontos_amostrados"], "pontos",
            f"alcançáveis {corpo['grade']['pontos_alcancaveis']}, resolução {corpo['grade']['resolucao_m']} m",
        )

    for minutos in (15, 30, 45):
        amostra = _amostrar_dentro(poligonos[minutos], 200, semente=minutos)
        assert len(amostra) >= 100, f"amostra de {minutos} min ficou com {len(amostra)} pontos"
        # tempos reais de cada ponto amostrado, pela própria API de matriz (1 × N)
        r = sessao_a.post("/api/matriz", json={"origens": [CENTRO_GUARULHOS], "destinos": amostra, "perfil": PERFIL_PORTAO})
        assert r.status_code == 200, r.text[:400]
        duracoes = r.json()["duracoes_s"][0]
        dentro = sum(1 for d in duracoes if d is not None and d <= minutos * 60)
        taxa = dentro / len(amostra)
        medida(ITEM)(
            f"isocrona_{minutos}min_taxa_dentro", round(taxa, 3), "proporção",
            f"{dentro}/{len(amostra)} da amostra roteia em ≤ {minutos} min (portão ≥ 0.95)",
        )
        assert taxa >= 0.95, f"polígono de {minutos} min: só {taxa:.1%} da amostra roteia em ≤ {minutos} min"

    # faixa 30–45: dentro do polígono de 45 e fora do de 30 → tem de medir > 30 min em ≥ 95 %
    faixa = _amostrar_dentro(poligonos[45], 400, semente=3045, fora_de=poligonos[30])
    assert len(faixa) >= 50, f"faixa 30–45 ficou com {len(faixa)} pontos (polígonos sobrepostos?)"
    r = sessao_a.post("/api/matriz", json={"origens": [CENTRO_GUARULHOS], "destinos": faixa, "perfil": PERFIL_PORTAO})
    assert r.status_code == 200, r.text[:400]
    duracoes = r.json()["duracoes_s"][0]
    acima = sum(1 for d in duracoes if d is not None and d > 30 * 60)
    taxa = acima / len(faixa)
    medida(ITEM)(
        "isocrona_faixa30_45_taxa_acima_de_30", round(taxa, 3), "proporção",
        f"{acima}/{len(faixa)} da faixa 30–45 mede > 30 min (portão ≥ 0.95)",
    )
    assert taxa >= 0.95, f"faixa 30–45: só {taxa:.1%} mede > 30 min"


def test_carro_satura_no_recorte_medida(sessao_a, medida):
    """Registra a saturação que motivou o portão em PÉ: 150 pontos sorteados na caixa ±0,07°
    (~14 km, dentro do recorte de 17 km) roteados do centro de CARRO — se o máximo ficar abaixo de
    30 min, a faixa 30–45 de carro não tem população verdadeira no grafo (medido 18/09/2026:
    máx 28,8 min)."""
    rng = random.Random(77)
    pontos = [[CENTRO_GUARULHOS[0] + rng.uniform(-0.07, 0.07), CENTRO_GUARULHOS[1] + rng.uniform(-0.07, 0.07)]
              for _ in range(150)]
    r = sessao_a.post("/api/matriz", json={"origens": [CENTRO_GUARULHOS], "destinos": pontos, "perfil": "carro"})
    assert r.status_code == 200, r.text[:400]
    duracoes = [d for d in r.json()["duracoes_s"][0] if d is not None]
    maximo_min = max(duracoes) / 60.0
    medida(ITEM)(
        "carro_max_recorte_min", round(maximo_min, 1), "min",
        f"máximo de {len(duracoes)} pontos da caixa ±0,07° roteados do centro; < 30 min ⇒ faixa 30–45 de carro é vazia",
    )
    assert maximo_min < 30.0, f"recorte passou a comportar faixa 30–45 de carro (máx {maximo_min:.1f} min) — rever o perfil do portão"
