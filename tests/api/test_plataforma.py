"""Superadmin (ADR 0002 seção 10): 404 para não superadmin; slug reservado/existente; plataforma não se suspende;
inquilino novo nasce com admin em trocar_senha; superadmin só existe no inquilino plataforma (gatilho)."""

import secrets

import psycopg2
import pytest

from tests.api.conftest import PREFIXO_TESTE, entrar, novo_cliente


def test_404_para_nao_superadmin(sessao_a, cliente, token_a):
    assert sessao_a.get("/api/plataforma/inquilinos").status_code == 404
    assert (
        sessao_a.post(
            "/api/plataforma/inquilinos", json={"slug": "x", "nome": "x", "admin_login": "a", "admin_nome": "a"}
        ).status_code
        == 404
    )
    assert cliente.get("/api/plataforma/inquilinos").status_code == 404
    r = cliente.get("/api/plataforma/inquilinos", headers={"Authorization": f"Bearer {token_a['token']}"})
    assert r.status_code == 404


def test_listar_criar_suspender(sessao_plat, cred):
    lista = sessao_plat.get("/api/plataforma/inquilinos").json()
    slugs = {t["slug"]: t for t in lista}
    assert {"plataforma", "demo", "demo2"} <= set(slugs) and slugs["demo"]["usuarios"] >= 1
    assert {"id", "slug", "nome", "ativo", "usuarios", "criado_em", "ultimo_acesso"} == set(lista[0])
    for reservado in ("plataforma", "api", "static", "admin"):
        r = sessao_plat.post(
            "/api/plataforma/inquilinos", json={"slug": reservado, "nome": "x", "admin_login": "a", "admin_nome": "A"}
        )
        assert r.status_code == 409, (reservado, r.text)
    r = sessao_plat.post(
        "/api/plataforma/inquilinos", json={"slug": "demo", "nome": "x", "admin_login": "a", "admin_nome": "A"}
    )
    assert r.status_code == 409 and r.json()["erro"] == "slug_existente"
    assert (
        sessao_plat.post(
            "/api/plataforma/inquilinos", json={"slug": "A B", "nome": "x", "admin_login": "a", "admin_nome": "A"}
        ).status_code
        == 422
    )
    r = sessao_plat.post(f"/api/plataforma/inquilinos/{slugs['plataforma']['id']}/suspender")
    assert r.status_code == 409 and r.json()["erro"] == "plataforma_nao_suspende"
    assert sessao_plat.post("/api/plataforma/inquilinos/999999/suspender").status_code == 404
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
    assert sessao_plat.post(f"/api/plataforma/inquilinos/{novo['id']}/suspender").status_code == 204
    assert c.get("/api/eu").status_code == 401
    assert sessao_plat.post(f"/api/plataforma/inquilinos/{novo['id']}/reativar").status_code == 204
    assert c.get("/api/eu").status_code == 200
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


def test_superadmin_so_no_inquilino_plataforma(conexao_plat_app):
    from tests.api.test_rls import contexto, ids_por_slug

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="superadmin_so_plataforma"):
            cur.execute("UPDATE plat.usuario SET superadmin = true WHERE login = 'admin'")
    conexao_plat_app.rollback()
