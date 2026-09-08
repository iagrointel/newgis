"""Periódicos da plataforma (ADR 0003 seção 7): declarados aqui, sincronizados para `plat.agenda` do inquilino
técnico `plataforma` na partida do worker. Este arquivo entrega três: `jobs.expurgo` (job terminado há > 90 dias,
job_log > 30 dias, marcadores e passos órfãos em plat_trabalho, diretórios de trabalho órfãos > 7 dias),
`jobs.sessoes_expurgar` (sessões vencidas e desafios 2FA expirados, `plat.sessoes_expurgar()` da 003, já existia
sem periódico que a chamasse) e `jobs.manutencao_analyze` (ANALYZE semanal nas tabelas centrais, `plat.
manutencao_analyze` da 026 — ANALYZE não pode rodar como plat_app, então a função é SECURITY DEFINER). As duas
chaves de trinco que só a plataforma usa vivem no espaço de nome reservado `sys:` (app/limites.py): o gatilho
plat.job_chave_reservada recusa essa chave a trabalho de inquilino comum criado fora de agenda, e a partir da
migração 20260906T1615 o trinco é comparado por (inquilino, chave) — um inquilino não congela o outro. Somados aos
dois do catálogo (`app/catalogo/periodicos.py`, que se soma a esta lista na importação), o total é 5 (achado do
testador T3: o portão L0-05-d exige 5 periódicos e só 3 estavam registrados)."""

import shutil
import time
from pathlib import Path

from pydantic import BaseModel, Field

from app.jobs.registro import tarefa
from app.limites import CHAVE_RESERVADA

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
    ctx.progresso(50, f"banco: {r['jobs_apagados']} jobs, {r['logs_apagados']} linhas de log, "
                      f"{r['marcadores_apagados']} marcadores e {r['passos_apagados']} passos órfãos apagados")
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
    return {"jobs_apagados": r["jobs_apagados"], "logs_apagados": r["logs_apagados"],
            "marcadores_apagados": r["marcadores_apagados"], "passos_apagados": r["passos_apagados"],
            "diretorios_apagados": apagados}


class SessoesExpurgarParametros(BaseModel):
    """Sem parâmetros: `plat.sessoes_expurgar()` não recebe argumento (roda sem contexto de inquilino, seção 3
    da 003 — a mesma sessão pode ter sido criada em qualquer inquilino)."""


@tarefa(nome="jobs.sessoes_expurgar",
        descricao="Expurgo: sessões vencidas (expira_em ou 24h sem uso) e desafios 2FA expirados, todos os inquilinos",
        parametros=SessoesExpurgarParametros, pesado=False, memoria_mb=256, timeout_s=120, tentativas=1,
        chave=lambda p: f"{CHAVE_RESERVADA}sessoes_expurgar", perfil_minimo="admin")
def jobs_sessoes_expurgar(ctx) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT plat.sessoes_expurgar() AS n")
        n = cur.fetchone()["n"]
    ctx.progresso(100, f"{n} sessões vencidas apagadas")
    return {"sessoes_apagadas": n}


TABELAS_ANALYZE = ("job", "job_log", "item", "item_versao", "agenda", "usuario", "evento")


class ManutencaoAnalyzeParametros(BaseModel):
    tabelas: list[str] | None = Field(None, max_length=50, description="default: as tabelas centrais do plat")


@tarefa(nome="jobs.manutencao_analyze",
        descricao="Manutenção: ANALYZE nas tabelas centrais da plataforma (estimativas do planejador em dia)",
        parametros=ManutencaoAnalyzeParametros, pesado=False, memoria_mb=256, timeout_s=1800, tentativas=1,
        chave=lambda p: f"{CHAVE_RESERVADA}manutencao_analyze", perfil_minimo="admin")
def jobs_manutencao_analyze(ctx, tabelas: list[str] | None = None) -> dict:
    with ctx.db() as cur:
        if tabelas:
            cur.execute("SELECT plat.manutencao_analyze(%s) AS feitas", (tabelas,))
        else:
            cur.execute("SELECT plat.manutencao_analyze() AS feitas")
        feitas = list(cur.fetchone()["feitas"] or [])
    ctx.progresso(100, f"ANALYZE em {len(feitas)} tabelas: {', '.join(feitas) or '(nenhuma)'}")
    return {"tabelas": feitas}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("expurgo diário", "30 3 * * *", "jobs.expurgo", {}),
    ("sessões vencidas", "0 * * * *", "jobs.sessoes_expurgar", {}),
    ("manutenção semanal", "0 4 * * 0", "jobs.manutencao_analyze", {}),
]
