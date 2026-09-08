"""e2e do roteiro de demonstração (item L7-29-roteiro-demonstração): percorre os 9 passos de
docs/DEMO.md na ordem, contra a instalação real, com captura de tela POR PASSO
(tests/e2e/capturas/L7-29-roteiro-demonstracao_pNN_<passo>.png) e tempo total medido, reprova se
passar de 30 minutos (cláusula do portão). Os passos reusam as mesmas provas dos e2e de cada tela
(catálogo L0-03, upload L0-04-a, tarefas L0-05, mapa L2-01-a, construtor L5-01-a, auditoria L0-10):
o roteiro não cria caminho novo, ele anda no caminho que já tem prova. Medidas em
tests/medidas/L7-29-roteiro-demonstracao.json com a carga da máquina no fim da rodada.

Passo 5 (fila) precisa do worker da instalação rodando; sem worker a tarefa não sai de pendente e o
passo reprova com razão (o roteiro promete progresso ao vivo, que é trabalho do worker).
Passo 6 precisa do basemap PMTiles servido pelo nginx (L2-01-a); sem ele o mapa fica em branco e a
prova de cores distintas reprova."""

import os
import re
import tempfile
import time
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela, sufixo
from tests.e2e.test_layout_paginas import (
    _abrir_construtor,
    _abrir_executor,
    _criar_item,
    _montar_app_por_arrasto,
    _salvar,
)
from tests.e2e.test_mapa import _cores_distintas

ITEM = "L7-29-roteiro-demonstracao"
TEMPO_LIMITE_S = 30 * 60
CAPTURAS = Path(__file__).parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _csv_temporario(tamanho: int) -> Path:
    """CSV de carga para o passo 4: 34 MiB = 3 partes de 16 MiB (app/limites.UPLOAD_PARTE_BYTES)."""
    linha = b"talhao,area_ha,cultura\n1,12.50,soja\n"
    conteudo = (linha * (tamanho // len(linha) + 1))[:tamanho]
    f = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    f.write(conteudo)
    f.close()
    return Path(f.name)


def _ram_livre_gb() -> float:
    campos = {}
    for linha in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        chave, _, valor = linha.partition(":")
        campos[chave.strip()] = valor.split()[0]
    return int(campos["MemAvailable"]) / 1048576


def _limpar_aviso(page, seletor: str = "#aviso") -> None:
    """o aviso guarda o estado da ação anterior; limpar antes de esperar o 'ok' da próxima evita
    esperar um ok velho (mesma técnica de tests/e2e/test_conteudo.py)."""
    page.evaluate(f"() => document.querySelector('{seletor}')?.limpar()")


def test_roteiro_30_minutos(page, base_url, credenciais_demo, admin_api, api_auth, medida):
    slug, admin_login, senha_admin = credenciais_demo
    tela = Tela(page, base_url)
    s = sufixo()
    por_passo_ms: dict[str, float] = {}
    t0 = time.perf_counter()

    def capturar(nome: str) -> Path:
        # captura com o prefixo DESTE item: Tela.capturar usa o ITEM do módulo dela (apoio),
        # que não é o do roteiro.
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        tela.page.screenshot(path=str(caminho), full_page=True)
        return caminho

    # ---- passo 1: a porta de entrada (versão e saúde na primeira tela)
    t = time.perf_counter()
    tela.ir("/")
    assert re.fullmatch(r"\d+\.\d+\.\d+", page.text_content("#versao-numero").strip())
    assert page.text_content("#saude-estado").strip() == "ok"
    por_passo_ms["p01_inicio_ms"] = round((time.perf_counter() - t) * 1000, 1)
    capturar("p01_inicio")

    # ---- passo 2: acesso controlado (tela de entrada, depois credencial certa)
    t = time.perf_counter()
    page.goto(f"/entrar?inquilino={slug}&proximo=/conteudo", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    capturar("p02_entrada")
    page.fill("#login", admin_login)
    page.fill("#senha", senha_admin)
    page.click("#entrar")
    page.wait_for_url(lambda u: not u.rstrip("/").endswith("/entrar") and "/entrar?" not in u, timeout=20000)
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    por_passo_ms["p02_entrada_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 3: catálogo (pasta, item, título, tags, busca, favorito, lixeira)
    t = time.perf_counter()
    titulo = f"Demo mapa {s}"
    nome_pasta = f"Demo pasta {s}"
    item_id = pasta_id = None
    try:
        page.click("#pasta-nova")
        d = page.locator("plat-dialogo dialog[open]").last
        d.locator("input[name='nome']").fill(nome_pasta)
        d.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        arvore = tela.api("GET", "/api/pastas/arvore").json()
        planas = arvore if isinstance(arvore, list) else arvore.get("itens", [])
        pasta_id = next((p["id"] for p in planas if p["nome"] == nome_pasta), None)
        assert pasta_id, planas
        page.locator("#pastas .no").first.click()
        page.click("#novo-item")
        page.click("#novo-mapa")
        d = page.locator("#painel-novo dialog[open]").last
        d.locator("input[name='titulo']").fill(titulo)
        d.locator("button[type='submit']").click()
        page.wait_for_selector("#painel dialog[open] #item-titulo", timeout=15000)
        assert page.text_content("#painel dialog[open] #item-titulo").strip() == titulo
        item_id = page.text_content("#painel dialog[open] #item-uuid").strip()
        capturar("p03_item")
        # título em linha
        page.click("#painel dialog[open] button[data-campo='titulo']")
        d = page.locator("#painel-editar dialog[open]").last
        d.locator("input[name='titulo']").fill(f"{titulo} editado")
        d.locator("button[type='submit']").click()
        page.wait_for_function(
            "() => document.querySelector('#painel dialog[open] #item-titulo')?.textContent.trim()"
            f" === '{titulo} editado'", timeout=15000)
        # tags
        page.click("#painel dialog[open] button[data-campo='tags']")
        page.fill("#tags-entrada", "demo, roteiro")
        page.click("#tags-salvar")
        page.wait_for_function(
            "() => document.querySelectorAll('#painel dialog[open] [data-campo=tags] .chip').length >= 2",
            timeout=15000)
        # fechar o painel e buscar por campo
        page.locator("#painel dialog[open] .fechar-x").click()
        page.wait_for_url(lambda u: u.rstrip("/").endswith("/conteudo"), timeout=10000)
        page.fill("#busca input", f"titulo:{s}")
        page.press("#busca input", "Enter")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=15000)
        capturar("p03_busca")
        # favoritar e ver na aba
        page.locator(f"#lista tr[data-id='{item_id}'] button.favorito").click()
        page.wait_for_function(
            f"() => document.querySelector('#lista tr[data-id=\"{item_id}\"] button.favorito')"
            "?.getAttribute('aria-pressed') === 'true'", timeout=10000)
        page.click("#aba-favoritos")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=10000)
        page.click("#aba-meus")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=10000)
        # apagar → lixeira → restaurar com o mesmo identificador
        page.locator(f"#lista tr[data-id='{item_id}'] .titulo-item").click()
        page.wait_for_selector("#painel dialog[open] #item-mais", timeout=15000)
        page.click("#item-mais")
        page.click("#item-apagar")
        _limpar_aviso(page)
        page.locator("#painel-editar dialog[open] .dialogo-botoes button", has_text="Apagar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        tela.esperar_status(404)
        assert tela.api("GET", f"/api/itens/{item_id}").status == 404
        page.click("#aba-lixeira")
        page.wait_for_selector(f"#lixeira-tabela tbody tr:has-text({sufixo_citado(s)})", timeout=15000)
        capturar("p03_lixeira")
        _limpar_aviso(page)
        page.locator(f"#lixeira-tabela tbody tr:has-text({sufixo_citado(s)})").locator(
            "button", has_text="Restaurar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela.api("GET", f"/api/itens/{item_id}").status == 200
    finally:
        if item_id:
            admin_api.delete(f"/api/itens/{item_id}")
            admin_api.post("/api/lixeira/esvaziar", data={"ids": [item_id]})
        if pasta_id:
            admin_api.delete(f"/api/pastas/{pasta_id}")
    por_passo_ms["p03_catalogo_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 4: envio de arquivo em partes (34 MiB = 3 partes de 16 MiB)
    t = time.perf_counter()
    caminho_csv = _csv_temporario(34 * 1024 * 1024)
    try:
        tela.ir("/uploads")
        capturar("p04_uploads")
        page.set_input_files("#upload-arquivo", str(caminho_csv))
        page.click("#upload-enviar")
        page.wait_for_selector("#upload-rotulo-progresso:not([hidden])", timeout=15000)
        page.wait_for_function(
            "() => /parte \\d+ de 3/.test(document.querySelector('#upload-rotulo-progresso')?.textContent || '')"
            " || document.querySelector('#aviso')?.textContent?.includes('arquivo enviado')", timeout=30000)
        capturar("p04_progresso")
        page.wait_for_function(
            "() => document.querySelector('#aviso')?.textContent?.includes('arquivo enviado')", timeout=120000)
        assert page.get_attribute("#upload-progresso", "value") == "100"
        capturar("p04_concluido")
    finally:
        caminho_csv.unlink(missing_ok=True)
    por_passo_ms["p04_upload_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 5: fila de tarefas (progresso ao vivo, conclusão e cancelamento; precisa do worker)
    t = time.perf_counter()
    tela.ir("/tarefas")
    page.wait_for_selector("#lista-corpo", timeout=20000)

    def _criar_job(duracao_s: int, passos: int) -> dict:
        r = tela.api("POST", "/api/jobs", {"tipo": "prova.progresso",
                                           "parametros": {"duracao_s": duracao_s, "passos": passos}})
        assert r.status == 201, (r.status, r.text())
        return r.json()

    def _fila_vazia(timeout_ms: int = 60000) -> None:
        # espera o tique do resumo que viu zero ativos (o mesmo tique grava o contador interno da
        # página; é ele que autoriza a próxima tarefa a aparecer na lista por mudança de contagem)
        page.wait_for_function(
            "() => (document.querySelector('#resumo-texto')?.textContent || '')"
            ".startsWith('0 na fila · 0 rodando')", timeout=timeout_ms)

    # higiene: uma rodada anterior interrompida pode ter deixado uma prova de 300 s ocupando o
    # worker (1 processo); cancela as pendentes/rodando velhas e espera a fila ficar vazia.
    tela.esperar_status(409)  # cancelar em estado final (corrida entre listar e cancelar)
    for estado in ("rodando", "pendente"):
        velhos = tela.api("GET", f"/api/jobs?tipo=prova.progresso&estado={estado}&limite=50").json()
        for j in velhos.get("itens", []):
            tela.api("POST", f"/api/jobs/{j['id']}/cancelar", {})
    _fila_vazia()

    # 45 s e não menos: a lista relê a 1ª página só quando o resumo (a cada 10 s) vê o contador de
    # ativos mudar; um job curto demais nasce e conclui ENTRE dois tiques e a linha nunca aparece.
    job_curto = _criar_job(45, 9)
    page.wait_for_selector(f"#lista-corpo tr[data-id='{job_curto['id']}']", timeout=25000)
    page.wait_for_selector(
        f"#lista-corpo tr[data-id='{job_curto['id']}'][data-estado='rodando']", timeout=30000)
    capturar("p05_rodando")
    page.wait_for_selector(
        f"#lista-corpo tr[data-id='{job_curto['id']}'][data-estado='concluido']", timeout=120000)
    # espera a fila esvaziar antes da segunda tarefa: A terminou e B começa no mesmo segundo, o
    # contador fica 1→1 entre tiques, a lista não relê e a linha de B nunca é inserida (a assinatura
    # ao vivo só cobre linha que já está na lista).
    _fila_vazia()
    job_longo = _criar_job(300, 10)
    page.wait_for_selector(
        f"#lista-corpo tr[data-id='{job_longo['id']}'][data-estado='rodando']", timeout=30000)
    page.locator(f"#lista-corpo tr[data-id='{job_longo['id']}'] button.acao-cancelar").click()
    page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    page.wait_for_selector(
        f"#lista-corpo tr[data-id='{job_longo['id']}'][data-estado='cancelado']", timeout=30000)
    capturar("p05_cancelado")
    por_passo_ms["p05_tarefas_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 6: mapa com base local (controles, zoom e desenho de verdade)
    t = time.perf_counter()
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    page.wait_for_timeout(1500)  # primeiro quadro do WebGL
    assert page.locator(".maplibregl-ctrl-zoom-in").count() == 1
    assert page.locator(".maplibregl-ctrl-scale").count() == 1
    page.click(".maplibregl-ctrl-zoom-in")
    page.wait_for_timeout(800)
    captura_mapa = capturar("p06_mapa")
    assert _cores_distintas(captura_mapa) > 50, "o mapa não desenhou (captura sem cor)"
    por_passo_ms["p06_mapa_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 7: construtor de aplicação (2 páginas por arrasto, executor, janela modal)
    t = time.perf_counter()
    iid_app = _criar_item(admin_api, f"demo-app-{s}")
    try:
        _abrir_construtor(tela, page, iid_app)
        _montar_app_por_arrasto(page)
        _salvar(page)
        capturar("p07_construtor")
        _abrir_executor(tela, page, iid_app)
        page.wait_for_selector(".exec-pagina[data-pagina='central']", timeout=10000)
        page.click(".exec-menu a[data-ir-pagina='detalhes']")
        page.wait_for_selector(".exec-pagina[data-pagina='detalhes']", timeout=5000)
        capturar("p07_executor")
        jid = page.locator("dialog[data-janela]").first.get_attribute("data-janela")
        page.click(f"[data-janela-abrir='{jid}']")
        page.wait_for_selector(f"dialog[data-janela='{jid}'][open]", timeout=5000)
        page.keyboard.press("Escape")
        page.wait_for_function(
            "(id) => !document.querySelector(`dialog[data-janela=\"${id}\"]`).hasAttribute('open')",
            arg=jid, timeout=5000)
    finally:
        admin_api.delete(f"/api/itens/{iid_app}")
        admin_api.post("/api/lixeira/esvaziar", data={"ids": [iid_app]})
    por_passo_ms["p07_construtor_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 8: auditoria de acesso (filtro por status, CSV, eventos)
    t = time.perf_counter()
    tela.ir("/admin/log")
    page.wait_for_function(
        "() => document.querySelectorAll('#tabela tbody td:not(.vazio)').length >= 1", timeout=15000)
    page.locator("#filtros select[name='status']").select_option("2xx")
    page.click("#filtrar")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#tabela tbody .marcador')]"
        ".every(m => m.textContent[0] === '2')", timeout=15000)
    href = page.get_attribute("#exportar-csv", "href")
    assert href and "formato=csv" in href, href
    csv = tela.api("GET", href)
    assert csv.status == 200 and csv.headers.get("content-type", "").startswith("text/csv")
    capturar("p08_log")
    page.click("#aba-eventos")
    page.wait_for_function(
        "() => document.querySelectorAll('#tabela-eventos tbody td:not(.vazio)').length >= 1",
        timeout=15000)
    assert any("usuarios/entrar" in c for c in page.locator("#tabela-eventos tbody td").all_text_contents())
    por_passo_ms["p08_auditoria_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- passo 9: saúde da instalação pela interface de programação
    t = time.perf_counter()
    resposta = tela.api("GET", "/saude")
    assert resposta.status == 200, (resposta.status, resposta.text())
    assert resposta.json().get("banco") == "ok", resposta.text()
    tela.ir("/")
    assert page.text_content("#saude-estado").strip() == "ok"
    capturar("p09_saude")
    por_passo_ms["p09_saude_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # ---- cláusula do portão: tempo total ≤ 30 min medido
    total_s = round(time.perf_counter() - t0, 1)
    assert total_s <= TEMPO_LIMITE_S, f"roteiro passou de 30 minutos: {total_s} s"
    tela.verificar()

    gravar = medida(ITEM)
    gravar("roteiro_total_s", total_s, "s",
           "test_roteiro_30_minutos de ponta a ponta (chromium do playwright, instalação da trilha)")
    gravar("roteiro_passos", len(por_passo_ms), "passos",
           "docs/DEMO.md passos 1 a 9 percorridos na ordem")
    gravar("versao10_passos", "1,2,3,6,8,9", "lista",
           "docs/DEMO.md seção 'Versão de 10 minutos' (subconjunto dos mesmos passos do e2e)")
    capturas = sorted(Path(__file__).parent.glob(f"capturas/{ITEM}_p*.png"))
    gravar("capturas_por_passo", len(capturas), "arquivos",
           "tests/e2e/capturas/L7-29-roteiro-demonstracao_pNN_*.png")
    gravar("carga_1min", round(os.getloadavg()[0], 2), "carga",
           "os.getloadavg()[0] no fim da rodada (regra de medição do laço)")
    gravar("ram_livre_gb", round(_ram_livre_gb(), 1), "GB",
           "MemAvailable de /proc/meminfo no fim da rodada")
    for nome, ms in por_passo_ms.items():
        gravar(nome, ms, "ms", "duração do passo dentro de test_roteiro_30_minutos")


def sufixo_citado(s: str) -> str:
    """seletor :has-text() com o sufixo citado sem quebrar a aspas do locator."""
    return '"' + s + '"'
