"""Superadmin (ADR 0002 seção 10; item L0-07-f-console-plataforma): 404 em TODAS as rotas /api/plataforma para quem
não é superadmin (sessão comum, token, sem credencial, cookie forjado); slug reservado 409 e slug fora do CHECK
422 (a expressão do CHECK é a mesma da API); plataforma não se suspende; inquilino novo nasce com admin em
trocar_senha e com as cotas pedidas; suspenso = 503 com a mensagem do operador em login, sessão viva e token, dado
intacto; cotas alteráveis; 2FA de um admin de inquilino desligado pelo operador (só admin, nunca em plataforma);
fila agregada e eventos da plataforma; superadmin só existe no inquilino plataforma (gatilho)."""

import re
import secrets
from pathlib import Path

import psycopg2
import pytest

from app.auth import rotas_plataforma
from tests.api.conftest import (
    PREFIXO_TESTE,
    InquilinoTemporario,
    arquivo_openapi,
    com_token,
    entrar,
    ligar_2fa,
    novo_cliente,
)

ROOT = Path(__file__).resolve().parents[2]
ITEM = "L0-07-f-console-plataforma"


def _rotas_plataforma() -> list[tuple[str, str]]:
    spec = arquivo_openapi()
    return sorted(
        (m.upper(), c) for c, ms in spec["paths"].items() if c.startswith("/api/plataforma") for m in ms
    )


def _url(caminho: str) -> str:
    return caminho.replace("{id}", "1").replace("{usuario_id}", "1")


def _corpo(metodo: str, caminho: str):
    if metodo == "POST" and caminho == "/api/plataforma/inquilinos":
        return {"slug": "zt-forjado", "nome": "x", "admin_login": "a", "admin_nome": "A"}
    if metodo == "PUT":
        return {"cota_usuarios": 3}
    return None


def test_404_para_nao_superadmin_em_todas_as_rotas(sessao_a, cliente, token_a, medida):
    """superadmin false = 404 em todas as rotas /api/plataforma: sessão de admin comum, token admin:inquilino,
    sem credencial e cookie forjado (valor aleatório: 401, nunca 404 de recurso nem 2xx)."""
    rotas = _rotas_plataforma()
    assert len(rotas) >= 10, rotas
    forjado = novo_cliente()
    forjado.cookies.set("plat_sessao", secrets.token_hex(32))
    for metodo, caminho in rotas:
        kw = {"json": _corpo(metodo, caminho)} if _corpo(metodo, caminho) is not None else {}
        r = sessao_a.request(metodo, _url(caminho), **kw)
        assert r.status_code == 404, (metodo, caminho, r.status_code, r.text)
        r = com_token(cliente, token_a["token"], metodo, _url(caminho), **kw)
        assert r.status_code == 404, ("token", metodo, caminho, r.status_code)
        r = cliente.request(metodo, _url(caminho), **kw)
        assert r.status_code == 404, ("anonimo", metodo, caminho, r.status_code)
        r = forjado.request(metodo, _url(caminho), **kw)
        assert r.status_code in (401, 404), ("cookie forjado", metodo, caminho, r.status_code)
    medida(ITEM)("rotas_plataforma_404_nao_superadmin", len(rotas), "rotas",
                 "rotas /api/plataforma do docs/openapi.json chamadas com sessão comum, token, anônimo e cookie forjado")


def test_superadmin_nao_se_forja_pelo_proprio_perfil(sessao_a, ids):
    """admin de inquilino comum não vira superadmin por PUT /api/usuarios/{id} nem por /api/eu (gatilho
    superadmin_so_plataforma); o console continua 404 depois da tentativa."""
    meu = ids["a"]["id"]
    r = sessao_a.put(f"/api/usuarios/{meu}", json={"superadmin": True})
    assert r.status_code in (200, 422), r.text
    assert sessao_a.get("/api/eu").json()["superadmin"] is False
    assert sessao_a.get("/api/plataforma/inquilinos").status_code == 404


def test_check_do_banco_e_a_mesma_expressao_da_api():
    """slug inválido pelo CHECK = 422: a API valida antes com a MESMA expressão regular do CHECK de plat.tenant.slug
    (002_identidade.sql); se um dia divergirem, este teste avisa, e a rota ainda mapeia CheckViolation para 422."""
    sql = (ROOT / "db" / "migracoes" / "002_identidade.sql").read_text(encoding="utf-8")
    m = re.search(r"slug\s+text UNIQUE NOT NULL CHECK \(slug ~ '([^']+)'\)", sql)
    assert m, "CHECK de slug não encontrado na 002"
    assert m.group(1) == rotas_plataforma.SLUG.pattern


def test_listar_criar_suspender(sessao_plat, cred):
    lista = sessao_plat.get("/api/plataforma/inquilinos").json()
    slugs = {t["slug"]: t for t in lista}
    assert {"plataforma", "demo", "demo2"} <= set(slugs) and slugs["demo"]["usuarios"] >= 1
    assert {
        "id", "slug", "nome", "ativo", "usuarios", "usuarios_ativos", "cota_usuarios", "criado_em", "ultimo_acesso",
        "cota_bytes", "bytes_usados", "itens", "cota_itens", "jobs_pendentes", "jobs_rodando", "suspensao",
    } <= set(lista[0])
    assert slugs["demo"]["usuarios_ativos"] <= slugs["demo"]["usuarios"] and slugs["demo"]["cota_bytes"] > 0
    # slug reservado (lista única plat.slug_reservado): 'plat' e 'public' são os que o adversário tenta
    for reservado in ("plataforma", "api", "static", "admin", "plat", "public", "mapa", "conteudo"):
        r = sessao_plat.post(
            "/api/plataforma/inquilinos", json={"slug": reservado, "nome": "x", "admin_login": "a", "admin_nome": "A"}
        )
        assert r.status_code == 409 and r.json()["erro"] == "slug_reservado", (reservado, r.text)
    r = sessao_plat.post(
        "/api/plataforma/inquilinos", json={"slug": "demo", "nome": "x", "admin_login": "a", "admin_nome": "A"}
    )
    assert r.status_code == 409 and r.json()["erro"] == "slug_existente"
    for invalido in ("A B", "x", "-abc", "a" * 40, "ção"):
        r = sessao_plat.post(
            "/api/plataforma/inquilinos", json={"slug": invalido, "nome": "x", "admin_login": "a", "admin_nome": "A"}
        )
        assert r.status_code == 422, (invalido, r.text)
    # o próprio inquilino do superadmin não se suspende (refutação do adversário)
    r = sessao_plat.post(f"/api/plataforma/inquilinos/{slugs['plataforma']['id']}/suspender")
    assert r.status_code == 409 and r.json()["erro"] == "plataforma_nao_suspende"
    assert sessao_plat.get("/api/plataforma/inquilinos").json()
    assert sessao_plat.post("/api/plataforma/inquilinos/999999/suspender").status_code == 404
    assert sessao_plat.get("/api/plataforma/inquilinos/999999").status_code == 404
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(2)}"
    r = sessao_plat.post(
        "/api/plataforma/inquilinos",
        json={
            "slug": slug,
            "nome": "Inquilino de teste",
            "admin_login": "gestor",
            "admin_nome": "Gestor",
            "config": {"zoom": 5},
        },
    )
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["admin"]["login"] == "gestor" and len(novo["senha_temporaria"]) == 12
    c = novo_cliente()
    r = entrar(c, slug, "gestor", novo["senha_temporaria"])
    assert r.status_code == 200 and r.json()["usuario"]["pendencias"] == ["trocar_senha"]
    assert (
        r.json()["usuario"]["superadmin"] is False and r.json()["usuario"]["inquilino"]["config_publica"]["zoom"] == 5
    )
    # suspender COM mensagem: login, sessão viva e (abaixo) token recebem 503 com a mensagem; dado intacto
    r = sessao_plat.post(
        f"/api/plataforma/inquilinos/{novo['id']}/suspender", json={"mensagem": "manutenção até sexta"}
    )
    assert r.status_code == 204
    r = c.get("/api/eu")
    assert r.status_code == 503 and r.json()["erro"] == "inquilino_suspenso", r.text
    assert "manutenção até sexta" in r.json()["mensagem"] and r.json()["detalhe"]["mensagem"] == "manutenção até sexta"
    r = novo_cliente().post("/api/login", json={"inquilino": slug, "login": "gestor", "senha": novo["senha_temporaria"]})
    assert r.status_code == 503 and "manutenção até sexta" in r.json()["mensagem"]
    lista = {t["slug"]: t for t in sessao_plat.get("/api/plataforma/inquilinos").json()}
    assert lista[slug]["ativo"] is False and lista[slug]["suspensao"]["mensagem"] == "manutenção até sexta"
    assert lista[slug]["usuarios"] == 1  # nada apagado
    assert sessao_plat.post(f"/api/plataforma/inquilinos/{novo['id']}/reativar").status_code == 204
    assert c.get("/api/eu").status_code == 200  # a mesma sessão volta: dado intacto
    assert sessao_plat.get(f"/api/plataforma/inquilinos/{novo['id']}").json()["suspensao"] is None
    tipos = {e["tipo"] for e in sessao_plat.get("/api/eventos?limite=20").json()["itens"]}
    assert {"inquilinos/criar", "inquilinos/suspender", "inquilinos/reativar"} <= tipos
    # apagar: o inquilino some com tudo (a sessão do admin dele morre), o slug fica livre, plataforma não se apaga
    c.post("/api/grupos", json={"nome": "zt-grupo-do-inquilino"})
    assert sessao_plat.delete(f"/api/plataforma/inquilinos/{novo['id']}").status_code == 204
    assert sessao_plat.delete(f"/api/plataforma/inquilinos/{novo['id']}").status_code == 404
    assert c.get("/api/eu").status_code == 401
    assert slug not in {t["slug"] for t in sessao_plat.get("/api/plataforma/inquilinos").json()}
    r = sessao_plat.delete(f"/api/plataforma/inquilinos/{slugs['plataforma']['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "plataforma_nao_apaga"
    assert "inquilinos/apagar" in {e["tipo"] for e in sessao_plat.get("/api/eventos?limite=5").json()["itens"]}


def test_suspenso_nao_autentica_nem_por_token(sessao_plat, cliente):
    inq = InquilinoTemporario(sessao_plat)
    try:
        r = inq.admin.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-susp", "escopos": ["catalogo:ler"]})
        assert r.status_code == 201, r.text
        token = r.json()["token"]
        assert com_token(cliente, token, "GET", "/api/eu").status_code == 200
        assert sessao_plat.post(f"/api/plataforma/inquilinos/{inq.id}/suspender", json={}).status_code == 204
        r = com_token(cliente, token, "GET", "/api/eu")
        assert r.status_code == 503 and r.json()["erro"] == "inquilino_suspenso", r.text
        assert r.json()["detalhe"]["mensagem"] is None  # sem mensagem: texto padrão
        r = inq.admin.get("/api/eu")
        assert r.status_code == 503 and r.json()["erro"] == "inquilino_suspenso"
        # escrita com token também 503 (nunca 2xx), e o token continua existindo depois de reativar
        assert com_token(cliente, token, "POST", "/api/itens", json={"tipo": "mapa", "titulo": "x"}).status_code == 503
        assert sessao_plat.post(f"/api/plataforma/inquilinos/{inq.id}/reativar").status_code == 204
        assert com_token(cliente, token, "GET", "/api/eu").status_code == 200
        assert inq.admin.get("/api/eu").status_code == 200
    finally:
        inq.apagar()


def test_criar_com_cotas_detalhe_e_alterar_cotas(sessao_plat):
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(2)}"
    r = sessao_plat.post(
        "/api/plataforma/inquilinos",
        json={
            "slug": slug,
            "nome": "Com cotas",
            "admin_login": "admin",
            "admin_nome": "Admin",
            "cotas": {"cota_bytes": 200 * 1024 * 1024, "cota_usuarios": 7, "cota_jobs_dia": 11, "cota_itens": 13},
        },
    )
    assert r.status_code == 201, r.text
    tid, temporaria = r.json()["id"], r.json()["senha_temporaria"]
    try:
        d = sessao_plat.get(f"/api/plataforma/inquilinos/{tid}").json()
        assert d["slug"] == slug and d["ativo"] is True
        assert d["cotas"] == {
            "cota_bytes": 200 * 1024 * 1024, "cota_usuarios": 7, "cota_itens": 13, "cota_jobs_dia": 11,
            "cota_jobs_simultaneos": 2, "cota_agendas": 50,
        }
        assert d["uso"]["usuarios"] == 1 and d["uso"]["bytes_usados"] == 0 and d["uso"]["itens"] == 0
        assert [a["login"] for a in d["admins"]] == ["admin"] and d["admins"][0]["totp_ativo"] is False
        # cota inválida: zero/negativo/abaixo do mínimo = 422; corpo vazio = 422
        for corpo in ({"cota_usuarios": 0}, {"cota_jobs_dia": -1}, {"cota_bytes": 1}, {}, {"outra": 1}):
            r = sessao_plat.put(f"/api/plataforma/inquilinos/{tid}/cotas", json=corpo)
            assert r.status_code == 422, (corpo, r.text)
        r = sessao_plat.put(f"/api/plataforma/inquilinos/{tid}/cotas", json={"cota_usuarios": 9, "cota_agendas": 3})
        assert r.status_code == 200, r.text
        assert r.json()["cotas"]["cota_usuarios"] == 9 and r.json()["cotas"]["cota_agendas"] == 3
        assert r.json()["cotas"]["cota_jobs_dia"] == 11  # chave ausente mantém
        assert sessao_plat.put("/api/plataforma/inquilinos/999999/cotas", json={"cota_usuarios": 9}).status_code == 404
        # a cota vale de verdade: o admin do inquilino vê o mesmo número em GET /api/org
        c = novo_cliente()
        assert entrar(c, slug, "admin", temporaria).status_code == 200
        assert c.put("/api/eu/senha", json={"atual": temporaria, "nova": "Senha-definitiva-1" + secrets.token_hex(3)}).status_code == 204
        org = c.get("/api/org").json()
        assert org["usuarios"]["cota"] == 9 and org["armazenamento"]["cota_bytes"] == 200 * 1024 * 1024
        lista = {t["slug"]: t for t in sessao_plat.get("/api/plataforma/inquilinos").json()}
        assert lista[slug]["cota_usuarios"] == 9 and lista[slug]["cota_itens"] == 13
        ev = sessao_plat.get("/api/plataforma/eventos?tipo=inquilinos/cotas&limite=5").json()
        assert ev["total"] >= 1 and ev["itens"][0]["alvo_id"] == str(tid)
        assert ev["itens"][0]["propriedades"] == {"cota_usuarios": 9, "cota_agendas": 3}
    finally:
        sessao_plat.delete(f"/api/plataforma/inquilinos/{tid}")


def test_2fa_de_admin_desligado_pelo_operador(sessao_plat, sessao_a, ids):
    inq = InquilinoTemporario(sessao_plat)
    try:
        segredo, _codigos = ligar_2fa(inq.admin)
        d = sessao_plat.get(f"/api/plataforma/inquilinos/{inq.id}").json()
        assert d["admins"][0]["totp_ativo"] is True
        # membro comum do inquilino: 409 (o admin do inquilino resolve); usuário de outro inquilino: 404
        r = inq.admin.post("/api/usuarios", json={"login": "editor1", "nome": "Editor", "perfil": "editor"})
        assert r.status_code == 201, r.text
        editor_id = r.json()["usuario"]["id"]
        r = sessao_plat.post(f"/api/plataforma/inquilinos/{inq.id}/admins/{editor_id}/2fa/desativar")
        assert r.status_code == 409 and r.json()["erro"] == "so_admin_de_inquilino", r.text
        r = sessao_plat.post(f"/api/plataforma/inquilinos/{inq.id}/admins/{ids['a']['id']}/2fa/desativar")
        assert r.status_code == 404, r.text
        # nunca no inquilino da plataforma (o 2FA do operador é obrigatório)
        plat_id = next(t["id"] for t in sessao_plat.get("/api/plataforma/inquilinos").json() if t["slug"] == "plataforma")
        r = sessao_plat.post(f"/api/plataforma/inquilinos/{plat_id}/admins/{ids['plat']['id']}/2fa/desativar")
        assert r.status_code == 409 and r.json()["erro"] == "plataforma_2fa_obrigatorio", r.text
        assert sessao_plat.get("/api/eu").status_code == 200  # a sessão do operador segue viva
        # o caso real: admin do inquilino perdeu o aparelho
        r = sessao_plat.post(f"/api/plataforma/inquilinos/{inq.id}/admins/{inq.admin_id}/2fa/desativar")
        assert r.status_code == 204, r.text
        assert inq.admin.get("/api/eu").status_code == 401  # sessões do alvo encerradas
        c = novo_cliente()
        r = c.post("/api/login", json={"inquilino": inq.slug, "login": "admin", "senha": inq.senha})
        assert r.status_code == 200 and not r.json().get("exige_2fa"), r.text
        assert r.json()["usuario"]["totp_ativo"] is False
        inq.admin = c
        ev = sessao_plat.get("/api/plataforma/eventos?tipo=inquilinos/2fa_desligar&limite=3").json()
        assert ev["itens"][0]["propriedades"] == {"usuario_id": inq.admin_id, "login": "admin"}
        assert ev["itens"][0]["ator"]["id"] == ids["plat"]["id"]
    finally:
        inq.apagar()


def test_fila_agregada_e_eventos_da_plataforma(sessao_plat, sessao_a):
    r = sessao_plat.get("/api/plataforma/fila")
    assert r.status_code == 200, r.text
    fila = r.json()
    assert set(fila) == {"total", "mais_antigo_pendente_em", "por_inquilino", "workers"}
    assert set(fila["total"]) == {"pendente", "rodando", "concluido_24h", "falhou_24h", "cancelado_24h"}
    for linha in fila["por_inquilino"]:
        assert {"id", "slug", "pendente", "rodando", "falhou_24h", "concluido_24h"} == set(linha)
    for w in fila["workers"]:
        assert {"nome", "processos", "rodando", "heartbeat_em", "vivo"} == set(w)
    # um job pendente de demo (agendado para o futuro, nunca roda) aparece na linha de demo
    from tests.api import cruzado_casos as cc

    r = sessao_a.post("/api/jobs", json=cc.JOB_PENDENTE)
    if r.status_code == 201:
        try:
            fila = sessao_plat.get("/api/plataforma/fila").json()
            demo = next(x for x in fila["por_inquilino"] if x["slug"] == "demo")
            assert demo["pendente"] >= 1 and fila["total"]["pendente"] >= 1
        finally:
            sessao_a.post(f"/api/jobs/{r.json()['id']}/cancelar")
    # eventos da plataforma: só o inquilino plataforma; paginação; filtro por tipo; nunca eventos de demo
    ev = sessao_plat.get("/api/plataforma/eventos?limite=5").json()
    assert set(ev) == {"total", "itens"} and 0 < len(ev["itens"]) <= 5 and ev["total"] >= len(ev["itens"])
    assert all(e["tipo"].startswith("inquilinos/") or "/" in e["tipo"] for e in ev["itens"])
    ev2 = sessao_plat.get("/api/plataforma/eventos?limite=2&deslocamento=2").json()
    assert [e["id"] for e in ev2["itens"]] == [e["id"] for e in ev["itens"][2:4]]
    ev3 = sessao_plat.get("/api/plataforma/eventos?tipo=inquilinos/criar&limite=3").json()
    assert all(e["tipo"] == "inquilinos/criar" for e in ev3["itens"])
    assert sessao_plat.get("/api/plataforma/eventos?limite=0").status_code == 422
    # o evento de demo criado agora (grupo) NÃO aparece na trilha da plataforma
    nome = f"{PREFIXO_TESTE}-grupo-{secrets.token_hex(2)}"
    g = sessao_a.post("/api/grupos", json={"nome": nome})
    if g.status_code == 201:
        try:
            ev = sessao_plat.get("/api/plataforma/eventos?tipo=grupos/criar&limite=50").json()
            assert nome not in str(ev)
        finally:
            sessao_a.delete(f"/api/grupos/{g.json()['id']}")


def test_superadmin_so_no_inquilino_plataforma(conexao_plat_app):
    from tests.api.test_rls import contexto, ids_por_slug

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="superadmin_so_plataforma"):
            cur.execute("UPDATE plat.usuario SET superadmin = true WHERE login = 'admin'")
    conexao_plat_app.rollback()
