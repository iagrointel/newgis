"""Item L5-01-d-widgets-pagina-menu, funções puras no node (web/js/widgets/seguro.js) e o registro:
URL segura recusa javascript:/data: fora de imagem/protocolo relativo; lista de domínios do embed; sandbox sem
allow-same-origin; Markdown mínimo; {campo} escapado; os manifestos do registro validam, com os 12 deste item
(texto e botão já existiam — ganharam aqui o `elemento` real e os campos de esquema que faltavam) presentes
entre eles."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def executar_js(codigo: str):
    processo = subprocess.run(
        ["node", "--input-type=module", "-e", codigo], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return json.loads(processo.stdout)


CABECALHO = "const s = await import('./web/js/widgets/seguro.js');\n"

VETORES_URL_RECUSADOS = [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "java\\tscript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
    "//evil.invalido/x",
    "file:///etc/passwd",
    "\\\\evil.invalido\\x",
    "sem-esquema/relativo",
]


def test_url_segura_recusa_os_vetores_e_aceita_o_normal():
    r = executar_js(
        CABECALHO
        + f"""
      const recusados = {json.dumps(VETORES_URL_RECUSADOS)}.map((u) => s.urlSegura(u));
      const aceitos = ['https://exemplo.invalido/a?b=1', 'http://exemplo.invalido', '/conteudo/x', 'mailto:a@b.c',
                       'tel:+5511'].map((u) => s.urlSegura(u));
      const imagem = [s.urlSegura('data:image/png;base64,iVBORw0KGgo=', {{imagem: true}}),
                      s.urlSegura('data:image/png;base64,iVBORw0KGgo='), s.urlSegura('mailto:a@b.c', {{imagem: true}})];
      console.log(JSON.stringify({{recusados, aceitos, imagem}}));
    """
    )
    assert r["recusados"] == [None] * len(VETORES_URL_RECUSADOS), r["recusados"]
    assert r["aceitos"] == [
        "https://exemplo.invalido/a?b=1",
        "http://exemplo.invalido/",
        "/conteudo/x",
        "mailto:a@b.c",
        "tel:+5511",
    ]
    assert r["imagem"][0].startswith("data:image/png") and r["imagem"][1] is None and r["imagem"][2] is None


def test_dominio_do_embed_e_sandbox():
    r = executar_js(
        CABECALHO
        + """
      console.log(JSON.stringify({
        sub: s.hostPermitido('https://mapas.exemplo.invalido/x', ['exemplo.invalido']),
        exato: s.hostPermitido('https://exemplo.invalido/', ['*.exemplo.invalido']),
        http: s.hostPermitido('http://exemplo.invalido/', ['exemplo.invalido']),
        sufixo_falso: s.hostPermitido('https://exemplo.invalido.mal.invalido/', ['exemplo.invalido']),
        vazio: s.hostPermitido('https://exemplo.invalido/', []),
        sandbox: s.sandboxDe(['allow-scripts', 'allow-same-origin', 'allow-top-navigation', 'allow-forms']),
      }));
    """
    )
    assert r == {
        "sub": True,
        "exato": True,
        "http": False,
        "sufixo_falso": False,
        "vazio": False,
        "sandbox": "allow-scripts allow-forms",
    }


def test_markdown_minimo_e_campos_da_feicao():
    r = executar_js(
        CABECALHO
        + """
      const md = ['# Título', '', 'Olá **{nome}** *it* `c` [site](https://x.invalido) [mal](javascript:alert(1))', '',
                  '- a', '- b', '', '1. um', '', '---',
                  '![alt](https://x.invalido/i.png) ![m](javascript:1)'].join('\\n');
      const feicao = {properties: {nome: '<img src=x onerror=alert(1)>'}};
      const html = s.markdownParaHtml(s.substituirCampos(md, feicao));
      console.log(JSON.stringify({html, campos: s.substituirCampos('{a} {b} {c}', {a: 1, b: '<x>'})}));
    """
    )
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
    esperados = {
        "texto",
        "imagem",
        "botao",
        "cartao",
        "incorporar",
        "divisor",
        "menu",
        "controlador",
        "compartilhar",
        "login",
        "idioma",
        "tema",
    }
    assert esperados <= set(r), esperados - set(r)
    # os 12 do item + os 10 que já existiam antes dele (L5-06/L5-07/L5-01-c: mapa, legenda, tabela, grafico,
    # lista, consulta, selecao, info-feicao, adicionar-dado, filtro) — sem duplicata nenhuma no registro.
    assert len(r) == len(set(r)) == 22, r


def test_widgets_do_item_usam_o_elemento_que_o_modulo_registra_de_verdade():
    """achado de 15/09: `botao`/`texto` já estavam no registro mas com `elemento: 'plat-botao'`/`'plat-texto'`
    — nomes que `web/js/widgets/base.js::definir` nunca registrou (o módulo define `plat-w-<nome>`, ver
    `botao.js`/`texto.js`); `document.createElement(manifesto.elemento)` criaria um elemento MORTO. Cobre os
    12 do item, que são os que este item entrega/corrige."""
    r = executar_js("""
      const { REGISTRO } = await import('./web/js/widgets/registro.js');
      const nomes = ["texto", "imagem", "botao", "cartao", "incorporar", "divisor", "menu", "controlador",
                     "compartilhar", "login", "idioma", "tema"];
      const saida = Object.fromEntries(nomes.map((n) => [n, REGISTRO.get(n).elemento]));
      console.log(JSON.stringify(saida));
    """)
    for nome, elemento in r.items():
        assert elemento == f"plat-w-{nome}", (nome, elemento)


def test_modulos_dos_widgets_novos_ficam_abaixo_de_60_kb():
    for nome in (
        "imagem",
        "cartao",
        "incorporar",
        "divisor",
        "menu",
        "controlador",
        "compartilhar",
        "login",
        "idioma",
        "tema",
        "seguro",
    ):
        assert (ROOT / "web/js/widgets" / f"{nome}.js").stat().st_size <= 60 * 1024, nome


def test_paleta_de_paginas_tem_os_nove_tipos_sem_colidir_com_menu_texto_imagem():
    """achado de 15/09 (comentário de `executor.js::TIPOS_WIDGET_PAGINA`): nove tipos do item batem por NOME
    entre `editor/paleta_paginas.js` e `widgets/registro.js` (botão, cartão, incorporar, divisor, controlador,
    compartilhar, login, idioma, tema); `texto`/`imagem` continuam com o esquema PRÓPRIO da paleta (o
    executor os desenha direto, não pelo motor) e o de menu vive na paleta como `menu_widget`, de propósito,
    para não pisar no tipo `menu` de navegação entre páginas (esquema totalmente diferente, já existente)."""
    r = executar_js("""
      const { PALETA_PAGINAS } = await import('./web/js/editor/paleta_paginas.js');
      const { REGISTRO } = await import('./web/js/widgets/registro.js');
      console.log(JSON.stringify({
        tipos: Object.keys(PALETA_PAGINAS.tipos),
        ordem: PALETA_PAGINAS.ordem,
        registro: [...REGISTRO.keys()],
      }));
    """)
    nove = {"botao", "cartao", "incorporar", "divisor", "controlador", "compartilhar", "login", "idioma", "tema"}
    assert nove <= set(r["tipos"]), nove - set(r["tipos"])
    assert nove <= set(r["registro"]), nove - set(r["registro"])
    assert "menu_widget" in r["tipos"] and "menu_widget" not in r["registro"]  # nome de propósito diferente
    assert set(r["ordem"]) == set(r["tipos"])  # toda chave de `tipos` está em `ordem` e vice-versa
    # os que colidem por acaso: paleta e registro têm o MESMO nome mas o executor nunca casa por ele
    assert {"texto", "imagem", "mapa", "tabela"} <= (set(r["tipos"]) & set(r["registro"]))


def test_executor_lista_so_os_nove_sem_colisao_em_tipos_de_widget_pagina():
    r = executar_js("""
      const { tiposDeWidget } = await import('./web/js/executor/executor.js');
      const nove = ["botao", "cartao", "incorporar", "divisor", "controlador",
                    "compartilhar", "login", "idioma", "tema"];
      const colisao = ["texto", "imagem", "mapa", "tabela", "menu", "menu_widget"];
      const nos = [...nove, ...colisao].map((tipo, i) => ({id: `n${i}`, tipo, pai: null, propriedades: {}}));
      const doc = {corpo: {nos}};
      console.log(JSON.stringify(tiposDeWidget(doc).sort()));
    """)
    assert r == sorted(
        ["botao", "cartao", "incorporar", "divisor", "controlador", "compartilhar", "login", "idioma", "tema"]
    )


def test_botao_com_acao_de_link_e_de_pagina_valida_no_esquema():
    """achado de 15/09: o manifesto de `botao` não tinha o campo `acao` — `validarEsquema` recusava
    `{rotulo, acao: {...}}` (que é como `botao.js` lê a configuração) como "campo desconhecido"."""
    r = executar_js("""
      const { obterManifesto, validarEsquema } = await import('./web/js/widgets/registro.js');
      const esquema = obterManifesto('botao').esquema_config;
      const saida = {};
      for (const [nome, config] of Object.entries({
        link: {rotulo: 'Ir', acao: {tipo: 'link', url: 'https://exemplo.invalido/x', nova_aba: true}},
        pagina: {rotulo: 'Ir', acao: {tipo: 'pagina', pagina: 'sobre'}},
        campo_estranho: {rotulo: 'Ir', acao: {tipo: 'link', bicho: 1}},
      })) {
        try { validarEsquema(config, esquema); saida[nome] = null; } catch (erro) { saida[nome] = erro.message; }
      }
      console.log(JSON.stringify(saida));
    """)
    assert r["link"] is None and r["pagina"] is None
    assert "campo desconhecido" in r["campo_estranho"]
