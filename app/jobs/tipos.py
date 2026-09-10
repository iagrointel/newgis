"""Importa cada módulo de tipos (o registro é preenchido na importação) e expõe REGISTRO. Linhas futuras
acrescentam aqui a importação do seu módulo de tarefas (ex.: app.ingestao.tarefas no L0-04)."""

from app.agol import (
    tarefas as agol_tarefas,  # noqa: F401 — L2-08: agol.publicar (hosted feature layer no AGOL do cliente)
)
from app.backup import (
    tarefas as backup_tarefas,  # noqa: F401 — L0-06: backup.executar/backup.ensaio_restauracao + periódicos
)
from app.catalogo import (
    tarefas as catalogo_tarefas,  # noqa: F401 — L0-03: 6 tipos catalogo.* e os periódicos do catálogo
)
from app.conexao import tarefas as conexao_tarefas  # noqa: F401 — L6-02-l: conexoes.saude_verificar + periódico
from app.correio import tarefas as correio_tarefas  # noqa: F401 — L0-07-d: correio.enviar (somente_sistema)
from app.imagens import ingestao as imagens_ingestao  # noqa: F401 — L1-02: imagens.ingestar (upload -> COG -> pgSTAC)
from app.imagens import (
    reexecucao as imagens_reexecucao,  # noqa: F401 — L1-01-j: imagens.preencher_proveniencia/imagens.reexecutar
)
from app.ingestao import tarefas as ingestao_tarefas  # noqa: F401 — L0-04: ingestao.inspecionar/ingestao.carregar
from app.jobs import periodicos, tipos_prova  # noqa: F401 — importação registra os tipos
from app.jobs.registro import REGISTRO
from app.modelo3d import ingestao as modelo3d_ingestao  # noqa: F401 — L1-03: modelo3d.converter (IFC -> xkt)
from app.rede_utilidades import (
    tarefas as rede_tarefas,  # noqa: F401 — L4-04-b redes.subredes_atualizar e L4-01-c rede.importar_bdgd
)
from app.uploads import tarefas as uploads_tarefas  # noqa: F401 — L0-04-a: uploads.expirar + periódico

__all__ = ["REGISTRO"]
