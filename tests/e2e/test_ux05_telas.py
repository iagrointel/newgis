"""e2e do item UX-05-telas-conexoes-uploads-tarefas-compartilhado. Sobre os fluxos já provados em test_conexoes.py,
test_uploads.py e test_tarefas.py, este arquivo prova o que o item acrescenta:

1. /conexoes: criar, editar e apagar (com confirmação) pela tela; erro da API nomeado no campo (422 url_insegura no
   endereço, 409 no nome) e nunca um status cru; ordenação por coluna com aria-sort; busca com estado "nada
   corresponde"; estados vazio, carregando, erro (rota derrubada pela própria página) e negado; capturas 390/1280; axe;
2. /uploads: fila com vários arquivos, uma barra por arquivo e a barra do arquivo em curso com bytes e velocidade;
   cancelar antes de começar, remover, tentar de novo; erro da API (413) nomeado na linha; refutação do item — um
   arquivo de 256 MiB sintético (Blob em memória, partes interceptadas no navegador para não tocar o disco) com
   progresso pintado por quadro e NENHUMA tarefa longa do fio principal acima de 250 ms (PerformanceObserver
   longtask + maior intervalo entre quadros); o número vai para tests/medidas/UX-05.json com a carga da máquina;
3. /tarefas: estados vazio (com limpar filtros), erro e negado na lista; detalhe de id inexistente com estado nomeado;
   troca de idioma sem chave crua; axe; capturas;
4. /c/<token>: página pública SEM chrome interno (sem barra lateral e sem menu), ficha do item, itens incluídos com
   "ver" (GET /api/compartilhado/{token}/itens/{id}), estados link inválido (404), expirado (410, interceptado) e
   erro; axe; capturas."""

import datetime
import json
import os
import re
import time
import uuid

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, local, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-05"
LARGURAS = (390, 1280)
URL_404_ESTAVEL = "https://api.github.com/repos/inexistente-zt-e2e-ux05/tambem-inexistente"
TAREFA_LONGA_MAX_MS = 250
BYTES_SINTETICOS = 256 * 1024 * 1024  # 16 partes de 16 MiB
# só a LISTA (/api/jobs?...): resumo, tipos e o detalhe seguem para o servidor
ROTA_JOBS = re.compile(r".*/api/jobs\?.*")


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page, privilegios=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(privilegios))
    assert cruas == [], cruas


def _privilegios(tela):
    r = tela.api("GET", "/api/privilegios")
    return {p["nome"] for p in r.json()} if r.status == 200 else set()


def _erro_json(status, mensagem, req_id="e2e-ux05-ref"):
    return {
        "status": status,
        "content_type": "application/json",
        "body": json.dumps({"erro": "provocado", "mensagem": mensagem, "req_id": req_id}),
        "headers": {"X-Req-Id": req_id},
    }


# ---------------------------------------------------------------- 1. conexões


def test_conexoes_criar_editar_ordenar_apagar_e_estados(page, base_url, credenciais_demo, api_auth):
    if "/api/conexoes" not in api_auth:
        pytest.skip("backend sem /api/conexoes no OpenAPI")
    slug, login, senha = credenciais_demo
    s = sufixo()
    nome = f"zt-ux05-conexao-{s}"
    tela = Tela(page, base_url)
    criadas = []
    try:
        tela.entrar(slug, login, senha, proximo="/conexoes")
        tela.ir("/conexoes")
        privilegios = _privilegios(tela)
        _axe(page, "lista")
        _sem_chave_crua(page, privilegios)
        _capturar(page, "conexoes_lista")

        # estado vazio (se a lista está vazia) traz a ação de criar; senão a tabela está visível
        vazio = page.locator("#lista-estado[tipo='vazio']")
        if vazio.count() and vazio.is_visible():
            assert page.locator("#lista-caixa").is_hidden()
            assert vazio.locator("button", has_text="nova conexão").count() == 1
        else:
            assert page.locator("#lista-caixa").is_visible()

        # criar: obrigatórios no cliente, 422 url_insegura nomeado no campo, 201 com a linha na tabela
        page.click("#conexao-nova")
        page.wait_for_selector("#conexao-form-caixa:not([hidden])")
        _axe(page, "formulário")
        _capturar(page, "conexoes_form")
        page.click("#conexao-form button[type=submit]")
        assert page.locator("#conexao-form [data-campo='nome'] .erro-campo").count() == 1
        page.fill("#conexao-form input[name=nome]", nome)
        page.select_option("#conexao-form select[name=tipo]", "http")
        page.fill("#conexao-form input[name=url]", "http://127.0.0.1:1/interno")
        tela.esperar_status(422)
        page.click("#conexao-form button[type=submit]")
        page.wait_for_selector("#conexao-form [data-campo='url'] .erro-campo")
        texto_erro = page.text_content("#conexao-form [data-campo='url'] .erro-campo") or ""
        assert "422" not in texto_erro and len(texto_erro) > 10, texto_erro
        assert page.evaluate("() => document.activeElement.name") == "url"
        _capturar(page, "conexoes_form_erro", larguras=(1280,))
        page.fill("#conexao-form input[name=url]", URL_404_ESTAVEL)
        page.click("#conexao-form button[type=submit]")
        page.wait_for_selector("#conexao-form-caixa[hidden]", state="attached")
        linha = page.locator("#lista-corpo tr", has_text=nome)
        linha.wait_for(timeout=10000)
        cid = linha.get_attribute("data-id")
        criadas.append(cid)
        assert linha.locator(".marcador").inner_text().strip() == "nunca testada"
        assert "criada" in (page.text_content("#lista-aviso") or "")

        # nome repetido: 409 nomeado no campo nome
        page.click("#conexao-nova")
        page.fill("#conexao-form input[name=nome]", nome)
        page.select_option("#conexao-form select[name=tipo]", "http")
        page.fill("#conexao-form input[name=url]", URL_404_ESTAVEL)
        tela.esperar_status(409)
        page.click("#conexao-form button[type=submit]")
        page.wait_for_selector("#conexao-form [data-campo='nome'] .erro-campo")
        assert "409" not in (page.text_content("#conexao-form [data-campo='nome'] .erro-campo") or "")
        page.click("#conexao-form .botoes button:not([type=submit])")
        page.wait_for_selector("#conexao-form-caixa[hidden]", state="attached")

        # editar: tipo travado, nome muda, PATCH volta na linha
        linha.locator("button.acao-editar").click()
        page.wait_for_selector("#conexao-form-caixa:not([hidden])")
        assert "editar conexão" in (page.text_content("#conexao-form-titulo") or "")
        assert page.locator("#conexao-form select[name=tipo]").is_disabled()
        assert page.input_value("#conexao-form input[name=url]") == URL_404_ESTAVEL
        page.fill("#conexao-form input[name=nome]", f"{nome}-ed")
        page.click("#conexao-form button[type=submit]")
        page.wait_for_selector("#conexao-form-caixa[hidden]", state="attached")
        page.locator("#lista-corpo tr", has_text=f"{nome}-ed").wait_for(timeout=10000)

        # ordenação por coluna: aria-sort alterna e a ordem dos valores segue
        page.click("#lista th[data-campo='tipo']")
        assert page.get_attribute("#lista th[data-campo='tipo']", "aria-sort") == "ascending"
        tipos = page.eval_on_selector_all(
            "#lista-corpo tr td:nth-child(2)", "els => els.map(e => e.textContent.trim().toLowerCase())"
        )
        assert tipos == sorted(tipos), tipos
        page.keyboard.press("Enter")  # o th ainda tem o foco: teclado também ordena
        assert page.get_attribute("#lista th[data-campo='tipo']", "aria-sort") == "descending"
        tipos = page.eval_on_selector_all(
            "#lista-corpo tr td:nth-child(2)", "els => els.map(e => e.textContent.trim().toLowerCase())"
        )
        assert tipos == sorted(tipos, reverse=True), tipos

        # busca: nada corresponde -> estado com ação de limpar
        page.fill("#lista-busca input", "zt-nada-corresponde-xyz")
        page.press("#lista-busca input", "Enter")
        page.wait_for_selector("#lista-estado[tipo='vazio']:not([hidden])")
        assert "nada contém" in (page.text_content("#lista-estado") or "")
        page.locator("#lista-estado button", has_text="limpar busca").click()
        page.wait_for_selector("#lista-caixa:not([hidden])")
        assert page.input_value("#lista-busca input") == ""

        # erro e negado: a própria página derruba a rota
        tela.esperar_status(500, 403)
        page.route(
            "**/api/conexoes",
            lambda r: (
                r.fulfill(**_erro_json(500, "banco indisponível (provocado)"))
                if r.request.method == "GET"
                else r.continue_()
            ),
        )
        page.click("#lista-recarregar")
        page.wait_for_selector("#lista-estado[tipo='erro']:not([hidden])")
        assert page.locator("#lista-estado").get_attribute("role") == "alert"
        assert "e2e-ux05-ref" in (page.text_content("#lista-estado") or "")
        _capturar(page, "conexoes_erro", larguras=(1280,))
        page.unroute("**/api/conexoes")
        page.route(
            "**/api/conexoes",
            lambda r: (
                r.fulfill(**_erro_json(403, "sem privilégio (provocado)"))
                if r.request.method == "GET"
                else r.continue_()
            ),
        )
        page.locator("#lista-estado button", has_text="tentar de novo").click()
        page.wait_for_selector("#lista-estado[tipo='negado']:not([hidden])")
        _capturar(page, "conexoes_negado", larguras=(1280,))
        page.unroute("**/api/conexoes")
        page.click("#lista-recarregar")
        page.wait_for_selector("#lista-caixa:not([hidden])")

        # apagar com confirmação
        linha = page.locator("#lista-corpo tr", has_text=f"{nome}-ed")
        linha.locator("button.acao-apagar").click()
        dialogo = page.locator("plat-dialogo dialog[open]")
        dialogo.wait_for()
        assert f"{nome}-ed" in dialogo.inner_text()
        _capturar(page, "conexoes_apagar_confirma", larguras=(1280,))
        dialogo.locator(".dialogo-botoes button.perigo").click()
        page.wait_for_function(
            "(n) => !document.querySelector('#lista-corpo')?.textContent.includes(n)", arg=f"{nome}-ed", timeout=10000
        )
        criadas.clear()
        assert "apagada" in (page.text_content("#lista-aviso") or "")
        _axe(page, "lista depois")
        tela.verificar()
    finally:
        for cid in criadas:
            tela.api("DELETE", f"/api/conexoes/{cid}")


# ---------------------------------------------------------------- 2. uploads


def _csv_temporario(tmp_path, nome, linhas=40):
    p = tmp_path / nome
    p.write_bytes(b"talhao,area_ha,cultura\n" + b"".join(f"{i},12.5,soja\n".encode() for i in range(linhas)))
    return p


def _gravar_medida(nome, valor, unidade, comando, extra=None):
    caminho = RAIZ / "tests" / "medidas" / f"{ITEM}.json"
    dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {"item": ITEM, "medidas": {}}
    dados["gerado_em"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    m = {
        "valor": valor,
        "unidade": unidade,
        "carga_1min": round(os.getloadavg()[0], 2),
        "medido_em": dados["gerado_em"],
        "comando": comando,
    }
    if extra:
        m.update(extra)
    dados["medidas"][nome] = m
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def test_uploads_fila_estados_e_fio_principal_livre(page, base_url, credenciais_demo, api_auth, tmp_path):
    if "/api/uploads" not in api_auth:
        pytest.skip("backend sem /api/uploads no OpenAPI")
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    itens_criados = []
    try:
        tela.entrar(slug, login, senha, proximo="/uploads")
        tela.ir("/uploads")
        _axe(page, "uploads vazio")
        _sem_chave_crua(page)
        _capturar(page, "uploads_vazio")

        # fila com dois arquivos reais pequenos: ambos concluem, cada um com a própria barra e o link do item
        a = _csv_temporario(tmp_path, f"zt-ux05-a-{s}.csv")
        b = _csv_temporario(tmp_path, f"zt-ux05-b-{s}.csv", linhas=80)
        page.set_input_files("#upload-arquivo", [str(a), str(b)])
        assert page.locator("#upload-fila li").count() == 2
        assert "2 arquivos" in (page.text_content("#upload-nome") or "")
        _axe(page, "fila")
        _capturar(page, "uploads_fila")
        page.click("#upload-enviar")
        page.wait_for_function(
            "() => document.querySelectorAll('#upload-fila li[data-estado=concluido]').length === 2", timeout=60000
        )
        assert "2 arquivos enviados" in (page.text_content("#aviso") or "")
        assert page.locator("#upload-resultado a").count() == 2
        assert page.get_attribute("#upload-progresso", "value") == "100"
        for href in page.eval_on_selector_all("#upload-resultado a", "els => els.map(e => e.getAttribute('href'))"):
            itens_criados.append(href.rsplit("/", 1)[-1])
        _capturar(page, "uploads_concluido")
        page.click("#upload-limpar")
        assert page.locator("#upload-fila li").count() == 0

        # cancelar antes de começar, tentar de novo fica disponível, remover tira da fila
        c = _csv_temporario(tmp_path, f"zt-ux05-c-{s}.csv")
        page.set_input_files("#upload-arquivo", str(c))
        page.locator("#upload-fila li button.acao-cancelar").click()
        assert page.get_attribute("#upload-fila li", "data-estado") == "cancelado"
        assert page.locator("#upload-fila li button.acao-repetir").is_visible()
        page.locator("#upload-fila li button.acao-remover").click()
        assert page.locator("#upload-fila li").count() == 0

        # erro da API nomeado na linha: POST /api/uploads devolve 413 (provocado)
        tela.esperar_status(413)
        page.route(
            "**/api/uploads",
            lambda r: (
                r.fulfill(**_erro_json(413, "cota de armazenamento do inquilino excedida (provocado)"))
                if r.request.method == "POST"
                else r.continue_()
            ),
        )
        page.set_input_files("#upload-arquivo", str(c))
        page.click("#upload-enviar")
        page.wait_for_selector("#upload-fila li[data-estado=falhou]")
        assert "cota de armazenamento" in (page.text_content("#upload-fila li .estado-arquivo") or "")
        assert page.locator("#upload-fila li button.acao-repetir").is_visible()
        _capturar(page, "uploads_erro", larguras=(1280,))
        page.unroute("**/api/uploads")
        page.locator("#upload-fila li button.acao-remover").click()

        # refutação: 256 MiB sintéticos em memória, partes e conclusão interceptadas no navegador (nada vai ao disco
        # do servidor); o que se mede é o fio principal enquanto a tela pinta o progresso
        page.route(
            "**/api/uploads/*/partes/*", lambda r: r.fulfill(status=200, content_type="application/json", body="{}")
        )
        page.route(
            "**/api/uploads/*/concluir",
            lambda r: r.fulfill(
                status=202, content_type="application/json", body=json.dumps({"arquivo_id": str(uuid.uuid4())})
            ),
        )
        page.route(
            "**/api/uploads/*",
            lambda r: r.fulfill(status=204, body="") if r.request.method == "DELETE" else r.continue_(),
        )
        page.evaluate(
            """(bytes) => {
              const parte = 16 * 1024 * 1024;
              const bloco = new Uint8Array(parte);
              for (let i = 0; i < parte; i += 4096) bloco[i] = 65;
              const partes = [];
              for (let i = 0; i < bytes / parte; i += 1) partes.push(bloco);
              const f = new File(partes, 'zt-ux05-grande.csv', { type: 'text/csv' });
              const dt = new DataTransfer();
              dt.items.add(f);
              const entrada = document.getElementById('upload-arquivo');
              entrada.files = dt.files;
              entrada.dispatchEvent(new Event('change', { bubbles: true }));
              const m = { longas: [], maiorIntervalo: 0, textos: new Set(), ultimo: performance.now() };
              window.__medida = m;
              new PerformanceObserver((l) => {
                for (const e of l.getEntries()) m.longas.push(Math.round(e.duration));
              }).observe({ entryTypes: ['longtask'] });
              const tick = () => {
                const agora = performance.now();
                m.maiorIntervalo = Math.max(m.maiorIntervalo, agora - m.ultimo);
                m.ultimo = agora;
                if (!m.parar) requestAnimationFrame(tick);
              };
              requestAnimationFrame(tick);
              const rotulo = document.getElementById('upload-rotulo-progresso');
              new MutationObserver(() => m.textos.add(rotulo.textContent))
                .observe(rotulo, { childList: true, characterData: true, subtree: true });
            }""",
            BYTES_SINTETICOS,
        )
        assert "256" in (page.text_content("#upload-nome") or "")
        t0 = time.perf_counter()
        page.click("#upload-enviar")
        page.wait_for_selector("#upload-fila li[data-estado=concluido]", timeout=120000)
        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        medida = page.evaluate(
            "() => { const m = window.__medida; m.parar = true; "
            "return { longas: m.longas, maiorIntervalo: Math.round(m.maiorIntervalo), textos: [...m.textos] }; }"
        )
        fila = page.evaluate("() => window.plat.uploads.fila()")
        assert fila[-1]["estado"] == "concluido" and fila[-1]["partes"] == 16, fila
        maior_longa = max(medida["longas"], default=0)
        assert maior_longa <= TAREFA_LONGA_MAX_MS, medida["longas"]
        # o rótulo mudou ao longo do envio (uma pintura por quadro, nunca uma só ao fim) e traz bytes e velocidade
        assert len(medida["textos"]) >= 4, medida["textos"]
        assert any("MB" in t and "/s" in t for t in medida["textos"]), medida["textos"]
        _gravar_medida(
            "upload_256mib_maior_tarefa_longa_ms",
            maior_longa,
            "ms",
            "playwright chromium 1280x800: File de 256 MiB em memória (16 partes de 16 MiB), PUT/concluir "
            "interceptados no navegador; PerformanceObserver longtask + maior intervalo entre requestAnimationFrame "
            "durante o envio (tests/e2e/test_ux05_telas.py)",
            {
                "tarefas_longas_ms": medida["longas"],
                "maior_intervalo_entre_quadros_ms": medida["maiorIntervalo"],
                "pinturas_do_rotulo": len(medida["textos"]),
                "envio_total_ms": total_ms,
            },
        )
        page.unroute("**/api/uploads/*/partes/*")
        page.unroute("**/api/uploads/*/concluir")
        page.unroute("**/api/uploads/*")
        _capturar(page, "uploads_grande", larguras=(1280,))
        tela.verificar()
    finally:
        if itens_criados:
            for iid in itens_criados:
                tela.api("DELETE", f"/api/itens/{iid}")
            tela.api("POST", "/api/lixeira/esvaziar", {"ids": itens_criados})


# ---------------------------------------------------------------- 3. tarefas


def test_tarefas_estados_detalhe_inexistente_e_idioma(page, base_url, credenciais_demo, api_auth):
    if "/api/jobs" not in api_auth:
        pytest.skip("backend sem /api/jobs no OpenAPI")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/tarefas")
    tela.ir("/tarefas")
    page.wait_for_function("() => /\\d/.test(document.querySelector('#lista-total').textContent)", timeout=15000)
    # os nomes dos tipos de job (catalogo.miniatura, ...) têm a forma de chave de i18n e aparecem no filtro de tipo
    privilegios = _privilegios(tela) | {tp["nome"] for tp in tela.api("GET", "/api/jobs/tipos").json()}
    _axe(page, "tarefas")
    _sem_chave_crua(page, privilegios)
    _capturar(page, "tarefas_lista")

    # vazio (rota devolve zero), erro (500) e negado (403): a própria página derruba a rota de lista
    tela.esperar_status(500, 403)
    page.route(
        ROTA_JOBS,
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"itens": [], "total": 0})),
    )
    page.select_option("#f-estado", "cancelado")
    page.wait_for_selector("#lista-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#lista-estado button", has_text="limpar filtros").count() == 1
    assert page.locator("#lista-caixa").is_visible() and page.locator("#lista-corpo tr").count() == 0
    _capturar(page, "tarefas_vazio", larguras=(1280,))
    page.unroute(ROTA_JOBS)
    page.route(ROTA_JOBS, lambda r: r.fulfill(**_erro_json(500, "fila indisponível (provocado)")))
    page.locator("#lista-estado button", has_text="limpar filtros").click()
    page.wait_for_selector("#lista-estado[tipo='erro']:not([hidden])")
    assert "e2e-ux05-ref" in (page.text_content("#lista-estado") or "")
    assert page.locator("#lista-caixa").is_hidden()
    page.unroute(ROTA_JOBS)
    page.route(ROTA_JOBS, lambda r: r.fulfill(**_erro_json(403, "sem jobs.ver (provocado)")))
    page.locator("#lista-estado button", has_text="tentar de novo").click()
    page.wait_for_selector("#lista-estado[tipo='negado']:not([hidden])")
    _capturar(page, "tarefas_negado", larguras=(1280,))
    page.unroute(ROTA_JOBS)
    page.click("#f-limpar")
    page.wait_for_selector("#lista-caixa:not([hidden])")

    # detalhe de id inexistente: estado nomeado dentro do painel, com "fechar"
    tela.esperar_status(404)
    inexistente = "00000000-0000-4000-8000-000000000000"
    tela.ir(f"/tarefas/{inexistente}")
    page.wait_for_selector("#detalhe-estado-area[tipo='vazio']:not([hidden])", timeout=15000)
    assert "não encontrada" in (page.text_content("#detalhe-estado-area") or "")
    _axe(page, "detalhe inexistente")
    _capturar(page, "tarefas_detalhe_inexistente", larguras=(1280,))
    page.locator("#detalhe-estado-area button", has_text="fechar").click()
    page.wait_for_selector("#detalhe[hidden]", state="attached")

    # idioma: en sem chave crua e com os cabeçalhos traduzidos
    tela.ir("/tarefas?idioma=en")
    page.wait_for_function("() => document.querySelector('h1')?.textContent.trim() === 'Tasks'", timeout=15000)
    assert page.text_content("#lista th[data-campo='criado_em']").strip() == "created"
    _sem_chave_crua(page, privilegios)
    _capturar(page, "tarefas_en", larguras=(1280,))
    tela.ir("/tarefas?idioma=pt-BR")
    page.wait_for_function("() => document.querySelector('h1')?.textContent.trim() === 'Tarefas'", timeout=15000)
    tela.verificar()


# ---------------------------------------------------------------- 4. página pública


def test_compartilhado_publico_sem_chrome_e_estados(page, base_url, credenciais_demo, api_auth, browser):
    if "/api/compartilhado/{token}" not in api_auth:
        pytest.skip("backend sem /api/compartilhado no OpenAPI")
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    ids = []
    try:
        tela.entrar(slug, login, senha, proximo="/conteudo")
        # o item principal é um app cujo corpo lista o mapa incluído: a relação mapa_de_app nasce do extrator do
        # documento (PUT /relacoes direto é recusado em tipos com extrator), e só dependência entra no link
        dados_mapa = {"esquema_versao": 1, "corpo": {}}
        r = tela.api("POST", "/api/itens", {"tipo": "mapa", "titulo": f"zt-ux05 incluído {s}", "dados": dados_mapa})
        assert r.status == 201, r.text()
        incluido = r.json()["id"]
        ids.append(incluido)
        r = tela.api(
            "POST",
            "/api/itens",
            {
                "tipo": "app",
                "titulo": f"zt-ux05 mapa {s}",
                "resumo": "aplicativo de prova do link público",
                "tags": ["ux05"],
                "dados": {"tipo": "app", "esquema_versao": 1, "corpo": {"mapas": [incluido]}},
            },
        )
        assert r.status == 201, r.text()
        principal = r.json()["id"]
        ids.append(principal)
        r = tela.api("POST", f"/api/itens/{principal}/links", {"nome": f"zt-ux05-{s}", "itens_incluidos": [incluido]})
        assert r.status == 201, r.text()
        token = r.json()["token"]

        # contexto novo, sem cookie: a página é pública
        ctx = browser.new_context(ignore_https_errors=local(base_url), base_url=base_url, locale="pt-BR")
        pub = ctx.new_page()
        publica = Tela(pub, base_url)
        try:
            publica.ir(f"/c/{token}")
            assert pub.locator("#lateral, aside.lateral, nav.lateral").count() == 0
            assert pub.locator(".publica-topo").count() == 1
            assert pub.locator("#item h2").inner_text().strip() == f"zt-ux05 mapa {s}"
            assert pub.locator("#incluidos-tabela tbody tr").count() == 1
            _axe(pub, "pública")
            _sem_chave_crua(pub)
            _capturar(pub, "compartilhado")
            # item incluído: GET /api/compartilhado/{token}/itens/{id} pela ação "ver"
            pub.locator("#incluidos-tabela button.acao-ver").click()
            pub.wait_for_selector("#incluido:not([hidden]) .ficha-item h2")
            assert pub.locator("#incluido .ficha-item h2").inner_text().strip() == f"zt-ux05 incluído {s}"
            _axe(pub, "incluído")
            _capturar(pub, "compartilhado_incluido", larguras=(1280,))
            pub.locator("#incluido button.fechar-incluido").click()
            assert pub.locator("#incluido").is_hidden()
            # estados: link inválido (404 real), expirado (410 interceptado) e erro (500 interceptado)
            publica.esperar_status(404, 410, 500)
            publica.ir("/c/zt-token-inexistente")
            pub.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
            assert "link inválido" in (pub.text_content("#estado") or "")
            assert pub.locator("#item").is_hidden()
            _capturar(pub, "compartilhado_invalido", larguras=(1280,))
            pub.route("**/api/compartilhado/*", lambda r: r.fulfill(**_erro_json(410, "este link expirou (provocado)")))
            publica.ir(f"/c/{token}")
            pub.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
            assert "expirou" in (pub.text_content("#estado") or "")
            pub.unroute("**/api/compartilhado/*")
            pub.route(
                "**/api/compartilhado/*", lambda r: r.fulfill(**_erro_json(500, "banco indisponível (provocado)"))
            )
            publica.ir(f"/c/{token}")
            pub.wait_for_selector("#estado[tipo='erro']:not([hidden])")
            assert "e2e-ux05-ref" in (pub.text_content("#estado") or "")
            pub.unroute("**/api/compartilhado/*")
            pub.locator("#estado button", has_text="tentar de novo").click()
            pub.wait_for_selector("#item:not([hidden]) h2")
            publica.verificar()
        finally:
            ctx.close()
        tela.verificar()
    finally:
        for iid in ids:
            tela.api("DELETE", f"/api/itens/{iid}")
        if ids:
            tela.api("POST", "/api/lixeira/esvaziar", {"ids": ids})
