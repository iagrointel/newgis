"""Gera `docs/LIMITES.md` a partir de `app/limites.py` (item L0-12, decisão de docs/CONTRATO_API.md seção
"Limites"; ADR 0002 seção 11 e ADR 0004 seção 14 já apontam para cá). NÃO editar LIMITES.md à mão: o valor que
aparece ali é o `repr()` do valor que o Python importou do módulo, não um número digitado de novo — é assim que
o teste (`tests/unit/test_limites_doc.py`) confere "número no doc = número no código" sem duplicar a lista.

`python3 docs/gerar_limites.py` escreve o arquivo; `--check` só confere e sai != 0 se estiver desatualizado
(usado no teste e em `make limites`). Agrupa pelas seções `# ---` do arquivo, na ordem em que aparecem; o
único valor não escalar (`AUTH_PADROES`, um dicionário) ganha sua própria subtabela (chave, padrão, mínimo,
máximo), na mesma forma que a ADR 0002 seção 11 já usa em prosa."""

import argparse
import importlib
import re
import sys
import tokenize
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:  # roda como `python docs/gerar_limites.py`, sem PYTHONPATH=.
    sys.path.insert(0, str(RAIZ))
ORIGEM = RAIZ / "app" / "limites.py"
DESTINO = RAIZ / "docs" / "LIMITES.md"

RE_SECAO = re.compile(r"^#\s*---\s*(.+?)\s*$")
RE_NOME = re.compile(r"^([A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=")


def _comentarios_por_linha() -> dict[int, str]:
    """{linha: texto do comentário} via tokenize — não confunde '#' com string nem quebra em valor multi-linha."""
    saida = {}
    with ORIGEM.open("rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.COMMENT:
                saida[tok.start[0]] = tok.string.lstrip("#").strip()
    return saida


def _secoes_e_nomes() -> list[tuple[str, list[tuple[str, int]]]]:
    """[(nome_da_secao, [(NOME_DA_CONSTANTE, linha_da_atribuicao), ...])], na ordem do arquivo."""
    secoes: list[tuple[str, list[tuple[str, int]]]] = []
    atual, nomes = "geral", []
    for numero, linha in enumerate(ORIGEM.read_text(encoding="utf-8").splitlines(), start=1):
        m_secao = RE_SECAO.match(linha)
        if m_secao:
            if nomes:
                secoes.append((atual, nomes))
            atual, nomes = m_secao.group(1), []
            continue
        m_nome = RE_NOME.match(linha)
        if m_nome:
            nomes.append((m_nome.group(1), numero))
    if nomes:
        secoes.append((atual, nomes))
    return secoes


def gerar_markdown() -> str:
    modulo = importlib.import_module("app.limites")
    comentarios = _comentarios_por_linha()
    partes = [
        "# Limites da plataforma\n",
        "Gerado de `app/limites.py` por `docs/gerar_limites.py` (`make limites`); não editar à mão — "
        "`tests/unit/test_limites_doc.py` falha se este arquivo divergir do código, e a coluna \"valor\" é o "
        "`repr()` do que o Python leu do módulo, nunca um número digitado de novo (ADR 0001 seção 12, regra "
        "1). O comentário ao lado da constante no código é a explicação, quando houver.\n",
    ]
    for secao, nomes in _secoes_e_nomes():
        partes.append(f"\n## {secao}\n")
        partes.append("| nome | valor | explicação |")
        partes.append("|---|---|---|")
        for nome, linha in nomes:
            valor = getattr(modulo, nome)
            if isinstance(valor, dict):
                partes.append(f"| `{nome}` | *(dicionário; ver subtabela abaixo)* | {comentarios.get(linha, '—')} |")
            else:
                partes.append(f"| `{nome}` | `{valor!r}` | {comentarios.get(linha, '—')} |")
        for nome, _ in nomes:
            valor = getattr(modulo, nome)
            if isinstance(valor, dict):
                partes.append(f"\n### `{nome}`\n")
                partes.append("| chave | padrão | mínimo | máximo |")
                partes.append("|---|---|---|---|")
                for chave, (padrao, minimo, maximo) in valor.items():
                    partes.append(f"| `{chave}` | `{padrao!r}` | `{minimo!r}` | `{maximo!r}` |")
    return "\n".join(partes) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="não escreve; sai != 0 se LIMITES.md estiver desatualizado")
    args = ap.parse_args()
    novo = gerar_markdown()
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != novo:
            print("docs/LIMITES.md desatualizado em relação a app/limites.py; rode: make limites", file=sys.stderr)
            raise SystemExit(1)
        return
    DESTINO.write_text(novo, encoding="utf-8")
    print(f"escrito: {DESTINO}")


if __name__ == "__main__":
    main()
