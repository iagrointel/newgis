"""Registra os tipos de job da exportação no `app.jobs.registro.REGISTRO` (importado por `app/jobs/tipos.py`);
mesmo papel de `app/uploads/tarefas.py` para o upload retomável."""

from app.exportacao.periodicos import exportacao_expirar  # noqa: F401 — a importação registra o tipo
from app.exportacao.tarefas import exportacao_gerar  # noqa: F401

__all__ = ["exportacao_expirar", "exportacao_gerar"]
