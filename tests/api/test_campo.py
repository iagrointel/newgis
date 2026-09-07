"""API do item L2-07-a-pwa-instalavel-cache (PWA de campo): `POST /api/campo/sessao` sempre emite escopo
`campo:usar`/`CAMPO_TOKEN_DIAS` dias (nunca escolhido pelo chamador); `GET /api/campo/mapas` só devolve tipo
`mapa` e respeita a RLS de `plat.item` entre inquilinos; token revogado bloqueia com o código já usado por todo
token de serviço (`token_revogado`); e — cláusula da refutação — o valor do token NUNCA aparece na linha de
acesso estruturada (`app/log.py`/`app.auth.middleware`), só o `id`/prefixo. Os testes de navegador (manifest,
service worker, offline, versão do shell, toque, lighthouse) estão em `tests/e2e/test_campo_pwa.py`."""

import logging

from app import limites
from tests.api.conftest import PREFIXO_TESTE, com_token


def _mapa(sessao, titulo: str):
    r = sessao.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": titulo, "dados": {"esquema_versao": 1, "corpo": {"camadas": [{"id": "c1"}]}}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_sessao_de_campo_emite_token_com_escopo_fixo(sessao_a):
    r = sessao_a.post("/api/campo/sessao", json={})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["token"].startswith("plat_")
    assert j["escopos"] == ["campo:usar"]
    assert j["tenant_slug"] == "demo"
    assert "id" in j and "expira_em" in j
    assert sessao_a.delete(f"/api/tokens/{j['id']}").status_code == 204


def test_sem_sessao_401(cliente):
    r = cliente.post("/api/campo/sessao", json={})
    assert r.status_code == 401


def test_token_de_campo_nao_serve_para_escopo_maior(sessao_a, cliente):
    """um token `campo:usar` não abre `/api/itens` (que exige `catalogo:ler`) — o escopo é fechado ao que o
    item declara, não uma porta geral para o resto da API."""
    tok = sessao_a.post("/api/campo/sessao", json={}).json()
    try:
        r = com_token(cliente, tok["token"], "GET", "/api/itens")
        assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_mapas_de_campo_so_do_proprio_inquilino(sessao_a, sessao_b, cliente):
    m_a = _mapa(sessao_a, f"{PREFIXO_TESTE}-campo-a")
    m_b = _mapa(sessao_b, f"{PREFIXO_TESTE}-campo-b")
    tok_a = sessao_a.post("/api/campo/sessao", json={}).json()
    try:
        r = com_token(cliente, tok_a["token"], "GET", "/api/campo/mapas")
        assert r.status_code == 200, r.text
        titulos = [m["titulo"] for m in r.json()["mapas"]]
        assert m_a["titulo"] in titulos
        assert m_b["titulo"] not in titulos  # RLS: token do inquilino A nunca vê item do B
    finally:
        sessao_a.delete(f"/api/tokens/{tok_a['id']}")
        sessao_a.delete(f"/api/itens/{m_a['id']}")
        sessao_b.delete(f"/api/itens/{m_b['id']}")


def test_token_revogado_bloqueia_com_o_mesmo_codigo_de_sempre(sessao_a, cliente):
    tok = sessao_a.post("/api/campo/sessao", json={}).json()
    assert sessao_a.delete(f"/api/tokens/{tok['id']}").status_code == 204
    r = com_token(cliente, tok["token"], "GET", "/api/campo/mapas")
    assert r.status_code == 401 and r.json()["erro"] == "token_revogado"


def test_limite_de_tokens_por_usuario_vale_tambem_para_campo(sessao_a):
    """`campo:usar` usa a MESMA tabela/limite de `tokens.py` (`TOKENS_POR_USUARIO`) — não é um contador à
    parte que alguém possa esgotar sem perceber."""
    criados = []
    try:
        # zera o que sobrar de outra rodada antes de bater no teto (RLS: só os do próprio usuário)
        ativos = sessao_a.get("/api/tokens").json()
        for t in ativos:
            if t["revogado_em"] is None:
                sessao_a.delete(f"/api/tokens/{t['id']}")
        for _ in range(limites.TOKENS_POR_USUARIO):
            r = sessao_a.post("/api/campo/sessao", json={})
            assert r.status_code == 201, r.text
            criados.append(r.json()["id"])
        r = sessao_a.post("/api/campo/sessao", json={})
        assert r.status_code == 422 and r.json()["erro"] == "limite_tokens"
    finally:
        for tid in criados:
            sessao_a.delete(f"/api/tokens/{tid}")


def test_token_de_campo_nunca_aparece_no_log_de_acesso(sessao_a, caplog):
    """`app/log.py` grava uma linha JSON por requisição (`plat.acesso`) com método/rota/status/tempo — nunca o
    corpo. Prova direta: captura o logger durante a emissão e confere que o valor do token (que só existe DEPOIS
    da resposta) não aparece em nenhuma linha registrada durante a chamada."""
    with caplog.at_level(logging.INFO, logger="plat.acesso"):
        r = sessao_a.post("/api/campo/sessao", json={})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    try:
        linhas = [rec.getMessage() for rec in caplog.records]
        assert linhas, "nenhuma linha de acesso capturada — o teste não provou nada"
        assert not any(token in linha for linha in linhas), linhas
        assert not any("plat_" in linha for linha in linhas), linhas  # nem o prefixo de nenhum outro token
    finally:
        sessao_a.delete(f"/api/tokens/{r.json()['id']}")
