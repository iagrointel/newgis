"""Adversário de linha L2 (parte 1) — hipótese transversal nº 2 do laudo: `docs/openapi.json` (o documento
que vários itens desta linha citam como a fonte "OpenAPI 3.0" publicada — p.ex. a hipótese de
`L2-04-g-ogc-api-features-crs-cql2` promete "/api OpenAPI 3.0"; é também o arquivo que
`docs/gerar_*` e o SDK de `scripts/gerar_sdk.sh` leem para gerar cliente/documentação) **diverge do app
vivo em `wt/uniao`**, sem nenhuma guarda automática: `make openapi` só SOBRESCREVE o arquivo, não existe
alvo `make` nem teste que compare o commitado contra `app.openapi()` gerado a partir do código atual.

Achado concreto (o mesmo que prova `L2-03-b` nesta linha): `docs/openapi.json` documenta
`/api/camadas/{id}/feicoes/unir`, `/api/camadas/{id}/feicoes/dividir`,
`/api/camadas/{id}/feicoes/{globalid}` (+ histórico/restaurar/anexos) — rotas que NÃO existem no app vivo
(ver `test_l2_adv1_edicao_geometria.py` e o laudo). Ou seja: quem confia em `docs/openapi.json` para saber
"o que a API oferece" (inclusive um cliente ou uma ferramenta de conformidade externa) é enganado na
direção mais perigosa — a de achar que uma capacidade existe quando não existe.

Este teste não é específico de um item: generaliza a checagem para QUALQUER rota documentada e ausente
(não o inverso — rotas novas ainda não documentadas são uma lacuna de doc, não um risco de cliente
quebrado, e ficam de fora de propósito)."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _rotas_vivas() -> set[str]:
    sys.path.insert(0, str(ROOT))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from app.main import app

    return set(app.openapi()["paths"].keys())


def _rotas_commitadas() -> set[str]:
    return set(json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))["paths"].keys())


@pytest.mark.xfail(
    strict=True,
    reason=(
        "docs/openapi.json (commitado) documenta rotas que não existem no app vivo de wt/uniao — inclusive "
        "/api/camadas/{id}/feicoes/unir e /feicoes/dividir (L2-03-b, ver test_l2_adv1_edicao_geometria.py) "
        "e as de histórico/anexo de L2-03-d/L2-03-e (já refutados). Não há alvo make nem teste que compare "
        "o commitado contra app.openapi() gerado do código atual — `make openapi` só sobrescreve, nunca "
        "verifica. Quem toma docs/openapi.json como contrato (cliente, SDK, ferramenta de conformidade "
        "externa) recebe capacidade que não existe."
    ),
)
def test_l2_docs_openapi_nao_documenta_rota_ausente_do_app_vivo():
    fantasmas = sorted(_rotas_commitadas() - _rotas_vivas())
    assert fantasmas == [], f"rotas documentadas em docs/openapi.json e ausentes do app vivo: {fantasmas}"
