"""Mesclagem de três vias por nó (item L5-13-edicao-concorrente, `app/catalogo/mesclagem.py`). Cláusula do portão:
"nenhum caso perde alteração (teste automatizado com 100 pares de edições aleatórias em nós disjuntos)" — 100
pares, cada um com dois lados editando nós DIFERENTES a partir da mesma base (alterar propriedade, mover,
redimensionar, inserir, remover), e o resultado tem de conter TODA alteração dos dois lados. Mais: mesmo nó com
valores diferentes = conflito nomeado (nunca escolha silenciosa); mesmo nó com o mesmo valor = sem conflito;
removido de um lado e alterado do outro = conflito; ordem determinística."""

from __future__ import annotations

import copy
import random

from app.catalogo import mesclagem

ULIDS = [f"01J{str(i).zfill(23)}"[:26] for i in range(200)]


def _no(i: int, pai: str | None = None, **props):
    return {"id": ULIDS[i], "tipo": "texto", "pai": pai, "largura_colunas": 6,
            "propriedades": {"texto": f"n{i}", **props}}


def _base(n: int = 12) -> dict:
    nos = [_no(i) for i in range(n)]
    return {"nos": nos, "ligacoes": [{"de": ULIDS[0], "para": ULIDS[1]}], "titulo": "base"}


def _editar_aleatorio(corpo: dict, ids: list[str], rng: random.Random, prefixo: str) -> dict:
    """Aplica 1 a 4 edições só nos nós `ids` (mais inserções de nós novos); devolve o corpo novo."""
    novo = copy.deepcopy(corpo)
    por_id = {n["id"]: n for n in novo["nos"]}
    for nid in ids:
        acao = rng.choice(["propriedade", "largura", "mover", "remover", "inserir"])
        n = por_id[nid]
        if acao == "propriedade":
            n["propriedades"]["texto"] = f"{prefixo}-{rng.randint(1, 10**6)}"
        elif acao == "largura":
            n["largura_colunas"] = rng.choice([3, 4, 6, 12])
        elif acao == "mover":
            novo["nos"].remove(n)
            novo["nos"].insert(rng.randint(0, len(novo["nos"])), n)
        elif acao == "remover":
            novo["nos"].remove(n)
        else:
            faixa = 100 if prefixo == "a" else 150  # ids novos de cada lado nunca colidem (nós disjuntos)
            novo["nos"].insert(rng.randint(0, len(novo["nos"])), _no(faixa + rng.randint(0, 49), origem=prefixo))
    return novo


def _mudancas(base: dict, depois: dict) -> dict[str, dict | None]:
    """id -> nó final (None = removido) para cada nó que mudou entre base e depois."""
    b = {n["id"]: n for n in base["nos"]}
    d = {n["id"]: n for n in depois["nos"]}
    saida: dict[str, dict | None] = {}
    for nid in set(b) | set(d):
        if b.get(nid) != d.get(nid):
            saida[nid] = d.get(nid)
    return saida


def test_cem_pares_de_edicoes_aleatorias_em_nos_disjuntos_nunca_perdem_alteracao():
    rng = random.Random(2026)
    perdidas = 0
    for par in range(100):
        base = _base(12)
        ids = [n["id"] for n in base["nos"]]
        rng.shuffle(ids)
        corte = rng.randint(1, len(ids) - 1)
        lado_a, lado_b = ids[:corte], ids[corte:]
        servidor = _editar_aleatorio(base, lado_a[: rng.randint(1, min(4, len(lado_a)))], rng, "a")
        cliente = _editar_aleatorio(base, lado_b[: rng.randint(1, min(4, len(lado_b)))], rng, "b")
        r = mesclagem.mesclar(base, servidor, cliente)
        assert r.ok, (par, r.conflitos, r.chaves_conflito)
        final = {n["id"]: n for n in r.corpo["nos"]}
        for lado in (servidor, cliente):
            for nid, esperado in _mudancas(base, lado).items():
                if final.get(nid) != esperado:
                    perdidas += 1
        # nó que ninguém tocou continua igual à base
        intocados = set(ids) - set(_mudancas(base, servidor)) - set(_mudancas(base, cliente))
        for nid in intocados:
            assert final[nid] == next(n for n in base["nos"] if n["id"] == nid)
        assert len(final) == len(r.corpo["nos"]), "id repetido no resultado"
    assert perdidas == 0


def test_mesmo_no_com_valores_diferentes_e_conflito_nomeado():
    base = _base(3)
    servidor, cliente = copy.deepcopy(base), copy.deepcopy(base)
    servidor["nos"][1]["propriedades"]["texto"] = "do servidor"
    cliente["nos"][1]["propriedades"]["texto"] = "do cliente"
    cliente["nos"][2]["largura_colunas"] = 12  # nó disjunto: mescla mesmo com o conflito no outro
    r = mesclagem.mesclar(base, servidor, cliente)
    assert not r.ok and [c["id"] for c in r.conflitos] == [ULIDS[1]]
    assert r.conflitos[0]["cliente"]["propriedades"]["texto"] == "do cliente"
    assert r.conflitos[0]["servidor"]["propriedades"]["texto"] == "do servidor"
    assert r.relatorio()["conflitos"] == [ULIDS[1]] and ULIDS[2] in r.relatorio()["do_cliente"]


def test_mesmo_no_com_o_mesmo_valor_nao_e_conflito():
    base = _base(3)
    servidor, cliente = copy.deepcopy(base), copy.deepcopy(base)
    servidor["nos"][0]["propriedades"]["texto"] = cliente["nos"][0]["propriedades"]["texto"] = "igual"
    r = mesclagem.mesclar(base, servidor, cliente)
    assert r.ok and r.corpo["nos"][0]["propriedades"]["texto"] == "igual"


def test_removido_de_um_lado_e_alterado_do_outro_e_conflito():
    base = _base(3)
    servidor, cliente = copy.deepcopy(base), copy.deepcopy(base)
    del servidor["nos"][1]
    cliente["nos"][1]["propriedades"]["texto"] = "editei o que o outro apagou"
    r = mesclagem.mesclar(base, servidor, cliente)
    assert [c["id"] for c in r.conflitos] == [ULIDS[1]] and r.conflitos[0]["servidor"] is None
    # removido dos dois lados: sem conflito, some
    cliente2 = copy.deepcopy(base)
    del cliente2["nos"][1]
    r2 = mesclagem.mesclar(base, servidor, cliente2)
    assert r2.ok and [n["id"] for n in r2.corpo["nos"]] == [ULIDS[0], ULIDS[2]]


def test_no_criado_no_servidor_entra_depois_do_antecessor_e_ligacoes_sao_conjunto():
    base = _base(3)
    servidor, cliente = copy.deepcopy(base), copy.deepcopy(base)
    servidor["nos"].insert(1, _no(50))  # servidor criou entre 0 e 1
    servidor["ligacoes"].append({"de": ULIDS[1], "para": ULIDS[2]})
    cliente["nos"].append(_no(60))  # cliente criou no fim
    cliente["ligacoes"] = []  # cliente removeu a ligação da base
    cliente["titulo"] = "do cliente"
    r = mesclagem.mesclar(base, servidor, cliente)
    assert r.ok
    assert [n["id"] for n in r.corpo["nos"]] == [ULIDS[0], ULIDS[50], ULIDS[1], ULIDS[2], ULIDS[60]]
    assert r.corpo["ligacoes"] == [{"de": ULIDS[1], "para": ULIDS[2]}]
    assert r.corpo["titulo"] == "do cliente"
    # ordem determinística: duas chamadas iguais dão o mesmo corpo
    assert mesclagem.mesclar(base, servidor, cliente).corpo == r.corpo


def test_chave_de_corpo_alterada_dos_dois_lados_e_conflito():
    base = _base(2)
    servidor, cliente = copy.deepcopy(base), copy.deepcopy(base)
    servidor["titulo"], cliente["titulo"] = "s", "c"
    r = mesclagem.mesclar(base, servidor, cliente)
    assert r.chaves_conflito == ["titulo"] and not r.ok
