"""e2e do formulário de coleta (item L2-07-b) em viewport de celular (Pixel 7: 412x915, escala 2.625): abre o
formulário de cascata, escolhe estado -> município -> bairro (as listas de baixo mudam), busca na lista,
recarrega a página e confere que o rascunho voltou, envia e vê a feição gravada; capturas em
tests/e2e/capturas/L2-07-b_*.png.

Servidor: nginx da URL interna, ou na trilha `venv/bin/python -m uvicorn tests.e2e.servidor_coleta:app --port 85NN
--ssl-keyfile ... --ssl-certfile ...` com PLAT_URL_PUBLICA=https://127.0.0.1:85NN (a checagem de Origin do ADR
0002 seção 5.3 exige https, por isso o certificado autoassinado e `ignore_https_errors`). O formulário é importado
pela própria página (fetch com o cookie da sessão) e apagado no fim."""

import base64
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, credenciais

pytestmark = [pytest.mark.lento, pytest.mark.e2e]
XLSFORMS = Path(__file__).resolve().parents[1] / "coleta" / "xlsforms"
ITEM = "L2-07-b-formulario-de-coleta-xlsform"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "locale": "pt-BR", "viewport": {"width": 412, "height": 915},
            "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True, "ignore_https_errors": True}


def _fetch_json(page, metodo: str, caminho: str, corpo=None):
    return page.evaluate(
        """async ([metodo, caminho, corpo]) => {
            const cab = { 'Content-Type': 'application/json' };
            const init = { method: metodo, credentials: 'same-origin', headers: cab };
            if (corpo !== null) init.body = JSON.stringify(corpo);
            const r = await fetch(caminho, init);
            let j = null; try { j = await r.json(); } catch (e) { j = null; }
            return [r.status, j];
        }""",
        [metodo, caminho, corpo],
    )


def test_cascata_rascunho_e_envio_no_pixel7(page, base_url, medida):
    cred = credenciais()
    if "demo" not in cred:
        pytest.skip("tests/credenciais.txt sem a linha de demo")
    login, senha = cred["demo"]
    tela = Tela(page, base_url)
    tela.entrar("demo", login, senha, proximo="/")
    conteudo = base64.b64encode((XLSFORMS / "cascata.xlsx").read_bytes()).decode("ascii")
    status, f = _fetch_json(page, "POST", "/api/formularios/xlsform",
                            {"nome": "cascata.xlsx", "conteudo": conteudo, "titulo": "zt e2e cascata"})
    assert status == 201, (status, f)
    try:
        tela.ir(f"/coleta?formulario={f['id']}", "coleta_abrir_ms")
        page.select_option("#c-estado", "ba")
        opcoes = [o.get_attribute("value") for o in page.query_selector_all("#c-municipio option")]
        assert set(opcoes) == {"", "ssa", "ilh"}, opcoes  # só municípios da Bahia
        page.select_option("#c-municipio", "ssa")
        opcoes = [o.get_attribute("value") for o in page.query_selector_all("#c-bairro option")]
        assert set(opcoes) == {"", "ssa_pit", "ssa_bar"}, opcoes
        page.fill("#c-municipio-busca", "ilh")  # busca filtra a lista sem perder a escolha atual
        opcoes = [o.get_attribute("value") for o in page.query_selector_all("#c-municipio option")]
        assert "ilh" in opcoes and "ssa" in opcoes
        page.fill("#c-municipio-busca", "")
        page.select_option("#c-bairro", "ssa_pit")
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_pixel7_cascata.png"), full_page=True)
        # rascunho sobrevive à recarga
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        assert page.eval_on_selector("#c-estado", "e => e.value") == "ba"
        assert page.eval_on_selector("#c-municipio", "e => e.value") == "ssa"
        assert page.eval_on_selector("#c-bairro", "e => e.value") == "ssa_pit"
        assert page.get_attribute("#formulario", "data-rascunho") == "1"
        page.click("#enviar")
        page.wait_for_selector("#formulario[data-enviado]", timeout=20000)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_pixel7_enviado.png"), full_page=True)
        assert page.evaluate(f"localStorage.getItem('plat_coleta_rascunho_{f['id']}') === null")  # rascunho apagado
        tela.verificar()
        status, feicoes = _fetch_json(page, "GET", f"/api/camadas/{f['documento']['camada_destino']}/feicoes/"
                                      + page.get_attribute("#formulario", "data-enviado"))
        assert status == 200 and feicoes["atributos"]["bairro"] == "ssa_pit", (status, feicoes)
        for nome, ms in tela.medidas.items():
            medida(ITEM)(nome, ms, "ms", "e2e Pixel 7 (tests/e2e/test_coleta_pixel7.py)")
    finally:
        _fetch_json(page, "DELETE", f"/api/itens/{f['id']}")
        _fetch_json(page, "DELETE", f"/api/itens/{f['documento']['camada_destino']}")
