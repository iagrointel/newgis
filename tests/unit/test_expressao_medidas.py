"""Grava `tests/medidas/L2-10-c-expressao.json` (ADR 0001 seção 10) — os números que
`ARQUITETURA.md`/`README.md`/`docs/PARIDADE.md` citam para este item saem daqui, nunca digitados
à mão. Só grava quando `PLAT_GRAVAR_MEDIDAS=1` (o testador roda isto explicitamente; a suíte comum
não suja a árvore)."""

import json
import subprocess
import sys
import time
from pathlib import Path

from app.expressao.avaliador_py import (
    LIMITE_MS_SERVIDOR,
    TABELA_FUNCOES,
    ErroExpressao,
    analisar,
    avaliar_texto,
)

ROOT = Path(__file__).resolve().parents[2]
VETORES = ROOT / "tests" / "expressoes" / "vetores.json"
VETORES_CONVERGENCIA = ROOT / "tests" / "expressoes" / "vetores_convergencia.json"
DOC = ROOT / "docs" / "EXPRESSAO.md"


def test_medidas_do_nucleo_da_linguagem_de_expressao(medida):
    grava = medida("L2-10-c-expressao")

    grava("funcoes_implementadas", len(TABELA_FUNCOES), "funções", "len(TABELA_FUNCOES) em avaliador_py.py")

    vetores = json.loads(VETORES.read_text(encoding="utf-8"))
    grava(
        "vetores_de_equivalencia",
        len(vetores),
        "vetores",
        "len(json.load(tests/expressoes/vetores.json)) — extensão exige ≥ 200",
    )

    convergencia = json.loads(VETORES_CONVERGENCIA.read_text(encoding="utf-8"))
    grava(
        "vetores_de_convergencia_pos_adversario",
        len(convergencia),
        "vetores",
        "len(json.load(tests/expressoes/vetores_convergencia.json)) — os casos em que os dois avaliadores "
        "divergiam no ataque de 06/09 (resto, ponto de código, algarismo não-ASCII, fração de milissegundo) "
        "viraram vetor compartilhado; rodam junto dos 309 em test_expressao_equivalencia.py",
    )

    secao10 = DOC.read_text(encoding="utf-8").split("## 10. Paridade")[1].split("## 11.")[0]
    estados = [
        c[2]
        for c in ([x.strip() for x in linha.strip().strip("|").split("|")] for linha in secao10.splitlines())
        if len(c) >= 3 and c[2] in {"feito", "parcial", "fora"}
    ]
    grava(
        "linhas_feito_na_paridade_arcade",
        estados.count("feito"),
        f"linhas de {len(estados)}",
        "linhas marcadas `feito` na seção 10 de docs/EXPRESSAO.md depois da revisão de 06/09 (eram 29; "
        "toda linha `feito` precisa de vetor de teste e de nenhuma diferença escrita — "
        "test_expressao_paridade.py)",
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
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(ROOT),
        check=True,
    )
    resultados_js = json.loads(r.stdout)
    ida_e_volta = sum(1 for item in resultados_js if item["erro_ida_e_volta"] is None)
    assert ida_e_volta == len(vetores)
    grava(
        "vetores_ast_ida_e_volta_nos_dois_lados",
        ida_e_volta,
        "vetores",
        "executar_js.mjs: astParaJson → JSON → astDeJson → avaliar == avaliar direto; Python idem em "
        "test_ast_ida_e_volta_avalia_igual_em_todos_os_vetores; cruzado (AST do Python lida no JS) em "
        "test_ast_exportada_pelo_python_reimportada_no_javascript_avalia_igual_em_todos_os_vetores",
    )
    sys.path.insert(0, str(Path(__file__).parent))
    from test_expressao_extensao import medir_corte_javascript_ms, medir_corte_python_ms

    codigo_py, ms_py = medir_corte_python_ms()
    codigo_js, ms_js = medir_corte_javascript_ms()
    assert codigo_py == "tempo_excedido" and codigo_js == "tempo_excedido"
    grava(
        "tempo_corte_relogio_50ms_python_ms",
        round(ms_py, 2),
        "ms",
        "40 × Contagem(Unicos($x)) com 1.024 dicionários, limite_passos=10^9, limite_ms=50 → tempo_excedido "
        "(test_expressao_extensao.medir_corte_python_ms)",
    )
    grava(
        "tempo_corte_relogio_50ms_javascript_ms",
        round(ms_js, 2),
        "ms",
        "mesmo ataque com avaliador.js, limiteMs=LIMITE_MS_CLIENTE (50) → tempo_excedido "
        "(test_expressao_extensao.medir_corte_javascript_ms)",
    )
    from test_expressao_extensao import _ATAQUE_TEMPO, _CONTEXTO_ATAQUE

    t0 = time.perf_counter()
    try:
        avaliar_texto(_ATAQUE_TEMPO, _CONTEXTO_ATAQUE, limite_passos=10**9, limite_ms=LIMITE_MS_SERVIDOR)
        raise AssertionError("o ataque terminou sem erro no orçamento de servidor")
    except ErroExpressao as exc:
        assert exc.codigo == "tempo_excedido"
    ms_servidor = (time.perf_counter() - t0) * 1000.0
    grava(
        "tempo_corte_relogio_500ms_servidor_ms",
        round(ms_servidor, 2),
        "ms",
        "mesmo ataque (40 × Contagem(Unicos($x)) com 1.024 dicionários) com limite_ms=LIMITE_MS_SERVIDOR "
        "(500) → tempo_excedido; mede o teto do servidor, não o do cliente",
    )

    passos_ataque = None
    try:
        avaliar_texto(_ATAQUE_TEMPO, _CONTEXTO_ATAQUE, limite_ms=10**6)
    except ErroExpressao as exc:
        passos_ataque = exc.codigo
    assert passos_ataque == "limite_passos"
    grava(
        "orcamento_de_passos_padrao",
        10**5,
        "passos",
        "LIMITE_PASSOS do avaliador; o mesmo ataque com relógio folgado (limite_ms=10^6) para em "
        "limite_passos, provando que os dois orçamentos cortam de forma independente",
    )

    concordam = sum(1 for item in resultados_js if item["erro"] is None)
    assert concordam == len(vetores), "não registrar como prova vetores que falharam no JavaScript"
    grava(
        "vetores_avaliados_sem_erro_no_lado_javascript",
        concordam,
        "vetores",
        "executar_js.mjs sobre tests/expressoes/vetores.json — cada um também comparado byte a byte "
        "com o resultado Python em test_expressao_equivalencia.py",
    )
