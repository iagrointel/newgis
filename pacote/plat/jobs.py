"""Fila de jobs: criar, acompanhar progresso, cancelar e ESPERAR. `Jobs.esperar` é o bloco de
construção das ferramentas (`plat.ferramentas`): consulta o job num intervalo fixo até um estado
final e devolve o job completo (com `resultado` ou `erro` e a procedência que o worker grava).

Exemplo (`pla` é uma `Plataforma` já conectada; o doctest roda contra a demo com worker vivo):

    >>> ponto = {"type": "Point", "coordinates": [220000.0, 7450000.0]}
    >>> job = pla.jobs.criar("ferramentas.buffer", {"geometria": ponto, "distancia_m": 100.0})
    >>> pronto = pla.jobs.esperar(job["id"], intervalo_s=0.2)
    >>> pronto["estado"]
    'concluido'
    >>> pronto["resultado"]["area_m2"] > 30000
    True
"""

from __future__ import annotations

import time
from typing import Any, Callable

from plat import erros
from plat.cliente import Plataforma

FINAIS = ("concluido", "falhou", "cancelado")


class Jobs:
    def __init__(self, pla: Plataforma):
        self._pla = pla

    def criar(self, tipo: str, parametros: dict[str, Any] | None = None, *, prioridade: str | None = None,
              agendado_para: str | None = None) -> dict:
        """Enfileira um job (`POST /api/jobs`); `agendado_para` é ISO-8601 com fuso. Sem privilégio
        `jobs.executar` no dono do token a recusa é `ErroPermissao` (403)."""
        corpo: dict[str, Any] = {"tipo": tipo, "parametros": parametros or {}}
        if prioridade:
            corpo["prioridade"] = prioridade
        if agendado_para:
            corpo["agendado_para"] = agendado_para
        return self._pla.post("/api/jobs", json=corpo)

    def obter(self, job_id: str) -> dict:
        """Estado atual do job (`GET /api/jobs/{id}`), com progresso, resultado/erro e procedência."""
        return self._pla.get(f"/api/jobs/{job_id}")

    def cancelar(self, job_id: str) -> dict:
        """Pede cancelamento (`POST /api/jobs/{id}/cancelar`): cooperativo — o worker checa entre passos."""
        return self._pla.post(f"/api/jobs/{job_id}/cancelar")

    def esperar(self, job_id: str, *, intervalo_s: float = 1.0, timeout_s: float = 600.0,
                ao_progresso: Callable[[int, str | None], None] | None = None) -> dict:
        """Bloqueia até um estado final; no fim devolve o job COMPLETO. Falha de job levanta
        `FalhaJob` com a mensagem do job; estourar `timeout_s` levanta `FalhaJob.cancelado=False`
        com o último estado visto (o job continua na fila — cancelar é responsabilidade de quem chamou)."""
        fim = time.monotonic() + timeout_s
        ultimo: dict[str, Any] = {}
        while True:
            ultimo = self.obter(job_id)
            if ao_progresso and ultimo.get("estado") == "rodando":
                ao_progresso(int(ultimo.get("progresso") or 0), ultimo.get("mensagem"))
            estado = ultimo.get("estado")
            if estado == "concluido":
                return ultimo
            if estado == "cancelado":
                raise erros.FalhaJob(f"job {job_id} cancelado", cancelado=True, job=ultimo)
            if estado == "falhou":
                raise erros.FalhaJob(f"job {job_id} falhou: {ultimo.get('erro')}", job=ultimo)
            if time.monotonic() >= fim:
                raise erros.FalhaJob(
                    f"job {job_id} não terminou em {timeout_s:g} s (último estado: {estado!r})", job=ultimo
                )
            time.sleep(intervalo_s)
