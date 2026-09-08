"""Modelos 3D no navegador de verdade (item L2-09-c-modelos-gltf-ifc-3dtiles).

Cada teste é uma cláusula do portão de pronto:

  * o GLB aparece na POSIÇÃO e na ESCALA corretas — a caixa envolvente do que o navegador desenhou é
    comparada com a que o servidor calculou, canto a canto, com folga de 0,5 m;
  * o modelo é realmente DESENHADO (prova de pixel: a tela com o modelo difere da tela sem ele);
  * clique num elemento mostra as propriedades daquele elemento, com captura de tela;
  * a árvore 3D Tiles carrega pelo deck.gl e os quadros por segundo são medidos com a carga da máquina
    gravada ao lado (tests/medidas), nunca um número solto;
  * nenhum erro de console no caminho inteiro.

Sobe o SEU servidor (scripts/servir_local.py) na base da trilha, em porta livre — nunca as unidades da
máquina. Sem a bancada (`scripts/modelo3d_demo.py criar`) ou sem o chromium do playwright, os testes
SALTAM dizendo o motivo; nunca passam por omissão.
"""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import psycopg2
import pytest

RAIZ = Path(__file__).resolve().parents[2]
CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L2-09-c-modelos-gltf-ifc-3dtiles"
TITULO_CENA = "cena-modelos (L2-09-c)"
NOME_CASA = "modelo-casa (L2-09-c)"
NOME_CAIXA = "modelo-caixa (L2-09-c)"
FAIXA_PORTAS = range(8400, 8470)
TOLERANCIA_M = 0.5      # a folga que o portão do item declara
FPS_ALVO = 30.0

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _porta_livre(usadas: set[int]) -> int:
    for p in FAIXA_PORTAS:
        if p in usadas:
            continue
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                usadas.add(p)
                return p
    raise RuntimeError("nenhuma porta livre na faixa deste papel")


def _esperar(url: str, segundos: float = 40.0) -> bool:
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            httpx.get(url, timeout=2, verify=False)  # noqa: S501 — certificado do próprio teste
            return True
        except httpx.HTTPError:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def portas():
    return set()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="module")
def servidor(env, portas, tmp_path_factory):
    """Servidor da trilha em HTTPS: a defesa de CSRF compara Origin com PLAT_URL_PUBLICA, que só aceita
    https. Em produção quem termina o TLS é o nginx."""
    porta = _porta_livre(portas)
    pasta = tmp_path_factory.mktemp("tls-modelos")
    cert, chave = pasta / "cert.pem", pasta / "chave.pem"
    gerado = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
         "-keyout", str(chave), "-out", str(cert)], capture_output=True)
    if gerado.returncode != 0:
        pytest.skip("openssl não gerou o certificado do servidor de teste")
    url = f"https://127.0.0.1:{porta}"
    proc = subprocess.Popen(
        [str(RAIZ / "venv" / "bin" / "python"), str(RAIZ / "scripts" / "servir_local.py"),
         "--porta", str(porta), "--cert", str(cert), "--chave", str(chave)],
        cwd=str(RAIZ), env={**os.environ, "PLAT_URL_PUBLICA": url},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _esperar(f"{url}/api/saude"):
        proc.terminate()
        pytest.skip(f"servidor local da trilha não subiu em {url}")
    yield {"url": url}
    proc.terminate()
    proc.wait(timeout=20)


@pytest.fixture(scope="module")
def bancada(env):
    """(id da cena, ids dos modelos, caixa que o SERVIDOR calculou) lidos da base da trilha."""
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()
            if adm is None:
                pytest.skip("inquilino demo sem admin semeado")
            cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(adm["tenant_id"]),))
            cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(adm["usuario_id"]),))
            cur.execute("SELECT id FROM plat.item WHERE titulo = %s AND tipo = 'cena' AND apagado_em IS NULL "
                        "ORDER BY criado_em DESC LIMIT 1", (TITULO_CENA,))
            cena = cur.fetchone()
            cur.execute("SELECT id, nome, caixa, estado, tileset, elementos FROM plat.modelo3d "
                        "WHERE nome IN (%s, %s)", (NOME_CASA, NOME_CAIXA))
            modelos = {r["nome"]: r for r in cur.fetchall()}
    finally:
        con.close()
    if not cena or len(modelos) != 2:
        pytest.skip("bancada do item ausente: rode venv/bin/python scripts/modelo3d_demo.py criar")
    return {"cena": str(cena["id"]),
            "casa": {**modelos[NOME_CASA], "id": str(modelos[NOME_CASA]["id"])},
            "caixa": {**modelos[NOME_CAIXA], "id": str(modelos[NOME_CAIXA]["id"])}}


@pytest.fixture(scope="module")
def credenciais_trilha(env):
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (RAIZ / "tests" / "credenciais.txt"))
    if not caminho.exists():
        pytest.skip("sem arquivo de credenciais da trilha")
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3 and partes[0] == "demo":
            return partes
    pytest.skip("arquivo de credenciais sem a linha do inquilino demo")


@pytest.fixture
def cena_aberta(page, servidor, bancada, credenciais_trilha):
    erros: list[str] = []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: erros.append(f"pedido falhou: {r.url} ({r.failure})"))
    page.on("response", lambda r: erros.append(f"resposta {r.status}: {r.url}") if r.status >= 400 else None)
    slug, login, senha = credenciais_trilha
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{servidor['url']}/entrar?inquilino={slug}&proximo=/", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)
    page.fill("#login", login)
    page.fill("#senha", senha)
    page.click("#entrar")
    page.wait_for_url(lambda u: "/entrar" not in u, timeout=30000)
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)
    page.goto(f"{servidor['url']}/cena?item={bancada['cena']}", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)
    page.wait_for_function("() => window.plat && window.plat.cena && window.plat.cena.modelos", timeout=30000)
    return {"page": page, "erros": erros, "base": servidor["url"]}


def _esperar_modelo(page, modelo_id, tempo=60000):
    page.wait_for_function(
        """(id) => {
             const c = window.plat.cena.modelos.camadas.get(id);
             return !!(c && (c.pronto || c.erro));
           }""", arg=modelo_id, timeout=tempo)
    erro = page.evaluate("(id) => (window.plat.cena.modelos.camadas.get(id) || {}).erro || null",
                         modelo_id)
    assert erro is None, f"a camada do modelo não montou: {erro}"


# ---------------------------------------------------------------- cláusulas
def test_o_glb_aparece_na_posicao_e_na_escala_declaradas(cena_aberta, bancada, medida):
    """Cláusula do portão: a caixa projetada bate com a esperada a menos de 0,5 m, canto a canto."""
    from app.modelos3d import posicionamento

    page = cena_aberta["page"]
    _esperar_modelo(page, bancada["casa"]["id"])
    desenhada = page.evaluate("(id) => window.plat.cena.modelos.camadas.get(id).caixaGeografica()",
                              bancada["casa"]["id"])
    esperada = bancada["casa"]["caixa"]
    assert desenhada, "o navegador não devolveu a caixa do modelo desenhado"
    piores = []
    for eixo in ("oeste", "leste"):
        piores.append(posicionamento.distancia_m((desenhada[eixo], esperada["sul"]),
                                                 (esperada[eixo], esperada["sul"]),
                                                 altura_m=esperada["altura_minima"]))
    for eixo in ("sul", "norte"):
        piores.append(posicionamento.distancia_m((esperada["oeste"], desenhada[eixo]),
                                                 (esperada["oeste"], esperada[eixo]),
                                                 altura_m=esperada["altura_minima"]))
    piores.append(abs(desenhada["altura_minima"] - esperada["altura_minima"]))
    piores.append(abs(desenhada["altura_maxima"] - esperada["altura_maxima"]))
    pior = max(piores)
    medida(ITEM)("erro_da_caixa_projetada", round(pior, 4), "m",
                 "venv/bin/pytest tests/e2e/test_modelos3d.py -k posicao_e_na_escala")
    assert pior <= TOLERANCIA_M, {"pior_erro_m": pior, "desenhada": desenhada, "esperada": esperada}


def test_o_modelo_e_de_fato_desenhado(cena_aberta, bancada):
    """Prova de pixel: com o modelo ligado a tela é diferente da tela sem ele. Configuração certa e nada
    na tela é a falha que mais engana num visualizador 3D."""
    from io import BytesIO

    import numpy as np
    from PIL import Image

    page = cena_aberta["page"]
    _esperar_modelo(page, bancada["casa"]["id"])
    page.wait_for_timeout(1500)
    esperada_na_tela = page.evaluate(
        "(id) => { const c = window.plat.cena.modelos.camadas.get(id).caixaNaTela(); "
        "const r = window.plat.cena.map.getCanvas().getBoundingClientRect(); "
        "return {x0: c.x0 + r.x, x1: c.x1 + r.x, y0: c.y0 + r.y, y1: c.y1 + r.y}; }",
        bancada["casa"]["id"])
    tela_com = page.screenshot()
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    Image.open(BytesIO(tela_com)).save(CAPTURAS / f"{ITEM}_com_modelo.png")
    com = np.asarray(Image.open(BytesIO(tela_com)).convert("RGB"), dtype=np.int16)
    page.evaluate("(id) => { const m = window.plat.cena.modelos; "
                  "window.plat.cena.map.removeLayer('plat-modelo-' + id); m.camadas.delete(id); "
                  "window.plat.cena.map.triggerRepaint(); }", bancada["casa"]["id"])
    page.wait_for_timeout(1500)
    sem = np.asarray(Image.open(BytesIO(page.screenshot())).convert("RGB"), dtype=np.int16)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    Image.open(BytesIO(page.screenshot())).save(CAPTURAS / f"{ITEM}_sem_modelo.png")
    mudou = np.abs(com - sem).max(axis=2) > 12
    diferentes = int(mudou.sum())
    assert diferentes >= 200, f"só {diferentes} pixels mudaram ao desligar o modelo: nada foi desenhado"
    # e os pixels que mudaram têm de estar DENTRO da área que o modelo ocupa na tela: mudança em qualquer
    # outro lugar seria da interface, não do modelo. (Fração da caixa não serve de limiar aqui: a caixa
    # inclui o elemento fino de referência geográfica do arquivo, que atravessa o terreno inteiro e é
    # quase todo ar; o que se afirma é "foi desenhado, e no lugar certo", não "encheu a caixa".)
    caixa_tela = esperada_na_tela
    ys, xs = np.nonzero(mudou)
    escala = com.shape[1] / page.viewport_size["width"]
    dentro = ((xs >= (caixa_tela["x0"] - 8) * escala) & (xs <= (caixa_tela["x1"] + 8) * escala)
              & (ys >= (caixa_tela["y0"] - 8) * escala) & (ys <= (caixa_tela["y1"] + 8) * escala))
    assert dentro.mean() > 0.95, (f"{100 * (1 - dentro.mean()):.1f}% dos pixels que mudaram estão fora da "
                                  "área projetada do modelo")


def test_clique_num_elemento_mostra_as_propriedades(cena_aberta, bancada):
    """Cláusula do portão: clique num elemento mostra suas propriedades, com captura."""
    page = cena_aberta["page"]
    _esperar_modelo(page, bancada["casa"]["id"])
    page.wait_for_timeout(1000)
    # varredura em grade sobre a área que o modelo ocupa na tela: escolher um ponto "no olho" faria o
    # teste depender do enquadramento, não do produto. A grade sai dos 8 cantos da caixa DESENHADA.
    alvo = page.evaluate(
        """(id) => {
             const c = window.plat.cena.modelos.camadas.get(id);
             const t = c.caixaNaTela();
             const x0 = t.x0, x1 = t.x1, y0 = t.y0, y1 = t.y1;
             for (let i = 0; i <= 16; i += 1) {
               for (let j = 0; j <= 16; j += 1) {
                 const x = x0 + ((x1 - x0) * i) / 16;
                 const y = y0 + ((y1 - y0) * j) / 16;
                 const achado = c.elementoNoPonto({x, y});
                 if (achado && achado.guid) return {x, y, guid: achado.guid, tipo: achado.tipo};
               }
             }
             return {caixa_na_tela: [x0, y0, x1, y1]};
           }""", bancada["casa"]["id"])
    assert alvo.get("guid"), f"nenhum elemento atingido pelo raio em 289 pontos da grade: {alvo}"
    # o ponto veio em coordenada do CANVAS (é o que map.project devolve); o mouse do navegador anda em
    # coordenada da PÁGINA, e entre as duas há a barra lateral e a linha de ferramentas da tela
    caixa_canvas = page.evaluate("() => { const r = window.plat.cena.map.getCanvas().getBoundingClientRect();"
                                 " return {x: r.x, y: r.y}; }")
    page.mouse.click(alvo["x"] + caixa_canvas["x"], alvo["y"] + caixa_canvas["y"])
    achado = alvo
    page.wait_for_selector("#modelo-propriedades [data-campo='guid']", timeout=15000)
    mostrado = page.text_content("#modelo-propriedades [data-campo='guid']")
    assert mostrado == achado["guid"]
    tipo = page.text_content("#modelo-propriedades [data-campo='tipo']")
    assert tipo and tipo.startswith("IFC")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_elemento.png"))


def test_a_ficha_do_elemento_bate_com_a_api(cena_aberta, bancada):
    page = cena_aberta["page"]
    _esperar_modelo(page, bancada["casa"]["id"])
    dados = page.evaluate(
        """async (id) => {
             const r = await fetch(`/api/modelos/${id}/elementos?limite=500`, {credentials: 'same-origin'});
             return r.json();
           }""", bancada["casa"]["id"])
    assert dados["total"] == bancada["casa"]["elementos"]
    guids_no_gltf = page.evaluate(
        "(id) => { const c = window.plat.cena.modelos.camadas.get(id); const g = []; "
        "c.raiz.traverse((o) => { if (o.userData && o.userData.guid) g.push(o.userData.guid); }); return g; }",
        bancada["casa"]["id"])
    da_api = {e["guid"] for e in dados["itens"]}
    assert set(guids_no_gltf) <= da_api
    assert len(guids_no_gltf) == sum(1 for e in dados["itens"] if e["tem_geometria"])


def test_o_tileset_carrega_pelo_deck_gl(cena_aberta, bancada, medida):
    """Cláusula do portão: o tileset gerado carrega. O deck.gl é o cliente; a árvore vem da nossa API."""
    page = cena_aberta["page"]
    assert page.evaluate("() => !!(window.deck && window.deck.Tile3DLayer)"), "deck.gl não carregou"
    carregado = page.evaluate(
        """async (id) => {
             const r = await fetch(`/api/modelos/${id}/3dtiles/tileset.json`, {credentials: 'same-origin'});
             if (!r.ok) return {erro: r.status};
             const t = await r.json();
             const filhos = t.root.children || [];
             const conteudos = [];
             for (const f of filhos) {
               const c = await fetch(`/api/modelos/${id}/3dtiles/${f.content.uri}`, {credentials: 'same-origin'});
               conteudos.push({uri: f.content.uri, ok: c.ok, bytes: (await c.arrayBuffer()).byteLength});
             }
             return {versao: t.asset.version, filhos: filhos.length, conteudos};
           }""", bancada["caixa"]["id"])
    assert carregado.get("versao") == "1.1", carregado
    assert carregado["filhos"] >= 1
    assert all(c["ok"] and c["bytes"] > 0 for c in carregado["conteudos"]), carregado
    page.evaluate("(id) => window.plat.cena.modelos.tilesets.ativar("
                  "{id, url_tileset: `/api/modelos/${id}/3dtiles/tileset.json`})", bancada["caixa"]["id"])
    page.wait_for_timeout(4000)
    montado = page.evaluate("(id) => window.plat.cena.modelos.tilesets.camadas.has(id)",
                            bancada["caixa"]["id"])
    assert montado
    medida(ITEM)("tileset_carregado_no_navegador",
                 {"tiles": carregado["filhos"], "versao": carregado["versao"]}, "contagem",
                 "venv/bin/pytest tests/e2e/test_modelos3d.py -k tileset_carrega")


def test_quadros_por_segundo_com_o_modelo_na_tela(cena_aberta, bancada, medida):
    """Número de desempenho vai com a carga da máquina ao lado; sem isso não vale como prova."""
    page = cena_aberta["page"]
    _esperar_modelo(page, bancada["casa"]["id"])
    page.wait_for_timeout(1000)
    fps = page.evaluate(
        """async () => {
             const m = window.plat.cena.map;
             let n = 0;
             const t0 = performance.now();
             const conta = () => { n += 1; };
             m.on('render', conta);
             m.easeTo({bearing: m.getBearing() + 120, duration: 3000});
             await new Promise((r) => setTimeout(r, 3200));
             m.off('render', conta);
             return (n * 1000) / (performance.now() - t0);
           }""")
    carga = os.getloadavg()[0]
    linhas = Path("/proc/meminfo").read_text().splitlines()
    livre_gb = round(int(next(x.split()[1] for x in linhas if x.startswith("MemAvailable"))) / 1048576, 2)
    medida(ITEM)("quadros_por_segundo_com_modelo",
                 {"fps": round(fps, 1), "alvo": FPS_ALVO, "carga_1min": round(carga, 2),
                  "ram_livre_gb": livre_gb, "navegador": "chromium do playwright, sem GPU"}, "quadros/s",
                 "venv/bin/pytest tests/e2e/test_modelos3d.py -k quadros_por_segundo")
    if carga > 8:
        pytest.skip(f"carga da máquina em {carga:.1f} (teto 8): medida gravada, cláusula não aferida")
    assert fps >= FPS_ALVO, {"fps": fps, "carga_1min": carga, "ram_livre_gb": livre_gb}


def test_nenhum_erro_de_console_no_caminho_inteiro(cena_aberta, bancada):
    page = cena_aberta["page"]
    _esperar_modelo(page, bancada["casa"]["id"])
    ponto = page.evaluate("(id) => { const c = window.plat.cena.modelos.camadas.get(id).centroNaTela();"
                          " const r = window.plat.cena.map.getCanvas().getBoundingClientRect();"
                          " return c && {x: c.x + r.x, y: c.y + r.y}; }", bancada["casa"]["id"])
    if ponto:
        page.mouse.click(ponto["x"], ponto["y"])
    page.wait_for_timeout(1500)
    assert cena_aberta["erros"] == []
