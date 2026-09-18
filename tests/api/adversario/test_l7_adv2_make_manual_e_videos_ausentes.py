"""Adversário de linha L7 operação (parte 2) — itens `L7-04-a-manual-capturas-geradas` e
`L7-04-d-videos-por-tarefa` (laudo `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`).

O portão LITERAL dos dois itens cita um comando exato:
  - L7-04-a: "`make manual` sai 0 e produz HTML + PDF"
  - L7-04-d: "`make videos` produz ≥ 10 vídeos com legenda e áudio"

Nenhum dos dois alvos existe no `Makefile` desta árvore (idêntico ao de `wt/uniao`, confirmado por
`git diff wt/uniao -- Makefile` vazio — não é regressão desta rodada nem deste ramo). O `.PHONY` do
Makefile lista `check check-rapido lint tokens sem-marcador teste e2e medidas migrar openapi vendor
limites seguranca-deps varredura-cve correcoes seguranca seguranca-gravar seguranca-zap ferramentas
homolog pacote-rede conformidade conformidade-conferir` — nem `manual` nem `videos` aparecem, e
`make -n manual` / `make -n videos` falham com "No rule to make target". Os scripts por trás dos dois
itens continuam no repositório (`docs/gerar_manual.py`, `scripts/videos/gerar.py`) e o CHANGELOG/ADR
seguem descrevendo `make manual`/`make videos` como comandos vivos (`docs/adr/
20260908T1925-manual-gerado-pelo-e2e.md`, `CHANGELOG.md` linha ~1855) — o alvo do Makefile
provavelmente se perdeu numa fusão (mesmo padrão do achado transversal nº1 do laudo parte 1: pedaço
"morto" que ninguém religou depois de juntar ramos), mas o efeito É que HOJE nenhum dos dois portões
literais pode ser satisfeito digitando o comando que o próprio item descreve.

Achado adicional para L7-04-d: mesmo que `make videos` existisse, `scripts/videos/roteiros.py`
confere cada vídeo contra uma seção do `MANUAL.md` DA RAIZ (`scripts/videos/gerar.py::
confere_secoes_manual`, `caminho = RAIZ / "MANUAL.md"`) — não contra `docs/manual/<tela>.md`, que é
o manual GERADO pelo e2e que o item `L7-04-a` promete ("gerado, não escrito à mão"). `MANUAL.md` da
raiz é o documento histórico mantido à mão (citado no brief comum como "MANUAL.md ... só se o item
pedir"). Ou seja, a cláusula "cada [vídeo] ligado à seção do manual" hoje amarra ao manual ERRADO: o
antigo, escrito à mão, não o novo, gerado — mesmo que os dois tenham títulos de seção parecidos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]


def _make_dry_run(alvo: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", "-n", alvo], cwd=RAIZ, capture_output=True, text=True, timeout=30, check=False,
    )


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_make_manual_existe_como_alvo():
    resultado = _make_dry_run("manual")
    assert resultado.returncode == 0, (
        f"make -n manual falhou (rc={resultado.returncode}): {resultado.stderr.strip()}"
    )


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_make_videos_existe_como_alvo():
    resultado = _make_dry_run("videos")
    assert resultado.returncode == 0, (
        f"make -n videos falhou (rc={resultado.returncode}): {resultado.stderr.strip()}"
    )


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_roteiro_de_videos_confere_contra_o_manual_gerado():
    texto = (RAIZ / "scripts" / "videos" / "gerar.py").read_text(encoding="utf-8")
    assert 'RAIZ / "docs" / "manual"' in texto or 'docs/manual' in texto, (
        "gerar.py confere as seções contra MANUAL.md da raiz, não contra docs/manual/<tela>.md "
        "(o manual gerado pelo e2e de L7-04-a)"
    )
