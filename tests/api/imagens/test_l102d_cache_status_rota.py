"""Item L1-02-d — a rota que mostra a taxa de acerto do cache por dia.

Aqui se mede o que só a rota prova: que ela existe, que exige sessão (não token de serviço), que não
é cacheada e que a leitura do journal de verdade não derruba a resposta nesta máquina.
"""

from __future__ import annotations

import secrets


def test_a_rota_de_status_do_cache_responde_para_a_sessao(sessao_a):
    r = sessao_a.get("/api/imagens/cache/status", params={"desde": "-2h"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["estado"] in ("ok", "sem_dado", "sem_linhas"), corpo
    assert corpo["janela"]["desde"] == "-2h"
    assert "no-store" in (r.headers.get("cache-control") or "")


def test_quando_ha_dado_a_taxa_e_por_dia_e_fica_entre_0_e_1(sessao_a):
    corpo = sessao_a.get("/api/imagens/cache/status", params={"desde": "-2h"}).json()
    for dia in corpo.get("dias", []):
        assert len(dia["dia"]) == 10, dia
        if dia["taxa_de_acerto"] is not None:
            assert 0.0 <= dia["taxa_de_acerto"] <= 1.0, dia
            assert dia["pedidos_com_cache"] == dia["acertos"] + dia["erros"], dia


def test_a_rota_nao_aceita_token_de_servico(sessao_a):
    """Estado de infraestrutura não sai por token de ladrilho."""
    r = sessao_a.post("/api/tokens", json={"nome": f"zt-l102d-{secrets.token_hex(4)}",
                                           "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app, base_url="http://testserver") as c:
            resp = c.get("/api/imagens/cache/status",
                         headers={"Authorization": f"Bearer {r.json()['token']}"})
        assert resp.status_code in (401, 403), resp.status_code
    finally:
        sessao_a.delete(f"/api/tokens/{r.json()['id']}")
