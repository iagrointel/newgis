"""Adversário do item L2-04-a-leitor-rls-martin (papel de leitura, contexto por token, prova de inquilino).

Este arquivo NÃO é do construtor: é a bateria de refutação de uma sessão adversária independente. Ataca a
mesma superfície do `test_leitor_tiles.py`, mas do ponto de vista de quem TEM a credencial do papel de leitura
(o mesmo papel que o Martin usa, conecta de fora, é compartilhado por todos os inquilinos) e quer ler a camada
de outro inquilino. Reusa as fixtures do arquivo do construtor (`leitor`, `camadas`, `instalador`).

Convenção: cada teste afirma que o ATAQUE FALHA (a defesa segura). Se um destes passar a falhar, a RLS do
papel de leitura foi furada. As demonstrações que exigem o segredo cru ou o papel global `plat_leitor`
(amarração da prova à conexão pelo pid; vazamento residual de camada só-`camada_preparar`; leitura do segredo
por `plat_app`) estão no laudo `laco/handoffs/T3/L2-04-a-leitor-rls-martin-ADVERSARIO.md` com comando e saída,
porque precisam de conexão de superusuário e de um segundo papel, fora do alcance da fixture `leitor`.
"""

import json
import secrets

import psycopg2
import pytest

from tests.api.test_leitor_tiles import (  # noqa: F401  (fixtures usadas por injeção)
    _admin,
    _schema,
    _tile,
    camadas,
    instalador,
    leitor,
)
from tests.api.test_rls import contexto


def _conta(cur, c):
    cur.execute(f'SELECT count(*) AS n FROM "{c["esquema"]}"."{c["tabela"]}"')
    return cur.fetchone()["n"]


def test_leitor_nao_le_o_segredo_da_prova(env, leitor, camadas):
    """Sem o segredo não há como forjar a prova. O papel de leitura não pode SELECIONAR `segredo_leitor`."""
    s = _schema(env)
    with leitor.cursor() as cur, pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute(f"SELECT valor FROM {s}.segredo_leitor")
    leitor.rollback()


def test_leitor_nao_executa_prova_leitor(env, leitor, camadas):
    """A função que devolveria a prova de qualquer inquilino é negada ao papel de leitura."""
    s = _schema(env)
    with leitor.cursor() as cur, pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute(f"SELECT {s}.prova_leitor(1)")
    leitor.rollback()


def test_guc_crua_sem_prova_nao_le_nada(env, leitor, camadas):
    """`SET plat.tenant_id`/`plat.prova` com valores forjados não abre a camada: a política do leitor exige a
    prova, e a prova errada não bate."""
    b = camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.prova', repeat('de',32), true)",
                    (str(b["tenant_id"]),))
        assert _conta(cur, b) == 0
    leitor.rollback()


def test_token_de_a_nao_le_camada_de_b(env, leitor, camadas):
    """Com um token legítimo de A: lê A (3), não lê B (0), na MESMA transação. É o contrato central do item,
    reafirmado pelo adversário porque é o que mais importa."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid) AS t", (a["token"], a["item"]))
        assert cur.fetchone()["t"] == a["tenant_id"]
        assert _conta(cur, a) == 3
        assert _conta(cur, b) == 0
    leitor.rollback()


def test_override_do_tenant_id_apos_o_contexto_nao_le_b(env, leitor, camadas):
    """Depois de `contexto_por_token` de A, sobrescrever só `plat.tenant_id` para B não lê B: a `plat.prova`
    posta continua a de A e `tenant_leitor()` recomputa a prova de B (que não bate)."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
        cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(b["tenant_id"]),))
        assert _conta(cur, b) == 0
    leitor.rollback()


def test_prova_de_a_reusada_como_prova_de_b_nao_le_b(env, leitor, camadas):
    """A `plat.prova` de A é legível na sessão (`current_setting`) mas embute o inquilino: reusá-la como prova
    de B não abre B."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (a["token"], a["item"]))
        cur.execute("SELECT current_setting('plat.prova', true) AS p")
        prova_a = cur.fetchone()["p"]
        assert prova_a  # a prova de A existe na sessão
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.prova', %s, true)",
                    (str(b["tenant_id"]), prova_a))
        assert _conta(cur, b) == 0
    leitor.rollback()


def test_token_amplo_de_a_nao_alcanca_b(env, leitor, camadas):
    """Escopo não é inquilino: o token AMPLO de A (escopo `camada:ler` sem pin de item, criado pela fixture do
    construtor) passa a validação de escopo, mas não muda o inquilino do contexto. Na função de tile de B
    levanta `tile_de_outro_inquilino`; na leitura direta de B, o contexto continua o inquilino de A e B dá 0."""
    a, b = camadas["demo"], camadas["demo2"]
    with leitor.cursor() as cur, pytest.raises(psycopg2.Error) as e:
        cur.execute(f'SELECT "{b["esquema"]}"."{b["funcao"]}"(0,0,0,%s::json)',
                    (json.dumps({"token": a["token_amplo"]}),))
    assert "tile_de_outro_inquilino" in str(e.value)
    leitor.rollback()
    with leitor.cursor() as cur:
        # escopo padrão 'camada:ler' sem item: é o que o token amplo cobre. O inquilino resolvido é o de A.
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL) AS t", (a["token_amplo"],))
        assert cur.fetchone()["t"] == a["tenant_id"]
        assert _conta(cur, b) == 0
    leitor.rollback()


def test_plat_app_nao_le_o_segredo_nem_forja_a_prova(conexao_plat_app):
    """Conserto do achado F1: `plat_app` herdava SELECT/EXECUTE de `001_fundacao.sql` (GRANT ... ON ALL
    TABLES + DEFAULT PRIVILEGES) e conseguia ler `segredo_leitor` e chamar `prova_leitor` de qualquer
    inquilino — o texto do item promete que só função SECURITY DEFINER lê o segredo. A migração
    `20260906T1818_leitor_seguranca_padrao` revoga os dois de `plat_app` explicitamente."""
    con = conexao_plat_app
    with con.cursor() as cur, pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("SELECT valor FROM plat.segredo_leitor")
    con.rollback()
    with con.cursor() as cur, pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("SELECT plat.prova_leitor(1)")
    con.rollback()


def test_camada_preparar_sozinho_nao_habilita_o_leitor(leitor, conexao_plat_app):
    """Conserto do achado F3: uma camada que passa só por `camada_preparar` (029), sem `camada_tile_garantir`,
    não pode ficar legível pelo papel de leitura. Antes do conserto a 029 concedia SELECT a `plat_leitor` e o
    incluía na política ALL — um `SET plat.tenant_id` cru, sem token e sem prova, bastava para ler. Agora
    `camada_preparar` não concede nada ao leitor: a tentativa falha FECHADA (permissão negada), não aberta."""
    con = conexao_plat_app
    with con.cursor() as cur:
        adm = _admin(con, "demo2")
    contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
    esquema, tabela = "d_demo2", "c_" + secrets.token_hex(8)
    try:
        with con.cursor() as cur:
            cur.execute(f'CREATE TABLE "{esquema}"."{tabela}" '
                        f'(fid bigserial PRIMARY KEY, nome text, geom geometry(Point, 4326))')
            cur.execute(f'INSERT INTO "{esquema}"."{tabela}" (nome, geom) VALUES '
                        f"('sozinha', ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326))")
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)",
                        (esquema, tabela, adm["usuario_id"]))
        con.commit()

        with leitor.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(adm["tenant_id"]),))
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f'SELECT count(*) FROM "{esquema}"."{tabela}"')
        leitor.rollback()
    finally:
        with con.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{esquema}"."{tabela}"')
        con.commit()
