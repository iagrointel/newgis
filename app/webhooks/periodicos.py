"""Periódico de expurgo do log de entregas de webhook (item L7-08-a), somado à lista `PERIODICOS` do
worker na importação (o mesmo padrão de `app.uploads.periodicos`/`app.catalogo.periodicos`: o worker lê
a lista de `app/jobs/periodicos.py` ao sincronizar; nenhum arquivo do L0-05 é editado). Roda no inquilino
técnico `plataforma`; o DELETE em si atravessa inquilinos dentro de `plat.webhook_entregas_expurgar`
(SECURITY DEFINER com a mesma guarda de contexto de `plat.jobs_expurgar`, migração 20260909T0345)."""

from pydantic import BaseModel, Field

from app import limites
from app.jobs import periodicos as base
from app.jobs.registro import tarefa


class ExpurgarParametros(BaseModel):
    dias: int = Field(limites.WEBHOOK_ENTREGA_RETENCAO_DIAS, ge=1, le=3650)


@tarefa(
    nome="webhooks.expurgar",
    descricao="Expurgo do log de entregas de webhook (retenção padrão de 30 dias)",
    parametros=ExpurgarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=600,
    tentativas=1,
    perfil_minimo="admin",
)
def webhooks_expurgar(ctx, dias: int = limites.WEBHOOK_ENTREGA_RETENCAO_DIAS) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT plat.webhook_entregas_expurgar(%s) AS n", (int(dias),))
        n = cur.fetchone()["n"]
    ctx.progresso(100, f"{n} entregas expurgadas")
    return {"expurgadas": n}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("expurgo de entregas de webhook", "17 4 * * *", "webhooks.expurgar",
     {"dias": limites.WEBHOOK_ENTREGA_RETENCAO_DIAS}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
