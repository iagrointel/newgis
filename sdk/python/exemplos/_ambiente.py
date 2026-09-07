"""Ambiente comum dos 10 exemplos: lê URL/credenciais de variável de ambiente quando executado como
script (`python exemplos/01_login.py`) e recebe os mesmos valores por parâmetro quando chamado pelo
teste (`tests/sdk/test_exemplos.py`) — o MESMO código roda nos dois casos, sem `if __name__` duplicado
por exemplo."""

from __future__ import annotations

import os

# `dados` mínimo válido para tipo_item "mapa" (app/catalogo/rotas_itens.py valida contra
# docs/esquemas/mapa.json — esquema_versao e corpo são obrigatórios; um mapa vazio é válido).
DADOS_MAPA = {"esquema_versao": 1, "corpo": {}}


def do_ambiente() -> tuple[str, str, str, str]:
    """(url, inquilino, login, senha) das variáveis PLAT_SDK_URL/INQUILINO/LOGIN/SENHA — só para uso
    manual fora do pytest; a suíte passa os valores da fixture `credenciais_demo` direto."""
    url = os.environ.get("PLAT_SDK_URL", "http://127.0.0.1:8278")
    inquilino = os.environ.get("PLAT_SDK_INQUILINO", "demo")
    login = os.environ.get("PLAT_SDK_LOGIN", "admin")
    senha = os.environ.get("PLAT_SDK_SENHA", "")
    if not senha:
        raise SystemExit("defina PLAT_SDK_SENHA (veja laco/var/trilha/il708bsdkpy.credenciais.txt)")
    return url, inquilino, login, senha
