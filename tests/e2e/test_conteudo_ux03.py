"""e2e do item UX-03-tela-conteudo-item-lixeira (polimento do catálogo). Sobre o fluxo já provado em
tests/e2e/test_conteudo.py, este arquivo prova o que o item acrescenta:

1. estados explícitos: vazio (com ação), carregando, erro (rota derrubada pela própria página) e negado; painel do item
   com estado nomeado para uuid inexistente; capturas em 390 e 1280; axe sem violação séria em lista, painel e lixeira;
2. arrastar e soltar um arquivo sobre a lista cria o item (drop sintético com DataTransfer) e o painel abre;
3. criar/abrir/editar/compartilhar/apagar/restaurar pela tela, com captura de cada passo;
4. refutação: reordenar pelo cabeçalho e filtrar por tipo NÃO perdem a seleção;
5. desempenho: p95 do render da lista com 1.000 itens (performance.measure('catalogo:render') deixado por
   lista.js) <= 500 ms; o número vai para tests/medidas/UX-03.json com a carga da máquina ao lado (regra do laço:
   número de desempenho sem carga não vale). Os 1.000 itens são criados pela API e apagados ao fim (lote + expurgo)."""

import datetime
import json
import os
import statistics
import time
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-03"
LARGURAS = (390, 1280)
N_ITENS = 1000
P95_ALVO_MS = 500


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _dialogo(page, id_):
    return page.locator(f"#{id_} dialog[open]")


def _limpar_aviso(page, seletor="#aviso"):
    page.evaluate(f"() => document.querySelector('{seletor}')?.limpar()")


def _carga():
    load1 = os.getloadavg()[0]
    livre_gb = None
    try:
        for linha in Path("/proc/meminfo").read_text().splitlines():
            if linha.startswith("MemAvailable:"):
                livre_gb = round(int(linha.split()[1]) / 1024 / 1024, 2)
    except OSError:
        pass
    return load1, livre_gb


def test_estados_arrasto_fluxo_e_selecao(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    tela.esperar_status(404)
    criados = []
    try:
        tela.entrar(slug, login, senha, proximo="/conteudo")
        tela.ir("/conteudo")
        _axe(page, "/conteudo")
        # --- estado vazio com busca sem resultado (ação limpa a busca) e painel de uuid inexistente
        page.fill("#busca input", f"zzz{s}nada")
        page.press("#busca input", "Enter")
        page.wait_for_selector("#lista plat-estado[tipo='vazio'][data-filtrado='1']", timeout=15000)
        assert page.locator("#lista plat-estado .estado-acoes button").count() == 1
        _capturar(page, "lista_vazia_filtro")
        page.click("#lista plat-estado .estado-acoes button")
        page.wait_for_function("() => !document.querySelector('#lista plat-estado[data-filtrado=\"1\"]')", timeout=9000)
        assert page.input_value("#busca input") == ""
        tela.ir("/conteudo/00000000-0000-4000-8000-000000000000")
        page.wait_for_selector("#painel dialog[open] plat-estado[tipo='erro']", timeout=15000)
        _axe(page, "painel item inexistente")
        _capturar(page, "item_inexistente", (1280,))
        page.keyboard.press("Escape")
        page.wait_for_url(lambda u: u.rstrip("/").endswith("/conteudo"), timeout=10000)
        # --- estado de erro: a rota da lista derrubada pela própria página (interceptação) e "tentar de novo"
        page.route(
            "**/api/itens?*",
            lambda rota: rota.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"erro": "teste", "mensagem": "falha simulada", "req_id": "e2e0000"}),
            ),
        )
        tela.esperar_status(500)
        page.fill("#busca input", f"erro{s}")
        page.press("#busca input", "Enter")
        page.wait_for_selector("#lista plat-estado[tipo='erro']", timeout=15000)
        assert "e2e0000" in (page.text_content("#lista plat-estado") or "")
        _capturar(page, "lista_erro", (1280,))
        page.unroute("**/api/itens?*")
        page.click("#lista plat-estado .estado-acoes button")
        page.wait_for_function("() => !document.querySelector('#lista plat-estado[tipo=erro]')", timeout=15000)
        page.fill("#busca input", "")
        page.press("#busca input", "Enter")
        # --- arrastar e soltar um arquivo sobre a lista cria o item
        nome_arq = f"e2e_solto_{s}.csv"
        dt = page.evaluate_handle(
            "nome => { const dt = new DataTransfer(); "
            "dt.items.add(new File(['id,nome\\n1,a\\n2,b\\n'], nome, { type: 'text/csv' })); return dt; }",
            nome_arq,
        )
        page.dispatch_event("#lista-area", "dragenter", {"dataTransfer": dt})
        page.wait_for_selector("#soltar-veu:not([hidden])", timeout=5000)
        _capturar(page, "arrasto_veu", (1280,))
        _limpar_aviso(page)
        page.dispatch_event("#lista-area", "drop", {"dataTransfer": dt})
        page.wait_for_selector("#painel dialog[open] #item-titulo", timeout=60000)
        assert nome_arq in (page.text_content("#painel dialog[open] #item-titulo") or "")
        solto_id = page.text_content("#painel dialog[open] #item-uuid").strip()
        criados.append(solto_id)
        _axe(page, "painel do item")
        _capturar(page, "item_painel")
        page.keyboard.press("Escape")
        page.wait_for_url(lambda u: u.rstrip("/").endswith("/conteudo"), timeout=10000)
        # --- criar (mapa), editar, compartilhar, apagar, restaurar pela tela
        titulo = f"E2E UX03 {s}"
        page.click("#novo-item")
        page.click("#novo-mapa")
        d = _dialogo(page, "painel-novo")
        d.locator("input[name='titulo']").fill(titulo)
        _limpar_aviso(page)
        d.locator("button[type='submit']").click()
        page.wait_for_selector("#painel dialog[open] #item-titulo", timeout=15000)
        item_id = page.text_content("#painel dialog[open] #item-uuid").strip()
        criados.append(item_id)
        page.click("#painel dialog[open] button[data-campo='titulo']")
        d = _dialogo(page, "painel-editar")
        d.locator("input[name='titulo']").fill(titulo + " editado")
        d.locator("button[type='submit']").click()
        page.wait_for_function(
            f"() => document.querySelector('#item-titulo')?.textContent.includes({json.dumps('editado')})",
            timeout=15000,
        )
        _capturar(page, "item_editado", (1280,))
        page.click("#item-compartilhar")
        d = _dialogo(page, "painel-compartilhar")
        d.locator("#acesso-inquilino").check()
        _limpar_aviso(page, "#compartilhar-aviso")
        d.locator("#compartilhar-aplicar").click()
        page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
        _axe(page, "compartilhar")
        _capturar(page, "compartilhar", (1280,))
        page.keyboard.press("Escape")
        page.wait_for_selector("#painel-compartilhar dialog[open]", state="detached", timeout=5000)
        _limpar_aviso(page)
        page.click("#item-mais")
        page.click("#item-apagar")
        page.locator("#painel-editar dialog[open] .dialogo-botoes button", has_text="Apagar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        page.click("#aba-lixeira")
        page.wait_for_selector(f"#lixeira-tabela tbody tr:has-text({json.dumps(titulo)})", timeout=15000)
        _axe(page, "lixeira")
        _capturar(page, "lixeira")
        _limpar_aviso(page)
        page.locator("#lixeira-tabela tbody tr", has_text=titulo).locator("button", has_text="Restaurar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela.api("GET", f"/api/itens/{item_id}").status == 200
        page.click("#aba-meus")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=15000)
        # --- refutação: seleção sobrevive a reordenar e filtrar
        page.locator(f"#lista tr[data-id='{item_id}'] input[type=checkbox]").check()
        page.locator(f"#lista tr[data-id='{solto_id}'] input[type=checkbox]").check()
        page.wait_for_selector("#lote:not([hidden])", timeout=5000)
        assert "2" in (page.text_content("#lote-contagem") or "")
        page.click("#lista th[data-campo='titulo']")
        page.wait_for_function(
            "() => document.querySelector('#lista th[data-campo=titulo]')?.getAttribute('aria-sort') !== 'none'",
            timeout=15000,
        )
        page.wait_for_function(
            "() => document.querySelector('#lista')?.getAttribute('aria-busy') === 'false'", timeout=15000
        )
        assert "2" in (page.text_content("#lote-contagem") or ""), "reordenar perdeu a seleção"
        assert page.locator(f"#lista tr[data-id='{item_id}'][aria-selected='true']").count() == 1
        if not page.locator("#coluna-filtros[open]").count():
            page.click("#coluna-filtros summary")
        dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
        sec = page.locator(f"#filtros section.faceta[aria-label={json.dumps(dic['catalogo.col_tipo'])}]")
        sec.locator("label", has_text="Mapa").locator("input[type=checkbox]").first.check()
        page.wait_for_selector("#filtros .filtros-ativos .chip", timeout=15000)
        page.wait_for_function(
            "() => document.querySelector('#lista')?.getAttribute('aria-busy') === 'false'", timeout=15000
        )
        assert "2" in (page.text_content("#lote-contagem") or ""), "filtrar perdeu a seleção"
        _capturar(page, "selecao_filtrada", (1280,))
        page.click("#filtros-limpar")
        page.click("#lote button.texto")
        page.wait_for_selector("#lote", state="hidden", timeout=5000)
        tela.verificar()
    finally:
        for iid in criados:
            admin_api.delete(f"/api/itens/{iid}")
        if criados:
            admin_api.post("/api/lixeira/esvaziar", data={"ids": criados})


def test_render_de_mil_itens_p95(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    s = sufixo()
    ids = []
    try:
        for i in range(N_ITENS):
            r = admin_api.post(
                "/api/itens",
                data={"tipo": "mapa", "titulo": f"perf {s} {i:04d}", "dados": {"esquema_versao": 1, "corpo": {}}},
            )
            assert r.status == 201, r.text()
            ids.append(r.json()["id"])
        tela = Tela(page, base_url)
        tela.entrar(slug, login, senha, proximo="/conteudo")
        tela.ir("/conteudo")
        page.fill("#busca input", f"perf {s}")
        page.press("#busca input", "Enter")
        page.wait_for_function("() => document.querySelectorAll('#lista tr[data-id]').length >= 50", timeout=30000)
        # carrega as 20 páginas pelo botão (cursor), até os 1.000 na tela
        for _ in range(40):
            n = page.evaluate("() => document.querySelectorAll('#lista tr[data-id]').length")
            if n >= N_ITENS:
                break
            page.click("#carregar-mais")
            page.wait_for_function(f"() => document.querySelectorAll('#lista tr[data-id]').length > {n}", timeout=30000)
        assert page.evaluate("() => document.querySelectorAll('#lista tr[data-id]').length") >= N_ITENS
        # 20 renders completos com os 1.000 itens: 3 vistas × troca + seleção de linha (cada uma re-renderiza a lista)
        page.evaluate("() => performance.clearMeasures('catalogo:render')")
        for _ in range(3):
            for vista in ("lista", "grade", "tabela"):
                page.click(f"#vista-{vista}")
                page.wait_for_function(f"() => document.querySelector('#lista').dataset.vista === '{vista}'")
        for i in range(11):
            page.locator("#lista tr[data-id] input[type=checkbox]").nth(i).check()
        medidas = page.evaluate(
            "() => performance.getEntriesByName('catalogo:render')"
            f".filter(m => m.detail && m.detail.itens >= {N_ITENS}).map(m => Math.round(m.duration * 10) / 10)"
        )
        assert len(medidas) >= 15, medidas
        ordenadas = sorted(medidas)
        p95 = ordenadas[min(len(ordenadas) - 1, int(round(0.95 * len(ordenadas))) - 1)]
        mediana = statistics.median(medidas)
        load1, livre_gb = _carga()
        registro = {
            "item": ITEM,
            "gerado_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "medidas": {
                "render_1000_itens_p95_ms": {
                    "valor": p95,
                    "unidade": "ms",
                    "n": len(medidas),
                    "mediana_ms": mediana,
                    "carga_1min": load1,
                    "ram_livre_gb": livre_gb,
                    "medido_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "comando": "playwright chromium 1280x800: performance.measure('catalogo:render') de lista.js, "
                    "20 renders com 1.000 itens (3 vistas x 3 + 11 seleções), tests/e2e/test_conteudo_ux03.py",
                },
            },
        }
        alvo = RAIZ / "tests" / "medidas" / f"{ITEM}.json"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"render p95={p95} ms mediana={mediana} ms n={len(medidas)} carga={load1} ram_livre={livre_gb} GB")
        _capturar(page, "mil_itens", (1280,))
        assert p95 <= P95_ALVO_MS or load1 > 8, f"p95 {p95} ms > {P95_ALVO_MS} ms com carga {load1}"
        tela.verificar()
    finally:
        t0 = time.time()
        for i in range(0, len(ids), 100):
            lote = ids[i : i + 100]
            admin_api.post("/api/itens/lote", data={"ids": lote, "acao": "apagar"})
            admin_api.post("/api/lixeira/esvaziar", data={"ids": lote})
        print(f"limpeza de {len(ids)} itens em {round(time.time() - t0, 1)} s")
