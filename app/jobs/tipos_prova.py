"""Tipos de diagnóstico do produto (ADR 0003 seções 3 e 12). `prova.progresso` é a tarefa de referência da
plataforma: N passos com progresso, log e efeito parcial em plat_trabalho.passos (apagado na limpeza, inclusive em
Cancelado; uma tabela por job custaria 0,5-1 s de DDL neste servidor), marcador gravado só no último passo
(prova "nunca concluído sem execução inteira"). Os demais exercitam cada caminho de morte da seção 6: memória,
falha comum/definitiva, tarefa que ignora o cancelamento, job pesado, tempo esgotado. Todos com perfil_minimo=editor."""

import uuid

from pydantic import BaseModel, Field

from app.jobs.registro import FalhaDefinitiva, tarefa


class ProgressoParametros(BaseModel):
    duracao_s: int = Field(300, ge=0, le=3600, description="duração total em segundos")
    passos: int = Field(60, ge=1, le=1000, description="número de passos com progresso")
    chave: str | None = Field(None, max_length=200, description="lock lógico: mesma chave nunca roda em paralelo")


@tarefa(nome="prova.progresso", descricao="Diagnóstico: N passos com progresso, log e marcador de fim",
        parametros=ProgressoParametros, pesado=False, memoria_mb=256, timeout_s=7200, tentativas=3,
        chave=lambda p: p.get("chave"), versao=1)
def prova_progresso(ctx, duracao_s: int = 300, passos: int = 60, chave: str | None = None) -> dict:
    jid = str(ctx.job_id)
    with ctx.db() as cur:  # recomeço do zero: nada de execução anterior sobra (reinício = reexecução)
        cur.execute("DELETE FROM plat_trabalho.passos WHERE job_id = %s", (jid,))
    ctx.log("INFO", f"início: {passos} passos em {duracao_s} s; efeito parcial em plat_trabalho.passos; "
                    f"tentativa {ctx.tentativa}")
    intervalo = duracao_s / passos
    cada = max(1, passos // 10)
    try:
        for i in range(1, passos + 1):
            ctx.dormir(intervalo)
            with ctx.db() as cur:
                cur.execute("INSERT INTO plat_trabalho.passos(job_id, passo) VALUES (%s, %s)", (jid, i))
            ctx.progresso(i * 100 // passos, f"passo {i} de {passos}")
            if i % cada == 0 or i == passos:
                ctx.log("INFO", f"passo {i} de {passos}")
        marcador = uuid.uuid4()
        with ctx.db() as cur:
            cur.execute("INSERT INTO plat_trabalho.marcadores(job_id, marcador) VALUES (%s, %s)",
                        (str(ctx.job_id), str(marcador)))
        return {"passos": passos, "duracao_s": duracao_s, "marcador": str(marcador)}
    finally:
        with ctx.db() as cur:
            cur.execute("DELETE FROM plat_trabalho.passos WHERE job_id = %s", (jid,))


class MemoriaParametros(BaseModel):
    mb: int = Field(600, ge=1, le=8192)


@tarefa(nome="prova.memoria", descricao="Diagnóstico: aloca N MB para provar o limite de memória do filho",
        parametros=MemoriaParametros, pesado=False, memoria_mb=256, timeout_s=120, tentativas=1)
def prova_memoria(ctx, mb: int = 600) -> dict:
    ctx.log("INFO", f"alocando {mb} MB sob RLIMIT_DATA")
    bloco = bytearray(mb * 1024 * 1024)
    bloco[::4096] = b"\x01" * len(bloco[::4096])
    return {"mb": mb, "alocado": True}


class FalhaParametros(BaseModel):
    definitiva: bool = False


@tarefa(nome="prova.falha", descricao="Diagnóstico: levanta exceção comum (retenta 2/4/8 s) ou FalhaDefinitiva",
        parametros=FalhaParametros, pesado=False, memoria_mb=256, timeout_s=60, tentativas=3)
def prova_falha(ctx, definitiva: bool = False) -> dict:
    ctx.log("INFO", f"tentativa {ctx.tentativa}: vai falhar ({'definitiva' if definitiva else 'comum'})")
    if definitiva:
        raise FalhaDefinitiva("falha definitiva de prova")
    raise RuntimeError(f"falha comum de prova na tentativa {ctx.tentativa}")


class DuracaoParametros(BaseModel):
    duracao_s: int = Field(120, ge=1, le=3600)


@tarefa(nome="prova.ignora_cancelamento", descricao="Diagnóstico: laço que nunca lê a flag de cancelamento",
        parametros=DuracaoParametros, pesado=False, memoria_mb=256, timeout_s=600, tentativas=1)
def prova_ignora_cancelamento(ctx, duracao_s: int = 120) -> dict:
    import time

    ctx.log("INFO", f"dormindo {duracao_s} s sem checar cancelamento")
    fim = time.monotonic() + duracao_s
    while time.monotonic() < fim:
        time.sleep(0.5)  # nunca chama progresso()/cancelado(): só SIGKILL o encerra
    return {"duracao_s": duracao_s}


class PesadoParametros(BaseModel):
    duracao_s: int = Field(20, ge=1, le=3600)


@tarefa(nome="prova.pesado", descricao="Diagnóstico: job pesado (só 1 por vez na máquina)",
        parametros=PesadoParametros, pesado=True, memoria_mb=512, timeout_s=3600, tentativas=1)
def prova_pesado(ctx, duracao_s: int = 20) -> dict:
    passos = max(1, duracao_s)
    for i in range(1, passos + 1):
        ctx.dormir(duracao_s / passos)
        ctx.progresso(i * 100 // passos, f"pesado {i}/{passos}")
    return {"duracao_s": duracao_s}


@tarefa(nome="prova.tempo_esgotado", descricao="Diagnóstico: timeout_s=5 com tarefa mais longa (tempo esgotado)",
        parametros=DuracaoParametros, pesado=False, memoria_mb=256, timeout_s=5, tentativas=1)
def prova_tempo_esgotado(ctx, duracao_s: int = 120) -> dict:
    passos = max(1, duracao_s)
    for i in range(1, passos + 1):
        ctx.dormir(1)
        ctx.progresso(i * 100 // passos, f"segundo {i} de {duracao_s}")
    return {"duracao_s": duracao_s}
