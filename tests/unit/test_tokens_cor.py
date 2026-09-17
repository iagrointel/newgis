"""Conserto do item L0-14-identidade-visual sobre a refutação do adversário G4: "56 literais de cor fora de
`web/estilo/tokens.css` (style.css 21, mapa.css 9, tarefas.css 9, conteudo.css 4, js 13) e a varredura que o
portão exige não existe em tests/ nem no Makefile".

Esta varredura percorre inteiro `web/**/*.css` (exceto `web/vendor/` e o próprio `web/estilo/tokens.css`), todo
`web/js/**/*.js` (exceto vendor) e também o CSS que mora DENTRO de HTML — bloco `<style>` e atributo
`style="..."` — porque ali a cor escapa de quem só olha arquivo `.css`. Reprova qualquer literal de cor
(`#rgb`, `#rrggbb[aa]`, `rgb()`, `rgba()`, `hsl()`, `hsla()` e companhia, e nome de cor CSS) fora de
`var(--...)`.

Depois do conserto do turno 5 o CSS do produto está em ZERO literal: nenhuma exceção de CSS existe mais. O que
sobra é JavaScript que NÃO pode usar `var(--...)` por construção — o estilo do MapLibre é JSON lido pelo canvas
e não resolve variável de CSS, a cena 3D e os gráficos em SVG puro idem — e a cor que ele escreve é cartografia
ou dado, não cromo do produto. Para esse resto a exceção não é "arquivo liberado": é ORÇAMENTO CONTADO, escrito
como `caminho/relativo @N  # motivo`. N é o número de linhas com literal de cor que aquele arquivo tem direito
de ter. Um literal novo faz a contagem passar de N e REPROVA; uma limpeza faz a contagem cair abaixo de N e
também reprova, obrigando a baixar o orçamento no mesmo commit. As formas `caminho/relativo` (arquivo inteiro)
e `caminho/relativo:linha` continuam aceitas para um caso pontual, mas nenhum arquivo do produto as usa hoje.

`tests/tokens_cor.excecoes` é a lista; cada linha traz motivo escrito, nunca um achado escondido sem explicação.
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


def _carregar_excecoes() -> tuple[dict[str, set[str]], dict[str, int]]:
    """devolve (marcas, orcamentos):
    - marcas: caminho -> {"*"} (arquivo inteiro) ou conjunto de números de linha em texto;
    - orcamentos: caminho -> N da forma `caminho @N` (número de linhas com literal que o arquivo pode ter)."""
    excecoes: dict[str, set[str]] = {}
    orcamentos: dict[str, int] = {}
    if not EXCECOES.exists():
        return excecoes, orcamentos
    for bruta in EXCECOES.read_text(encoding="utf-8").splitlines():
        linha = bruta.split("#", 1)[0].strip()
        if not linha:
            continue
        assert "#" in bruta, f"exceção sem motivo escrito: {bruta!r}"
        assert bruta.split("#", 1)[1].strip(), f"exceção com motivo vazio: {bruta!r}"
        if "@" in linha:
            caminho, _, n = linha.partition("@")
            orcamentos[caminho.strip()] = int(n.strip())
        elif ":" in linha:
            caminho, _, num = linha.rpartition(":")
            excecoes.setdefault(caminho, set()).add(num)
        else:
            excecoes.setdefault(linha, set()).add("*")
    return excecoes, orcamentos


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


RE_BLOCO_STYLE = re.compile(r"<style[^>]*>([\s\S]*?)</style>", re.I)
RE_ATRIBUTO_STYLE = re.compile(r"""style\s*=\s*["']([^"']*)["']""", re.I)


# As duas páginas de RENDER HEADLESS (item L2-12) não são tela do produto: são o viewport de um navegador sem
# interface que vira imagem. Não carregam tokens.css de propósito (nenhum cromo), e o fundo é o do canvas —
# preto de mapa numa, branco de papel na outra. São duas, nomeadas, e o teste abaixo confere que continuam
# sendo só estas duas e que cada uma diz isso no próprio arquivo.
PAGINAS_DE_RENDER = {"render_mapa.html", "render_layout_mapa.html"}


def _achados_html() -> list[tuple[str, int, str]]:
    """CSS embutido em HTML: bloco <style> e atributo style=. Mesma regra do arquivo .css."""
    achados = []
    for p in sorted(WEB.rglob("*.html")):
        if "vendor" in p.parts or p.name in PAGINAS_DE_RENDER:
            continue
        texto = p.read_text(encoding="utf-8")
        rel = str(p.relative_to(ROOT))
        for m in RE_BLOCO_STYLE.finditer(texto):
            base = texto.count("\n", 0, m.start(1))
            for n, linha in enumerate(_sem_comentarios_css(m.group(1)).splitlines(), 1):
                if linha.lstrip().startswith("@media"):
                    continue
                if _tem_cor(_fora_de_var(linha)):
                    achados.append((rel, base + n, linha.strip()[:120]))
        for m in RE_ATRIBUTO_STYLE.finditer(texto):
            if _tem_cor(_fora_de_var(m.group(1))):
                achados.append((rel, texto.count("\n", 0, m.start()) + 1, m.group(0).strip()[:120]))
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
    excecoes, orcamentos = _carregar_excecoes()
    todos = _achados_css() + _achados_html() + _achados_js()
    nao_justificados = [
        f"{rel}:{n}: {linha}"
        for rel, n, linha in todos
        if rel not in orcamentos and not _excluido(rel, n, excecoes)
    ]
    assert nao_justificados == [], (
        f"{len(nao_justificados)} literal(is) de cor fora de web/estilo/tokens.css e sem exceção justificada "
        f"em tests/tokens_cor.excecoes:\n" + "\n".join(nao_justificados)
    )


def test_nenhum_css_do_produto_tem_literal_de_cor():
    """a cláusula (a) do portão do item L0-14 em uma frase: CSS em zero, sem exceção nenhuma — arquivo .css e
    também o CSS embutido em HTML. Separado do teste acima de propósito: este não olha a lista de exceções,
    então nem uma exceção nova o silencia."""
    achados = [f"{rel}:{n}: {linha}" for rel, n, linha in _achados_css() + _achados_html()]
    assert achados == [], f"{len(achados)} literal(is) de cor em CSS fora de tokens.css:\n" + "\n".join(achados)


def test_orcamento_de_literal_em_js_bate_exatamente():
    """o JS que não pode usar var() (paint do MapLibre, cena 3D, SVG puro) tem orçamento contado por arquivo.
    Literal novo estoura o orçamento; limpeza feita sem baixar o número também reprova, para a lista não
    envelhecer sozinha."""
    _, orcamentos = _carregar_excecoes()
    reais: dict[str, int] = {}
    for rel, _n, _linha in _achados_css() + _achados_html() + _achados_js():
        reais[rel] = reais.get(rel, 0) + 1
    divergencias = []
    for caminho, previsto in sorted(orcamentos.items()):
        if not (ROOT / caminho).is_file():
            divergencias.append(f"{caminho}: arquivo não existe mais (apague a linha do orçamento)")
            continue
        achado = reais.get(caminho, 0)
        if achado != previsto:
            verbo = "cresceu" if achado > previsto else "caiu"
            divergencias.append(f"{caminho}: orçamento @{previsto}, medido {achado} ({verbo})")
    sem_orcamento = sorted(c for c in reais if c not in orcamentos)
    assert divergencias == [], "orçamento de literal de cor fora do combinado:\n" + "\n".join(divergencias)
    assert sem_orcamento == [], "arquivo com literal de cor e sem orçamento declarado:\n" + "\n".join(sem_orcamento)


def test_a_varredura_pega_um_literal_plantado_em_css_e_em_js():
    """CONTROLE POSITIVO: sem ele a varredura pode estar passando porque não olha nada. Planta um literal em
    arquivo de verdade dentro de web/ (e não em memória, para exercitar o mesmo caminho de disco que o teste
    de cima usa), confere que a varredura o encontra, e apaga o arquivo no fim, com ou sem falha."""
    casos = {
        "zz_controle_positivo.css": (".plantado { color: #ff00aa; }\n", _achados_css),
        "js/zz_controle_positivo.js": ("export const c = '#ff00aa';\n", _achados_js),
        "zz_controle_positivo.html": ("<style>.a { color: #ff00aa; }</style>\n", _achados_html),
        "zz_controle_atributo.html": ('<div style="color: #ff00aa"></div>\n', _achados_html),
    }
    for nome, (conteudo, varredura) in casos.items():
        alvo = WEB / nome
        antes = len(varredura())
        alvo.write_text(conteudo, encoding="utf-8")
        try:
            achados = varredura()
            rel = str(alvo.relative_to(ROOT))
            assert len(achados) == antes + 1, f"{nome}: a varredura não viu o literal plantado"
            assert any(r == rel for r, _n, _l in achados), f"{nome}: achado não aponta para o arquivo plantado"
        finally:
            alvo.unlink()
        assert len(varredura()) == antes, f"{nome}: a varredura não voltou ao estado anterior"

    # e o contrário: o que NÃO é cor não pode virar achado (senão o guarda vira ruído e alguém o desliga)
    limpo = WEB / "zz_controle_negativo.css"
    antes = len(_achados_css())
    limpo.write_text(".a { color: var(--i-acento); border: var(--i-fio) solid var(--i-linha); }\n", encoding="utf-8")
    try:
        assert len(_achados_css()) == antes, "a varredura acusou um arquivo que só usa var(--...)"
    finally:
        limpo.unlink()


def test_toda_excecao_declarada_ainda_existe_no_arquivo():
    """exceção órfã (arquivo apagado/renomeado ou linha que já não tem mais cor) é sinal de limpeza pendente —
    reprovar para a lista de exceções não crescer sem manutenção."""
    excecoes, orcamentos = _carregar_excecoes()
    achados = {(rel, n) for rel, n, _ in _achados_css() + _achados_html() + _achados_js()}
    achados_por_arquivo: dict[str, set[int]] = {}
    for rel, n in achados:
        achados_por_arquivo.setdefault(rel, set()).add(n)
    orfas = []
    for caminho, marcas in list(excecoes.items()) + [(c, set()) for c in orcamentos]:
        alvo = ROOT / caminho
        if not alvo.is_file():
            orfas.append(f"{caminho}: arquivo não existe mais")
            continue
        if marcas == {"*"} or not marcas:
            continue
        for num in marcas:
            if int(num) not in achados_por_arquivo.get(caminho, set()):
                orfas.append(f"{caminho}:{num}: não há mais literal de cor nesta linha")
    assert orfas == [], "exceção órfã em tests/tokens_cor.excecoes:\n" + "\n".join(orfas)


def test_as_paginas_de_render_sao_so_duas_e_se_declaram():
    """o único jeito de escapar da varredura de HTML é estar em PAGINAS_DE_RENDER. Então a lista é conferida:
    duas páginas, ambas existem, ambas dizem no próprio arquivo que são render sem cromo, e nenhuma delas
    carrega tokens.css (se carregasse, não haveria motivo para a exceção)."""
    assert PAGINAS_DE_RENDER == {"render_mapa.html", "render_layout_mapa.html"}
    for nome in sorted(PAGINAS_DE_RENDER):
        alvo = WEB / nome
        assert alvo.is_file(), nome
        texto = alvo.read_text(encoding="utf-8")
        assert "render" in texto.lower() and "sem" in texto.lower(), f"{nome} não explica que é página de render"
        assert "/static/estilo/tokens.css" not in texto, f"{nome} carrega tokens.css: apague a exceção"
