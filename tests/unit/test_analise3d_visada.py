"""Unidade da linha de visada (L2-09-d).

Cláusula 1 do portão: "linha de visada com obstrução conhecida (dado sintético: morro entre dois
pontos) dá o ponto de obstrução a <= 30 m" — o morro aqui é gaussiano de parâmetros conhecidos, e o
ponto de obstrução verdadeiro é recalculado por varredura densa independente para comparar.

Refutação do item (adversário): observador ABAIXO do terreno e alvo a 200 km — nenhum dos dois pode
passar em silêncio; os dois viram 422 com o código do motivo.
"""

import math

import pytest

from app.analise3d.terreno import Terreno
from app.analise3d.visada import linha_de_visada
from app.erros import ErroAPI

CELULA = 10.0
N = 60  # 60x60 células de 10 m = 600 m de lado
X0, Y0 = 240000.0, 7360000.0
CENTRO = 300.0  # metros a partir do x0 (centro do morro)


def morro_sintetico(altura_cume: float = 100.0, sigma: float = 60.0) -> Terreno:
    alturas = []
    for i in range(N):
        y = i * CELULA
        linha = []
        for j in range(N):
            x = j * CELULA
            r2 = (x - CENTRO) ** 2 + (y - CENTRO) ** 2
            linha.append(round(altura_cume * math.exp(-r2 / (2 * sigma * sigma)), 3))
        alturas.append(linha)
    return Terreno(srid=31983, x0=X0, y0=Y0, celula_m=CELULA, alturas=alturas)


def cruzamento_verdadeiro(terreno: Terreno, obs, alvo, z_obs: float, z_alvo: float, passo: float = 0.25) -> tuple:
    """Varredura densa independente: primeiro ponto (x, y) em que o terreno passa acima da reta."""
    dx, dy = alvo[0] - obs[0], alvo[1] - obs[1]
    distancia = math.hypot(dx, dy)
    d = 0.0
    while d <= distancia:
        f = d / distancia
        z_reta = z_obs + (z_alvo - z_obs) * f
        z_terreno = terreno.amostrar(obs[0] + dx * f, obs[1] + dy * f)
        if z_terreno > z_reta + 1e-9:
            return (obs[0] + dx * f, obs[1] + dy * f)
        d += passo
    return None


def test_visada_limpa_em_terreno_plano_e_visivel():
    plano = Terreno(srid=31983, x0=X0, y0=Y0, celula_m=CELULA, alturas=[[0.0] * N for _ in range(N)])
    r = linha_de_visada(plano, (X0, Y0 + 300), (X0 + 590, Y0 + 300), 2.0, 0.0)
    assert r["visivel"] is True
    assert r["ponto_de_obstrucao"] is None
    assert r["distancia_m"] == pytest.approx(590.0)


def test_clausula_1_ponto_de_obstrucao_no_morro_a_30_m(medida):
    terreno = morro_sintetico()
    obs = (X0 + 2 * CELULA, Y0 + CENTRO)
    alvo = (X0 + 58 * CELULA, Y0 + CENTRO)
    r = linha_de_visada(terreno, obs, alvo, 2.0, 0.0)
    assert r["visivel"] is False
    assert r["ponto_de_obstrucao"] is not None
    verdadeiro = cruzamento_verdadeiro(terreno, obs, alvo, r["z_observador_m"], r["z_alvo_m"])
    assert verdadeiro is not None
    erro = math.hypot(
        r["ponto_de_obstrucao"]["x"] - verdadeiro[0], r["ponto_de_obstrucao"]["y"] - verdadeiro[1]
    )
    assert erro <= 30.0, f"ponto de obstrução a {erro:.1f} m do verdadeiro"
    medida("L2-09-d-analise-3d-visibilidade")(
        "clausula1_erro_ponto_obstrucao_m", round(erro, 2), "m",
        "erro contra varredura densa independente (passo 0,25 m) no morro sintético",
    )
    # o ponto declarado está entre o observador e o alvo, com a distância dos dois lados conferida
    p = r["ponto_de_obstrucao"]
    assert p["distancia_do_observador_m"] + p["distancia_do_alvo_m"] == pytest.approx(r["distancia_m"], abs=1e-6)
    assert p["z_terreno_m"] > p["z_linha_m"]


def test_mirante_no_cume_ve_a_borda_leste_do_morro():
    """Do cume com um mirante de 30 m a reta desce mais rápido que o ombro do domo e a borda leste
    é vista; a 2 m do chão o próprio ombro do morro obstrui (é física do domo, não defeito)."""
    terreno = morro_sintetico()
    cume = (X0 + CENTRO, Y0 + CENTRO)
    borda = (X0 + 58 * CELULA, Y0 + CENTRO)
    r = linha_de_visada(terreno, cume, borda, 30.0, 0.0)
    assert r["visivel"] is True
    # e a 2 m o ombro do domo obstrui logo após o cume (comportamento esperado)
    r2 = linha_de_visada(terreno, cume, borda, 2.0, 0.0)
    assert r2["visivel"] is False
    assert r2["ponto_de_obstrucao"]["distancia_do_observador_m"] < 30.0


def test_refutacao_observador_abaixo_do_terreno_e_422():
    terreno = morro_sintetico()
    with pytest.raises(ErroAPI) as e:
        linha_de_visada(terreno, (X0 + 100, Y0 + CENTRO), (X0 + 500, Y0 + CENTRO), -5.0, 0.0)
    assert e.value.status_code == 422 and e.value.erro == "ponto_abaixo_do_terreno"


def test_refutacao_alvo_a_200_km_fora_do_terreno_e_422():
    terreno = morro_sintetico()
    with pytest.raises(ErroAPI) as e:
        linha_de_visada(terreno, (X0 + 100, Y0 + CENTRO), (X0 + 100 + 200_000.0, Y0 + CENTRO), 2.0, 0.0)
    assert e.value.status_code == 422 and e.value.erro == "ponto_fora_do_terreno"


def test_refutacao_passo_fino_demais_estoura_o_teto_de_amostras_e_422():
    terreno = morro_sintetico()
    with pytest.raises(ErroAPI) as e:
        linha_de_visada(terreno, (X0 + 100, Y0 + CENTRO), (X0 + 500, Y0 + CENTRO), 2.0, 0.0, passo_m=0.01)
    assert e.value.status_code == 422 and e.value.erro == "amostras_acima_do_teto"


def test_visada_nula_quando_os_dois_pontos_sao_o_mesmo():
    terreno = morro_sintetico()
    with pytest.raises(ErroAPI) as e:
        linha_de_visada(terreno, (X0 + 100, Y0 + CENTRO), (X0 + 100, Y0 + CENTRO), 2.0, 0.0)
    assert e.value.status_code == 422 and e.value.erro == "visada_nula"
