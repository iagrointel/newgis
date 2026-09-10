"""e2e do FORMULÁRIO DE CONFIGURAÇÃO DE TRAÇADO (item L4-02-e-configuracoes-de-tracado).

A tela `/redes/configuracoes` lista as configurações da rede escolhida — as seis que vêm com o pacote
elétrica-BR e as que a equipe salvou — e traz o formulário que cria uma nova: código, nome, tipo de traçado,
tipo de resultado, uma barreira de condição (atributo, operador, valor) e uma função sobre atributo. O teste
percorre o caminho inteiro pela tela: escolher a rede, ver a lista com as prontas, preencher o formulário,
salvar, ver a linha nova na tabela e apagá-la.

A rede é criada pela API antes de abrir a tela (só o pacote — o formulário não depende de topologia) e
apagada no fim."""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-02-e-configuracoes-de-tracado"
PORTA = 8380  # porta desta trilha (o prompt do item); conferida livre com `ss -ltn` antes de subir
URL_TESTE = f"http://127.0.0.1:{PORTA}"


@pytest.fixture(scope="session")
def base_url():
    """Servidor próprio da trilha, com `web/` em /static — mesma montagem do e2e dos controladores: os e2e do
    repositório correm contra a URL interna servida por nginx, que roda o código de `master`, não o do ramo."""
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from app.main import app as aplicacao
    from app.settings import settings

    object.__setattr__(settings, "PLAT_URL_PUBLICA", URL_TESTE)
    servidor_asgi = Starlette(routes=[
        Mount("/static", StaticFiles(directory=str(RAIZ / "web")), name="estaticos"),
        Mount("/", aplicacao),
    ])
    config = uvicorn.Config(servidor_asgi, host="127.0.0.1", port=PORTA, log_level="warning")
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.time() + 30
    while not servidor.started and time.time() < limite:
        time.sleep(0.1)
    if not servidor.started:
        pytest.skip(f"o servidor de teste não subiu na porta {PORTA}")
    yield URL_TESTE
    servidor.should_exit = True
    thread.join(timeout=20)


def _rede(tela) -> str:
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l402e-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()
    return rid


def test_formulario_de_configuracao_na_tela(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/configuracoes")
    rid = _rede(tela)
    try:
        tela.ir("/redes/configuracoes", "abrir_configuracoes_ms")
        assert page.title().startswith("Configurações de traçado")

        page.select_option("#rede", rid)
        page.wait_for_selector("#configuracoes table", timeout=30000)
        # as seis configurações que vêm com o pacote elétrica-BR já aparecem
        assert int(page.get_attribute("#configuracoes", "data-total")) >= 6
        assert page.locator("#configuracoes tr[data-codigo='kva_a_jusante']").count() == 1
        assert page.locator("#configuracoes td.origem:has-text('pacote')").count() >= 6

        page.wait_for_selector("#formulario:not([hidden])", timeout=30000)
        page.fill("#codigo", "zt-da-tela")
        page.fill("#nome", "Configuração feita na tela")
        page.select_option("#tipo", "jusante")
        page.select_option("#tipo_resultado", "elementos")
        page.fill("#barreira_atributo", "estado")
        page.select_option("#barreira_operador", "=")
        page.fill("#barreira_valor", "aberto")
        page.select_option("#funcao", "soma")
        page.fill("#funcao_atributo", "pot_nom")
        page.click("#salvar")

        page.wait_for_selector("#configuracoes tr[data-codigo='zt-da-tela']", timeout=30000)
        linha = page.locator("#configuracoes tr[data-codigo='zt-da-tela']")
        assert "usuario" in linha.locator("td.origem").text_content()
        assert "soma" in linha.locator("td.funcoes").text_content()

        # a configuração salva pela tela é a mesma que a API devolve, com a barreira e a função dentro
        r = tela.api("GET", f"/api/rede/{rid}/config_tracado?limite=100")
        assert r.status == 200, r.text()
        salva = next(c for c in r.json()["itens"] if c["codigo"] == "zt-da-tela")
        assert salva["tipo"] == "jusante", salva
        assert salva["config"]["barreiras_condicao"] == [
            {"atributo": "estado", "operador": "=", "valor": "aberto", "aplica_a": "ambos"}], salva
        assert salva["config"]["funcoes"][0]["atributo"] == "pot_nom", salva

        linha.locator("button.apagar").click()
        page.wait_for_function(
            "() => !document.querySelector(\"#configuracoes tr[data-codigo='zt-da-tela']\")", timeout=30000)

        tela.capturar_em = None
        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_configuracoes_ms", tela.medidas["abrir_configuracoes_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
