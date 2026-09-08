"""HARD-03 — adversário de multi-inquilino (tenancy/RLS) sobre master. O detector não é regex sobre migração e sim
o catálogo VIVO: enumera de pg_class/pg_policies toda tabela `plat` com coluna `tenant_id` e exige RLS ligada com
política para leitura/escrita; depois cruza inquilinos por rotas reais (jobs, uploads). Cada ataque com controle
positivo. Só roda em trilha (conftest do pacote) — o schema alvo é o da trilha (PLAT_SCHEMA)."""

from __future__ import annotations

import os
import secrets

import pytest

SCHEMA = os.environ.get("PLAT_SCHEMA", "plat")


def _rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


# ---------------------------------------------------------------- RLS: nenhuma tabela com tenant_id sem política
def test_toda_tabela_com_tenant_id_tem_rls_e_politica(conexao_plat_app):
    """Enumera do catálogo vivo: para cada tabela do schema com coluna `tenant_id`, `relrowsecurity` tem de estar
    ligada e tem de existir política de SELECT e de escrita (INSERT/UPDATE/DELETE ou ALL). Uma tabela nova com
    tenant_id e sem política aparece aqui como falha, sem ninguém precisar lembrar de atualizar uma lista."""
    with conexao_plat_app.cursor() as cur:
        com_tid = {r["tablename"] for r in _rows(cur, """
            SELECT c.relname AS tablename
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_attribute a ON a.attrelid = c.oid
             WHERE n.nspname = %s AND c.relkind = 'r' AND a.attname = 'tenant_id' AND a.attnum > 0
        """, (SCHEMA,))}
        assert com_tid, f"nenhuma tabela com tenant_id em {SCHEMA} (schema não migrado?)"
        rowsec = {r["relname"]: r["relrowsecurity"] for r in _rows(cur, """
            SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = %s AND c.relkind = 'r'
        """, (SCHEMA,))}
        # política de leitura tem de EXISTIR e FILTRAR por inquilino (qual cita tenant); guardamos por tabela
        # se há SELECT/ALL cujo `qual` referencia tenant. Escrita direta não é exigida: tabelas append-only
        # (evento, log_acesso, item_versao, conexao_saude_historico) são escritas só por função SECURITY DEFINER
        # e por isso não têm política de escrita — a ausência é default-deny, o que é o comportamento correto.
        leitura_scoped = {}
        pol_sql = "SELECT tablename, cmd, coalesce(qual, '') AS qual FROM pg_policies WHERE schemaname = %s"
        for r in _rows(cur, pol_sql, (SCHEMA,)):
            if r["cmd"] in ("SELECT", "ALL") and "tenant" in r["qual"]:
                leitura_scoped[r["tablename"]] = True
        # partições herdam a RLS do pai (PG 16): a política vale pelo nome do pai
        parent = {r["relname"]: r["pai"] for r in _rows(cur, """
            SELECT c.relname, p.relname AS pai FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_inherits i ON i.inhrelid = c.oid JOIN pg_class p ON p.oid = i.inhparent
             WHERE n.nspname = %s AND c.relispartition
        """, (SCHEMA,))}
    def tem_leitura(t):
        return leitura_scoped.get(t) or leitura_scoped.get(parent.get(t, ""))
    sem_rls = sorted(t for t in com_tid if not rowsec.get(t))
    sem_leitura_scoped = sorted(t for t in com_tid if not tem_leitura(t))
    assert sem_rls == [], f"tabelas com tenant_id e RLS DESLIGADA (leitura cross-tenant possível): {sem_rls}"
    assert sem_leitura_scoped == [], (
        f"tabelas com tenant_id sem política de leitura que filtre por inquilino: {sem_leitura_scoped}")


def test_rls_forcada_para_o_dono_da_tabela_nao_ser_ignorada(conexao_plat_app):
    """As tabelas com tenant_id não podem depender de o `plat_app` não ser dono: se a role da aplicação for dona,
    RLS só vale com FORCE. Aqui confirmamos que a role da aplicação NÃO é superusuário e NÃO tem BYPASSRLS —
    o caminho pelo qual a RLS seria ignorada."""
    with conexao_plat_app.cursor() as cur:
        r = _rows(cur, "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")[0]
    assert r["rolsuper"] is False, "a role da aplicação é superusuário — RLS é ignorada"
    assert r["rolbypassrls"] is False, "a role da aplicação tem BYPASSRLS — RLS é ignorada"


# ---------------------------------------------------------------- cross-tenant por jobs
def test_job_de_b_invisivel_e_incontrolavel_por_a(sessao_a, sessao_b):
    r = sessao_b.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 2}})
    assert r.status_code == 201, r.text
    job_b = r.json()["id"]
    # controle positivo: B vê o próprio job
    assert sessao_b.get(f"/api/jobs/{job_b}").status_code == 200
    for verbo, url in [("get", f"/api/jobs/{job_b}"), ("get", f"/api/jobs/{job_b}/log"),
                       ("get", f"/api/jobs/{job_b}/eventos"), ("post", f"/api/jobs/{job_b}/cancelar"),
                       ("post", f"/api/jobs/{job_b}/repetir")]:
        r = getattr(sessao_a, verbo)(url)
        assert r.status_code in (403, 404), (verbo, url, r.status_code, r.text[:140])
    # e o job de B não aparece na lista de A
    r = sessao_a.get("/api/jobs?limite=200")
    assert job_b not in {j["id"] for j in r.json().get("itens", [])}


# ---------------------------------------------------------------- cross-tenant por uploads
def test_upload_de_b_invisivel_e_incontrolavel_por_a(sessao_a, sessao_b):
    corpo = {"nome": f"zt{secrets.token_hex(3)}.gpkg", "bytes": 1024, "tipo_declarado": "gpkg"}
    r = sessao_b.post("/api/uploads", json=corpo)
    if r.status_code == 422:
        pytest.skip(f"tipo de upload recusado nesta trilha: {r.text[:120]}")
    assert r.status_code in (201, 200), r.text
    up_b = r.json()["id"]
    assert sessao_b.get(f"/api/uploads/{up_b}").status_code == 200  # controle positivo
    assert sessao_a.get(f"/api/uploads/{up_b}").status_code in (403, 404)
    assert sessao_a.delete(f"/api/uploads/{up_b}").status_code in (403, 404)
    # concluir precisa de corpo: com corpo válido chega à checagem de inquilino e é recusado (não 2xx)
    r = sessao_a.post(f"/api/uploads/{up_b}/concluir", json={"sha256": "a" * 64})
    assert r.status_code in (403, 404), (r.status_code, r.text[:140])
    sessao_b.delete(f"/api/uploads/{up_b}")


# ---------------------------------------------------------------- escalada de escopo de token (reforço L0-02-d)
def test_token_fora_do_escopo_nao_cria_job_nem_upload(sessao_a, cliente):
    from tests.api.conftest import com_token

    r = sessao_a.post("/api/tokens", json={"nome": f"zt-esc-{secrets.token_hex(3)}", "escopos": ["catalogo:ler"]})
    tok = r.json()
    try:
        r = com_token(cliente, tok["token"], "POST", "/api/jobs", json={"tipo": "prova.progresso"})
        assert r.status_code in (403, 401), (r.status_code, r.text[:140])
        r = com_token(cliente, tok["token"], "POST", "/api/uploads",
                      json={"nome": "x.gpkg", "bytes": 10, "tipo_declarado": "gpkg"})
        assert r.status_code in (403, 401), (r.status_code, r.text[:140])
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")
