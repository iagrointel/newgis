"""Registra o job periódico do upload retomável (`uploads.expirar`, L0-04-a) no `app.jobs.registro.REGISTRO`:
importar este módulo (feito por `app/jobs/tipos.py`) basta — o decorador `@tarefa` já registra na importação, e
`app.uploads.periodicos` soma a agenda à lista do worker."""

from app.uploads.periodicos import uploads_expirar  # noqa: F401

__all__ = ["uploads_expirar"]
