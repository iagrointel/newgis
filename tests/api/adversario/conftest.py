"""Adversário HARD-03: só roda contra base de trilha/homologação. Em produção (PLAT_SCHEMA=plat) o pacote inteiro
é pulado — os testes criam objetos de ataque e nunca podem tocar o schema real (regra do brief do endurecimento)."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PLAT_SCHEMA", "plat") == "plat":
        marca = pytest.mark.skip(reason="adversário HARD-03 só roda em trilha (PLAT_SCHEMA != plat)")
        for it in items:
            if "tests/api/adversario/" in str(it.fspath).replace("\\", "/"):
                it.add_marker(marca)
