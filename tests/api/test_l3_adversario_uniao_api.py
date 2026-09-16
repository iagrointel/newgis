"""Adversário da LINHA L3 (motor AMC), achado de API sobre a base `wt/uniao` (16/09/2026).

L3-01-h-presets foi marcado ENTREGUE ("22 unit+12 API+218 cruzado+1 e2e verdes"), mas em
`app/main.py` a rota nunca foi de fato ligada: linha 24 importa
`from app.amc.rotas import router as rotas_amc_presets` — o MESMO objeto router que a linha 23
já importa como `rotas_amc` (o router geral de modelos/conjuntos/execuções, sem UM endpoint de
preset). `app.amc.presets` (CRUD, `PresetAplicar`, `PresetImportar`) não define nenhum APIRouter e
não existe `app/amc/rotas_presets.py` neste repositório: a lógica ficou pronta, mas nunca virou
rota. `include_router(rotas_amc_presets)` na prática registra `app/amc/rotas.py` DUAS VEZES.

Consequência medida: TODA a suíte tests/api/test_amc_presets_api.py falha com 404 'recurso
inexistente' em POST /api/amc/presets (12 de 12 testes), porque a rota não existe."""

from __future__ import annotations

import pytest

from tests.api.conftest import PREFIXO_TESTE


@pytest.mark.xfail(
    strict=True,
    reason="POST /api/amc/presets devolve 404 'recurso inexistente' na base wt/uniao: "
           "app/main.py importa app.amc.rotas.router DUAS VEZES (uma vez como rotas_amc, outra com "
           "o apelido rotas_amc_presets) em vez de importar o router de presets — que não existe "
           "como APIRouter em lugar nenhum do repositório (app/amc/presets.py só tem os modelos "
           "Pydantic e a lógica; não há app/amc/rotas_presets.py). O item L3-01-h-presets está "
           "inteiro fora do ar nesta união. Reproduz: qualquer teste de "
           "tests/api/test_amc_presets_api.py na mesma base (12 de 12 falham com 404).",
)
def test_criar_preset_por_api_esta_no_ar(sessao_a):
    r = sessao_a.post("/api/amc/presets", json={
        "nome": f"{PREFIXO_TESTE}-adversario-l3-presets", "descricao": "achado do adversário",
        "escopo": "usuario",
        "conteudo": {"fatores": ["a", "b"], "pesos": {"a": 1.0, "b": 1.0}},
    })
    assert r.status_code == 201, r.text
