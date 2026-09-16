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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-13: mesclagem.mesclar() identifica ligação pelo JSON canônico do objeto inteiro (sem id "
        "próprio); dois lados mudando um CAMPO da mesma ligação lógica (mesmo de/para) viram duas chaves "
        "canônicas distintas -> duas ADIÇÕES independentes, nunca um conflito. As duas variantes "
        "contraditórias sobrevivem juntas no documento final com Resultado.ok=True."
    ),
)
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
