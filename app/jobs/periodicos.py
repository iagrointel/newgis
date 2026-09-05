"""Periódicos da plataforma (ADR 0003 seção 7): declarados aqui, sincronizados para `plat.agenda` do inquilino
técnico `plataforma` na partida do worker. Este item entrega um: `jobs.expurgo` (job terminado há > 90 dias,
job_log > 30 dias, diretórios de trabalho órfãos > 7 dias)."""

import shutil
import time
from pathlib import Path

from pydantic import BaseModel, Field

from app.jobs.registro import tarefa

DIAS_JOB = 90
DIAS_LOG = 30
DIAS_DIRETORIO = 7


class ExpurgoParametros(BaseModel):
    dias_job: int = Field(DIAS_JOB, ge=1, le=3650)
    dias_log: int = Field(DIAS_LOG, ge=1, le=3650)
    dias_diretorio: int = Field(DIAS_DIRETORIO, ge=1, le=3650)


@tarefa(nome="jobs.expurgo", descricao="Expurgo: jobs terminados, linhas de log e diretórios de trabalho antigos",
        parametros=ExpurgoParametros, pesado=False, memoria_mb=256, timeout_s=1800, tentativas=1, perfil_minimo="admin")
def jobs_expurgo(ctx, dias_job: int = DIAS_JOB, dias_log: int = DIAS_LOG, dias_diretorio: int = DIAS_DIRETORIO) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.jobs_expurgar(%s, %s)", (dias_job, dias_log))
        r = cur.fetchone()
    rodando = {str(x) for x in (r["rodando"] or [])}
    ctx.progresso(50, f"banco: {r['jobs_apagados']} jobs e {r['logs_apagados']} linhas de log apagados")
    dir_jobs: Path = ctx.dir_trabalho.parent
    limite = time.time() - dias_diretorio * 86400
    apagados = 0
    for d in dir_jobs.iterdir():
        if not d.is_dir() or d.name in rodando or d.name == str(ctx.job_id):
            continue
        try:
            if d.stat().st_mtime < limite:
                shutil.rmtree(d, ignore_errors=True)
                apagados += 1
        except OSError as e:
            ctx.log("AVISO", f"não apagou {d.name}: {e}")
    ctx.progresso(100, f"diretórios apagados: {apagados}")
    return {"jobs_apagados": r["jobs_apagados"], "logs_apagados": r["logs_apagados"], "diretorios_apagados": apagados}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("expurgo diário", "30 3 * * *", "jobs.expurgo", {}),
]
