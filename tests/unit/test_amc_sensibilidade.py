"""Sensibilidade do motor multicritério (item L3-02-b). Sem banco: `app.amc.sensibilidade` é puro
(numpy + scipy.stats.qmc), como o combinador e o sorteio que ele reusa.

Cláusulas do portão de pronto cobertas aqui:
- a função de teste de Ishigami reproduz os índices de referência em forma fechada dentro de ± 0,05;
- o relatório por modelo traz N, os índices e o intervalo por reamostragem (bootstrap);
- o texto de saída diz que a sensibilidade mede a dependência do modelo ao peso, não importância real.
A cláusula de tempo está em `test_amc_sensibilidade_desempenho.py` (medida gravada com carga e RAM ao
lado); a refutação do fator duplicado está em `test_amc_sensibilidade_adversario.py`."""

import math

import numpy as np
import pytest

from app.amc import sensibilidade as sens

TOLERANCIA_REFERENCIA = 0.05
N_ISHIGAMI = 16384


def _modelo_de_quatro_fatores(unidades: int = 300):
    """Modelo de teste: três fatores que variam e um praticamente constante (o constante tem de sair
    como irrelevante, porque mexer no peso dele não muda a lista)."""
    rng = np.random.default_rng(3)
    m = rng.uniform(0.0, 100.0, size=(unidades, 4))
    m[:, 3] = 50.0
    pesos = [3.0, 2.0, 1.0, 2.0]
    ids = ["declividade", "acesso", "uso", "constante"]
    return m, pesos, ids


# --------------------------------------------------------------------------- função de referência

def test_ishigami_reproduz_os_indices_de_referencia():
    referencia = sens.indices_analiticos_ishigami()
    r = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=N_ISHIGAMI, semente=7, n_bootstrap=0)
    erro_s1 = np.abs(r.s1 - np.array(referencia["s1"]))
    erro_st = np.abs(r.st - np.array(referencia["st"]))
    assert erro_s1.max() <= TOLERANCIA_REFERENCIA, f"1ª ordem fora da referência: {erro_s1}"
    assert erro_st.max() <= TOLERANCIA_REFERENCIA, f"total fora da referência: {erro_st}"
    assert abs(r.variancia - referencia["variancia"]) <= 0.5
    assert r.n == N_ISHIGAMI and r.n_avaliacoes == N_ISHIGAMI * 5


def test_referencia_analitica_do_ishigami_bate_com_a_literatura():
    """S1 ≈ [0,314; 0,442; 0] e ST ≈ [0,557; 0,442; 0,244] para a=7 e b=0,1 (Saltelli et al.)."""
    r = sens.indices_analiticos_ishigami()
    assert r["s1"] == pytest.approx([0.3139, 0.4424, 0.0], abs=1e-3)
    assert r["st"] == pytest.approx([0.5576, 0.4424, 0.2437], abs=1e-3)


def test_terceira_variavel_do_ishigami_e_irrelevante_de_1a_ordem_mas_nao_no_total():
    """x3 não tem efeito próprio (S1 = 0) e ainda assim manda no resultado por interação com x1
    (ST ≈ 0,24). É por isso que o relatório lê o índice TOTAL para dizer o que é irrelevante."""
    r = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=N_ISHIGAMI, semente=11, n_bootstrap=0)
    assert abs(r.s1[2]) < 0.05
    assert r.st[2] > 0.15
    assert r.irrelevantes == []


def test_mesma_semente_reproduz_bit_a_bit_e_semente_diferente_muda():
    a = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=1024, semente=5, n_bootstrap=20)
    b = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=1024, semente=5, n_bootstrap=20)
    c = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=1024, semente=6, n_bootstrap=20)
    assert np.array_equal(a.s1, b.s1) and np.array_equal(a.st, b.st)
    assert np.array_equal(a.ic_s1, b.ic_s1)
    assert not np.array_equal(a.s1, c.s1)


# --------------------------------------------------------------------------- contrato da amostra

def test_n_precisa_ser_potencia_de_dois():
    with pytest.raises(sens.ErroSensibilidade, match="potência de 2"):
        sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=1000, semente=1, n_bootstrap=0)


def test_faixa_degenerada_e_recusada():
    with pytest.raises(sens.ErroSensibilidade, match="limite de cima"):
        sens.sobol(sens.ishigami, {"x1": (0.0, 0.0)}, n=64, semente=1, n_bootstrap=0)


def test_saida_nao_finita_e_recusada_em_vez_de_virar_indice_sem_sentido():
    with pytest.raises(sens.ErroSensibilidade, match="não finito"):
        sens.sobol(lambda x: np.full(x.shape[0], np.nan), {"a": (0.0, 1.0)}, n=64, semente=1, n_bootstrap=0)


def test_funcao_constante_devolve_indice_indefinido_e_diz_por_que():
    r = sens.sobol(lambda x: np.ones(x.shape[0]), {"a": (0.0, 1.0), "b": (0.0, 1.0)},
                   n=64, semente=1, n_bootstrap=10)
    assert np.isnan(r.s1).all() and np.isnan(r.st).all()
    assert any("variância do resultado é zero" in o for o in r.observacoes)
    assert r.irrelevantes == []  # sem variância não se declara ninguém irrelevante


def test_amostra_de_saltelli_troca_uma_coluna_por_vez():
    a, b, ab, nomes = sens.amostra_saltelli({"x": (0.0, 1.0), "y": (10.0, 20.0)}, 16, semente=2)
    assert nomes == ["x", "y"] and a.shape == (16, 2) and ab.shape == (2, 16, 2)
    assert np.array_equal(ab[0][:, 0], b[:, 0]) and np.array_equal(ab[0][:, 1], a[:, 1])
    assert np.array_equal(ab[1][:, 1], b[:, 1]) and np.array_equal(ab[1][:, 0], a[:, 0])
    assert a[:, 1].min() >= 10.0 and a[:, 1].max() <= 20.0  # a faixa declarada é respeitada


def test_grupo_troca_as_colunas_juntas_e_o_indice_sai_por_grupo():
    limites = {"a": (0.0, 1.0), "b": (0.0, 1.0), "c": (0.0, 1.0)}
    r = sens.sobol(lambda x: x[:, 0] + x[:, 1] + x[:, 2], limites, n=1024, semente=4, n_bootstrap=0,
                   grupos={"ab": ["a", "b"], "c": ["c"]})
    assert r.nomes == ["ab", "c"]
    # soma de três uniformes independentes: o grupo ab explica 2/3 da variância, c explica 1/3
    assert r.s1[0] == pytest.approx(2 / 3, abs=0.05)
    assert r.s1[1] == pytest.approx(1 / 3, abs=0.05)


def test_grupo_que_esquece_entrada_ou_repete_entrada_e_recusado():
    limites = {"a": (0.0, 1.0), "b": (0.0, 1.0)}
    with pytest.raises(sens.ErroSensibilidade, match="ficaram de fora"):
        sens.sobol(lambda x: x[:, 0], limites, n=64, semente=1, n_bootstrap=0, grupos={"g": ["a"]})
    with pytest.raises(sens.ErroSensibilidade, match="dois grupos"):
        sens.sobol(lambda x: x[:, 0], limites, n=64, semente=1, n_bootstrap=0,
                   grupos={"g": ["a", "b"], "h": ["a"]})


# --------------------------------------------------------------------------- intervalo por bootstrap

def test_intervalo_por_bootstrap_cerca_o_indice_e_encolhe_quando_n_cresce():
    pequeno = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=512, semente=3, n_bootstrap=200)
    grande = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=8192, semente=3, n_bootstrap=200)
    for r in (pequeno, grande):
        for i in range(len(r.nomes)):
            assert r.ic_st[i, 0] <= r.st[i] <= r.ic_st[i, 1]
    largura_pequeno = float((pequeno.ic_st[:, 1] - pequeno.ic_st[:, 0]).mean())
    largura_grande = float((grande.ic_st[:, 1] - grande.ic_st[:, 0]).mean())
    assert largura_grande < largura_pequeno


def test_sem_bootstrap_o_intervalo_sai_indefinido_e_nao_zero():
    r = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=256, semente=3, n_bootstrap=0)
    assert np.isnan(r.ic_s1).all() and np.isnan(r.ic_st).all()
    assert r.como_dicionario()["entradas"][0]["intervalo_total"] == [None, None]


# --------------------------------------------------------------------------- sensibilidade do modelo

def test_fator_constante_sai_como_irrelevante_e_os_outros_mandam():
    m, pesos, ids = _modelo_de_quatro_fatores()
    r = sens.sensibilidade_global(m, pesos, ids_fatores=ids, n=1024, semente=11, k_top=30, n_bootstrap=0)
    assert r.nomes == [f"peso:{i}" for i in ids]
    assert r.irrelevantes == ["peso:constante"]
    for nome, total in zip(r.nomes, r.st, strict=True):
        if nome != "peso:constante":
            assert total > sens.LIMIAR_IRRELEVANTE


def test_peso_de_fator_que_nao_existe_e_recusado():
    m, pesos, ids = _modelo_de_quatro_fatores(50)
    with pytest.raises(sens.ErroSensibilidade, match="não está no modelo"):
        sens.sensibilidade_global(m, pesos, ids_fatores=ids, n=64, semente=1, k_top=5,
                                  faixas_peso={"inexistente": (-0.2, 0.2)}, n_bootstrap=0)


def test_parametro_de_transformacao_entra_na_mesma_amostra_dos_pesos():
    """O corte de uma transformação em degrau é sorteado junto com os pesos: quando o corte manda mais
    que os pesos, o índice dele tem de sair maior que o de todos eles."""
    rng = np.random.default_rng(9)
    bruto = rng.uniform(0.0, 100.0, size=(200, 3))

    def transformacao(matriz, parametros):
        corte = parametros["corte"]
        saida = matriz.copy()
        saida[:, 0] = np.where(matriz[:, 0] >= corte, 100.0, 0.0)
        return saida

    r = sens.sensibilidade_global(
        bruto, [8.0, 1.0, 1.0], ids_fatores=["a", "b", "c"], n=512, semente=13, k_top=20,
        alvo="nota_media", transformacao=transformacao, faixas_parametros={"corte": (10.0, 90.0)},
        n_bootstrap=0,
    )
    indices = dict(zip(r.nomes, r.st, strict=True))
    assert "parametro:corte" in indices
    assert indices["parametro:corte"] > max(v for n, v in indices.items() if n.startswith("peso:"))


def test_parametro_declarado_sem_funcao_de_transformacao_e_recusado():
    m, pesos, ids = _modelo_de_quatro_fatores(50)
    with pytest.raises(sens.ErroSensibilidade, match="nenhuma função de transformação"):
        sens.sensibilidade_global(m, pesos, ids_fatores=ids, n=64, semente=1, k_top=5,
                                  faixas_parametros={"corte": (0.0, 1.0)}, n_bootstrap=0)


def test_alvo_desconhecido_e_recusado():
    m, pesos, ids = _modelo_de_quatro_fatores(50)
    with pytest.raises(sens.ErroSensibilidade, match="alvo desconhecido"):
        sens.sensibilidade_global(m, pesos, ids_fatores=ids, n=64, semente=1, alvo="melhor_peso",
                                  n_bootstrap=0)


def test_combinador_normalizado_avisa_que_o_indice_a_ler_e_o_total():
    m, pesos, ids = _modelo_de_quatro_fatores(100)
    r = sens.sensibilidade_global(m, pesos, ids_fatores=ids, n=256, semente=2, k_top=10, n_bootstrap=0)
    assert any("peso RELATIVO" in o for o in r.observacoes)


# --------------------------------------------------------------------------- tornado local (OAT)

def test_tornado_move_cada_peso_de_menos_50_a_mais_100_por_cento():
    m, pesos, ids = _modelo_de_quatro_fatores()
    t = sens.tornado_oat(m, pesos, ids_fatores=ids, k_top=30)
    assert t["faixa_peso"] == [-0.5, 1.0]
    assert [b["fator"] for b in t["barras"]][-1] == "constante"  # ordenado pela amplitude, menor no fim
    for barra in t["barras"]:
        assert barra["multiplicadores"][0] == pytest.approx(0.5)
        assert barra["multiplicadores"][-1] == pytest.approx(2.0)
        assert 0.0 <= barra["menor_concordancia"] <= 1.0
        assert barra["amplitude"] == pytest.approx(1.0 - barra["menor_concordancia"])
    constante = next(b for b in t["barras"] if b["fator"] == "constante")
    assert constante["amplitude"] == 0.0  # mover o peso de um fator constante não mexe na lista
    assert len(t["top_k_base"]) == 30


def test_tornado_com_peso_parado_no_meio_devolve_concordancia_1():
    m, pesos, ids = _modelo_de_quatro_fatores(120)
    t = sens.tornado_oat(m, pesos, ids_fatores=ids, k_top=12, faixa_peso=(-0.001, 0.001), passos=3)
    for barra in t["barras"]:
        assert barra["concordancia"][1] == pytest.approx(1.0)  # o passo do meio é o próprio peso base


def test_tornado_recusa_faixa_e_passos_invalidos():
    m, pesos, ids = _modelo_de_quatro_fatores(30)
    with pytest.raises(sens.ErroSensibilidade, match="faixa do peso"):
        sens.tornado_oat(m, pesos, ids_fatores=ids, k_top=3, faixa_peso=(-1.5, 1.0))
    with pytest.raises(sens.ErroSensibilidade, match="pelo menos 2 passos"):
        sens.tornado_oat(m, pesos, ids_fatores=ids, k_top=3, passos=1)


def test_unidade_vetada_nunca_entra_no_topk_da_sensibilidade():
    m, pesos, ids = _modelo_de_quatro_fatores(80)
    m[0, :] = 100.0  # a melhor unidade possível...
    fracao = np.zeros(80)
    fracao[0] = 1.0  # ...mas inteiramente vetada
    t = sens.tornado_oat(m, pesos, ids_fatores=ids, k_top=8, fracao_vetada=fracao)
    assert 0 not in t["top_k_base"]


# --------------------------------------------------------------------------- relatório por modelo

def test_relatorio_por_modelo_tem_n_indices_intervalo_tempo_e_o_texto_da_ressalva():
    m, pesos, ids = _modelo_de_quatro_fatores()
    r = sens.relatorio_sensibilidade(m, pesos, modelo="SIG de teste interno — galpão",
                                     versao_modelo="v1", ids_fatores=ids, n=512, semente=17, k_top=30)
    assert r["modelo"] == "SIG de teste interno — galpão" and r["versao_modelo"] == "v1"
    assert r["global"]["n"] == 512
    assert r["global"]["n_avaliacoes"] == 512 * (4 + 2)
    assert r["global"]["semente"] == 17
    assert r["global"]["n_bootstrap"] == 100 and r["global"]["nivel_confianca"] == 0.95
    for entrada in r["global"]["entradas"]:
        assert entrada["primeira_ordem"] is not None and entrada["total"] is not None
        baixo, alto = entrada["intervalo_total"]
        assert baixo is not None and alto is not None and baixo <= entrada["total"] <= alto
    assert r["tempo_s"] > 0 and r["tempo_global_s"] > 0 and r["tempo_local_s"] > 0
    assert r["irrelevantes"] == ["peso:constante"]
    assert "peso:declividade" in r["mandam_no_resultado"]
    assert r["local"]["barras"] and r["local"]["k_top"] == 30
    # a ressalva de leitura, em toda saída
    for texto in (r["texto_explicacao"], r["global"]["texto_explicacao"], r["local"]["texto_explicacao"]):
        assert "não" in texto and "importância real" in texto
    assert r["aviso"] == sens.AVISO_SENSIBILIDADE
    assert "não a importância real do fator no território" in r["aviso"]


def test_relatorio_e_serializavel_em_json():
    import json

    m, pesos, ids = _modelo_de_quatro_fatores(60)
    r = sens.relatorio_sensibilidade(m, pesos, modelo="teste", ids_fatores=ids, n=128, semente=1,
                                     k_top=6, n_bootstrap=20)
    texto = json.dumps(r, ensure_ascii=False)
    assert "NaN" not in texto and "Infinity" not in texto


def test_faixa_de_copias_alarga_por_raiz_de_n():
    assert sens.faixa_de_copias((-0.4, 0.4), 1) == (-0.4, 0.4)
    baixo, alto = sens.faixa_de_copias((-0.4, 0.4), 2)
    assert alto == pytest.approx(0.4 * math.sqrt(2)) and baixo == pytest.approx(-alto)
    with pytest.raises(sens.ErroSensibilidade, match="pelo menos 1"):
        sens.faixa_de_copias((-0.4, 0.4), 0)
