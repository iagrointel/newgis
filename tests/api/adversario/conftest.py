"""Adversário HARD-03: só roda contra base de trilha/homologação. Em produção (PLAT_SCHEMA=plat) o pacote inteiro
é pulado com o motivo — os testes criam usuários, papéis, tokens e itens de ataque e nunca podem tocar o schema
real (regra dura do brief do líder de endurecimento)."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PLAT_SCHEMA", "plat") == "plat":
        marca = pytest.mark.skip(reason="adversário HARD-03 só roda em trilha (PLAT_SCHEMA != plat)")
        for it in items:
            if "tests/api/adversario/" in str(it.fspath).replace("\\", "/"):
                it.add_marker(marca)
