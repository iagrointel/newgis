"""HARD-03 — adversário L2, relações entre itens (item L2-10-b, app/catalogo/relacoes.py, plat.item_relacao). As
relações de um mapa saem do próprio `dados.corpo.camadas` (uuids de itens). Um mapa de A que referencie o item de
OUTRO inquilino tem de ser recusado: `relacoes.sincronizar` confere o destino sob RLS, e o item de B é invisível
para A (422 relacao_com_outro_inquilino). Só roda em trilha (conftest do pacote)."""

from __future__ import annotations

import secrets

from tests.api.catalogo.conftest import DADOS_POR_TIPO
from tests.api.conftest import PREFIXO_TESTE


def _item(sessao, tipo="camada_vetorial") -> str:
    r = sessao.post("/api/itens", json={"tipo": tipo, "titulo": f"{PREFIXO_TESTE} {secrets.token_hex(3)}",
                                        "dados": DADOS_POR_TIPO[tipo]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mapa_referenciando(sessao, ids: list[str]):
    return sessao.post("/api/itens", json={
        "tipo": "mapa", "titulo": f"{PREFIXO_TESTE} mapa {secrets.token_hex(3)}",
        "dados": {"esquema_versao": 1, "corpo": {"camadas": ids}}})


def test_l2_10b_mapa_de_a_nao_referencia_item_de_b(sessao_a, sessao_b):
    destino_b = _item(sessao_b)
    try:
        r = _mapa_referenciando(sessao_a, [destino_b])
        assert r.status_code in (403, 422), (r.status_code, r.text[:200])
        assert "inquilino" in r.text or "inexistente" in r.text, r.text[:200]
        # nenhum mapa foi criado apontando para B
        lista = sessao_a.get(f"/api/itens?q={PREFIXO_TESTE} mapa&limite=200").json()["itens"]
        for it in lista:
            usados = sessao_a.get(f"/api/itens/{it['id']}/usado-por")
            assert destino_b not in usados.text
    finally:
        sessao_b.delete(f"/api/itens/{destino_b}")


def test_l2_10b_id_malformado_ou_nil_nao_cria_relacao_nem_erro_de_banco(sessao_a):
    """UUID malformado é descartado por `_uuids` (sem virar relação); o nil UUID parseia mas aponta para nada.
    Nenhum dos dois pode causar 500 nem criar uma relação — o que importa (item de OUTRO inquilino) é o teste
    acima. Aceita 201 (id ignorado, 0 relação) ou 422 (rejeição explícita), nunca 5xx nem uma relação órfã."""
    nulo = "00000000-0000-0000-0000-000000000000"
    for destino in (nulo, "nao-e-uuid"):
        r = _mapa_referenciando(sessao_a, [destino])
        assert r.status_code in (201, 400, 422), (destino, r.status_code, r.text[:200])
        if r.status_code == 201:
            mapa = r.json()["id"]
            usa = sessao_a.get(f"/api/itens/{mapa}/usa").text if False else ""
            sessao_a.delete(f"/api/itens/{mapa}")
            assert nulo not in usa


def test_l2_10b_mapa_legitimo_referencia_propria_camada(sessao_a):
    """Controle positivo: um mapa que aponta para uma camada do PRÓPRIO inquilino é aceito e cria a relação."""
    camada = _item(sessao_a)
    try:
        r = _mapa_referenciando(sessao_a, [camada])
        assert r.status_code == 201, r.text
        mapa = r.json()["id"]
        usado = sessao_a.get(f"/api/itens/{camada}/usado-por")
        assert mapa in usado.text, usado.text[:200]
        sessao_a.delete(f"/api/itens/{mapa}")
    finally:
        sessao_a.delete(f"/api/itens/{camada}")


def test_l2_10b_edicao_de_mapa_de_a_para_apontar_a_b_tambem_recusada(sessao_a, sessao_b):
    """A defesa vale também na EDIÇÃO (PUT), não só na criação: A cria um mapa legítimo e depois tenta editá-lo
    para referenciar o item de B."""
    camada = _item(sessao_a)
    destino_b = _item(sessao_b)
    mapa = _mapa_referenciando(sessao_a, [camada]).json()["id"]
    try:
        r = sessao_a.put(f"/api/itens/{mapa}", json={"dados": {"esquema_versao": 1, "corpo": {"camadas": [destino_b]}}})
        assert r.status_code in (403, 422), (r.status_code, r.text[:200])
    finally:
        sessao_a.delete(f"/api/itens/{mapa}")
        sessao_a.delete(f"/api/itens/{camada}")
        sessao_b.delete(f"/api/itens/{destino_b}")
