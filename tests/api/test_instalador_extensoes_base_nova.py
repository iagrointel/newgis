"""Portão do item L7-01-d contra banco de verdade: numa base que só tem PostGIS, a função de extensões
do instalador (db/extensoes.sh, a mesma que o install.sh chama na seção "b") termina com as quatro
extensões de db/extensoes.txt, e o dump do schema da plataforma restaura nessa base sem passo manual —
a tabela `item` nasce. A refutação está no mesmo arquivo: sem `unaccent`, a restauração perde a tabela
`item` e a conferência do instalador reprova nomeando a extensão.

Nunca roda o install.sh: ele grava em /etc/plat e mexe em unidade de produção. O que se exercita aqui é
só a função de extensões, contra bases descartáveis criadas e derrubadas por este arquivo.
"""

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.backup import drill, tarefas
from app.settings import settings

ITEM = "L7-01-d-instalador-extensoes"
RAIZ = Path(__file__).resolve().parents[2]
LEITOR_BASH = RAIZ / "db" / "extensoes.sh"
ARQUIVO = RAIZ / "db" / "extensoes.txt"
# prefixo próprio, nunca `plat_drill_` (do ensaio de restauração) nem o banco da plataforma
PREFIXO = "plat_ext_teste_"


def _postgres(*args, entrada=None, timeout=300):
    return subprocess.run(["sudo", "-n", "-u", "postgres", *args], input=entrada,
                          capture_output=True, text=True, timeout=timeout)


def _psql(banco, sql, timeout=300):
    r = _postgres("psql", "-d", banco, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql,
                  timeout=timeout)
    assert r.returncode == 0, f"{sql}\n{r.stderr}"
    return r.stdout.strip()


def _extensoes(banco) -> set[str]:
    return set(_psql(banco, "SELECT extname FROM pg_extension").split())


def _criar_base(nome, extensoes):
    _derrubar_base(nome)
    r = _postgres("createdb", nome)
    assert r.returncode == 0, r.stderr
    for ext in extensoes:
        _psql(nome, f"CREATE EXTENSION IF NOT EXISTS {ext}")


def _derrubar_base(nome):
    assert nome.startswith(PREFIXO), nome  # guarda: este arquivo nunca derruba outra base
    _postgres("dropdb", "--if-exists", nome)


@pytest.fixture(scope="module")
def dump(env):
    """Dump em formato custom do schema desta trilha — o mesmo tipo de arquivo que o backup lógico do
    L0-06-a produz. Só o esquema: o que se prova é a criação dos objetos, e o dump fica pequeno numa
    máquina com o disco apertado. O arquivo nasce no diretório de backups do produto (tarefas.dir_backups,
    já preparado para receber escrita do dono `postgres`) e é apagado no fim; /tmp/pytest-of-dev não serve,
    o `postgres` não atravessa esse diretório."""
    if not shutil.which("sudo") or _postgres("true").returncode != 0:
        pytest.skip("sem sudo -n -u postgres nesta máquina")
    arquivo = tarefas.dir_backups() / f"ext_l701d_{os.getpid()}.dump"
    banco = urlparse(env["PLAT_DSN"]).path.lstrip("/")
    r = _postgres("pg_dump", "-d", banco, "-n", settings.PLAT_SCHEMA, "--schema-only", "-Fc",
                  "-f", str(arquivo), timeout=600)
    assert r.returncode == 0, r.stderr
    assert arquivo.stat().st_size > 0
    try:
        yield arquivo
    finally:
        arquivo.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def base_so_postgis(dump):
    nome = f"{PREFIXO}{os.getpid()}"
    _criar_base(nome, ["postgis"])
    try:
        yield nome
    finally:
        _derrubar_base(nome)


@pytest.fixture(scope="module")
def base_sem_unaccent(dump):
    nome = f"{PREFIXO}{os.getpid()}_sem"
    _criar_base(nome, [e for e in drill.extensoes_do_ensaio() if e != "unaccent"])
    try:
        yield nome
    finally:
        _derrubar_base(nome)


def _garantir(banco, arquivo=ARQUIVO):
    """Chama plat_extensoes_garantir exatamente como o install.sh chama, com o psql desta máquina."""
    comando = (f'. "{LEITOR_BASH}"; PSQL=(sudo -n -u postgres psql -d {banco} -X -q -v ON_ERROR_STOP=1); '
               f'plat_extensoes_garantir "{arquivo}" "${{PSQL[@]}}"')
    return subprocess.run(["bash", "-c", comando], capture_output=True, text=True, timeout=600)


def _restaurar(banco, dump):
    return _postgres("pg_restore", "-d", banco, "--no-owner", "--no-privileges", str(dump), timeout=600)


def test_01_base_so_com_postgis_termina_com_as_quatro_extensoes(base_so_postgis, medida):
    """Cláusula 1a do portão: a base começa como o instalador a encontrava (só PostGIS) e a função da
    seção "b" do install.sh a deixa com as quatro de db/extensoes.txt, conferidas em pg_extension."""
    antes = _extensoes(base_so_postgis)
    assert "unaccent" not in antes and "pg_trgm" not in antes
    r = _garantir(base_so_postgis)
    assert r.returncode == 0, r.stderr
    depois = _extensoes(base_so_postgis)
    assert set(drill.extensoes_do_ensaio()) <= depois, sorted(depois)
    assert "extensões conferidas em pg_extension" in r.stdout
    medida(ITEM)("extensoes_apos_instalador", sorted(set(drill.extensoes_do_ensaio()) & depois),
                 "nomes", "tests/api/test_instalador_extensoes_base_nova.py::test_01")


def test_02_o_dump_restaura_na_base_nova_e_a_tabela_item_nasce(base_so_postgis, dump, medida):
    """Cláusulas 1b e 2: sem nenhum passo manual entre criar a base e restaurar, a tabela `item` existe."""
    r = _restaurar(base_so_postgis, dump)
    # O código do pg_restore não é a prova (mesma leitura do ensaio do L0-06-c, tarefas._restaurar_e_contar):
    # o schema desta casa tem vistas e chaves estrangeiras que apontam para o schema `acervo`, um ativo que
    # não existe numa base recém-criada. Esses erros são nomeados e conferidos; nenhum outro é aceito.
    fora_do_acervo = [li for li in r.stderr.splitlines()
                      if li.startswith("pg_restore: error:") and "acervo" not in li]
    assert fora_do_acervo == [], "\n".join(fora_do_acervo[:20])
    item = _psql(base_so_postgis,
                 f"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                 f"WHERE n.nspname = '{settings.PLAT_SCHEMA}' AND c.relname = 'item' AND c.relkind = 'r'")
    assert item == "1", f"tabela item ausente na base restaurada (extensões: {sorted(_extensoes(base_so_postgis))})"
    config = _psql(base_so_postgis,
                   f"SELECT count(*) FROM pg_ts_config t JOIN pg_namespace n ON n.oid = t.cfgnamespace "
                   f"WHERE n.nspname = '{settings.PLAT_SCHEMA}' AND t.cfgname = 'pt_sem_acento'")
    assert config == "1"
    medida(ITEM)("tabela_item_apos_restauracao_em_base_nova", True, "booleano",
                 "tests/api/test_instalador_extensoes_base_nova.py::test_02")
    medida(ITEM)("pg_restore_codigo_base_nova", r.returncode, "codigo de saida",
                 "so erros do schema externo acervo; a prova e a presenca da tabela item")


def test_03_refutacao_sem_unaccent_a_restauracao_perde_a_tabela_item(base_sem_unaccent, dump, medida):
    """Refutação exigida, metade 1: é `unaccent` mesmo que sustenta a tabela `item`, não outra coisa."""
    assert "unaccent" not in _extensoes(base_sem_unaccent)
    _restaurar(base_sem_unaccent, dump)  # o pg_restore sai != 0 aqui; o que se afirma é o resultado
    item = _psql(base_sem_unaccent,
                 f"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                 f"WHERE n.nspname = '{settings.PLAT_SCHEMA}' AND c.relname = 'item' AND c.relkind = 'r'")
    assert item == "0", "sem unaccent a tabela item nasceu: a hipótese do item cairia"
    medida(ITEM)("tabela_item_sem_unaccent", False, "booleano",
                 "tests/api/test_instalador_extensoes_base_nova.py::test_03")


def test_04_refutacao_extensao_que_nao_nasce_reprova_nomeando_a_extensao(base_sem_unaccent, tmp_path):
    """Refutação exigida, metade 2: com `unaccent` fora do alcance do CREATE EXTENSION, a conferência em
    pg_extension reprova e a mensagem traz o nome. O psql de mentira aqui não cria unaccent e repassa
    todo o resto ao psql de verdade — é o jeito de simular, sem desinstalar nada da máquina, uma base
    onde a extensão não nasce."""
    falso = tmp_path / "psql_sem_unaccent"
    falso.write_text('#!/bin/bash\nfor a in "$@"; do [[ "$a" == *"EXTENSION IF NOT EXISTS unaccent" ]] '
                     '&& exit 0; done\nexec sudo -n -u postgres psql "$@"\n', encoding="utf-8")
    falso.chmod(0o755)
    comando = (f'. "{LEITOR_BASH}"; PSQL=({falso} -d {base_sem_unaccent} -X -q -v ON_ERROR_STOP=1); '
               f'plat_extensoes_garantir "{ARQUIVO}" "${{PSQL[@]}}"')
    r = subprocess.run(["bash", "-c", comando], capture_output=True, text=True, timeout=600)
    assert r.returncode != 0
    assert "unaccent" in r.stderr and "ausente" in r.stderr, r.stderr
