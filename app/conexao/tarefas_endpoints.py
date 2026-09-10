"""Job `endpoints_publicos.retestar` (item L6-02-m-catalogo-endpoints-brasil): semeia o catálogo de conectores
públicos (semente curada + registro do acervo, via `plat.endpoint_publico_semear`) e retesta TODAS as entradas
por HTTP com `endpoints_publicos.testar`, gravando cada resultado por `plat.endpoint_publico_registrar`. Roda no
inquilino técnico `plataforma` uma vez por semana (periódico em `app/conexao/periodicos.py`, decisão B12)
e pode ser enfileirado por um admin (`POST /api/jobs`). Trabalho de rede FORA do bloco `with ctx.db()` (regra do
ContextoJob: 60 s de idle_in_transaction). Entrada que falha sai da lista viva no mesmo instante (a API lista
`vivo = true`)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.conexao import endpoints_publicos
from app.jobs.registro import tarefa


class RetestarParametros(BaseModel):
    limite: int = Field(1000, ge=1, le=5000)
    semear: bool = True


@tarefa(
    nome="endpoints_publicos.retestar",
    descricao="Semeia e retesta por HTTP o catálogo de conectores públicos (entrada morta sai da lista)",
    parametros=RetestarParametros, pesado=False, memoria_mb=256, timeout_s=1800, tentativas=1,
    chave=lambda p: "endpoints_publicos_retestar", perfil_minimo="admin",
)
def endpoints_publicos_retestar(ctx, limite: int = 1000, semear: bool = True) -> dict:
    return retestar(ctx, limite=limite, semear=semear)


def retestar(ctx, limite: int = 1000, semear: bool = True) -> dict:
    """corpo do job, separado para os testes chamarem com um contexto mínimo (db/verificar/progresso)."""
    semeados = 0
    with ctx.db() as cur:
        if semear:
            semeados = endpoints_publicos.semear(cur)
        cur.execute(
            "SELECT id, tipo, url FROM plat.endpoint_publico ORDER BY testado_em NULLS FIRST, id LIMIT %s", (limite,)
        )
        entradas = cur.fetchall()
    vivos = mortos = 0
    for i, e in enumerate(entradas):
        ctx.verificar()
        r = endpoints_publicos.testar(e["url"], e["tipo"])  # rede fora da transação
        with ctx.db() as cur:
            endpoints_publicos.registrar(cur, e["id"], r)
        vivos += int(r.vivo)
        mortos += int(not r.vivo)
        ctx.progresso(int((i + 1) / max(len(entradas), 1) * 100), f"{i + 1}/{len(entradas)} testados")
    ctx.progresso(100, f"{len(entradas)} testados: {vivos} vivos, {mortos} fora do ar")
    return {"semeados": semeados, "testados": len(entradas), "vivos": vivos, "fora_do_ar": mortos}

