"""Saneador de HTML da descrição (ADR 0004 seção 2.4): script, onerror, javascript:, iframe, data: em img, HTML cru
no Markdown — nada sobrevive; tabela e link https sobrevivem; h1 vira h2; comentários somem."""

import pytest

from app.catalogo import texto

VETORES = [
    "<script>alert(1)</script>",
    '<img src="x" onerror="alert(1)">',
    '<a href="javascript:alert(1)">x</a>',
    '<iframe src="https://x"></iframe>',
    '<img src="data:image/png;base64,AAAA">',
    '<div style="background:url(javascript:1)">x</div>',
    "<object data='x'></object><embed src='x'>",
    "<svg onload=alert(1)></svg>",
    "<a href='https://x' onclick='alert(1)'>x</a>",
    "<!-- comentário --><p>x</p>",
    "<style>body{display:none}</style>",
    "<form action='https://x'><button>x</button></form>",
]


@pytest.mark.parametrize("vetor", VETORES)
def test_vetor_classico_nao_sobrevive(vetor):
    html = texto.markdown_para_html(vetor)
    baixo = html.lower()
    for proibido in (
        "<script",
        "onerror",
        "javascript:",
        "<iframe",
        "data:",
        "onload",
        "onclick",
        "<style",
        "<object",
        "<embed",
        "<svg",
        "<form",
        "<button",
        "<!--",
        "style=",
    ):
        assert proibido not in baixo, (vetor, html)


def test_markdown_com_tabela_e_link_https_sobrevive():
    md = "# Título\n\nTexto **forte** e [link](https://exemplo.gov.br/x).\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    html = texto.markdown_para_html(md)
    assert "<h2>Título</h2>" in html and "<strong>forte</strong>" in html
    assert '<a href="https://exemplo.gov.br/x" rel="noopener noreferrer">link</a>' in html
    assert "<table>" in html and "<td>1</td>" in html


def test_img_so_https_http_ou_api():
    assert '<img src="/api/itens/x/miniatura" />' in texto.sanear('<img src="/api/itens/x/miniatura">')
    assert "src=" not in texto.sanear('<img src="/etc/passwd">')
    assert "src=" not in texto.sanear('<img src=" JAVASCRIPT:x">')


def test_texto_escapado_e_none():
    assert texto.markdown_para_html(None) is None
    assert "&lt;b&gt;" in texto.sanear("&lt;b&gt;x")
    assert texto.sanear("a < b & c") == "a &lt; b &amp; c"


def test_tag_desconhecida_some_mas_conteudo_fica():
    assert texto.sanear("<span class='x'>texto</span>") == "texto"
    assert texto.sanear("<h1>t</h1><h6>u</h6>") == "<h2>t</h2><h4>u</h4>"
