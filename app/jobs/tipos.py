"""Importa cada módulo de tipos (o registro é preenchido na importação) e expõe REGISTRO. Linhas futuras
acrescentam aqui a importação do seu módulo de tarefas (ex.: app.ingestao.tarefas no L0-04)."""

from app.catalogo import (
    tarefas as catalogo_tarefas,  # noqa: F401 — L0-03: 6 tipos catalogo.* e os periódicos do catálogo
)
from app.jobs import periodicos, tipos_prova  # noqa: F401 — importação registra os tipos
from app.jobs.registro import REGISTRO
from app.raster import tarefas as raster_tarefas  # noqa: F401 — L1-01-b: raster.validar

__all__ = ["REGISTRO"]
