"""e2e do item L5-20-sites-paginas-publicas, no chromium do playwright:

1. o site é montado por ARRASTO de verdade na tela `/sites` (HTML5 Drag and Drop, as primitivas do L5-08):
   página -> seção -> seis cartões (texto, imagem, galeria, busca, chamada, estatísticas — os que rendem
   superfície de acessibilidade: formulário com rótulo, imagem com alternativo, lista de links); é gravado e
   publicado pela própria tela;
2. a página publicada `/s/<inquilino>/` mostra o conteúdo montado — e o mesmo endereço, lido como texto puro
   pelo contexto de rede do navegador (sem executar script), já traz o texto (a prova sem navegador nenhum
   está em `tests/api/catalogo/test_site.py`);
3. acessibilidade: axe-core 4.12.1 (`tests/e2e/vendor/`, MPL-2.0, só teste) sobre a página publicada, com a
   pontuação ponderada descrita em `_pontuacao_acessibilidade` — a cláusula do portão pede "Lighthouse
   acessibilidade >= 90" e o binário do Lighthouse NÃO está instalado nesta máquina (seria dependência npm
   nova, com o disco a 98 %); o que se mede é o MOTOR que o Lighthouse usa nessa categoria, com o mesmo
   esquema de auditoria ponderada. A medida é gravada dizendo exatamente isso, sem chamar-se de Lighthouse.

Refutação do adversário no mesmo arquivo: nenhum controle da página publicada sem nome acessível, e o
`X-Robots-Tag` conferido em cada uma das páginas do site.
"""

import pytest

from tests.e2e.apoio import RAIZ, Tela, sufixo

ITEM = "L5-20-sites-paginas-publicas"
AXE = RAIZ / "tests" / "e2e" / "vendor" / "axe-4.12.1.min.js"
PESO = {"critical": 10, "serious": 7, "moderate": 3, "minor": 1}
PESO_PADRAO = 3

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """O e2e roda contra o servidor da trilha, com certificado autoassinado (TLS é obrigatório: a defesa de
    CSRF compara `Origin` com `PLAT_URL_PUBLICA`, que é sempre https)."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture
def admin_api(playwright, base_url, credenciais_demo):
    """Mesmo contexto autenticado do conftest, com `ignore_https_errors`: o servidor da trilha usa certificado
    autoassinado (ver o docstring do módulo)."""
    slug, login, senha = credenciais_demo
    ctx = playwright.request.new_context(base_url=base_url, ignore_https_errors=True)
    r = ctx.post("/api/login", data={"inquilino": slug, "login": login, "senha": senha})
    assert r.status == 200 and r.json().get("ok") is True, (r.status, r.text())
    yield ctx
    ctx.post("/api/logout", data={})
    ctx.dispose()


def _criar_site(admin_api, titulo: str) -> str:
    r = admin_api.post("/api/itens", data={
        "tipo": "site", "titulo": titulo,
        "dados": {"tipo": "site", "esquema_versao": 1, "corpo": {"nos": [], "ligacoes": []}}})
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _id_do_tipo(page, tipo: str) -> str:
    return page.get_attribute(f'[data-tipo="{tipo}"].no-editor', "data-no")


def _fundo_da_tela(page) -> dict:
    caixa = page.locator("#tela").bounding_box()
    return {"x": 20, "y": caixa["height"] - 8}


def _montar_por_arrasto(page) -> None:
    page.drag_and_drop('[data-paleta="pagina"]', "#tela", target_position=_fundo_da_tela(page))
    pagina = _id_do_tipo(page, "pagina")
    page.drag_and_drop('[data-paleta="secao"]', f'[data-filhos-de="{pagina}"]')
    secao = _id_do_tipo(page, "secao")
    for tipo in ("texto", "imagem", "galeria", "busca", "chamada", "estatisticas"):
        page.drag_and_drop(f'[data-paleta="{tipo}"]', f'[data-filhos-de="{secao}"]')
    # o cabeçalho e o rodapé pertencem ao site inteiro: soltos no fundo da tela, fora da página
    page.drag_and_drop('[data-paleta="cabecalho"]', "#tela", target_position=_fundo_da_tela(page))
    page.drag_and_drop('[data-paleta="rodape"]', "#tela", target_position=_fundo_da_tela(page))
    texto = _id_do_tipo(page, "texto")
    page.click(f'[data-no="{texto}"]')
    page.fill('[data-prop="texto"]', "Conteúdo montado por arrasto na tela do construtor.")
    page.keyboard.press("Tab")
    page.wait_for_function(
        "(id) => document.querySelector(`[data-resumo=\"${id}\"]`) !== null", arg=texto, timeout=5000)


def _pontuacao_acessibilidade(page) -> tuple[float, list[dict]]:
    """Pontuação de acessibilidade no esquema do Lighthouse: cada auditoria é aprovada ou reprovada (sem meio
    termo) e vale um peso; a nota é a soma dos pesos aprovados sobre a soma de todos os pesos, em 0-100. O
    conjunto de auditorias é o do axe-core (o mesmo motor que a categoria de acessibilidade do Lighthouse usa)
    nas etiquetas WCAG 2.0/2.1 A e AA, e o peso vem do impacto que o próprio axe declara na regra
    (critical 10, serious 7, moderate 3, minor 1; sem impacto declarado, 3)."""
    page.add_script_tag(path=str(AXE))
    resultado = page.evaluate(
        "async () => { const r = await axe.run(document, {runOnly: {type: 'tag',"
        " values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}});"
        " const enxuto = (l) => l.map((v) => ({id: v.id, impact: v.impact, help: v.help,"
        "   alvos: v.nodes.slice(0, 5).map((n) => n.target.join(' '))}));"
        " return {passes: enxuto(r.passes), violations: enxuto(r.violations)}; }"
    )
    peso = lambda a: PESO.get(a.get("impact") or "", PESO_PADRAO)  # noqa: E731
    aprovado = sum(peso(a) for a in resultado["passes"])
    reprovado = sum(peso(a) for a in resultado["violations"])
    total = aprovado + reprovado
    return (100.0 if total == 0 else round(100 * aprovado / total, 1)), resultado["violations"]


def test_montar_por_arrasto_publicar_e_ver_a_pagina(page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_site(admin_api, f"zt-site-{sufixo()}")
    try:
        tela.ir(f"/sites?item={iid}")
        page.wait_for_selector("#tela", timeout=10000)
        _montar_por_arrasto(page)
        page.click("#salvar")
        page.wait_for_function(
            "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000)
        page.click("#publicar")
        page.wait_for_function(
            "() => document.getElementById('site-estado').textContent.startsWith('publicado')", timeout=10000)
        tela.verificar()

        # a página publicada, anônima: o texto montado por arrasto está lá
        # `bypass_csp`: a página publicada manda `script-src 'self'`, que (corretamente) impede injetar o
        # axe-core na página. O que se mede é o DOM, idêntico com ou sem a política; a política em si é
        # conferida em tests/api/catalogo/test_site.py, não relaxada aqui.
        anonimo = page.context.browser.new_context(ignore_https_errors=True, locale="pt-BR", bypass_csp=True)
        pagina = anonimo.new_page()
        pagina.goto(f"{base_url}/s/{slug}/", wait_until="domcontentloaded")
        assert "Conteúdo montado por arrasto na tela do construtor." in pagina.content()
        # o mesmo endereço lido como TEXTO, sem execução de script
        resposta = anonimo.request.get(f"{base_url}/s/{slug}/")
        assert resposta.status == 200
        assert "Conteúdo montado por arrasto na tela do construtor." in resposta.text()
        assert resposta.headers["x-robots-tag"] == "noindex, nofollow"

        nota, violacoes = _pontuacao_acessibilidade(pagina)
        graves = [v for v in violacoes if v["impact"] in ("critical", "serious")]
        medida(ITEM)(
            "acessibilidade_pontuacao", nota, "0-100",
            "axe-core 4.12.1 (motor da categoria de acessibilidade do Lighthouse) sobre /s/<inquilino>/, "
            "etiquetas wcag2a/wcag2aa/wcag21a/wcag21aa, auditorias ponderadas por impacto "
            "(critical 10, serious 7, moderate 3, minor 1); o binário do Lighthouse não está instalado nesta máquina",
        )
        medida(ITEM)("acessibilidade_violacoes_criticas_serias", len(graves), "violações",
                     "axe.run() na página publicada, filtro impact in (critical, serious)")
        assert graves == [], graves
        assert nota >= 90, (nota, violacoes)

        # adversário: nenhum controle sem nome acessível na página publicada
        sem_nome = pagina.evaluate(
            "() => [...document.querySelectorAll('a,button,input,select,iframe,img')]"
            " .filter((e) => !(e.getAttribute('aria-label') || e.getAttribute('title') ||"
            "   (e.tagName === 'IMG' ? e.getAttribute('alt') !== null : (e.textContent || '').trim()) ||"
            "   (e.labels && e.labels.length)))"
            " .map((e) => e.outerHTML.slice(0, 80))"
        )
        assert sem_nome == [], sem_nome
        anonimo.close()
    finally:
        admin_api.delete(f"/api/itens/{iid}/site")
        admin_api.delete(f"/api/itens/{iid}?cascata=true")
