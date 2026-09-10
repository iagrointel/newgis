"""Refutação do item L3-02-b, feita contra o próprio código: o adversário duplica um fator (a MESMA
camada entrando duas vezes, com metade do peso em cada cópia) e confere que os índices das duas cópias
somam o índice do fator único dentro de ± 0,05.

O que este arquivo mede e declara (é o achado do item, não uma desculpa):

1. Somar os índices TOTAIS das duas cópias, uma a uma, NÃO devolve o índice do fator único: o total de
   cada cópia já conta a interação entre elas, e somar conta essa interação duas vezes. A conta certa é
   o índice do GRUPO das duas colunas trocadas juntas (`grupos=` em `app.amc.sensibilidade.sobol`).
2. Repartir o peso em duas metades sorteadas de forma independente com a MESMA faixa relativa reduz
   pela metade a variância do peso somado, e por isso reduz o índice mesmo com a conta certa. Para a
   comparação ser entre iguais, a faixa de cada cópia se alarga por √2 (`faixa_de_copias`), o que
   deixa média e variância do peso somado idênticas às do peso único.

As duas coisas são propriedades da análise de sensibilidade, não defeitos do modelo — e as duas
aparecem aqui como número medido, com o valor da diferença ingênua registrado."""

import numpy as np
import pytest

from app.amc import sensibilidade as sens

TOLERANCIA = 0.05
N = 4096
SEMENTE = 9
FAIXA = (-0.4, 0.4)


def _caso():
    """Três fatores; o primeiro (peso 3) é o que será repartido em duas cópias de peso 1,5."""
    rng = np.random.default_rng(5)
    m = rng.uniform(0.0, 100.0, size=(200, 3))
    unico = (m, [3.0, 2.0, 1.0], ["a", "b", "c"])
    duplicado = (np.hstack([m, m[:, [0]]]), [1.5, 2.0, 1.0, 1.5], ["a1", "b", "c", "a2"])
    return unico, duplicado


def _indices(caso, *, alvo, faixas_peso=None, grupos=None):
    m, pesos, ids = caso
    r = sens.sensibilidade_global(m, pesos, ids_fatores=ids, n=N, semente=SEMENTE, k_top=20, alvo=alvo,
                                  faixa_peso=FAIXA, faixas_peso=faixas_peso, grupos=grupos, n_bootstrap=0)
    return dict(zip(r.nomes, r.s1, strict=True)), dict(zip(r.nomes, r.st, strict=True))


@pytest.mark.parametrize("alvo", ["nota_media", "concordancia_topk"])
def test_fator_duplicado_soma_o_indice_do_fator_unico(alvo):
    """A refutação exigida, com a comparação entre iguais: cópias com faixa alargada por √2 e índice do
    GRUPO das duas. Vale para a 1ª ordem e para o total, nos dois alvos."""
    unico, duplicado = _caso()
    faixa_copia = sens.faixa_de_copias(FAIXA, 2)
    s1_u, st_u = _indices(unico, alvo=alvo)
    s1_d, st_d = _indices(
        duplicado, alvo=alvo,
        faixas_peso={"a1": faixa_copia, "a2": faixa_copia},
        grupos={"peso:a (duas cópias)": ["peso:a1", "peso:a2"], "peso:b": ["peso:b"], "peso:c": ["peso:c"]},
    )
    grupo = "peso:a (duas cópias)"
    assert s1_d[grupo] == pytest.approx(s1_u["peso:a"], abs=TOLERANCIA)
    assert st_d[grupo] == pytest.approx(st_u["peso:a"], abs=TOLERANCIA)
    # os fatores não mexidos continuam no mesmo lugar
    assert st_d["peso:b"] == pytest.approx(st_u["peso:b"], abs=TOLERANCIA)
    assert st_d["peso:c"] == pytest.approx(st_u["peso:c"], abs=TOLERANCIA)


def test_somar_os_totais_das_copias_uma_a_uma_conta_a_interacao_duas_vezes():
    """Contraprova da conta ERRADA: somar ST de cada cópia passa do índice único, porque o total de
    cada uma já inclui a interação com a outra. É por isso que o item expõe índice de grupo."""
    unico, duplicado = _caso()
    faixa_copia = sens.faixa_de_copias(FAIXA, 2)
    _, st_u = _indices(unico, alvo="concordancia_topk")
    _, st_d = _indices(duplicado, alvo="concordancia_topk",
                       faixas_peso={"a1": faixa_copia, "a2": faixa_copia})
    soma_ingenua = st_d["peso:a1"] + st_d["peso:a2"]
    assert soma_ingenua > st_u["peso:a"] + TOLERANCIA


def test_repartir_o_peso_sem_alargar_a_faixa_derruba_o_indice_pela_perda_de_variancia():
    """Contraprova da faixa ERRADA: duas metades independentes na mesma faixa relativa têm metade da
    variância do peso único, e o índice do grupo cai junto. Medido, não suposto."""
    unico, duplicado = _caso()
    _, st_u = _indices(unico, alvo="nota_media")
    _, st_d = _indices(duplicado, alvo="nota_media",
                       grupos={"g": ["peso:a1", "peso:a2"], "peso:b": ["peso:b"], "peso:c": ["peso:c"]})
    assert st_d["g"] < st_u["peso:a"] - TOLERANCIA


def test_ordem_dos_fatores_nao_muda_o_indice_de_cada_fator():
    """Permutar a ordem das colunas (e dos pesos e dos identificadores junto) não pode mudar o índice
    atribuído a cada fator — o mesmo ataque que o item L3-02-a sofreu no sorteio."""
    rng = np.random.default_rng(21)
    m = rng.uniform(0.0, 100.0, size=(150, 4))
    pesos = [3.0, 2.0, 1.0, 4.0]
    ids = ["a", "b", "c", "d"]
    direto = _indices((m, pesos, ids), alvo="nota_media")[1]
    ordem = [3, 1, 0, 2]
    trocado = _indices((m[:, ordem], [pesos[i] for i in ordem], [ids[i] for i in ordem]),
                       alvo="nota_media")[1]
    for i in ids:
        assert trocado[f"peso:{i}"] == pytest.approx(direto[f"peso:{i}"], abs=TOLERANCIA)


def test_fator_repetido_com_o_mesmo_identificador_continua_recusado_pelo_combinador():
    """A camada duplicada tem de entrar com identificador próprio: o combinador (item L3-01-e) recusa o
    mesmo identificador duas vezes, e a sensibilidade não pode contornar essa recusa."""
    m = np.random.default_rng(1).uniform(0.0, 100.0, size=(40, 2))
    with pytest.raises(sens.ErroSensibilidade, match="mais de uma vez"):
        sens.sensibilidade_global(m, [1.0, 1.0], ids_fatores=["a", "a"], n=64, semente=1, k_top=4,
                                  n_bootstrap=0)


def test_indice_nunca_e_apresentado_como_importancia_do_fator_no_territorio():
    """Ataque de linguagem: nenhuma saída pode dizer 'importância', 'peso ótimo' ou 'melhor peso' sem a
    ressalva junto — a frase da casa é que se mede a dependência do modelo, não o mundo."""
    m = np.random.default_rng(2).uniform(0.0, 100.0, size=(60, 3))
    r = sens.relatorio_sensibilidade(m, [1.0, 2.0, 3.0], modelo="teste", ids_fatores=["a", "b", "c"],
                                     n=128, semente=4, k_top=6, n_bootstrap=10)
    texto = " ".join([r["aviso"], r["texto_explicacao"], r["descricao_alvo"],
                      *r["global"]["observacoes"], r["local"]["metodo"]]).lower()
    assert "peso ótimo" not in texto and "melhor peso" not in texto
    assert "não a importância real" in texto
    assert "medida de importância real do fator no território" in texto  # a negativa explícita
