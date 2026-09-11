"""Backup lógico por inquilino e ensaio de restauração (item L0-06-backup-status). Os dois jobs rodam pelo
plat-worker REAL desta trilha (mesmo padrão de tests/api/test_smtp_convites.py: "os testes esperam a
entrega de verdade, não simulam o worker") — o `TestClient` só insere o job pela API; quem executa
pg_dump/pg_restore é o processo `app.jobs.worker` já de pé.

Quatro provas exigidas pelo item:
1. `backup.executar` grava a linha em `plat.backup` e o objeto existe mesmo no bucket do inquilino;
2. `backup.ensaio_restauracao` confere COUNT(*) por tabela e DERRUBA o schema temporário ao final;
3. o inquilino B nunca vê o backup/ensaio do inquilino A (RLS por tenant_id);
4. o teto de tamanho do dump é recusado — sobre a função real de guarda (`app.backup.tarefas.
   _conferir_teto`), não um dump de gigabytes de verdade (impraticável e arriscado com o disco desta
   máquina a 99%, CLAUDE.md)."""

import os
import time

import psycopg2
import psycopg2.extras
import pytest

from app import objetos
from app.backup import nucleo, tarefas

TIMEOUT_JOB_S = 90


def _conexao():
    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    con.autocommit = True
    return con


def esperar_job(sessao, job_id: str, timeout: float = TIMEOUT_JOB_S) -> dict:
    """Espera o job chegar a estado final; devolve o JSON (mesmo padrão de tests/api/catalogo/conftest.py e
    tests/api/ingestao/conftest.py — cópia local: subpacotes-irmãos não compartilham conftest)."""
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = sessao.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
            return ultimo
        time.sleep(1.0)
    pytest.fail(f"job {job_id} não terminou em {timeout} s: {ultimo}")


def disparar(sessao, tipo: str, parametros: dict | None = None) -> dict:
    r = sessao.post("/api/jobs", json={"tipo": tipo, "parametros": parametros or {}})
    assert r.status_code == 201, r.text
    return esperar_job(sessao, r.json()["id"])


@pytest.fixture(scope="module")
def worker_vivo(sessao_a):
    r = sessao_a.get("/saude").json()
    fila = r.get("fila") or {}
    if not fila.get("workers_vivos"):
        pytest.fail(f"nenhum worker vivo em /saude ({fila}) — religue o worker da trilha antes de rodar este teste")
    return fila


@pytest.fixture(scope="module")
def backup_a(worker_vivo, sessao_a):
    """Um backup.executar real do inquilino A, reusado pelos testes de leitura/ensaio (evita repetir o
    pg_dump em cada teste)."""
    job = disparar(sessao_a, "backup.executar")
    assert job["estado"] == "concluido", job
    return job


def test_backup_grava_linha_e_objeto(backup_a, sessao_a):
    resultado = backup_a["resultado"]
    assert resultado["bytes"] > 0
    assert resultado["tabelas"] >= 0
    assert len(resultado["sha256"]) == 64
    assert resultado["esquema"].startswith("d_")

    r = sessao_a.get("/api/backup/backups?limite=1")
    assert r.status_code == 200, r.text
    linha = r.json()["itens"][0]
    assert linha["id"] == resultado["backup_id"]
    assert linha["esquema"] == resultado["esquema"]
    assert linha["sha256"] == resultado["sha256"]
    assert linha["bytes"] == resultado["bytes"]

    # o objeto está mesmo no bucket DESTE inquilino (não um caminho fictício só na linha do banco)
    assert objetos.existe(resultado["chave"])


def test_ensaio_confere_contagem_e_derruba_schema(backup_a, sessao_a):
    job = disparar(sessao_a, "backup.ensaio_restauracao")
    assert job["estado"] == "concluido", job
    resultado = job["resultado"]
    assert resultado["ok"] is True, resultado
    assert resultado["backup_id"] == backup_a["resultado"]["backup_id"]
    assert resultado["tabelas"] >= 0
    assert resultado["duracao_drill_s"] >= 0

    r = sessao_a.get("/api/backup/ensaios?limite=1")
    assert r.status_code == 200, r.text
    linha = r.json()["itens"][0]
    assert linha["id"] == resultado["drill_id"]
    assert linha["ok"] is True
    assert linha["tabelas"] == resultado["tabelas"]
    schema_ensaio = linha["schema_ensaio"]
    assert schema_ensaio and schema_ensaio.startswith(nucleo.PREFIXO_SCHEMA_ENSAIO)

    con = _conexao()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema_ensaio,))
            assert cur.fetchone() is None, f"schema de ensaio {schema_ensaio} não foi derrubado ao final"
    finally:
        con.close()


def test_inquilino_b_nao_ve_backup_do_a(backup_a, sessao_b):
    r = sessao_b.get("/api/backup/backups?limite=200")
    assert r.status_code == 200, r.text
    assert all(item["id"] != backup_a["resultado"]["backup_id"] for item in r.json()["itens"])

    r = sessao_b.get("/api/backup/ensaios?limite=200")
    assert r.status_code == 200, r.text
    # nenhuma linha de ensaio do inquilino A aparece do lado de B (RLS pela mesma política p_backup_drill)
    assert all(item["backup_id"] != backup_a["resultado"]["backup_id"] for item in r.json()["itens"])


def test_teto_do_dump_recusado(tmp_path, monkeypatch):
    """`_conferir_teto` é o guardião real chamado por `backup_executar` (app/backup/tarefas.py) — aqui ele
    roda isolado, sobre um arquivo pequeno com o teto encolhido por monkeypatch, para provar a recusa e o
    apagamento do arquivo sem precisar de um dump de gigabytes."""
    monkeypatch.setattr(tarefas.limites, "BACKUP_DUMP_BYTES_MAX", 10)
    arquivo = tmp_path / "d_demo_20260910_999999.dump"
    arquivo.write_bytes(b"x" * 100)  # 100 bytes > teto (monkeypatchado para 10)

    with pytest.raises(tarefas.FalhaDefinitiva, match="acima do teto"):
        tarefas._conferir_teto(arquivo, "d_demo")
    assert not arquivo.exists(), "o dump acima do teto tem de ser apagado, nunca ficar no disco"


def test_teto_do_dump_aceita_dentro_do_limite(tmp_path, monkeypatch):
    monkeypatch.setattr(tarefas.limites, "BACKUP_DUMP_BYTES_MAX", 1000)
    arquivo = tmp_path / "d_demo_20260910_999998.dump"
    arquivo.write_bytes(b"x" * 100)
    assert tarefas._conferir_teto(arquivo, "d_demo") == 100
    assert arquivo.exists()
