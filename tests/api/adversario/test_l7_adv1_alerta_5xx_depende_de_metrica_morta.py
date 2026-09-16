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

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
ALERTAS = RAIZ / "deploy" / "alertas.yml"
APP = RAIZ / "app"

METRICA_HTTP = re.compile(r"\bplat_http_requests_total\b")


def _metrica_e_incrementada_em_algum_lugar() -> bool:
    for caminho in APP.rglob("*.py"):
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        if ".labels(" in texto and ("HTTP_REQUISICOES" in texto) and "app/metricas.py" not in str(caminho):
            return True
    return False


@pytest.mark.xfail(
    strict=True,
    reason=(
        "a regra de alerta '5xx > 1% em 5 min' (deploy/alertas.yml) consulta plat_http_requests_total, "
        "que nunca recebe amostra (app/metricas.py::registrar_requisicao não é chamada de lugar nenhum — "
        "achado transversal nº 1 do laudo L7 parte 1). rate() sobre uma métrica sem série nenhuma não "
        "dispara alerta, não importa quantos 5xx reais aconteçam. Item L7-06-b-alertas."
    ),
)
def test_regra_de_5xx_usa_metrica_que_e_incrementada():
    texto_alertas = ALERTAS.read_text()
    assert METRICA_HTTP.search(texto_alertas), "deploy/alertas.yml não cita mais plat_http_requests_total"
    assert _metrica_e_incrementada_em_algum_lugar(), (
        "plat_http_requests_total (usada pela regra de 5xx) nunca é incrementada fora de app/metricas.py "
        "— o histórico chamador .labels(...) só existe na própria definição da métrica"
    )
