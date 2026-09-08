"""Servidor local de desenvolvimento do plat: a API (app.main) mais /static/ servido do disco (web/), que em
produção é papel do nginx (ADR 0001 seção 4.3). Serve para abrir as telas de um worktree no navegador e para
o e2e de identidade visual (tests/e2e/test_estilo.py) sem nginx. Nunca substitui a unidade plat-api.
Uso: set -a; source <env da trilha>; set +a; venv/bin/python scripts/servir_local.py --porta 8157

Com `--cert`/`--chave` serve por TLS. Isso é necessário no e2e que ESCREVE pela tela: a defesa de CSRF
(app/auth/sessao.py::checar_escrita_sob_cookie) compara o cabeçalho `Origin` do navegador com
`PLAT_URL_PUBLICA`, que é obrigatoriamente `https://` — sem TLS, todo PATCH/PUT feito pelo navegador volta
403 origem_invalida. Certificado autoassinado serve (o navegador do teste abre com ignore_https_errors)."""

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
    p.add_argument("--cert", default=None, help="certificado TLS (PEM); com --chave, serve por https")
    p.add_argument("--chave", default=None, help="chave privada do certificado (PEM)")
    a = p.parse_args()
    uvicorn.run(servidor, host=a.host, port=a.porta, log_level="warning", access_log=False,
                ssl_certfile=a.cert, ssl_keyfile=a.chave)
