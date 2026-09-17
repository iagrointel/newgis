"""Item L3-04-restricoes — o COMBINADOR de restrições (`app.amc.restricao.compor`) medido contra um caso
calculado À MÃO, escrito por extenso neste arquivo.

Por que um arquivo separado de `tests/unit/test_amc_restricao.py`: aquele prova a AVALIAÇÃO de cada
restrição contra o banco (`ST_Intersects`/`ST_DWithin` recomputados fora do módulo). Este prova a
COMPOSIÇÃO — a parte pura, sem banco — e faz isso com um caso cujo resultado esperado foi calculado à
mão, nunca copiado da saída do próprio código. É a diferença entre o teste provar a conta e o teste
provar que o código concorda consigo mesmo.

Cláusulas do `portao_de_pronto` medidas aqui (o resto do portão está no arquivo vizinho):
- "composição por OU" com restrições SOBREPOSTAS (a mesma unidade vetada por mais de uma restrição);
- "unidade restrita = favorabilidade 0 com motivo e contagem separada por restrição" — a contagem por
  restrição é conferida contra a tabela-verdade escrita à mão, inclusive quando a soma das contagens é
  MAIOR que o total vetado (é exatamente o que a sobreposição produz);
- "restrição nunca é sorteada em robustez" não é deste arquivo (é do módulo `app.amc.robustez`).

O CASO, escrito à mão (tabela-verdade declarada, não medida):

    unidade      u0   u1   u2   u3   u4   u5
    R1 (norma)    V    V    .    .    .    .
    R2 (precau)   .    V    V    V    .    .
    R3 (norma)    V    .    V    .    V    .

Contas feitas à mão a partir dessa tabela, antes de rodar o código:

  contagem por restrição (cada uma conta as SUAS unidades, sem descontar sobreposição):
      R1 = 2 (u0, u1)   R2 = 3 (u1, u2, u3)   R3 = 3 (u0, u2, u4)   soma = 8

  composição por OU (uma unidade basta uma restrição para ser vetada):
      vetadas = {u0, u1, u2, u3, u4} = 5 unidades; livre = {u5}
      fracao_vetada = [1,0; 1,0; 1,0; 1,0; 1,0; 0,0]
      conferência da diferença 8 − 5 = 3: são as três sobreposições — u0 (R1 e R3), u1 (R1 e R2) e
      u2 (R2 e R3). Nenhuma unidade é vetada por 3 restrições neste caso.

  motivo (a PRIMEIRA restrição, na ordem declarada, que vetou a unidade):
      u0 → R1 (norma)      u1 → R1 (norma)      u2 → R2 (precaução)
      u3 → R2 (precaução)  u4 → R3 (norma)      u5 → nenhum

  a mesma tabela na ordem declarada INVERTIDA [R3, R2, R1] muda SÓ o motivo, nunca a fração nem a
  contagem:
      u0 → R3 (norma)      u1 → R2 (precaução)  u2 → R3 (norma)
      u3 → R2 (precaução)  u4 → R3 (norma)      u5 → nenhum
"""

import pytest

from app.amc import combinacao
from app.amc.restricao import compor

IDS = ["u0", "u1", "u2", "u3", "u4", "u5"]

# tabela-verdade escrita à mão (True = a restrição veta aquela unidade)
TABELA = {
    "R1": [True,  True,  False, False, False, False],
    "R2": [False, True,  True,  True,  False, False],
    "R3": [True,  False, True,  False, True,  False],
}

R1 = {"id": "R1", "nome": "unidade de conservação", "base": "norma",
      "base_legal": "Lei fictícia 1.111/2026", "motivo": "sobreposição com UC de proteção integral",
      "fonte": "camada de teste", "regra": {"tipo": "intersecta"}}
R2 = {"id": "R2", "nome": "distância de nascente", "base": "precaucao",
      "motivo": "faixa de precaução da casa ao redor da nascente", "fonte": "camada de teste",
      "buffer_m": 100.0, "regra": {"tipo": "intersecta"}}
R3 = {"id": "R3", "nome": "fração em várzea", "base": "norma",
      "base_legal": "Lei fictícia 2.222/2026", "motivo": "fração em área de várzea acima do limiar",
      "fonte": "camada de teste", "regra": {"tipo": "fracao_area_minima", "fracao_minima": 0.3}}


def _resultado(chave: str) -> dict[str, dict]:
    """Converte uma linha da tabela-verdade na forma que `avaliar` devolve, sem tocar no banco: a
    correção do `avaliar` contra PostGIS está em tests/unit/test_amc_restricao.py."""
    return {uid: {"vetada": veta, "fracao_intersectada": None}
            for uid, veta in zip(IDS, TABELA[chave], strict=True)}


def _avaliacoes(ordem: list[dict]) -> list[tuple[dict, dict[str, dict]]]:
    return [(r, _resultado(r["id"])) for r in ordem]


def test_fracao_vetada_bate_com_o_ou_calculado_a_mao():
    composto = compor(IDS, _avaliacoes([R1, R2, R3]))
    # calculado à mão a partir da tabela-verdade do cabeçalho: u0..u4 vetadas, u5 livre
    assert composto["fracao_vetada"] == [1.0, 1.0, 1.0, 1.0, 1.0, 0.0]
    assert composto["unidades_vetadas_total"] == 5


def test_contagem_por_restricao_bate_com_a_tabela_e_soma_mais_que_o_total_vetado():
    """A contagem é POR restrição e não desconta sobreposição: 2 + 3 + 3 = 8 contra 5 unidades vetadas
    no OU. A diferença de 3 são as três sobreposições (u0, u1, u2), contadas à mão no cabeçalho."""
    composto = compor(IDS, _avaliacoes([R1, R2, R3]))
    contagem = {c["id"]: c["unidades_vetadas"] for c in composto["contagem_por_restricao"]}
    assert contagem == {"R1": 2, "R2": 3, "R3": 3}
    assert sum(contagem.values()) == 8
    assert composto["unidades_vetadas_total"] == 5
    assert sum(contagem.values()) - composto["unidades_vetadas_total"] == 3
    for c in composto["contagem_por_restricao"]:
        assert c["total_unidades"] == 6
        assert c["base"] in ("norma", "precaucao")


def test_veto_nunca_pesa_unidade_vetada_por_duas_restricoes_continua_fracao_1():
    """u0 é vetada por R1 E R3; u1 por R1 E R2; u2 por R2 E R3. Veto não soma: a fração final de cada
    uma tem de ser exatamente 1,0 — nunca 2,0, nunca um veto 'mais forte' que outro."""
    composto = compor(IDS, _avaliacoes([R1, R2, R3]))
    for i in (0, 1, 2):
        assert composto["fracao_vetada"][i] == 1.0
    assert set(composto["fracao_vetada"]) == {0.0, 1.0}


def test_motivo_e_o_da_primeira_restricao_na_ordem_declarada():
    composto = compor(IDS, _avaliacoes([R1, R2, R3]))
    motivo = dict(zip(IDS, composto["motivo"], strict=True))
    # calculado à mão: u0,u1 → R1 (norma); u2,u3 → R2 (precaução); u4 → R3 (norma); u5 → nenhum
    assert motivo["u0"].startswith("a norma veda: ") and "1.111/2026" in motivo["u0"]
    assert motivo["u1"].startswith("a norma veda: ") and "1.111/2026" in motivo["u1"]
    assert motivo["u2"].startswith("vetamos por precaução: ")
    assert motivo["u3"].startswith("vetamos por precaução: ")
    assert motivo["u4"].startswith("a norma veda: ") and "2.222/2026" in motivo["u4"]
    assert motivo["u5"] is None


def test_ordem_declarada_invertida_muda_so_o_motivo():
    direto = compor(IDS, _avaliacoes([R1, R2, R3]))
    invertido = compor(IDS, _avaliacoes([R3, R2, R1]))
    assert invertido["fracao_vetada"] == direto["fracao_vetada"]
    assert invertido["unidades_vetadas_total"] == direto["unidades_vetadas_total"]
    contagem = {c["id"]: c["unidades_vetadas"] for c in invertido["contagem_por_restricao"]}
    assert contagem == {"R1": 2, "R2": 3, "R3": 3}
    motivo = dict(zip(IDS, invertido["motivo"], strict=True))
    # calculado à mão para a ordem [R3, R2, R1]
    assert "2.222/2026" in motivo["u0"]                       # u0 agora é R3
    assert motivo["u1"].startswith("vetamos por precaução: ")  # u1 agora é R2
    assert "2.222/2026" in motivo["u2"]                       # u2 agora é R3
    assert motivo["u3"].startswith("vetamos por precaução: ")
    assert "2.222/2026" in motivo["u4"]
    assert motivo["u5"] is None


def test_favorabilidade_final_calculada_a_mao_zera_nas_vetadas_e_preserva_a_livre():
    """Conta feita à mão: dois fatores, pesos 1 e 3 (o combinador normaliza pela soma, 4).
    Para toda unidade os fatores são 80 e 40, logo a nota SEM veto é (1·80 + 3·40)/4 = 200/4 = 50,0.
    Com o veto, as 5 unidades vetadas saem em 0,0 e só u5 fica com 50,0."""
    composto = compor(IDS, _avaliacoes([R1, R2, R3]))
    fatores = [[80.0, 40.0] for _ in IDS]
    res = combinacao.combinar(
        fatores, [1.0, 3.0], fracao_vetada=composto["fracao_vetada"],
        motivo_veto=composto["motivo"], ids_fatores=["f_a", "f_b"],
    )
    assert [float(v) for v in res.fav] == [0.0, 0.0, 0.0, 0.0, 0.0, 50.0]
    for i in range(5):
        assert bool(res.vetado[i]) is True
        assert res.motivo[i] == composto["motivo"][i]
    assert not bool(res.vetado[5])
    assert res.motivo[5] is None


def test_par_positivo_nenhuma_restricao_veta_nada_nao_vira_veto_silencioso():
    """Par positivo da recusa: com as três restrições avaliadas e NENHUMA vetando, a composição devolve
    fração 0 para todo mundo, motivo nenhum e contagem zerada — o combinador preserva os 50,0 calculados
    à mão acima. Provar que barra o inválido não basta: tem de provar que deixa passar o válido."""
    vazio = {uid: {"vetada": False, "fracao_intersectada": None} for uid in IDS}
    composto = compor(IDS, [(R1, vazio), (R2, vazio), (R3, vazio)])
    assert composto["fracao_vetada"] == [0.0] * 6
    assert composto["motivo"] == [None] * 6
    assert composto["unidades_vetadas_total"] == 0
    assert [c["unidades_vetadas"] for c in composto["contagem_por_restricao"]] == [0, 0, 0]
    res = combinacao.combinar([[80.0, 40.0] for _ in IDS], [1.0, 3.0],
                              fracao_vetada=composto["fracao_vetada"], ids_fatores=["f_a", "f_b"])
    assert [float(v) for v in res.fav] == [50.0] * 6


def test_restricao_sem_resultado_para_uma_unidade_nao_veta_por_omissao():
    """Se o dicionário de avaliação não traz uma unidade (por exemplo, a consulta não a devolveu), a
    composição tem de tratar como NÃO vetada, nunca como vetada por omissão. Calculado à mão: só u1
    aparece vetada, logo fração = [0, 1, 0, 0, 0, 0] e total = 1."""
    parcial = {"u1": {"vetada": True, "fracao_intersectada": None}}
    composto = compor(IDS, [(R1, parcial)])
    assert composto["fracao_vetada"] == [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    assert composto["unidades_vetadas_total"] == 1
    assert composto["contagem_por_restricao"][0]["unidades_vetadas"] == 1


def test_lista_de_avaliacoes_vazia_nao_veta_ninguem_e_nao_quebra():
    composto = compor(IDS, [])
    assert composto["fracao_vetada"] == [0.0] * 6
    assert composto["contagem_por_restricao"] == []
    assert composto["unidades_vetadas_total"] == 0


def test_motivo_de_base_desconhecida_e_recusado_na_composicao():
    """Recusa: uma restrição com `base` fora de {norma, precaucao} não pode produzir motivo em silêncio
    (seria uma frase inventada no relatório). O par positivo é todo o resto deste arquivo, onde as bases
    declaradas são aceitas e produzem a frase certa."""
    from app.amc.restricao import ErroRestricao
    ruim = dict(R1)
    ruim["base"] = "achismo"
    with pytest.raises(ErroRestricao) as e:
        compor(IDS, [(ruim, _resultado("R1"))])
    assert e.value.codigo == "base_desconhecida"
