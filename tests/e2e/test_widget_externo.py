"""e2e do SDK de widget externo (item L5-36-widgets-personalizados-sdk), no chromium do playwright contra a
frente de teste sem nginx (tests/e2e/frente_estatica.py serve /static/):

1. caminho feliz: admin instala o semáforo de exemplo (pacote SANDBOX) e um widget de rótulo em modo normal;
   o documento do aplicativo os cita; /aplicativo?item= monta os dois — o sandbox corre num iframe de origem
   opaca com data-widget-origem no elemento, e o clique na tabela chega a ele como ação (`clique` com ids) e
   pinta o nível; o modo normal importa o TEXTO verificado (blob) e define o próprio elemento;
2. adversário: DENTRO do sandbox document.cookie lança SecurityError, fetch para a API é barrado pelo CSP
   (connect-src 'none') — e o único erro de console da página é a recusa do próprio CSP;
3. integridade: módulo adulterado no caminho (page.route muda o corpo mantendo o cabeçalho de sha256) é
   recusado pelo navegador — aviso nomeado e caixa de erro no lugar do widget, a página segue."""

import json

import pytest

from app.catalogo.documento import gerar_ulid
from scripts.widget_empacotar import empacotar
from tests.e2e.apoio import Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L5-36-widgets-personalizados-sdk"
EXEMPLO = "web/ext/exemplo/semaforo"

ROTULO_MODULO = """import { PlatWidget, definir } from '/static/js/widgets/base.js';
class PlatRotuloSimples extends PlatWidget {
  renderizar() {
    const p = document.createElement('p');
    p.textContent = this.configuracao.texto || 'sem texto';
    p.setAttribute('data-rotulo-simples', '1');
    this.replaceChildren(p);
  }
}
definir('plat-rotulo-simples', PlatRotuloSimples);
"""

ROTULO_MANIFESTO = {
    "nome": "rotulo-simples", "versao": "1.0.0", "api_widget": 1,
    "modulo": "./rotulo.js", "elemento": "plat-rotulo-simples",
    "esquema_config": {"type": "object", "additionalProperties": False,
                       "properties": {"texto": {"type": "string", "maxLength": 200}}},
    "eventos": [], "acoes": ["piscar"], "fontes": {"min": 0, "max": 0, "tipos": []},
    "i18n": "widget.rotulo-simples",
}


def _pacote_rotulo() -> dict:
    return {"manifesto": ROTULO_MANIFESTO, "modulo": ROTULO_MODULO, "sandbox": False}


def _documento() -> dict:
    n_tabela, n_semaforo, n_rotulo = gerar_ulid(), gerar_ulid(), gerar_ulid()
    return {"tipo": "app", "esquema_versao": 3, "corpo": {
        "nos": [
            {"id": n_tabela, "tipo": "tabela", "posicao": {"coluna": 1, "linha": 1, "largura": 6, "altura": 2},
             "configuracao": {"colunas": [{"campo": "nome", "rotulo": "Nome"}],
                              "linhas": [{"__id": "a", "nome": "Um"}, {"__id": "b", "nome": "Dois"}]}},
            {"id": n_semaforo, "tipo": "semaforo", "posicao": {"coluna": 7, "linha": 1, "largura": 3, "altura": 2},
             "configuracao": {"rotulo": "Nível da seleção"}},
            {"id": n_rotulo, "tipo": "rotulo-simples", "posicao": {"coluna": 10, "linha": 1, "largura": 3, "altura": 1},
             "configuracao": {"texto": "modo normal"}},
        ],
        "ligacoes": [{"origem": n_tabela, "alvo": n_semaforo, "evento": "clique", "acao": "clique"}],
    }}


@pytest.fixture
def tela(page, base_url, credenciais_demo):
    t = Tela(page, base_url)
    t.entrar(*credenciais_demo, proximo="/")
    yield t
    page.context.close()


@pytest.fixture
def app_item(tela):
    """Item de aplicativo citando os dois widgets; apagado no fim."""
    r = tela.api("POST", "/api/itens", corpo=json.dumps({"tipo": "app", "titulo": "zt-app-widgets-externos",
                                                         "dados": _documento()}))
    assert r.status == 201, r.text()
    item = r.json()
    yield item
    tela.api("DELETE", f"/api/itens/{item['id']}")


@pytest.fixture
def instalado(tela):
    """Semáforo (sandbox) + rótulo (modo normal) instalados; apagados no fim."""
    for pacote in (empacotar(f"{EXEMPLO}"), _pacote_rotulo()):
        r = tela.api("POST", "/api/widgets/externos", corpo=json.dumps(pacote))
        assert r.status == 201, r.text()
    yield
    for nome in ("semaforo", "rotulo-simples"):
        tela.api("DELETE", f"/api/widgets/externos/{nome}")


def test_widget_externo_sandbox_e_modo_normal_no_aplicativo(tela, instalado, app_item, base_url, medida):
    tela.ir(f"{base_url}/aplicativo?item={app_item['id']}")

    # sandbox: hospedeiro com a origem do código à vista, iframe de origem opaca montado
    hospedeiro = tela.page.locator("plat-widget-sandboxe[data-tipo=semaforo]")
    assert hospedeiro.count() == 1
    moldura = hospedeiro.locator("iframe[data-widget-origem]")
    assert moldura.get_attribute("data-widget-origem").startswith("widget externo semaforo 1.0.0 (sandbox")
    assert moldura.get_attribute("sandbox") == "allow-scripts"

    dentro = tela.page.frame_locator("plat-widget-sandboxe iframe")
    dentro.locator('[data-nivel="cinza"]').wait_for(timeout=5000)  # o semáforo já montou e pintou o nível inicial

    # modo normal: o módulo importado (texto verificado) definiu o próprio elemento
    assert tela.page.locator("plat-rotulo-simples p[data-rotulo-simples]").text_content() == "modo normal"

    # a ligação do documento leva o clique da tabela ao sandbox (a tabela emite sempre 1 id) → verde
    tela.page.locator("plat-tabela tbody tr").first.click()
    dentro.locator('[data-nivel="verde"]').wait_for(timeout=5000)
    # a segunda ação declarada no manifesto ('selecao_mudou') também cruza a ponte: 2 ids → amarelo
    tela.page.evaluate("(host) => host.executar('selecao_mudou', { ids: ['a', 'b'] })",
                       hospedeiro.element_handle())
    dentro.locator('[data-nivel="amarelo"]').wait_for(timeout=5000)

    # o semáforo falou pelo barramento de verdade (evento declarado no manifesto)
    emitidos = tela.page.evaluate("""async () => {
      const bus = window.plat.widgets.barramento;
      let recebido = null;
      bus.addEventListener('evento', (e) => { if (e.detail.nome === 'semaforo.nivel') recebido = e.detail.detalhe; });
      const host = document.querySelector('plat-widget-sandboxe[data-tipo=semaforo]');
      host.emitir('semaforo.nivel', { nivel: 'vermelho' });
      await new Promise((r) => setTimeout(r, 50));
      return recebido;
    }""")
    assert emitidos == {"nivel": "vermelho"}

    tela.verificar()
    pintura = tela.page.evaluate(
        "() => performance.getEntriesByType('paint').find((e) => e.name === 'first-contentful-paint')?.startTime || 0")
    gravar = medida(ITEM)
    gravar("carregamento_pagina_ms", pintura, "ms",
           "First Contentful Paint de /aplicativo?item= com 2 widgets externos instalados "
           "(tests/e2e/test_widget_externo.py)")


def test_adversario_dentro_do_sandbox_sem_cookie_e_sem_rede(tela, instalado, app_item, base_url):
    # coletor local: o erro de console do CSP é a PROVA do bloqueio, e o teste quer nomeá-lo
    erros: list[str] = []
    tela.page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    tela.ir(f"{base_url}/aplicativo?item={app_item['id']}")
    dentro = tela.page.frame_locator("plat-widget-sandboxe iframe")
    dentro.locator('[data-nivel="cinza"]').wait_for(timeout=5000)  # o semáforo já montou e pintou o nível inicial

    # a sonda roda DENTRO da moldura: de fora, até `window.origin` é negado (prova extra do isolamento)
    moldura = next(f for f in tela.page.frames if f is not tela.page.main_frame)
    resultado = moldura.evaluate("""async () => {
      const fora = { cookie: null, fetch: null, origem: null };
      try { fora.origem = window.origin; } catch (e) { fora.origem = e.name; }
      try { window.document.cookie; } catch (e) { fora.cookie = e.name; }
      try { const r = await fetch('/api/eu'); fora.fetch = `HTTP ${r.status}`; }
      catch (e) { fora.fetch = e.name; }
      return fora;
    }""")
    assert resultado["origem"] == "null", "sandbox com allow-same-origin = isolamento de mentira"
    assert resultado["cookie"] == "SecurityError"
    assert resultado["fetch"] == "TypeError", "fetch do sandbox não foi barrado pelo CSP"
    # o único erro de console é a recusa do próprio CSP (a prova do bloqueio), nada mais
    csp = [e for e in erros if "Content Security Policy" in e and "connect-src" in e]
    assert csp, "o CSP deveria registrar a recusa do fetch"
    assert [e for e in erros if "Content Security Policy" not in e] == []


def test_modulo_adulterado_no_caminho_e_recusado_pelo_hash(tela, instalado, app_item, base_url, page):
    sha = tela.api("GET", "/api/widgets/externos/semaforo").json()["sha256"]
    # mesmo cabeçalho de sha256, corpo diferente: o navegador precisa pegar pela conferência do conteúdo
    corpo = tela.api("GET", "/api/widgets/externos/semaforo/modulo.js").text() + "\n// adulterado\n"

    def adulterar(rota):
        rota.fulfill(status=200, headers={"X-Plat-Widget-Sha256": sha,
                                          "Content-Type": "text/javascript; charset=utf-8"}, body=corpo)

    page.route("**/api/widgets/externos/semaforo/modulo.js", adulterar)
    try:
        tela.ir(f"{base_url}/aplicativo?item={app_item['id']}")
        aviso = page.locator('#avisos-barramento p[data-tipo="widget-externo-recusado"]')
        assert aviso.count() == 1
        assert "sha256" in aviso.text_content()
        assert page.locator("plat-widget-sandboxe[data-tipo=semaforo]").count() == 0
        erro = page.locator('.plat-widget-erro[data-widget="semaforo"]')
        assert erro.count() == 1
        assert "tipo desconhecido" in erro.text_content()
        # o que NÃO foi adulterado segue montado
        assert page.locator("plat-rotulo-simples p[data-rotulo-simples]").count() == 1
    finally:
        page.unroute("**/api/widgets/externos/semaforo/modulo.js")
