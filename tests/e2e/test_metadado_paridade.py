"""e2e do item L0-09-metadado-catalogo (cláusulas "editor de metadado na tela", "e2e" e "paridade escrita",
na mesma prova): abre a aba Metadado de uma camada no Chromium, preenche o essencial, valida, salva — e então,
pelo MESMO cookie da sessão, confere que cada valor digitado na tela aparece nas três saídas ISO do catálogo
(GET /api/itens/{id}/metadado.xml em 19139 e em 19115-3, e CSW GetRecordById com outputSchema gmd). 0 erro de
console fora do 404 esperado da miniatura ausente.

Servidor próprio da trilha (mesmo padrão de tests/e2e/test_rede_simples.py): a URL pública da trilha é
deliberadamente inválida (laco/trilha_ambiente.sh), então o teste sobe a aplicação DESTE worktree embrulhada
num Starlette com StaticFiles — é montagem de teste, a aplicação não muda. tests/e2e/test_metadado_mgb.py
cobra o fluxo do editor campo a campo na bancada com DNS; aqui fica a ponta que o portão do L0-09 pede: o que
se digita NA TELA é o que a descoberta externa devolve.

A camada é real em `d_demo` preparada por `plat.camada_preparar` (o caminho físico da ingestão, mesmo helper
de tests/api/test_tabela_atributos.py, solta no fim): sem ela o mapa da página do item responde 500 e o e2e
mediria a ausência da tabela, não o metadado.
"""

import os
import threading
import time

import pytest
import uvicorn

from tests.api.test_tabela_atributos import _criar_camada
from tests.e2e.apoio import RAIZ, sufixo  # noqa: F401 (RAIZ usada na montagem estática abaixo)
from tests.e2e.apoio_catalogo import TelaCatalogo
from tests.e2e.test_mapa_tabela import _SessaoDoNavegador

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

PORTA = 8317  # porta desta trilha; conferida livre com `ss -ltn` antes de subir
URL_TESTE = f"http://127.0.0.1:{PORTA}"


@pytest.fixture(scope="session")
def base_url():
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from app.main import app as aplicacao
    from app.settings import settings

    # A guarda de CSRF compara o cabeçalho Origin com PLAT_URL_PUBLICA (app/auth/sessao.py). O navegador do
    # teste fala com 127.0.0.1, então sem este ajuste toda escrita da tela viria 403. `settings` recusa URL
    # que não comece com https por variável de ambiente; ajuste local do processo de teste.
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


def test_editor_na_tela_e_o_que_o_catalogo_publica(page, base_url, credenciais_demo, medida):
    if not os.environ.get("PLAT_DSN"):
        pytest.skip("sem PLAT_DSN no ambiente: a camada de teste precisa do banco")
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    org = f"Org e2e paridade {s}"
    email = f"paridade-{s}@exemplo.org"
    licenca = f"Licenca e2e {s}"
    crs = "31983"
    tela = TelaCatalogo(page, base_url)
    tela.esperar_status(404)  # a miniatura ausente responde 404 e o Chromium registra como console.error
    tela.entrar(slug, admin_login, senha_admin)
    # a camada entra pelo MESMO cookie da tela (é a sessão do usuário que vai abrir o editor)
    item_id, _schema, _tabela, fechar = _criar_camada(_SessaoDoNavegador(tela), os.environ, 1)
    try:
        tela.ir(f"/conteudo/{item_id}")
        page.wait_for_selector("#item-abas", timeout=15000)
        page.click("#item-aba-metadado")
        page.wait_for_selector("#mgb-form", timeout=15000)

        page.fill("#mgb-contato-org", org)
        page.fill("#mgb-contato-email", email)
        page.fill("#mgb-licenca", licenca)
        page.fill("#mgb-esp-xmin", "-48.5")
        page.fill("#mgb-esp-ymin", "-16.2")
        page.fill("#mgb-esp-xmax", "-47.1")
        page.fill("#mgb-esp-ymax", "-15.3")
        page.fill("#mgb-sr-codigo", crs)
        page.fill("#mgb-sr-codespace", "EPSG")
        page.fill("#mgb-item-resumo", f"resumo da paridade escrita {s}")
        page.fill("#mgb-item-tags", "zt-e2e-paridade")
        page.click("#mgb-validar")
        page.wait_for_selector("#mgb-faltantes .ok", timeout=10000)
        tela.capturar("paridade_metadado_validado")

        page.click("#mgb-salvar")
        page.wait_for_selector("#mgb-aviso[data-tipo='ok']", timeout=15000)
        tela.capturar("paridade_metadado_salvo")

        # paridade escrita, ponta a ponta: o digitado na tela tem de estar nas três saídas ISO do catálogo —
        # inclusive a extensão espacial DECLARADA (que diverge do extent do dado de propósito: é ela que a
        # exportação publica, regra metadado_mgb.espacial_efetivo)
        escritos = (org, email, licenca, crs, "-48.5", "-15.3")
        saidas = {
            "metadado_xml_19139": tela.api("GET", f"/api/itens/{item_id}/metadado.xml"),
            "metadado_xml_19115_3": tela.api("GET", f"/api/itens/{item_id}/metadado.xml?formato=19115-3"),
            "csw_getrecordbyid_iso": tela.api(
                "GET",
                f"/csw?REQUEST=GetRecordById&ID={item_id}"
                "&OUTPUTSCHEMA=http://www.isotc211.org/2005/gmd",
            ),
        }
        for nome, resposta in saidas.items():
            assert resposta.ok, (nome, resposta.status)
            corpo = resposta.text()
            for escrito in escritos:
                assert escrito in corpo, f"{nome} não devolveu o que a tela gravou: {escrito!r}"

        ruins = [(u, st) for u, st in tela.respostas if st >= 400 and st not in tela.esperados]
        assert not ruins, f"respostas >= 400 fora das esperadas: {ruins}"
        tela.verificar()
        medida("L0-09-metadado-catalogo")(
            "e2e_paridade_editor_tela_iso_passou", 1, "bool",
            "playwright chromium (servidor local da trilha): aba Metadado, preencher essencial, validar, "
            "salvar e conferir os 6 valores nas 3 saídas ISO (19139, 19115-3, CSW GetRecordById)",
        )
    finally:
        fechar()
