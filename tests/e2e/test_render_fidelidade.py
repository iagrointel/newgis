"""Fidelidade do motor de render contra o visualizador (item L2-12-a-motor-render-servidor).

Cláusula do portão: "imagem igual à captura do visualizador na mesma extensão (<= 2 % de pixels
diferentes)". As duas imagens comparadas aqui nascem de caminhos diferentes:

  * **visualizador**: a tela `/mapa` de verdade, aberta com sessão no navegador, com os controles e o
    painel que ela tem — a captura é só do `canvas` do MapLibre, que é onde mora o mapa;
  * **servidor**: `POST /api/render/mapa`, que navega a página headless `/render/mapa` dentro do pool do
    chromium e devolve o PNG.

"Mesma extensão" é imposta, não torcida: mede-se o tamanho em pixels de CSS do canvas do visualizador e
pede-se ao servidor exatamente essa largura e altura, com o MESMO centro e o MESMO zoom. No MapLibre, o
zoom fixa a resolução por pixel, então mesmo centro + mesmo zoom + mesmo tamanho é a mesma extensão em
metros. A base é a mesma nos dois lados (o recorte local em pmtiles): a página do render não tem outra, e
o visualizador abre nela.

Uma coisa é escondida de propósito antes da captura, e fica declarada aqui: os CONTROLES do visualizador
(navegação, escala, coordenadas, seletor de camada base e atribuição) são elementos de HTML desenhados POR
CIMA do canvas, e a captura de um elemento no chromium pega a região da tela, com o que estiver sobreposto.
Eles não são o mapa — a página do render não tem chrome nenhum, por construção (web/render_mapa.html). Por
isso `display:none` neles antes da captura. Nada mais é alterado: o canvas é o mesmo, no mesmo lugar.

O que este teste NÃO prova: fidelidade com camadas do catálogo desenhadas por cima. O motor recusa
documento com camada (`501 render_de_camada_nao_suportado`, fronteira declarada em app/render/rotas.py),
então a comparação é do mapa-base — que é o que o motor sabe desenhar hoje.

Bancada: a receita de docs/BANCADA_E2E.md, com UMA diferença medida em 18/09/2026 — aqui o servidor da
trilha sobe em **HTTP**, não no TLS autoassinado. Motivo: quem navega a página do render é o chromium do
POOL, dentro do processo do servidor, e ele recusa o certificado autoassinado da bancada
(`net::ERR_CERT_AUTHORITY_INVALID` no `goto`, e a rota devolve 500). Repassar a âncora de certificado ao
pytest não alcança esse navegador, e afrouxar a verificação de certificado do motor seria mexer no produto
para o teste passar. Em HTTP, a guarda de CSRF recusaria o login feito pela PÁGINA (Origin !=
PLAT_URL_PUBLICA), e é para isso que serve `escrita_do_navegador_sem_origin` — o mesmo recurso já usado
por outros e2e de trilha, documentado em tests/e2e/apoio.py.

    set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
    venv/bin/python scripts/servir_local.py --porta 8501 &
    bash /home/dev/plataforma/laco/roda_teste.sh tests/e2e/test_render_fidelidade.py -q \
      --base-url http://127.0.0.1:8501
"""

from __future__ import annotations

import io
import json
import os

import pytest
from PIL import Image

from tests.e2e.apoio import CAPTURAS, Tela, escrita_do_navegador_sem_origin

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-12-a-motor-render-servidor"
# centro e zoom do recorte local (mesmo padrão de web/js/mapa/mapa.js e de render_entrada.js)
CENTRO = [-46.593018, -23.493476]
ZOOM = 13
TETO_DIFERENTES = 0.02  # 2 % — o número do portão
# tolerância por canal: o visualizador compõe o canvas na tela e o render captura o viewport da página
# headless; os dois passam pelo MESMO chromium e pelo MESMO estilo, mas o antisserrilhado de rótulo e de
# via não é bit a bit reproduzível entre dois contextos. Um pixel conta como DIFERENTE quando algum canal
# anda mais de 8/255 — perto do exato, longe de esconder uma camada faltando ou um deslocamento.
TOLERANCIA_CANAL = 8


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True}


def _abrir_visualizador(page, base_url, credenciais_demo) -> Tela:
    slug, login, senha = credenciais_demo
    escrita_do_navegador_sem_origin(page)  # bancada em HTTP; ver a docstring do módulo
    tela = Tela(page, base_url, item=ITEM)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=30000)
    page.wait_for_function("() => window.plat && window.plat.mapa && window.plat.mapa.map", timeout=30000)
    # mesma extensão dos dois lados: centro e zoom cravados, sem animação, e espera pelo 'idle' (tiles
    # carregadas E desenhadas) — 'load' dispara antes das tiles chegarem e capturaria o fundo vazio
    page.evaluate(
        """([centro, zoom]) => { window.plat.mapa.map.jumpTo({ center: centro, zoom }); }""",
        [CENTRO, ZOOM],
    )
    page.wait_for_function(
        """() => new Promise((ok) => { const m = window.plat.mapa.map;
             if (m.loaded() && m.areTilesLoaded()) { ok(true); } else { m.once('idle', () => ok(true)); } })""",
        timeout=30000,
    )
    # controles do visualizador fora da captura (ver docstring do módulo): são HTML sobre o canvas.
    # `.mapa-painel` é a classe dos painéis flutuantes do próprio produto (web/mapa.html) e
    # `.maplibregl-ctrl*` a dos controles da biblioteca. Só eles, nunca um ancestral: esconder o pai
    # zeraria o container do mapa junto (medido: clientWidth virou 0).
    page.evaluate(
        """() => { for (const el of document.querySelectorAll(
                     '.mapa-painel, .maplibregl-ctrl, .maplibregl-ctrl-group, .maplibregl-ctrl-attrib'))
                     { el.style.visibility = 'hidden'; } }""")
    page.wait_for_timeout(300)
    return tela


def test_render_do_servidor_bate_com_a_captura_do_visualizador(page, base_url, url_publica_resolve,
                                                                credenciais_demo, medida):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina (bancada: docs/BANCADA_E2E.md)")
    tela = _abrir_visualizador(page, base_url, credenciais_demo)

    tamanho = page.evaluate(
        """() => { const c = window.plat.mapa.map.getContainer();
                   return { largura: c.clientWidth, altura: c.clientHeight }; }""")
    largura, altura = int(tamanho["largura"]), int(tamanho["altura"])
    assert largura >= 64 and altura >= 64, tamanho

    do_visualizador = Image.open(io.BytesIO(page.locator("#mapa canvas.maplibregl-canvas").screenshot()))
    do_visualizador = do_visualizador.convert("RGB")
    # o canvas do MapLibre tem o tamanho do container em pixels de CSS; se o navegador estiver com fator de
    # escala != 1 a captura sai maior, e aí a comparação é feita na escala do visualizador
    largura, altura = do_visualizador.size

    r = tela.api("POST", "/api/render/mapa", corpo={"largura": largura, "altura": altura, "formato": "png",
                                                     "centro": CENTRO, "zoom": ZOOM})
    assert r.status == 200, (r.status, r.text()[:400])
    do_servidor = Image.open(io.BytesIO(r.body())).convert("RGB")
    assert do_servidor.size == (largura, altura), (do_servidor.size, (largura, altura))

    a = do_visualizador.load()
    b = do_servidor.load()
    total = largura * altura
    diferentes = iguais_exatos = 0
    for j in range(altura):
        for i in range(largura):
            pa, pb = a[i, j], b[i, j]
            delta = max(abs(pa[0] - pb[0]), abs(pa[1] - pb[1]), abs(pa[2] - pb[2]))
            if delta == 0:
                iguais_exatos += 1
            if delta > TOLERANCIA_CANAL:
                diferentes += 1
    fracao = diferentes / total
    carga = [round(x, 2) for x in os.getloadavg()]
    laudo = {"largura": largura, "altura": altura, "total_px": total, "px_diferentes": diferentes,
             "px_iguais_exatos": iguais_exatos, "pct_diferentes": round(fracao * 100, 3),
             "tolerancia_por_canal": TOLERANCIA_CANAL, "teto_pct": TETO_DIFERENTES * 100,
             "centro": CENTRO, "zoom": ZOOM, "carga_1min": carga[0], "carga_5min": carga[1],
             "carga_15min": carga[2]}
    gravar = medida(ITEM)
    gravar("fidelidade_px_diferentes_pct", round(fracao * 100, 3), "%",
           "pixels em que algum canal RGB anda mais de 8/255 entre a captura do canvas do visualizador "
           "(/mapa, com sessão) e o PNG de POST /api/render/mapa no MESMO centro, zoom e tamanho; teto do "
           "portão 2 %. Laudo: " + json.dumps(laudo, ensure_ascii=False))
    gravar("fidelidade_px_iguais_exatos_pct", round(iguais_exatos / total * 100, 3), "%",
           "pixels idênticos bit a bit entre as duas imagens (informativo: mostra quanto da diferença é "
           "antisserrilhado de borda e quanto seria conteúdo faltando)")
    gravar("fidelidade_carga_1min", carga[0], "carga",
           "carga de 1 min da máquina no instante da medida")

    # as duas imagens e a máscara da diferença ficam em tests/e2e/capturas (ignoradas pelo git): sem elas,
    # uma reprovação vira um número sem como ser olhado — e a primeira reprovação desta cláusula foi
    # diagnosticada exatamente olhando as duas imagens lado a lado.
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    do_visualizador.save(CAPTURAS / f"{ITEM}_visualizador.png")
    do_servidor.save(CAPTURAS / f"{ITEM}_servidor.png")
    mascara = Image.new("L", (largura, altura))
    m = mascara.load()
    for j in range(altura):
        for i in range(largura):
            pa, pb = a[i, j], b[i, j]
            m[i, j] = 255 if max(abs(pa[k] - pb[k]) for k in range(3)) > TOLERANCIA_CANAL else 0
    mascara.save(CAPTURAS / f"{ITEM}_diferenca.png")

    tela.verificar()
    assert fracao <= TETO_DIFERENTES, laudo
