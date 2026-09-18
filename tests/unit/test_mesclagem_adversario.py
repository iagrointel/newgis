"""Adversário de linha L5 builder (parte 1) — item L5-13-edicao-concorrente
(`app/catalogo/mesclagem.py`).

Achado: uma LIGAÇÃO não tem id próprio — `mesclar()` a identifica pelo JSON canônico do objeto inteiro
("cada ligação identificada pelo seu JSON canônico [...] a lista é um conjunto", docstring do módulo).
Quando os dois lados editam um CAMPO da MESMA ligação lógica (mesma `de`/`para`, ex.: o `tipo` da relação)
a partir da mesma base, cada lado produz uma chave canônica DIFERENTE — não existe "a mesma unidade
mudada dos dois lados" para `_tres_vias` comparar, então as duas versões entram como duas ADIÇÕES
independentes. Resultado: a ligação original desaparece (as duas concordam em removê-la, cada uma na sua
leitura) e as DUAS variantes conflitantes (`tipo: seleciona` e `tipo: zoom`, no teste abaixo) sobrevivem
juntas no documento final, com `Resultado.ok is True` — nenhum conflito relatado, nenhum aviso.

Isso não é "perde alteração" (a cláusula literal do portão) — é o oposto e, para o produto, pior: as DUAS
alterações concorrentes sobrevivem silenciosamente misturadas (duas ligações contraditórias entre os
mesmos dois nós), quando o usuário esperava que sua edição SUBSTITUÍSSE a ligação anterior. Nenhum teste
oficial (`tests/unit/test_mesclagem.py`) edita a MESMA ligação lógica dos dois lados — o único teste de
ligação (`test_no_criado_no_servidor_entra_depois_do_antecessor_e_ligacoes_sao_conjunto`) tem um lado
REMOVENDO e o outro mantendo, nunca os dois lados MODIFICANDO o mesmo par `de`/`para` de formas
diferentes."""

from __future__ import annotations

import pytest

from app.catalogo import mesclagem

ULIDS = [f"01J{str(i).zfill(23)}"[:26] for i in range(4)]


def _base_com_ligacao(tipo: str) -> dict:
    nos = [{"id": ULIDS[0], "tipo": "a"}, {"id": ULIDS[1], "tipo": "b"}]
    return {"nos": nos, "ligacoes": [{"de": ULIDS[0], "para": ULIDS[1], "tipo": tipo}]}


# CONSERTADO (17/09/2026, ramo wt/l56): `mesclagem._mapas_de_ligacoes` passou a identificar a ligação
# pelo par lógico (de, para), caindo no JSON canônico só quando o mesmo par aparece duas vezes num dos
# lados. Os pares positivos estão nos dois testes seguintes.
def test_dois_lados_mudam_o_tipo_da_mesma_ligacao_e_conflito_nomeado_nao_duplicacao_silenciosa():
    base = _base_com_ligacao("filtra")
    cliente = _base_com_ligacao("seleciona")
    servidor = _base_com_ligacao("zoom")

    r = mesclagem.mesclar(base, servidor, cliente)

    # portão do item: "nó [aqui, unidade] que os dois lados mudaram de forma DIFERENTE [...] é CONFLITO —
    # a função devolve a lista e quem chama responde 409 [...] nada é escolhido às escondidas". A mesma
    # promessa, aplicada à ligação (a única outra unidade do documento que o próprio módulo diz seguir
    # "a mesma regra"), exige que isto seja relatado como conflito — não que as duas sobrevivam juntas.
    assert not r.ok, r.relatorio()
    assert len(r.corpo["ligacoes"]) == 1, (
        "duas variantes contraditórias da MESMA ligação (mesmo de/para) sobreviveram juntas, sem "
        f"conflito relatado: {r.corpo['ligacoes']}"
    )


def test_um_lado_so_muda_a_ligacao_e_mesclagem_continua_automatica():
    """Par positivo 1: quando SÓ o cliente muda a ligação, continua sendo mesclagem automática (não virou
    conflito para todo mundo por causa do conserto)."""
    r = mesclagem.mesclar(_base_com_ligacao("filtra"), _base_com_ligacao("filtra"), _base_com_ligacao("seleciona"))
    assert r.ok, r.relatorio()
    assert r.corpo["ligacoes"] == [{"de": ULIDS[0], "para": ULIDS[1], "tipo": "seleciona"}]


def test_duas_ligacoes_entre_o_mesmo_par_continuam_sendo_conjunto():
    """Par positivo 2: quando o documento tem DUAS ligações entre os mesmos dois nós, o par deixa de ser
    identidade e vale a regra antiga (conjunto por JSON canônico) — adicionar de um lado e manter do outro
    não vira conflito."""
    def doc(ligacoes):
        return {"nos": [{"id": ULIDS[0], "tipo": "a"}, {"id": ULIDS[1], "tipo": "b"}], "ligacoes": ligacoes}

    a = {"de": ULIDS[0], "para": ULIDS[1], "tipo": "filtra"}
    b = {"de": ULIDS[0], "para": ULIDS[1], "tipo": "zoom"}
    c = {"de": ULIDS[1], "para": ULIDS[0], "tipo": "seleciona"}
    r = mesclagem.mesclar(doc([a, b]), doc([a, b]), doc([a, b, c]))
    assert r.ok, r.relatorio()
    assert len(r.corpo["ligacoes"]) == 3, r.corpo["ligacoes"]
