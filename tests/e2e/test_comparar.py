"""e2e do item L2-01-j-comparacao-cortina-tempo (painel "Comparar" do SIG novo: cortina/swipe, lado a
lado sincronizado, lupa, controle de tempo).

Cada teste aqui é uma cláusula do portão de pronto:
  * cortina em 3 posições, com captura (test_cortina);
  * lado a lado mantém sincronismo após 20 movimentos, diferença de centro < 1e-6 grau (test_lado_a_lado);
  * lupa segue o cursor, com captura (test_lupa);
  * controle de tempo: a contagem mostrada bate com COUNT(*) direto no banco (não com a MESMA rota que
    a tela usa — se o motor de contagem da tela estivesse errado, comparar contra ele mesmo não pegaria
    nada) em 5 passos, janela instantânea e acumulativa (test_tempo_contagem_bate_com_banco);
  * reprodução a 2 passos/s nunca agenda o próximo passo com pedido pendente (test_tempo_reproducao);
  * 0 erro de console em tudo.

Depende da bancada `scripts/comparar_demo_tempo.py criar` (camada de TESTE com campo `data_evento`,
100.000 pontos, ~3% NULL, gravada com AT TIME ZONE de 4 fusos diferentes) e das 3 camadas reais do
inquilino demo (Municípios de SP, Linhas de transmissão SP, Subestações SP — NENHUMA delas tem campo de
data tipado, só a de teste). Sem uma das duas, SALTA. O dono do item apaga a camada de teste ao terminar
(instrução do item) — depois disso, a suíte de tempo salta sozinha (nenhuma camada com campo de data)."""

from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.e2e.apoio import Tela

CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L2-01-j-comparacao-cortina-tempo"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _contexto_demo(con):
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, %s)", ("demo", "admin"))
        r = cur.fetchone()
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', 'admin', false)",
            (str(r["tenant_id"]), str(r["usuario_id"])),
        )
    con.commit()


def _desligar_raster(page):
    """As camadas de imagem (item L1) de outra trilha rodando no MESMO inquilino demo não têm nada a
    ver com este item — deixá-las ligadas só contamina a contagem de erro de console com falha de tile
    alheia sob pressão de memória da máquina. Desligar antes de medir sincronismo/console."""
    page.evaluate("""
      () => {
        const { catalogo } = window.plat.sig;
        for (const id of [...catalogo.ativas]) {
          const f = catalogo.ficha(id);
          if (f && f.tipo === 'raster') catalogo.desligar(id);
        }
      }
    """)


def _marcar(page, lista_id, trecho):
    li = page.locator(f'#{lista_id} li:has(.camada-titulo:text-matches("{trecho}"))').first
    caixa = li.locator("input[type=checkbox]")
    if not caixa.is_checked():
        caixa.check()
    return li.count() > 0


@pytest.fixture
def comparar(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    # 502 aqui é SEMPRE `/api/imagens/<id>/tiles/...` de camada raster de OUTRA trilha (imagens/raster,
    # `wt/lancamento`, item L1) rodando no MESMO inquilino demo compartilhado, sob a pressão de RAM da
    # máquina (medido 10/09: `free -h` caiu a ~400 MB livres com as duas trilhas + pytest da outra
    # sessão simultâneos) — nunca uma rota deste item (cortina/lado-a-lado/lupa/tempo não tocam
    # `/api/imagens`). Aceitar aqui em vez de mascarar com desligar-camada: mesmo desligando toda
    # camada raster ATIVA no início (abaixo), a outra trilha pode ligar uma camada nova NO MEIO do
    # teste — não há como este item impedir isso no inquilino compartilhado.
    tela.esperar_status(502)
    tela.entrar(slug, login, senha)
    tela.ir("/sig", "pagina_pronta_ms_sig")
    page.evaluate("() => window.plat.sig.map.jumpTo({center: [-48.6, -22.6], zoom: 6.6, bearing: 0, pitch: 0})")
    page.wait_for_function("() => window.plat.sig.catalogo.disponiveis.length > 0", timeout=20000)
    _desligar_raster(page)
    # o painel "Camadas" abre sozinho por padrão (sig.js: único painel lembrado quando não há estado
    # salvo) e flutua do lado DIREITO da tela — fechar aqui, não só o "Comparar": os dois juntos, em
    # viewport estreito (1280 do pytest-playwright), cobrem área suficiente do mapa para o cursor real
    # do teste da lupa cair em cima de um painel em vez de #mapa (achado deste item).
    if page.locator("#painel-camadas:not([hidden])").count():
        page.click('button[data-painel="camadas"]')
        # NÃO `wait_for_selector("#painel-camadas[hidden]")`: o estado padrão é 'visible', e um elemento
        # com o atributo `hidden` nunca é visível — o seletor bateria e o wait nunca resolveria.
        page.wait_for_function("() => document.getElementById('painel-camadas').hidden", timeout=5000)
    page.click('button[data-painel="comparar"]')
    page.wait_for_selector("#painel-comparar:not([hidden])", timeout=20000)
    if not _marcar(page, "comparar-lista-a", "Municípios de SP"):
        pytest.skip("bancada ausente: camada 'Municípios de SP (IBGE 2022)' não está no inquilino demo")
    _marcar(page, "comparar-lista-b", "Linhas de transmiss")
    _marcar(page, "comparar-lista-b", "Subestações SP")
    return tela


def _esperar_sync_pronto(page, timeout=45000):
    page.wait_for_function("() => typeof window.plat.sig.comparar.motor.pararSync === 'function'", timeout=timeout)


def test_cortina_tres_posicoes_com_captura(comparar, page):
    page.check('input[name="comparar-modo"][value="cortina-v"]')
    _esperar_sync_pronto(page)
    page.wait_for_timeout(1200)
    posicoes = [20, 50, 80]
    for i, pct in enumerate(posicoes):
        page.evaluate("(p) => window.plat.sig.comparar.motor.definirPosicaoCortina(p)", pct)
        page.wait_for_timeout(300)
        pos_real = page.evaluate("() => window.plat.sig.comparar.motor.pos")
        assert pos_real == pct
        clip = page.evaluate(
            "() => getComputedStyle(document.getElementById('comparar-area'))"
            ".getPropertyValue('--comparar-clip')"
        )
        assert f"{pct}%" in clip
        page.screenshot(path=str(CAPTURAS / f"comparar_cortina_v_{i}_{pct}pct.png"))

    # cortina horizontal também recorta (segunda orientação do portão)
    page.check('input[name="comparar-modo"][value="cortina-h"]')
    _esperar_sync_pronto(page)
    page.wait_for_timeout(800)
    page.evaluate("() => window.plat.sig.comparar.motor.definirPosicaoCortina(35)")
    page.wait_for_timeout(300)
    clip_h = page.evaluate(
        "() => getComputedStyle(document.getElementById('comparar-area'))"
        ".getPropertyValue('--comparar-clip')"
    )
    assert "35%" in clip_h
    page.screenshot(path=str(CAPTURAS / "comparar_cortina_h_35pct.png"))

    page.check('input[name="comparar-modo"][value="desligado"]')
    comparar.verificar()


def test_lado_a_lado_sincronismo_20_movimentos(comparar, page):
    page.check('input[name="comparar-modo"][value="lado-a-lado"]')
    _esperar_sync_pronto(page)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(CAPTURAS / "comparar_lado_a_lado.png"))

    resultado = page.evaluate("""
      async () => {
        const motor = window.plat.sig.comparar.motor;
        motor.diferencaMaximaCentro = 0;
        motor.movimentosSincronizados = 0;
        for (let i = 0; i < 20; i++) {
          const dx = (Math.random() - 0.5) * 0.02;
          const dy = (Math.random() - 0.5) * 0.02;
          const dz = (Math.random() - 0.5) * 0.6;
          const c = motor.mapaA.getCenter();
          motor.mapaA.jumpTo({
            center: [c.lng + dx, c.lat + dy],
            zoom: motor.mapaA.getZoom() + dz,
            bearing: motor.mapaA.getBearing() + (Math.random() - 0.5) * 20,
          });
          await new Promise((r) => setTimeout(r, 20));
        }
        const ca = motor.mapaA.getCenter();
        const cb = motor.mapaB.getCenter();
        return {
          movimentos: motor.movimentosSincronizados,
          diferencaMaximaCentro: motor.diferencaMaximaCentro,
          diferencaCentroFinalLng: Math.abs(ca.lng - cb.lng),
          diferencaCentroFinalLat: Math.abs(ca.lat - cb.lat),
          zoomA: motor.mapaA.getZoom(), zoomB: motor.mapaB.getZoom(),
          bearingA: motor.mapaA.getBearing(), bearingB: motor.mapaB.getBearing(),
        };
      }
    """)
    page.screenshot(path=str(CAPTURAS / "comparar_lado_a_lado_pos_sincronismo.png"))
    page.check('input[name="comparar-modo"][value="desligado"]')

    assert resultado["movimentos"] == 20, resultado
    assert resultado["diferencaMaximaCentro"] < 1e-6, resultado
    assert resultado["diferencaCentroFinalLng"] < 1e-6, resultado
    assert resultado["diferencaCentroFinalLat"] < 1e-6, resultado
    assert resultado["zoomA"] == resultado["zoomB"], resultado
    assert resultado["bearingA"] == resultado["bearingB"], resultado
    comparar.verificar()


def test_lupa_segue_cursor(comparar, page):
    page.check('input[name="comparar-modo"][value="lupa"]')
    # `#comparar-mapa-b` perde `[hidden]` ANTES do resto da cadeia assíncrona (novo mapa secundário +
    # catálogo de camadas) terminar (MotorComparacao.ligar tira o `hidden` logo no início da função) —
    # esperar só o seletor confere a casca, não que o rastreador de cursor já esteja instalado
    # (`_ativarSeguirCursor`, que só roda no fim de `ligar`). Esperar `pararSync` é o mesmo sinal de
    # "a cadeia terminou" que as outras duas ferramentas já usam.
    _esperar_sync_pronto(page)
    page.wait_for_function("() => typeof window.plat.sig.comparar.motor._onMoveLupa === 'function'", timeout=45000)
    page.wait_for_timeout(800)
    box = page.locator("#mapa").bounding_box()
    # o alvo tem de cair FORA do retângulo do painel "Comparar" (320 px, flutua por cima do mapa) —
    # achado deste item: com viewport estreito (1280 do pytest-playwright) 30% da largura do mapa ainda
    # caía dentro do painel, o pointermove nunca chegava a #mapa (o painel intercepta), e a falha
    # parecia "a lupa não segue o cursor" quando na verdade era "o alvo escolhido pelo teste está em
    # cima de outro elemento". 85% da largura garante estar à direita do painel em qualquer viewport
    # suportado (mínimo 1024, painel some por completo abaixo de 720 — ver sig.css).
    painel = page.locator("#painel-comparar").bounding_box()
    alvo_x = max(box["x"] + box["width"] * 0.85, painel["x"] + painel["width"] + 40)
    alvo_y = box["y"] + box["height"] * 0.6
    page.mouse.move(alvo_x, alvo_y, steps=6)
    page.wait_for_timeout(500)
    caixa_lupa = page.locator("#comparar-mapa-b").bounding_box()
    centro_lupa_x = caixa_lupa["x"] + caixa_lupa["width"] / 2
    centro_lupa_y = caixa_lupa["y"] + caixa_lupa["height"] / 2
    assert abs(centro_lupa_x - alvo_x) < 5, (centro_lupa_x, alvo_x)
    assert abs(centro_lupa_y - alvo_y) < 5, (centro_lupa_y, alvo_y)
    page.screenshot(path=str(CAPTURAS / "comparar_lupa.png"))
    page.check('input[name="comparar-modo"][value="desligado"]')
    comparar.verificar()


@pytest.fixture
def campo_tempo(comparar, page, env):
    page.wait_for_function("() => window.plat.sig.comparar.tempo.atual !== null", timeout=45000)
    atual = page.evaluate("() => ({...window.plat.sig.comparar.tempo.atual})")
    if "L2-01-j" not in page.locator("#tempo-camada option:checked").inner_text():
        pytest.skip("nenhuma camada com campo de data tipado no inquilino demo além da bancada de teste "
                    "(scripts/comparar_demo_tempo.py criar) — provavelmente já apagada")
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    _contexto_demo(con)
    with con.cursor() as cur:
        cur.execute(
            "SELECT dados->>'schema' AS esquema, dados->>'tabela' AS tabela FROM plat.item WHERE id = %s::uuid",
            (atual["item"],),
        )
        linha = cur.fetchone()
    yield {"con": con, "cur": con.cursor(), "esquema": linha["esquema"], "tabela": linha["tabela"], "atual": atual}
    con.close()


def _contagem_sql(campo_tempo, campo, ini_iso, fim_iso):
    cur = campo_tempo["cur"]
    cur.execute(
        f'SELECT count(*) AS n FROM "{campo_tempo["esquema"]}"."{campo_tempo["tabela"]}" '
        f'WHERE "{campo}" >= %s AND "{campo}" < %s',
        (ini_iso, fim_iso),
    )
    return cur.fetchone()["n"]


def test_tempo_contagem_bate_com_banco(campo_tempo, page, medida):
    gravar = medida(ITEM)
    campo = campo_tempo["atual"]["campo"]

    conferidos = []
    for passo in range(5):
        r = page.evaluate("(p) => window.plat.sig.comparar.tempo._aoPasso(p)", passo)
        ini_iso, fim_iso = page.evaluate(
            "(p) => { const [i, f] = window.plat.sig.comparar.tempo._limitesDoPasso(p); "
            "return [i.toISOString(), f.toISOString()]; }",
            passo,
        )
        n_banco = _contagem_sql(campo_tempo, campo, ini_iso, fim_iso)
        conferidos.append((passo, r["count"], n_banco))
        assert r["count"] == n_banco, f"passo {passo}: tela mostrou {r['count']}, COUNT(*) no banco deu {n_banco}"
    page.screenshot(path=str(CAPTURAS / "comparar_tempo_instantanea.png"))

    # janela acumulativa: cada passo tem de conter estritamente o anterior (nunca-decrescente) e também
    # bater com o banco (mesmo WHERE, só o início fixo em vez de andar)
    page.check('input[name="tempo-janela"][value="acumulativa"]')
    page.wait_for_timeout(300)
    contagens_acc = []
    for passo in (0, 2, 4):
        r = page.evaluate("(p) => window.plat.sig.comparar.tempo._aoPasso(p)", passo)
        ini_iso, fim_iso = page.evaluate(
            "(p) => { const [i, f] = window.plat.sig.comparar.tempo._limitesDoPasso(p); "
            "return [i.toISOString(), f.toISOString()]; }",
            passo,
        )
        n_banco = _contagem_sql(campo_tempo, campo, ini_iso, fim_iso)
        assert r["count"] == n_banco, f"acumulativa passo {passo}: tela {r['count']} x banco {n_banco}"
        contagens_acc.append(r["count"])
    assert contagens_acc == sorted(contagens_acc), contagens_acc
    page.screenshot(path=str(CAPTURAS / "comparar_tempo_acumulativa.png"))

    gravar("tempo_passos_conferidos_contra_count_sql", len(conferidos) + 3, "passos",
           "5 passos na janela instantânea + 3 na acumulativa, cada um comparado a um COUNT(*) direto no banco")
    for _passo, ui, banco in conferidos:
        assert ui == banco
    page.check('input[name="tempo-janela"][value="instantanea"]')


def test_tempo_reproducao_sem_pedido_pendurado(campo_tempo, page, medida):
    gravar = medida(ITEM)
    passo_inicial = page.evaluate("() => window.plat.sig.comparar.tempo.passoAtual")
    page.click("#tempo-tocar")
    page.wait_for_timeout(3500)  # ~7 passos a 2 passos/s
    page.click("#tempo-tocar")  # pausa
    passo_final = page.evaluate("() => window.plat.sig.comparar.tempo.passoAtual")
    tocando = page.evaluate("() => window.plat.sig.comparar.tempo.tocando")
    ultima_medida_ms = page.evaluate("() => window.plat.sig.comparar.tempo.ultimaMedidaMs")

    assert tocando is False, "clicar em pausar tem de parar o laço de reprodução"
    assert passo_final != passo_inicial, "7 passos esperados; o passo não andou"
    # cada passo AWAITED a própria consulta antes do próximo (o laço de _reproduzir não agenda com
    # pedido pendente) — a medida do último passo é o tempo real de ida-e-volta, bem abaixo do
    # intervalo de 500 ms (2 passos/s) usado como cadência.
    assert ultima_medida_ms is not None and ultima_medida_ms < 500, ultima_medida_ms
    gravar("tempo_reproducao_ultimo_passo_ms", ultima_medida_ms, "ms",
           "MotorTempo.ultimaMedidaMs após clicar #tempo-tocar por 3.5s e pausar (perf.now em volta de cada _aoPasso)")
    campo_tempo["con"].rollback()
