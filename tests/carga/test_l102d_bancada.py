"""Portão do item L1-02-d (cache nginx + bancada de carga), provado de ponta a ponta nesta trilha.

Um caso só, de propósito: as seis cláusulas dividem a MESMA pilha (aplicação em uvicorn + nginx de
usuário com proxy_cache) e a mesma rodada de medição — a fase quente depende do aquecimento, a
revogação depende do ladrilho quente, e a eviction depende de tudo antes ter passado. Separar em
testes faria cada um re-subir a pilha (~30 s cada) para medir a mesma coisa.

Escreve `tests/medidas/L1-02-d-cache-nginx-e-carga.json` só com PLAT_GRAVAR_MEDIDAS=1 (regra da casa:
a suíte não suja a árvore; a evidência commitada foi gerada com ela ligada).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.carga import tiles as bancada

ROOT = Path(__file__).resolve().parents[2]
SAIDA = ROOT / "tests" / "medidas" / "L1-02-d-cache-nginx-e-carga.json"
TENANT_DEMO = 1


@pytest.fixture(scope="module")
def pilha(tmp_path_factory):
    base = tmp_path_factory.mktemp("l102d")
    acervo = base / "acervo"
    acervo.mkdir()
    with bancada.Pilha(base, acervo, max_cache_mb=bancada.MAX_CACHE_MB) as p:
        yield p


@pytest.fixture(scope="module")
def alvo(pilha):
    cog = bancada._gerar_cog(pilha.acervo / "bancada.tif")
    return bancada.semear_item(TENANT_DEMO, "bancada.tif", cog)


@pytest.fixture(scope="module")
def sessao():
    from tests.api.conftest import _sessao_admin, credenciais

    c = credenciais()
    if "demo" not in c:
        pytest.skip("credenciais sem a linha de demo")
    return _sessao_admin(c, "demo")


@pytest.fixture(scope="module")
def tokens(sessao):
    def criar(nome: str) -> dict:
        r = sessao.post("/api/tokens", json={"nome": nome, "escopos": ["tiles:ler"]})
        assert r.status_code == 201, r.text
        return r.json()

    ta, tb = criar("zt-l102d-bancada-a"), criar("zt-l102d-bancada-b")
    yield ta, tb
    sessao.delete(f"/api/tokens/{tb['id']}")


def test_bancada_completa(pilha, alvo, sessao, tokens):
    ta, tb = tokens

    def revogar_a() -> None:
        r = sessao.delete(f"/api/tokens/{ta['id']}")
        assert r.status_code == 204, r.text

    res = bancada.rodar(pilha, ta["token"], tb["token"], alvo["item_id"], revogar_a)
    assert not res["erros_fatais"], res["erros_fatais"]
    bancada.gravar_json(
        res,
        onde=(f"trilha l102dca50db (Hetzner): nginx de usuário 127.0.0.1:{pilha.porta_nginx} -> "
              f"uvicorn 127.0.0.1:{pilha.porta_app}; COG sintético local via acervo:// (sem Garage)"),
        saida=SAIDA)

    detalhe = json.dumps(res, ensure_ascii=False, indent=1)
    # portão do pai: >= 500 tiles/s quente com 0 erro (a bancada mede de 1 a 200 conexões)
    assert res["quente"]["passou"], detalhe
    assert [n["conexoes"] for n in res["quente"]["niveis"]] == list(bancada.NIVEIS_QUENTE)
    assert res["quente"]["niveis"][0]["conexoes"] == 1
    assert res["quente"]["niveis"][-1]["conexoes"] == 200
    # frio >= 15 tiles/s com 1 conexão, todo MISS, todo ladrilho com pixel (200, nunca 204/404)
    assert res["frio_1_conexao"]["passou"], detalhe
    # proxy_cache_lock: 20 simultâneos ao mesmo ladrilho frio = 1 MISS, contado no log do nginx
    assert res["proxy_cache_lock"]["passou"], detalhe
    # a chave inclui os parâmetros de renderização: NDVI e RGB do mesmo item não se misturam
    assert res["chave_com_parametros"]["passou"], detalhe
    # token revogado não é servido do cache (auth_request antes do cache), em <= 5 s
    assert res["revogacao"]["passou"], detalhe
    # cache além de max_size: eviction acontece sem erro nenhum
    assert res["eviction"]["passou"], detalhe
