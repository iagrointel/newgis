"""Guarda do sistema de design (item UX-01-sistema-de-design): nenhuma cor nem tamanho literal fora de
`web/estilo/tokens.css`. Varre `web/**` (fora vendor/ e dados/):

- CSS: cor literal (#hex, rgb()/rgba(), hsl()/hsla(), nome de cor CSS em valor de propriedade) em qualquer arquivo
  que não seja tokens.css; tamanho literal (px/rem/em/pt, exceto 0) nas propriedades de ESCALA font-size, line-height,
  border-radius, gap, row-gap, column-gap, padding*, margin* (largura, altura, grid e posição são layout, não token;
  bordas de 1 px e outline entram por token mas não são varridas).
- HTML e JS: cor literal dentro de `style="..."`, de `.style.<prop> =` e de objetos `{ style: ... }`; e `font-size`/
  `padding`/`margin` literal dentro desses mesmos trechos. Cores em JS fora de estilo (âncoras `#senha`, ids) não
  contam; a cartografia do MapLibre (js/mapa/estilo.js lê JSON, não CSS) entra pela lista de exceções.

Exceções: `web/estilo/tokens_excecoes.json` — {arquivo, motivo}, uma por linha, sempre com motivo.

Uso: `python3 docs/verificar_tokens.py` lista as ocorrências (`arquivo:linha: trecho`) e sai 1 se houver alguma;
o teste `tests/unit/test_tokens_visuais.py` chama `ocorrencias()` e exige lista vazia."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "web"
TOKENS = WEB / "estilo" / "tokens.css"
EXCECOES = WEB / "estilo" / "tokens_excecoes.json"

NOMES_DE_COR = (
    "white|black|red|green|blue|yellow|orange|gray|grey|silver|navy|teal|purple|pink|brown|cyan|magenta|"
    "aqua|lime|maroon|olive|fuchsia|gold|coral|salmon|crimson|indigo|violet|khaki|ivory|beige|tan|wheat"
)
RE_COR = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|(?<=:)\s*(?:" + NOMES_DE_COR + r")\b"
    r"|(?<=\s)(?:" + NOMES_DE_COR + r")(?=\s*[;)])"
)
PROPRIEDADES_ESCALA = (
    r"font-size|line-height|border-radius|gap|row-gap|column-gap|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?"
)
RE_TAMANHO = re.compile(
    r"(?:^|[;{\s])(" + PROPRIEDADES_ESCALA + r")\s*:\s*([^;}]*)", re.IGNORECASE
)
RE_UNIDADE = re.compile(r"(?<![\w.-])(?!0(?:px|rem|em|pt)\b)\d*\.?\d+(?:px|rem|em|pt)\b")
RE_ESTILO_HTML = re.compile(r"""style\s*=\s*"([^"]*)\"""")
RE_ESTILO_JS = re.compile(r"""\.style\.[A-Za-z]+\s*=\s*([^;\n]*)|[{,]\s*style\s*:\s*([^,}\n]*)""")
RE_COMENTARIO_CSS = re.compile(r"/\*.*?\*/", re.DOTALL)


def _excecoes() -> dict[str, str]:
    if not EXCECOES.exists():
        return {}
    dados = json.loads(EXCECOES.read_text(encoding="utf-8"))
    return {e["arquivo"]: e["motivo"] for e in dados.get("excecoes", [])}


def _arquivos() -> list[Path]:
    saida = []
    for p in sorted(WEB.rglob("*")):
        if not p.is_file() or p.suffix not in (".css", ".html", ".js"):
            continue
        if "vendor" in p.parts or "dados" in p.parts or p == TOKENS:
            continue
        saida.append(p)
    return saida


def _linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def _apagar_comentarios(texto: str) -> str:
    """mantém as quebras de linha para o número da linha bater"""
    return RE_COMENTARIO_CSS.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), texto)


def _ocorrencias_css(texto: str, rel: str) -> list[str]:
    saida = []
    limpo = _apagar_comentarios(texto)
    for m in RE_COR.finditer(limpo):
        saida.append(f"{rel}:{_linha_de(limpo, m.start())}: cor literal `{m.group(0).strip()}`")
    for m in RE_TAMANHO.finditer(limpo):
        valor = m.group(2)
        if RE_UNIDADE.search(valor):
            saida.append(f"{rel}:{_linha_de(limpo, m.start(1))}: tamanho literal em {m.group(1)}: `{valor.strip()}`")
    return saida


def _ocorrencias_estilo_embutido(texto: str, rel: str, trechos) -> list[str]:
    saida = []
    for m in trechos:
        trecho = next((g for g in m.groups() if g), "")
        if not trecho:
            continue
        if RE_COR.search(trecho) or (RE_TAMANHO.search(trecho) and RE_UNIDADE.search(trecho)):
            saida.append(f"{rel}:{_linha_de(texto, m.start())}: estilo embutido com literal `{trecho.strip()[:80]}`")
    return saida


def ocorrencias() -> list[str]:
    exc = _excecoes()
    saida = []
    for arq in _arquivos():
        rel = str(arq.relative_to(RAIZ))
        if rel in exc:
            continue
        texto = arq.read_text(encoding="utf-8", errors="replace")
        if arq.suffix == ".css":
            saida.extend(_ocorrencias_css(texto, rel))
        elif arq.suffix == ".html":
            saida.extend(_ocorrencias_estilo_embutido(texto, rel, RE_ESTILO_HTML.finditer(texto)))
            for m in re.finditer(r"<style[^>]*>(.*?)</style>", texto, re.DOTALL):
                saida.extend(f"{rel}:{_linha_de(texto, m.start()) + int(o.split(':')[1]) - 1}: {o.split(': ', 1)[1]}"
                             for o in _ocorrencias_css(m.group(1), rel))
        else:
            saida.extend(_ocorrencias_estilo_embutido(texto, rel, RE_ESTILO_JS.finditer(texto)))
    return saida


def excecoes_sem_arquivo() -> list[str]:
    return [a for a in _excecoes() if not (RAIZ / a).is_file()]


def main() -> int:
    lista = ocorrencias()
    for o in lista:
        print(o)
    orfas = excecoes_sem_arquivo()
    for a in orfas:
        print(f"exceção sem arquivo: {a}")
    print(f"{len(lista)} ocorrência(s) fora de tokens.css; {len(orfas)} exceção(ões) órfã(s)")
    return 1 if lista or orfas else 0


if __name__ == "__main__":
    sys.exit(main())
