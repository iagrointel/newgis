"""Registra `inquilino.exportar` no `app.jobs.registro.REGISTRO` (importado por `app/jobs/tipos.py`);
mesmo papel de `app/exportacao/tipos_job.py` para a exportação de camada."""

from app.exportacao_inquilino.tarefas import inquilino_exportar  # noqa: F401

__all__ = ["inquilino_exportar"]
