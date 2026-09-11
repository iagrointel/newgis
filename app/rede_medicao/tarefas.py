"""Tipo de job do módulo rede_medicao (item L4-13-integracao-telemetria), registrado pelo decorador @tarefa
do L0-05 e importado em app/jobs/tipos.py: `rede_medicao.particoes_criar` garante as partições mensais de
`plat.rede_medicao` alguns meses à frente. A agenda já nasce PAUSADA (migração 20260910T2351: ativa=false —
"ativa é do operador", mesmo texto de 004_jobs.sql); o mês corrente e o seguinte já existem desde a
migração, então rodar isto é só para quem quer a fila de partições mais larga antes da virada."""

from pydantic import BaseModel, Field

from app.jobs import periodicos as base
from app.jobs.registro import tarefa


class ParticoesCriarParametros(BaseModel):
    meses_adiante: int = Field(3, ge=1, le=24)


@tarefa(nome="rede_medicao.particoes_criar",
        descricao="Telemetria: garante as partições mensais de plat.rede_medicao alguns meses à frente",
        parametros=ParticoesCriarParametros, pesado=False, memoria_mb=256, timeout_s=120, tentativas=2,
        chave=lambda p: "rede_medicao_particoes_criar", perfil_minimo="admin")
def rede_medicao_particoes_criar(ctx, meses_adiante: int = 3) -> dict:
    criadas = []
    with ctx.db() as cur:
        for i in range(meses_adiante + 1):
            cur.execute(
                "SELECT plat.rede_medicao_particao_garantir("
                "(date_trunc('month', now()) + (%s || ' months')::interval)::date) AS nome",
                (i,),
            )
            criadas.append(cur.fetchone()["nome"])
    ctx.progresso(100, f"partições garantidas: {', '.join(criadas)}")
    return {"particoes": criadas}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("rede_medicao: criar partições futuras", "0 5 1 * *", "rede_medicao.particoes_criar", {}),
]
for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
