"""Teto de eventos por segundo POR FONTE, com descarte contado (item L2-14-a-ingestao-de-fluxos).

Balde de fichas (token bucket) em memória do processo `plat-fluxo`: a fonte ganha `limite_eventos_s` fichas
por segundo, acumula no máximo um segundo de folga e cada evento consome uma ficha. Sem ficha, o evento é
DESCARTADO e CONTADO (`descartados_limite`) — nunca enfileirado, porque enfileirar o excesso é o mesmo que
não ter teto: a memória do processo cresceria até o fim.

Não é distribuído: com N processos `plat-fluxo`, o teto efetivo é N × `limite_eventos_s`. Está declarado
assim no manual e no ADR; um teto exato entre processos exigiria contador central por evento, que custa mais
que o próprio evento.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Balde:
    taxa: float
    fichas: float = 0.0
    quando: float = field(default_factory=time.monotonic)
    descartados: int = 0

    def __post_init__(self):
        self.fichas = float(self.taxa)

    def permitir(self, quantos: int = 1, agora: float | None = None) -> int:
        """Devolve quantos dos `quantos` eventos passam; o resto entra em `descartados`."""
        agora = time.monotonic() if agora is None else agora
        decorrido = max(0.0, agora - self.quando)
        self.quando = agora
        self.fichas = min(float(self.taxa), self.fichas + decorrido * self.taxa)
        passam = int(min(quantos, self.fichas))
        self.fichas -= passam
        self.descartados += quantos - passam
        return passam

    def ajustar(self, taxa: float) -> None:
        """Fonte editada: o teto novo vale já, sem perder as fichas acumuladas além do novo teto."""
        self.taxa = float(taxa)
        self.fichas = min(self.fichas, self.taxa)
