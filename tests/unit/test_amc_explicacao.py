"""Item L3-01-f-explicacao — lógica pura (sem banco): transformação valor bruto → favorabilidade, montagem da
tabela da explicação e a prova central do portão — "soma das contribuições exibidas = favorabilidade gravada"
— sobre 100 unidades sorteadas, comparando com uma chamada independente a `app.amc.combinacao.combinar`."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.amc import combinacao
from app.amc.esquema import CAMINHO_ESQUEMA
from app.amc.explicacao import (
    MAPA_COMBINADOR,
    MAPA_POLITICA,
    aplicar_transformacao,
    montar_explicacao,
)

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- vocabulário: nada por trás do esquema
def test_mapa_combinador_cobre_todo_o_enum_do_esquema():
    esquema = json.loads(CAMINHO_ESQUEMA.read_text(encoding="utf-8"))
    enum = set(esquema["properties"]["combinador"]["properties"]["tipo"]["enum"])
    assert enum == set(MAPA_COMBINADOR)
    assert set(MAPA_COMBINADOR.values()) <= set(combinacao.COMBINADORES)


def test_mapa_politica_cobre_todo_o_enum_do_esquema():
    esquema = json.loads(CAMINHO_ESQUEMA.read_text(encoding="utf-8"))
    enum = set(esquema["properties"]["dado_ausente"]["enum"])
    assert enum == set(MAPA_POLITICA)
    assert set(MAPA_POLITICA.values()) <= set(combinacao.POLITICAS_AUSENTE)


# ---------------------------------------------------------------- transformação por tipo
def test_transformacao_ausencia_nunca_vira_numero():
    assert aplicar_transformacao(None, {"tipo": "linear", "minimo": 0, "maximo": 10}) == (None, None)


def test_transformacao_continua_e_delegada_a_biblioteca_de_transformacoes():
    """Enquanto o item L3-01-d era pendente, as doze funções contínuas saíam sem nota e com a lacuna nomeada.
    Com ele entregue, a explicação DELEGA a app/amc/transformacoes.py — é o que impede a explicação de uma
    unidade e a matriz da tela do motor (item L3-01-g) de darem números diferentes para o mesmo fator."""
    fav, obs = aplicar_transformacao(5.0, {"tipo": "gaussiana", "midpoint": 5, "spread": 1})
    assert fav == pytest.approx(100.0)  # no ponto médio a gaussiana vale o máximo
    assert obs is None
    longe, _ = aplicar_transformacao(9.0, {"tipo": "gaussiana", "midpoint": 5, "spread": 1})
    assert longe < fav


def test_transformacao_de_tipo_inexistente_continua_sem_nota_e_com_a_lacuna_nomeada():
    fav, obs = aplicar_transformacao(5.0, {"tipo": "nao_existe"})
    assert fav is None
    assert "nao_existe" in obs


@pytest.mark.parametrize(
    "valor,esperado",
    [(1.0, 90.0), (2.0, 40.0), (3.0, 10.0)],
)
def test_transformacao_categoria_bate_a_chave_numerica(valor, esperado):
    t = {"tipo": "categoria", "notas": {"1": 90, "2": 40, "3": 10}}
    fav, obs = aplicar_transformacao(valor, t)
    assert fav == esperado and obs is None


def test_transformacao_categoria_sem_nota_usa_outros():
    t = {"tipo": "categoria", "notas": {"1": 90}, "outros": 5}
    fav, obs = aplicar_transformacao(9.0, t)
    assert fav == 5.0 and "outros" in obs


def test_transformacao_categoria_sem_nota_e_sem_outros_fica_sem_numero():
    t = {"tipo": "categoria", "notas": {"1": 90}}
    fav, obs = aplicar_transformacao(9.0, t)
    assert fav is None and obs is not None


def test_transformacao_faixas_classifica_por_bin_semiaberto():
    t = {"tipo": "faixas", "quebras": [10, 20, 30], "notas": [100, 60, 20, 0]}
    assert aplicar_transformacao(5.0, t)[0] == 100    # abaixo da 1a quebra: 1a faixa
    assert aplicar_transformacao(10.0, t)[0] == 60    # no limite: entra na faixa seguinte
    assert aplicar_transformacao(15.0, t)[0] == 60
    assert aplicar_transformacao(30.0, t)[0] == 0     # na última quebra ou acima: última faixa
    assert aplicar_transformacao(1000.0, t)[0] == 0


def test_transformacao_faixas_abaixo_acima_declarados():
    t = {"tipo": "faixas", "quebras": [10, 20], "notas": [80, 40, 10], "abaixo": 99, "acima": 1}
    fav_abaixo, obs_abaixo = aplicar_transformacao(-5.0, t)
    fav_acima, obs_acima = aplicar_transformacao(500.0, t)
    assert (fav_abaixo, fav_acima) == (99.0, 1.0)
    assert "abaixo" in obs_abaixo and "acima" in obs_acima


@pytest.mark.parametrize(
    "direcao,valor,esperado",
    [("crescente", 0, 0.0), ("crescente", 30, 100.0), ("crescente", 15, 50.0),
     ("decrescente", 0, 100.0), ("decrescente", 30, 0.0), ("decrescente", 15, 50.0)],
)
def test_transformacao_linear_interpola_e_orienta(direcao, valor, esperado):
    t = {"tipo": "linear", "minimo": 0, "maximo": 30, "direcao": direcao}
    fav, obs = aplicar_transformacao(float(valor), t)
    assert fav == pytest.approx(esperado) and obs is None


def test_transformacao_linear_fora_da_faixa_sem_declaracao_satura():
    t = {"tipo": "linear", "minimo": 0, "maximo": 10}
    assert aplicar_transformacao(-5.0, t)[0] == 0.0
    assert aplicar_transformacao(50.0, t)[0] == 100.0


def test_transformacao_linear_fora_da_faixa_com_declaracao_usa_a_nota_declarada():
    t = {"tipo": "linear", "minimo": 0, "maximo": 10, "abaixo": 5, "acima": 95}
    assert aplicar_transformacao(-5.0, t)[0] == 5.0
    assert aplicar_transformacao(50.0, t)[0] == 95.0


def test_transformacao_degraus_bandas_fora_de_ordem_sao_ordenadas():
    t = {"tipo": "degraus",
         "bandas": [{"ate": 2000, "nota": 60}, {"ate": 500, "nota": 100}, {"ate": 10000, "nota": 20}]}
    assert aplicar_transformacao(100.0, t)[0] == 100.0
    assert aplicar_transformacao(1000.0, t)[0] == 60.0
    assert aplicar_transformacao(5000.0, t)[0] == 20.0


def test_transformacao_degraus_acima_da_ultima_banda():
    sem_acima = {"tipo": "degraus", "bandas": [{"ate": 500, "nota": 100}]}
    fav, obs = aplicar_transformacao(9999.0, sem_acima)
    assert fav == 100.0 and "última banda" in obs
    com_acima = {"tipo": "degraus", "bandas": [{"ate": 500, "nota": 100}], "acima": 0}
    fav2, obs2 = aplicar_transformacao(9999.0, com_acima)
    assert fav2 == 0.0 and "acima" in obs2


# ---------------------------------------------------------------- montagem da explicação
def _modelo(combinador_tipo="soma_ponderada_normalizada", dado_ausente="excluir_fator", gama=None):
    combinador = {"tipo": combinador_tipo}
    if gama is not None:
        combinador["gama"] = gama
    return {
        "esquema": "amc_modelo.v1", "nome": "modelo de teste unitário", "combinador": combinador,
        "dado_ausente": dado_ausente,
        "fatores": [
            {"id": "declividade", "nome": "declividade média", "fonte": "MDE de teste", "unidade": "%",
             "direcao": "menor_melhor", "base": "engenharia", "camada": {"tipo": "item", "id": "x"},
             "extrator": {"tipo": "raster_media"},
             "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 30, "direcao": "decrescente"}, "peso": 3.0},
            {"id": "dist_via", "nome": "distância à via", "fonte": "malha viária de teste", "unidade": "m",
             "direcao": "menor_melhor", "base": "engenharia", "camada": {"tipo": "item", "id": "y"},
             "extrator": {"tipo": "linha_distancia_mais_proxima"},
             "transformacao": {"tipo": "degraus", "bandas": [{"ate": 500, "nota": 100}, {"ate": 2000, "nota": 60},
                                                              {"ate": 10000, "nota": 20}], "acima": 0}, "peso": 1.5},
            {"id": "uso_solo", "nome": "classe de uso do solo", "fonte": "MapBiomas de teste", "unidade": "classe",
             "direcao": "maior_melhor", "base": "preferencia", "camada": {"tipo": "item", "id": "z"},
             "extrator": {"tipo": "raster_moda"},
             "transformacao": {"tipo": "categoria", "notas": {"1": 100, "15": 20}, "outros": 0}, "peso": 2.0},
            {"id": "dens_pop", "nome": "densidade populacional", "fonte": "censo de teste", "unidade": "hab/km²",
             "direcao": "menor_melhor", "base": "norma", "camada": {"tipo": "item", "id": "w"},
             "extrator": {"tipo": "raster_media"},
             "transformacao": {"tipo": "faixas", "quebras": [50, 200], "notas": [100, 50, 10]}, "peso": 1.0},
        ],
    }


def _pesos(m):
    return {f["id"]: f["peso"] for f in m["fatores"]}


def test_montar_explicacao_soma_das_contribuicoes_bate_a_favorabilidade_recalculada():
    m = _modelo()
    brutos = {"declividade": {"valor": 12.0, "cobertura": 1.0}, "dist_via": {"valor": 1200.0, "cobertura": 1.0},
              "uso_solo": {"valor": 15.0, "cobertura": 1.0}, "dens_pop": {"valor": 30.0, "cobertura": 1.0}}
    exp = montar_explicacao(m, _pesos(m), brutos)
    soma = sum(linha.contribuicao for linha in exp.fatores)
    assert soma == pytest.approx(exp.favorabilidade_recalculada, abs=1e-9)


def test_montar_explicacao_100_unidades_sorteadas_bate_combinacao_independente(medida):
    """A prova do portão: gera 100 unidades sintéticas, monta a explicação de cada uma e confere que a soma das
    contribuições exibidas bate |Δ| ≤ 0,5 com uma chamada SEPARADA a `combinacao.combinar` sobre a MESMA matriz
    de favorabilidades já transformadas (o "resultado gravado" que um motor futuro produziria)."""
    m = _modelo()
    ids = [f["id"] for f in m["fatores"]]
    pesos = _pesos(m)
    pesos_array = [pesos[i] for i in ids]
    rng = np.random.default_rng(20260907)
    brutos_por_valor = {
        "declividade": lambda: rng.uniform(-5, 40),
        "dist_via": lambda: rng.uniform(0, 15000),
        "uso_solo": lambda: float(rng.choice([1, 15, 7])),
        "dens_pop": lambda: rng.uniform(0, 400),
    }
    maior_delta = 0.0
    for _ in range(100):
        brutos = {}
        favores = []
        for fid in ids:
            valor = None if rng.uniform() < 0.05 else float(brutos_por_valor[fid]())
            brutos[fid] = {"valor": valor, "cobertura": 1.0}
            fav, _obs = aplicar_transformacao(valor, next(f for f in m["fatores"] if f["id"] == fid)["transformacao"])
            favores.append(fav)
        gravado_resultado = combinacao.combinar([favores], pesos_array, ids_fatores=ids)
        fav_gravado = gravado_resultado.fav[0]
        fav_gravado = None if not math.isfinite(fav_gravado) else float(fav_gravado)
        resultado_gravado = {"favorabilidade": fav_gravado, "vetado": False, "motivo": None,
                              "cobertura": float(gravado_resultado.cobertura[0])}
        exp = montar_explicacao(m, pesos, brutos, resultado_gravado)
        soma = sum(linha.contribuicao for linha in exp.fatores if linha.contribuicao is not None)
        if exp.favorabilidade_recalculada is None:
            assert fav_gravado is None
            continue
        delta_soma = abs(soma - exp.favorabilidade_recalculada)
        delta_gravado = abs(exp.favorabilidade_recalculada - fav_gravado) if fav_gravado is not None else 0.0
        maior_delta = max(maior_delta, delta_soma, delta_gravado)
    assert maior_delta <= 0.5, maior_delta
    gravar = medida("L3-01-f-explicacao")
    gravar("maior_delta_100_unidades_sorteadas", round(maior_delta, 6), "pontos",
          "100 unidades sintéticas (seed 20260907, 5% de fator ausente por unidade); "
          "|soma das contribuições − favorabilidade recalculada| e |recalculada − gravada independente|")


def test_montar_explicacao_politica_pessimista_inclui_fator_ausente_com_nota_zero():
    m = _modelo(dado_ausente="nota_pessimista")
    brutos = {"declividade": {"valor": None, "cobertura": 0.0}, "dist_via": {"valor": 1200.0, "cobertura": 1.0},
              "uso_solo": {"valor": 1.0, "cobertura": 1.0}, "dens_pop": {"valor": 30.0, "cobertura": 1.0}}
    exp = montar_explicacao(m, _pesos(m), brutos)
    linha = next(linha for linha in exp.fatores if linha.fator_id == "declividade")
    assert linha.presente is True and linha.favorabilidade_fator is None and linha.contribuicao == 0.0
    soma = sum(linha.contribuicao for linha in exp.fatores)
    assert soma == pytest.approx(exp.favorabilidade_recalculada, abs=1e-9)


def test_montar_explicacao_politica_unidade_nula_fica_sem_nota_com_um_fator_faltando():
    m = _modelo(dado_ausente="unidade_nula")
    brutos = {"declividade": {"valor": None, "cobertura": 0.0}, "dist_via": {"valor": 1200.0, "cobertura": 1.0},
              "uso_solo": {"valor": 1.0, "cobertura": 1.0}, "dens_pop": {"valor": 30.0, "cobertura": 1.0}}
    exp = montar_explicacao(m, _pesos(m), brutos)
    assert exp.favorabilidade_recalculada is None
    assert all(linha.contribuicao is None for linha in exp.fatores)


def test_montar_explicacao_combinador_sem_peso_nao_finge_decompor():
    m = _modelo(combinador_tipo="minimo")
    brutos = {"declividade": {"valor": 12.0, "cobertura": 1.0}, "dist_via": {"valor": 1200.0, "cobertura": 1.0},
              "uso_solo": {"valor": 15.0, "cobertura": 1.0}, "dens_pop": {"valor": 30.0, "cobertura": 1.0}}
    exp = montar_explicacao(m, _pesos(m), brutos)
    assert exp.contribuicoes_aditivas is False
    assert all(linha.contribuicao is None for linha in exp.fatores)
    assert any("não decompõe" in o for o in exp.observacoes)


def test_montar_explicacao_unidade_vetada_mostra_motivo_sem_recalcular_o_veto():
    m = _modelo()
    brutos = {"declividade": {"valor": 12.0, "cobertura": 1.0}, "dist_via": {"valor": 1200.0, "cobertura": 1.0},
              "uso_solo": {"valor": 15.0, "cobertura": 1.0}, "dens_pop": {"valor": 30.0, "cobertura": 1.0}}
    resultado_gravado = {"favorabilidade": None, "vetado": True,
                         "motivo": "unidade inteiramente coberta por restrição declarada no modelo", "cobertura": 1.0}
    exp = montar_explicacao(m, _pesos(m), brutos, resultado_gravado)
    assert exp.vetado is True
    assert exp.motivo_veto == resultado_gravado["motivo"]
    assert exp.favorabilidade_gravada is None
    assert exp.delta is None
    # os fatores continuam explicados (o porquê da nota que a unidade TERIA, mesmo vetada)
    assert exp.favorabilidade_recalculada is not None


def test_montar_explicacao_transformacao_fora_de_escopo_aparece_declarada_na_tabela():
    m = _modelo()
    m["fatores"][0]["transformacao"] = {"tipo": "gaussiana", "media": 15}
    brutos = {"declividade": {"valor": 12.0, "cobertura": 1.0}, "dist_via": {"valor": 1200.0, "cobertura": 1.0},
              "uso_solo": {"valor": 15.0, "cobertura": 1.0}, "dens_pop": {"valor": 30.0, "cobertura": 1.0}}
    exp = montar_explicacao(m, _pesos(m), brutos)
    linha = next(linha for linha in exp.fatores if linha.fator_id == "declividade")
    assert linha.valor_bruto == 12.0 and linha.favorabilidade_fator is None and linha.observacao is not None
    assert any("L3-01-d-transformacoes" in o for o in exp.observacoes)
