"""e2e do popup em tempo de execução (item L2-01-d-popup-runtime), no navegador de verdade (chromium
do playwright). Cada teste aqui é uma cláusula literal do portão:

  * clique em ponto com 3 feições coincidentes mostra "1 de 3" e navega;
  * campo nulo aparece como "—", nunca "null"/"undefined";
  * número 1234567.891 aparece como "1.234.567,89" com 2 decimais configuradas;
  * data aparece no fuso do inquilino (America/Sao_Paulo e UTC dão textos diferentes);
  * popup em viewport 390 px abre como painel inferior (captura);
  * campo com HTML/script aparece como TEXTO, nunca executa (refutação do item);
  * 50 cliques rápidos sem consulta pendurada (refutação do item).

A geometria Multi + campo nulo (as outras duas cláusulas do portão) já são provadas em
`tests/e2e/test_mapa_web.py::test_janela_de_atributos_com_campo_nulo_e_geometria_multi`, que este item
ajustou para o novo DOM (paginador) sem duplicar o cenário; a expressão de área x ST_Area está em
`tests/api/test_mapa_popup_api.py` (mais barato medir tolerância numérica ali do que no navegador).

Depende da bancada `scripts/mapa_demo_popup.py criar` e do Martin no ar; sem uma das duas, SALTA."""

from pathlib import Path

import pytest

from tests.e2e.apoio import Tela
from tests.e2e.test_mapa_web import _esperar_feicoes, _ligar, martin_no_ar  # noqa: F401 (fixture reusada)

CAPTURAS = Path(__file__).resolve().parent / "capturas"
BANCADA_ITEM = "(L2-01-d"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture
def mapa(page, base_url, credenciais_demo, martin_no_ar):
    """Sessão aberta na tela /mapa, com a bancada DESTE item conferida (mesma família "(L2-01", filtro
    mais estrito para não depender da bancada do item-pai estar presente também)."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa_popup")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    titulos = page.locator(".camada-titulo").all_inner_texts()
    if not any(BANCADA_ITEM in t for t in titulos):
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_popup.py criar")
    page.wait_for_function("() => !!(window.plat && window.plat.org)", timeout=5000)
    return tela


def _clicar_no_ponto_coincidente(page):
    """Os fid 1/2/3 da bancada (scripts/mapa_demo_popup.py) estão na MESMA coordenada exata
    (-46.633, -23.55); aproxima até um pixel e clica no centro do mapa."""
    _ligar(page, "mapa-popup (", enquadrar=False)
    page.evaluate("""() => {
      const m = window.plat.mapa;
      m.map.jumpTo({ center: [-46.633, -23.55], zoom: 16 });
    }""")
    _esperar_feicoes(page, 30000)
    caixa = page.locator("#mapa").bounding_box()
    page.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)


def test_paginacao_entre_tres_feicoes_coincidentes(mapa, page):
    _clicar_no_ponto_coincidente(page)
    page.wait_for_selector(".popup-plat .popup-pager", timeout=10000)
    assert page.locator(".popup-pager-texto").inner_text().strip() == "1 de 3"
    # navega: próxima feição muda o texto do título (nomes diferentes na bancada)
    titulo1 = page.locator(".popup-conteudo h3").inner_text()
    page.locator('.popup-pager button[aria-label="próxima feição"]').click()
    page.wait_for_function(
        "(t0) => document.querySelector('.popup-pager-texto').textContent.trim() === '2 de 3'", titulo1)
    titulo2 = page.locator(".popup-conteudo h3").inner_text()
    assert titulo1 != titulo2
    page.locator('.popup-pager button[aria-label="próxima feição"]').click()
    page.wait_for_function(
        "() => document.querySelector('.popup-pager-texto').textContent.trim() === '3 de 3'")
    mapa.verificar()


def test_campo_nulo_numero_grande_e_texto_bruto_nunca_executa(mapa, page):
    _clicar_no_ponto_coincidente(page)
    page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
    # fid 3 (a terceira do trio coincidente) tem TODO campo nulo, exceto data_evento_ms
    for _ in range(2):
        page.locator('.popup-pager button[aria-label="próxima feição"]').click()
        page.wait_for_timeout(150)
    nome_row = page.locator('.popup-tabela tr[data-campo="nome"]')
    assert nome_row.locator("td").inner_text().strip() == "—"
    assert "null" not in page.locator(".popup-conteudo").inner_text().lower()
    assert "undefined" not in page.locator(".popup-conteudo").inner_text().lower()

    # volta para o fid 1 (valor_numero = 1234567.891, configurado com 2 casas)
    page.locator('.popup-pager button[aria-label="feição anterior"]').click()
    page.locator('.popup-pager button[aria-label="feição anterior"]').click()
    page.wait_for_function("() => document.querySelector('.popup-pager-texto').textContent.trim() === '1 de 3'")
    valor = page.locator('.popup-tabela tr[data-campo="valor_numero"] td').inner_text().strip()
    assert valor == "1.234.567,89", valor

    # fid 2 tem o campo com <script> — precisa aparecer como TEXTO na tabela, nunca executar
    dialogos = []
    page.on("dialog", lambda d: (dialogos.append(d.message), d.dismiss()))
    page.locator('.popup-pager button[aria-label="próxima feição"]').click()
    page.wait_for_function("() => document.querySelector('.popup-pager-texto').textContent.trim() === '2 de 3'")
    texto_obs = page.locator('.popup-tabela tr[data-campo="obs_bruta"] td').inner_text()
    assert "<script>" in texto_obs  # o texto CRU aparece na tela...
    assert page.locator(".popup-tabela script").count() == 0  # ...mas nunca vira um elemento <script>
    assert dialogos == [], dialogos  # e nunca dispara alert()
    mapa.verificar()


def _gravar_fuso_do_demo(conexao_plat_app, fuso: str) -> None:
    """`tenant.config.fuso` não tem UI/rota pública ainda (`/api/org` não expõe esta chave — fronteira
    honesta desta trilha, ver handoff); a cláusula do portão pede o MESMO instante em dois fusos, e o
    jeito mais barato de provar isso é gravar a chave direto, como a bancada do item já faz."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(adm["tenant_id"]),))
        cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(adm["usuario_id"]),))
        cur.execute("UPDATE plat.tenant SET config = config || jsonb_build_object('fuso', %s::text) "
                    "WHERE id = plat.tenant_atual()", (fuso,))
    conexao_plat_app.commit()


def test_data_no_fuso_do_inquilino_utc_e_sao_paulo(mapa, page, conexao_plat_app):
    """A cláusula pede o MESMO instante em dois fusos. `tenant.config.fuso` muda direto no banco; a
    tela relê `/api/mapa/fuso` só ao abrir — recarrega a página entre as duas medições."""
    try:
        _gravar_fuso_do_demo(conexao_plat_app, "America/Sao_Paulo")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_function(
            "() => window.plat && window.plat.org && window.plat.org.fuso === 'America/Sao_Paulo'", timeout=5000)
        _clicar_no_ponto_coincidente(page)
        page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
        texto_sp = page.locator('.popup-tabela tr[data-campo="data_evento_ms"] td').inner_text().strip()

        _gravar_fuso_do_demo(conexao_plat_app, "UTC")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_function("() => window.plat && window.plat.org && window.plat.org.fuso === 'UTC'", timeout=5000)
        _clicar_no_ponto_coincidente(page)
        page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
        texto_utc = page.locator('.popup-tabela tr[data-campo="data_evento_ms"] td').inner_text().strip()

        assert texto_sp != texto_utc, (texto_sp, texto_utc)
    finally:
        # nunca deixa o inquilino de demonstração com fuso diferente do padrão para o resto da suíte
        _gravar_fuso_do_demo(conexao_plat_app, "America/Sao_Paulo")


def test_painel_acoplado_em_viewport_estreito(mapa, page):
    page.set_viewport_size({"width": 390, "height": 844})
    _clicar_no_ponto_coincidente(page)
    page.wait_for_selector("#popup-dock:not([hidden]) .popup-tabela", timeout=10000)
    assert page.locator(".maplibregl-popup").count() == 0  # nunca o popup flutuante nesta largura
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / "L2-01-d-popup-runtime_painel_acoplado.png"))
    page.locator(".popup-dock-fechar").click()
    page.wait_for_selector("#popup-dock[hidden]", timeout=5000)
    mapa.verificar()


def test_cinquenta_cliques_rapidos_sem_consulta_pendurada(mapa, page):
    _ligar(page, "mapa-popup (", enquadrar=False)
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-46.633, -23.55], zoom: 16 })")
    _esperar_feicoes(page, 30000)
    caixa = page.locator("#mapa").bounding_box()
    cx, cy = caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2
    for _ in range(50):
        page.mouse.click(cx, cy)
    page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
    # nenhum "carregando…" pendurado 2 s depois do último clique (a última chamada teve tempo de responder)
    page.wait_for_timeout(2000)
    assert page.locator("td.carregando").count() == 0
    mapa.verificar()
