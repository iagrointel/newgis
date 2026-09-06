"""Periódicos da plataforma (ADR 0003 seção 7): declarados aqui, sincronizados para `plat.agenda` do inquilino
técnico `plataforma` na partida do worker. Este arquivo entrega três: `jobs.expurgo` (job terminado há > 90 dias,
job_log > 30 dias, marcadores e passos órfãos em plat_trabalho, diretórios de trabalho órfãos > 7 dias),
`jobs.sessoes_expurgar` (sessões vencidas e desafios 2FA expirados, `plat.sessoes_expurgar()` da 003, já existia
sem periódico que a chamasse) e `jobs.manutencao_analyze` (ANALYZE semanal nas tabelas centrais, `plat.
manutencao_analyze` da 026 — ANALYZE não pode rodar como plat_app, então a função é SECURITY DEFINER). Somados aos
dois do catálogo (`app/catalogo/periodicos.py`, que se soma a esta lista na importação), o total é 5 (achado do
testador T3: o portão L0-05-d exige 5 periódicos e só 3 estavam registrados)."""

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
        chave=lambda p: "sessoes_expurgar", perfil_minimo="admin")
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
        chave=lambda p: "manutencao_analyze", perfil_minimo="admin")
def jobs_manutencao_analyze(ctx, tabelas: list[str] | None = None) -> dict:
    with ctx.db() as cur:
        if tabelas:
            cur.execute("SELECT plat.manutencao_analyze(%s) AS feitas", (tabelas,))
        else:
            cur.execute("SELECT plat.manutencao_analyze() AS feitas")
        feitas = list(cur.fetchone()["feitas"] or [])
    ctx.progresso(100, f"ANALYZE em {len(feitas)} tabelas: {', '.join(feitas) or '(nenhuma)'}")
    return {"tabelas": feitas}


class UsoMedirParametros(BaseModel):
    dia: str | None = Field(
        None, description="dia medido (AAAA-MM-DD, UTC); default: hoje. Um por execução — para uma série "
        "retroativa, um job por dia (a cláusula '30 pontos' do portão é exercitada assim nos testes).")


@tarefa(nome="jobs.uso_medir",
        descricao="Medição de uso: um ponto de plat.uso_inquilino por inquilino ativo (banco, bucket, itens, "
                  "usuários ativos, jobs, requisições) e reconciliação de tenant.uso_bytes",
        parametros=UsoMedirParametros, pesado=False, memoria_mb=256, timeout_s=1800, tentativas=1,
        chave=lambda p: f"uso_medir:{p.get('dia') or 'hoje'}", perfil_minimo="admin")
def jobs_uso_medir(ctx, dia: str | None = None) -> dict:
    """Um ponto da série por inquilino. Os bytes do bucket vêm da Admin API do Garage (HTTP — por isso o SQL de
    plat.uso_medir recebe o número de fora); Garage fora do ar NÃO falha o job: o inquilino é medido sem a
    coluna bytes_bucket (NULL preserva a medição anterior, migração 20260906T2124) e o resultado declara."""
    from app import objetos  # adiado: o worker importa este módulo mesmo sem Garage configurado

    if dia:
        try:
            d = datetime.date.fromisoformat(dia)
        except ValueError as e:
            raise ValueError(f"dia deve ser AAAA-MM-DD, recebido {dia!r}") from e
    else:
        d = datetime.datetime.now(datetime.UTC).date()
    with ctx.db() as cur:
        cur.execute("SELECT plat.uso_tenants_ativos() AS id")
        tenants = [r["id"] for r in cur.fetchall()]
        cur.execute("SELECT * FROM plat.uso_buckets_listar()")
        buckets = {r["tenant_id"]: r["bucket_id"] for r in cur.fetchall()}
    admin = objetos._admin() if buckets else None
    medidos, sem_bucket, garage_falhou = 0, 0, 0
    for i, tenant_id in enumerate(tenants):
        bytes_bucket = None
        if tenant_id in buckets:
            try:
                bytes_bucket = int(admin.info_bucket(buckets[tenant_id]).get("bytes", 0))
            except Exception as e:  # noqa: BLE001 — Garage fora não derruba a medição dos demais
                ctx.log("AVISO", f"Garage não mediu o bucket do inquilino {tenant_id}: {str(e)[:200]}")
                garage_falhou += 1
        else:
            sem_bucket += 1
        with ctx.db() as cur:
            cur.execute("SELECT plat.uso_medir(%s, %s, %s) AS m", (tenant_id, d, bytes_bucket))
        medidos += 1
        if medidos % 10 == 0 or medidos == len(tenants):
            ctx.progresso(round(100 * medidos / max(1, len(tenants))), f"{medidos}/{len(tenants)} inquilinos")
    return {"dia": d.isoformat(), "inquilinos": medidos, "sem_bucket": sem_bucket, "garage_falhou": garage_falhou}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("expurgo diário", "30 3 * * *", "jobs.expurgo", {}),
    ("sessões vencidas", "0 * * * *", "jobs.sessoes_expurgar", {}),
    ("manutenção semanal", "0 4 * * 0", "jobs.manutencao_analyze", {}),
    ("medição de uso diária", "47 3 * * *", "jobs.uso_medir", {}),
]
