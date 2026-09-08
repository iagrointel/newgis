"""e2e do item L5-04-a-blocos-de-conteudo (chromium do playwright), cláusula a cláusula do portão:

1. narrativa com 10 blocos de 8 tipos montada por ARRASTO (paleta → tela) e, num segundo item, só por TECLADO;
   os dois documentos gravados são idênticos (mesma forma canônica do e2e do L5-08);
2. o bloco de mapa reabre EXATAMENTE na vista salva: a vista é gravada pelo controle do painel ("Usar esta vista")
   e conferida no leitor por bbox, tolerância 1 % — refutação: 5 mapas com vistas diferentes reabertos em DOIS
   viewports (1280×800 e 480×900), deriva máxima gravada em tests/medidas;
3. imagem sem texto alternativo bloqueia a publicação com mensagem (botão Publicar do construtor) e, com o texto,
   publica por link (L5-14): a página /p/<inquilino>/<slug> abre ANÔNIMA num contexto novo com os blocos lidos;
4. refutação "injeta HTML no texto": <script>, onerror e javascript: no Markdown não chegam ao DOM da leitura;
5. 0 erro de console em todos os caminhos.
Precisa de `scripts/servir_local.py` (serve /static) — sem Martin, sem bancada."""

import json
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela, sufixo

ITEM = "L5-04-a-blocos-de-conteudo"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

SEQUENCIA = ["capa", "texto", "imagem", "mapa", "tabela", "botao", "separador", "incorporar", "texto", "imagem"]
VISTAS = [
    [-46.70, -23.60, -46.50, -23.45], [-46.65, -23.55, -46.60, -23.52], [-46.9, -23.8, -46.3, -23.3],
    [-46.62, -23.50, -46.58, -23.47], [-47.0, -24.0, -46.0, -23.0],
]


def _criar(admin_api, titulo, blocos=None):
    r = admin_api.post("/api/itens", data={"tipo": "narrativa", "titulo": titulo, "dados": {
        "tipo": "narrativa", "esquema_versao": 1, "corpo": {"nos": blocos or [], "ligacoes": []}}})
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _dados(admin_api, iid):
    r = admin_api.get(f"/api/itens/{iid}")
    assert r.status == 200, r.text()
    return r.json()


def _ulid(i):
    # ULID sintético válido (Crockford, primeiro dígito 0-7) e distinto por índice
    base = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return "0" + "".join(base[(i * 7 + k) % 32] for k in range(25))


def _blocos_de_teste(*tipos_props):
    return [{"id": _ulid(i + 1), "tipo": t, "pai": None, "largura_colunas": 12, "propriedades": p}
            for i, (t, p) in enumerate(tipos_props)]


def _canonico(dados):
    nos = dados["dados"]["corpo"]["nos"]
    return [{"tipo": n["tipo"], "pai": n.get("pai"), "largura": n.get("largura_colunas"),
             "propriedades": n.get("propriedades")} for n in nos]


def _abrir(tela, page, iid):
    tela.ir(f"/construtor?item={iid}")
    page.wait_for_selector("#tela", timeout=10000)


def _salvar(page):
    page.click("#salvar")
    page.wait_for_function("() => document.getElementById('estado-salvo').textContent.startsWith('gravado')",
                           timeout=10000)


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=False)


@pytest.fixture
def tela(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo

    def sem_origin(rota):
        cab = {k: v for k, v in rota.request.headers.items() if k.lower() != "origin"}
        rota.fulfill(response=rota.fetch(headers=cab))
    # o servidor local não é a URL pública da trilha: a guarda de CSRF compara o Origin (mesma decisão dos
    # e2e do L2-01-f e L2-01-i); as escritas do construtor saem sem Origin
    page.route("**/api/itens/**", sem_origin)
    t = Tela(page, base_url)
    t.entrar(slug, login, senha)
    yield t
    page.unroute_all(behavior="ignoreErrors")


def test_dez_blocos_de_oito_tipos_por_arrasto_e_por_teclado(tela, page, admin_api, medida):
    grava = medida(ITEM)
    # --- por arrasto
    id_a = _criar(admin_api, f"zt-narrativa-arrasto-{sufixo()}")
    _abrir(tela, page, id_a)
    for tipo in SEQUENCIA:
        caixa = page.locator("#tela").bounding_box()
        page.drag_and_drop(f'[data-paleta="{tipo}"]', "#tela", target_position={"x": 20, "y": caixa["height"] - 6})
    page.wait_for_function("() => document.querySelectorAll('#tela .no-editor').length === 10", timeout=10000)
    _salvar(page)
    _capturar(page, "editor_arrasto")
    d1 = _dados(admin_api, id_a)
    # --- por teclado (botão Adicionar da paleta, Enter)
    id_t = _criar(admin_api, f"zt-narrativa-teclado-{sufixo()}")
    _abrir(tela, page, id_t)
    for tipo in SEQUENCIA:
        page.focus(f'[data-adicionar="{tipo}"]')
        page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelectorAll('#tela .no-editor').length === 10", timeout=10000)
    # reordenar por teclado: o último bloco (imagem) sobe uma posição — e o mesmo é feito por arrasto no outro item
    ultimo = page.locator("#tela .no-editor").nth(9).get_attribute("data-no")
    page.focus(f'[data-arvore="{ultimo}"]')
    page.keyboard.press("Alt+ArrowUp")
    page.wait_for_function("(id) => document.querySelectorAll('#tela .no-editor')[8].dataset.no === id", arg=ultimo,
                           timeout=5000)
    _salvar(page)
    d2 = _dados(admin_api, id_t)
    # o item do arrasto recebe a mesma reordenação, por arrasto (soltar SOBRE um nó = entrar antes dele)
    _abrir(tela, page, id_a)
    nos = page.locator("#tela .no-editor")
    page.drag_and_drop(f'[data-no="{nos.nth(9).get_attribute("data-no")}"] > .no-cabecalho',
                       f'[data-no="{nos.nth(8).get_attribute("data-no")}"]')
    page.wait_for_function("() => document.querySelectorAll('#tela .no-editor')[9].dataset.tipo === 'texto'",
                           timeout=5000)
    _salvar(page)
    d1 = _dados(admin_api, id_a)
    c1, c2 = _canonico(d1), _canonico(d2)
    assert c1 == c2, json.dumps({"arrasto": c1, "teclado": c2}, ensure_ascii=False, indent=1)
    assert [n["tipo"] for n in c1] == SEQUENCIA[:8] + ["imagem", "texto"]
    assert len({n["tipo"] for n in c1}) == 8 and all(n["pai"] is None and n["largura"] == 12 for n in c1)
    tela.verificar()
    grava("blocos", 10, "blocos", "e2e: 10 blocos de 8 tipos por arrasto == por teclado")
    grava("diferenca_arrasto_teclado", 0, "campos", "canônico(arrasto) == canônico(teclado)")


def test_mapa_reabre_na_vista_salva_em_dois_viewports(tela, page, admin_api, medida, playwright, browser):
    grava = medida(ITEM)
    blocos = _blocos_de_teste(("capa", {"titulo": "Mapas"}),
                              *[("mapa", {"legenda": f"vista {i + 1}"}) for i in range(5)])
    iid = _criar(admin_api, f"zt-narrativa-mapas-{sufixo()}", blocos)
    _abrir(tela, page, iid)
    # a vista de cada bloco é gravada pelo CONTROLE do painel: enquadrar o mapa do painel e "Usar esta vista"
    for i, bbox in enumerate(VISTAS):
        no = blocos[i + 1]["id"]
        page.click(f'[data-no="{no}"]')
        page.wait_for_selector(f'[data-vista-de="{no}"][data-pronto="1"]', timeout=30000)
        page.evaluate("([id, b]) => document.querySelector(`[data-vista-de=\"${id}\"]`).platMapa.map"
                      ".fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 0, duration: 0 })", [no, bbox])
        page.wait_for_timeout(200)
        page.click(f'[data-usar-vista="{no}"]')
        page.wait_for_function("(id) => document.querySelector(`[data-vista-estado=\"${id}\"]`).textContent"
                               ".startsWith('vista salva')", arg=no, timeout=5000)
    _capturar(page, "editor_vista_mapa")
    _salvar(page)
    d = _dados(admin_api, iid)
    vistas = [n["propriedades"]["vista"] for n in d["dados"]["corpo"]["nos"] if n["tipo"] == "mapa"]
    assert len(vistas) == 5 and all("bbox" in v and "proporcao" in v for v in vistas)
    # a caixa gravada pelo controle é a que o mapa do painel mostrava (o fitBounds do próprio controle)
    for v, bbox in zip(vistas, VISTAS, strict=True):
        assert abs((v["bbox"][2] - v["bbox"][0]) - (bbox[2] - bbox[0])) / (bbox[2] - bbox[0]) < 0.05 \
            or abs((v["bbox"][3] - v["bbox"][1]) - (bbox[3] - bbox[1])) / (bbox[3] - bbox[1]) < 0.05

    # reabrir no leitor em dois viewports: deriva do bbox ≤ 1 % em todos os 5 mapas
    derivas = {}
    for largura, altura in ((1280, 800), (480, 900)):
        page.set_viewport_size({"width": largura, "height": altura})
        tela.ir(f"/executar?item={iid}")
        page.wait_for_function("() => document.querySelectorAll('.bloco-mapa-quadro[data-pronto=\"1\"]').length === 5",
                               timeout=60000)
        page.wait_for_timeout(300)
        medidas = page.evaluate("""() => [...document.querySelectorAll('.bloco-mapa-quadro')].map((q) => {
            const m = q.platMapa.map; const b = m.getBounds();
            return { id: q.dataset.bloco, bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
                     largura: q.clientWidth, altura: q.clientHeight };
        })""")
        for m, v in zip(medidas, vistas, strict=True):
            o, s, le, n = v["bbox"]
            bo, bs, bl, bn = m["bbox"]
            deriva = max(abs((bl - bo) - (le - o)) / (le - o), abs((bn - bs) - (n - s)) / (n - s),
                         abs((bl + bo) / 2 - (le + o) / 2) / (le - o), abs((bn + bs) / 2 - (n + s) / 2) / (n - s))
            derivas[f"{largura}x{altura}:{m['id']}"] = deriva
            assert deriva <= 0.01, (largura, m, v, deriva)
        _capturar(page, f"leitor_{largura}x{altura}")
    grava("deriva_maxima_vista_mapa", round(max(derivas.values()), 5), "fração",
          "5 mapas × 2 viewports: |bbox lido − bbox salvo| / bbox salvo")
    grava("mapas_conferidos", len(derivas), "medições", "5 vistas em 1280×800 e 480×900")
    tela.verificar()


def test_imagem_sem_texto_alternativo_bloqueia_e_com_texto_publica_por_link(tela, page, admin_api, playwright,
                                                                             base_url):
    blocos = _blocos_de_teste(("capa", {"titulo": "Publicação", "subtitulo": "com imagem"}),
                              ("texto", {"markdown": "# Um título\n\nUm parágrafo com **negrito**."}),
                              ("imagem", {"url": "/static/favicon.svg", "alternativo": "", "legenda": "logotipo"}),
                              ("separador", {}), ("botao", {"rotulo": "Site", "url": "https://exemplo.org"}))
    iid = _criar(admin_api, f"zt-narrativa-publica-{sufixo()}", blocos)
    _abrir(tela, page, iid)
    page.on("dialog", lambda d: d.accept())
    tela.esperar_status(422)
    page.click("#publicar")
    page.wait_for_selector('#publicado-em[data-estado="recusado"]', timeout=15000)
    aviso = page.text_content("#aviso") or ""
    assert "texto alternativo" in aviso and "imagem" in aviso, aviso
    _capturar(page, "publicacao_recusada")
    # o autor preenche o texto alternativo no painel e publica
    page.click(f'[data-no="{blocos[2]["id"]}"]')
    page.fill('[data-prop="alternativo"]', "logotipo da plataforma")
    page.keyboard.press("Tab")
    _salvar(page)
    page.click("#publicar")
    page.wait_for_selector("#link-publicado", timeout=15000)
    url = page.get_attribute("#link-publicado", "href")
    assert "/p/demo/" in url
    _capturar(page, "publicacao_ok")
    tela.verificar()
    # leitura ANÔNIMA por link, num contexto novo (sem cookie): os blocos estão lá, com o texto alternativo
    ctx = playwright.chromium.launch().new_context(base_url=base_url, viewport={"width": 1000, "height": 800})
    try:
        p2 = ctx.new_page()
        erros = []
        p2.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        p2.goto(url, wait_until="domcontentloaded")
        p2.wait_for_selector("article.narrativa", timeout=20000)
        assert p2.locator("article.narrativa .bloco").count() == 5
        assert p2.get_attribute("article.narrativa img", "alt") == "logotipo da plataforma"
        assert p2.locator("article.narrativa h1").first.text_content() == "Publicação"
        assert p2.locator("article.narrativa .bloco-texto strong").text_content() == "negrito"
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        p2.screenshot(path=str(CAPTURAS / f"{ITEM}_publicada_anonima.png"))
        assert erros == [], erros
    finally:
        ctx.close()


def test_html_hostil_no_texto_e_sanitizado(tela, page, admin_api):
    hostil = ("Antes <script>window.__xss = 1</script> depois\n\n<img src=x onerror=\"window.__xss = 2\">\n\n"
              "[clique](javascript:window.__xss=3) e <a href=\"javascript:window.__xss=4\">outro</a>\n\n"
              "<style>@import url('https://fora.invalido/x.css')</style> <iframe src=\"https://fora.invalido\"></iframe>")
    blocos = _blocos_de_teste(("texto", {"markdown": hostil}),
                              ("tabela", {"cabecalho": "a | <b>b</b>", "linhas": "<script>x</script> | 2"}))
    iid = _criar(admin_api, f"zt-narrativa-xss-{sufixo()}", blocos)
    tela.ir(f"/executar?item={iid}")
    page.wait_for_selector("article.narrativa .bloco-texto", timeout=15000)
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__xss") is None
    # nada executável chega ao DOM: nem elemento, nem atributo de evento, nem href javascript: (o texto hostil
    # pode sobreviver como TEXTO escapado — isso é o correto, e por isso a conferência é por elemento/atributo)
    perigosos = page.evaluate(r"""() => {
      const a = document.querySelector('article.narrativa');
      return { tags: [...a.querySelectorAll('script, style, iframe, object, embed, form')].map((e) => e.tagName),
               eventos: [...a.querySelectorAll('*')]
                 .filter((e) => [...e.attributes].some((x) => /^on/i.test(x.name))).length,
               js: [...a.querySelectorAll('[href], [src]')].map((e) => e.getAttribute('href') || e.getAttribute('src'))
                     .filter((v) => /^\s*javascript:/i.test(v)).length };
    }""")
    assert perigosos == {"tags": [], "eventos": 0, "js": 0}, perigosos
    assert page.locator("article.narrativa table td").first.text_content() == "<script>x</script>"  # texto, não HTML
    assert page.locator("article.narrativa table th").nth(1).text_content() == "<b>b</b>"
    _capturar(page, "texto_hostil")
    tela.verificar()
