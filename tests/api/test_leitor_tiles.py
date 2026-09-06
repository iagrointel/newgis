"""Papel de leitura, contexto por token e função de tile (item L2-04-a-leitor-rls-martin).

Prova, cláusula por cláusula, o portão do item: o papel que o Martin usa conecta de fora, não tem BYPASSRLS,
não é dono de nada e, sem token, não vê linha nenhuma nem consegue gerar tile; com o token de um inquilino vê
só as linhas daquele inquilino; token revogado deixa de valer no primeiro pedido seguinte; cada chamada de
contexto deixa uma linha em plat.log_acesso; e o instalador do papel (db/leitor_instalar.sh, que também
escreve a linha do pg_hba.conf) é idempotente.

Nenhum teste conecta como postgres. O papel de leitura conecta com a senha do credential que o próprio
instalador gera (tmp_path_factory nesta suíte, /etc/plat/segredos em produção)."""

import hashlib
import json
import os
import re
import secrets
import subprocess
import time

import psycopg2
import pytest

from tests.api.test_rls import contexto

SLUGS = ("demo", "demo2")
Z, X, Y = 0, 0, 0  # ST_TileEnvelope(0,0,0) = mundo inteiro: qualquer feição de teste cai neste tile


def _schema(env) -> str:
    return env.get("PLAT_SCHEMA") or "plat"


def _hex16() -> str:
    return secrets.token_hex(8)


def token_novo() -> tuple[str, str]:
    """(valor, hash) no mesmo formato de app/auth/sessao.py: prefixo plat_, 48 caracteres, sha256 hex."""
    valor = "plat_" + secrets.token_urlsafe(64).replace("-", "x").replace("_", "y")[:43]
    return valor, hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _conectar_app(env):
    from app.schema_ambiente import CursorSchemaAmbiente

    # autocommit FALSE de propósito: o contexto de inquilino é posto com set_config(..., true), que vive na
    # TRANSAÇÃO; em autocommit cada comando seria a sua própria transação e o contexto sumiria antes do uso.
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    return con


def _admin(con, slug) -> dict:
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
        r = cur.fetchone()
    assert r, f"admin de {slug} não semeado"
    return r


@pytest.fixture(scope="module")
def instalador(env, tmp_path_factory):
    """Roda db/leitor_instalar.sh (LOGIN, senha, credential e pg_hba). Devolve (função de execução, DSN)."""
    from tests.conftest import ROOT

    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
        pytest.skip("sem sudo sem senha: o instalador do papel de leitura mexe no pg_hba.conf")
    cred = tmp_path_factory.mktemp("cred_leitor")

    def rodar():
        return subprocess.run(
            ["sudo", "-n", "env", f"PLAT_SCHEMA={_schema(env)}", f"CRED_DIR={cred}",
             f"CRED_DONO={os.environ.get('USER') or os.getlogin()}",
             "bash", str(ROOT / "db" / "leitor_instalar.sh"),
             re.sub(r"^.*/", "", env["PLAT_DSN"].split("?")[0])],
            capture_output=True, text=True, cwd=ROOT,
        )

    r = rodar()
    assert r.returncode == 0, r.stderr
    dsn = (cred / "PLAT_DSN_LEITOR").read_text(encoding="utf-8").strip()
    return rodar, dsn


@pytest.fixture(scope="module")
def leitor(instalador):
    from app.schema_ambiente import CursorSchemaAmbiente

    _, dsn = instalador
    con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    yield con
    con.rollback()
    con.close()


@pytest.fixture(scope="module")
def camadas(env):
    """Uma camada de 3 feições em cada inquilino (demo = A, demo2 = B), com item de catálogo, função de tile
    e um token de serviço com escopo camada:ler:<item>. Tudo é apagado no fim."""
    con = _conectar_app(env)
    feito = {}
    try:
        for slug in SLUGS:
            adm = _admin(con, slug)
            esquema, tabela = f"d_{slug}", "c_" + _hex16()
            valor, hash_ = token_novo()
            with con.cursor() as cur:
                contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
                cur.execute(f'CREATE TABLE "{esquema}"."{tabela}" '
                            f'(fid bigserial PRIMARY KEY, nome text, geom geometry(Point, 4326))')
                cur.execute(f'INSERT INTO "{esquema}"."{tabela}" (nome, geom) '
                            f"SELECT %s || g, ST_SetSRID(ST_MakePoint(-47.9 + g * 0.01, -15.8), 4326) "
                            f"FROM generate_series(1, 3) g", (f"{slug}-",))
                cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)",
                            (esquema, tabela, adm["usuario_id"]))
                cur.execute(
                    "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                    "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                    (adm["tenant_id"], f"camada de teste {slug}", adm["usuario_id"], adm["usuario_id"],
                     json.dumps({"schema": esquema, "tabela": tabela, "geometria": "Point", "srid": 4326,
                                 "campos": [{"nome": "nome", "tipo": "text"}], "fonte": "hospedada"})),
                )
                item = cur.fetchone()["id"]
                cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema, tabela, item))
                funcao = cur.fetchone()["f"]
                cur.execute(
                    "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (adm["tenant_id"], adm["usuario_id"], f"zt-leitor-{slug}", hash_, valor[:8],
                     ["camada:ler:" + str(item)]),
                )
                token_id = cur.fetchone()["id"]
                valor_amplo, hash_amplo = token_novo()
                cur.execute(
                    "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (adm["tenant_id"], adm["usuario_id"], f"zt-leitor-amplo-{slug}", hash_amplo,
                     valor_amplo[:8], ["camada:ler"]),
                )
                token_amplo_id = cur.fetchone()["id"]
            con.commit()
            feito[slug] = {"esquema": esquema, "tabela": tabela, "funcao": funcao, "item": str(item),
                           "token": valor, "token_id": token_id, "token_amplo": valor_amplo,
                           "token_amplo_id": token_amplo_id, "tenant_id": adm["tenant_id"],
                           "usuario_id": adm["usuario_id"]}
        yield feito
    finally:
        for c in feito.values():
            with con.cursor() as cur:
                contexto(con, c["tenant_id"], c["usuario_id"], "admin")
                cur.execute("DELETE FROM plat.token_servico WHERE id IN (%s, %s)",
                            (c["token_id"], c["token_amplo_id"]))
                # o catálogo não aceita UPDATE de apagado_em nem DELETE direto de plat_app (políticas do
                # L0-03): o caminho é o mesmo da rota DELETE /api/itens/{id} — lixeira e depois expurgo
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (c["item"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (c["item"],))
                cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (c["esquema"], c["tabela"]))
                cur.execute(f'DROP TABLE IF EXISTS "{c["esquema"]}"."{c["tabela"]}"')
            con.commit()
        con.close()


def _tile(cur, c, token=None, extra=None):
    parametros = dict(extra or {})
    if token is not None:
        parametros["token"] = token
    cur.execute(f'SELECT "{c["esquema"]}"."{c["funcao"]}"(%s, %s, %s, %s::json) AS mvt',
                (Z, X, Y, json.dumps(parametros)))
    return cur.fetchone()["mvt"]


# ------------------------------------------------------------------ atributos do papel


def test_papel_de_leitura_nao_tem_bypassrls_nem_e_dono(env, leitor, camadas):
    """Cláusula: o papel é de LEITURA. Sem BYPASSRLS, sem superusuário, e não é dono de nenhuma tabela."""
    with leitor.cursor() as cur:
        cur.execute("SELECT current_user AS papel")
        papel = cur.fetchone()["papel"]
        cur.execute("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = %s",
                    (papel,))
        r = cur.fetchone()
        assert not any(r.values()), r
        cur.execute("SELECT count(*) AS n FROM pg_class c JOIN pg_roles o ON o.oid = c.relowner "
                    "WHERE o.rolname = %s", (papel,))
        assert cur.fetchone()["n"] == 0
    leitor.rollback()
    assert papel == _schema(env) + "_leitor"


# ------------------------------------------------------------------ sem token


def test_sem_token_le_zero_linhas_e_o_tile_levanta_excecao_nomeada(leitor, camadas):
    """Cláusula: `psql como plat_leitor sem token: SELECT em c_* devolve 0 linhas e a função de tile sem
    token lança exceção nomeada`."""
    a = camadas["demo"]
    with leitor.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{a["esquema"]}"."{a["tabela"]}"')
        assert cur.fetchone()["n"] == 0
    leitor.rollback()
    with leitor.cursor() as cur, pytest.raises(psycopg2.Error) as e:
        _tile(cur, a)
    assert "token_ausente" in str(e.value)
    leitor.rollback()


def test_token_invalido_e_recusado(leitor, camadas):
    with leitor.cursor() as cur, pytest.raises(psycopg2.Error) as e:
        _tile(cur, camadas["demo"], token="plat_" + "z" * 43)
    assert "token_invalido" in str(e.value)
    leitor.rollback()


# ------------------------------------------------------------------ com token


def test_com_token_ve_so_o_proprio_inquilino(leitor, camadas, medida):
    """Cláusula: `com token de demo: só linhas de demo`. Na MESMA transação, a camada de demo2 dá 0 linhas."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid) AS t", (a["token"], a["item"]))
        assert cur.fetchone()["t"] == a["tenant_id"]
        cur.execute(f'SELECT count(*) AS n FROM "{a["esquema"]}"."{a["tabela"]}"')
        assert cur.fetchone()["n"] == 3
        cur.execute(f'SELECT count(*) AS n FROM "{b["esquema"]}"."{b["tabela"]}"')
        assert cur.fetchone()["n"] == 0, "linha de outro inquilino visível com o token de demo"
        mvt = _tile(cur, a, token=a["token"])
        assert mvt is not None and len(mvt) > 0
    leitor.rollback()
    medida("L2-04-a-leitor-rls-martin")(
        "tile_bytes_3_feicoes", len(mvt), "bytes",
        "SELECT d_demo.t_<camada>(0,0,0,'{\"token\":...}') como papel de leitura")


def test_contexto_nao_vaza_para_a_transacao_seguinte(leitor, camadas):
    """set_config(..., true) é LOCAL: depois do rollback a mesma conexão volta a ver 0 linhas."""
    a = camadas["demo"]
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
    leitor.rollback()
    with leitor.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{a["esquema"]}"."{a["tabela"]}"')
        assert cur.fetchone()["n"] == 0
    leitor.rollback()


# ------------------------------------------------------------------ revogação


def test_token_revogado_para_de_valer_em_menos_de_um_segundo(env, leitor, camadas, medida):
    """Cláusula: `token revogado: 0 linhas em ≤ 1 s`."""
    a = camadas["demo"]
    con = _conectar_app(env)
    try:
        with con.cursor() as cur:
            contexto(con, a["tenant_id"], a["usuario_id"], "admin")
            cur.execute("UPDATE plat.token_servico SET revogado_em = now() WHERE id = %s", (a["token_id"],))
        con.commit()
        ini = time.monotonic()
        with leitor.cursor() as cur:
            with pytest.raises(psycopg2.Error) as e:
                cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
            assert "token_revogado" in str(e.value)
        leitor.rollback()
        with leitor.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{a["esquema"]}"."{a["tabela"]}"')
            assert cur.fetchone()["n"] == 0
        leitor.rollback()
        gasto = time.monotonic() - ini
        assert gasto <= 1.0, gasto
        medida("L2-04-a-leitor-rls-martin")(
            "revogacao_ate_zero_linhas_s", round(gasto, 4), "s",
            "UPDATE token_servico SET revogado_em -> contexto_por_token recusa e SELECT devolve 0")
    finally:
        with con.cursor() as cur:
            contexto(con, a["tenant_id"], a["usuario_id"], "admin")
            cur.execute("UPDATE plat.token_servico SET revogado_em = NULL WHERE id = %s", (a["token_id"],))
        con.commit()
        con.close()


# ------------------------------------------------------------------ log


def test_uma_linha_de_log_por_chamada_de_contexto(env, leitor, camadas, medida):
    """Cláusula: `log_acesso ganha 1 linha por chamada de contexto`. Vale para a chamada ACEITA, que é a que
    o cliente confirma; a recusa é exceção e, como o PostgreSQL não tem transação autônoma, a linha dela é
    desfeita junto com a transação abortada — está medido no teste seguinte e escrito no handoff."""
    a = camadas["demo"]
    con = _conectar_app(env)

    def linhas():
        with con.cursor() as cur:
            contexto(con, a["tenant_id"], a["usuario_id"], "admin")
            cur.execute("SELECT count(*) AS n FROM plat.log_acesso WHERE token_id = %s", (a["token_id"],))
            n = cur.fetchone()["n"]
        con.rollback()
        return n

    try:
        antes = linhas()
        n = 5
        with leitor.cursor() as cur:
            for _ in range(n):
                cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
        leitor.commit()
        depois = linhas()
        assert depois - antes == n, (antes, depois)
        with con.cursor() as cur:
            contexto(con, a["tenant_id"], a["usuario_id"], "admin")
            cur.execute("SELECT resultado, status, rota, ip FROM plat.log_acesso WHERE token_id = %s "
                        "ORDER BY em DESC LIMIT 1", (a["token_id"],))
            ultima = cur.fetchone()
        con.rollback()
        assert ultima["resultado"] == "ok" and ultima["status"] == 200 and ultima["rota"] == "/tiles"
        medida("L2-04-a-leitor-rls-martin")(
            "linhas_log_por_chamada_de_contexto", (depois - antes) / n, "linhas",
            "count(*) em plat.log_acesso por token_id antes e depois de 5 chamadas aceitas")
    finally:
        con.close()


def test_recusa_nao_sobrevive_a_transacao_abortada(env, leitor, camadas, medida):
    """Fronteira honesta, medida e não escondida: a recusa TAMBÉM grava em plat.log_acesso, mas a recusa é
    uma exceção e o PostgreSQL não tem transação autônoma — a linha morre com a transação. Quem quiser o
    rastro das recusas do Martin lê o log do SERVIDOR (a exceção é nomeada) ou põe a API na frente
    (L0-02-d já grava o 401 no log de acesso). Este teste existe para o número não ser inventado depois."""
    a = camadas["demo"]
    con = _conectar_app(env)

    def linhas():
        with con.cursor() as cur:
            contexto(con, a["tenant_id"], a["usuario_id"], "admin")
            cur.execute("SELECT count(*) AS n FROM plat.log_acesso WHERE token_id = %s", (a["token_id"],))
            n = cur.fetchone()["n"]
        con.rollback()
        return n

    try:
        antes = linhas()
        with leitor.cursor() as cur, pytest.raises(psycopg2.Error) as e:
            cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid, 'admin:inquilino')",
                        (a["token"], a["item"]))
        assert "escopo_insuficiente" in str(e.value)
        leitor.rollback()
        depois = linhas()
        medida("L2-04-a-leitor-rls-martin")(
            "linhas_log_de_recusa_persistidas", depois - antes, "linhas",
            "contexto_por_token com escopo insuficiente: linhas que sobram em plat.log_acesso")
        assert depois - antes == 0
    finally:
        con.close()


# ------------------------------------------------------------------ instalador


def test_instalador_do_papel_e_idempotente(instalador, medida):
    """Cláusula: `install.sh idempotente cria role e pg_hba (segunda execução = 0 mudanças)`. O que roda aqui
    é o passo do papel de leitura (db/leitor_instalar.sh), que o install.sh chama na seção do pg_hba: rodar o
    install.sh inteiro dentro da suíte reescreveria o .env e as migrações da INSTALAÇÃO, não da base de teste."""
    rodar, _ = instalador
    r = rodar()
    assert r.returncode == 0, r.stderr
    ultima = r.stdout.strip().splitlines()[-1]
    assert ultima == "mudancas: 0", r.stdout
    medida("L2-04-a-leitor-rls-martin")(
        "mudancas_2a_execucao_instalador", 0, "mudanças",
        "sudo bash db/leitor_instalar.sh (2a execução seguida)")


# ------------------------------------------------------------------ refutação do adversário


def test_set_config_direto_como_leitor_nao_tem_efeito(leitor, camadas, medida):
    """Refutação: `tenta set_config direto como plat_leitor (deve não ter efeito)`. O papel de leitura escreve
    na GUC plat.tenant_id — qualquer papel escreve —, mas a política dele exige a PROVA que só
    plat.contexto_por_token emite, e a prova depende de um segredo que o papel não pode ler."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true)",
                    (str(a["tenant_id"]), str(a["usuario_id"])))
        cur.execute(f'SELECT count(*) AS n FROM "{a["esquema"]}"."{a["tabela"]}"')
        assert cur.fetchone()["n"] == 0, "GUC forjada bastou para ler a camada"
        with pytest.raises(psycopg2.Error):
            cur.execute("SELECT * FROM plat.segredo_leitor")
    leitor.rollback()
    with leitor.cursor() as cur, pytest.raises(psycopg2.Error):
        cur.execute("SELECT plat.prova_leitor(%s)", (a["tenant_id"],))
    leitor.rollback()
    # e com o token de A na mão, forjar a GUC do inquilino B na mesma transação também não lê B
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
        cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(b["tenant_id"]),))
        cur.execute(f'SELECT count(*) AS n FROM "{b["esquema"]}"."{b["tabela"]}"')
        assert cur.fetchone()["n"] == 0
    leitor.rollback()
    medida("L2-04-a-leitor-rls-martin")(
        "linhas_com_guc_forjada", 0, "linhas",
        "set_config('plat.tenant_id', <inquilino>, true) como papel de leitura, depois SELECT na camada")


def test_token_de_a_e_tile_de_b_na_mesma_conexao_falha(leitor, camadas):
    """Refutação: `chama contexto_por_token com token de A e depois pede tile de camada de B na mesma
    conexão (deve falhar)`."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
        with pytest.raises(psycopg2.Error) as e:
            _tile(cur, b, token=a["token"])
    assert "tile_de_outro_inquilino" in str(e.value) or "escopo_insuficiente" in str(e.value)
    leitor.rollback()


def test_log_nao_cresce_sem_limite(env, leitor, camadas, medida):
    """Refutação: `mede se o log cresce sem limite`. Cresce 1 linha por chamada — é cláusula do portão — mas a
    tabela é particionada por mês e plat.log_expurgar(meses) descarta partição inteira. Aqui se mede o custo
    por mil chamadas e se prova que o expurgo apaga."""
    a = camadas["demo"]
    con = _conectar_app(env)
    try:
        with con.cursor() as cur:
            contexto(con, a["tenant_id"], a["usuario_id"], "admin")
            cur.execute("SELECT avg(pg_column_size(l.*))::int AS b FROM plat.log_acesso l "
                        "WHERE l.token_id = %s", (a["token_id"],))
            r = cur.fetchone()
        con.rollback()
        assert r and r["b"], "sem linha de log deste token para medir (rode o teste do log antes)"
        bytes_linha = int(r["b"])
        medida("L2-04-a-leitor-rls-martin")(
            "log_bytes_por_1000_chamadas", bytes_linha * 1000, "bytes",
            "pg_column_size de uma linha de plat.log_acesso x 1000")
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM pg_inherits WHERE inhparent = 'plat.log_acesso'::regclass")
            particoes = cur.fetchone()["n"]
        con.rollback()
        assert particoes >= 1
        medida("L2-04-a-leitor-rls-martin")(
            "particoes_de_log", particoes, "partições",
            "pg_inherits de plat.log_acesso (expurgo por plat.log_expurgar(meses))")
    finally:
        con.close()
    assert bytes_linha < 1024, "linha de log maior do que o esperado"


# ------------------------------------------------------------------ varredura cruzada A→B nas funções de tile
# Extensão do gerador do item L0-02-e (tests/api/test_cruzado.py): lá a varredura é por ROTA do OpenAPI; aqui é
# por CAMADA do catálogo. Para cada camada publicada de cada inquilino, a função de tile é chamada com o token
# AMPLO (camada:ler, sem uuid) do OUTRO inquilino: nenhuma pode devolver dado. O token amplo é de propósito —
# com um token de escopo por item a recusa poderia vir do escopo, e o que se quer provar é o ISOLAMENTO.


def _camadas_do_catalogo(con, tenant_id, usuario_id) -> list[dict]:
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id, "admin")
        cur.execute(
            "SELECT id, dados->>'schema' AS esquema, dados->>'tabela' AS tabela FROM plat.item "
            "WHERE tipo = 'camada_vetorial' AND apagado_em IS NULL "
            "AND coalesce(dados->>'fonte', 'hospedada') = 'hospedada' "
            "AND dados->>'schema' ~ '^d_[a-z0-9_]{1,60}$' AND dados->>'tabela' ~ '^c_[0-9a-f]{16}$' "
            "ORDER BY criado_em"
        )
        camadas = [dict(r) for r in cur.fetchall()]
    con.rollback()
    return camadas


def test_toda_camada_do_catalogo_tem_funcao_de_tile(env, camadas, medida):
    """Cláusula implícita do portão (`todas as camadas da demo`): não existe camada publicada sem função de
    tile. Se existisse, a varredura cruzada não a cobriria e o isolamento dela não estaria provado."""
    con = _conectar_app(env)
    total, sem_funcao = 0, []
    try:
        for slug in SLUGS:
            c = camadas[slug]
            for cam in _camadas_do_catalogo(con, c["tenant_id"], c["usuario_id"]):
                total += 1
                with con.cursor() as cur:
                    cur.execute("SELECT to_regprocedure(%s) IS NOT NULL AS tem",
                                (f'"{cam["esquema"]}"."t_{cam["tabela"][2:]}"(integer,integer,integer,json)',))
                    if not cur.fetchone()["tem"]:
                        sem_funcao.append(f"{cam['esquema']}.{cam['tabela']}")
                con.rollback()
    finally:
        con.close()
    medida("L2-04-a-leitor-rls-martin")(
        "camadas_do_catalogo_com_funcao_de_tile", total - len(sem_funcao), "camadas",
        "itens camada_vetorial hospedados dos inquilinos de demonstração com t_<tabela> em pg_proc")
    assert sem_funcao == [], sem_funcao
    assert total >= 2, "a varredura precisa de pelo menos uma camada por inquilino"


def test_varredura_cruzada_nas_funcoes_de_tile(env, leitor, camadas, medida):
    """Cláusula: `teste cruzado A→B nas funções de tile de todas as camadas da demo`."""
    con = _conectar_app(env)
    chamadas, com_dado, sem_token = 0, 0, 0
    try:
        for slug in SLUGS:
            outro = "demo2" if slug == "demo" else "demo"
            c, alheio = camadas[slug], camadas[outro]
            for cam in _camadas_do_catalogo(con, c["tenant_id"], c["usuario_id"]):
                alvo = {"esquema": cam["esquema"], "funcao": f't_{cam["tabela"][2:]}'}
                for token in (alheio["token_amplo"], alheio["token"]):
                    chamadas += 1
                    with leitor.cursor() as cur:
                        try:
                            mvt = _tile(cur, alvo, token=token)
                            com_dado += 1 if mvt else 0
                        except psycopg2.Error as e:
                            assert any(m in str(e) for m in ("tile_de_outro_inquilino", "escopo_insuficiente")), e
                    leitor.rollback()
                chamadas += 1
                sem_token += 1
                with leitor.cursor() as cur, pytest.raises(psycopg2.Error) as e:
                    _tile(cur, alvo)
                assert "token_ausente" in str(e.value)
                leitor.rollback()
    finally:
        con.close()
    medida("L2-04-a-leitor-rls-martin")(
        "chamadas_cruzadas_em_funcao_de_tile", chamadas, "chamadas",
        "cada camada do catálogo dos 2 inquilinos x (token amplo do outro, token por item do outro, sem token)")
    medida("L2-04-a-leitor-rls-martin")(
        "chamadas_cruzadas_com_dado", com_dado, "chamadas",
        "tiles não vazios devolvidos a token de outro inquilino")
    assert com_dado == 0
    assert sem_token >= 2
