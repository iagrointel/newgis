"""Fixtures emprestadas da fila (tests/api/jobs/conftest.py) para os testes do conector externo: o modo copiado
é um job, e um job só termina se houver worker. Reexportadas aqui em vez de duplicadas — a definição continua
uma só, em `tests/api/jobs/conftest.py`."""

from tests.api.jobs.conftest import (  # noqa: F401 — importar registra as fixtures neste diretório
    cliente_demo,
    iniciar_worker,
    sessao_demo,
)
