#!/usr/bin/env python3
"""Troca a folha antiga pela nova numa tela, sem tocar em mais nada.

    venv/bin/python tests/e2e/migra_folha.py <arquivo.html> [...]

A troca e literal: a linha `<link rel="stylesheet" href="/static/style.css">` vira as duas linhas
`estilo/base.css` + `estilo/componentes.css`, na mesma posicao (depois de tokens.css, antes da folha propria
da tela). Nada mais do HTML muda - estrutura e comportamento sao os mesmos, e e isso que
tests/e2e/test_migracao_folha.py confere com a impressao digital da arvore.

Nao decide nada sozinho: as regras que so existem em style.css e que a tela usa de verdade sao medidas no
navegador (campo `so_na_antiga_e_pegam` do relatorio da fase 'antes') e levadas a mao."""

import sys
from pathlib import Path

ANTIGA = '<link rel="stylesheet" href="/static/style.css">'
NOVA = ('<link rel="stylesheet" href="/static/estilo/base.css">\n'
        '<link rel="stylesheet" href="/static/estilo/componentes.css">')


def migrar(caminho: Path) -> bool:
    texto = caminho.read_text(encoding="utf-8")
    if ANTIGA not in texto:
        return False
    assert texto.count(ANTIGA) == 1, f"{caminho}: mais de uma linha da folha antiga"
    assert "/static/estilo/tokens.css" in texto, f"{caminho}: sem tokens.css (toda tela carrega os tokens primeiro)"
    caminho.write_text(texto.replace(ANTIGA, NOVA), encoding="utf-8")
    return True


if __name__ == "__main__":
    n = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if migrar(p):
            n += 1
            print("migrada:", p)
        else:
            print("sem a folha antiga (nada a fazer):", p)
    print(f"{n} tela(s) migrada(s)")
