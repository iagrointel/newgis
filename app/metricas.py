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
import os
import subprocess

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

log = logging.getLogger("plat.metricas")

# Sem prazo declarado (nunca instalado, ou nunca passou): número alto de propósito — maior que
# qualquer limiar de alerta razoável (dias/horas), para que "nunca aconteceu" dispare, não silencie.
_SEM_PRAZO = 999_999

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


def _dias_restantes_certificado(caminho: str) -> float | None:
    """Dias até o certificado em `caminho` (PEM) vencer, via `openssl x509` (CLI já presente na casa;
    stdlib `ssl` não decodifica arquivo PEM solto sem socket vivo). `None` = não deu para ler (arquivo
    ausente/ilegível) — o item L7-06-b trata isso como cláusula não medida, nunca como "ok"."""
    try:
        saida = subprocess.run(  # noqa: S603,S607 — comando fixo, caminho vem de configuração local
            ["openssl", "x509", "-enddate", "-noout", "-in", caminho],
            capture_output=True, text=True, timeout=2, check=True,
        ).stdout.strip()
        # formato: "notAfter=Sep  7 17:00:00 2026 GMT"
        import datetime as _dt
        venc = _dt.datetime.strptime(saida.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=_dt.UTC)
        return (venc - _dt.datetime.now(_dt.UTC)).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001 — leitura de certificado nunca derruba o scrape
        log.exception("plat_certificado_dias_restantes: falha ao ler %s", caminho)
        return None


class _ColetorFila(Collector):
    """plat.fila_estado() é SECURITY DEFINER e devolve um agregado CROSS-INQUILINO (contagem só, sem
    tenant_id, sem slug): zero cardinalidade nova. Consultado a cada scrape (o Prometheus da casa faz
    scrape a cada 15s; uma consulta agregada dessas não pesa no pool). Mesmo coletor também expõe, pelo
    mesmo padrão (agregado, SECURITY DEFINER, sem cardinalidade nova), as famílias que o item
    L7-06-b-alertas precisa: idade do job mais antigo rodando, horas desde o último backup/drill, e —
    fora do banco — dias restantes do certificado configurado em `PLAT_CERTIFICADO_CAMINHO`."""

    def __init__(self, obter_cursor):
        self._obter_cursor = obter_cursor

    def collect(self):
        fila = GaugeMetricFamily(
            "plat_jobs_fila", "Fila de jobs por estado, agregada em todos os inquilinos", labels=["estado"]
        )
        workers = GaugeMetricFamily(
            "plat_jobs_workers_vivos", "Processos worker com heartbeat nos últimos 90 segundos"
        )
        mais_antigo = GaugeMetricFamily(
            "plat_jobs_rodando_mais_antigo_segundos",
            "Segundos desde que o job RODANDO há mais tempo começou (0 se não há nenhum rodando)",
        )
        backup = GaugeMetricFamily(
            "plat_backup_horas_desde_ultimo",
            "Horas desde a última execução OK de backup/drill (item L7-06-b); alto de propósito se nunca houve",
            labels=["tipo"],
        )
        duracao = GaugeMetricFamily(
            "plat_backup_ultima_duracao_segundos",
            "Duração da ÚLTIMA execução OK de backup/drill, em segundos (item L7-06-d)",
            labels=["tipo"],
        )
        tamanho = GaugeMetricFamily(
            "plat_backup_ultimo_bytes",
            "Tamanho do artefato da ÚLTIMA execução OK de backup/drill, em bytes (item L7-06-d)",
            labels=["tipo"],
        )
        usuarios = GaugeMetricFamily(
            "plat_usuarios_ativos_24h",
            "Usuários distintos com acesso registrado nas últimas 24 h, agregado em todos os "
            "inquilinos (sem rótulo por inquilino, usuário, IP ou token)",
        )
        bucket_cota = GaugeMetricFamily(
            "plat_bucket_cota_bytes", "Cota de armazenamento do inquilino, em bytes", labels=["tenant_id"]
        )
        bucket_usado = GaugeMetricFamily(
            "plat_bucket_usado_bytes", "Bytes guardados pelo inquilino (arquivos vivos)", labels=["tenant_id"]
        )
        bucket_objetos = GaugeMetricFamily(
            "plat_bucket_objetos", "Arquivos vivos do inquilino", labels=["tenant_id"]
        )
        dado_bytes = GaugeMetricFamily(
            "plat_tenant_dado_bytes",
            "Tamanho do schema de dado do inquilino, em bytes (substitui plat_tenant_schema_bytes do "
            "postgres_exporter, que a RLS de plat.tenant deixava sempre vazia)",
            labels=["tenant_id"],
        )
        linha = None
        antigo_s = 0
        horas_backup = _SEM_PRAZO
        horas_drill = _SEM_PRAZO
        ultimos = []
        ativos_24h = 0
        buckets = []
        dados = []
        try:
            with self._obter_cursor() as cur:
                cur.execute("SELECT * FROM plat.fila_estado()")
                linha = cur.fetchone()
                cur.execute("SELECT plat.fila_job_mais_antigo_rodando_segundos() AS v")
                antigo_s = cur.fetchone()["v"]
                cur.execute("SELECT plat.backup_horas_desde_ultimo('backup') AS v")
                r = cur.fetchone()["v"]
                horas_backup = float(r) if r is not None else _SEM_PRAZO
                cur.execute("SELECT plat.backup_horas_desde_ultimo('drill') AS v")
                r = cur.fetchone()["v"]
                horas_drill = float(r) if r is not None else _SEM_PRAZO
                cur.execute("SELECT * FROM plat.backup_ultimo()")
                ultimos = cur.fetchall()
                cur.execute("SELECT plat.usuarios_ativos_24h() AS v")
                ativos_24h = cur.fetchone()["v"] or 0
                cur.execute("SELECT * FROM plat.arquivo_bucket_uso()")
                buckets = cur.fetchall()
                cur.execute("SELECT * FROM plat.tenant_dado_bytes()")
                dados = cur.fetchall()
        except Exception:  # noqa: BLE001 — a coleta de métrica nunca derruba o scrape nem a resposta
            log.exception("coletor de fila/alertas: falha ao consultar o banco")
        fila.add_metric(["pendente"], linha["pendentes"] if linha else 0)
        fila.add_metric(["rodando"], linha["rodando"] if linha else 0)
        workers.add_metric([], linha["workers_vivos"] if linha else 0)
        mais_antigo.add_metric([], antigo_s)
        backup.add_metric(["backup"], horas_backup)
        backup.add_metric(["drill"], horas_drill)
        yield fila
        yield workers
        for u in ultimos:
            # duracao_s/bytes podem ser nulos (execução registrada por rotina antiga, sem medida):
            # nesse caso a SÉRIE não é criada, para o painel mostrar ausência em vez de zero falso.
            if u["duracao_s"] is not None:
                duracao.add_metric([u["tipo"]], float(u["duracao_s"]))
            if u["bytes"] is not None:
                tamanho.add_metric([u["tipo"]], float(u["bytes"]))
        usuarios.add_metric([], ativos_24h)
        for b in buckets:
            tid = str(b["tenant_id"])
            bucket_cota.add_metric([tid], float(b["cota_bytes"]))
            bucket_usado.add_metric([tid], float(b["usado_bytes"]))
            bucket_objetos.add_metric([tid], float(b["objetos"]))
        for d in dados:
            dado_bytes.add_metric([str(d["tenant_id"])], float(d["bytes"]))
        yield mais_antigo
        yield backup
        yield duracao
        yield tamanho
        yield usuarios
        yield bucket_cota
        yield bucket_usado
        yield bucket_objetos
        yield dado_bytes

        caminho_cert = os.environ.get("PLAT_CERTIFICADO_CAMINHO")
        if caminho_cert:
            dias = _dias_restantes_certificado(caminho_cert)
            certificado = GaugeMetricFamily(
                "plat_certificado_dias_restantes",
                "Dias até o certificado TLS configurado vencer (a família só existe se "
                "PLAT_CERTIFICADO_CAMINHO estiver definido)",
            )
            certificado.add_metric([], dias if dias is not None else _SEM_PRAZO)
            yield certificado


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
