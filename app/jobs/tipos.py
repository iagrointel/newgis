"""Importa cada módulo de tipos (o registro é preenchido na importação) e expõe REGISTRO. Linhas futuras
acrescentam aqui a importação do seu módulo de tarefas (ex.: app.ingestao.tarefas no L0-04)."""

from app.catalogo import (
    tarefas as catalogo_tarefas,  # noqa: F401 — L0-03: 6 tipos catalogo.* e os periódicos do catálogo
)
from app.conexao import tarefas as conexao_tarefas  # noqa: F401 — L6-02-l: conexoes.saude_verificar + periódico
from app.correio import tarefas as correio_tarefas  # noqa: F401 — L0-07-d: correio.enviar (somente_sistema)
from app.exportacao import tipos_job as exportacao_tipos  # noqa: F401 — L0-04-h: exportacao.gerar + periódico
from app.geoparquet import tipos_job as geoparquet_tipos  # noqa: F401 — L2-15-a: geoparquet.gerar
from app.consulta_grande import consulta_livre as cg_consulta_livre  # noqa: F401 — L2-15-b: consulta_sql
from app.consulta_grande import ferramentas_grandes as cg_ferramentas  # noqa: F401 — L2-15-b: 6 grandes
from app.ferramentas import buffer as ferramentas_buffer  # noqa: F401 — L2-05-a: ferramenta de exemplo
from app.ferramentas import executor as ferramentas_executor  # noqa: F401 — L2-05-a: ferramentas.executar
from app.ingestao import tarefas as ingestao_tarefas  # noqa: F401 — L0-04: ingestao.inspecionar/ingestao.carregar
from app.jobs import periodicos, tipos_prova  # noqa: F401 — importação registra os tipos
from app.jobs.registro import REGISTRO
from app.uploads import tarefas as uploads_tarefas  # noqa: F401 — L0-04-a: uploads.expirar + periódico

__all__ = ["REGISTRO"]
