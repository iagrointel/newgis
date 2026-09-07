"""Job de atualização de subrede (item L4-04-b-atualizar-e-exportar-subrede).

A hipótese do item diz `atualizar subrede = JOB`, e o motivo é medido: numa rede de cooperativa a atualização
percorre dezenas de milhares de elementos por subrede. Numa requisição HTTP isso ou estoura o tempo do proxy
ou prende um worker da API. Aqui vai para a fila (`app.jobs`), com progresso por subrede e cancelamento.

O trabalho em si é `subredes.atualizar_todas` — o MESMO caminho que a rota síncrona de uma subrede só usa
(`subredes.atualizar`). O job não tem lógica própria; ele é o transporte.

Registro no `REGISTRO` acontece na importação (feita por `app/jobs/tipos.py`), como nos demais módulos."""

from pydantic import BaseModel, Field

from app.jobs.registro import tarefa
from app.rede_utilidades import subredes


class AtualizarSubredesParametros(BaseModel):
    rede_id: str = Field(min_length=36, max_length=36)
    # `todas=False` (padrão) é a atualização INCREMENTAL: só as subredes sujas, inclusive as que a área suja
    # da última edição tocou. `todas=True` refaz a rede inteira (primeira carga, ou desconfiança do índice).
    todas: bool = False
    # `tier` restringe o lote a um tier da rede (código do pacote); vazio = todos.
    tier: str | None = Field(default=None, max_length=63)


@tarefa(
    nome="redes.subredes_atualizar",
    descricao="Atualiza as subredes sujas de uma rede de utilidades (traçado, nome nos elementos, "
              "propagação, linha agregada)",
    parametros=AtualizarSubredesParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: f"redes_subredes_atualizar:{p['rede_id']}",
    perfil_minimo="editor",
)
def redes_subredes_atualizar(ctx, rede_id: str, todas: bool = False, tier: str | None = None) -> dict:
    with ctx.db() as cur:
        return subredes.atualizar_todas(cur, ctx.tenant_id, rede_id, todas=todas, tier=tier,
                                        progresso=ctx.progresso)


__all__ = ["redes_subredes_atualizar"]
