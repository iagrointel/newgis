#!/usr/bin/env python3
"""Gera `docs/LICENCAS_SIMBOLOS.md` a partir do manifesto vivo (item L2-02-e-simbolos-sprites-glifos):
uma linha por ícone/padrão embutido (`app.simbolos.biblioteca.manifesto`) + uma por fonte de mapa
(lida de `web/vendor/VERSOES.txt`, seção "Glifos de mapa"). Nunca editar o .md à mão — reexecutar isto."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.simbolos import biblioteca  # noqa: E402

DESTINO = ROOT / "docs" / "LICENCAS_SIMBOLOS.md"
VERSOES = ROOT / "web" / "vendor" / "VERSOES.txt"


def _fontes_de_mapa() -> list[dict]:
    saida = []
    for linha in VERSOES.read_text(encoding="utf-8").splitlines():
        if not linha.startswith(("noto-sans-regular-", "open-sans-regular-")):
            continue
        partes = linha.split(None, 4)
        if len(partes) < 5:
            continue
        arquivo, versao, sha, licenca, origem = partes
        saida.append({"arquivo": arquivo, "versao": versao, "sha256": sha, "licenca": licenca, "origem": origem})
    return saida


def gerar() -> str:
    registros = biblioteca.manifesto()
    fontes = _fontes_de_mapa()
    linhas = [
        "# Licenças dos símbolos e fontes embutidos",
        "",
        "Gerado por `scripts/gerar_licencas_simbolos.py` a partir de `app/simbolos/biblioteca.py` "
        "(manifesto vivo) e `web/vendor/VERSOES.txt` — nunca editar este arquivo à mão.",
        "",
        f"Total: **{len(registros)} ícones/padrões** (item L2-02-e-simbolos-sprites-glifos, portão exige "
        "≥ 150) + **{n} fontes de glifo de mapa**.".format(n=len(fontes)),
        "",
        "## Ícones e padrões de preenchimento (produção própria)",
        "",
        "| arquivo | categoria | tipo | licença | sha256 |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(registros, key=lambda x: x["arquivo"]):
        linhas.append(
            f"| `{r['arquivo']}` | {r['categoria']} | {r['tipo']} | {r['licenca']} | `{r['sha256'][:16]}…` |"
        )
    linhas += [
        "",
        "Autoria de todos os registros acima: " + registros[0]["autor"] if registros else "",
        "",
        "## Fontes de glifo de mapa (embutidas em `web/vendor/`, servidas ao Martin)",
        "",
        "| arquivo | versão | licença | origem |",
        "|---|---|---|---|",
    ]
    for f in fontes:
        linhas.append(f"| `{f['arquivo']}` | {f['versao']} | {f['licenca']} | {f['origem']} |")
    linhas.append("")
    return "\n".join(linhas)


def main() -> None:
    DESTINO.write_text(gerar(), encoding="utf-8")
    n_reg, n_fontes = len(biblioteca.manifesto()), len(_fontes_de_mapa())
    print(f"escrito {DESTINO} ({n_reg} registros de ícone/padrão + {n_fontes} de fonte)")


if __name__ == "__main__":
    main()
