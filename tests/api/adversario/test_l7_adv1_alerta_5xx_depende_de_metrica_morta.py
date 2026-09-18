"""Adversário de linha L7 operação (parte 1) — item `L7-06-b-alertas`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`), consequência direta do achado transversal nº 1
(`L7-06-a-metricas-exporters`: `plat_http_requests_total` nunca é incrementada).

A regra de alerta "5xx > 1% em 5 min" em `deploy/alertas.yml` consulta:

    sum(rate(plat_http_requests_total{status=~"5.."}[5m]))
      / clamp_min(sum(rate(plat_http_requests_total[5m])), 0.001) > 0.01

Como `plat_http_requests_total` nunca recebe amostra nenhuma (ver
`test_l7_adv1_metricas_http_nunca_incrementadas.py`), essa expressão PromQL nunca produz série de dados —
não é "0%", é ausência de série — e o Alertmanager nunca dispara essa regra, não importa quantos 5xx
reais aconteçam em produção. Este teste confere a ligação estática: toda métrica `plat_http_*` citada em
`deploy/alertas.yml` precisa ter, em algum lugar de `app/`, uma chamada real que a incremente/observe."""

from __future__ import annotations

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
ALERTAS = RAIZ / "deploy" / "alertas.yml"
APP = RAIZ / "app"

METRICA_HTTP = re.compile(r"\bplat_http_requests_total\b")


def _funcoes_que_tocam(constante: str) -> set[str]:
    """Funções de app/metricas.py cujo corpo usa a constante da métrica (ex.: HTTP_REQUISICOES)."""
    arvore = ast.parse((APP / "metricas.py").read_text(encoding="utf-8"))
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef):
            for dentro in ast.walk(no):
                if isinstance(dentro, ast.Name) and dentro.id == constante:
                    nomes.add(no.name)
    return nomes


def _chamadores_fora_de_metricas(nomes: set[str]) -> list[str]:
    """Arquivos de app/ (fora de metricas.py) que CHAMAM alguma dessas funções."""
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


# CONSERTADO (18/09/2026, turno L7 do construtor). O defeito ERA real e foi corrigido em
# app/auth/middleware.py, que agora chama app.metricas.registrar_requisicao em toda requisição. A
# conferência antiga procurava a sequência literal `.labels(` num arquivo fora de app/metricas.py e por
# isso continuava reprovando depois do conserto: o `.labels(...)` fica, e deve ficar, dentro de
# `registrar_requisicao`, que é a única dona da métrica. A conferência agora segue a CADEIA (quem toca a
# constante -> quem chama essa função) e, abaixo, confere ao vivo que a família da regra de alerta ganha
# série de verdade depois de tráfego — é a série, não a forma da chamada, que faz a regra disparar.
def test_regra_de_5xx_usa_metrica_que_e_incrementada():
    texto_alertas = ALERTAS.read_text()
    assert METRICA_HTTP.search(texto_alertas), "deploy/alertas.yml não cita mais plat_http_requests_total"
    funcoes = _funcoes_que_tocam("HTTP_REQUISICOES")
    assert funcoes, "nenhuma função de app/metricas.py toca HTTP_REQUISICOES"
    chamadores = _chamadores_fora_de_metricas(funcoes)
    assert chamadores, (
        "plat_http_requests_total (usada pela regra de 5xx) nunca é incrementada fora de app/metricas.py: "
        f"nenhum arquivo de app/ chama {sorted(funcoes)}"
    )


def test_serie_da_regra_de_5xx_existe_apos_trafego(cliente):
    """Par positivo da conferência estática acima: a expressão PromQL da regra só produz série se a
    família tiver amostra. Mede-se a família inteira (com rótulo de status) depois de tráfego real."""
    for _ in range(5):
        cliente.get("/api/versao")
    r = cliente.get("/metrics")
    assert r.status_code == 200
    series = [li for li in r.text.splitlines()
              if li.startswith("plat_http_requests_total{") and 'status="' in li]
    assert series, "plat_http_requests_total continua sem série nenhuma depois de tráfego real"
