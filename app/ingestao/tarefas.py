"""Registra os dois tipos de job da ingestão vetorial (ADR 0005) no `app.jobs.registro.REGISTRO`: importar este
módulo (feito por `app/jobs/tipos.py`) basta — o decorador `@tarefa` já faz o registro na importação."""

from app.ingestao.carregar import ingestao_carregar  # noqa: F401
from app.ingestao.inspecionar import ingestao_inspecionar  # noqa: F401

__all__ = ["ingestao_inspecionar", "ingestao_carregar"]
