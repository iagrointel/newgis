"""Registra os tipos de job da ingestão vetorial (ADR 0005) e da exportação (item L6-02-o) no
`app.jobs.registro.REGISTRO`: importar este módulo (feito por `app/jobs/tipos.py`) basta — o decorador `@tarefa`
já faz o registro na importação."""

from app.ingestao.carregar import ingestao_carregar  # noqa: F401
from app.ingestao.exportar import ingestao_exportar_camada, ingestao_exportar_inquilino  # noqa: F401
from app.ingestao.inspecionar import ingestao_inspecionar  # noqa: F401

__all__ = ["ingestao_inspecionar", "ingestao_carregar", "ingestao_exportar_camada", "ingestao_exportar_inquilino"]
