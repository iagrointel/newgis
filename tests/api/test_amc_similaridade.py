"""Item L3-17-similaridade — os VIZINHOS ESPERADOS de um conjunto pequeno e conhecido, pela API
`POST /api/amc/similaridade`, contra um exemplo calculado À MÃO e escrito por extenso aqui.

Arquivo separado de `tests/api/amc/test_amc_similaridade_api.py` de propósito: aquele prova o contrato
HTTP (campos da resposta, 422 de métrica e de referência, exportação, autenticação). Este mede a cláusula
do `portao_de_pronto` que só vale com número de fora — "reproduz exemplo numérico de referência" — e a
ordem dos vizinhos que sai dele.

## O exemplo, calculado à mão

Quatro unidades nos quatro cantos de um quadrado, em dois campos:

    unidade   x   y
    A         0   0
    B         0   4
    C         4   0
    D         4   4

Padronização por z-score com desvio POPULACIONAL (ddof = 0), que é o que o módulo declara usar:

    campo x: valores 0, 0, 4, 4 → média = 2; variância = ((-2)² + (-2)² + 2² + 2²)/4 = 16/4 = 4 → desvio = 2
    campo y: valores 0, 4, 0, 4 → média = 2; variância = 4 → desvio = 2

    z(A) = (−1, −1)   z(B) = (−1, +1)   z(C) = (+1, −1)   z(D) = (+1, +1)

Os quatro vetores padronizados são os cantos do quadrado [−1, 1]². Com A como única referência, o
centroide de referência é o próprio z(A) = (−1, −1).

**Distância euclidiana** no espaço padronizado, e o índice `1/(1 + d)` que o módulo declara:

    d(A,A) = 0                        → índice = 1/(1+0)           = 1,0
    d(B,A) = |(0, 2)| = 2             → índice = 1/(1+2)           = 1/3 = 0,3333333…
    d(C,A) = |(2, 0)| = 2             → índice = 1/3 = 0,3333333…
    d(D,A) = |(2, 2)| = 2·√2 = 2,8284271 → índice = 1/3,8284271    = 0,2612039…

**Cosseno** com o centroide (−1, −1), e o índice `(cos + 1)/2`:

    A: produto interno 2, normas √2·√2 = 2 → cos = +1 → índice = (1+1)/2   = 1,0
    B: produto interno (−1)(−1) + (1)(−1) = 0 → cos = 0  → índice = (0+1)/2 = 0,5
    C: produto interno (1)(−1) + (−1)(−1) = 0 → cos = 0  → índice = 0,5
    D: produto interno −2, normas 2 → cos = −1 → índice = (−1+1)/2 = 0,0

**Ordem esperada dos vizinhos**, nas duas métricas: A, B, C, D. B e C empatam (0,3333… na euclidiana,
0,5 no cosseno) e o desempate declarado pelo módulo é por distância euclidiana padronizada crescente
(empatada também, 2 = 2) e depois por `unidade_id` crescente — logo B antes de C, deterministicamente.

Nenhum desses números saiu de `app.amc.similaridade`: todos vêm da conta acima.
"""

import math

UNIDADES = {
    "A": {"x": 0.0, "y": 0.0},
    "B": {"x": 0.0, "y": 4.0},
    "C": {"x": 4.0, "y": 0.0},
    "D": {"x": 4.0, "y": 4.0},
}

# índices calculados à mão no cabeçalho
EUCLIDIANA = {"A": 1.0, "B": 1.0 / 3.0, "C": 1.0 / 3.0, "D": 1.0 / (1.0 + 2.0 * math.sqrt(2.0))}
COSSENO = {"A": 1.0, "B": 0.5, "C": 0.5, "D": 0.0}
ORDEM_ESPERADA = ["A", "B", "C", "D"]


def _ranking(sessao, **extra) -> list[dict]:
    r = sessao.post("/api/amc/similaridade",
                    json={"unidades": UNIDADES, "referencias": ["A"], **extra})
    assert r.status_code == 200, r.text
    return r.json()["ranking"]


def test_estatisticas_batem_com_a_padronizacao_calculada_a_mao(sessao_a):
    """Média 2 e desvio populacional 2 nos dois campos — a base de toda a conta do cabeçalho. Se o módulo
    usasse desvio amostral (ddof = 1), daria 2,309 e todos os índices abaixo mudariam."""
    r = sessao_a.post("/api/amc/similaridade", json={"unidades": UNIDADES, "referencias": ["A"]})
    assert r.status_code == 200, r.text
    est = r.json()["estatisticas"]
    for campo in ("x", "y"):
        assert est[campo]["media"] == 2.0, campo
        assert abs(est[campo]["desvio"] - 2.0) < 1e-12, campo


def test_vizinhos_esperados_pela_distancia_euclidiana(sessao_a):
    ranking = _ranking(sessao_a, metrica="euclidiana")
    assert [u["unidade_id"] for u in ranking] == ORDEM_ESPERADA
    assert [u["posicao"] for u in ranking] == [1, 2, 3, 4]
    for u in ranking:
        esperado = EUCLIDIANA[u["unidade_id"]]
        assert abs(u["indice_similaridade"] - esperado) < 1e-9, (u, esperado)


def test_vizinhos_esperados_pelo_cosseno(sessao_a):
    ranking = _ranking(sessao_a, metrica="cosseno")
    assert [u["unidade_id"] for u in ranking] == ORDEM_ESPERADA
    for u in ranking:
        esperado = COSSENO[u["unidade_id"]]
        assert abs(u["indice_similaridade"] - esperado) < 1e-9, (u, esperado)


def test_empate_de_b_e_c_e_desempatado_por_id_de_forma_deterministica(sessao_a):
    """B e C são simétricos em relação a A: empatam no índice nas duas métricas. O desempate declarado é
    por id crescente, então a ordem tem de ser a MESMA em repetições e nas duas métricas."""
    for metrica in ("cosseno", "euclidiana"):
        ordens = [[u["unidade_id"] for u in _ranking(sessao_a, metrica=metrica)] for _ in range(3)]
        assert ordens == [ORDEM_ESPERADA] * 3, (metrica, ordens)
    cos = {u["unidade_id"]: u["indice_similaridade"] for u in _ranking(sessao_a, metrica="cosseno")}
    assert abs(cos["B"] - cos["C"]) < 1e-12


def test_o_oposto_da_referencia_fica_em_ultimo_nas_duas_metricas(sessao_a):
    """D é o canto oposto a A no quadrado padronizado: cosseno −1 (índice 0,0 exato) e a maior distância
    euclidiana (2√2). Tem de fechar o ranking nas duas métricas, nunca ficar no meio."""
    for metrica in ("cosseno", "euclidiana"):
        ranking = _ranking(sessao_a, metrica=metrica)
        assert ranking[-1]["unidade_id"] == "D", (metrica, ranking)
    cos = {u["unidade_id"]: u["indice_similaridade"] for u in _ranking(sessao_a, metrica="cosseno")}
    assert abs(cos["D"] - 0.0) < 1e-12


def test_referencia_igual_ao_candidato_da_indice_1_e_primeiro_lugar(sessao_a):
    """Refutação declarada do item. Vale nas duas métricas porque as duas dão 1,0 exato quando o vetor da
    unidade é idêntico ao centroide de referência (conta do cabeçalho)."""
    for metrica in ("cosseno", "euclidiana"):
        ranking = _ranking(sessao_a, metrica=metrica)
        assert ranking[0]["unidade_id"] == "A" and ranking[0]["posicao"] == 1, metrica
        assert abs(ranking[0]["indice_similaridade"] - 1.0) < 1e-12, metrica


def test_duas_referencias_dao_o_centroide_calculado_a_mao(sessao_a):
    """Com A e D como referências, o centroide é a média de z(A) = (−1,−1) e z(D) = (+1,+1), ou seja
    (0, 0) — o vetor nulo. Não existe ângulo com o vetor nulo: o cosseno é indefinido, e o módulo tem de
    dizer isso ou devolver um valor declarado, nunca um NaN escondido no ranking.
    Na métrica euclidiana a conta é exata: d(A) = d(B) = d(C) = d(D) = √2 = 1,4142136, logo TODAS as
    quatro empatam em índice 1/(1+√2) = 0,4142136 e a ordem vira a alfabética do desempate."""
    r = sessao_a.post("/api/amc/similaridade",
                      json={"unidades": UNIDADES, "referencias": ["A", "D"], "metrica": "euclidiana"})
    assert r.status_code == 200, r.text
    ranking = r.json()["ranking"]
    esperado = 1.0 / (1.0 + math.sqrt(2.0))
    for u in ranking:
        assert abs(u["indice_similaridade"] - esperado) < 1e-9, u
    assert [u["unidade_id"] for u in ranking] == ORDEM_ESPERADA


def test_campo_sem_variacao_nao_discrimina_e_nao_divide_por_zero(sessao_a):
    """Par positivo da convenção declarada no módulo: um terceiro campo com o MESMO valor em todas as
    unidades tem desvio 0 e não pode mudar nada — os índices calculados à mão continuam valendo, e não
    pode aparecer NaN nem erro 500."""
    unidades = {k: {**v, "z": 7.0} for k, v in UNIDADES.items()}
    r = sessao_a.post("/api/amc/similaridade",
                      json={"unidades": unidades, "referencias": ["A"], "metrica": "euclidiana"})
    assert r.status_code == 200, r.text
    ranking = r.json()["ranking"]
    assert [u["unidade_id"] for u in ranking] == ORDEM_ESPERADA
    for u in ranking:
        assert abs(u["indice_similaridade"] - EUCLIDIANA[u["unidade_id"]]) < 1e-9, u


def test_escolher_so_um_campo_muda_os_vizinhos_de_forma_previsivel(sessao_a):
    """Escolhendo só `y`, a dimensão x some: z(A) = z(C) = −1 e z(B) = z(D) = +1. Pela euclidiana, A e C
    ficam a distância 0 da referência (índice 1,0) e B e D a distância 2 (índice 1/3). Ordem esperada,
    com o desempate por id: A, C, B, D — diferente da ordem com os dois campos."""
    r = sessao_a.post("/api/amc/similaridade",
                      json={"unidades": UNIDADES, "referencias": ["A"], "campos": ["y"],
                            "metrica": "euclidiana"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["campos"] == ["y"]
    ranking = corpo["ranking"]
    assert [u["unidade_id"] for u in ranking] == ["A", "C", "B", "D"]
    indices = {u["unidade_id"]: u["indice_similaridade"] for u in ranking}
    assert abs(indices["A"] - 1.0) < 1e-12 and abs(indices["C"] - 1.0) < 1e-12
    assert abs(indices["B"] - 1.0 / 3.0) < 1e-9 and abs(indices["D"] - 1.0 / 3.0) < 1e-9
