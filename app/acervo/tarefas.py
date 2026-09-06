"""Verificação periódica de FRESCOR das camadas do acervo da casa (item L6-01-h-frescor-verificacao;
migração 20260906T1617_acervo_frescor.sql). Reaproveita o relógio do L0-05 no mesmo molde de
`app/conexao/tarefas.py` (L6-02-l) e de `app/catalogo/periodicos.py`: um tipo registrado por `@tarefa`, um
periódico acrescentado à lista do worker por um módulo PRÓPRIO (`app/acervo/periodicos.py`) — nenhum arquivo
do L0-05 é editado.

O que a rodada faz, por camada EXPOSTA do registro (`plat.acervo_camada`, item L6-01-a):

  1. `COUNT(*)` EXATO sob `SET LOCAL statement_timeout` de 25 s (o prazo por tabela que a casa já usa em
     `contagem2.py` e em `scripts/acervo_sync.py`). Estourar o prazo é um ESTADO PRÓPRIO
     (`nao_contado_no_prazo`), nunca zero e nunca `reltuples`: a estimativa não entra no histórico, porque foi
     exatamente a diferença entre estimativa e contagem que revelou as duas tabelas fantasma da casa em 01/09.
  2. Hash de conteúdo, quando a camada tem comando de reexecução registrado e a contagem coube no teto de
     `LIMITE_HASH_LINHAS` linhas. O hash é o da função `plat.acervo_camada_hash` (soma de linhas ordenadas,
     documentada na migração), NÃO o `COPY ... | sha256sum` que a casa guarda em `acervo.fonte.sha256_cmd`:
     medido em 06/09/2026, a maioria daqueles comandos ainda é um MODELO com `<schema>.<tabela>` por preencher
     e os executáveis são canos de shell com `sudo`, que o worker não tem e nunca deve ter. Executar texto de
     shell vindo de uma tabela seria execução de comando arbitrário; o que se compara aqui é o hash desta
     rodada contra o da rodada anterior — divergiu, o conteúdo mudou.
  3. Teste HTTP dos endereços confirmados das fontes que têm camada exposta, pelo `buscar_seguro` de
     `app/conexao/seguranca.py` (defesa de SSRF, sem seguir redirecionamento às cegas), com `User-Agent` que
     identifica a plataforma e um TETO POR RODADA (`LIMITE_ENDPOINTS`): a verificação é de dezenas de
     endereços, nunca uma varredura em massa contra órgão público.

Tudo é gravado em `plat` pelas funções SECURITY DEFINER da migração. ⛔ `acervo.*` é só leitura: nenhuma
linha deste arquivo escreve lá.

Trinco: o tipo roda com `chave=None` DE PROPÓSITO. A `chave` de `plat.job` é global (índice `ix_job_chave` da
004 e o casamento `r.chave = j.chave` do despachante da 006 não têm `tenant_id`), então chave constante deixa
qualquer inquilino ocupar o trinco do periódico da plataforma — foi por isso que o item L0-05-d-periodicos foi
refutado em 06/09. A exclusão mútua desta rodada mora em `plat.acervo_frescor_execucao`, num índice único
parcial POR `tenant_id`, e as funções ainda exigem o inquilino técnico `plataforma`. `somente_sistema=True`
fecha a porta de `POST /api/jobs`.
"""

import datetime
import time

import psycopg2
import psycopg2.errors
from pydantic import BaseModel, Field

from app.jobs.registro import tarefa
from app.limites import CONEXAO_CONECTAR_TIMEOUT_S, CONEXAO_LER_TIMEOUT_S

TIMEOUT_CONTAGEM_MS = 25_000       # prazo por tabela, igual ao contagem2.py da casa
TIMEOUT_HASH_MS = 25_000
LIMITE_HASH_LINHAS = 1_000_000     # acima disto o hash de conteúdo não cabe no prazo: fica declarado, não estimado
LIMITE_CAMADAS = 1_000
LIMITE_ENDPOINTS = 40              # dezenas por rodada, nunca varredura em massa contra órgão público
INTERVALO_RECHECAGEM_DIAS = 6      # o periódico é semanal; 6 dias evita pular uma semana por atraso de minutos
PRAZO_TOTAL_S = 1_740.0            # 29 min, com folga sob o portão de 30 min
MANTER_HISTORICO = 12              # portão: histórico de 12 verificações por camada
AGENTE = "plat-acervo-frescor/1.0 (verificacao de frescor do acervo; plataforma interna)"


class FrescorParametros(BaseModel):
    limite_camadas: int = Field(LIMITE_CAMADAS, ge=1, le=10_000)
    limite_endpoints: int = Field(LIMITE_ENDPOINTS, ge=0, le=200)
    intervalo_dias: int = Field(INTERVALO_RECHECAGEM_DIAS, ge=0, le=365)
    manter: int = Field(MANTER_HISTORICO, ge=1, le=100)
    prazo_s: float = Field(PRAZO_TOTAL_S, ge=1.0, le=3_600.0)
    timeout_contagem_ms: int = Field(TIMEOUT_CONTAGEM_MS, ge=100, le=120_000)


def _contar(ctx, camada_id: str, timeout_ms: int) -> tuple[str, int | None]:
    """COUNT(*) exato; o prazo é armado no CLIENTE (`SET LOCAL`) porque o Postgres arma o cronômetro de
    `statement_timeout` no início do comando de cliente — um SET dentro da função não valeria para a própria
    chamada em curso. Estouro devolve ('nao_contado_no_prazo', None), nunca zero."""
    try:
        with ctx.db() as cur:
            cur.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
            cur.execute("SELECT plat.acervo_camada_contar(%s) AS n", (camada_id,))
            return "contado", int(cur.fetchone()["n"])
    except psycopg2.errors.QueryCanceled:
        return "nao_contado_no_prazo", None
    except psycopg2.Error as e:
        ctx.log("AVISO", f"contagem de {camada_id} falhou: {str(e).strip()[:200]}")
        return "erro", None


def _hash(ctx, camada_id: str, comando: str | None, linhas: int | None,
          hash_anterior: str | None) -> tuple[str, str | None]:
    if not (comando or "").strip():
        return "sem_comando", None
    if linhas is None:
        return "nao_recalculado_sem_contagem", None
    if linhas > LIMITE_HASH_LINHAS:
        return "nao_recalculado_tabela_grande", None
    try:
        with ctx.db() as cur:
            cur.execute("SET LOCAL statement_timeout = %s", (TIMEOUT_HASH_MS,))
            cur.execute("SELECT plat.acervo_camada_hash(%s) AS h", (camada_id,))
            valor = cur.fetchone()["h"]
    except psycopg2.errors.QueryCanceled:
        return "nao_recalculado_tabela_grande", None
    except psycopg2.Error as e:
        ctx.log("AVISO", f"hash de {camada_id} falhou: {str(e).strip()[:200]}")
        return "erro", None
    if hash_anterior is not None and valor != hash_anterior:
        return "divergente", valor
    return "recalculado", valor


def _testar_endpoints(ctx, execucao: int, limite: int, intervalo: datetime.timedelta,
                      manter: int) -> tuple[int, int]:
    """Teste HTTP dos endereços confirmados das fontes com camada exposta. Devolve (testados, responderam)."""
    from app.conexao import seguranca

    if limite <= 0:
        return 0, 0
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.acervo_frescor_endpoints(%s, %s)", (intervalo, limite))
        alvos = cur.fetchall()
    responderam = 0
    for alvo in alvos:
        ctx.verificar()
        r = seguranca.buscar_seguro(
            alvo["url"], metodo="GET", timeout_conectar=CONEXAO_CONECTAR_TIMEOUT_S,
            timeout_ler=CONEXAO_LER_TIMEOUT_S, cabecalhos={"User-Agent": AGENTE},
        )
        if r.ok:
            responderam += 1
        with ctx.db() as cur:
            cur.execute(
                "SELECT plat.acervo_frescor_registrar_endpoint(%s, %s, %s, %s, %s, %s, %s, %s)",
                (execucao, alvo["fonte_id"], alvo["url"], r.ok, r.status, r.mensagem, r.latencia_ms, manter),
            )
    return len(alvos), responderam


@tarefa(
    nome="acervo.frescor_verificar",
    descricao="Frescor do acervo: COUNT(*) com prazo, hash de conteúdo e teste HTTP dos endereços das camadas expostas",
    parametros=FrescorParametros, pesado=False, memoria_mb=256, timeout_s=2400, tentativas=1,
    chave=None, perfil_minimo="admin", somente_sistema=True,
)
def acervo_frescor_verificar(ctx, limite_camadas: int = LIMITE_CAMADAS, limite_endpoints: int = LIMITE_ENDPOINTS,
                             intervalo_dias: int = INTERVALO_RECHECAGEM_DIAS, manter: int = MANTER_HISTORICO,
                             prazo_s: float = PRAZO_TOTAL_S,
                             timeout_contagem_ms: int = TIMEOUT_CONTAGEM_MS) -> dict:
    inicio = time.monotonic()
    intervalo = datetime.timedelta(days=intervalo_dias)
    with ctx.db() as cur:
        cur.execute("SELECT plat.acervo_frescor_abrir() AS id")
        execucao = int(cur.fetchone()["id"])
    try:
        with ctx.db() as cur:
            cur.execute("SELECT * FROM plat.acervo_frescor_candidatas(%s, %s)", (intervalo, limite_camadas))
            candidatas = cur.fetchall()
        verificadas = nao_contadas = mudancas = divergencias = 0
        historico_minimo = None
        for i, c in enumerate(candidatas):
            ctx.verificar()
            if time.monotonic() - inicio > prazo_s:
                ctx.log("AVISO", f"prazo de {prazo_s:.0f}s atingido com {len(candidatas) - i} camadas por verificar")
                break
            t0 = time.monotonic()
            estado, linhas = _contar(ctx, c["acervo_camada_id"], timeout_contagem_ms)
            hash_estado, hash_valor = _hash(ctx, c["acervo_camada_id"], c["comando_reexecucao"], linhas,
                                            c["hash_anterior"])
            duracao = int((time.monotonic() - t0) * 1000)
            with ctx.db() as cur:
                cur.execute(
                    "SELECT * FROM plat.acervo_frescor_registrar_camada(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (execucao, c["acervo_camada_id"], estado, linhas, hash_estado, hash_valor,
                     c["comando_reexecucao"], duracao, manter),
                )
                r = cur.fetchone()
            verificadas += 1
            nao_contadas += int(estado != "contado")
            mudancas += int(bool(r["mudanca_relevante"]))
            divergencias += int(hash_estado == "divergente")
            historico_minimo = r["historico"] if historico_minimo is None else min(historico_minimo, r["historico"])
            ctx.progresso(int((i + 1) / max(len(candidatas), 1) * 90),
                          f"{i + 1}/{len(candidatas)} camadas verificadas")
        testados, responderam = _testar_endpoints(ctx, execucao, limite_endpoints, intervalo, manter)
    finally:
        with ctx.db() as cur:
            cur.execute("SELECT plat.acervo_frescor_fechar(%s)", (execucao,))
    duracao_total_s = time.monotonic() - inicio
    ctx.progresso(100, f"{verificadas} camadas, {testados} endereços, {mudancas} mudanças acima de 5 %")
    return {
        "execucao_id": execucao, "camadas_candidatas": len(candidatas), "camadas_verificadas": verificadas,
        "camadas_nao_contadas": nao_contadas, "mudancas": mudancas, "hashes_divergentes": divergencias,
        "endpoints_testados": testados, "endpoints_responderam": responderam,
        "historico_minimo": historico_minimo, "duracao_s": round(duracao_total_s, 1),
    }


from app.acervo import periodicos  # noqa: E402,F401 — importar acrescenta o periódico semanal à lista do worker
