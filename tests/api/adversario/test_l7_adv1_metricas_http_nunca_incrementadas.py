"""Adversário de linha L7 operação (parte 1) — item `L7-06-a-metricas-exporters`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`; achado transversal nº 1).

`app/metricas.py` declara `plat_http_requests_total`, `plat_http_request_duracao_segundos`,
`plat_tiles_requisicoes_total` e `plat_jobs_processados_total`, com as funções que as incrementariam
(`registrar_requisicao`, `registrar_tile`, `registrar_job_processado`) — mas nenhuma delas é chamada de
lugar nenhum em `app/`. `app/main.py` e `app/auth/middleware.py` (o único ponto que vê toda requisição)
nunca importam `app.metricas`. Confirmado ao vivo: `GET /metrics` depois de dezenas de requisições reais
na trilha `uniao` mostra `# HELP`/`# TYPE` para `plat_http_requests_total`, mas zero séries."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
APP = RAIZ / "app"

FUNCOES_DE_REGISTRO = ("registrar_requisicao", "registrar_tile", "registrar_job_processado")


def _chamadores_fora_de_metricas(nome_funcao: str) -> list[str]:
    """Arquivos (fora de app/metricas.py) que citam `nome_funcao` como CHAMADA (Call), não só import."""
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
                if nome == nome_funcao:
                    achados.append(str(caminho.relative_to(RAIZ)))
                    break
    return achados


@pytest.mark.parametrize("funcao", FUNCOES_DE_REGISTRO)
# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_funcao_de_registro_de_metrica_tem_chamador(funcao):
    chamadores = _chamadores_fora_de_metricas(funcao)
    assert chamadores, f"{funcao} não é chamada em nenhum arquivo fora de app/metricas.py"


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_metrica_http_tem_pelo_menos_uma_serie_apos_trafego(cliente):
    for _ in range(5):
        cliente.get("/api/versao")
    r = cliente.get("/metrics")
    assert r.status_code == 200
    linhas = [li for li in r.text.splitlines() if li.startswith("plat_http_requests_total")]
    assert linhas, "nenhuma série de plat_http_requests_total mesmo após tráfego real"
