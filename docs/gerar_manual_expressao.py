"""Gera a seção "Linguagem de expressão" de `MANUAL.md` a partir do CÓDIGO (item L5-11).

Mesmo padrão de `docs/gerar_limites.py`: o que aparece no manual é o que o Python importou de
`app.expressao.avaliador_py.TABELA_FUNCOES` e de `app.expressao.perfis.PERFIS`, nunca um texto
digitado de novo — é assim que `tests/unit/test_expressao_manual.py` confere "função no manual =
função no código" (com UM exemplo por função, que é a cláusula do portão) sem duplicar a lista.

    python3 docs/gerar_manual_expressao.py            # reescreve o trecho entre os marcadores
    python3 docs/gerar_manual_expressao.py --check    # só confere; sai != 0 se estiver desatualizado
"""

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
DESTINO = RAIZ / "MANUAL.md"
INICIO = "<!-- inicio: catalogo de expressao gerado por docs/gerar_manual_expressao.py -->"
FIM = "<!-- fim: catalogo de expressao gerado por docs/gerar_manual_expressao.py -->"


def _aridade(minimo: int, maximo: int | None) -> str:
    if maximo == minimo:
        return str(minimo)
    if maximo is None:
        return f"{minimo} ou mais"
    return f"{minimo}-{maximo}"


def gerar_markdown() -> str:
    from app.expressao.avaliador_py import TABELA_FUNCOES
    from app.expressao.perfis import PERFIS

    linhas = [
        "",
        "### Perfis (onde a expressão é usada)",
        "",
        "| perfil | tipo de valor que tem de devolver | orçamento de tempo | para que serve |",
        "|---|---|---|---|",
    ]
    for nome, perfil in PERFIS.items():
        tipos = " · ".join(perfil["tipos"])
        linhas.append(f"| `{nome}` | {tipos} | {perfil['limite_ms']} ms | {perfil['descricao']} |")
    linhas += [
        "",
        f"### Catálogo de funções ({len(TABELA_FUNCOES)}), uma linha e um exemplo por função",
        "",
        "| função | argumentos | o que faz | exemplo |",
        "|---|---|---|---|",
    ]
    for nome, (minimo, maximo, descricao, exemplo) in TABELA_FUNCOES.items():
        linhas.append(f"| `{nome}` | {_aridade(minimo, maximo)} | {descricao} | `{exemplo}` |")
    linhas.append("")
    return "\n".join(linhas)


def _partes(texto: str) -> tuple[str, str]:
    if INICIO not in texto or FIM not in texto:
        raise SystemExit(f"MANUAL.md sem os marcadores {INICIO} / {FIM}")
    antes, resto = texto.split(INICIO, 1)
    _meio, depois = resto.split(FIM, 1)
    return antes, depois


def texto_esperado() -> str:
    antes, depois = _partes(DESTINO.read_text(encoding="utf-8"))
    return antes + INICIO + "\n" + gerar_markdown() + FIM + depois


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="só confere, não escreve")
    args = p.parse_args()
    esperado = texto_esperado()
    if DESTINO.read_text(encoding="utf-8") == esperado:
        return 0
    if args.check:
        print("MANUAL.md desatualizado: rode python3 docs/gerar_manual_expressao.py", file=sys.stderr)
        return 1
    DESTINO.write_text(esperado, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
