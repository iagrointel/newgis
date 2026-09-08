"""Servidor local de desenvolvimento do plat: a API (app.main) mais /static/ servido do disco (web/), que em
produção é papel do nginx (ADR 0001 seção 4.3). Serve para abrir as telas de um worktree no navegador e para
o e2e de identidade visual (tests/e2e/test_estilo.py) sem nginx. Nunca substitui a unidade plat-api.
Uso: set -a; source <env da trilha>; set +a; venv/bin/python scripts/servir_local.py --porta 8157

Escrita pelo navegador exige Origin igual a PLAT_URL_PUBLICA (CSRF, app/auth/sessao.py), e PLAT_URL_PUBLICA tem de
ser https. Para o e2e exercitar escrita contra este servidor: certificado autoassinado (`openssl req -x509 ... -addext
subjectAltName=IP:127.0.0.1`), `--certificado`/`--chave`, PLAT_URL_PUBLICA=https://127.0.0.1:<porta> no ambiente do
servidor e `--base-url https://127.0.0.1:<porta>` no pytest (tests/e2e/conftest.py já ignora erro de certificado
quando o host é 127.0.0.1)."""

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.main import WEB  # noqa: E402
from app.main import app as api  # noqa: E402

servidor = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
servidor.mount("/static", StaticFiles(directory=str(Path(WEB))), name="static")
servidor.mount("/", api)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--porta", type=int, default=8157)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--certificado", help="PEM do certificado; com --chave liga TLS (Origin https no e2e de escrita)")
    p.add_argument("--chave", help="PEM da chave privada")
    a = p.parse_args()
    uvicorn.run(servidor, host=a.host, port=a.porta, log_level="warning", access_log=False,
                ssl_certfile=a.certificado, ssl_keyfile=a.chave)
