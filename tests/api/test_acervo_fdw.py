"""Item L6-01-j-multi-servidor: camadas do acervo que vivem em OUTRO servidor da casa, lidas por
postgres_fdw só-leitura (migração 20260906T2108_acervo_remoto_fdw; `scripts/acervo_fdw_sync.py`).

Portão de pronto (3 cláusulas, `laco/estado.json`):
  1. "3 tabelas remotas lidas por FDW com tempo medido" -> test_tres_tabelas_remotas_lidas_por_fdw_com_tempo_medido
  2. "ficha mostra 'servidor remoto'" -> test_ficha_mostra_servidor_remoto
  3. "falha de rede vira aviso, não camada vazia" -> test_falha_de_rede_vira_aviso_nao_camada_vazia

Fixture: um servidor "remoto" em LOOPBACK (mesma instância Postgres, host 127.0.0.1, schema separado
de `plat_tf<trilha>`) — postgres_fdw não distingue loopback de máquina de verdade; o mecanismo testado
(CREATE SERVER, USER MAPPING, IMPORT FOREIGN SCHEMA, COUNT(*) através da foreign table, connect_timeout)
é IDÊNTICO ao de um servidor remoto de verdade. As candidatas entram por declaração manual em
`acervo_servidor_tabela` (mesmo caminho que a documentação do script descreve para não poluir
`acervo.objeto`, que é o registro real e compartilhado). `fonte_id` usa uma fonte REAL e com licença
escrita (`acervo.fonte`, regra D17) para que a ficha (`GET /api/acervo/{fonte_id}`) a exiba — só leitura,
nada é alterado em `acervo.fonte`.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import psycopg2.sql
import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "scripts" / "acervo_fdw_sync.py"
FONTE_COM_LICENCA = "mesmas-paginas-de-lote"  # lida, não alterada; ver classe de teste para a query dinâmica


def _psql(sql: str, banco: str = "iagro_sat") -> None:
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-d", banco, "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"psql falhou: {r.stderr}\nSQL: {sql}"


def _rodar_fdw_sync(schema_plat: str, segredos: Path, servidor: str | None = None, timeout: int = 60):
    args = ["sudo", "-u", "postgres", "python3", str(SYNC), "--banco", "iagro_sat",
            "--schema", schema_plat, "--segredos", str(segredos)]
    if servidor:
        args += ["--servidor-remoto", servidor]
    return subprocess.run(args, capture_output=True, text=True, env=os.environ.copy(), timeout=timeout)


@pytest.fixture(scope="module")
def fdw_fixture(env):
    """Monta a fixture uma vez para os 3 testes do item: schema 'remoto' com 3 tabelas geométricas +
    servidor declarado em plat_t<trilha>.acervo_servidor + 3 candidatas em acervo_servidor_tabela.
    Fonte real com licença escrita, escolhida dinamicamente (nunca hardcoded contra o dia em que ela
    perder a licença ou sumir)."""
    schema_plat = env["PLAT_SCHEMA"]
    if not schema_plat or schema_plat == "plat":
        pytest.skip("precisa rodar contra uma base de trilha (PLAT_SCHEMA=plat_t<nome>), nunca produção")

    worker_dsn = urlparse(env["PLAT_DSN_WORKER"])
    worker_user = worker_dsn.username
    worker_pass = worker_dsn.password

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT fonte_id FROM acervo.fonte WHERE licenca IS NOT NULL AND btrim(licenca) <> '' "
                        "ORDER BY fonte_id LIMIT 1")
            r = cur.fetchone()
    finally:
        con.close()
    assert r is not None, "o teste pressupõe pelo menos 1 fonte com licença escrita em acervo.fonte"
    fonte_id = r["fonte_id"]

    schema_remoto = f"{schema_plat}_fdw_remoto_teste"
    tabelas = ["teste_fdw_a", "teste_fdw_b", "teste_fdw_c"]
    # a rodada roda como `postgres` (sudo -u postgres, mesma identidade de db/migrar.sh); o cofre de
    # teste precisa ser LEGÍVEL por esse usuário. `tmp_path_factory` fica sob um diretório 0700 do
    # `dev` (pytest-of-dev/pytest-N), que barra a TRAVESSIA para `postgres` mesmo com o arquivo em
    # 644 — por isso o cofre de teste mora à parte, em /tmp, com o caminho todo aberto (é senha de
    # role de teste isolada da trilha, não segredo de produção).
    import shutil
    import tempfile

    segredos = Path(tempfile.mkdtemp(prefix="plat_fdw_segredos_teste_"))
    os.chmod(segredos, 0o755)
    (segredos / "loop_pw").write_text(worker_pass, encoding="utf-8")
    os.chmod(segredos / "loop_pw", 0o644)

    _psql(f"DROP SCHEMA IF EXISTS {schema_remoto} CASCADE")
    _psql(f"CREATE SCHEMA {schema_remoto}")
    linhas_por_tabela = {"teste_fdw_a": 3, "teste_fdw_b": 5, "teste_fdw_c": 2}
    for t in tabelas:
        n = linhas_por_tabela[t]
        _psql(
            f"CREATE TABLE {schema_remoto}.{t} (id serial PRIMARY KEY, nome text, "
            f"geom geometry(Point, 4326))"
        )
        valores = ", ".join(f"('item {i}', ST_SetSRID(ST_MakePoint({i}, {i}), 4326))" for i in range(n))
        _psql(f"INSERT INTO {schema_remoto}.{t} (nome, geom) VALUES {valores}")
        _psql(f"GRANT SELECT ON {schema_remoto}.{t} TO {worker_user}")
    _psql(f"GRANT USAGE ON SCHEMA {schema_remoto} TO {worker_user}")

    servidor = "teste_loop_ok"
    _psql(
        f"INSERT INTO {schema_plat}.acervo_servidor "
        f"(servidor, host, porta, banco, fdw_usuario, segredo_ref, ativo) "
        f"VALUES ('{servidor}', '127.0.0.1', 5432, 'iagro_sat', '{worker_user}', 'loop_pw', true) "
        f"ON CONFLICT (servidor) DO UPDATE SET host = EXCLUDED.host, porta = EXCLUDED.porta, "
        f"fdw_usuario = EXCLUDED.fdw_usuario, segredo_ref = EXCLUDED.segredo_ref, ativo = true"
    )
    for t in tabelas:
        _psql(
            f"INSERT INTO {schema_plat}.acervo_servidor_tabela (servidor, schema_nome, tabela, fonte_id) "
            f"VALUES ('{servidor}', '{schema_remoto}', '{t}', '{fonte_id}') "
            f"ON CONFLICT (servidor, schema_nome, tabela) DO UPDATE SET fonte_id = EXCLUDED.fonte_id"
        )

    dados = {
        "schema_plat": schema_plat, "schema_remoto": schema_remoto, "servidor": servidor,
        "tabelas": tabelas, "linhas_por_tabela": linhas_por_tabela, "fonte_id": fonte_id,
        "segredos": segredos, "worker_user": worker_user,
    }
    yield dados

    # teardown: nunca depende do DROP SCHEMA plat_t<trilha> CASCADE do fim de turno — o SERVER FDW é
    # objeto GLOBAL (fora de qualquer schema) e o schema remoto de teste está FORA de plat_t<trilha>.
    nome_srv = f"fdw_{schema_plat}_{servidor}"
    _psql(f"DROP SERVER IF EXISTS {nome_srv} CASCADE")
    _psql(f"DELETE FROM {schema_plat}.acervo_servidor WHERE servidor = '{servidor}'")
    _psql(f"DROP SCHEMA IF EXISTS {schema_remoto} CASCADE")
    shutil.rmtree(segredos, ignore_errors=True)


def test_tres_tabelas_remotas_lidas_por_fdw_com_tempo_medido(fdw_fixture, medida):
    """Cláusula 1: 3 tabelas remotas lidas por FDW, com `fdw_latencia_ms` MEDIDO (nunca digitado) e
    `linhas_exatas` batendo com o COUNT(*) real da tabela remota."""
    grava = medida("L6-01-j-multi-servidor")
    d = fdw_fixture
    inicio = time.monotonic()
    r = _rodar_fdw_sync(d["schema_plat"], d["segredos"], servidor=d["servidor"])
    duracao = time.monotonic() - inicio
    assert r.returncode == 0, r.stderr
    print(f"acervo_fdw_sync.py (3 tabelas, servidor de teste): {duracao:.2f}s — {r.stdout.strip()}")
    grava("tabelas_remotas_lidas_por_fdw", 3, "tabelas",
          "test_tres_tabelas_remotas_lidas_por_fdw_com_tempo_medido")
    grava("duracao_rodada_3_tabelas", round(duracao, 2), "s",
          "test_tres_tabelas_remotas_lidas_por_fdw_com_tempo_medido")

    from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA

    plat_dsn = os.environ["PLAT_DSN"]
    con = psycopg2.connect(plat_dsn, cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT tabela, modo_acesso, linhas_exatas, fdw_latencia_ms, fdw_verificado_em, fdw_tabela "
                "FROM plat.acervo_camada WHERE servidor = %s ORDER BY tabela",
                (d["servidor"],),
            )
            linhas = cur.fetchall()
    finally:
        con.close()

    assert len(linhas) == 3, f"esperava 3 camadas remotas, achei {len(linhas)}: {linhas}"
    for row in linhas:
        assert row["modo_acesso"] == "fdw", row
        assert row["fdw_latencia_ms"] is not None and row["fdw_latencia_ms"] >= 0, row
        assert row["fdw_verificado_em"] is not None, row
        assert row["linhas_exatas"] == d["linhas_por_tabela"][row["tabela"]], row
        assert row["fdw_tabela"], row
        print(f"  {row['tabela']}: linhas_exatas={row['linhas_exatas']} "
              f"fdw_latencia_ms={row['fdw_latencia_ms']} fdw_tabela={row['fdw_tabela']}")
    grava("fdw_latencia_ms_maxima", max(row["fdw_latencia_ms"] for row in linhas), "ms",
          "test_tres_tabelas_remotas_lidas_por_fdw_com_tempo_medido")


def test_ficha_mostra_servidor_remoto(fdw_fixture, sessao_a):
    """Cláusula 2: a ficha da fonte (GET /api/acervo/{fonte_id}) mostra que a camada vem de OUTRO
    servidor — texto literal 'servidor remoto (<nome>)', nunca escondido atrás de um código."""
    d = fdw_fixture
    # garante que a rodada da cláusula 1 já aconteceu (mesma fixture de módulo; se este teste rodar
    # sozinho, sincroniza aqui — não depende de ordem entre funções)
    r = _rodar_fdw_sync(d["schema_plat"], d["segredos"], servidor=d["servidor"])
    assert r.returncode == 0, r.stderr

    resp = sessao_a.get(f"/api/acervo/{d['fonte_id']}")
    assert resp.status_code == 200, resp.text
    j = resp.json()
    camadas_remotas = [c for c in j["camadas"] if c["servidor"] == d["servidor"]]
    assert len(camadas_remotas) == 3, camadas_remotas
    for c in camadas_remotas:
        assert c["modo_acesso"] == "fdw"
        assert c["origem"] == f"servidor remoto ({d['servidor']})", c
        assert "servidor remoto" in c["origem"]
    print(f"ficha de {d['fonte_id']}: {len(camadas_remotas)} camada(s) mostrando "
          f"'{camadas_remotas[0]['origem']}'")


def test_falha_de_rede_vira_aviso_nao_camada_vazia(fdw_fixture, medida):
    """Cláusula 3 (é também a refutação do item): o adversário derruba a rede do servidor de teste
    (porta que ninguém escuta) e confere que a camada NÃO vira '0 feições' — ela conserva
    `linhas_exatas` da última leitura boa, muda para `modo_acesso = 'indisponivel'` e ganha um
    `aviso` explicando."""
    grava = medida("L6-01-j-multi-servidor")
    d = fdw_fixture
    schema_plat = d["schema_plat"]

    # 1) roda com a rede boa e confere que a contagem real fica registrada
    r = _rodar_fdw_sync(schema_plat, d["segredos"], servidor=d["servidor"])
    assert r.returncode == 0, r.stderr
    plat_dsn = os.environ["PLAT_DSN"]
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(plat_dsn, cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT tabela, linhas_exatas FROM plat.acervo_camada WHERE servidor = %s ORDER BY tabela",
                (d["servidor"],),
            )
            antes = {row["tabela"]: row["linhas_exatas"] for row in cur.fetchall()}
    finally:
        con.close()
    assert all(v is not None and v > 0 for v in antes.values()), antes

    # 2) "derruba a rede": aponta o servidor declarado para uma porta que ninguém escuta (conexão
    # recusada imediatamente — não precisa esperar o connect_timeout de 10 s)
    _psql(
        f"UPDATE {schema_plat}.acervo_servidor SET porta = 1 WHERE servidor = '{d['servidor']}'"
    )
    r2 = _rodar_fdw_sync(schema_plat, d["segredos"], servidor=d["servidor"])
    assert r2.returncode == 0, r2.stderr
    print(f"rodada com rede derrubada: {r2.stdout.strip()}")

    con = psycopg2.connect(plat_dsn, cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT tabela, modo_acesso, linhas_exatas, aviso FROM plat.acervo_camada "
                "WHERE servidor = %s ORDER BY tabela",
                (d["servidor"],),
            )
            depois = cur.fetchall()
    finally:
        con.close()

    assert len(depois) == 3, depois
    for row in depois:
        assert row["modo_acesso"] == "indisponivel", row
        assert row["aviso"], f"{row['tabela']}: falha de rede sem aviso"
        assert "servidor remoto" in row["aviso"] or d["servidor"] in row["aviso"], row
        # a cláusula do portão: NUNCA vira '0 feições' — a última contagem boa continua lá
        assert row["linhas_exatas"] == antes[row["tabela"]], (
            f"{row['tabela']}: linhas_exatas mudou de {antes[row['tabela']]} para "
            f"{row['linhas_exatas']} numa falha de rede (deveria conservar a última contagem boa)"
        )
        assert row["linhas_exatas"] != 0
        print(f"  {row['tabela']}: modo_acesso=indisponivel linhas_exatas={row['linhas_exatas']} "
              f"(preservado) aviso={row['aviso'][:80]!r}")

    grava("camadas_preservadas_apos_queda_de_rede", len(depois), "camadas",
          "test_falha_de_rede_vira_aviso_nao_camada_vazia")
    grava("linhas_exatas_zeradas_por_falha_de_rede", 0, "camadas",
          "test_falha_de_rede_vira_aviso_nao_camada_vazia")

    # 3) restaura a porta boa para não vazar estado quebrado para os outros testes deste módulo
    _psql(f"UPDATE {schema_plat}.acervo_servidor SET porta = 5432 WHERE servidor = '{d['servidor']}'")
    r3 = _rodar_fdw_sync(schema_plat, d["segredos"], servidor=d["servidor"])
    assert r3.returncode == 0, r3.stderr


# -------------------------------------------------------------------------------------------------
# Furo 3 do turno de segurança (17/09/2026) — achado `L0-04-i` no caminho do ACERVO REMOTO.
#
# A migração `20260916T0643_fdw_papel_por_inquilino.sql` fechou o caminho da conexão publicada por
# inquilino, mas `scripts/acervo_fdw_sync.py` continuava criando `USER MAPPING FOR <schema>_app` com a
# senha do Postgres remoto nas OPTIONS. `pg_user_mappings.umoptions` só fica escondido de quem não é
# dono do mapeamento nem superusuário, e `<schema>_app` é o papel de LOGIN compartilhado por todos os
# inquilinos (ADR 0001) — a senha ficava legível, em claro e para sempre, por qualquer sessão de
# qualquer inquilino.
#
# CONSERTO: o mapeamento passa a pertencer ao papel-contêiner NOLOGIN `<schema>_fdw_acervo`, do qual
# `<schema>_app` nunca é membro; as foreign tables vivem no schema privado `<espelho>_ft` com esse dono
# e a aplicação lê VISTAS de mesmo nome em `<espelho>`, também do papel-contêiner (vista sem
# `security_invoker` executa com os direitos do dono, e é o dono que o postgres_fdw usa para escolher o
# USER MAPPING).
#
# Par de provas: o ATAQUE (ler a senha pelo catálogo, como a aplicação) e o CONTROLE POSITIVO (a
# mesma sessão continua contando as linhas da tabela remota pela vista).
def test_ataque_senha_do_fdw_nao_e_legivel_pela_aplicacao_no_catalogo(fdw_fixture, env):
    """ATAQUE: `SELECT umoptions FROM pg_user_mappings` numa sessão `<schema>_app` — a mesma que
    qualquer inquilino tem. Nenhuma opção de nenhum mapeamento pode voltar preenchida."""
    d = fdw_fixture
    r = _rodar_fdw_sync(d["schema_plat"], d["segredos"], servidor=d["servidor"])
    assert r.returncode == 0, r.stderr

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT current_user AS u")
            papel_de_login = cur.fetchone()["u"]
            cur.execute(
                "SELECT srvname, usename, umoptions FROM pg_user_mappings "
                "WHERE srvname LIKE 'fdw\\_%' AND umoptions IS NOT NULL"
            )
            visiveis = cur.fetchall()
    finally:
        con.close()
    assert papel_de_login.endswith("_app"), papel_de_login
    # nunca imprime o valor: só o nome do servidor e do papel dono do mapeamento
    assert visiveis == [], (
        "a sessão da aplicação enxerga as OPTIONS (senha em claro) destes mapeamentos: "
        + str([(v["srvname"], v["usename"]) for v in visiveis])
    )


def test_legitimo_aplicacao_continua_lendo_a_camada_remota_pela_vista(fdw_fixture, env):
    """CONTROLE POSITIVO: sem mapeamento próprio, a sessão da aplicação ainda lê a tabela remota — pela
    vista do papel-contêiner — e a contagem bate com o que a tabela remota tem de verdade."""
    d = fdw_fixture
    r = _rodar_fdw_sync(d["schema_plat"], d["segredos"], servidor=d["servidor"])
    assert r.returncode == 0, r.stderr

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT tabela, fdw_tabela FROM plat.acervo_camada WHERE servidor = %s ORDER BY tabela",
                (d["servidor"],),
            )
            linhas = cur.fetchall()
            assert len(linhas) == 3, linhas
            for linha in linhas:
                esperado = d["linhas_por_tabela"][linha["tabela"]]
                schema, _, tabela = linha["fdw_tabela"].partition(".")
                cur.execute(
                    psycopg2.sql.SQL("SELECT count(*) AS n FROM {}.{}").format(
                        psycopg2.sql.Identifier(schema), psycopg2.sql.Identifier(tabela)
                    )
                )
                assert cur.fetchone()["n"] == esperado, linha
                print(f"  {linha['tabela']}: {esperado} linhas lidas por {linha['fdw_tabela']} como app")
    finally:
        con.close()
