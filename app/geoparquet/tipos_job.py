"""Registra o tipo de job do geoparquet no `app.jobs.registro.REGISTRO` (importado por `app/jobs/tipos.py`);
mesmo papel de `app.exportacao.tipos_job` para a exportação de formato (item L0-04-h)."""

from app.geoparquet.tarefas import geoparquet_gerar  # noqa: F401 — a importação registra o tipo

__all__ = ["geoparquet_gerar"]
