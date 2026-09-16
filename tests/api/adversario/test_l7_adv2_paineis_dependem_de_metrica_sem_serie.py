"""Adversário de linha L7 operação (parte 2) — item `L7-06-d-paineis`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`; achado transversal nº1, herdado do laudo
parte 1: `app/metricas.py::registrar_requisicao/registrar_tile/registrar_job_processado` seguem sem
NENHUM chamador fora do próprio módulo).

O painel `deploy/grafana/paineis/plat-visao-geral.json` tem 10 quadros; o quadro "10. Jobs concluídos
por estado final (1 h)" consulta `sum by (estado_final) (increase(plat_jobs_processados_total[1h]))`
— e `plat_jobs_processados_total` nunca ganha uma série no Prometheus da trilha viva (confirmado por
`GET /api/v1/query?query=plat_jobs_processados_total` → `"result":[]`), porque
`registrar_job_processado()` nunca é chamada por código nenhum. Esse quadro mostra "No data" sempre,
contradizendo a cláusula literal do portão ("os 5 painéis carregam sem 'No data' contra homologação
com carga curta"). O quadro "8. Respostas 5xx (15 min)" usa `plat_http_requests_total{status=~"5.."}
... or vector(0)` — o `or vector(0)` esconde a métrica morta atrás de um zero permanente, o que evita
"No data" mas faz o painel mentir por omissão (5xx real nunca aparece, porque o contador nunca
incrementa)."""

from __future__ import annotations

import json
from pathlib import Path

import urllib.parse
import urllib.request

import pytest

RAIZ = Path(__file__).resolve().parents[3]
PAINEL_VISAO_GERAL = RAIZ / "deploy" / "grafana" / "paineis" / "plat-visao-geral.json"
PROMETHEUS = "http://127.0.0.1:9090"

METRICAS_SEM_CHAMADOR = (
    "plat_http_requests_total",
    "plat_tiles_requisicoes_total",
    "plat_jobs_processados_total",
    "plat_http_request_duracao_segundos",
)


def _expressoes_do_painel(caminho: Path) -> list[str]:
    dado = json.loads(caminho.read_text(encoding="utf-8"))
    expressoes = []

    def _andar(objeto):
        if isinstance(objeto, dict):
            if "expr" in objeto:
                expressoes.append(objeto["expr"])
            for valor in objeto.values():
                _andar(valor)
        elif isinstance(objeto, list):
            for item in objeto:
                _andar(item)

    _andar(dado)
    return expressoes


@pytest.mark.xfail(
    strict=True,
    reason=(
        "deploy/grafana/paineis/plat-visao-geral.json não usa nenhuma das métricas HTTP/tiles/jobs "
        "que app/metricas.py declara mas nunca incrementa — na verdade usa pelo menos duas delas "
        "(plat_http_requests_total no quadro 8, plat_jobs_processados_total no quadro 10). Item "
        "L7-06-d-paineis, achado transversal nº1 herdado."
    ),
)
def test_painel_visao_geral_evita_as_metricas_sem_chamador():
    expressoes = " ".join(_expressoes_do_painel(PAINEL_VISAO_GERAL))
    usadas = [m for m in METRICAS_SEM_CHAMADOR if m in expressoes]
    assert not usadas, f"quadros do painel usam métrica(s) sem nenhum chamador: {usadas}"


def _prometheus_tem_serie(query: str) -> bool:
    url = f"{PROMETHEUS}/api/v1/query?query={urllib.parse.quote(query)}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        corpo = json.loads(resp.read())
    return bool(corpo.get("data", {}).get("result"))


def _prometheus_vivo() -> bool:
    try:
        urllib.request.urlopen(f"{PROMETHEUS}/-/ready", timeout=3)
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _prometheus_vivo(), reason="Prometheus da trilha não está acessível agora")
@pytest.mark.xfail(
    strict=True,
    reason=(
        "GET /api/v1/query?query=plat_jobs_processados_total no Prometheus da trilha viva devolve "
        "result=[] — o quadro 10 do painel Visão geral ('Jobs concluídos por estado final') mostra "
        "'No data' sempre, contradizendo a cláusula literal do portão. Item L7-06-d-paineis."
    ),
)
def test_metrica_do_quadro_jobs_tem_serie_no_prometheus_vivo():
    assert _prometheus_tem_serie("plat_jobs_processados_total"), (
        "plat_jobs_processados_total sem série no Prometheus — o quadro 'Jobs concluídos' está sempre "
        "em 'No data'"
    )
