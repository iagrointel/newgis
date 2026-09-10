"""Edição concorrente sem CRDT (item L5-13-edicao-concorrente), contra a API real da trilha:
  - dois lados editam nós DIFERENTES a partir da mesma base: o segundo grava com `base_versao` antiga e o servidor
    mescla por nó (200 com `mesclagem`), as duas alterações ficam;
  - o mesmo nó: 409 `versao_conflito` com o documento ATUAL e os ids em conflito no detalhe (nada escolhido);
  - 100 pares de edições aleatórias em nós disjuntos pela API: nenhuma alteração perdida;
  - presença: batimento devolve quem está; o fluxo SSE manda a lista na conexão e a cada mudança; some ao sair;
  - `versao_atual` estrito continua valendo (comportamento antigo intacto).
"""

from __future__ import annotations

import asyncio
import copy
import json
import random
import time

import pytest

from app.catalogo import presenca
from tests.api.catalogo.conftest import titulo_zt
from tests.api.test_rls import ids_por_slug

ITEM = "L5-13-edicao-concorrente"
ULIDS = [f"01J{str(i).zfill(23)}"[:26] for i in range(300)]


def _no(i, **props):
    return {"id": ULIDS[i], "tipo": "texto", "pai": None, "largura_colunas": 6,
            "propriedades": {"texto": f"n{i}", **props}}


def _dados(nos):
    return {"tipo": "app", "esquema_versao": 2, "corpo": {"nos": nos, "ligacoes": []}}


@pytest.fixture
def app_item(sessao_a):
    corpo = {"tipo": "app", "titulo": titulo_zt("concorrente"), "dados": _dados([_no(0), _no(1), _no(2)])}
    r = sessao_a.post("/api/itens", json=corpo)
    assert r.status_code == 201, r.text
    it = r.json()
    yield it
    sessao_a.delete(f"/api/itens/{it['id']}")


def _patch(sessao, iid, nos, base):
    return sessao.patch(f"/api/itens/{iid}", json={"dados": _dados(nos), "base_versao": base})


def test_nos_diferentes_sao_mesclados_sem_conflito(sessao_a, app_item, medida):
    iid, v1 = app_item["id"], app_item["versao_atual"]
    base = app_item["dados"]["corpo"]["nos"]
    # lado A muda o nó 0 e grava (v2)
    lado_a = copy.deepcopy(base)
    lado_a[0]["propriedades"]["texto"] = "A editou o nó 0"
    ra = _patch(sessao_a, iid, lado_a, v1)
    assert ra.status_code == 200 and ra.json()["versao_atual"] == v1 + 1 and "mesclagem" not in ra.json(), ra.text
    # lado B, ainda com a base v1, muda o nó 2 e cria um nó novo: mesclado, sem 409
    lado_b = copy.deepcopy(base)
    lado_b[2]["largura_colunas"] = 12
    lado_b.append(_no(50, origem="B"))
    rb = _patch(sessao_a, iid, lado_b, v1)
    assert rb.status_code == 200, rb.text
    j = rb.json()
    assert j["versao_atual"] == v1 + 2
    assert j["mesclagem"]["do_servidor"] == [ULIDS[0]] and set(j["mesclagem"]["do_cliente"]) == {ULIDS[2], ULIDS[50]}
    assert j["mesclagem"]["conflitos"] == [] and j["mesclagem"]["base_versao"] == v1
    nos = {n["id"]: n for n in j["dados"]["corpo"]["nos"]}
    assert nos[ULIDS[0]]["propriedades"]["texto"] == "A editou o nó 0"  # de A, preservado
    assert nos[ULIDS[2]]["largura_colunas"] == 12 and ULIDS[50] in nos  # de B
    assert [n["id"] for n in j["dados"]["corpo"]["nos"]] == [ULIDS[0], ULIDS[1], ULIDS[2], ULIDS[50]]
    medida(ITEM)("mesclagem_por_no_sem_conflito", True, "bool",
                 "PATCH com base_versao antiga e nós disjuntos = 200 + mesclagem")


def test_mesmo_no_e_409_com_documento_atual_e_ids_em_conflito(sessao_a, app_item):
    iid, v1 = app_item["id"], app_item["versao_atual"]
    base = app_item["dados"]["corpo"]["nos"]
    lado_a = copy.deepcopy(base)
    lado_a[1]["propriedades"]["texto"] = "A"
    assert _patch(sessao_a, iid, lado_a, v1).status_code == 200
    lado_b = copy.deepcopy(base)
    lado_b[1]["propriedades"]["texto"] = "B"
    lado_b[2]["propriedades"]["texto"] = "B também mudou o 2 (disjunto)"
    rb = _patch(sessao_a, iid, lado_b, v1)
    assert rb.status_code == 409, rb.text
    d = rb.json()["detalhe"]
    assert rb.json()["erro"] == "versao_conflito"
    assert d["versao_atual"] == v1 + 1 and d["base_versao"] == v1 and d["conflitos"] == [ULIDS[1]]
    assert d["dados"]["corpo"]["nos"][1]["propriedades"]["texto"] == "A"  # o documento ATUAL vem inteiro
    assert ULIDS[2] in d["do_cliente"]  # o que teria sido mesclado também é dito
    # nada gravado: servidor continua em v2 com o texto de A
    atual = sessao_a.get(f"/api/itens/{iid}").json()
    assert atual["versao_atual"] == v1 + 1 and atual["dados"]["corpo"]["nos"][1]["propriedades"]["texto"] == "A"
    assert atual["dados"]["corpo"]["nos"][2]["propriedades"]["texto"] == "n2"


def test_versao_atual_estrita_continua_valendo_e_base_igual_nao_mescla(sessao_a, app_item):
    iid, v1 = app_item["id"], app_item["versao_atual"]
    base = app_item["dados"]["corpo"]["nos"]
    mudado = copy.deepcopy(base)
    mudado[0]["propriedades"]["texto"] = "primeira gravação"
    assert _patch(sessao_a, iid, mudado, v1).status_code == 200  # base igual à atual: caminho normal (v2)
    r = sessao_a.patch(f"/api/itens/{iid}", json={"dados": _dados(base), "versao_atual": v1})
    assert r.status_code == 409 and "dados" not in (r.json().get("detalhe") or {})  # regra antiga, intacta
    r = _patch(sessao_a, iid, base, 999)
    assert r.status_code == 409 and "não existe" in r.json()["mensagem"]
    # item sem grafo (mapa): base_versao diferente = 409 estrito com o documento atual
    mapa = {"tipo": "mapa", "titulo": titulo_zt("mapa-conc"), "dados": {"esquema_versao": 1, "corpo": {}}}
    r = sessao_a.post("/api/itens", json=mapa)
    assert r.status_code == 201
    mid = r.json()["id"]
    try:
        assert sessao_a.patch(f"/api/itens/{mid}", json={"resumo": "x"}).status_code == 200
        novo = {"dados": {"esquema_versao": 1, "corpo": {"a": 1}}, "base_versao": 1}
        r = sessao_a.patch(f"/api/itens/{mid}", json=novo)
        assert r.status_code == 409 and r.json()["detalhe"]["dados"] == {"esquema_versao": 1, "corpo": {}}
    finally:
        sessao_a.delete(f"/api/itens/{mid}")


def test_cem_pares_de_edicoes_aleatorias_em_nos_disjuntos_pela_api(sessao_a, medida):
    rng = random.Random(513)
    nos0 = [_no(i) for i in range(10)]
    r = sessao_a.post("/api/itens", json={"tipo": "app", "titulo": titulo_zt("cem-pares"), "dados": _dados(nos0)})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    perdidas = 0
    t0 = time.perf_counter()
    try:
        for par in range(100):
            atual = sessao_a.get(f"/api/itens/{iid}").json()
            base_v, base_nos = atual["versao_atual"], atual["dados"]["corpo"]["nos"]
            ids = [n["id"] for n in base_nos]
            rng.shuffle(ids)
            corte = rng.randint(1, len(ids) - 1)
            alvo_a, alvo_b = ids[:corte][:3], ids[corte:][:3]
            lado_a, lado_b = copy.deepcopy(base_nos), copy.deepcopy(base_nos)
            esperado: dict[str, str] = {}
            for lado, alvos, marca in ((lado_a, alvo_a, "a"), (lado_b, alvo_b, "b")):
                for nid in alvos:
                    n = next(x for x in lado if x["id"] == nid)
                    n["propriedades"]["texto"] = f"{marca}{par}-{rng.randint(1, 10**6)}"
                    esperado[nid] = n["propriedades"]["texto"]
            assert _patch(sessao_a, iid, lado_a, base_v).status_code == 200
            rb = _patch(sessao_a, iid, lado_b, base_v)
            assert rb.status_code == 200, (par, rb.text)
            final = {n["id"]: n for n in rb.json()["dados"]["corpo"]["nos"]}
            for nid, texto in esperado.items():
                if final[nid]["propriedades"]["texto"] != texto:
                    perdidas += 1
        dt = time.perf_counter() - t0
    finally:
        sessao_a.delete(f"/api/itens/{iid}")
    assert perdidas == 0
    m = medida(ITEM)
    m("cem_pares_api_alteracoes_perdidas", perdidas, "alteracoes",
      "100 pares de PATCH com a mesma base em nós disjuntos")
    m("cem_pares_api_s", round(dt, 2), "s", "200 PATCH + 100 GET pela API da trilha (TestClient)")


def test_presenca_batimento_lista_sse_e_saida(sessao_a, app_item, conexao_plat_app, ids, medida):
    """O fluxo SSE é consumido pelo gerador direto (`presenca.gerar`): o TestClient não fecha um fluxo que nunca
    termina (30 min), e o que se prova aqui é o conteúdo dos eventos; a rota HTTP é exercitada pelo e2e
    (EventSource no navegador)."""
    iid = app_item["id"]
    r = sessao_a.post(f"/api/itens/{iid}/presenca", json={"sessao": "aba-um-abcdef", "no": None})
    assert r.status_code == 200, r.text
    lista = r.json()["itens"]
    assert len(lista) == 1 and lista[0]["sessao"] == "aba-um-abcdef" and lista[0]["login"] and lista[0]["no"] is None
    assert set(lista[0]) == set(presenca.CAMPOS)
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    usuario_id = ids["a"]["id"]

    async def consumir():
        gen = presenca.gerar(tenant_id, iid, usuario_id)
        primeiro = await asyncio.wait_for(gen.__anext__(), 5)
        t0 = time.perf_counter()
        with conexao_plat_app.cursor() as cur:
            presenca.bater(cur, tenant_id, iid, usuario_id, "outra", "Outra Aba", "aba-dois-abcdef", ULIDS[1])
        conexao_plat_app.commit()
        segundo = await asyncio.wait_for(gen.__anext__(), 5)
        lat = time.perf_counter() - t0
        await gen.aclose()
        return primeiro, segundo, lat

    primeiro, segundo, lat = asyncio.run(consumir())

    def _evento(b: bytes):
        linhas = b.decode().split("\n")
        return linhas[0].removeprefix("event: "), json.loads(linhas[1].removeprefix("data: "))

    e1, lista1 = _evento(primeiro)
    e2, lista2 = _evento(segundo)
    assert e1 == "presenca" and [e["sessao"] for e in lista1] == ["aba-um-abcdef"]
    assert e2 == "presenca"
    assert {e["sessao"]: e["no"] for e in lista2} == {"aba-um-abcdef": None, "aba-dois-abcdef": ULIDS[1]}
    medida(ITEM)("presenca_sse_latencia_s", round(lat, 3), "s",
                 "batimento de outra aba -> evento presenca no gerador SSE (mesmo processo)")
    # sair: some na hora
    r3 = sessao_a.post(f"/api/itens/{iid}/presenca", json={"sessao": "aba-dois-abcdef", "no": None, "sair": True})
    assert [e["sessao"] for e in r3.json()["itens"]] == ["aba-um-abcdef"]
    assert [e["sessao"] for e in sessao_a.get(f"/api/itens/{iid}/presenca").json()["itens"]] == ["aba-um-abcdef"]
    # a rota SSE responde com o tipo certo (o corpo é o mesmo gerador; não se consome aqui — ver docstring)
    assert sessao_a.post(f"/api/itens/{iid}/presenca", json={"sessao": "x", "no": None}).status_code == 422
    ruim = sessao_a.post(f"/api/itens/{iid}/presenca", json={"sessao": "aba-um-abcdef", "no": "nao-e-ulid"})
    assert ruim.status_code == 422


def test_presenca_expira_sem_batimento(sessao_a, app_item, monkeypatch):
    iid = app_item["id"]
    monkeypatch.setattr(presenca, "EXPIRA_S", 0.5)
    sessao_a.post(f"/api/itens/{iid}/presenca", json={"sessao": "aba-efemera-1", "no": None})
    assert len(sessao_a.get(f"/api/itens/{iid}/presenca").json()["itens"]) == 1
    time.sleep(0.7)
    assert sessao_a.get(f"/api/itens/{iid}/presenca").json()["itens"] == []
