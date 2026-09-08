"""Prova de COMPORTAMENTO do achado F9: rodando com PLAT_SCHEMA apontando para o schema de uma trilha,
cada um dos cinco módulos fala com AQUELE schema, não com o `plat` de produção.

Detector (mesmo do adversário, laco/handoffs/T4/ADVERSARIO-reescritor-schema.md): a role da trilha não
tem USAGE no schema `plat`. Logo, toda consulta que escapa da reescrita volta com
`permission denied for schema plat`. Nada é escrito em produção e o resultado não depende de
interpretação — ou a consulta chegou no schema da trilha, ou o Postgres recusou.

Só roda em trilha/homologação (PLAT_SCHEMA != 'plat').
"""

import importlib.util
import sys
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import SCHEMA_PADRAO

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def schema_da_trilha(env) -> str:
    s = env.get("PLAT_SCHEMA") or SCHEMA_PADRAO
    if s == SCHEMA_PADRAO:
        pytest.skip("prova de isolamento só roda em trilha/homologação (PLAT_SCHEMA != 'plat')")
    return s


def _modulo(caminho_relativo: str):
    caminho = RAIZ / caminho_relativo
    nome = "f9amb_" + caminho.stem
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


def _consulta_de_prova(con, schema: str):
    """Uma consulta com `plat.` escrito na mão, pelo cursor que o módulo entrega. Se escapar da
    reescrita, o Postgres recusa por privilégio; se for reescrita, responde do schema da trilha."""
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.privilegio")
            n = cur.fetchone()["n"]
            cur.execute("SELECT current_schemas(false) AS s")
        con.rollback()
    except psycopg2.errors.InsufficientPrivilege as e:
        pytest.fail(
            f"a consulta escapou do reescritor e bateu no schema de PRODUÇÃO: {e}. "
            f"Esperado: falar com {schema}."
        )
    finally:
        con.close()
    assert n > 0, "leu do schema da trilha, mas a tabela veio vazia"


def test_eventos_fala_com_o_schema_da_trilha(schema_da_trilha):
    from app.jobs import eventos

    _consulta_de_prova(eventos._conectar(), schema_da_trilha)


def test_acervo_sync_fala_com_o_schema_da_trilha(env, schema_da_trilha):
    mod = _modulo("scripts/acervo_sync.py")
    _consulta_de_prova(mod._conectar({"dsn": env["PLAT_DSN"]}), schema_da_trilha)


def test_acervo_licenca_sync_fala_com_o_schema_da_trilha(env, schema_da_trilha):
    mod = _modulo("scripts/acervo_licenca_sync.py")
    _consulta_de_prova(mod._conectar({"dsn": env["PLAT_DSN"]}), schema_da_trilha)


def test_geocodificador_fala_com_o_schema_da_trilha(env, schema_da_trilha, monkeypatch):
    mod = _modulo("scripts/geocodificador_instalar_uf.py")
    monkeypatch.setattr(mod, "_dsn", lambda: env["PLAT_DSN"])
    _consulta_de_prova(mod._conectar(), schema_da_trilha)


def test_geocodificador_carrega_endereco_no_schema_da_trilha(env, schema_da_trilha, monkeypatch):
    """O caminho de escrita real do geocodificador é um `COPY plat.geo_endereco ... FROM STDIN` em lotes
    de 20.000. COPY não passa pelo `execute` do cursor: sem a sobrescrita de `copy_expert` o lote inteiro
    ia para produção mesmo com a conexão certa. Aqui o lote é VAZIO — a prova é o schema alcançado, não
    linha gravada."""
    mod = _modulo("scripts/geocodificador_instalar_uf.py")
    monkeypatch.setattr(mod, "_dsn", lambda: env["PLAT_DSN"])
    con = mod._conectar()
    try:
        with con.cursor() as cur:
            mod._copiar_lote(cur, [])
        con.rollback()
    except psycopg2.errors.InsufficientPrivilege as e:
        pytest.fail(f"o COPY escapou do reescritor e apontou para o `plat` de produção: {e}")
    finally:
        con.close()


def test_gerar_privilegios_le_o_banco_da_trilha(env, schema_da_trilha, monkeypatch):
    mod = _modulo("docs/gerar_privilegios.py")
    monkeypatch.setattr(mod, "_dsn", lambda: env["PLAT_DSN"])
    try:
        privilegios, tetos = mod._ler_banco()
    except psycopg2.errors.InsufficientPrivilege as e:
        pytest.fail(f"`make privilegios` leu o `plat` de PRODUÇÃO em vez de {schema_da_trilha}: {e}")
    assert privilegios, "leu do schema da trilha, mas não veio privilégio nenhum"


def test_a_role_da_trilha_realmente_nao_alcanca_producao(env, schema_da_trilha):
    """Sem esta linha o detector acima não vale nada: se a role tivesse USAGE em `plat`, todos os testes
    passariam por acidente, escrevendo em produção."""
    con = psycopg2.connect(env["PLAT_DSN"])
    try:
        with con.cursor() as cur:
            cur.execute("SELECT has_schema_privilege(current_user, 'plat', 'USAGE') AS pode")
            pode = cur.fetchone()[0]
    finally:
        con.close()
    assert pode is False, "a role da trilha alcança o schema `plat` — o detector deste arquivo é cego"
