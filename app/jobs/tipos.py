"""Importa cada módulo de tipos (o registro é preenchido na importação) e expõe REGISTRO. Linhas futuras
acrescentam aqui a importação do seu módulo de tarefas (ex.: app.ingestao.tarefas no L0-04)."""

from app import status_tarefas  # noqa: F401 — L0-06-e: status.amostrar + periódico de 5 min
from app.backup import tarefas as backup_tarefas  # noqa: F401 — L0-06-a: backup.dump_logico/verificar + periódicos
from app.acervo import tarefas as acervo_tarefas  # noqa: F401 — L6-01-i: acervo.expor_arquivo
from app.catalogo import (
    tarefas as catalogo_tarefas,  # noqa: F401 — L0-03: 6 tipos catalogo.* e os periódicos do catálogo
)
from app.conexao import tarefas as conexao_tarefas  # noqa: F401 — L6-02-l: conexoes.saude_verificar + periódico
from app.correio import tarefas as correio_tarefas  # noqa: F401 — L0-07-d: correio.enviar (somente_sistema)
from app.imagens import ingestao as imagens_ingestao  # noqa: F401 — L1-02: imagens.ingestar (upload -> COG -> pgSTAC)
from app.imagens import (  # noqa: F401 — L1-01-i: periódico semanal do raster
    periodicos as imagens_periodicos,
)
from app.imagens import tarefas as imagens_tarefas  # noqa: F401 — L1-01-i: raster_apagar_objetos + raster_gc
from app.edicao import tarefas as edicao_tarefas  # noqa: F401 — L2-03-f: camadas.lote (edição em lote como job)
from app.exportacao import tipos_job as exportacao_tipos  # noqa: F401 — L0-04-h: exportacao.gerar + periódico
from app.exportacao_inquilino import tipos_job as exportacao_inquilino_tipos  # noqa: F401 — L0-06-d
from app.exportacao import tipos_job as exportacao_tipos  # noqa: F401 — L0-04-h: exportacao.gerar + periódico
from app.geocodificador import lote as geocodificacao_lote  # noqa: F401 — L2-11-a: geocodificacao.lote
from app.geocodificador import tarefas as geocodificador_tarefas  # noqa: F401 — L2-11-a: geocodificador.lote_csv
from app.ingestao import tarefas as ingestao_tarefas  # noqa: F401 — L0-04: ingestao.inspecionar/ingestao.carregar
from app.jobs import periodicos, tipos_prova  # noqa: F401 — importação registra os tipos
from app.jobs.registro import REGISTRO
from app.rede_utilidades import (
    tarefas as rede_tarefas,  # noqa: F401 — L4-04-b redes.subredes_atualizar e L4-01-c rede.importar_bdgd
)
from app.exportacao import tipos_job as exportacao_tipos  # noqa: F401 — L0-04-h: exportacao.gerar + periódico
from app.ingestao import tarefas as ingestao_tarefas  # noqa: F401 — L0-04: ingestao.inspecionar/ingestao.carregar
from app.intercambio import (  # noqa: F401 — L6-02-o: intercambio.exportar_camada/exportar_inquilino
    exportar as intercambio_exportar,
)
from app.jobs import periodicos, tipos_prova  # noqa: F401 — importação registra os tipos
from app.jobs.registro import REGISTRO
from app.layout import tarefas as layout_tarefas  # noqa: F401 — L2-12-b: layout.exportar
from app.regras import tarefas as regras_tarefas  # noqa: F401 — L2-10-d: camadas.validar
from app.replica import tarefas as replica_tarefas  # noqa: F401 — L2-13-b: replicas.criar
from app.migracao import tarefas as migracao_tarefas  # noqa: F401 — L2-08-a: migracao.inventariar
from app.raster import tarefas as raster_tarefas  # noqa: F401 — L1-01-b: raster.validar
from app.relatorios import tarefas as relatorios_tarefas  # noqa: F401 — L0-07-e: relatorios.gerar (CSV do admin)
from app.migracao import tarefas as migracao_tarefas  # noqa: F401 — L2-08-a: migracao.inventariar
from app.uploads import tarefas as uploads_tarefas  # noqa: F401 — L0-04-a: uploads.expirar + periódico

__all__ = ["REGISTRO"]
