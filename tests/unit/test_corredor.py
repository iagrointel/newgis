"""Motor de traçado linear: composição da superfície, caminho de custo mínimo e corredor-epsilon
(item L3-10-corredor-custo-minimo).

Aqui ficam as INVARIANTES em grade pequena, onde o resultado certo se escreve à mão: os dois motores
(`fila` e `esparso`) têm de dar o mesmo custo, a diagonal não se espreme entre dois vetos, o salto de cavalo
não pula por cima de veto, o corredor contém o caminho ótimo e cresce com o epsilon. A reprodução do trecho
de referência da casa está em `test_corredor_referencia.py`, que só roda com o arquivo à mão."""

import numpy as np
import pytest

from app.amc import corredor as C

MOTORES = ("fila", "esparso")


def grade(lin=9, col=9, valor=1.0):
    return np.full((lin, col), valor, dtype=np.float32), np.zeros((lin, col), dtype=bool)


@pytest.mark.parametrize("motor", MOTORES)
def test_reta_em_grade_uniforme_custa_o_comprimento(motor):
    custo, veto = grade()
    r = C.caminho(custo, veto, (0, 0), (0, 8), motor=motor)
    assert r["celulas_percorridas"] == 9
    assert r["custo"] == pytest.approx(8.0)
    assert C.sinuosidade(r["celulas"]) == pytest.approx(1.0)


@pytest.mark.parametrize("motor", MOTORES)
def test_os_dois_motores_dao_o_mesmo_custo_em_superficie_irregular(motor):
    rng = np.random.default_rng(7)
    custo = rng.uniform(1.0, 9.0, size=(40, 40)).astype(np.float32)
    veto = rng.random((40, 40)) < 0.15
    veto[0, 0] = veto[39, 39] = False
    r = C.caminho(custo, veto, (0, 0), (39, 39), motor=motor)
    esperado = C.caminho(custo, veto, (0, 0), (39, 39), motor="fila")["custo"]
    assert r["custo"] == pytest.approx(esperado, rel=1e-6)
    # nenhuma célula do caminho é vetada, e cada passo é um dos 16 deslocamentos
    passos = np.abs(np.diff(r["celulas"], axis=0))
    assert not veto[r["celulas"][:, 0], r["celulas"][:, 1]].any()
    assert set(map(tuple, passos)) <= {(abs(a), abs(b)) for a, b in C.PASSOS_8 + C.PASSOS_CAVALO}


@pytest.mark.parametrize("motor", MOTORES)
def test_diagonal_nao_se_espreme_entre_dois_vetos(motor):
    """Com (0,1) e (1,0) vetados, o passo (0,0)->(1,1) não existe: (0,0) fica sem saída nenhuma (os saltos de
    cavalo também atravessam uma das duas células vetadas), e o motor diz `sem_caminho` em vez de espremer."""
    custo, veto = grade(3, 3)
    veto[0, 1] = veto[1, 0] = True
    with pytest.raises(C.ErroCorredor) as e:
        C.caminho(custo, veto, (0, 0), (2, 2), motor=motor)
    assert e.value.codigo == "sem_caminho"


@pytest.mark.parametrize("motor", MOTORES)
def test_diagonal_passa_com_um_ortogonal_livre(motor):
    """Um só dos dois ortogonais vetado: a diagonal existe (é a regra do motor de referência da casa)."""
    custo, veto = grade(3, 3)
    veto[0, 1] = True
    r = C.caminho(custo, veto, (0, 0), (1, 1), motor=motor)
    assert [tuple(x) for x in r["celulas"]] == [(0, 0), (1, 1)]
    assert r["custo"] == pytest.approx(np.sqrt(2.0))


@pytest.mark.parametrize("motor", MOTORES)
def test_salto_de_cavalo_nao_pula_por_cima_de_veto(motor):
    """Parede vertical inteira com uma única passagem: o caminho passa pela passagem, nunca por cima."""
    custo, veto = grade(9, 9)
    veto[:, 4] = True
    veto[7, 4] = False
    r = C.caminho(custo, veto, (0, 0), (0, 8), motor=motor)
    assert (7, 4) in [tuple(x) for x in r["celulas"]]
    assert not veto[r["celulas"][:, 0], r["celulas"][:, 1]].any()


@pytest.mark.parametrize("motor", MOTORES)
def test_sem_caminho_quando_a_parede_e_inteira(motor):
    custo, veto = grade(9, 9)
    veto[:, 4] = True
    with pytest.raises(C.ErroCorredor) as e:
        C.caminho(custo, veto, (0, 0), (0, 8), motor=motor)
    assert e.value.codigo == "sem_caminho"


@pytest.mark.parametrize("motor", MOTORES)
def test_ponto_em_veto_e_fora_da_grade_sao_recusados(motor):
    custo, veto = grade()
    veto[0, 0] = True
    with pytest.raises(C.ErroCorredor) as e:
        C.caminho(custo, veto, (0, 0), (8, 8), motor=motor)
    assert e.value.codigo == "ponto_em_veto"
    with pytest.raises(C.ErroCorredor) as e:
        C.caminho(custo, veto, (1, 1), (99, 8), motor=motor)
    assert e.value.codigo == "ponto_fora_da_grade"


def test_vizinhanca_e_motor_invalidos():
    custo, veto = grade()
    with pytest.raises(C.ErroCorredor) as e:
        C.caminho(custo, veto, (0, 0), (8, 8), vizinhanca=5)
    assert e.value.codigo == "vizinhanca_invalida"
    with pytest.raises(C.ErroCorredor) as e:
        C.caminho(custo, veto, (0, 0), (8, 8), motor="turbo")
    assert e.value.codigo == "motor_invalido"


@pytest.mark.parametrize("motor", MOTORES)
def test_o_caminho_desvia_do_caro_e_a_conta_fecha(motor):
    """Faixa cara no meio: o caminho ou paga a faixa ou contorna, e o custo é sempre o menor dos dois."""
    custo, veto = grade(11, 11)
    custo[5, :] = 50.0
    custo[5, 9] = 1.0            # uma passagem barata na faixa
    r = C.caminho(custo, veto, (0, 0), (10, 0), motor=motor)
    assert (5, 9) in [tuple(x) for x in r["celulas"]]
    assert r["custo"] < 50.0


@pytest.mark.parametrize("motor", MOTORES)
def test_corredor_contem_o_caminho_e_cresce_com_o_epsilon(motor):
    rng = np.random.default_rng(3)
    custo = rng.uniform(1.0, 4.0, size=(30, 30)).astype(np.float32)
    veto = np.zeros((30, 30), dtype=bool)
    linha = C.caminho(custo, veto, (0, 0), (29, 29), motor=motor)
    c0 = C.corredor(custo, veto, (0, 0), (29, 29), epsilon=0.0, motor=motor)
    c5 = C.corredor(custo, veto, (0, 0), (29, 29), epsilon=0.05, motor=motor)
    c10 = C.corredor(custo, veto, (0, 0), (29, 29), epsilon=0.10, motor=motor)
    assert c0["mascara"][linha["celulas"][:, 0], linha["celulas"][:, 1]].all()
    assert c0["celulas"] <= c5["celulas"] <= c10["celulas"]
    assert c5["otimo"] == pytest.approx(linha["custo"], rel=1e-6)
    assert c5["teto"] == pytest.approx(linha["custo"] * 1.05, rel=1e-6)


def test_corredor_nunca_inclui_celula_vetada():
    rng = np.random.default_rng(11)
    custo = rng.uniform(1.0, 4.0, size=(25, 25)).astype(np.float32)
    veto = rng.random((25, 25)) < 0.2
    veto[0, 0] = veto[24, 24] = False
    faixa = C.corredor(custo, veto, (0, 0), (24, 24), epsilon=0.2)
    assert not (faixa["mascara"] & veto).any()


def test_epsilon_fora_do_limite():
    custo, veto = grade()
    with pytest.raises(C.ErroCorredor) as e:
        C.corredor(custo, veto, (0, 0), (8, 8), epsilon=1.5)
    assert e.value.codigo == "epsilon_fora_do_limite"


def test_composicao_por_maximo_nao_depende_da_ordem_e_o_veto_vence():
    forma = (12, 12)
    a = np.zeros(forma, dtype=bool)
    a[4:8, :] = True
    b = np.zeros(forma, dtype=bool)
    b[:, 4:8] = True
    v = np.zeros(forma, dtype=bool)
    v[6, 6] = True
    c1 = C.Camada("a", "custo", a, peso=3.0)
    c2 = C.Camada("b", "custo", b, peso=5.0)
    cv = C.Camada("v", "veto", v)
    s1 = C.compor([c1, c2, cv], forma=forma)
    s2 = C.compor([c2, cv, c1], forma=forma)
    assert np.array_equal(s1.custo, s2.custo) and np.array_equal(s1.veto, s2.veto)
    assert s1.custo[5, 5] == pytest.approx(5.0)     # máximo, não soma
    assert s1.custo[5, 0] == pytest.approx(3.0)
    assert s1.custo[0, 0] == pytest.approx(1.0)
    assert s1.veto[6, 6] and s1.custo[6, 6] == C.CUSTO_VETO


def test_atracao_e_passada_final_com_piso():
    forma = (10, 10)
    caro = np.ones(forma, dtype=bool)
    junto = np.zeros(forma, dtype=bool)
    junto[3, :] = True
    s = C.compor([C.Camada("caro", "custo", caro, peso=4.0),
                  C.Camada("faixa", "atrai", junto, valor=0.1)], forma=forma, min_atracao=0.55)
    assert s.custo[3, 3] == pytest.approx(4.0 * 0.55)   # o piso segura o desconto
    assert s.custo[0, 0] == pytest.approx(4.0)


def test_compressao_de_amplitude_e_monotona_e_tem_ponto_fixo_em_um():
    rng = np.random.default_rng(5)
    pen = rng.uniform(1.0, 60.0, size=(20, 20)).astype(np.float32)
    pen[0, 0] = 1.0
    veto = np.zeros((20, 20), dtype=bool)
    comprimido, diag = C.comprimir_amplitude(pen, veto, alvo=8.0)
    assert comprimido[0, 0] == pytest.approx(1.0)
    ordem_antes = np.argsort(pen, axis=None)
    ordem_depois = np.argsort(comprimido, axis=None)
    assert np.array_equal(ordem_antes, ordem_depois)     # a hierarquia sobrevive
    assert comprimido.max() == pytest.approx(8.0, rel=1e-4)
    assert diag["alfa"] < 1.0


def test_curva_de_relevo_por_faixa():
    decl = np.array([[0.0, 5.0], [30.0, 90.0]], dtype=np.float32)
    f = C.curva_relevo(decl)
    assert f[0, 0] == pytest.approx(1.00) and f[0, 1] == pytest.approx(1.10)
    assert f[1, 0] == pytest.approx(1.90) and f[1, 1] == pytest.approx(2.60)


def test_metricas_contam_km_por_camada_no_eixo():
    custo, veto = grade(11, 11)
    dentro = np.zeros((11, 11), dtype=bool)
    dentro[:, :6] = True
    r = C.caminho(custo, veto, (0, 0), (0, 10))
    m = C.metricas(r["celulas"], custo, resolucao_m=100.0, camadas=[C.Camada("uc", "custo", dentro, peso=2.0)])
    assert m["comprimento_km"] == pytest.approx(1.0)      # 10 passos de 100 m
    assert m["sinuosidade"] == pytest.approx(1.0)
    assert m["km_por_camada"]["uc"] == pytest.approx(0.6, abs=0.101)
