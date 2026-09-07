"""Portão literal do item L0-06-c-restore-drill, ponta a ponta contra a base da trilha (worker extra em
subprocesso + TestClient, mesmo padrão de tests/api/test_backup_dump.py): o ensaio restaura o último dump
num banco temporário, compara COUNT(*) de todas as tabelas com tenant_id contra a produção, confere o
sha256 de objetos do bucket contra o manifesto, grava a linha em plat.backup_drill e publica a data do
último ensaio em /saude. O dump corrompido de propósito é acusado e notificado.

Ordem importa (o arquivo é sequencial): ensaio curto de demo2 -> linha nova depois do dump -> dump
corrompido -> página de status. O dump corrompido é apagado no fim (arquivo + linha)."""

import contextlib
import json
import os
import time
from pathlib import Path

import pytest

from app.settings import settings
from tests import jobs_sessao
from tests.api.jobs.conftest import WorkerExtra, criar_job, esperar

ITEM = "L0-06-c-restore-drill"
PORTA_WORKER = 18217
TETO_DRILL_CURTO_S = 60.0


@pytest.fixture(scope="module")
def sessao_plataforma(env):
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        yield jobs_sessao.criar_sessao(con, "plataforma", "admin")
    finally:
        con.close()


@pytest.fixture(scope="module")
def cliente_plataforma(env, sessao_plataforma):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, cookies={jobs_sessao.COOKIE_SESSAO: sessao_plataforma[0]}) as c:
        yield c


@pytest.fixture(scope="module")
def worker(env, cliente_plataforma):
    w = WorkerExtra(env, f"teste-drill-{os.getpid()}", 1, PORTA_WORKER)
    yield w
    w.parar()


_CTX: dict[int, tuple[int, int]] = {}


@pytest.fixture(scope="module")
def con_plataforma(env, sessao_plataforma):
    """Conexão como o papel da aplicação já no inquilino técnico; o contexto é reaplicado a cada cursor
    porque `set_config(..., true)` é local à transação (mesma razão de tests/api/test_backup_dump.py)."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    from app.schema_ambiente import CursorSchemaAmbiente

    with con.cursor(cursor_factory=CursorSchemaAmbiente) as cur:
        jobs_sessao.contexto(cur, sessao_plataforma[1], sessao_plataforma[2], "admin")
        cur.execute("UPDATE plat.tenant SET config = config || '{\"cota_jobs_dia\": 100000}' "
                    "WHERE slug = 'plataforma'")
        cur.execute("UPDATE plat.usuario SET email = 'superadmin.backup@example.com' WHERE superadmin")
    con.commit()
    _CTX[id(con)] = (sessao_plataforma[1], sessao_plataforma[2])
    try:
        yield con
    finally:
        _CTX.pop(id(con), None)
        con.close()


@contextlib.contextmanager
def _cursor_ctx(con):
    from app.schema_ambiente import CursorSchemaAmbiente

    cur = con.cursor(cursor_factory=CursorSchemaAmbiente)
    tenant_id, usuario_id = _CTX[id(con)]
    jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
    try:
        yield cur
    finally:
        con.commit()
        cur.close()


def _rodar(cliente, tipo, parametros, timeout=600, final="concluido"):
    job = criar_job(cliente, tipo, parametros)
    fim = esperar(cliente, job["id"], timeout=timeout)
    assert fim["estado"] == final, json.dumps(fim, ensure_ascii=False)[:800]
    return fim


def _drills(con, esquema=None):
    with _cursor_ctx(con) as cur:
        cur.execute("SELECT * FROM plat.backup_drill_listar(%s, 100)", (esquema,))
        return [dict(r) for r in cur.fetchall()]


def _backups(con, esquema=None):
    with _cursor_ctx(con) as cur:
        cur.execute("SELECT * FROM plat.backup_listar(%s, 100)", (esquema,))
        return [dict(r) for r in cur.fetchall()]


def _ram_livre_gb() -> float:
    for linha in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if linha.startswith("MemAvailable:"):
            return int(linha.split()[1]) / 1e6
    return 0.0


def test_01_drill_curto_de_demo2_sem_divergencia(cliente_plataforma, worker, con_plataforma, medida):
    """Ensaio curto (um inquilino) — é este que entra no `make check` pela suíte: dump fresco, restauração
    num banco temporário, COUNT(*) igual tabela a tabela e sha256 dos objetos contra o manifesto."""
    _rodar(cliente_plataforma, "backup.dump_logico", {"somente": ["demo2"], "origem": "teste"})
    ini = time.monotonic()
    fim = _rodar(cliente_plataforma, "backup.restore_drill", {"somente": ["demo2"], "origem": "teste"})
    dur = round(time.monotonic() - ini, 1)
    resultado = fim["resultado"]
    assert resultado["esquemas"] == 1, resultado
    ensaio = resultado["ensaios"][0]
    assert ensaio["esquema"] == "d_demo2"
    assert ensaio["divergencias"] == [], ensaio
    assert ensaio["ok"] is True
    assert ensaio["tabelas"] >= 1, "d_demo2 sem tabela com tenant_id: o ensaio não provaria nada"
    assert ensaio["objetos_conferidos"] >= 1, "nenhum objeto do bucket conferido contra o manifesto"

    linhas = _drills(con_plataforma, "d_demo2")
    assert linhas, "ensaio não gravou linha em plat.backup_drill"
    linha = linhas[0]
    assert linha["ok"] is True and linha["divergencias"] == []
    assert linha["tabelas"] == ensaio["tabelas"] and linha["linhas"] == ensaio["linhas"]
    assert float(linha["duracao_drill_s"]) > 0
    # a base de comparação é o instante do dump, gravado na linha
    assert linha["dump_em"] is not None

    medida(ITEM)("drill_curto_duracao_s", dur, "s",
                 "POST /api/jobs backup.restore_drill somente=[demo2] até concluido")
    medida(ITEM)("duracao_drill_s", float(linha["duracao_drill_s"]), "s", "plat.backup_drill.duracao_drill_s")
    medida(ITEM)("drill_curto_teto_s", TETO_DRILL_CURTO_S, "s", "cláusula do portão: drill curto <= 60 s")
    medida(ITEM)("drill_curto_tabelas", ensaio["tabelas"], "tabelas", "tabelas com tenant_id em d_demo2")
    medida(ITEM)("drill_curto_linhas", ensaio["linhas"], "linhas", "soma dos COUNT(*) na cópia restaurada")
    medida(ITEM)("drill_curto_objetos", ensaio["objetos_conferidos"], "objetos",
                 "objetos do bucket com sha256 conferido contra o manifesto")
    medida(ITEM)("carga_1min", round(os.getloadavg()[0], 2), "carga", "os.getloadavg()[0] na hora do ensaio")
    medida(ITEM)("ram_livre_gb", round(_ram_livre_gb(), 1), "GB", "MemAvailable de /proc/meminfo")
    assert dur <= TETO_DRILL_CURTO_S, (
        f"ensaio curto levou {dur} s (teto {TETO_DRILL_CURTO_S} s, carga {os.getloadavg()[0]:.2f})")


def test_02_linha_nova_apos_o_dump_e_acusada_como_posterior(cliente_plataforma, worker, con_plataforma,
                                                            medida):
    """Refutação do adversário: acrescentar linha na produção DEPOIS do dump. O ensaio compara com o
    instante do dump, então a diferença aparece nomeada (tabela e delta) e não vira divergência."""
    _rodar(cliente_plataforma, "backup.dump_logico", {"somente": ["plat"], "origem": "teste"})
    with _cursor_ctx(con_plataforma) as cur:
        for _ in range(3):
            cur.execute("SELECT plat.evento_registrar('backup/ensaio', 'backup', NULL, "
                        "'{\"origem\": \"refutacao L0-06-c\"}'::jsonb, NULL, NULL)")
    fim = _rodar(cliente_plataforma, "backup.restore_drill", {"somente": ["plat"], "origem": "teste"})
    ensaio = fim["resultado"]["ensaios"][0]
    assert ensaio["esquema"] == settings.PLAT_SCHEMA
    assert ensaio["divergencias"] == [], ensaio["divergencias"]
    eventos = [p for p in ensaio["posteriores"] if p["tabela"].startswith("evento")]
    assert eventos, f"a linha nova não foi acusada: {ensaio['posteriores']}"
    assert sum(p["delta"] for p in eventos) >= 3, eventos
    medida(ITEM)("posterior_delta_evento", sum(p["delta"] for p in eventos), "linhas",
                 "3 eventos gravados depois do dump; delta das partições de evento no ensaio")
    medida(ITEM)("drill_plat_tabelas", ensaio["tabelas"], "tabelas",
                 f"tabelas com tenant_id em {settings.PLAT_SCHEMA}")


def test_03_dump_corrompido_registra_a_divergencia_e_notifica(cliente_plataforma, worker, con_plataforma,
                                                              medida):
    _rodar(cliente_plataforma, "backup.dump_logico", {"somente": ["demo2"], "origem": "teste"})
    linha = _backups(con_plataforma, "d_demo2")[0]
    caminho = Path(linha["arquivo"])
    with open(caminho, "r+b") as f:
        f.seek(64)
        original = f.read(1)
        f.seek(64)
        f.write(bytes([original[0] ^ 0xFF]))
    fim = _rodar(cliente_plataforma, "backup.restore_drill", {"somente": ["demo2"], "origem": "teste"},
                 final="falhou")
    assert "sha256 do dump difere" in (fim.get("erro") or ""), fim.get("erro")

    registro = _drills(con_plataforma, "d_demo2")[0]
    assert registro["ok"] is False
    assert registro["divergencias"], registro
    assert registro["divergencias"][0]["arquivo"] == str(caminho)
    assert "sha256" in registro["divergencias"][0]["motivo"]

    with _cursor_ctx(con_plataforma) as cur:
        cur.execute("SELECT propriedades FROM plat.evento WHERE tipo = 'backup/falha' ORDER BY id DESC LIMIT 1")
        ev = cur.fetchone()
        assert ev is not None, "sem evento backup/falha"
        assert "ensaio de restauração" in json.dumps(ev["propriedades"], ensure_ascii=False)
        cur.execute("SELECT parametros FROM plat.job WHERE tipo = 'correio.enviar' "
                    "ORDER BY criado_em DESC LIMIT 1")
        correio = cur.fetchone()
        assert correio is not None, "sem e-mail enfileirado ao superadmin"
        assert correio["parametros"]["destinatario"] == "superadmin.backup@example.com"
    medida(ITEM)("dump_corrompido_acusado_e_notificado", True, "bool",
                 "1 byte trocado no dump -> job falhou + linha ok=false + evento backup/falha + correio")

    # limpeza: o dump corrompido sai (linha + arquivo + objeto), a trilha não fica com backup ruim
    with _cursor_ctx(con_plataforma) as cur:
        cur.execute("SELECT * FROM plat.backup_apagar(%s)", ([linha["id"]],))
    caminho.unlink(missing_ok=True)


def test_04_status_publica_a_data_do_ultimo_ensaio(cliente_plataforma):
    corpo = cliente_plataforma.get("/saude").json()
    assert "backup_drill" in corpo, corpo
    bloco = corpo["backup_drill"]
    assert bloco.get("ultimo_em"), bloco
    assert "ok" in bloco and "divergencias" in bloco and "duracao_drill_s" in bloco
