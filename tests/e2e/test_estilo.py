"""Item L0-14-identidade-visual, cláusulas que exigem navegador (chromium do playwright):
(d) os 6 componentes de base nos 7 estados, montados com os elementos reais em /estilo;
(e) a página /estilo é gerada dos tokens: o número de tokens que ela mostra é o número de tokens do arquivo;
(f) contraste AA medido em claro e escuro em todas as telas: para cada nó de texto visível, cor calculada sobre o
    fundo composto (percorre os ancestrais até achar fundo opaco, compõe alfa), razão WCAG 2 (1.4.3); texto
    normal exige 4,5:1, texto grande (>= 24 px, ou >= 18,66 px em negrito) 3:1. axe-core roda por cima quando
    existe no disco (PLAT_AXE_JS ou os caminhos conhecidos; nunca vendorizado aqui) e não pode ter violação
    crítica ou séria;
(g) captura antes e depois de cada tela em tests/e2e/capturas/L0-14_<tela>_{antes,depois_escuro,depois_claro}.png
    (o "antes" vem da URL de produção, PLAT_URL_ANTES, uma vez; se o arquivo já existe, não é regravado);
(h) a régua existe nas telas: contagem do título com procedência da chamada real, linha de procedência no rodapé,
    etiqueta visível com foco de teclado.
Medidas gravadas em tests/medidas/L0-14.json (PLAT_GRAVAR_MEDIDAS=1), com o comando."""
# ruff: noqa: E501 -- o JS de medição de contraste e os seletores longos ficam em uma linha por legibilidade do próprio JS

import json
import os
import re
from pathlib import Path

import pytest

from tests.e2e.apoio import RAIZ, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-14"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
TELAS = [
    ("inicio", "/"), ("conta", "/conta"), ("usuarios", "/admin/usuarios"), ("grupos", "/admin/grupos"),
    ("papeis", "/admin/papeis"), ("tokens", "/admin/tokens"), ("log", "/admin/log"), ("organizacao", "/admin/organizacao"),
    ("tarefas", "/tarefas"), ("conteudo", "/conteudo"), ("conexoes", "/conexoes"), ("uploads", "/uploads"),
    ("mapa", "/mapa"), ("estilo", "/estilo"),
]
TELAS_PUBLICAS = [("entrar", "/entrar?inquilino=demo"), ("redefinir_senha", "/redefinir-senha")]
AXE_CANDIDATOS = [os.environ.get("PLAT_AXE_JS", ""), "/home/dev/tribuna/node_modules/axe-core/axe.min.js",
                  "/home/dev/teletech/web/node_modules/axe-core/axe.min.js"]

# mede o contraste de todo nó de texto visível; devolve as violações e o total de nós medidos
JS_CONTRASTE = r"""
() => {
  const rgb = (s) => { const m = s.match(/rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\)/); return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null; };
  const lum = ({ r, g, b }) => { const f = (c) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const compor = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const fundoDe = (el) => {
    let camadas = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      const c = rgb(cs.backgroundColor);
      if (c && c.a > 0) { camadas.push(c); if (c.a >= 1) break; }
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && !/gradient/.test(cs.backgroundImage)) return null;
    }
    let base = rgb(getComputedStyle(document.documentElement).backgroundColor);
    if (!base || base.a < 1) base = { r: 255, g: 255, b: 255, a: 1 };
    let cor = base;
    for (let i = camadas.length - 1; i >= 0; i--) cor = compor(camadas[i], cor);
    return cor;
  };
  const violacoes = []; let medidos = 0;
  const andar = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const vistos = new Set();
  for (let n = andar.nextNode(); n; n = andar.nextNode()) {
    if (!n.nodeValue.trim()) continue;
    const el = n.parentElement;
    if (!el || vistos.has(el)) continue;
    vistos.add(el);
    if (el.closest('script, style, noscript, [hidden], .sr-only, .maplibregl-ctrl, dialog:not([open]), .regua-texto')) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (el.closest('[disabled], [aria-disabled="true"]')) continue;
    const frente0 = rgb(cs.color); if (!frente0) continue;
    const fundo = fundoDe(el); if (!fundo) continue;
    const frente = frente0.a < 1 ? compor(frente0, fundo) : frente0;
    const la = lum(frente), lb = lum(fundo);
    const razao = (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
    const px = parseFloat(cs.fontSize); const peso = parseInt(cs.fontWeight, 10) || 400;
    const grande = px >= 24 || (px >= 18.66 && peso >= 700);
    const minimo = grande ? 3 : 4.5;
    medidos++;
    if (razao < minimo) {
      const sel = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '');
      violacoes.push({ sel, texto: n.nodeValue.trim().slice(0, 40), razao: Math.round(razao * 100) / 100, minimo, cor: cs.color, fundo: `rgb(${Math.round(fundo.r)}, ${Math.round(fundo.g)}, ${Math.round(fundo.b)})` });
    }
  }
  return { medidos, violacoes };
}
"""


def _axe_js() -> str | None:
    for c in AXE_CANDIDATOS:
        if c and Path(c).is_file():
            return c
    return None


def _capturar(page, nome: str) -> Path:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{nome}.png"
    page.screenshot(path=str(caminho), full_page=True)
    return caminho


def _ir(tela: Tela, caminho: str) -> None:
    tela.page.goto(caminho, wait_until="domcontentloaded")
    tela.page.wait_for_selector("body[data-pronto='1']", timeout=30000)


@pytest.fixture(scope="module")
def sessao(playwright, base_url, url_publica_resolve, credenciais_demo):
    """um contexto por módulo (Playwright é caro; 8 bancadas dividem 12 núcleos): entra uma vez, navega tudo."""
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    navegador = playwright.chromium.launch()
    ctx = navegador.new_context(base_url=base_url, locale="pt-BR", viewport={"width": 1280, "height": 800}, color_scheme="dark")
    page = ctx.new_page()
    tela = Tela(page, base_url)
    slug, login, senha = credenciais_demo
    tela.entrar(slug, login, senha, "/")
    yield tela
    ctx.close()
    navegador.close()


def test_g_captura_antes_da_url_de_producao(playwright):
    """'antes' = as telas como estão na URL de produção (código anterior ao item), uma vez; arquivo existente não é
    regravado, para o par antes/depois sobreviver ao deploy deste próprio item."""
    url = os.environ.get("PLAT_URL_ANTES", "https://plat.iagrointel.com").rstrip("/")
    cred_arquivo = Path(os.environ.get("PLAT_CREDENCIAIS_ANTES", "/home/dev/plataforma/enterprise/tests/credenciais.txt"))
    faltam = [n for n, _ in TELAS + TELAS_PUBLICAS if not (CAPTURAS / f"{ITEM}_{n}_antes.png").exists()]
    if not faltam:
        pytest.skip("capturas 'antes' já existem; não regravar")
    if not cred_arquivo.exists():
        pytest.skip(f"sem credenciais de produção em {cred_arquivo}")
    cred = {}
    for linha in cred_arquivo.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3:
            cred[partes[0]] = (partes[1], partes[2])
    if "demo" not in cred:
        pytest.skip("credenciais de produção sem inquilino demo")
    navegador = playwright.chromium.launch()
    ctx = navegador.new_context(base_url=url, locale="pt-BR", viewport={"width": 1280, "height": 800}, color_scheme="dark")
    page = ctx.new_page()
    try:
        page.goto("/entrar?inquilino=demo", wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=30000)
        for nome, caminho in TELAS_PUBLICAS:
            if nome in faltam:
                page.goto(caminho, wait_until="domcontentloaded")
                page.wait_for_selector("body[data-pronto='1']", timeout=30000)
                _capturar(page, f"{nome}_antes")
        page.goto("/entrar?inquilino=demo&proximo=/", wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=30000)
        page.fill("#login", cred["demo"][0])
        page.fill("#senha", cred["demo"][1])
        page.click("#entrar")
        page.wait_for_url(lambda u: "/entrar" not in u, timeout=30000)
        for nome, caminho in TELAS:
            if nome not in faltam:
                continue
            r = page.goto(caminho, wait_until="domcontentloaded")
            if r is not None and r.status == 404:
                continue  # tela que ainda não existe na produção (por exemplo /estilo): sem 'antes'
            try:
                page.wait_for_selector("body[data-pronto='1']", timeout=30000)
            except Exception:  # noqa: BLE001 - tela sem marca de pronto na produção: captura o que há
                pass
            _capturar(page, f"{nome}_antes")
        page.request.post(f"{url}/api/logout", data={})
    finally:
        ctx.close()
        navegador.close()
    assert any((CAPTURAS / f"{ITEM}_{n}_antes.png").exists() for n, _ in TELAS)


@pytest.mark.parametrize("tema", ["escuro", "claro"])
def test_f_g_contraste_aa_e_captura_depois(sessao: Tela, tema, medida):
    page = sessao.page
    page.emulate_media(color_scheme="dark" if tema == "escuro" else "light")
    page.evaluate("() => { try { localStorage.removeItem('plat_tema'); } catch {} document.documentElement.removeAttribute('data-theme'); }")
    axe = _axe_js()
    axe_fonte = Path(axe).read_text(encoding="utf-8") if axe else None
    total_medidos = 0
    violacoes = {}
    axe_por_impacto = {}
    sessao.esperar_status(404)  # /conteudo/{id} inexistente e afins não contam; a lista abaixo é de telas
    for nome, caminho in TELAS + TELAS_PUBLICAS:
        if nome == "entrar" or nome == "redefinir_senha":
            continue  # públicas: capturadas ao fim, fora da sessão
        _ir(sessao, caminho)
        page.wait_for_timeout(250)
        assert page.evaluate("() => getComputedStyle(document.body).backgroundColor") != "rgba(0, 0, 0, 0)"
        r = page.evaluate(JS_CONTRASTE)
        total_medidos += r["medidos"]
        if r["violacoes"]:
            violacoes[nome] = r["violacoes"]
        if axe_fonte:
            page.add_script_tag(content=axe_fonte)
            res = page.evaluate("() => axe.run(document, { runOnly: ['color-contrast', 'focus-order-semantics', 'aria-allowed-attr', 'button-name', 'link-name', 'label'] })")
            for v in res.get("violations", []):
                axe_por_impacto.setdefault(v.get("impact") or "desconhecido", []).append(f"{nome}: {v['id']} ({len(v.get('nodes', []))} nós)")
        _capturar(page, f"{nome}_depois_{tema}")
    # públicas, sem sessão: nova aba no mesmo contexto (o cookie não atrapalha: /entrar redireciona só com sessão válida na tela)
    for nome, caminho in TELAS_PUBLICAS:
        _ir(sessao, caminho)
        page.wait_for_timeout(150)
        r = page.evaluate(JS_CONTRASTE)
        total_medidos += r["medidos"]
        if r["violacoes"]:
            violacoes[nome] = r["violacoes"]
        _capturar(page, f"{nome}_depois_{tema}")
    _ir(sessao, "/")
    gravar = medida(ITEM)
    gravar(f"contraste_{tema}_nos_medidos", total_medidos, "nós de texto",
           f"tests/e2e/test_estilo.py JS_CONTRASTE em {len(TELAS) + len(TELAS_PUBLICAS)} telas, color_scheme={tema}, chromium do playwright")
    gravar(f"contraste_{tema}_violacoes_aa", sum(len(v) for v in violacoes.values()), "nós abaixo de 4,5:1 (3:1 texto grande)",
           "mesma varredura; fórmula (L1+0,05)/(L2+0,05) sobre cor calculada e fundo composto pelos ancestrais")
    if axe_fonte:
        gravar(f"axe_{tema}_violacoes", {k: len(v) for k, v in axe_por_impacto.items()}, "violações por impacto",
               f"axe.run(document, runOnly color-contrast+nomes+rótulos) com {axe} injetado por add_script_tag")
    assert violacoes == {}, json.dumps(violacoes, ensure_ascii=False, indent=1)
    graves = axe_por_impacto.get("critical", []) + axe_por_impacto.get("serious", [])
    assert graves == [], graves
    sessao.verificar()


def test_e_pagina_estilo_e_gerada_dos_tokens_e_mostra_os_estados(sessao: Tela, medida):
    page = sessao.page
    page.emulate_media(color_scheme="dark")
    _ir(sessao, "/estilo")
    css = (RAIZ / "web" / "estilo" / "tokens.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*[\s\S]*?\*/", "", css)
    no_arquivo = len(set(re.findall(r"(--i-[a-z0-9-]+)\s*:", css)))
    na_pagina = int(re.search(r"\((\d+)\)", page.text_content("#tokens-n")).group(1))
    assert na_pagina == no_arquivo, (na_pagina, no_arquivo)
    assert page.locator("#tokens-tabela tbody tr").count() == no_arquivo
    # paleta: toda razão de contraste texto × superfície medida na página é AA
    marcadores = page.locator("#paleta .contraste .marcador").all_text_contents()
    assert marcadores and all(m == "AA" for m in marcadores), marcadores
    # (d) 6 componentes × 7 estados presentes, com os elementos reais
    for comp in ("plat-aviso", "plat-busca", "plat-formulario", "plat-paginacao", "plat-tabela", "plat-dialogo"):
        for estado in ("repouso", "foco", "ativo", "desativado", "carregando", "vazio", "erro"):
            assert page.locator(f'[data-componente="{comp}"] [data-estado="{estado}"]').count() == 1, (comp, estado)
    assert page.locator('[data-componente="plat-tabela"] [data-estado="carregando"] plat-tabela[aria-busy="true"]').count() == 1
    assert page.locator('[data-componente="plat-tabela"] [data-estado="erro"] td.erro-linha button').count() == 1
    assert page.locator('[data-componente="plat-busca"] [data-estado="erro"] input[aria-invalid="true"]').count() == 1
    assert page.locator('[data-componente="plat-formulario"] [data-estado="vazio"] .form-vazio').count() == 1
    assert page.locator('[data-componente="plat-aviso"] [data-estado="carregando"] plat-aviso[aria-busy="true"]').count() == 1
    # (c) família de ícones inteira desenhada
    icones_js = (RAIZ / "web" / "js" / "base" / "icones.js").read_text(encoding="utf-8")
    familia = len(set(re.findall(r"^\s{2}([a-z_]+):\s*\[", icones_js, re.M)))
    assert page.locator("#icones .ic").count() == familia
    assert page.locator("#icones .ic svg").count() == familia
    # tema e densidade: botões reais
    page.click('#controle-tema button[data-tema="claro"]')
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") == "light"
    assert page.evaluate("() => localStorage.getItem('plat_tema')") == "claro"
    e4_normal = page.evaluate("() => { const s = document.createElement('div'); s.style.width = 'var(--i-e4)'; document.body.append(s); const w = s.getBoundingClientRect().width; s.remove(); return w; }")
    page.click('#controle-densidade button[data-densidade="compacta"]')
    e4_compacta = page.evaluate("() => { const s = document.createElement('div'); s.style.width = 'var(--i-e4)'; document.body.append(s); const w = s.getBoundingClientRect().width; s.remove(); return w; }")
    assert e4_compacta < e4_normal, (e4_compacta, e4_normal)
    page.click('#controle-densidade button[data-densidade="normal"]')
    page.click('#controle-tema button[data-tema="sistema"]')
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") is None
    gravar = medida(ITEM)
    gravar("tokens_no_arquivo", no_arquivo, "tokens --i-*", "grep -o -- '--i-[a-z0-9-]*:' web/estilo/tokens.css | sort -u | wc -l")
    gravar("icones_na_familia", familia, "ícones", "grep -cE '^  [a-z_]+: \\[' web/js/base/icones.js")
    gravar("componentes_x_estados", 6 * 7, "caixas em /estilo", "playwright: [data-componente] [data-estado] count por par")
    sessao.verificar()


def test_h_regua_nas_telas(sessao: Tela, medida):
    page = sessao.page
    page.emulate_media(color_scheme="dark")
    _ir(sessao, "/admin/usuarios")
    page.wait_for_selector("main > h1 .regua", timeout=15000)
    proc = page.get_attribute("main > h1 .regua", "data-procedencia")
    assert "GET /api/usuarios" in proc and "instante" in proc, proc
    assert re.search(r"\(\d+\)", page.text_content("main > h1 .regua")), page.text_content("main > h1 .regua")
    # o texto do título continua só com o número: a procedência vai no aria-label, não no textContent
    assert "procedência" not in page.text_content("main > h1")
    assert "procedência" in page.get_attribute("main > h1 .regua", "aria-label")
    # rodapé: linha de procedência com a chamada real
    itens = page.locator("main .regua-tela li").all_text_contents()
    assert any("/api/usuarios" in i for i in itens), itens
    assert any(re.search(r"\d{2}:\d{2}:\d{2} UTC", i) for i in itens), itens
    # foco de teclado mostra a etiqueta (::after visível)
    page.focus("main > h1 .regua")
    page.wait_for_timeout(400)  # transição de opacidade de --i-tempo (150 ms)
    opac = page.evaluate("() => getComputedStyle(document.querySelector('main > h1 .regua'), '::after').opacity")
    assert opac == "1", opac
    page.evaluate("() => document.activeElement.blur()")
    page.wait_for_timeout(400)
    opac2 = page.evaluate("() => getComputedStyle(document.querySelector('main > h1 .regua'), '::after').opacity")
    assert opac2 == "0", opac2
    # página inicial: versão e saúde com procedência e comando de conferência
    _ir(sessao, "/")
    assert "cat VERSAO" in page.get_attribute("#versao-numero", "data-procedencia")
    assert "GET /saude" in page.get_attribute("#saude-estado", "data-procedencia")
    gravar = medida(ITEM)
    gravar("regua_telas_com_linha_de_procedencia", len(TELAS), "telas", "montarLayout() chama reguaTela() em toda tela com sessão (web/js/base/layout.js)")
    sessao.verificar()
