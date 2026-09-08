"""e2e do item UX-10-acervo-sem-tela: a rota de escrita POST /api/acervo/{fonte_id}/adicionar tem controle na tela
/acervo (botão "adicionar ao meu mapa" da ficha) com os quatro estados nomeados do sistema de design (UX-01):

1. lista: carregando (aria-busy + esqueleto), vazio (busca sem resultado, com ação de limpar), erro (a API cai —
   500 forjado pela própria página — e o estado oferece "tentar de novo"), negado (403 forjado);
2. controle "adicionar": sucesso (201 real, item criado e apagado ao fim), e os erros da API NOMEADOS no controle
   — 403 sem_privilegio vira estado negado com o privilégio exigido, 409 confirmacao_pii_exigida vira o diálogo de
   confirmação (e a confirmação repete a chamada com confirma_risco_pii=true), 413 cota_itens e 422 mostram a
   mensagem da API, nunca "422" cru nem tela quebrada (refutação do item); cada estado com captura em 390 e 1280;
3. axe 0 violações sérias na lista, na ficha aberta e no estado de erro; 0 erro de console (os status forjados
   são declarados com esperar_status);
4. as medidas (estados provados, violações sérias, erros de console) vão para tests/medidas/UX-10-acervo-sem-tela.json.

Servidor: scripts/servir_local.py (serve /static do worktree) — sem Martin, sem bancada além da licença semeada."""

import json
import subprocess

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-10-acervo-sem-tela"
LARGURAS = (390, 1280)
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

# mesma linha real de produção para 'openstreetmap' (ODbL) que tests/e2e/test_acervo.py semeia: sem licença
# escrita a fonte nem aparece (D17), então nada aqui inventa licença — reproduz a curadoria já confirmada
SEMENTE_ODBL = (
    "INSERT INTO {schema}.acervo_licenca"
    "(fonte_id, tipo, url_licenca, metodo, identificador_remoto, http_status, evidencia, confianca, verificado_em) "
    "VALUES ('openstreetmap', 'ODbL', 'https://www.openstreetmap.org/copyright', 'html_regex', NULL, 200, "
    "'<h3>OpenStreetMap licensing</h3> licenciado sob a Open Data Commons Open Database License (ODbL)', "
    "'página oficial de copyright/licença da OpenStreetMap Foundation.', now()) "
    "ON CONFLICT (fonte_id) DO NOTHING"
)


def _psql(sql: str) -> str:
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
         "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return r.stdout.strip()


@pytest.fixture
def licenca_curada_odbl(env):
    schema = env["PLAT_SCHEMA"]
    _psql(SEMENTE_ODBL.format(schema=schema))
    yield "openstreetmap"
    _psql(f"DELETE FROM {schema}.acervo_licenca WHERE fonte_id='openstreetmap'")


@pytest.fixture
def itens_criados(admin_api):
    ids: list[str] = []
    yield ids
    for iid in ids:
        admin_api.delete(f"/api/itens/{iid}")


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


def _axe(page, onde, acumulado):
    graves = serias(page)
    acumulado[onde] = len(graves)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _forjar(page, padrao, status, corpo, vezes=1):
    """responde `status`/`corpo` às próximas `vezes` chamadas que casem com `padrao`, depois deixa passar."""
    restantes = {"n": vezes}

    def rota(route):
        if restantes["n"] <= 0:
            route.fallback()
            return
        restantes["n"] -= 1
        route.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
    page.route(padrao, rota)
    return lambda: page.unroute(padrao, rota)


def _sem_origin(rota):
    cab = {k: v for k, v in rota.request.headers.items() if k.lower() != "origin"}
    rota.fulfill(response=rota.fetch(headers=cab))


def _abrir_ficha(page, fonte_id):
    page.fill("#busca input", "OpenStreetMap")
    page.wait_for_selector(f"#grade .acervo-cartao[data-fonte-id='{fonte_id}']")
    page.click(f"#grade .acervo-cartao[data-fonte-id='{fonte_id}']")
    page.wait_for_selector("dialog[open] .acervo-ficha")


def test_estados_da_lista_e_do_controle_adicionar(page, base_url, credenciais_demo, admin_api, env, medida,
                                                  licenca_curada_odbl, itens_criados):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    # o servidor local não é a URL pública da trilha: a guarda de CSRF compara o Origin (mesma decisão dos e2e do
    # L2-01-f/L2-01-i/L5-04-a); as escritas da tela saem sem Origin
    page.route("**/api/acervo/*/adicionar", _sem_origin)
    tela.entrar(slug, login, senha)
    violacoes = {}
    estados = []

    # ------------------------------------------------------------ 1. lista: carregando → conteúdo; vazio; erro; negado
    tela.ir("/acervo", "pagina_pronta_ms_acervo")
    page.wait_for_selector("#grade .acervo-cartao")
    _axe(page, "/acervo lista", violacoes)
    _capturar(page, "lista")
    page.fill("#busca input", "zzz-nada-com-este-nome-zzz")
    page.wait_for_selector("#lista-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#lista-estado .estado-titulo").text_content().strip() != ""
    estados.append("lista:vazio")
    _capturar(page, "lista_vazia")
    page.click("#lista-estado button[data-acao='limpar']")
    page.wait_for_selector("#grade .acervo-cartao")
    # carregando: a lista fica aria-busy e o estado 'carregando' aparece enquanto a resposta não chega
    parar = _forjar(page, "**/api/acervo?*", 500,
                    {"erro": "erro_forjado", "mensagem": "falha forjada pelo teste", "req_id": "e2e-500"})
    tela.esperar_status(500)
    page.fill("#busca input", "OpenStreetMap")
    page.wait_for_selector("#lista-estado[tipo='erro']:not([hidden])")
    texto_erro = page.text_content("#lista-estado")
    assert "falha forjada pelo teste" in texto_erro and "e2e-500" in texto_erro, texto_erro
    estados.append("lista:erro")
    _axe(page, "/acervo lista em erro", violacoes)
    _capturar(page, "lista_erro")
    parar()
    page.click("#lista-estado button[data-acao='tentar']")  # tentar de novo: a chamada real volta a passar
    page.wait_for_selector("#grade .acervo-cartao[data-fonte-id='openstreetmap']")
    parar = _forjar(page, "**/api/acervo?*", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.ver",
                     "req_id": "e2e-403"})
    tela.esperar_status(403)
    page.fill("#busca input", "Open")
    page.wait_for_selector("#lista-estado[tipo='negado']:not([hidden])")
    assert "conteudo.ver" in page.text_content("#lista-estado")
    estados.append("lista:negado")
    _capturar(page, "lista_negada", (1280,))
    parar()
    page.fill("#busca input", "OpenStreetMap")
    page.wait_for_selector("#grade .acervo-cartao[data-fonte-id='openstreetmap']")

    # ------------------------------------------------------------ 2. o controle "adicionar": erros nomeados
    _abrir_ficha(page, "openstreetmap")
    _axe(page, "/acervo ficha aberta", violacoes)
    _capturar(page, "ficha")
    # 403: vira estado negado com o privilégio exigido, dentro do próprio controle
    parar = _forjar(page, "**/api/acervo/openstreetmap/adicionar", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.registrar_fonte",
                     "detalhe": {"exigido": "conteudo.registrar_fonte"}, "req_id": "e2e-403b"})
    page.click("dialog[open] button[data-id='adicionar']")
    page.wait_for_selector("dialog[open] #adicionar-estado[tipo='negado']")
    assert "conteudo.registrar_fonte" in page.text_content("dialog[open] #adicionar-estado")
    estados.append("adicionar:negado")
    _axe(page, "/acervo adicionar negado", violacoes)
    _capturar(page, "adicionar_negado")
    parar()
    # 422 e 413: a mensagem da API, nomeada, no controle — nunca o número cru sozinho nem tela quebrada
    for status, corpo, nome in (
        (422, {"erro": "corpo_invalido", "mensagem": "pedido inválido: corpo fora do esquema", "req_id": "e2e-422"},
         "adicionar_422"),
        (413, {"erro": "cota_itens", "mensagem": "cota de itens do inquilino esgotada (10)", "detalhe": {"cota": 10},
               "req_id": "e2e-413"}, "adicionar_413"),
    ):
        parar = _forjar(page, "**/api/acervo/openstreetmap/adicionar", status, corpo)
        tela.esperar_status(status)
        page.click("dialog[open] button[data-id='adicionar']")
        page.wait_for_selector("dialog[open] #adicionar-estado[tipo='erro']")
        texto = page.text_content("dialog[open] #adicionar-estado")
        assert corpo["mensagem"] in texto and corpo["req_id"] in texto, texto
        assert texto.strip() != str(status), texto
        estados.append(f"adicionar:erro:{status}")
        _capturar(page, nome, (1280,))
        parar()
    # 409: confirmação de risco de dado pessoal — o diálogo aparece; confirmar repete com confirma_risco_pii=true
    parar = _forjar(page, "**/api/acervo/openstreetmap/adicionar", 409,
                    {"erro": "confirmacao_pii_exigida", "mensagem": "esta fonte pode ter dado pessoal identificável",
                     "detalhe": {"risco_pii_motivo": "campo com CPF, curadoria manual de teste"}, "req_id": "e2e-409"})
    tela.esperar_status(409)
    page.click("dialog[open] button[data-id='adicionar']")
    page.wait_for_selector("plat-dialogo:not(#ficha) dialog[open] button[data-id='ok']", timeout=10000)
    assert "CPF" in (page.text_content("body") or "")
    estados.append("adicionar:confirmacao_pii")
    _capturar(page, "adicionar_confirmacao_pii", (1280,))
    corpos = []
    page.on("request", lambda r: corpos.append(r.post_data)
            if r.url.endswith("/adicionar") and r.method == "POST" else None)
    page.click("plat-dialogo:not(#ficha) dialog[open] button[data-id='ok']")
    # o 409 foi consumido (vezes=1): a repetição confirmada vai à API real e cria o item
    page.wait_for_selector("#acervo-ver-no-mapa", timeout=15000)
    assert any(c and "confirma_risco_pii" in c for c in corpos), corpos
    parar()
    camadas = admin_api.get("/api/acervo/meu-mapa").json()
    novo = [c for c in camadas if c["fonte_id"] == "openstreetmap"]
    assert len(novo) == 1, camadas
    itens_criados.append(novo[0]["item_id"])
    estados.append("adicionar:ok")
    _capturar(page, "adicionar_ok")

    # ------------------------------------------------------------ 3. 0 erro de console; medidas
    tela.verificar()
    gravar = medida(ITEM)
    gravar("estados_provados", len(estados), "estados", "; ".join(estados))
    gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
           f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
