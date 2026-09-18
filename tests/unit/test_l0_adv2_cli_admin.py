"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achado sobre `L0-14-cli-admin`. Laudo completo em
`laco/handoffs/T9/linha-L0-laudo-adversario-2.md`.

`scripts/plat` (o ponto de entrada real, o mesmo que `docs/CLI.md` e o portão do item apontam: "'plat
inquilino criar' é o que o install.sh usa para demo/demo2") foi SUBSTITUÍDO por um script bem menor e
completamente diferente, de outros dois itens (`L7-01-c-dado-demonstracao` e `L7-19-segredos-e-certificados`):
hoje `scripts/plat --help` só oferece os grupos `{segredo, demo}`. Nenhum dos grupos que o item promete
(`inquilino`, `usuario`, `token`, `camada`, `job`, `evento`) existe mais NO ARQUIVO QUE RODA.

A implementação completa continua no repositório, intacta, em `app/cli/principal.py` (247 linhas, todos os
`add_parser` de inquilino/usuario/token/camada/job/evento/saude/segredo/docs, commit `e22eb6b1b` — o mesmo
que fechou o item) — só não está mais ligada ao executável `scripts/plat`. `docs/CLI.md`, gerado supostamente
"a partir de `app/cli/principal.py`", ainda descreve os 75+ comandos que não existem mais no ponto de entrada
real, e diz textualmente "Ponto de entrada: `scripts/plat` no repositório".

Consequência medida ao vivo: `bash laco/roda_teste.sh tests/api/test_cli_admin.py` — 16 de 16 testes falham
hoje, todos com a mesma causa (`argument acao/grupo: invalid choice`)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# REMEDIADO (wt/l02, 18/09/2026): `scripts/plat` voltou a ser o atalho de uma linha para `python -m app.cli`
# que o ADR docs/adr/20260907T2318-linha-de-comando-plat.md (decisão 1) manda ele ser, e os dois grupos que
# haviam tomado o lugar do arquivo (`demo`, de L7-01-c, e `segredo`, de L7-19) viraram subcomandos do parser
# ÚNICO em app/cli/principal.py — que é de onde `plat docs` gera docs/CLI.md. O `xfail` saiu.
# Prova ao vivo desta trilha: tests/api/test_cli_admin.py 19/19 verdes, incluindo a cláusula do portão sobre
# o install.sh (passo h1b usa `plat inquilino criar --se-nao-existir --senha-arquivo`).
def test_scripts_plat_e_o_ponto_de_entrada_que_docs_cli_promete():
    r = subprocess.run([str(ROOT / "scripts" / "plat"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for grupo in ("inquilino", "usuario", "token", "camada", "job", "evento"):
        assert grupo in r.stdout, (
            f"'plat --help' não lista o grupo '{grupo}' (que docs/CLI.md e o portão do item prometem); "
            f"saída real: {r.stdout!r}"
        )
