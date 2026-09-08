"""Motor de localizar regiões (item L3-05-localizar-regioes, `app/amc/regioes.py`), sem banco. Cada cláusula do
portão vira um teste, na ordem em que o item as escreve:
1. superfície sintética com 3 picos: N = 3 devolve regiões com centróide a ≤ 2 células dos picos;
2. área total ± 5 % do alvo; 3. mínimos, máximos e distâncias respeitados;
4. compromisso 100 gera compacidade ≥ 0,9 da forma-alvo (círculo, quadrado e hexágono);
5. tempo em grade de 1 milhão de células medido (`tests/medidas`).
Refutação: área total maior que a área não vetada e N = 31 = recusa com mensagem; duas execuções com a mesma
semente = resultado idêntico."""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from app.amc import regioes as R

ITEM = "L3-05-localizar-regioes"
PICOS = ((25, 25), (30, 95), (95, 60))


def _superficie(lin: int = 120, col: int = 120, picos=PICOS, amp=(80, 75, 70), sigma=9.0) -> np.ndarray:
    yy, xx = np.mgrid[0:lin, 0:col]
    fav = np.full((lin, col), 10.0)
    for (cy, cx), a in zip(picos, amp, strict=False):
        fav = fav + a * np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma * sigma)))
    return fav


def _dist_ao_pico(r: R.Regiao) -> float:
    return min(math.dist(r.centroide, p) for p in PICOS)


def test_tres_picos_tres_regioes_no_lugar_certo():
    res = R.localizar(_superficie(), R.Pedido(n_regioes=3, area_total=900, semente_aleatoria=7))
    assert len(res.regioes) == 3
    assert all(_dist_ao_pico(r) <= 2.0 for r in res.regioes), [_dist_ao_pico(r) for r in res.regioes]
    # uma região por pico: os centróides não se repetem
    assert len({(round(r.centroide[0]), round(r.centroide[1])) for r in res.regioes}) == 3
    assert set(np.unique(res.rotulos)) == {0, 1, 2, 3}
    # rótulos e estatísticas concordam célula a célula
    for r in res.regioes:
        assert int(np.count_nonzero(res.rotulos == r.indice)) == r.celulas


def test_area_total_dentro_de_cinco_por_cento():
    fav = _superficie()
    for alvo in (300, 900, 2400):
        res = R.localizar(fav, R.Pedido(n_regioes=3, area_total=alvo, semente_aleatoria=7))
        assert abs(res.area_total - alvo) <= alvo * R.TOLERANCIA_AREA, (alvo, res.area_total)
        assert res.area_alvo == alvo
    # sem área pedida, o padrão é 10 % da área disponível (mesmo padrão da referência)
    res = R.localizar(fav, R.Pedido(n_regioes=1, semente_aleatoria=7))
    assert res.area_alvo == pytest.approx(fav.size * 0.1)


def test_minimo_maximo_e_distancias_respeitados():
    fav = _superficie()
    res = R.localizar(fav, R.Pedido(n_regioes=3, area_total=900, area_min=250, area_max=340,
                                    semente_aleatoria=7))
    assert all(250 <= r.area <= 340 for r in res.regioes), [r.area for r in res.regioes]
    # distância mínima: os picos estão a ~70 células; exigir 60 mantém as três, exigir 200 deixa menos
    res = R.localizar(fav, R.Pedido(n_regioes=3, area_total=900, distancia_min=60, semente_aleatoria=7))
    assert len(res.regioes) == 3
    for i, a in enumerate(res.regioes):
        for b in res.regioes[i + 1:]:
            assert math.dist(a.centroide, b.centroide) >= 60
    apertado = R.localizar(fav, R.Pedido(n_regioes=3, area_total=900, distancia_min=200, semente_aleatoria=7))
    assert len(apertado.regioes) < 3 and apertado.observacoes
    # distância máxima: 50 células é menos que a separação dos picos, então sobra menos de N
    perto = R.localizar(fav, R.Pedido(n_regioes=3, area_total=900, distancia_max=50, semente_aleatoria=7))
    for i, a in enumerate(perto.regioes):
        for b in perto.regioes[i + 1:]:
            assert math.dist(a.centroide, b.centroide) <= 50


@pytest.mark.parametrize("forma", ["circulo", "quadrado", "hexagono"])
def test_compromisso_cem_gera_a_forma_alvo(forma):
    res = R.localizar(_superficie(), R.Pedido(n_regioes=1, area_total=400, compromisso=100, forma=forma,
                                              semente_aleatoria=7))
    r = res.regioes[0]
    assert r.compacidade >= 0.9, (forma, r.compacidade)
    # e a compacidade medida contra a PRÓPRIA forma é a maior: um quadrado não é um bom círculo
    mascara = res.rotulos == r.indice
    assert R.compacidade(mascara, forma) >= max(
        R.compacidade(mascara, outra) for outra in R.FORMAS if outra != forma
    ) - 1e-9


def test_compromisso_zero_prefere_utilidade():
    fav = _superficie()
    so_forma = R.localizar(fav, R.Pedido(n_regioes=1, area_total=600, compromisso=100, semente_aleatoria=7))
    so_util = R.localizar(fav, R.Pedido(n_regioes=1, area_total=600, compromisso=0, semente_aleatoria=7))
    assert so_util.regioes[0].media >= so_forma.regioes[0].media
    assert so_forma.regioes[0].compacidade >= so_util.regioes[0].compacidade


def test_metodos_de_avaliacao_e_selecao():
    fav = _superficie()
    for metodo in R.AVALIACOES:
        res = R.localizar(fav, R.Pedido(n_regioes=2, area_total=600, metodo=metodo, semente_aleatoria=7))
        assert len(res.regioes) == 2 and res.parametros["metodo"] == metodo
        assert all(r.nota == pytest.approx(R._nota(r, metodo)) for r in res.regioes)
    seq = R.localizar(fav, R.Pedido(n_regioes=2, area_total=600, selecao="sequencial", semente_aleatoria=7))
    comb = R.localizar(fav, R.Pedido(n_regioes=2, area_total=600, selecao="combinatoria", semente_aleatoria=7))
    # a combinatória nunca é pior que a sequencial na soma das notas (é o que ela otimiza)
    assert sum(r.nota for r in comb.regioes) >= sum(r.nota for r in seq.regioes) - 1e-9


def test_veto_e_intransponivel_e_nao_entra_em_regiao():
    fav = _superficie()
    fav[20:31, :] = np.nan  # faixa vetada cortando o primeiro pico
    res = R.localizar(fav, R.Pedido(n_regioes=2, area_total=600, semente_aleatoria=7))
    assert not np.any(res.rotulos[~np.isfinite(fav)]), "célula sem dado dentro de região"
    assert res.parametros["area_disponivel"] == float(np.count_nonzero(np.isfinite(fav)))


def test_sem_ilhas_fecha_buraco_sem_engolir_veto():
    fav = _superficie()
    fav[24:27, 24:27] = 1.0     # cova de baixa favorabilidade no meio do pico
    fav[25, 25] = np.nan        # e uma célula vetada dentro da cova
    res = R.localizar(fav, R.Pedido(n_regioes=1, area_total=400, sem_ilhas=True, semente_aleatoria=7))
    mascara = res.rotulos == 1
    assert mascara[24, 26] and not mascara[25, 25], "buraco fechado, mas a célula vetada continua fora"


# ---- refutação do item
def test_area_maior_que_a_disponivel_recusa_com_mensagem():
    fav = _superficie(40, 40)
    fav[:, :20] = np.nan
    with pytest.raises(R.ErroRegioes) as e:
        R.localizar(fav, R.Pedido(n_regioes=1, area_total=1000))
    assert e.value.codigo == "area_maior_que_a_disponivel"
    assert e.value.detalhe["area_disponivel"] == 800 and e.value.detalhe["area_pedida"] == 1000
    assert "não vetada" in e.value.mensagem


def test_n_regioes_acima_de_trinta_recusa():
    with pytest.raises(R.ErroRegioes) as e:
        R.localizar(_superficie(), R.Pedido(n_regioes=31, area_total=900))
    assert e.value.codigo == "n_regioes_fora_do_limite" and e.value.detalhe["maximo"] == 30
    with pytest.raises(R.ErroRegioes) as e:
        R.localizar(_superficie(), R.Pedido(n_regioes=0, area_total=900))
    assert e.value.codigo == "n_regioes_fora_do_limite"


def test_mesma_semente_da_resultado_identico():
    fav = _superficie()
    pedido = R.Pedido(n_regioes=3, area_total=900, compromisso=40, semente_aleatoria=99)
    a, b = R.localizar(fav, pedido), R.localizar(fav, pedido)
    assert np.array_equal(a.rotulos, b.rotulos)
    assert a.como_dicionario() == b.como_dicionario()


def test_parametros_invalidos_tem_codigo_proprio():
    fav = _superficie(30, 30)
    casos = {
        "forma_desconhecida": R.Pedido(forma="losango"),
        "metodo_desconhecido": R.Pedido(metodo="chute"),
        "selecao_desconhecida": R.Pedido(selecao="magica"),
        "compromisso_fora_do_limite": R.Pedido(compromisso=101),
        "vizinhanca_invalida": R.Pedido(vizinhanca=6),
        "sementes_invalidas": R.Pedido(sementes="algumas"),
        "resolucao_invalida": R.Pedido(resolucao_crescimento="qualquer"),
        "area_min_maior_que_max": R.Pedido(area_min=100, area_max=10),
        "area_min_impossivel": R.Pedido(n_regioes=5, area_total=100, area_min=50),
        "area_max_impossivel": R.Pedido(n_regioes=2, area_total=500, area_max=10),
        "distancia_min_maior_que_max": R.Pedido(distancia_min=50, distancia_max=10),
        "area_total_invalida": R.Pedido(area_total=-1),
        "celula_invalida": R.Pedido(area_celula=0),
    }
    for codigo, pedido in casos.items():
        with pytest.raises(R.ErroRegioes) as e:
            R.localizar(fav, pedido)
        assert e.value.codigo == codigo, (codigo, e.value.codigo)
    with pytest.raises(R.ErroRegioes) as e:
        R.localizar(np.full((5, 5), np.nan), R.Pedido(area_total=1))
    assert e.value.codigo == "sem_area_disponivel"
    with pytest.raises(R.ErroRegioes) as e:
        R.localizar(np.array([1.0, 2.0]), R.Pedido())
    assert e.value.codigo == "grade_invalida"


def test_area_em_metros_quadrados_e_distancia_em_metros():
    """Com `area_celula`/`lado_celula`, o pedido fala em m² e m — é assim que a rota chama, com a resolução
    da grade do motor multicritério."""
    fav = _superficie()
    lado = 250.0  # célula de 250 m
    res = R.localizar(fav, R.Pedido(n_regioes=2, area_total=40e6, distancia_min=10_000,
                                    area_celula=lado * lado, lado_celula=lado, semente_aleatoria=7))
    assert abs(res.area_total - 40e6) <= 40e6 * R.TOLERANCIA_AREA
    a, b = res.regioes
    assert math.dist(a.centroide, b.centroide) * lado >= 10_000


def test_tempo_em_grade_de_um_milhao_de_celulas(medida):
    rng = np.random.default_rng(1)
    lin = col = 1000
    yy, xx = np.mgrid[0:lin, 0:col]
    fav = np.full((lin, col), 10.0)
    for cy, cx, amp, s in ((200, 200, 80, 60), (300, 800, 70, 55), (800, 500, 75, 65), (600, 150, 60, 50)):
        fav = fav + amp * np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * s * s)))
    fav = fav + rng.normal(0, 3, fav.shape)
    fav[fav < 0] = 0.0
    fav[100:140, :] = np.nan
    assert fav.size == 1_000_000
    t0 = time.perf_counter()
    res = R.localizar(fav, R.Pedido(n_regioes=3, area_total=30_000, semente_aleatoria=3))
    dt3 = time.perf_counter() - t0
    assert len(res.regioes) == 3 and abs(res.area_total - 30_000) <= 30_000 * R.TOLERANCIA_AREA
    t0 = time.perf_counter()
    res10 = R.localizar(fav, R.Pedido(n_regioes=10, area_total=60_000, semente_aleatoria=3))
    dt10 = time.perf_counter() - t0
    assert len(res10.regioes) == 10
    m = medida(ITEM)
    m("grade_1mi_n3_s", round(dt3, 2), "s", "localizar 3 regiões de 10.000 células em grade de 1.000×1.000")
    m("grade_1mi_n10_s", round(dt10, 2), "s", "localizar 10 regiões de 6.000 células na mesma grade")
    m("grade_1mi_celulas", int(fav.size), "celulas", "1.000×1.000, com 40.000 células vetadas")
