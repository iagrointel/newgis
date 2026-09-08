"""Backtest contra decisão real (item L3-09-backtest-decisao-real, `app/amc/backtest.py`), sem banco.
Cláusulas do portão que são de ALGORITMO:
- escolhas sintéticas geradas pelo próprio modelo dão AUC ≥ 0,95;
- escolhas aleatórias dão 0,5 ± 0,05;
- camada anacrônica marcada.
Refutação: escolhas = todas as unidades (AUC indefinida, com a frase que a tela mostra) e escolhas fora da
grade (a contagem `n_fora` chega ao relatório)."""

from __future__ import annotations

import numpy as np
import pytest

from app.amc import backtest as B

ITEM = "L3-09-backtest-decisao-real"


def _grade(n: int = 5000, semente: int = 0) -> np.ndarray:
    return np.random.default_rng(semente).uniform(0, 100, n)


def _melhores(fav: np.ndarray, k: int) -> np.ndarray:
    esc = np.zeros(fav.size, dtype=bool)
    esc[np.argsort(-fav)[:k]] = True
    return esc


def test_escolhas_do_proprio_modelo_dao_auc_alta():
    fav = _grade()
    r = B.avaliar(fav, _melhores(fav, 200), pedido=B.Pedido(n_permutacoes=200, semente=1))
    assert r.auc >= 0.95, r.auc
    assert r.percentil_mediano >= 95
    assert r.p_valor <= 1 / (200 + 1) + 1e-9, r.p_valor
    assert 0.45 <= r.nulo_auc_media <= 0.55
    assert r.n_escolhas == 200 and r.n_unidades == 5000 and r.permutacoes == 200


def test_escolhas_aleatorias_ficam_em_meio_a_meio(medida):
    """A cláusula do portão ('escolhas aleatórias 0,5 ± 0,05') é sobre o VALOR ESPERADO, e uma amostra tem
    dispersão: com 500 escolhas em 5.000 unidades o desvio-padrão teórico da AUC é
    sqrt((n1+n0+1)/(12·n1·n0)) ≈ 0,014, então uma tirada isolada passa de 0,05 uma vez a cada ~1.500. O teste
    mede as duas coisas: a média de 20 tiradas contra ± 0,02 (a afirmação de verdade) e cada tirada contra
    ± 0,05 (a cláusula literal), e grava a dispersão medida."""
    fav = _grade()
    rng = np.random.default_rng(7)
    aucs = []
    for k in range(20):
        esc = np.zeros(fav.size, dtype=bool)
        esc[rng.choice(fav.size, 500, replace=False)] = True
        r = B.avaliar(fav, esc, pedido=B.Pedido(n_permutacoes=50, semente=k))
        aucs.append(r.auc)
        assert 0.5 - 0.05 <= r.auc <= 0.5 + 0.05, (k, r.auc)
    media, desvio = float(np.mean(aucs)), float(np.std(aucs))
    assert abs(media - 0.5) <= 0.02, media
    m = medida(ITEM)
    m("auc_aleatoria_media", round(media, 4), "auc", "20 tiradas de 500 escolhas ao acaso em 5.000 unidades")
    m("auc_aleatoria_desvio", round(desvio, 4), "auc", "desvio-padrão medido das 20 tiradas (teórico ≈ 0,014)")


def test_escolhas_ruins_dao_auc_baixa_e_p_valor_alto():
    fav = _grade()
    piores = np.zeros(fav.size, dtype=bool)
    piores[np.argsort(fav)[:200]] = True
    r = B.avaliar(fav, piores, pedido=B.Pedido(n_permutacoes=200, semente=1))
    assert r.auc <= 0.05 and r.percentil_mediano <= 5
    assert r.p_valor >= 0.99, "o p-valor de uma cauda não pode 'premiar' um modelo que erra"


# ---- refutação do item
def test_todas_as_unidades_escolhidas_deixa_a_auc_indefinida():
    fav = _grade(500)
    r = B.avaliar(fav, np.ones(fav.size, dtype=bool), pedido=B.Pedido(n_permutacoes=10))
    assert r.auc is None
    assert "sem não-escolhas" in r.auc_indefinida and "não é 0,5 nem 1,0" in r.auc_indefinida
    assert r.percentil_mediano is not None, "o percentil continua fazendo sentido e é mostrado"
    assert r.p_valor is None


def test_nenhuma_escolha_na_grade_e_contagem_de_fora():
    fav = _grade(500)
    r = B.avaliar(fav, np.zeros(fav.size, dtype=bool), n_fora=42, pedido=B.Pedido(n_permutacoes=10))
    assert r.auc is None and r.n_escolhas == 0 and r.n_fora == 42
    assert "não há o que comparar" in r.auc_indefinida
    assert r.como_dicionario()["n_fora"] == 42


def test_camada_anacronica_e_marcada_com_a_frase():
    fav = _grade(500)
    esc = _melhores(fav, 50)
    r = B.avaliar(fav, esc, pedido=B.Pedido(n_permutacoes=10, data_decisao="2018-06-01",
                                            data_camada="2026-09-01"))
    assert r.anacronica is True
    assert any("ANACRÔNICO" in x for x in r.ressalvas)
    igual = B.avaliar(fav, esc, pedido=B.Pedido(n_permutacoes=10, data_decisao="2026-09-01",
                                                data_camada="2018-06-01"))
    assert igual.anacronica is False
    with pytest.raises(B.ErroBacktest) as e:
        B.avaliar(fav, esc, pedido=B.Pedido(n_permutacoes=10, data_decisao="ontem", data_camada="2026-01-01"))
    assert e.value.codigo == "data_invalida"


def test_ressalvas_saem_sempre_no_relatorio():
    fav = _grade(500)
    r = B.avaliar(fav, _melhores(fav, 50), pedido=B.Pedido(n_permutacoes=10))
    texto = " ".join(r.ressalvas)
    assert "não acerto futuro" in texto and "distância" in texto
    assert r.como_dicionario()["ressalvas"] == r.ressalvas


def test_preferencia_revelada_diz_sinal_e_ordem_nunca_peso():
    fav = _grade(2000, semente=3)
    n = fav.size
    perto = np.where(np.arange(n) < n // 2, 90.0, 10.0)     # metade alta = as primeiras unidades
    longe = 100.0 - perto
    rng = np.random.default_rng(5)
    esc = np.zeros(n, dtype=bool)
    esc[rng.choice(np.arange(n // 2), 100, replace=False)] = True   # escolhas todas na metade alta de `perto`
    r = B.avaliar(fav, esc, fatores={"perto_da_via": perto, "longe_da_via": longe},
                  pedido=B.Pedido(n_permutacoes=200, semente=2))
    por_nome = {f.nome: f for f in r.fatores}
    assert por_nome["perto_da_via"].sinal == "procurou" and por_nome["perto_da_via"].evitamento < -0.5
    assert por_nome["longe_da_via"].sinal == "evitou" and por_nome["longe_da_via"].evitamento > 0.5
    assert por_nome["perto_da_via"].fracao_escolhas == 1.0
    assert 0.4 <= por_nome["perto_da_via"].fracao_nulo <= 0.6
    # nada no relatório vira peso
    assert all(not hasattr(f, "peso") for f in r.fatores)
    assert "peso" not in {c for f in r.como_dicionario()["fatores"] for c in f}


def test_unidade_sem_nota_sai_da_conta_e_e_relatada():
    fav = _grade(1000)
    fav[:100] = np.nan
    esc = np.zeros(fav.size, dtype=bool)
    esc[:20] = True          # 20 escolhas em célula SEM nota
    esc[np.argsort(-np.nan_to_num(fav, nan=-1))[:30]] = True
    r = B.avaliar(fav, esc, pedido=B.Pedido(n_permutacoes=50))
    assert r.n_unidades == 900
    assert any("sem nota" in x for x in r.ressalvas)


def test_auc_e_percentil_conferem_com_a_conta_a_mao():
    fav = np.array([10.0, 20.0, 30.0, 40.0])
    esc = np.array([False, False, True, True])
    # as duas escolhas são as duas melhores: toda comparação escolhida × não-escolhida é vitória
    assert B.auc(fav, esc) == 1.0
    assert list(np.round(B.percentis(fav, esc), 1)) == [62.5, 87.5]
    # empate conta meio
    empate = np.array([10.0, 10.0])
    assert B.auc(empate, np.array([True, False])) == 0.5


def test_mesma_semente_da_relatorio_identico_e_limites():
    fav = _grade(1000)
    esc = _melhores(fav, 80)
    pedido = B.Pedido(n_permutacoes=300, semente=99)
    a, b = B.avaliar(fav, esc, pedido=pedido), B.avaliar(fav, esc, pedido=pedido)
    assert a.como_dicionario() == b.como_dicionario()
    with pytest.raises(B.ErroBacktest) as e:
        B.avaliar(fav, esc, pedido=B.Pedido(n_permutacoes=0))
    assert e.value.codigo == "permutacoes_fora_do_limite"
    with pytest.raises(B.ErroBacktest) as e:
        B.avaliar(fav, np.ones(3, dtype=bool), pedido=B.Pedido(n_permutacoes=10))
    assert e.value.codigo == "tamanhos_diferentes"
    with pytest.raises(B.ErroBacktest) as e:
        B.avaliar(np.full(10, np.nan), np.zeros(10, dtype=bool), pedido=B.Pedido(n_permutacoes=10))
    assert e.value.codigo == "sem_unidade_com_nota"
