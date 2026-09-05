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
    v = dict(dotenv_values(ROOT / ".env"))
    v.update({k: os.environ[k] for k in list(v) + ["PLAT_URL_PUBLICA", "PLAT_DSN"] if k in os.environ})
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
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
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
