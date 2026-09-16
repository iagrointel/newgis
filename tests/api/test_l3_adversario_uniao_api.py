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

import secrets

from tests.api.conftest import PREFIXO_TESTE


def test_criar_preset_por_api_esta_no_ar(sessao_a):
    nome = f"{PREFIXO_TESTE}-adversario-l3-presets-{secrets.token_hex(4)}"
    r = sessao_a.post("/api/amc/presets", json={
        "nome": nome, "descricao": "achado do adversário",
        "escopo": "usuario",
        "conteudo": {"fatores": ["a", "b"], "pesos": {"a": 1.0, "b": 1.0}},
    })
    try:
        assert r.status_code == 201, r.text
    finally:
        if r.status_code == 201:
            sessao_a.delete(f"/api/amc/presets/{r.json()['id']}")
