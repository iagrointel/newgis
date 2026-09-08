"""Tipos de job do ciclo de vida das imagens (item L1-01-i), registrados pelo decorador @tarefa e importados
em app/jobs/tipos.py: `imagens.raster_apagar_objetos` (somente_sistema: enfileirado pela rota de exclusão
com agendado_para = agora + RASTER_LIXEIRA_DIAS) e `imagens.raster_gc` (somente_sistema: periódico semanal
e CLI `plat raster gc`). Importar este módulo também soma o periódico semanal à lista do worker
(app/imagens/periodicos.py). Os corpos das tarefas vivem em app/imagens/ciclo_vida.py."""

from app.imagens import ciclo_vida
from app.imagens.ciclo_vida import LIMITE_RELATORIO_CHAVES, ApagarObjetosParametros, ColetaParametros
from app.jobs.registro import tarefa

__all__ = ["ApagarObjetosParametros", "ColetaParametros"]


@tarefa(
    nome="imagens.raster_apagar_objetos",
    descricao="Apaga os objetos (COGs e anexos) do balde de um item de imagem cuja retenção na lixeira venceu",
    parametros=ApagarObjetosParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=1800,
    tentativas=3,
    chave=lambda p: f"raster_apagar_objetos:{p['item_id']}",
    perfil_minimo="editor",
    somente_sistema=True,
)
def raster_apagar_objetos(ctx, item_id: str) -> dict:
    return ciclo_vida.apagar_objetos(ctx, item_id)


@tarefa(
    nome="imagens.raster_gc",
    descricao="Coleta de lixo das imagens: relatório de objetos órfãos, itens quebrados e lixeira vencida",
    parametros=ColetaParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: "raster_gc",
    perfil_minimo="admin",
    somente_sistema=True,
)
def raster_gc(ctx, limite_chaves: int = LIMITE_RELATORIO_CHAVES) -> dict:
    return ciclo_vida.coleta_de_lixo(ctx, limite_chaves)
