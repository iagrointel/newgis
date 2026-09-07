"""Métricas Prometheus da plataforma (item L7-06-a-metricas-exporters). Análise / beta privado.

Contrato de cardinalidade (docs/OBSERVABILIDADE.md): o único rótulo por inquilino permitido em qualquer
métrica é `tenant` = `plat.tenant.id` (inteiro opaco), NUNCA o slug (`d_<slug>` é o nome do schema e pode
carregar o nome do cliente), NUNCA o nome, NUNCA o token nem o `token_id`. `rota` é o PADRÃO da rota
casada pelo roteador (`request.scope["route"].path`, ex. "/api/jobs/{job_id}") — nunca o caminho literal
com o UUID/id do recurso, que teria cardinalidade ilimitada (esse caminho literal já existe, redigido,
em `plat.log_acesso` via `app.auth.redigir.rota_redigida`; é uma coisa DIFERENTE e não deve ser usada
como rótulo de métrica). Requisição sem rota casada (404 de caminho arbitrário) usa o rótulo fixo
"outro" para não virar um vetor de estouro de cardinalidade por sondagem.

Cada processo (API :8150, worker :8153) mantém o SEU PRÓPRIO CollectorRegistry — não há estado
compartilhado entre processos; o Prometheus soma pelos rótulos `job`/`instance` do scrape, nunca por
uma métrica única "global" calculada aqui.
"""

from __future__ import annotations

import logging

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

log = logging.getLogger("plat.metricas")

REGISTRO = CollectorRegistry(auto_describe=True)

# ---------------------------------------------------------------- HTTP (API)
HTTP_REQUISICOES = Counter(
    "plat_http_requests_total",
    "Requisições HTTP concluídas, por padrão de rota, código de status e inquilino (tenant_id opaco)",
    ["rota", "status", "tenant"],
    registry=REGISTRO,
)
HTTP_DURACAO_SEGUNDOS = Histogram(
    "plat_http_request_duracao_segundos",
    "Duração da requisição HTTP, por padrão de rota",
    ["rota"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRO,
)

# ---------------------------------------------------------------- ladrilhos/COG (API — o que a API atende
# diretamente: autorização de COG por Range/nginx; Martin tem métrica NATIVA própria, ver docs/OBSERVABILIDADE.md)
TILES_REQUISICOES = Counter(
    "plat_tiles_requisicoes_total",
    "Requisições de ladrilho raster/COG autorizadas pela API, por origem e resultado",
    ["origem", "resultado"],
    registry=REGISTRO,
)

# ---------------------------------------------------------------- jobs (worker)
JOBS_PROCESSADOS = Counter(
    "plat_jobs_processados_total",
    "Jobs finalizados pelo worker, por tipo e estado final (vocabulário fechado da coluna plat.job.estado)",
    ["tipo", "estado_final"],
    registry=REGISTRO,
)


def rota_para_metrica(request) -> str:
    """Padrão de rota para rótulo de métrica (baixa cardinalidade). Nunca o caminho literal."""
    rota = request.scope.get("route")
    if rota is not None and getattr(rota, "path", None):
        return rota.path
    return "outro"


def registrar_requisicao(rota: str, status: int, tenant_id: int | None, duracao_s: float) -> None:
    tenant = str(tenant_id) if tenant_id is not None else "-"
    HTTP_REQUISICOES.labels(rota=rota, status=str(status), tenant=tenant).inc()
    HTTP_DURACAO_SEGUNDOS.labels(rota=rota).observe(duracao_s)


def registrar_tile(origem: str, resultado: str) -> None:
    TILES_REQUISICOES.labels(origem=origem, resultado=resultado).inc()


def registrar_job_processado(tipo: str, estado_final: str | None) -> None:
    JOBS_PROCESSADOS.labels(tipo=tipo, estado_final=estado_final or "desconhecido").inc()


class _ColetorFila(Collector):
    """plat.fila_estado() é SECURITY DEFINER e devolve um agregado CROSS-INQUILINO (contagem só, sem
    tenant_id, sem slug): zero cardinalidade nova. Consultado a cada scrape (o Prometheus da casa faz
    scrape a cada 15s; uma consulta agregada dessas não pesa no pool)."""

    def __init__(self, obter_cursor):
        self._obter_cursor = obter_cursor

    def collect(self):
        fila = GaugeMetricFamily(
            "plat_jobs_fila", "Fila de jobs por estado, agregada em todos os inquilinos", labels=["estado"]
        )
        workers = GaugeMetricFamily(
            "plat_jobs_workers_vivos", "Processos worker com heartbeat nos últimos 90 segundos"
        )
        linha = None
        try:
            with self._obter_cursor() as cur:
                cur.execute("SELECT * FROM plat.fila_estado()")
                linha = cur.fetchone()
        except Exception:  # noqa: BLE001 — a coleta de métrica nunca derruba o scrape nem a resposta
            log.exception("plat_jobs_fila: falha ao consultar plat.fila_estado()")
        fila.add_metric(["pendente"], linha["pendentes"] if linha else 0)
        fila.add_metric(["rodando"], linha["rodando"] if linha else 0)
        workers.add_metric([], linha["workers_vivos"] if linha else 0)
        yield fila
        yield workers


_coletor_fila_registrado = False


def registrar_coletor_fila(obter_cursor) -> None:
    """Chamado UMA vez, só pela API (o worker não registra: evitaria abrir um segundo pool de conexões
    só para expor o mesmo agregado duas vezes)."""
    global _coletor_fila_registrado
    if _coletor_fila_registrado:
        return
    REGISTRO.register(_ColetorFila(obter_cursor))
    _coletor_fila_registrado = True


def expor() -> tuple[bytes, str]:
    return generate_latest(REGISTRO), CONTENT_TYPE_LATEST
