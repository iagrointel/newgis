"""Cláusula do portão do item L0-06-e-status: derrubar o worker muda o campo dentro da janela e religar o
traz de volta.

O que NÃO se faz aqui: `systemctl stop plat-worker`. Derrubar unidade de produção é proibido na trilha, e o
teste ficaria preso à máquina. O que a página realmente enxerga do worker é a sonda HTTP de PLAT_WORKER_URL,
então é ela que o teste encena, com um servidor de verdade numa porta livre: no ar -> `ok`; derrubado ->
`erro`; de volta -> `ok`. Entre um e outro o teste espera o cache vencer, que é o atraso máximo possível
(30 s, contra os 5 minutos que o portão admite).

O teste leva pouco mais de um minuto de relógio, quase todo em espera do cache.
"""

import dataclasses
import time

import pytest

from app import status
from app.settings import settings
from tests.api.test_status import _Servidor


def _apontar_worker(monkeypatch, porta: int) -> None:
    """`settings` é dataclass congelada: troca-se o objeto que app.status enxerga, não um campo dele."""
    monkeypatch.setattr(status, "settings", dataclasses.replace(settings, PLAT_WORKER_URL=f"http://127.0.0.1:{porta}"))


@pytest.fixture
def worker_de_mentira(monkeypatch):
    s = _Servidor()
    _apontar_worker(monkeypatch, s.porta)
    status.limpar_cache()
    yield s
    try:
        s.parar()
    except Exception:  # noqa: BLE001 — já pode estar parado pelo teste
        pass
    status.limpar_cache()


def _estado_worker(cliente) -> str:
    return cliente.get("/api/status").json()["servicos"]["worker"]["estado"]


def test_worker_cai_e_volta_dentro_da_janela(cliente, worker_de_mentira, monkeypatch):
    assert _estado_worker(cliente) == "ok"

    worker_de_mentira.parar()
    assert _estado_worker(cliente) == "ok", "o retrato ainda é o do cache — é isso que se espera"

    inicio = time.monotonic()
    time.sleep(status.CACHE_S + 1)
    assert _estado_worker(cliente) == "erro"
    demorou_para_cair = time.monotonic() - inicio
    assert demorou_para_cair < 300, demorou_para_cair

    de_volta = _Servidor()  # o worker volta (porta nova: a anterior pode ficar em TIME_WAIT)
    _apontar_worker(monkeypatch, de_volta.porta)
    inicio = time.monotonic()
    time.sleep(status.CACHE_S + 1)
    assert _estado_worker(cliente) == "ok"
    assert time.monotonic() - inicio < 300
    de_volta.parar()
