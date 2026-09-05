"""db/migrar.sh: idempotente (segunda rodada não insere linha), código 3 em arquivo aplicado editado,
RLS ativa com política em toda tabela com tenant_id (ADR 0001 seção 5 e portão P6)."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRAR = ROOT / "db" / "migrar.sh"
MIGRACOES = ROOT / "db" / "migracoes"


def rodar(**env):
    return subprocess.run(["bash", str(MIGRAR)], capture_output=True, text=True, env={**os.environ, **env})


def linhas(con):
    con.rollback()
    with con.cursor() as cur:
        cur.execute("SELECT nome, sha256 FROM plat.versao_migracao ORDER BY nome")
        return [(r["nome"], r["sha256"]) for r in cur.fetchall()]


def test_migrar_duas_vezes_nao_insere_linha(conexao_plat_app):
    antes = linhas(conexao_plat_app)
    r1 = rodar()
    assert r1.returncode == 0, r1.stderr
    r2 = rodar()
    assert r2.returncode == 0, r2.stderr
    assert linhas(conexao_plat_app) == antes
    assert "pendentes 0" in r2.stdout and "aplicadas 0" in r2.stdout
    assert r2.stdout.count("igual ") == len(list(MIGRACOES.glob("[0-9][0-9][0-9]_*.sql")))


def test_tabela_reflete_os_arquivos_em_disco(conexao_plat_app):
    nomes = {n for n, _ in linhas(conexao_plat_app)}
    assert nomes == {p.stem for p in MIGRACOES.glob("[0-9][0-9][0-9]_*.sql")}


def test_arquivo_aplicado_editado_devolve_codigo_3(tmp_path, conexao_plat_app):
    copia = tmp_path / "migracoes"
    shutil.copytree(MIGRACOES, copia)
    alvo = copia / "001_fundacao.sql"
    alvo.write_text(alvo.read_text(encoding="utf-8") + "\n-- edição posterior à aplicação\n", encoding="utf-8")
    antes = linhas(conexao_plat_app)
    r = rodar(PLAT_MIGRACOES=str(copia))
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "DIVERGENTE 001_fundacao" in r.stderr
    assert linhas(conexao_plat_app) == antes


def test_toda_tabela_com_tenant_id_tem_rls_e_politica(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("""
            SELECT c.relname, c.relrowsecurity,
                   (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS politicas
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'plat' AND c.relkind IN ('r', 'p')
              AND EXISTS (SELECT 1 FROM pg_attribute a
                          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
            ORDER BY 1""")
        tabelas = cur.fetchall()
    assert {t["relname"] for t in tabelas} >= {"usuario", "sessao", "token_servico", "log_acesso"}
    sem_rls = [t["relname"] for t in tabelas if not t["relrowsecurity"]]
    sem_politica = [t["relname"] for t in tabelas if t["politicas"] == 0]
    assert sem_rls == [], f"tabelas com tenant_id sem RLS: {sem_rls}"
    assert sem_politica == [], f"tabelas com tenant_id sem política: {sem_politica}"


def test_tenant_tambem_tem_rls(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'plat.tenant'::regclass")
        assert cur.fetchone()["relrowsecurity"] is True
