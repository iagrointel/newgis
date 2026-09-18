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

import ast
import json
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
PAINEL_VISAO_GERAL = RAIZ / "deploy" / "grafana" / "paineis" / "plat-visao-geral.json"
PROMETHEUS = "http://127.0.0.1:9090"
APP = RAIZ / "app"

# As quatro famílias que o laudo acusou de não ter chamador nenhum. A conferência abaixo não pergunta
# mais se o painel as EVITA (evitar seria esconder o quadro), e sim se cada uma delas, estando no
# painel, tem de fato quem a incremente.
METRICAS_ACUSADAS = (
    "plat_http_requests_total",
    "plat_tiles_requisicoes_total",
    "plat_jobs_processados_total",
    "plat_http_request_duracao_segundos",
)


# nome da métrica Prometheus -> constante que a declara em app/metricas.py
CONSTANTE_DA_METRICA = {
    "plat_http_requests_total": "HTTP_REQUISICOES",
    "plat_http_request_duracao_segundos": "HTTP_DURACAO_SEGUNDOS",
    "plat_tiles_requisicoes_total": "TILES_REQUISICOES",
    "plat_jobs_processados_total": "JOBS_PROCESSADOS",
}


def _funcoes_que_tocam(constante: str) -> set[str]:
    arvore = ast.parse((APP / "metricas.py").read_text(encoding="utf-8"))
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef):
            for dentro in ast.walk(no):
                if isinstance(dentro, ast.Name) and dentro.id == constante:
                    nomes.add(no.name)
    return nomes


def _chamadores_fora_de_metricas(nomes: set[str]) -> list[str]:
    achados = []
    for caminho in APP.rglob("*.py"):
        if caminho.name == "metricas.py":
            continue
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call):
                alvo = no.func
                nome = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", None)
                if nome in nomes:
                    achados.append(str(caminho.relative_to(RAIZ)))
                    break
    return achados


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


# CONSERTADO (18/09/2026, turno L7 do construtor). O defeito ERA real: as quatro famílias não tinham
# chamador. O conserto está em app/auth/middleware.py, app/tiles/rotas.py e app/jobs/worker.py. A
# conferência antiga exigia que o painel EVITASSE as métricas, o que é o remédio errado — apagar o
# quadro esconde o problema em vez de resolvê-lo. A conferência agora exige o contrário: toda métrica
# acusada que o painel consulta precisa ter quem a incremente.
def test_metrica_consultada_pelo_painel_tem_quem_a_incremente():
    expressoes = " ".join(_expressoes_do_painel(PAINEL_VISAO_GERAL))
    sem_chamador = {}
    for metrica in METRICAS_ACUSADAS:
        if metrica not in expressoes:
            continue
        funcoes = _funcoes_que_tocam(CONSTANTE_DA_METRICA[metrica])
        if not funcoes or not _chamadores_fora_de_metricas(funcoes):
            sem_chamador[metrica] = sorted(funcoes)
    assert not sem_chamador, (
        f"quadros do painel consultam métrica(s) que ninguém incrementa: {sem_chamador}"
    )


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
        "PENDENTE DE IMPLANTAÇÃO, não de código (medido em 18/09/2026). O chamador de "
        "registrar_job_processado existe em app/jobs/worker.py e a família ganha série num processo "
        "que rode ESTE código (test_l7_adv1_metricas_http_nunca_incrementadas.py mede a irmã "
        "plat_http_requests_total ao vivo e passa). O Prometheus de 127.0.0.1:9090 raspa a trilha "
        "viva, que roda master, e por isso GET /api/v1/query?query=plat_jobs_processados_total ainda "
        "devolve result=[]. A marca sai quando o ramo entrar em master e o worker da trilha reiniciar. "
        "Item L7-06-d-paineis."
    ),
)
def test_metrica_do_quadro_jobs_tem_serie_no_prometheus_vivo():
    assert _prometheus_tem_serie("plat_jobs_processados_total"), (
        "plat_jobs_processados_total sem série no Prometheus — o quadro 'Jobs concluídos' está sempre "
        "em 'No data'"
    )
