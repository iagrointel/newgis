"""Conserto do item L0-14-identidade-visual sobre a refutação do adversário G4: "56 literais de cor fora de
`web/estilo/tokens.css` (style.css 21, mapa.css 9, tarefas.css 9, conteudo.css 4, js 13) e a varredura que o
portão exige não existe em tests/ nem no Makefile".

Esta varredura percorre inteiro `web/**/*.css` (exceto `web/vendor/` e o próprio `web/estilo/tokens.css`) e todo
`web/js/**/*.js` (exceto vendor) e reprova qualquer literal de cor (`#rgb`/`#rrggbb[aa]`, `rgb()`/`rgba()`/
`hsl()`/`hsla()`/... e nome de cor CSS) fora de `var(--...)`. Exceções (uma por linha, `caminho/relativo` ou
`caminho/relativo:linha`, seguidas de `  # motivo`) moram em `tests/tokens_cor.excecoes` — cada uma justificada
por escrito, nunca usada para esconder um achado sem explicação.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
TOKENS = WEB / "estilo" / "tokens.css"
EXCECOES = ROOT / "tests" / "tokens_cor.excecoes"

COR_HEX = re.compile(r"(?<![\w#/])#[0-9a-fA-F]{3,8}\b")
COR_FUNCAO = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(\s*[\d.]")
COR_NOME = re.compile(
    r"(?<![\w-])(?:white|black|red|green|blue|yellow|orange|gray|grey|silver|navy|teal|purple|cyan|magenta|"
    r"lime|maroon|olive|aqua|fuchsia|crimson|gold|indigo|violet|pink|brown|beige|tan|salmon|coral|khaki|"
    r"lavender|ivory|linen|snow|azure|tomato|chocolate|whitesmoke|gainsboro|dimgray|dimgrey|darkgray|"
    r"lightgray|lightgrey|darkgrey|slategray|slategrey|steelblue|royalblue|dodgerblue|skyblue|deepskyblue|"
    r"firebrick|darkred|darkgreen|darkblue|seagreen|forestgreen|goldenrod|orangered|hotpink|deeppink|"
    r"turquoise|plum|orchid|wheat|peru|sienna|honeydew|mintcream|aliceblue)(?![\w-])"
)

# string/template literal completo (aspas simples, duplas ou crase) — em JS só o CONTEÚDO de string conta
# como literal de cor; código como `function rgb(texto)` ou `/conta#2fa` não é cor.
STRING_JS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`", re.S)


def _sem_comentarios_css(texto: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", texto)


def _sem_comentarios_js(texto: str) -> str:
    texto = re.sub(r"/\*[\s\S]*?\*/", "", texto)
    return re.sub(r"(^|[^:\\'\"])//[^\n]*", r"\1", texto)


def _fora_de_var(linha: str) -> str:
    """apaga só `var(--nome)` SEM valor de reserva (essa forma não pode esconder cor). `var(--nome, #fallback)`
    fica de pé de propósito: um literal escrito como reserva do var() ainda é um literal escrito à mão — se a
    variável falhar, é ele que aparece na tela — então continua sujeito à varredura."""
    return re.sub(r"var\(--[\w-]+\)", "", linha)


def _tem_cor(texto: str) -> bool:
    return bool(COR_HEX.search(texto) or COR_FUNCAO.search(texto) or COR_NOME.search(texto))


def _carregar_excecoes() -> dict[str, set[str]]:
    """chave = caminho relativo; valor = {"*"} (arquivo inteiro) ou conjunto de números de linha em texto."""
    excecoes: dict[str, set[str]] = {}
    if not EXCECOES.exists():
        return excecoes
    for bruta in EXCECOES.read_text(encoding="utf-8").splitlines():
        linha = bruta.split("#", 1)[0].strip()
        if not linha:
            continue
        assert "#" in bruta, f"exceção sem motivo escrito: {bruta!r}"
        if ":" in linha:
            caminho, _, num = linha.rpartition(":")
            excecoes.setdefault(caminho, set()).add(num)
        else:
            excecoes.setdefault(linha, set()).add("*")
    return excecoes


def _excluido(rel: str, numero: int, excecoes: dict[str, set[str]]) -> bool:
    marcas = excecoes.get(rel)
    if not marcas:
        return False
    return "*" in marcas or str(numero) in marcas


def _achados_css() -> list[tuple[str, int, str]]:
    achados = []
    for p in sorted(WEB.rglob("*.css")):
        if "vendor" in p.parts or p == TOKENS:
            continue
        texto = _sem_comentarios_css(p.read_text(encoding="utf-8"))
        for n, linha in enumerate(texto.splitlines(), 1):
            if linha.lstrip().startswith("@media"):
                continue
            if _tem_cor(_fora_de_var(linha)):
                achados.append((str(p.relative_to(ROOT)), n, linha.strip()[:120]))
    return achados


def _achados_js() -> list[tuple[str, int, str]]:
    achados = []
    for p in sorted(WEB.rglob("*.js")):
        if "vendor" in p.parts:
            continue
        texto = _sem_comentarios_js(p.read_text(encoding="utf-8"))
        for n, linha in enumerate(texto.splitlines(), 1):
            for m in STRING_JS.finditer(linha):
                if _tem_cor(_fora_de_var(m.group(0))):
                    achados.append((str(p.relative_to(ROOT)), n, linha.strip()[:120]))
                    break
    return achados


def test_nenhum_literal_de_cor_fora_dos_tokens_e_das_excecoes_justificadas():
    excecoes = _carregar_excecoes()
    todos = _achados_css() + _achados_js()
    nao_justificados = [
        f"{rel}:{n}: {linha}" for rel, n, linha in todos if not _excluido(rel, n, excecoes)
    ]
    assert nao_justificados == [], (
        f"{len(nao_justificados)} literal(is) de cor fora de web/estilo/tokens.css e sem exceção justificada "
        f"em tests/tokens_cor.excecoes:\n" + "\n".join(nao_justificados)
    )


def test_toda_excecao_declarada_ainda_existe_no_arquivo():
    """exceção órfã (arquivo apagado/renomeado ou linha que já não tem mais cor) é sinal de limpeza pendente —
    reprovar para a lista de exceções não crescer sem manutenção."""
    excecoes = _carregar_excecoes()
    achados = {(rel, n) for rel, n, _ in _achados_css() + _achados_js()}
    achados_por_arquivo: dict[str, set[int]] = {}
    for rel, n in achados:
        achados_por_arquivo.setdefault(rel, set()).add(n)
    orfas = []
    for caminho, marcas in excecoes.items():
        alvo = ROOT / caminho
        if not alvo.is_file():
            orfas.append(f"{caminho}: arquivo não existe mais")
            continue
        if marcas == {"*"}:
            continue
        for num in marcas:
            if int(num) not in achados_por_arquivo.get(caminho, set()):
                orfas.append(f"{caminho}:{num}: não há mais literal de cor nesta linha")
    assert orfas == [], "exceção órfã em tests/tokens_cor.excecoes:\n" + "\n".join(orfas)
