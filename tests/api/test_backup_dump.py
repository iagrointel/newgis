"""Portão literal do item L0-06-a-dump-logico, ponta a ponta contra a base da trilha (worker extra em
subprocesso + TestClient, mesmo padrão de tests/api/jobs): o periódico roda de verdade (POST /api/jobs do
tipo do periódico), o dump sai por `sudo -n -u postgres pg_dump -Fc`, o sha256 da linha casa com o arquivo,
há 1 arquivo por inquilino + 1 do plat, a retenção apaga o excedente, a falha de espaço vira job 'falhou'
COM notificação (evento + e-mail enfileirado), o adversário que corrompe 1 byte é acusado pela verificação,
a linha apagada à mão aparece como arquivo órfão, e o dump de demo2 restaurado num banco temporário conta
as mesmas linhas.

Ordem importa (o arquivo é sequencial): dump completo -> retenção -> espaço -> restauração -> sha ->
órfão -> recusa fora do inquilino técnico. Limpeza: o arquivo órfão do teste é removido no fim."""

import contextlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from app.settings import settings
from tests import jobs_sessao
from tests.api.jobs.conftest import WorkerExtra, criar_job, esperar

ITEM = "L0-06-a-dump-logico"
PORTA_WORKER = 18216


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
def sessao_demo(env):
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        yield jobs_sessao.criar_sessao(con, "demo", "admin")
    finally:
        con.close()


@pytest.fixture(scope="module")
def cliente_demo(env, sessao_demo):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, cookies={jobs_sessao.COOKIE_SESSAO: sessao_demo[0]}) as c:
        yield c


@pytest.fixture(scope="module")
def worker(env, cliente_plataforma):
    w = WorkerExtra(env, f"teste-backup-{os.getpid()}", 1, PORTA_WORKER)
    yield w
    w.parar()


@pytest.fixture(scope="module")
def con_plataforma(env, sessao_plataforma):
    """Conexão como plat_app já no contexto do inquilino técnico (lê plat.backup via RLS/funções).

    `set_config(..., true)` (usado por `jobs_sessao.contexto`) é LOCAL À TRANSAÇÃO: some no primeiro
    commit/rollback da conexão. Como esta conexão é module-scoped e reaproveitada por vários testes em
    transações distintas, guardamos o (tenant_id, usuario_id) em `_plat_ctx` e reaplicamos o contexto a
    cada cursor novo (`_cursor_ctx` abaixo) — mesmo padrão de `jobs_sessao.contexto` chamado a cada bloco
    em `tests/api/jobs/test_jobs_rls.py` e afins."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    from app.schema_ambiente import CursorSchemaAmbiente

    with con.cursor(cursor_factory=CursorSchemaAmbiente) as cur:
        jobs_sessao.contexto(cur, sessao_plataforma[1], sessao_plataforma[2], "admin")
        # cota do inquilino técnico folgada para a rodada de testes + e-mail do superadmin (notificação)
        cur.execute("UPDATE plat.tenant SET config = config || '{\"cota_jobs_dia\": 100000}' "
                    "WHERE slug = 'plataforma'")
        cur.execute("UPDATE plat.usuario SET email = 'superadmin.backup@example.com' WHERE superadmin")
        # limpa o rastro de rodadas anteriores da MESMA trilha (linha + arquivo + objeto do bucket): sem
        # isso `test_01_dump_completo` compara "linhas de plat.backup" com "dumps desta rodada" e vê mais
        # linhas do que dumps (achado real: 2 execuções seguidas da suíte sem limpar deram 7 == 4, nunca
        # verdadeiro). plat.backup_apagar já cuida de arquivo + objeto do Garage, não só da linha.
        cur.execute("SELECT * FROM plat.backup_listar(NULL, 10000)")
        antigos = [dict(r) for r in cur.fetchall()]
        if antigos:
            cur.execute("SELECT * FROM plat.backup_apagar(%s)", ([ln["id"] for ln in antigos],))
    con.commit()
    _CTX[id(con)] = (sessao_plataforma[1], sessao_plataforma[2])
    try:
        yield con
    finally:
        _CTX.pop(id(con), None)
        con.close()


# objeto connection do psycopg2 não aceita atributo novo (tipo C sem __dict__); guarda o (tenant_id,
# usuario_id) por identidade da conexão, popular em con_plataforma e lido por _cursor_ctx
_CTX: dict[int, tuple[int, int]] = {}


@contextlib.contextmanager
def _cursor_ctx(con):
    """Cursor novo já com o contexto (tenant_id/usuario_id) reaplicado — necessário porque `set_config`
    local não sobrevive ao commit da transação anterior na mesma conexão. Faz commit ao sair: sem isso a
    conexão fica presa numa transação idle-in-transaction pelo resto do módulo (inclusive durante o
    `test_04`, que passa dezenas de segundos em subprocessos de pg_dump/pg_restore) e o servidor a derruba
    (`idle_in_transaction_session_timeout`), quebrando os testes seguintes com 'SSL connection has been
    closed unexpectedly' — achado real ao rodar a suíte ponta a ponta, não de leitura de código."""
    from app.schema_ambiente import CursorSchemaAmbiente

    cur = con.cursor(cursor_factory=CursorSchemaAmbiente)
    tenant_id, usuario_id = _CTX[id(con)]
    jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
    try:
        yield cur
    finally:
        con.commit()
        cur.close()


def _listar_backups(con, esquema=None):
    with _cursor_ctx(con) as cur:
        cur.execute("SELECT * FROM plat.backup_listar(%s, 10000)", (esquema,))
        return [dict(r) for r in cur.fetchall()]


def _destino(con):
    with _cursor_ctx(con) as cur:
        cur.execute("SELECT * FROM plat.backup_destino_ler()")
        return dict(cur.fetchone())


def _cliente_garage(linha):
    from app.garage import ClienteS3

    return ClienteS3(settings.PLAT_GARAGE_URL, linha["chave_id"], linha["chave_segredo"],
                     settings.PLAT_GARAGE_REGIAO)


def _ram_livre_gb() -> float:
    for linha in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if linha.startswith("MemAvailable:"):
            return int(linha.split()[1]) / 1e6
    return 0.0


def _rodar(cliente, tipo, parametros, timeout=300, final="concluido"):
    job = criar_job(cliente, tipo, parametros)
    fim = esperar(cliente, job["id"], timeout=timeout)
    assert fim["estado"] == final, json.dumps(fim, ensure_ascii=False)[:800]
    return fim


def test_01_dump_completo(cliente_plataforma, worker, con_plataforma, medida):
    ini = time.monotonic()
    fim = _rodar(cliente_plataforma, "backup.dump_logico", {"origem": "teste"})
    dur = round(time.monotonic() - ini, 1)
    resultado = fim["resultado"]
    dumps = resultado["dumps"]

    # 1 arquivo por inquilino (com schema d_<slug> existente) + 1 do plat
    esquemas = {d["esquema"] for d in dumps}
    assert settings.PLAT_SCHEMA in esquemas
    por_inquilino = {d["slug"] for d in dumps if d["slug"]}
    assert {"demo", "demo2"} <= por_inquilino, dumps
    slugs_vistos = set()
    for d in dumps:
        chave = d["slug"] or "plat"
        assert chave not in slugs_vistos, f"dois arquivos para {chave}"
        slugs_vistos.add(chave)

    from app.backup import nucleo

    for d in dumps:
        caminho = Path(d["arquivo"])
        assert caminho.exists(), d
        assert nucleo.sha256_arquivo(caminho) == d["sha256"], f"sha256 da linha difere do arquivo: {d['arquivo']}"
        assert d["bytes"] == caminho.stat().st_size > 0
        # tabelas >= 0: o inquilino técnico 'plataforma' tem seu próprio d_plataforma, mas vazio (0
        # tabelas) — é um dump legítimo (arquivo com a definição do schema, sha256 íntegro), não um erro
        assert d["tempo_dump_s"] >= 0 and d["tabelas"] >= 0

    # as linhas de plat.backup refletem exatamente os dumps (mais novas primeiro)
    linhas = _listar_backups(con_plataforma)
    assert len(linhas) == len(dumps)
    assert {ln["sha256"] for ln in linhas} == {d["sha256"] for d in dumps}
    assert all(ln["bucket_chave"] for ln in linhas), "cópia no Garage ausente em alguma linha"

    # bucket: objetos dos dumps + manifesto por inquilino (chave, sha256, bytes)
    dest = _destino(con_plataforma)
    cliente = _cliente_garage(dest)
    objetos = {o["chave"]: o for o in cliente.listar(dest["alias"])}
    for ln in linhas:
        assert ln["bucket_chave"] in objetos, f"{ln['bucket_chave']} não está no bucket"
        assert objetos[ln["bucket_chave"]]["bytes"] == ln["bytes"]
    grupos = {(ln["inquilino_slug"] or "plat") for ln in linhas}
    manifestos = {}
    for grupo in grupos:
        chaves_m = sorted(c for c in objetos if c.startswith(f"{grupo}/manifesto-"))
        assert chaves_m, f"sem manifesto para {grupo}"
        manifestos[grupo] = json.loads(cliente.get(dest["alias"], chaves_m[-1]))
    for doc in manifestos.values():
        assert doc["objetos"], doc
        for o in doc["objetos"]:
            assert set(o) == {"chave", "sha256", "bytes"}
            assert o["chave"] in objetos

    medida(ITEM)("dump_completo_arquivos", len(dumps), "arquivos",
                 "POST /api/jobs backup.dump_logico na trilha il006adumpl")
    medida(ITEM)("dump_completo_duracao_s", dur, "s", "esperar(job) até concluido")
    # a carga da máquina ao lado de todo número de tempo: medida de duração sem ela não é prova de nada
    medida(ITEM)("carga_1min", round(os.getloadavg()[0], 2), "carga", "os.getloadavg()[0] na hora do dump")
    medida(ITEM)("ram_livre_gb", round(_ram_livre_gb(), 1), "GB", "MemAvailable de /proc/meminfo")
    medida(ITEM)("dump_completo_bytes", sum(d["bytes"] for d in dumps), "bytes", "soma dos dumps da rodada")
    for d in dumps:
        medida(ITEM)(f"tempo_dump_s[{d['esquema']}]", d["tempo_dump_s"], "s", "plat.backup.tempo_dump_s")
        medida(ITEM)(f"bytes[{d['esquema']}]", d["bytes"], "bytes", "plat.backup.bytes")


def test_02_retencao_apaga_o_excedente(cliente_plataforma, worker, con_plataforma):
    antes = _listar_backups(con_plataforma, "d_demo2")
    assert len(antes) >= 1
    # manter só 1 diário: a 2ª rodada tem de apagar TUDO o que era diário antes dela (inclusive o do teste 01)
    _rodar(cliente_plataforma, "backup.dump_logico",
           {"somente": ["demo2"], "manter_diarios": 1, "origem": "teste"})
    depois1 = _listar_backups(con_plataforma, "d_demo2")
    assert len([ln for ln in depois1 if not ln["semanal"]]) == 1
    _rodar(cliente_plataforma, "backup.dump_logico",
           {"somente": ["demo2"], "manter_diarios": 1, "origem": "teste"})
    depois2 = _listar_backups(con_plataforma, "d_demo2")
    diarios = [ln for ln in depois2 if not ln["semanal"]]
    assert len(diarios) == 1
    assert diarios[0]["id"] != depois1[0]["id"]
    # o arquivo e o objeto do diário anterior saíram junto com a linha
    assert not Path(depois1[0]["arquivo"]).exists()
    dest = _destino(con_plataforma)
    cliente = _cliente_garage(dest)
    assert cliente.head(dest["alias"], depois1[0]["bucket_chave"]) is None
    # o 15º diário é o que sai com o padrão de 14 (prova de unidade em tests/unit/test_backup_nucleo.py);
    # aqui a prova é do caminho real: linha + arquivo + objeto


def test_03_falha_de_espaco_vira_job_falhou_e_notifica(cliente_plataforma, worker, con_plataforma, medida):
    arquivos_antes = set(Path(settings.PLAT_BACKUP_DIR or "var/backups").glob("*.dump")) \
        if settings.PLAT_BACKUP_DIR else set((Path(__file__).resolve().parents[2] / "var" / "backups").glob("*.dump"))
    # 100000 GB (teto de DumpParametros.min_livre_gb) é bem mais que qualquer disco real desta máquina
    fim = _rodar(cliente_plataforma, "backup.dump_logico",
                 {"somente": ["demo2"], "min_livre_gb": 100000, "origem": "teste"}, final="falhou")
    assert "espaço insuficiente" in (fim.get("erro") or ""), fim.get("erro")
    assert "100000.0 GB" in (fim.get("erro") or ""), fim.get("erro")
    # nada foi escrito
    diretorio = Path(settings.PLAT_BACKUP_DIR) if settings.PLAT_BACKUP_DIR \
        else Path(__file__).resolve().parents[2] / "var" / "backups"
    assert set(diretorio.glob("*.dump")) == arquivos_antes
    # notificação, não silêncio: evento auditável + e-mail enfileirado ao superadmin
    with _cursor_ctx(con_plataforma) as cur:
        cur.execute("SELECT propriedades FROM plat.evento WHERE tipo = 'backup/falha' ORDER BY id DESC LIMIT 1")
        ev = cur.fetchone()
        assert ev is not None, "sem evento backup/falha"
        assert "espaço insuficiente" in json.dumps(ev["propriedades"], ensure_ascii=False)
        cur.execute("SELECT estado, parametros FROM plat.job WHERE tipo = 'correio.enviar' "
                    "ORDER BY criado_em DESC LIMIT 1")
        correio = cur.fetchone()
        assert correio is not None, "sem e-mail enfileirado ao superadmin"
        assert correio["parametros"]["destinatario"] == "superadmin.backup@example.com"
        assert correio["parametros"]["categoria"] == "backup"
    medida(ITEM)("falha_espaco_notifica", True, "bool",
                 "job falhou + evento backup/falha + correio.enviar enfileirado")


def test_04_restauracao_conta_as_mesmas_linhas(cliente_plataforma, worker, con_plataforma, medida):
    """O dump de d_demo2 restaurado num banco temporário conta as mesmas linhas, tabela a tabela (L0-06-c).
    Erros de gatilho que apontam para funções de OUTROS schemas (o d_demo2 é compartilhado entre trilhas e
    tem gatilhos criados por outras, ver handoff) são registrados, não escondidos: a prova é por COUNT(*)."""
    linha = _listar_backups(con_plataforma, "d_demo2")[0]
    dump = linha["arquivo"]
    tabelas = subprocess.run(
        ["sudo", "-n", "-u", "postgres", "psql", "-d", "iagro_sat", "-Atc",
         "SELECT tablename FROM pg_tables WHERE schemaname='d_demo2' ORDER BY 1"],
        capture_output=True, text=True, check=True).stdout.split()
    assert tabelas, "d_demo2 sem tabelas na base"
    tempdb = f"plat_rst_{os.getpid()}"
    erros_restore = ""
    try:
        subprocess.run(["sudo", "-n", "-u", "postgres", "createdb", tempdb], check=True)
        subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", tempdb, "-q", "-c",
                        "CREATE EXTENSION IF NOT EXISTS postgis"], check=True, capture_output=True)
        r = subprocess.run(["sudo", "-n", "-u", "postgres", "pg_restore", "-d", tempdb,
                            "--no-owner", "--no-privileges", dump], capture_output=True, text=True)
        erros_restore = (r.stderr or "").strip()
        for t in tabelas:
            origem = subprocess.run(
                ["sudo", "-n", "-u", "postgres", "psql", "-d", "iagro_sat", "-Atc",
                 f'SELECT count(*) FROM "d_demo2"."{t}"'], capture_output=True, text=True, check=True).stdout.strip()
            copia = subprocess.run(
                ["sudo", "-n", "-u", "postgres", "psql", "-d", tempdb, "-Atc",
                 f'SELECT count(*) FROM "d_demo2"."{t}"'], capture_output=True, text=True, check=True).stdout.strip()
            assert origem == copia, f"tabela {t}: origem {origem} != restaurada {copia}"
        total = sum(int(subprocess.run(
            ["sudo", "-n", "-u", "postgres", "psql", "-d", tempdb, "-Atc",
             f'SELECT count(*) FROM "d_demo2"."{t}"'], capture_output=True, text=True, check=True).stdout.strip())
            for t in tabelas)
    finally:
        subprocess.run(["sudo", "-n", "-u", "postgres", "dropdb", "--if-exists", tempdb],
                       capture_output=True)
    assert total > 0, "restauração sem nenhuma linha não prova nada"
    medida(ITEM)("restauracao_demo2_tabelas", len(tabelas), "tabelas", "COUNT(*) por tabela origem == cópia")
    medida(ITEM)("restauracao_demo2_linhas", total, "linhas", "soma dos COUNT(*) no banco temporário")
    medida(ITEM)("restauracao_demo2_avisos_pg_restore", erros_restore[:300], "texto",
                 "stderr do pg_restore (gatilhos de outros schemas, dado compartilhado entre trilhas)")


def test_05_adversario_corrompe_1_byte_e_a_verificacao_acusa(cliente_plataforma, worker, con_plataforma, medida):
    linha = _listar_backups(con_plataforma, "d_demo2")[0]
    caminho = Path(linha["arquivo"])
    with open(caminho, "r+b") as f:
        f.seek(100)
        original = f.read(1)
        f.seek(100)
        f.write(bytes([original[0] ^ 0x01]))
    fim = _rodar(cliente_plataforma, "backup.verificar", {"esquema": "d_demo2"}, final="falhou")
    assert linha["arquivo"] in (fim.get("erro") or ""), fim.get("erro")
    assert "sha256 divergente" in (fim.get("erro") or "")
    medida(ITEM)("adversario_1_byte_acusado", True, "bool",
                 "corromper 1 byte do último dump -> backup.verificar falhou nomeando o arquivo")


def test_06_linha_apagada_vira_arquivo_orfao_listado(cliente_plataforma, worker, con_plataforma, medida):
    linha = _listar_backups(con_plataforma, "d_demo2")[0]
    with _cursor_ctx(con_plataforma) as cur:
        cur.execute("SELECT * FROM plat.backup_apagar(%s)", ([linha["id"]],))
        assert cur.fetchone()["id"] == linha["id"]
    con_plataforma.commit()
    fim = _rodar(cliente_plataforma, "backup.verificar", {"esquema": "d_demo2"})
    orfaos = fim["resultado"]["orfaos"]
    assert linha["arquivo"] in orfaos, fim["resultado"]
    medida(ITEM)("adversario_orfao_listado", True, "bool",
                 "apagar a linha de plat.backup -> verificar conclui listando o arquivo órfão")
    # limpeza: remove o órfão (e os irmãos da mesma chave no bucket ficam para a retenção natural)
    Path(linha["arquivo"]).unlink(missing_ok=True)


def test_07_recusa_fora_do_inquilino_tecnico(cliente_demo, worker):
    fim = _rodar(cliente_demo, "backup.dump_logico", {"origem": "teste"}, final="falhou")
    assert "plataforma" in (fim.get("erro") or "")
