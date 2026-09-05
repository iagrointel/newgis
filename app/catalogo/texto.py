"""Descrição e termos de uso: Markdown guardado como texto e convertido no servidor para HTML saneado por lista de
permissão própria sobre html.parser (ADR 0004 seção 2.4). Nenhuma tag fora da lista sobrevive; `script`, `style`,
`iframe`, `object`, `embed`, `svg`, `math` somem com o conteúdo; atributos `on*`, `style` e URLs `javascript:`/`data:`
nunca passam; `href`/`src` só https://, http:// ou caminho que comece por /api/."""

import html
from html.parser import HTMLParser

import markdown

PERMITIDAS = frozenset(
    {
        "p",
        "br",
        "hr",
        "h2",
        "h3",
        "h4",
        "strong",
        "em",
        "del",
        "code",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "a",
        "img",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
)
VAZIAS = frozenset({"br", "hr", "img"})
COM_CONTEUDO_REMOVIDO = frozenset(
    {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "template",
        "noscript",
        "textarea",
        "select",
        "button",
        "form",
    }
)
REBAIXADAS = {"h1": "h2", "h5": "h4", "h6": "h4", "b": "strong", "i": "em", "s": "del", "strike": "del"}
ATRIBUTOS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}


def url_permitida(valor: str) -> bool:
    v = (valor or "").strip().lower().replace("\n", "").replace("\r", "").replace("\t", "")
    return v.startswith(("https://", "http://", "/api/"))


class _Saneador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._remover = 0

    def handle_starttag(self, tag, attrs):
        tag = REBAIXADAS.get(tag, tag)
        if tag in COM_CONTEUDO_REMOVIDO:
            self._remover += 1
            return
        if self._remover or tag not in PERMITIDAS:
            return
        saida = [tag]
        for nome, valor in attrs:
            nome = nome.lower()
            if nome not in ATRIBUTOS.get(tag, set()):
                continue
            if nome in ("href", "src") and not url_permitida(valor or ""):
                continue
            if nome in ("colspan", "rowspan") and not (valor or "").isdigit():
                continue
            saida.append(f'{nome}="{html.escape(valor or "", quote=True)}"')
        if tag == "a":
            saida.append('rel="noopener noreferrer"')
        self.partes.append("<" + " ".join(saida) + (" />" if tag in VAZIAS else ">"))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = REBAIXADAS.get(tag, tag)
        if tag in COM_CONTEUDO_REMOVIDO:
            self._remover = max(0, self._remover - 1)
            return
        if self._remover or tag not in PERMITIDAS or tag in VAZIAS:
            return
        self.partes.append(f"</{tag}>")

    def handle_data(self, dados):
        if not self._remover:
            self.partes.append(html.escape(dados, quote=False))

    def handle_comment(self, dados):
        return

    def handle_decl(self, decl):
        return

    def handle_pi(self, dados):
        return


def sanear(html_bruto: str) -> str:
    s = _Saneador()
    s.feed(html_bruto or "")
    s.close()
    return "".join(s.partes)


def markdown_para_html(texto: str | None) -> str | None:
    """Markdown → HTML (extensões tables e fenced_code) → saneado. None entra, None sai."""
    if texto is None:
        return None
    bruto = markdown.markdown(texto, extensions=["tables", "fenced_code"], output_format="html")
    return sanear(bruto)
