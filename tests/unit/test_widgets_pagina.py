"""Item L5-01-d-widgets-pagina-menu, funções puras no node (web/js/widgets/seguro.js) e o registro:
URL segura recusa javascript:/data: fora de imagem/protocolo relativo; lista de domínios do embed; sandbox sem
allow-same-origin; Markdown mínimo; {campo} escapado; os 16 manifestos do registro validam (12 deste item)."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def executar_js(codigo: str):
    processo = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=ROOT, text=True,
                              capture_output=True, check=True)
    return json.loads(processo.stdout)


CABECALHO = "const s = await import('./web/js/widgets/seguro.js');\n"

VETORES_URL_RECUSADOS = [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "java\\tscript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==", "vbscript:msgbox(1)", "//evil.invalido/x",
    "file:///etc/passwd", "\\\\evil.invalido\\x", "sem-esquema/relativo",
]


def test_url_segura_recusa_os_vetores_e_aceita_o_normal():
    r = executar_js(CABECALHO + f"""
      const recusados = {json.dumps(VETORES_URL_RECUSADOS)}.map((u) => s.urlSegura(u));
      const aceitos = ['https://exemplo.invalido/a?b=1', 'http://exemplo.invalido', '/conteudo/x', 'mailto:a@b.c',
                       'tel:+5511'].map((u) => s.urlSegura(u));
      const imagem = [s.urlSegura('data:image/png;base64,iVBORw0KGgo=', {{imagem: true}}),
                      s.urlSegura('data:image/png;base64,iVBORw0KGgo='), s.urlSegura('mailto:a@b.c', {{imagem: true}})];
      console.log(JSON.stringify({{recusados, aceitos, imagem}}));
    """)
    assert r["recusados"] == [None] * len(VETORES_URL_RECUSADOS), r["recusados"]
    assert r["aceitos"] == ["https://exemplo.invalido/a?b=1", "http://exemplo.invalido/", "/conteudo/x", "mailto:a@b.c",
                            "tel:+5511"]
    assert r["imagem"][0].startswith("data:image/png") and r["imagem"][1] is None and r["imagem"][2] is None


def test_dominio_do_embed_e_sandbox():
    r = executar_js(CABECALHO + """
      console.log(JSON.stringify({
        sub: s.hostPermitido('https://mapas.exemplo.invalido/x', ['exemplo.invalido']),
        exato: s.hostPermitido('https://exemplo.invalido/', ['*.exemplo.invalido']),
        http: s.hostPermitido('http://exemplo.invalido/', ['exemplo.invalido']),
        sufixo_falso: s.hostPermitido('https://exemplo.invalido.mal.invalido/', ['exemplo.invalido']),
        vazio: s.hostPermitido('https://exemplo.invalido/', []),
        sandbox: s.sandboxDe(['allow-scripts', 'allow-same-origin', 'allow-top-navigation', 'allow-forms']),
      }));
    """)
    assert r == {"sub": True, "exato": True, "http": False, "sufixo_falso": False, "vazio": False,
                 "sandbox": "allow-scripts allow-forms"}


def test_markdown_minimo_e_campos_da_feicao():
    r = executar_js(CABECALHO + """
      const md = ['# Título', '', 'Olá **{nome}** *it* `c` [site](https://x.invalido) [mal](javascript:alert(1))', '',
                  '- a', '- b', '', '1. um', '', '---',
                  '![alt](https://x.invalido/i.png) ![m](javascript:1)'].join('\\n');
      const feicao = {properties: {nome: '<img src=x onerror=alert(1)>'}};
      const html = s.markdownParaHtml(s.substituirCampos(md, feicao));
      console.log(JSON.stringify({html, campos: s.substituirCampos('{a} {b} {c}', {a: 1, b: '<x>'})}));
    """)
    html = r["html"]
    assert html.startswith("<h1>Título</h1>")
    assert "<strong>&lt;img src=x onerror=alert(1)&gt;</strong>" in html  # o valor da feição chega escapado
    assert '<a href="https://x.invalido/" rel="noopener noreferrer">site</a>' in html
    # link recusado vira texto, nunca href
    assert 'href="javascript' not in html and "[mal](javascript:alert(1))" in html
    assert "<ul>\n<li>a</li>\n<li>b</li>\n</ul>" in html and "<ol>\n<li>um</li>\n</ol>" in html
    assert "<hr>" in html
    assert '<img src="https://x.invalido/i.png" alt="alt">' in html
    assert "![m](javascript:1)" in html
    assert r["campos"] == "1 &lt;x&gt; {c}"


def test_registro_tem_os_doze_widgets_do_item_com_manifesto_valido():
    r = executar_js("""
      const { REGISTRO, validarManifesto } = await import('./web/js/widgets/registro.js');
      const nomes = [...REGISTRO.values()].map((m) => { validarManifesto(m); return m.nome; });
      console.log(JSON.stringify(nomes));
    """)
    esperados = {"texto", "imagem", "botao", "cartao", "incorporar", "divisor", "menu", "controlador", "compartilhar",
                 "login", "idioma", "tema"}
    assert esperados <= set(r), esperados - set(r)
    assert len(r) == 16


def test_modulos_dos_widgets_novos_ficam_abaixo_de_60_kb():
    for nome in ("imagem", "cartao", "incorporar", "divisor", "menu", "controlador", "compartilhar", "login", "idioma",
                 "tema", "seguro"):
        assert (ROOT / "web/js/widgets" / f"{nome}.js").stat().st_size <= 60 * 1024, nome
