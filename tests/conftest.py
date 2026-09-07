"""Fixtures do plat (ADR 0001 seção 10): cliente HTTP da API, conexão como plat_app, gravador de medidas,
URL pública. Nenhum teste conecta como postgres; RLS é provada com a role da aplicação."""

import datetime
import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
MEDIDAS = ROOT / "tests" / "medidas"


def valores_env() -> dict[str, str | None]:
    """.env + ambiente do processo. PLAT_SECRET e PLAT_DSN_WORKER não moram mais no .env desde o item
    L7-19 (LoadCredential do systemd, docs/SEGURANCA.md); o Makefile os injeta no ambiente do pytest
    (`sudo cat /etc/plat/segredos/...`), por isso entram sempre pela lista explícita, não só quando já
    estavam no dicionário do .env."""
    v = dict(dotenv_values(ROOT / ".env"))
    # item L7-31 (docs/HOMOLOGACAO.md): make homolog roda esta MESMA suíte com PLAT_SCHEMA/etc no
    # ambiente do processo (scripts/homolog_e2e.sh), nunca no .env real — entram pela lista explícita
    # pelo mesmo motivo de PLAT_SECRET/PLAT_DSN_WORKER acima.
    chaves = list(v) + ["PLAT_URL_PUBLICA", "PLAT_DSN", "PLAT_SECRET", "PLAT_DSN_WORKER",
                        "PLAT_SCHEMA", "PLAT_SCHEMA_TRABALHO", "PLAT_CANAL_JOB", "PLAT_CANAL_WORKER"]
    v.update({k: os.environ[k] for k in chaves if k in os.environ})
    return v


@pytest.fixture(scope="session")
def env() -> dict[str, str | None]:
    v = valores_env()
    if not v.get("PLAT_DSN"):
        pytest.skip("sem .env com PLAT_DSN (rode sudo bash install.sh <dominio> <porta>)")
    return v


@pytest.fixture(scope="session")
def cliente(env):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def conexao_plat_app(env):
    # CursorSchemaAmbiente, não RealDictCursor: esta conexão faz SQL cru com `plat.` literal, e sem a
    # reescrita ela ignora PLAT_SCHEMA e vai bater no schema de produção. É subclasse de RealDictCursor
    # e no-op quando o schema é o padrão, logo produção não muda em nada; sem isto, `make homolog` e as
    # bases por trilha (laco/trilha_ambiente.sh) erram por privilégio em vez de rodar isolados.
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        yield con
    finally:
        con.rollback()
        con.close()


@pytest.fixture(scope="session")
def base_url(request, env) -> str:
    """URL pública: --base-url quando dado, senão PLAT_URL_PUBLICA do .env (também usada pelo playwright)."""
    opcao = request.config.getoption("base_url", default=None)
    return (opcao or env["PLAT_URL_PUBLICA"]).rstrip("/")


@pytest.fixture(scope="session")
def url_publica_resolve(base_url) -> bool:
    host = urlparse(base_url).hostname or ""
    try:
        socket.gethostbyname(host)
        return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def medida():
    """medida(item)(nome, valor, unidade, comando) grava/atualiza tests/medidas/<item>.json."""
    from app.versao import git_sha_curto

    def para_item(item: str):
        caminho = MEDIDAS / f"{item}.json"

        def gravar(nome: str, valor, unidade: str, comando: str) -> None:
            if os.environ.get("PLAT_GRAVAR_MEDIDAS") != "1":
                return  # a suite nao pode sujar a arvore; o testador grava com PLAT_GRAVAR_MEDIDAS=1
            MEDIDAS.mkdir(parents=True, exist_ok=True)
            dados = {"item": item, "medidas": {}}
            if caminho.exists():
                dados = json.loads(caminho.read_text(encoding="utf-8"))
            dados["gerado_em"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            dados["git_sha"] = git_sha_curto()
            dados.setdefault("medidas", {})[nome] = {"valor": valor, "unidade": unidade, "comando": comando}
            caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

        return gravar

    return para_item


def pytest_sessionfinish(session, exitstatus):
    """Varredura final do resíduo zt-* no processo CONTROLADOR do pytest-xdist, depois que TODOS os workers
    terminaram.

    Por que aqui e não no conftest de tests/api: sob xdist quem colhe os testes é o worker, então o controlador
    só importa os conftests INICIAIS — os das pastas dadas na linha de comando. Com `pytest ... tests`, o único
    conftest inicial é este; um `pytest_sessionfinish` escrito em tests/api/conftest.py roda nos workers e nunca
    no controlador (medido em 07/09: o gancho só aparecia com w=True).

    Por que não deixar cada worker varrer: `varrer_residuos` e `_expurgar_zt` apagam por PREFIXO (todo token,
    usuário, grupo, papel, inquilino e item cujo nome começa por zt). Os workers terminam em instantes
    diferentes, então o primeiro a acabar apagava o que os outros ainda estavam usando — daí 401 no lugar de
    404 em test_plataforma/test_cruzado e item zt sobrando na contagem de test_busca. Na rodada serial (-n 0)
    este gancho não faz nada: lá quem varre continua sendo a fixture de sessão.
    """
    import os

    if os.environ.get("PYTEST_XDIST_WORKER") or not getattr(session.config.option, "numprocesses", None):
        return
    from tests.api.catalogo.conftest import _expurgar_zt
    from tests.api.conftest import _sessao_admin, _sessao_superadmin, credenciais, varrer_residuos

    try:
        c = credenciais()
        if all(slug in c for slug in ("demo", "demo2", "plataforma")):
            varrer_residuos(_sessao_admin(c, "demo"), _sessao_admin(c, "demo2"), _sessao_superadmin(c))
        env = valores_env()
        if env.get("PLAT_DSN"):
            for slug in ("demo", "demo2"):
                _expurgar_zt(env, slug)
    except Exception as e:  # noqa: BLE001 - limpeza best-effort: nunca derruba a rodada por causa dela
        session.config.pluginmanager.get_plugin("terminalreporter").write_line(
            f"[limpeza] varredura de resíduo zt-* no controlador falhou: {type(e).__name__}: {e}"
        )
