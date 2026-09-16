"""Adversário de linha L1 imagens (parte 2, turno 9) — item `L1-02-d-cache-nginx-cdn-e-bancada-de-
carga`, ENTREGUE (sem sha no ledger). Três cláusulas literais do portão não passam, e a prova disso
já está na própria evidência commitada como fechamento
(`tests/medidas/L1-02-d-cache-nginx-e-carga.json`):

1. Portão: "frio ≥ 15 tiles/s com 1 conexão". A medição commitada tem
   `carga.frio_1_conexao.tiles_por_s = 9,4` e o PRÓPRIO JSON já grava `"passou": false` para essa
   cláusula — ninguém releu o resultado antes de marcar ENTREGUE (mesmo padrão achado pelo
   adversário da linha irmã L2, parte 2: evidência commitada reprova o próprio portão).
2. Portão: "bancada `tests/carga/tiles.py` ... que mede quente/frio de 1 a 200 conexões". A medição
   commitada só tem UM ponto de conexão (16); o próprio campo `nao_feito` do JSON admite: "bancada
   de 1 a 200 conexões (só 16; a máquina tem três construtores rodando)".
3. Portão: "página interna de status mostra taxa de acerto do cache por dia". Não existe, em nenhum
   arquivo de `app/`, rota ou geração de página com taxa de acerto de cache — e o próprio campo
   `nao_feito` do JSON admite: "página interna de status com taxa de acerto do cache por dia".

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_cache_gate.py -q -rxX`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEDIDA = ROOT / "tests" / "medidas" / "L1-02-d-cache-nginx-e-carga.json"


def _dados():
    return json.loads(MEDIDA.read_text(encoding="utf-8"))


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-d CAI: a propria evidencia commitada como fechamento grava "
    "carga.frio_1_conexao.passou=false (tiles_por_s=9.4 contra o portao de >=15) — a cláusula do "
    "portao 'frio >= 15 tiles/s com 1 conexao' reprova pelo proprio numero que o time gravou."
))
def test_frio_uma_conexao_atende_o_portao():
    d = _dados()
    frio = d["carga"]["frio_1_conexao"]
    assert frio["passou"] is True, (
        f"frio_1_conexao nao passou no proprio JSON de fechamento: {frio}")


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-d CAI: o portao pede a bancada medindo de 1 A 200 conexoes; a medicao commitada tem um "
    "unico ponto (16 conexoes) e o proprio campo 'nao_feito' do JSON admite a bancada completa como "
    "pendente ('bancada de 1 a 200 conexoes (so 16; a maquina tem tres construtores rodando)')."
))
def test_bancada_cobre_a_faixa_de_1_a_200_conexoes():
    d = _dados()
    texto_nao_feito = " ".join(d.get("nao_feito", []))
    assert "bancada de 1 a 200" not in texto_nao_feito, (
        f"a propria evidencia admite a bancada de 1-200 conexoes como NAO FEITA: {texto_nao_feito!r}")


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-d CAI: nao existe, em app/, nenhuma rota/pagina que mostre taxa de acerto do cache por "
    "dia (grep de 'taxa de acerto'/'acerto do cache'/'hit_rate' em app/ nao acha nada); o proprio "
    "campo 'nao_feito' do JSON de fechamento admite isso: 'pagina interna de status com taxa de "
    "acerto do cache por dia'."
))
def test_pagina_de_status_com_taxa_de_acerto_do_cache_existe():
    achados = []
    for caminho in (ROOT / "app").rglob("*.py"):
        texto = caminho.read_text(encoding="utf-8", errors="ignore").lower()
        if "acerto do cache" in texto or "taxa de acerto" in texto or "cache_hit_rate" in texto:
            achados.append(str(caminho.relative_to(ROOT)))
    assert achados, "nenhum arquivo em app/ implementa taxa de acerto de cache por dia"
