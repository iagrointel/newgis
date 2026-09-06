"""Grava `tests/medidas/L2-10-c-expressao.json` (ADR 0001 seção 10) — os números que
`ARQUITETURA.md`/`README.md`/`docs/PARIDADE.md` citam para este item saem daqui, nunca digitados
à mão. Só grava quando `PLAT_GRAVAR_MEDIDAS=1` (o testador roda isto explicitamente; a suíte comum
não suja a árvore)."""

import json
import subprocess
import time
from pathlib import Path

from app.expressao.avaliador_py import (
    TABELA_FUNCOES,
    ErroExpressao,
    analisar,
)

ROOT = Path(__file__).resolve().parents[2]
VETORES = ROOT / "tests" / "expressoes" / "vetores.json"


def test_medidas_do_nucleo_da_linguagem_de_expressao(medida):
    grava = medida("L2-10-c-expressao")

    grava("funcoes_implementadas", len(TABELA_FUNCOES), "funções", "len(TABELA_FUNCOES) em avaliador_py.py")

    vetores = json.loads(VETORES.read_text(encoding="utf-8"))
    grava(
        "vetores_de_equivalencia",
        len(vetores),
        "vetores",
        "len(json.load(tests/expressoes/vetores.json)) — portão do item pede ≥ 20",
    )

    t0 = time.perf_counter()
    try:
        analisar("1" + "+1" * 900)
    except ErroExpressao:
        pass
    ms_cadeia = (time.perf_counter() - t0) * 1000.0
    grava(
        "tempo_ataque_cadeia_900_termos_ms",
        round(ms_cadeia, 2),
        "ms",
        "analisar('1'+'+1'*900) até levantar profundidade_excedida",
    )

    t0 = time.perf_counter()
    try:
        analisar("'" + ("a" * 10_000_000) + "'")
    except ErroExpressao:
        pass
    ms_string = (time.perf_counter() - t0) * 1000.0
    grava(
        "tempo_ataque_string_10mb_ms",
        round(ms_string, 2),
        "ms",
        "analisar(\"'\" + 'a'*10_000_000 + \"'\") até levantar expressao_grande",
    )

    t0 = time.perf_counter()
    try:
        analisar("(" * 500 + "1" + ")" * 500)
    except ErroExpressao:
        pass
    ms_parenteses = (time.perf_counter() - t0) * 1000.0
    grava(
        "tempo_ataque_500_parenteses_ms",
        round(ms_parenteses, 2),
        "ms",
        "analisar('('*500 + '1' + ')'*500) até levantar profundidade_excedida",
    )

    r = subprocess.run(
        ["node", str(ROOT / "tests" / "expressoes" / "executar_js.mjs")],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT), check=True,
    )
    resultados_js = json.loads(r.stdout)
    concordam = sum(1 for item in resultados_js if item["erro"] is None)
    grava(
        "vetores_avaliados_sem_erro_no_lado_javascript",
        concordam,
        "vetores",
        "executar_js.mjs sobre tests/expressoes/vetores.json — cada um também comparado byte a byte "
        "com o resultado Python em test_expressao_equivalencia.py",
    )
