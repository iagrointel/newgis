"""Importa cada módulo de tipos (o registro é preenchido na importação) e expõe REGISTRO. Linhas futuras
acrescentam aqui a importação do seu módulo de tarefas (ex.: app.ingestao.tarefas no L0-04).

Achado 15/09 (wt/f2-tiposjob, família "tipo de job órfão"): 27 módulos com @tarefa existiam no código
(muitos com rota que já os enfileira) mas nunca eram importados aqui — o tipo nunca entrava em REGISTRO e a
chamada batia em 422 tipo_desconhecido (POST /api/exportacoes entre elas). Ver
tests/unit/test_jobs_registro.py::test_todo_tipo_enfileirado_esta_registrado (varredura geral, não lista
fixa) para a prova de que isso não volta a acontecer em silêncio. Um 28º módulo, app.edicao.tarefas, FICA
DE FORA — ver comentário junto à importação de app.correio abaixo (bug pré-existente e alheio em
app/edicao/modelos.py, já presente em wt/uniao)."""

from app import (
    status_tarefas,  # noqa: F401 — L0-06-e-status: status.amostrar + periódico (achado L7-03-f)
    telemetria,  # noqa: F401 — achado 15/09: telemetria.enviar (envio diário do appliance)
)
from app.acervo import tarefas as acervo_tarefas  # noqa: F401 — achado 15/09: acervo.frescor_verificar
from app.agol import (
    tarefas as agol_tarefas,  # noqa: F401 — L2-08: agol.publicar (hosted feature layer no AGOL do cliente)
)
from app.amc import tarefas as amc_tarefas  # noqa: F401 — gerar_unidades/robustez_pesos/smaa/recombinar
from app.backup import (
    tarefas as backup_tarefas,  # noqa: F401 — L0-06: backup.executar/backup.ensaio_restauracao + periódicos
)
from app.catalogo import (
    tarefas as catalogo_tarefas,  # noqa: F401 — L0-03: 7 tipos catalogo.* e os periódicos do catálogo
)
from app.conexao import copia as conexao_copia  # noqa: F401 — achado 15/09: conexao.copiar_vetor
from app.conexao import tarefas as conexao_tarefas  # noqa: F401 — L6-02-l: conexoes.saude_verificar + periódico
from app.conexao import (
    tarefas_agendamento as conexao_tarefas_agendamento,  # noqa: F401 — achado 15/09: conexao.atualizar_copia/agenda.avisos_enviar + periódico
)
from app.conexao import (
    tarefas_arquivo as conexao_tarefas_arquivo,  # noqa: F401 — L6-02-h: arquivo por URL (CSV/GeoJSON/KML/KMZ/GeoRSS/GPX)
)
from app.conexao import (
    tarefas_endpoints as conexao_tarefas_endpoints,  # noqa: F401 — achado 15/09: endpoints_publicos.retestar
)
from app.edicao import (
    tarefas as edicao_tarefas,  # noqa: F401 — camadas.lote: modelos restaurados em 16/09 (f2ce41ab4)  # noqa: F401 — L0-07-d: correio.enviar (somente_sistema)
)

# app.edicao.tarefas (camadas.lote) FICA DE FORA de propósito: acionado 15/09, `app/edicao/lote.py` importa
# LoteEntrada/LoteFalha/LotePrevia/LoteSaida de app/edicao/modelos.py, que não os define (confirmado também
# em wt/uniao HEAD — não é regressão deste ramo). Bug pré-existente e fora do escopo "tipo de job órfão"
# (é o path SÍNCRONO de edição em lote que está quebrado, não o registro do tipo); nenhuma rota chama
# "camadas.lote" hoje (não apareceu na varredura de test_todo_tipo_enfileirado_esta_registrado), então
# importar aqui só derrubaria toda a suíte de jobs por um ImportError alheio. PARAR E RELATAR ao gerente
# em vez de inventar os 4 modelos ou de forçar o import: decisão de quem sabe a forma pretendida do modelo.
from app.exportacao import (
    tipos_job as exportacao_tipos_job,  # noqa: F401 — achado 15/09: exportacao.gerar (POST /api/exportacoes, 422 tipo_desconhecido) + exportacao.expirar
)
from app.exportacao_inquilino import (
    tarefas as exportacao_inquilino_tarefas,  # noqa: F401 — achado 15/09: inquilino.exportar
)
from app.ferramentas import executor as ferramentas_executor  # noqa: F401 — achado 15/09: ferramentas.executar
from app.ferramentas import (
    script_tarefas as ferramentas_script_tarefas,  # noqa: F401 — achado 15/09: ferramentas.executar_script
)
from app.ferramentas import tarefas as ferramentas_tarefas  # noqa: F401 — achado 15/09: ferramentas.buffer
from app.geocodificador import (
    tarefas as geocodificador_tarefas,  # noqa: F401 — achado 15/09: geocodificador.lote_csv
)
from app.geoparquet import tarefas as geoparquet_tarefas  # noqa: F401 — achado 15/09: geoparquet.gerar
from app.imagens import ingestao as imagens_ingestao  # noqa: F401 — L1-02: imagens.ingestar (upload -> COG -> pgSTAC)
from app.imagens import (
    reexecucao as imagens_reexecucao,  # noqa: F401 — L1-01-j: imagens.preencher_proveniencia/imagens.reexecutar
)
from app.imagens import (
    tarefas as imagens_tarefas,  # noqa: F401 — achado 15/09: imagens.raster_apagar_objetos/imagens.raster_gc
)
from app.ingestao import tarefas as ingestao_tarefas  # noqa: F401 — L0-04: ingestao.inspecionar/ingestao.carregar
from app.intercambio import (
    exportar as intercambio_exportar,  # noqa: F401 — achado 15/09: intercambio.exportar_camada/intercambio.exportar_inquilino
)
from app.jobs import periodicos, tipos_prova  # noqa: F401 — importação registra os tipos
from app.jobs import seguranca as jobs_seguranca  # noqa: F401 — L7-03-f: seguranca.varrer_cve + periódico
from app.jobs.registro import REGISTRO
from app.layout import tarefas as layout_tarefas  # noqa: F401 — achado 15/09: layout.exportar
from app.migracao import tarefas as migracao_tarefas  # noqa: F401 — achado 15/09: migracao.inventariar
from app.modelo3d import ingestao as modelo3d_ingestao  # noqa: F401 — L1-03: modelo3d.converter (IFC -> xkt)
from app.modelos3d import (
    tarefas as modelos3d_tarefas,  # noqa: F401 — achado 15/09: modelos3d.converter/modelo3d.tileset
)
from app.notebooks import (
    tarefas as notebooks_tarefas,  # noqa: F401 — achado 15/09: notebooks.executar/notebooks.ceifar
)
from app.odk import tarefas as odk_tarefas  # noqa: F401 — achado 15/09: odk.sincronizar
from app.ogc_mapas import tarefas as ogc_mapas_tarefas  # noqa: F401 — achado 15/09: wmts.publicar
from app.raster import tarefas as raster_tarefas  # noqa: F401 — achado 15/09: raster.validar
from app.rede_medicao import (
    tarefas as rede_medicao_tarefas,  # noqa: F401 — L4-13: rede_medicao.particoes_criar + periódico (pausado)
)
from app.rede_utilidades import (
    epanet_importar as rede_epanet_tarefas,  # noqa: F401 — L4-05-d: rede.epanet_importar
)
from app.rede_utilidades import (
    tarefas as rede_utilidades_tarefas,  # noqa: F401 — achado 15/09: rede.importar_bdgd/redes.subredes_atualizar/redes.analisar_alimentador
)
from app.regras import tarefas as regras_tarefas  # noqa: F401 — achado 15/09: camadas.validar
from app.relatorios import tarefas as relatorios_tarefas  # noqa: F401 — achado 15/09: relatorios.gerar
from app.replica import tarefas as replica_tarefas  # noqa: F401 — achado 15/09: replicas.criar
from app.uploads import tarefas as uploads_tarefas  # noqa: F401 — L0-04-a: uploads.expirar + periódico

__all__ = ["REGISTRO"]
