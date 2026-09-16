"""Ferramentas geoespaciais por job: `executar(nome, parametros)` cria o job, espera o fim e devolve
o RESULTADO do job; quando a ferramenta grava o resultado como item do catálogo, o dicionário traz
`item_id` e o item guarda a procedência (ferramenta, versão, sha256 da entrada, biblioteca).

Exemplo (buffer de 100 m em torno de um ponto em srid métrico; `pla` é uma `Plataforma` conectada):

    >>> r = pla.ferramentas.buffer({"type": "Point", "coordinates": [220000.0, 7450000.0]}, 100.0)
    >>> r["buffer"]["type"]
    'Polygon'
    >>> 30000 < r["area_m2"] < 32000
    True
    >>> item = pla.catalogo.abrir(r["item_id"])
    >>> item["tipo"]
    'ferramenta_resultado'
    >>> item["dados"]["procedencia"]["ferramenta"]
    'ferramentas.buffer'
"""

from __future__ import annotations

from typing import Any

from plat_geo.cliente import Plataforma

TETOS = {"ferramentas.buffer": {"distancia_m": "até 100 km; acima disso a API recusa (422)"}}


class Ferramentas:
    def __init__(self, pla: Plataforma):
        self._pla = pla
        self.jobs = pla.jobs

    def tipos(self) -> list[dict]:
        """Catálogo de tipos de job disponíveis (`GET /api/jobs/tipos`) — inclui as ferramentas."""
        return self._pla.get("/api/jobs/tipos")

    def executar(self, nome: str, parametros: dict[str, Any] | None = None, *, timeout_s: float = 600.0,
                 intervalo_s: float = 1.0, prioridade: str | None = None,
                 ao_progresso=None) -> dict:
        """Cria o job `nome`, espera o fim e devolve `job["resultado"]` (a ferramenta de catálogo traz
        `item_id`). Falha do job levanta `FalhaJob`; parâmetro fora do esquema levanta `ErroValidacao`
        já na criação (a API valida com pydantic antes de enfileirar)."""
        job = self.jobs.criar(nome, parametros or {}, prioridade=prioridade)
        pronto = self.jobs.esperar(job["id"], intervalo_s=intervalo_s, timeout_s=timeout_s,
                                   ao_progresso=ao_progresso)
        return pronto.get("resultado") or {}

    # ------------------------------------------------------------------ ferramentas prontas
    def buffer(self, geometria: dict, distancia_m: float, *, srid: int = 31983,
               titulo: str | None = None, timeout_s: float = 600.0, intervalo_s: float = 1.0) -> dict:
        """`ferramentas.buffer`: buffer PLANO no srid MÉTRICO informado (padrão 31983, SIRGAS 2000
        UTM 23S — metros). SRID geográfico (graus) é recusado com `ErroValidacao`: buffer em grau
        não tem unidade. O resultado vira item `ferramenta_resultado` com procedência."""
        parametros: dict[str, Any] = {"geometria": geometria, "distancia_m": distancia_m, "srid": srid}
        if titulo:
            parametros["titulo"] = titulo
        return self.executar("ferramentas.buffer", parametros, timeout_s=timeout_s, intervalo_s=intervalo_s)
