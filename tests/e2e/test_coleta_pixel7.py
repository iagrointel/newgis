"""e2e do formulário de coleta (item L2-07-b) em viewport de celular (Pixel 7: 412x915, escala 2.625): abre o
formulário de cascata, escolhe estado -> município -> bairro (as listas de baixo mudam), preenche, recarrega a
página e confere que o rascunho voltou, envia e vê a feição gravada; captura em tests/e2e/capturas/.

Precisa de servidor com /static servido (nginx da URL interna, ou `tests/e2e/servidor_coleta.py` na trilha) e de
um formulário importado antes (feito aqui pela API com o admin de demonstração)."""

import base64
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]
XLSFORMS = Path(__file__).resolve().parents[1] / "coleta" / "xlsforms"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "locale": "pt-BR", "viewport": {"width": 412, "height": 915},
            "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}


@pytest.fixture
def formulario_cascata(admin_api):
    conteudo = base64.b64encode((XLSFORMS / "cascata.xlsx").read_bytes()).decode("ascii")
    r = admin_api.post("/api/formularios/xlsform", data={"nome": "cascata.xlsx", "conteudo": conteudo,
                                                          "titulo": "zt e2e cascata"})
    assert r.status == 201, r.text()
    f = r.json()
    yield f
    admin_api.delete(f"/api/itens/{f['id']}")
    admin_api.delete(f"/api/itens/{f['documento']['camada_destino']}")


def test_cascata_rascunho_e_envio_no_pixel7(page, base_url, credenciais_demo, formulario_cascata, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo=f"/coleta?formulario={formulario_cascata['id']}")
    tela.ir(f"/coleta?formulario={formulario_cascata['id']}", "coleta_abrir_ms")
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
    tela.capturar("pixel7_cascata")
    # rascunho sobrevive à recarga
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    assert page.eval_on_selector("#c-estado", "e => e.value") == "ba"
    assert page.eval_on_selector("#c-municipio", "e => e.value") == "ssa"
    assert page.eval_on_selector("#c-bairro", "e => e.value") == "ssa_pit"
    assert page.get_attribute("#formulario", "data-rascunho") == "1"
    page.click("#enviar")
    page.wait_for_selector("#formulario[data-enviado]", timeout=20000)
    tela.capturar("pixel7_enviado")
    tela.verificar()
    for nome, ms in tela.medidas.items():
        medida("L2-07-b-formulario-de-coleta-xlsform")(nome, ms, "ms", "e2e Pixel 7")
