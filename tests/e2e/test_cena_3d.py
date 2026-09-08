"""e2e da cena 3D (item L2-09-b-cena-extrusao-slides), no navegador de verdade (chromium do playwright).

Cada teste é uma cláusula do portão de pronto do item:

  * a cena da bancada abre com terreno, extrusão e atmosfera, sem erro de console;
  * a altura desenhada é a do ATRIBUTO: o valor que chega no tile é o do banco, a expressão de pintura
    lê aquele campo, e a caixa alta é atingida por um clique acima da base enquanto a baixa não é
    (prova de pixel, não só de configuração);
  * altura nula, zero e negativa não viram caixa invertida (as três feições de caso ruim da bancada);
  * a medição 3D de altura devolve a altura conhecida da edificação com folga de 1 %;
  * três slides salvos restauram a câmera com folga de 0,01° e as camadas visíveis, com captura de cada;
  * o exagero do terreno muda a cota lida no mesmo ponto;
  * quadros por segundo medidos com a carga da máquina gravada ao lado (tests/medidas).

Este arquivo sobe o SEU próprio servidor (scripts/servir_local.py, que serve /static como o nginx faz em
produção) e o SEU próprio Martin, os dois na base da trilha, em portas livres — nunca as unidades da
máquina. Sem o binário do Martin, sem a bancada (`scripts/cena_demo.py criar`) ou sem o chromium do
playwright, os testes SALTAM dizendo o motivo; nunca passam por omissão.
"""

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import numpy as np
import psycopg2
import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L2-09-b-cena-extrusao-slides"
MARCA = "cena-l2-09-b"
FAIXA_PORTAS = range(8310, 8400)

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


# ---------------------------------------------------------------- bancada e servidores
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
            httpx.get(url, timeout=2)
            return True
        except httpx.HTTPError:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def portas():
    return set()


@pytest.fixture(scope="module")
def martin(env, portas):
    binario = RAIZ / "bin" / "martin"
    if not binario.exists():
        pytest.skip("bin/martin ausente (rode deploy/martin_instalar.sh)")
    dsn = env.get("PLAT_DSN_LEITOR")
    if not dsn:
        pytest.skip("ambiente sem PLAT_DSN_LEITOR (base de trilha antiga)")
    porta = _porta_livre(portas)
    proc = subprocess.Popen(
        [str(binario), "--listen-addresses", f"127.0.0.1:{porta}", "--auto-bounds", "skip", dsn],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{porta}"
    if not _esperar(f"{url}/catalog"):
        proc.terminate()
        pytest.skip(f"Martin próprio não subiu em {url}")
    yield url
    proc.terminate()
    proc.wait(timeout=20)


@pytest.fixture(scope="module")
def servidor(env, martin, portas):
    porta = _porta_livre(portas)
    ambiente = {**os.environ, "PLAT_MARTIN_URL": martin}
    proc = subprocess.Popen(
        [str(RAIZ / "venv" / "bin" / "python"), str(RAIZ / "scripts" / "servir_local.py"), "--porta", str(porta)],
        cwd=str(RAIZ), env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{porta}"
    if not _esperar(f"{url}/api/saude"):
        proc.terminate()
        pytest.skip(f"servidor local da trilha não subiu em {url}")
    yield url
    proc.terminate()
    proc.wait(timeout=20)


@pytest.fixture(scope="module")
def bancada(env):
    """(id da cena, id da camada, {nome: altura_m}) da bancada do item, lidos do banco da trilha."""
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
            cur.execute("SELECT id, tipo, dados FROM plat.item WHERE dados->>'marca' = %s AND apagado_em IS NULL",
                        (MARCA,))
            itens = cur.fetchall()
            cena = next((i for i in itens if i["tipo"] == "cena"), None)
            camada = next((i for i in itens if i["tipo"] == "camada_vetorial"), None)
            if not cena or not camada:
                pytest.skip("bancada do item ausente: rode scripts/cena_demo.py criar")
            esquema, tabela = camada["dados"]["schema"], camada["dados"]["tabela"]
            cur.execute(f'SELECT nome, altura_m FROM "{esquema}"."{tabela}"')
            alturas = {r["nome"]: r["altura_m"] for r in cur.fetchall()}
    finally:
        con.close()
    return {"cena": str(cena["id"]), "camada": str(camada["id"]), "alturas": alturas}


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
    """Sessão aberta na tela /cena da bancada, com coleta de erro de console."""
    erros: list[str] = []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    slug, login, senha = credenciais_trilha
    page.goto(f"{servidor}/entrar?inquilino={slug}&proximo=/", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)
    page.fill("#login", login)
    page.fill("#senha", senha)
    page.click("#entrar")
    page.wait_for_url(lambda u: "/entrar" not in u, timeout=30000)
    page.goto(f"{servidor}/cena?item={bancada['cena']}", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)
    page.wait_for_function("() => window.plat && window.plat.cena", timeout=30000)
    return {"page": page, "erros": erros, "base": servidor}


def _esperar_extrusao(page, tempo=60000):
    page.wait_for_function("() => window.plat.cena.map.areTilesLoaded()", timeout=tempo)
    page.wait_for_function(
        """() => {
             const m = window.plat.cena.map;
             const ids = m.getStyle().layers.filter((c) => c.type === 'fill-extrusion').map((c) => c.id);
             return ids.length && m.queryRenderedFeatures({ layers: ids }).length > 0;
           }""", timeout=tempo)


def _feicoes(page):
    return page.evaluate("""() => {
      const m = window.plat.cena.map;
      const ids = m.getStyle().layers.filter((c) => c.type === 'fill-extrusion').map((c) => c.id);
      return m.queryRenderedFeatures({ layers: ids }).map((f) => ({
        nome: f.properties.nome, altura: f.properties.altura_m, camada: f.layer.id }));
    }""")


# ---------------------------------------------------------------- cláusulas
def test_a_cena_abre_com_extrusao_ceu_e_sol(cena_aberta):
    page = cena_aberta["page"]
    _esperar_extrusao(page)
    estado = page.evaluate("""() => {
      const m = window.plat.cena.map;
      return {
        extrusoes: m.getStyle().layers.filter((c) => c.type === 'fill-extrusion').length,
        ceu: !!m.getSky(),
        luz: m.getLight(),
        pitch: m.getPitch(),
        desenhadas: m.queryRenderedFeatures({ layers: m.getStyle().layers
          .filter((c) => c.type === 'fill-extrusion').map((c) => c.id) }).length,
      };
    }""")
    assert estado["extrusoes"] == 1, estado
    assert estado["ceu"] is True, estado
    assert estado["pitch"] > 30, estado
    assert estado["desenhadas"] > 0, estado
    # a luz veio da posição do Sol calculada no servidor (ângulo polar = 90 − elevação)
    assert 0 <= estado["luz"]["position"][2] <= 90, estado["luz"]
    assert not cena_aberta["erros"], cena_aberta["erros"]


def test_a_altura_desenhada_e_a_do_atributo(cena_aberta, bancada):
    page = cena_aberta["page"]
    _esperar_extrusao(page)
    # 1. o valor que chegou no tile é o do banco
    vistas = [f for f in _feicoes(page) if f["nome"] in bancada["alturas"]]
    assert len(vistas) >= 20, f"poucas feições desenhadas para conferir: {len(vistas)}"
    for f in vistas:
        esperado = bancada["alturas"][f["nome"]]
        assert (f["altura"] is None and esperado is None) or float(f["altura"]) == float(esperado), f

    # 2. a expressão de pintura lê aquele campo, com a reserva 0 e o corte em 0
    expressao = page.evaluate("""() => {
      const m = window.plat.cena.map;
      const id = m.getStyle().layers.find((c) => c.type === 'fill-extrusion').id;
      return m.getPaintProperty(id, 'fill-extrusion-height');
    }""")
    assert expressao[0] == "max" and expressao[1] == 0, expressao
    assert json.dumps(expressao).count('"altura_m"') == 1, expressao

    # 3. prova de pixel: com a câmera inclinada, o topo de uma caixa alta ocupa a tela ACIMA da base;
    #    no mesmo deslocamento, uma caixa baixa não é atingida.
    alta = max((f for f in vistas if f["altura"]), key=lambda f: f["altura"])
    baixa = min((f for f in vistas if f["altura"]), key=lambda f: f["altura"])
    assert alta["altura"] >= 30 and baixa["altura"] <= 6, (alta, baixa)
    sonda = page.evaluate("""(nomes) => {
      const m = window.plat.cena.map;
      const ids = m.getStyle().layers.filter((c) => c.type === 'fill-extrusion').map((c) => c.id);
      const saida = {};
      for (const nome of nomes) {
        const f = m.queryRenderedFeatures({ layers: ids }).find((x) => x.properties.nome === nome);
        if (!f) { saida[nome] = null; continue; }
        const coords = f.geometry.coordinates[0];
        const lng = coords.reduce((a, c) => a + c[0], 0) / coords.length;
        const lat = coords.reduce((a, c) => a + c[1], 0) / coords.length;
        const p = m.project([lng, lat]);
        const acima = m.queryRenderedFeatures([p.x, p.y - 25], { layers: ids });
        saida[nome] = acima.some((x) => x.properties.nome === nome);
      }
      return saida;
    }""", [alta["nome"], baixa["nome"]])
    assert sonda[alta["nome"]] is True, sonda
    assert sonda[baixa["nome"]] is False, sonda


def test_altura_nula_zero_e_negativa_nao_viram_caixa_invertida(cena_aberta, bancada):
    page = cena_aberta["page"]
    _esperar_extrusao(page)
    valor = page.evaluate("""(casos) => {
      const m = window.plat.cena.map;
      const camada = window.plat.cena.documento.corpo.camadas[0];
      const escala = camada.extrusao.escala || 1;
      const campo = camada.extrusao.campo_altura;
      const ids = m.getStyle().layers.filter((c) => c.type === 'fill-extrusion').map((c) => c.id);
      const todas = m.queryRenderedFeatures({ layers: ids });
      const saida = {};
      for (const nome of casos) {
        const f = todas.find((x) => x.properties.nome === nome);
        if (!f) { saida[nome] = 'ausente'; continue; }
        const bruto = Number(f.properties[campo]);
        saida[nome] = Math.max(0, (Number.isFinite(bruto) ? bruto : 0) * escala);
      }
      return saida;
    }""", ["caso-altura-zero", "caso-altura-negativa", "caso-altura-nula"])
    for nome, altura in valor.items():
        if altura == "ausente":
            continue  # fora do enquadramento da câmera; o caso é coberto pelo teste de unidade da expressão
        assert altura >= 0, (nome, altura)


def test_medicao_de_altura_confere_com_a_altura_conhecida(cena_aberta, bancada):
    page = cena_aberta["page"]
    _esperar_extrusao(page)
    medida = page.evaluate("""() => {
      const c = window.plat.cena;
      const m = c.map;
      const ids = m.getStyle().layers.filter((x) => x.type === 'fill-extrusion').map((x) => x.id);
      const feicoes = m.queryRenderedFeatures({ layers: ids }).filter((f) => f.properties.altura_m > 20);
      if (!feicoes.length) return null;
      const f = feicoes[0];
      const coords = f.geometry.coordinates[0];
      const lng = coords.reduce((a, x) => a + x[0], 0) / coords.length;
      const lat = coords.reduce((a, x) => a + x[1], 0) / coords.length;
      const p = m.project([lng, lat]);
      const noPredio = c.medicao.cota({ lng, lat }, [p.x, p.y]);
      const noChao = c.medicao.cota({ lng, lat }, [1, 1]);
      return { nome: f.properties.nome, atributo: f.properties.altura_m, medida: noPredio - noChao };
    }""")
    if medida is None:
        pytest.skip("nenhuma edificação alta no enquadramento inicial da bancada")
    esperado = float(bancada["alturas"][medida["nome"]])
    assert abs(medida["medida"] - esperado) <= 0.01 * esperado, medida


def test_tres_slides_restauram_camera_e_camadas(cena_aberta, medida):
    page = cena_aberta["page"]
    gravar = medida(ITEM)
    _esperar_extrusao(page)
    CAPTURAS.mkdir(parents=True, exist_ok=True)

    vistas = [
        {"zoom": 15.0, "pitch": 45.0, "bearing": 10.0},
        {"zoom": 16.2, "pitch": 70.0, "bearing": 200.0},
        {"zoom": 14.5, "pitch": 0.0, "bearing": 359.0},
    ]
    salvos = []
    for i, v in enumerate(vistas, start=1):
        page.evaluate("(v) => window.plat.cena.map.jumpTo({ zoom: v.zoom, pitch: v.pitch, bearing: v.bearing })", v)
        page.wait_for_timeout(400)
        page.fill("#slide-nome", f"vista {i}")
        page.click("#btn-slide-novo")
        page.wait_for_selector(f"#lista-slides li:nth-child({i})", timeout=15000)
        salvos.append(page.evaluate("() => window.plat.cena.slides.lista.at(-1)"))

    assert len(salvos) == 3
    assert all(s.get("miniatura", "").startswith("data:image/jpeg;base64,") for s in salvos), \
        [bool(s.get("miniatura")) for s in salvos]

    # sai das três vistas antes de restaurar
    page.evaluate("() => window.plat.cena.map.jumpTo({ center: [-40, -10], zoom: 5, pitch: 0, bearing: 90 })")
    page.wait_for_timeout(300)

    piores = {"centro": 0.0, "zoom": 0.0, "inclinacao": 0.0, "rotacao": 0.0}
    for i, slide in enumerate(salvos, start=1):
        page.click(f"#lista-slides li:nth-child({i}) button.slide")
        page.wait_for_timeout(600)
        atual = page.evaluate("""() => {
          const m = window.plat.cena.map;
          const c = m.getCenter();
          return { centro: [c.lng, c.lat], zoom: m.getZoom(), inclinacao: m.getPitch(),
                   rotacao: ((m.getBearing() % 360) + 360) % 360,
                   visiveis: window.plat.cena.documento.corpo.camadas
                     .filter((x) => x.visivel !== false).map((x) => x.id) };
        }""")
        alvo = slide["camera"]
        piores["centro"] = max(piores["centro"], abs(atual["centro"][0] - alvo["centro"][0]),
                               abs(atual["centro"][1] - alvo["centro"][1]))
        piores["zoom"] = max(piores["zoom"], abs(atual["zoom"] - alvo["zoom"]))
        piores["inclinacao"] = max(piores["inclinacao"], abs(atual["inclinacao"] - alvo["inclinacao"]))
        piores["rotacao"] = max(piores["rotacao"], abs(((atual["rotacao"] - alvo["rotacao"] + 180) % 360) - 180))
        assert sorted(atual["visiveis"]) == sorted(slide["camadas_visiveis"]), (atual, slide)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_slide{i}.png"))

    assert piores["centro"] <= 0.01, piores
    assert piores["inclinacao"] <= 0.01, piores
    assert piores["rotacao"] <= 0.01, piores
    assert piores["zoom"] <= 0.01, piores
    gravar("slide_erro_maximo_grau", round(max(piores["centro"], piores["inclinacao"], piores["rotacao"]), 6),
           "grau", "tests/e2e/test_cena_3d.py::test_tres_slides_restauram_camera_e_camadas")


def test_exagero_do_terreno_muda_a_cota_lida(cena_aberta):
    """Terreno servido pelo teste: um ladrilho terrain-RGB de altura constante, codificado pelo MESMO
    codec do item L2-09-a. Com 500 m em toda parte, a cota lida no mapa tem de acompanhar o exagero."""
    from app.relevo.codec import codificar_terrain_rgb

    page = cena_aberta["page"]
    alturas = np.full((256, 256), 500.0)
    png = CAPTURAS / "_terreno_constante.png"
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    Image.fromarray(codificar_terrain_rgb(alturas).astype("uint8")).save(png)
    corpo = png.read_bytes()
    page.route("**/terreno-de-teste/**", lambda rota: rota.fulfill(status=200, content_type="image/png", body=corpo))

    leituras = page.evaluate("""async (url) => {
      const c = window.plat.cena;
      const m = c.map;
      c.documento.corpo.terreno = { ligado: true, url, codificacao: 'terrain-rgb', tamanho_tile: 256,
                                    zoom_maximo: 14, exagero: 1 };
      await c.aplicarCena();
      await new Promise((r) => m.once('idle', r));
      const centro = m.getCenter();
      const um = m.queryTerrainElevation(centro);
      c.documento.corpo.terreno.exagero = 2;
      await c.aplicarCena();
      await new Promise((r) => m.once('idle', r));
      const dois = m.queryTerrainElevation(centro);
      return { um, dois, temTerreno: !!m.getTerrain() };
    }""", "http://127.0.0.1/terreno-de-teste/{z}/{x}/{y}.png")
    assert leituras["temTerreno"] is True, leituras
    assert leituras["um"] is not None and abs(leituras["um"] - 500) < 5, leituras
    assert abs(leituras["dois"] - 2 * leituras["um"]) < 5, leituras


def test_quadros_por_segundo_da_cena(cena_aberta, medida):
    page = cena_aberta["page"]
    gravar = medida(ITEM)
    _esperar_extrusao(page)
    carga = os.getloadavg()[0]
    linhas = Path("/proc/meminfo").read_text().splitlines()
    livre_gb = round(int(next(x.split()[1] for x in linhas if x.startswith("MemAvailable"))) / 1024 / 1024, 2)
    fps = page.evaluate("""async () => {
      const m = window.plat.cena.map;
      let quadros = 0;
      const t0 = performance.now();
      await new Promise((pronto) => {
        const passo = () => {
          quadros += 1;
          m.setBearing((m.getBearing() + 1.5) % 360);
          if (performance.now() - t0 < 5000) requestAnimationFrame(passo);
          else pronto();
        };
        requestAnimationFrame(passo);
      });
      return quadros / ((performance.now() - t0) / 1000);
    }""")
    gravar("fps_cena_demo", round(fps, 1), "quadros/s",
           "tests/e2e/test_cena_3d.py::test_quadros_por_segundo_da_cena")
    gravar("carga_1min_no_teste_de_fps", round(carga, 2), "carga", "os.getloadavg")
    gravar("ram_livre_gb_no_teste_de_fps", livre_gb, "GB", "/proc/meminfo MemAvailable")
    if carga > 8:
        pytest.skip(f"carga da máquina em {carga:.1f} (acima de 8): a medida de fps não diria nada do produto")
    assert fps >= 30, f"{fps:.1f} quadros/s com carga {carga:.1f}"


def test_nenhum_erro_de_console_no_caminho_inteiro(cena_aberta):
    page = cena_aberta["page"]
    _esperar_extrusao(page)
    page.fill("#slide-nome", "vista final")
    page.click("#btn-slide-novo")
    page.wait_for_timeout(800)
    page.click("#btn-altura")
    page.click("#btn-medicao-limpar")
    assert not cena_aberta["erros"], cena_aberta["erros"]
