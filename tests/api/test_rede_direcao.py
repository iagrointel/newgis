"""Montante e jusante por distância ao controlador de subrede (item L4-02-b-montante-jusante).

O que cada teste prova, na ordem das cláusulas do portão:

1. `tipo=montante|jusante` no MESMO endpoint dos outros traçados, com o sentido vindo do controlador quando a
   rede tem controlador em tier hierárquico (`test_jusante_da_subestacao_*`, `test_montante_da_uc_*`);
2. jusante de um ponto = os elementos cujo caminho ao controlador passa por ele; montante = a cadeia até o
   controlador declarado (`test_jusante_do_transformador_e_so_a_baixa_tensao` e
   `test_montante_da_uc_chega_ao_controlador`);
3. laço → `direcao='indeterminado'` com os nós do laço (`test_laco_devolve_indeterminado_com_os_nos`);
4. malha (tier particionado) sem atributo de fluxo → `indeterminado`, nunca um sentido arbitrado
   (`test_tier_particionado_sem_atributo_e_indeterminado`);
5. rede sem controlador → o traçado por atributo do item L4-18 segue valendo, e a resposta diz
   `origem_direcao='atributo'` (`test_sem_controlador_cai_no_atributo`).

A cláusula do portão que fala da cooperativa de teste (jusante de cada UNTRMT × UCBT ligadas por UNI_TR_MT)
está medida em `test_rede_direcao_medida.py`, com o universo que o arquivo permite — e ele é vazio, pelo
motivo que aquele arquivo registra.

Refutação do adversário provada aqui: trocar o controlador de lado do alimentador inverte o jusante
(`test_trocar_o_controlador_de_lado_inverte_o_jusante`) — o sentido não está no desenho da linha, está no
controlador.

A rede sintética é a mesma cadeia SE — chave — transformador — UC do item L4-02-a (reusada de
`test_rede_tracado.py`, nunca reescrita), com um controlador de subrede marcado em cima."""

import pytest

from tests.api.test_rede_tracado import (
    _criar_rede,
    _habilitar,
    _importar_eletrica,
    _linha,
    _ponto,
    _rede_conhecida,
    limpar_redes,  # noqa: F401 — fixture reusada por nome pelo pytest
)


def _controlar(sessao, rid, feicao_id, subrede, tier="media_tensao", terminal=None, nome=None):
    corpo = {"feicao_id": feicao_id, "subrede": subrede, "tier": tier, "papel": "fonte"}
    if terminal is not None:
        corpo["terminal"] = terminal
    if nome is not None:
        corpo["nome"] = nome
    r = sessao.post(f"/api/rede/{rid}/controlador", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _direcao(sessao, rid, tipo, pontos, barreiras=None, origem=None):
    corpo = {"tipo": tipo, "pontos_partida": pontos}
    if barreiras:
        corpo["barreiras"] = barreiras
    if origem:
        corpo["origem_direcao"] = origem
    r = sessao.post(f"/api/rede/{rid}/tracar", json=corpo)
    return r


@pytest.fixture
def rede_com_controlador(sessao_a, env, limpar_redes):  # noqa: F811
    """Cadeia SE — chave — transformador — UC com a SUBESTAÇÃO marcada como controlador de subrede (fonte)
    no tier de média tensão."""
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "direcao")
    ctrl = _controlar(sessao_a, rid, ids["se"], "zt-alimentador", nome="zt-alimentador")
    return rid, ids, ctrl


# --- cláusulas 1 e 2: o sentido vem do controlador --------------------------------------------------------

def test_jusante_da_subestacao_pega_a_cadeia_inteira(sessao_a, rede_com_controlador):
    """A subestação é o controlador: tudo o que existe na cadeia está a jusante dela — os mesmos 9 elementos
    que o traçado `conectado` do item L4-02-a devolve, porque a cadeia inteira só chega ao controlador por
    ela."""
    rid, ids, _ = rede_com_controlador
    r = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["origem_direcao"] == "controlador" and j["direcao"] == "definida", j
    assert j["contagem"] == 9, j
    assert {e["feicao_id"] for e in j["elementos"]} == {
        ids["se"], ids["chave"], ids["l1"], ids["l2"], ids["transf"], ids["l3"], ids["uc"]}


def test_jusante_do_transformador_e_so_a_baixa_tensao(sessao_a, rede_com_controlador):
    """Jusante do terminal de BAIXA do transformador: só o que passa por ele para chegar ao controlador — o
    trecho de baixa tensão e a unidade de consumo. Nada da média tensão entra."""
    rid, ids, _ = rede_com_controlador
    r = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["transf"], "terminal": 2}])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["direcao"] == "definida", j
    achados = {e["feicao_id"] for e in j["elementos"]}
    assert achados == {ids["transf"], ids["l3"], ids["uc"]}, j
    assert ids["l1"] not in achados and ids["se"] not in achados


def test_montante_da_uc_chega_ao_controlador(sessao_a, rede_com_controlador):
    """Montante da unidade de consumo: a cadeia de volta até o controlador declarado, que sai nomeado na
    resposta (é a cláusula "montante de qualquer UC chega ao CTMT declarado")."""
    rid, ids, ctrl = rede_com_controlador
    r = _direcao(sessao_a, rid, "montante", [{"feicao_id": ids["uc"]}])
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["origem_direcao"] == "controlador" and m["direcao"] == "definida", m
    achados = {e["feicao_id"] for e in m["elementos"]}
    assert achados == {ids["uc"], ids["l3"], ids["transf"], ids["l2"], ids["chave"], ids["l1"], ids["se"]}, m
    assert [c["nome"] for c in m["controladores"]] == [ctrl["nome"]], m


def test_jusante_e_montante_sao_complementares_no_meio_da_cadeia(sessao_a, rede_com_controlador):
    """No terminal de alta do transformador, montante e jusante partem o mesmo caminho em dois: o único
    elemento em comum é o ponto de partida."""
    rid, ids, _ = rede_com_controlador
    montante = _direcao(sessao_a, rid, "montante", [{"feicao_id": ids["transf"], "terminal": 1}]).json()
    jusante = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["transf"], "terminal": 1}]).json()
    a = {(e["feicao_id"], e["terminal"]) for e in montante["elementos"]}
    b = {(e["feicao_id"], e["terminal"]) for e in jusante["elementos"]}
    assert a & b == {(ids["transf"], 1)}, (a, b)


def test_chave_aberta_corta_o_jusante(sessao_a, env, limpar_redes):  # noqa: F811
    """Chave aberta não conduz: o que está do outro lado dela deixa de ter caminho ao controlador, e some do
    jusante da subestação."""
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "direcao-aberta", chave_aberta=True)
    _controlar(sessao_a, rid, ids["se"], "zt-aberta", nome="zt-aberta")
    j = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}]).json()
    achados = {e["feicao_id"] for e in j["elementos"]}
    assert ids["se"] in achados and ids["l1"] in achados
    assert ids["l3"] not in achados and ids["uc"] not in achados, j


def test_barreira_corta_o_jusante(sessao_a, rede_com_controlador):
    rid, ids, _ = rede_com_controlador
    j = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}],
                 barreiras=[{"feicao_id": ids["transf"], "terminal": 1}]).json()
    achados = {e["feicao_id"] for e in j["elementos"]}
    assert ids["uc"] not in achados and ids["l3"] not in achados, j


# --- refutação: o sentido está no controlador, não no desenho da linha ------------------------------------

def test_trocar_o_controlador_de_lado_inverte_o_jusante(sessao_a, env, limpar_redes):  # noqa: F811
    """Refutação exigida pelo item: com o controlador na subestação, a unidade de consumo está a jusante da
    subestação. Movendo o controlador para o OUTRO LADO da chave de fronteira (sem tocar em geometria
    nenhuma), a própria subestação passa a estar a jusante da chave, e o que estava a jusante da subestação
    deixa de estar. O desenho não mudou; o sentido, sim."""
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "direcao-inverte")
    c1 = _controlar(sessao_a, rid, ids["se"], "zt-lado-a", nome="zt-lado-a")
    antes = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}]).json()
    assert ids["uc"] in {e["feicao_id"] for e in antes["elementos"]}, antes

    assert sessao_a.delete(f"/api/rede/{rid}/controlador/{c1['id']}").status_code == 204
    _controlar(sessao_a, rid, ids["transf"], "zt-lado-b", terminal=2, nome="zt-lado-b")
    depois = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["transf"], "terminal": 2}]).json()
    assert depois["direcao"] == "definida", depois
    assert ids["se"] in {e["feicao_id"] for e in depois["elementos"]}, depois
    invertido = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}]).json()
    assert {e["feicao_id"] for e in invertido["elementos"]} == {ids["se"]}, invertido


# --- cláusula 3: laço -------------------------------------------------------------------------------------

def test_laco_devolve_indeterminado_com_os_nos(sessao_a, env, limpar_redes):  # noqa: F811
    """Três trechos de média tensão fechando um triângulo: existem dois caminhos de cada vértice até o
    controlador, então "quem está acima de quem" depende do caminho. A resposta é `indeterminado` com os nós
    onde os dois caminhos se encontram — nunca um sentido escolhido pelo traçado."""
    rid = _criar_rede(sessao_a, "direcao-laco", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    a = (10.100, 20.100)
    b = (10.101, 20.100)
    c = (10.1005, 20.101)
    se = _ponto(sessao_a, rid, a[0], a[1], "subestacao")
    _linha(sessao_a, rid, [list(a), list(b)], "trecho_de_media_tensao")
    _linha(sessao_a, rid, [list(b), list(c)], "trecho_de_media_tensao")
    _linha(sessao_a, rid, [list(c), list(a)], "trecho_de_media_tensao")
    _habilitar(sessao_a, rid)
    _controlar(sessao_a, rid, se["id"], "zt-laco", nome="zt-laco")

    j = _direcao(sessao_a, rid, "jusante", [{"feicao_id": se["id"]}]).json()
    assert j["direcao"] == "indeterminado" and j["motivo"] == "laco", j
    assert j["nos_do_laco"], j
    assert j["elementos"] == [] and j["contagem"] == 0, j


# --- cláusula 4: malha (tier particionado) ----------------------------------------------------------------

def test_tier_particionado_sem_atributo_e_indeterminado(sessao_a, env, limpar_redes):  # noqa: F811
    """Controlador num tier PARTICIONADO (malha): a distância ao controlador não define sentido. Sem nenhum
    trecho declarando `direcao_fluxo`, a resposta é `indeterminado` com o motivo, nunca uma direção."""
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "direcao-malha")
    # `banco_de_capacitores` tem a categoria `controlador` no pacote elétrico; `estrutura` é o tier
    # particionado do mesmo pacote — é o par mínimo que produz um controlador em malha.
    _controlar(sessao_a, rid, ids["isolados"][0], "zt-malha", tier="estrutura", nome="zt-malha")
    j = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}]).json()
    assert j["direcao"] == "indeterminado" and j["motivo"] == "tier_particionado", j
    assert j["origem_direcao"] == "controlador" and j["contagem"] == 0, j


# --- cláusula 5: sem controlador, o atributo do item L4-18 segue valendo -----------------------------------

def test_sem_controlador_cai_no_atributo(sessao_a, rede_com_controlador, env, limpar_redes):  # noqa: F811
    """Rede sem nenhum controlador: o traçado por atributo de fluxo (item L4-18) responde, e a resposta diz
    de onde veio o sentido."""
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "direcao-sem-controlador")
    j = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}]).json()
    assert j["origem_direcao"] == "atributo", j
    assert j["contagem"] > 0, j


def test_origem_controlador_imposta_sem_controlador_recusa(sessao_a, env, limpar_redes):  # noqa: F811
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "direcao-imposta")
    r = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}], origem="controlador")
    assert r.status_code == 409 and r.json()["erro"] == "sem_controlador", r.text


def test_origem_atributo_imposta_ignora_o_controlador(sessao_a, rede_com_controlador):
    rid, ids, _ = rede_com_controlador
    j = _direcao(sessao_a, rid, "jusante", [{"feicao_id": ids["se"]}], origem="atributo").json()
    assert j["origem_direcao"] == "atributo", j
