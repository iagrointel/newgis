"""Periódico do retrato operacional (item L0-06-e-status): a cada 5 minutos grava em `plat.status_amostra` o
estado de cada serviço, que é o que a página /status usa para desenhar 90 dias de histórico e calcular o
percentual de disponibilidade do mês.

A amostra sai do MESMO `retrato()` que a página serve — se a página mostra `worker: erro`, é isso que entra no
histórico. Sem `chave` de deduplicação de propósito: o job é curto e barato, e chave de periódico da plataforma
é assunto de outro item (espaço de nome reservado)."""

import json

from pydantic import BaseModel, Field

from app import status
from app.jobs import periodicos as base
from app.jobs.registro import tarefa

DIAS_RETENCAO = 90


class AmostrarParametros(BaseModel):
    dias_retencao: int = Field(DIAS_RETENCAO, ge=1, le=3650, description="idade máxima de uma amostra guardada")


@tarefa(nome="status.amostrar",
        descricao="Retrato operacional: grava o estado de cada serviço em plat.status_amostra (histórico 90 dias)",
        parametros=AmostrarParametros, pesado=False, memoria_mb=256, timeout_s=120, tentativas=1,
        perfil_minimo="admin")
def status_amostrar(ctx, dias_retencao: int = DIAS_RETENCAO) -> dict:
    retrato = status.retrato()
    amostras = [{"servico": nome, "estado": s["estado"]} for nome, s in retrato["servicos"].items()]
    with ctx.db() as cur:
        cur.execute("SELECT plat.status_amostrar(%s::jsonb, %s) AS n", (json.dumps(amostras), dias_retencao))
        n = cur.fetchone()["n"]
    ctx.progresso(100, f"{n} amostras gravadas; estado geral {retrato['estado']}")
    return {"amostras": n, "estado": retrato["estado"],
            "servicos": {nome: s["estado"] for nome, s in retrato["servicos"].items()}}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("retrato operacional", "*/5 * * * *", "status.amostrar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
