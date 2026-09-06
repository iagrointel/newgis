"""e2e playwright da tela Tarefas (item L0-05-jobs, ADR 0003 seções 10 e 12) contra a URL interna.

Prova: (1) job disparado pela API aparece na lista SEM recarregar, o progresso sobe (dois valores distintos), termina
concluído e o detalhe mostra resultado e log; (2) cancelar pela tela → cancelado; (3) filtro por estado bate com a
API; (4) 1.000 jobs semeados pela função de demonstração plat.jobs_semear_demo (migração 014; INSERT direto
de job já concluído é barrado pela 006 e continua barrado) → primeira pintura ≤ 1 s; (5) agendas:
criar (cron inválida recusada campo a campo), pausar, retomar, apagar. Capturas em tests/e2e/capturas/L0-05-jobs_*.png;
0 erro de console; nenhuma resposta ≥ 400 além das que o teste provoca. Medidas pela fixture `medida`
(gravadas só com PLAT_GRAVAR_MEDIDAS=1). Sem /api/jobs no OpenAPI a suíte é pulada com a razão escrita."""

import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import pytest

CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L0-05-jobs"
COOKIE = "plat_sessao"
# respostas ≥ 400 que a própria tela ou o teste provocam de propósito
TOLERADAS = (
    (r"/api/eu$", 404),                  # trilha de identidade ainda não publicada: a tela segue só com jobs
    (r"/static/js/i18n/[^/]+\.json$", 404),  # dicionário i18n ainda não publicado (t() devolve a chave)
    (r"/api/agendas$", 422),             # cron inválida enviada de propósito
    (r"/api/agendas$", 409),             # nome repetido de uma execução anterior interrompida
)

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def api_jobs_disponivel(base_url, url_publica_resolve, playwright):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    req = playwright.request.new_context(base_url=base_url)
    try:
        r = req.get("/api/openapi.json")
        caminhos = r.json().get("paths", {}) if r.ok else {}
    finally:
        req.dispose()
    if "/api/jobs" not in caminhos:
        pytest.skip("o backend ainda não publicou /api/jobs no OpenAPI; testes prontos, esperando a trilha do backend")
    return True


def _sessao_propria(dsn: str, slug: str = "demo", login: str = "admin", dias: int = 1):
    """Sessão pelas funções SECURITY DEFINER (002/003; sem senha, sem conectar como postgres). A 003 exige o
    contexto do inquilino do usuário antes de auth_sessao_criar (contexto_confere) e recebe a validade em dias."""
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, %s)", (slug, login))
            r = cur.fetchone()
            assert r, f"usuário {login} de {slug} não semeado (rode install.sh)"
            cur.execute("SET search_path = plat, public")
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', %s, true)",
                (str(r["tenant_id"]), str(r["usuario_id"]), login),
            )
            cur.execute("SELECT plat.auth_sessao_criar(%s, %s, %s, %s) AS token",
                        (r["usuario_id"], dias, "127.0.0.1", "e2e tarefas"))
            token = cur.fetchone()["token"]
        con.commit()
        return token, r["tenant_id"], r["usuario_id"]
    finally:
        con.close()


@pytest.fixture(scope="session")
def sessao(env, api_jobs_disponivel):
    """(token, tenant_id, usuario_id) do admin de demo; usa tests/jobs_sessao.py do backend quando existir."""
    try:
        from tests.jobs_sessao import criar_sessao  # entregue pelo backend (handoff 30, passo 23)

        con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            r = criar_sessao(con)
            con.commit()
            return r
        finally:
            con.close()
    except ImportError:
        return _sessao_propria(env["PLAT_DSN"])


@pytest.fixture
def pagina(page, base_url, sessao):
    """página com o cookie de sessão, coleta de erros de console e de respostas ≥ 400."""
    token = sessao[0]
    u = urlparse(base_url)
    page.context.add_cookies([{
        "name": COOKIE, "value": token, "domain": u.hostname, "path": "/", "httpOnly": True,
        "secure": u.scheme == "https", "sameSite": "Lax",
    }])
    erros = []
    respostas = []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    page.on("response", lambda r: respostas.append((r.url, r.status)))
    page.erros = erros
    page.respostas = respostas
    return page


def conferir_limpo(page):
    """0 erro de console e 0 resposta ≥ 400 fora das toleradas. O Chromium grava um console.error genérico
    ("Failed to load resource: ... status of N") para toda resposta não-2xx: esse texto só é aceito quando uma
    resposta tolerada com o mesmo status foi registrada; qualquer outro erro de console reprova."""
    tolerada = lambda u, s: any(re.search(p, u) and s == st for p, st in TOLERADAS)  # noqa: E731
    status_tolerados = {s for u, s in page.respostas if s >= 400 and tolerada(u, s)}
    erros = [e for e in page.erros
             if not (re.search(r"Failed to load resource: .*status of (\d{3})", e)
                     and int(re.search(r"status of (\d{3})", e).group(1)) in status_tolerados)]
    assert erros == [], erros
    ruins = [(u, s) for u, s in page.respostas if s >= 400 and not tolerada(u, s)]
    assert ruins == [], ruins


def abrir_tarefas(page, caminho="/tarefas"):
    t0 = time.perf_counter()
    page.goto(caminho, wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    return round((time.perf_counter() - t0) * 1000, 1)


def criar_job(page, base_url, duracao_s, passos):
    corpo = {"tipo": "prova.progresso", "parametros": {"duracao_s": duracao_s, "passos": passos}}
    r = page.request.post(f"{base_url}/api/jobs", data=corpo)
    assert r.status == 201, f"POST /api/jobs → {r.status}: {r.text()}"
    return r.json()


def linha(page, job_id):
    return page.locator(f"#lista-corpo tr[data-id='{job_id}']")


def esperar_estado(page, job_id, estado, timeout_ms):
    page.wait_for_selector(f"#lista-corpo tr[data-id='{job_id}'][data-estado='{estado}']", timeout=timeout_ms)


def confirmar_dialogo(page):
    page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()


# ---------------------------------------------------------------- testes

def test_lista_progresso_ao_vivo_e_detalhe(pagina, base_url, medida):
    page = pagina
    pronto_ms = abrir_tarefas(page)
    assert page.text_content("h1").strip() == "Tarefas"
    assert page.locator("#lateral nav a[href='/tarefas']").count() == 1, "item Tarefas ausente na barra lateral"
    assert page.locator("#lista-corpo tr").count() >= 1

    # job disparado pela API: a linha tem de aparecer sem recarregar (resumo a cada 10 s relê a 1ª página)
    job = criar_job(page, base_url, duracao_s=60, passos=30)
    t_cria = time.perf_counter()
    page.wait_for_selector(f"#lista-corpo tr[data-id='{job['id']}']", timeout=25000)
    aparece_s = round(time.perf_counter() - t_cria, 1)

    # progresso: dois valores distintos observados na própria linha (SSE ou reserva por polling)
    vistos = []
    limite = time.time() + 480  # a fila pode estar ocupada por um job de 5 min de outro teste
    while time.time() < limite:
        tr = linha(page, job["id"])
        estado = tr.get_attribute("data-estado")
        if estado == "rodando":
            v = tr.locator(".c-progresso .valor").text_content()
            if v and (not vistos or vistos[-1] != v):
                vistos.append(v)
        if len(set(vistos)) >= 2 or estado in ("concluido", "falhou", "cancelado"):
            break
        time.sleep(0.5)
    estado_final = linha(page, job["id"]).get_attribute("data-estado")
    assert len(set(vistos)) >= 2, f"progresso não subiu na tela: {vistos} (estado {estado_final})"
    assert re.fullmatch(r"\d{1,3} %", vistos[-1]), vistos
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_lista.png"), full_page=True)

    esperar_estado(page, job["id"], "concluido", 150000)
    fim_api = page.request.get(f"{base_url}/api/jobs/{job['id']}").json()
    assert fim_api["estado"] == "concluido"

    # detalhe: clique na linha abre /tarefas/<id> com resultado e log
    linha(page, job["id"]).click()
    page.wait_for_selector("#detalhe[data-carregado='1']", timeout=15000)
    assert page.evaluate("location.pathname") == f"/tarefas/{job['id']}"
    assert "concluído" in page.text_content("#detalhe-estado")
    assert "passos" in page.text_content("#detalhe-resultado")
    page.select_option("#log-nivel", "DEBUG")
    assert page.locator("#log-linhas li").count() >= 1, "detalhe sem linha de log"
    log_api = page.request.get(f"{base_url}/api/jobs/{job['id']}/log?limite=500").json()["linhas"]
    assert page.locator("#log-linhas li").count() == len(log_api)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_detalhe.png"), full_page=True)

    # abrir por URL direta também funciona
    abrir_tarefas(page, f"/tarefas/{job['id']}")
    page.wait_for_selector("#detalhe[data-carregado='1']", timeout=15000)
    assert page.text_content("#detalhe-tipo").strip() == "prova.progresso"

    conferir_limpo(page)
    gravar = medida(ITEM)
    gravar("pagina_tarefas_pronta_ms", pronto_ms, "ms", "goto('/tarefas') até body[data-pronto=1] (chromium)")
    gravar("linha_nova_aparece_s", aparece_s, "s", "POST /api/jobs pela API até tr[data-id] na tela sem recarregar")
    gravar("progresso_valores_distintos", len(set(vistos)), "valores",
           "leituras distintas de .c-progresso .valor na linha durante o job de 60 s")


def test_cancelar_pela_tela(pagina, base_url, medida):
    page = pagina
    abrir_tarefas(page)
    job = criar_job(page, base_url, duracao_s=120, passos=60)
    page.wait_for_selector(f"#lista-corpo tr[data-id='{job['id']}']", timeout=25000)
    tr = linha(page, job["id"])
    tr.locator("button.acao-cancelar").click()
    t0 = time.perf_counter()
    confirmar_dialogo(page)
    # o botão fica desabilitado até o evento `estado` chegar; a linha termina em `cancelado`
    page.wait_for_selector(f"#lista-corpo tr[data-id='{job['id']}'] button.acao-cancelar[disabled]", timeout=5000)
    esperar_estado(page, job["id"], "cancelado", 60000)
    cancel_s = round(time.perf_counter() - t0, 2)
    assert page.request.get(f"{base_url}/api/jobs/{job['id']}").json()["estado"] == "cancelado"
    assert "cancelado" in tr.locator(".c-estado").text_content()
    conferir_limpo(page)
    medida(ITEM)("cancelamento_tela_s", cancel_s, "s",
                 "clique em cancelar + confirmação até tr[data-estado=cancelado] (job pendente ou rodando)")


def test_filtro_por_estado_bate_com_api(pagina, base_url):
    page = pagina
    abrir_tarefas(page)
    # mesmos parâmetros que a tela manda: período "tudo" e, para admin, "todos do inquilino"
    page.select_option("#f-periodo", "tudo")
    if page.locator("#f-quem").is_visible():
        page.select_option("#f-quem", "todos")
    page.select_option("#f-estado", "concluido")
    page.wait_for_function(
        "() => document.querySelectorAll('#lista-corpo tr[data-estado]:not([data-estado=concluido])').length === 0")
    api = page.request.get(f"{base_url}/api/jobs?estado=concluido&limite=50&ordenar=criado_em:desc").json()
    time.sleep(0.5)
    na_tela = page.locator("#lista-corpo tr[data-id]").count()
    assert na_tela == min(api["total"], 50), (na_tela, api["total"])
    total_tela = page.text_content("#lista-total")
    assert re.sub(r"\D", "", total_tela) == str(api["total"]), (total_tela, api["total"])
    if api["total"]:
        assert page.locator("#lista-corpo tr[data-id]").first.get_attribute("data-id") == api["itens"][0]["id"]
    conferir_limpo(page)


def test_primeira_pintura_com_mil_jobs(pagina, base_url, env, sessao, medida):
    page = pagina
    _, tenant_id, usuario_id = sessao
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', %s, true)",
                (str(tenant_id), str(usuario_id), "admin"),
            )
            cur.execute("SELECT to_regclass('plat.job') AS t")
            if cur.fetchone()["t"] is None:
                pytest.skip("plat.job ainda não existe (migração 004 do backend não aplicada)")
            cur.execute("SELECT plat.semente_demo_habilitada() AS ligada")
            if not cur.fetchone()["ligada"]:
                pytest.skip(
                    "plat.ambiente.semear_demo = false: a semeadura de demonstração está desligada nesta "
                    "instalação (ligar com PLAT_AMBIENTE=dev ou PLAT_SEMENTE_DEMO=sim no .env e rodar install.sh)"
                )
            # semeadura pela função SECURITY DEFINER de demonstração (migração 014): cria jobs TERMINAIS no
            # inquilino de demonstração do contexto; INSERT direto por plat_app é barrado pela 006, e é para
            # continuar barrado (o teste não afrouxa o produto para caber em si mesmo)
            cur.execute(
                "SELECT plat.jobs_semear_demo(%s, %s, %s::jsonb) AS n",
                (1000, "prova.progresso", '{"duracao_s": 0, "passos": 1}'),
            )
            semeados = cur.fetchone()["n"]
        con.commit()
        assert semeados >= 1000, semeados
        try:
            pronto_ms = abrir_tarefas(page)
            page.select_option("#f-periodo", "tudo")
            page.wait_for_function("() => /\\d/.test(document.querySelector('#lista-total').textContent)")
            total = int(re.sub(r"\D", "", page.text_content("#lista-total")))
            assert total >= 1000, total
            assert page.locator("#lista-corpo tr[data-id]").count() == 50
            pintura = page.evaluate(
                "() => { const e = performance.getEntriesByType('paint')"
                ".find(p => p.name === 'first-contentful-paint'); return e ? e.startTime : null; }"
            )
            assert pintura is not None, "sem first-contentful-paint"
            page.screenshot(path=str(CAPTURAS / f"{ITEM}_mil.png"), full_page=False)
            conferir_limpo(page)
            gravar = medida(ITEM)
            gravar("primeira_pintura_tarefas_ms", round(pintura, 1), "ms",
                   "first-contentful-paint de /tarefas com 1.000 jobs semeados por plat.jobs_semear_demo no inquilino "
                   "de demonstração (chromium)")
            gravar("pagina_tarefas_mil_pronta_ms", pronto_ms, "ms",
                   "goto('/tarefas') até body[data-pronto=1] com 1.000 jobs semeados")
            assert pintura <= 1000, f"primeira pintura {pintura:.0f} ms > 1.000 ms (portão do item)"
        finally:
            with con.cursor() as cur:
                cur.execute("SET search_path = plat, public")
                cur.execute(
                    "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', %s, true)",
                    (str(tenant_id), str(usuario_id), "admin"),
                )
                cur.execute("DELETE FROM plat.job WHERE parametros->>'semente_demo' = 'true'")
            con.commit()
    finally:
        con.close()


def test_agendas_criar_pausar_retomar_apagar(pagina, base_url):
    page = pagina
    abrir_tarefas(page)
    if not page.locator("#agendas").is_visible():
        pytest.skip("seção de agendas oculta para este perfil")
    nome = "e2e " + hashlib.sha1(str(time.time()).encode()).hexdigest()[:8]
    page.click("#agenda-nova")
    form = page.locator("#agenda-form")
    form.locator("input[name=nome]").fill(nome)
    form.locator("select[name=tipo]").select_option("prova.progresso")
    form.locator("textarea[name=parametros]").fill('{"duracao_s": 1, "passos": 1}')
    form.locator("input[name=fuso]").fill("America/Sao_Paulo")

    # cron com 4 campos: recusada no navegador, erro no próprio campo
    form.locator("input[name=cron]").fill("0 3 * *")
    form.locator("button[type=submit]").click()
    page.wait_for_selector("#agenda-form [data-campo=cron] .erro-campo", timeout=5000)
    # cron com minuto 61: chega ao servidor e volta 422 no campo (detalhe)
    form.locator("input[name=cron]").fill("61 3 * * *")
    form.locator("button[type=submit]").click()
    page.wait_for_selector("#agenda-form [data-campo=cron] .erro-campo, #agenda-form plat-aviso:not([hidden])",
                           timeout=10000)
    assert page.locator(f"#agendas-tabela tr:has-text('{nome}')").count() == 0

    form.locator("input[name=cron]").fill("0 3 * * *")
    form.locator("button[type=submit]").click()
    row = page.locator(f"#agendas-tabela tr:has-text('{nome}')")
    row.wait_for(timeout=10000)
    assert page.locator("#agenda-form-caixa").is_hidden()
    assert "pausada" not in row.text_content()

    row.locator("button.acao-pausar").click()
    page.wait_for_selector(f"#agendas-tabela tr:has-text('{nome}') .marcador:has-text('pausada')", timeout=10000)
    api = page.request.get(f"{base_url}/api/agendas?limite=200").json()
    mina = [a for a in api["itens"] if a["nome"] == nome]
    assert mina and mina[0]["ativa"] is False

    row = page.locator(f"#agendas-tabela tr:has-text('{nome}')")
    row.locator("button.acao-retomar").click()
    page.wait_for_selector(f"#agendas-tabela tr:has-text('{nome}') button.acao-pausar", timeout=10000)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_agendas.png"), full_page=True)

    row = page.locator(f"#agendas-tabela tr:has-text('{nome}')")
    row.locator("button.acao-apagar").click()
    confirmar_dialogo(page)
    page.wait_for_function(f"() => !document.querySelector('#agendas-tabela').textContent.includes('{nome}')",
                           timeout=10000)
    api = page.request.get(f"{base_url}/api/agendas?limite=200").json()
    assert not [a for a in api["itens"] if a["nome"] == nome]
    conferir_limpo(page)


# ---------------------------------------------------------------- periódicos (item L0-05-d, achado do testador T3)
# os periódicos da plataforma (expurgo/sessões/manutenção/lixeira/versões) são linhas de `plat.agenda` do
# inquilino TÉCNICO `plataforma` (ADR 0003 seção 7): o admin de um inquilino comum nunca as vê (RLS), então a
# tela só mostra "os periódicos" para quem loga como admin de `plataforma` — sessão própria aqui, sem senha,
# pelas mesmas funções SECURITY DEFINER que `sessao`/`sessao_visualizador` já usam.

@pytest.fixture(scope="session")
def sessao_plataforma_e2e(env, api_jobs_disponivel):
    from tests import jobs_sessao

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        r = jobs_sessao.criar_sessao(con, "plataforma", "admin")
        con.commit()
        return r
    finally:
        con.close()


@pytest.fixture
def pagina_plataforma(page, base_url, sessao_plataforma_e2e):
    u = urlparse(base_url)
    page.context.add_cookies([{
        "name": COOKIE, "value": sessao_plataforma_e2e[0], "domain": u.hostname, "path": "/",
        "httpOnly": True, "secure": u.scheme == "https", "sameSite": "Lax",
    }])
    erros, respostas = [], []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    page.on("response", lambda r: respostas.append((r.url, r.status)))
    page.erros = erros
    page.respostas = respostas
    return page


def test_tela_lista_os_periodicos_e_rodar_agora_admin_plataforma(pagina_plataforma, base_url):
    """Portão literal L0-05-d: 'tela lista os periódicos e permite rodar agora (admin)'. Usa `manutenção semanal`
    (ANALYZE nas tabelas centrais, migração 026) porque é o mais seguro de disparar fora de hora: só lê/atualiza
    estatística do planejador, nunca apaga nada."""
    page = pagina_plataforma
    abrir_tarefas(page)
    if not page.locator("#agendas").is_visible():
        pytest.skip("seção de agendas oculta para este perfil")
    for nome_p in ("expurgo diário", "sessões vencidas", "manutenção semanal", "lixeira diária", "versões diárias"):
        page.locator(f"#agendas-tabela tr:has-text('{nome_p}')").first.wait_for(timeout=10000)
    antes = page.request.get(f"{base_url}/api/jobs",
                             params={"tipo": "jobs.manutencao_analyze", "limite": 1}).json()["total"]
    row = page.locator("#agendas-tabela tr:has-text('manutenção semanal')")
    row.locator("button.acao-rodar").click()
    page.wait_for_function(
        "async ([base, antes]) => {"
        "  const r = await fetch(`${base}/api/jobs?tipo=jobs.manutencao_analyze&limite=1`);"
        "  const j = await r.json();"
        "  return j.total > antes;"
        "}",
        arg=[base_url, antes], timeout=15000)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_periodicos.png"), full_page=True)
    conferir_limpo(page)


# ---------------------------------------------------------------- perfil visualizador (correção T2 (3))

@pytest.fixture
def sessao_visualizador(env, sessao):
    """Usuário `visualizador` temporário no inquilino demo + token de sessão; apagado no fim.
    Antes da migração 015 este perfil tomava 403 em /api/jobs* e a tela ficava em '…' com 4 erros de console."""
    from tests import jobs_sessao

    _, tenant_id, admin_id = sessao
    login = "zt-vis-tarefas"
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        uid = jobs_sessao.criar_usuario_temporario(con, tenant_id, admin_id, login, "visualizador")
        token = jobs_sessao.sessao_de_usuario(con, tenant_id, uid, login)
        yield token, tenant_id, uid
    finally:
        try:
            jobs_sessao.apagar_usuario_temporario(con, tenant_id, admin_id, login)
        finally:
            con.close()


@pytest.fixture
def pagina_visualizador(page, base_url, sessao_visualizador):
    u = urlparse(base_url)
    page.context.add_cookies([{
        "name": COOKIE, "value": sessao_visualizador[0], "domain": u.hostname, "path": "/", "httpOnly": True,
        "secure": u.scheme == "https", "sameSite": "Lax",
    }])
    erros, respostas = [], []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    page.on("response", lambda r: respostas.append((r.url, r.status)))
    page.erros = erros
    page.respostas = respostas
    return page


def test_visualizador_le_a_tela_em_modo_so_leitura(pagina_visualizador, base_url):
    """P1 para o perfil `visualizador`: a tela Tarefas pinta, lista em modo só-leitura e não tem erro de console.
    Modo só-leitura = sem cancelar, sem repetir, sem a seção de agendas (todas exigem jobs.executar)."""
    page = pagina_visualizador
    abrir_tarefas(page)
    assert page.text_content("h1").strip() == "Tarefas"

    # a lista carregou de verdade (não ficou em "…"): o contador tem número e a tabela existe
    page.wait_for_function("() => /\\d/.test(document.querySelector('#lista-total').textContent)", timeout=10000)
    assert re.search(r"\d", page.text_content("#lista-total"))
    assert page.locator("#lista").is_visible()

    # nenhuma rota de leitura da fila devolveu 403 (era o defeito)
    proibidas = [(u, s) for u, s in page.respostas if s == 403 and "/api/" in u]
    assert proibidas == [], proibidas
    lidas = {u.split(base_url)[-1].split("?")[0] for u, s in page.respostas if s == 200 and "/api/jobs" in u}
    assert {"/api/jobs", "/api/jobs/resumo", "/api/jobs/tipos"} <= lidas, lidas

    # só-leitura: nenhum botão de execução na tela, seção de agendas oculta
    assert page.locator("#lista-corpo button.acao-cancelar").count() == 0
    assert page.locator("#lista-corpo button.acao-repetir").count() == 0
    assert page.locator("#agendas").is_hidden()
    assert page.locator("#f-quem").is_hidden()  # filtro "quem" é de admin

    page.screenshot(path=str(CAPTURAS / f"{ITEM}_visualizador.png"), full_page=False)
    conferir_limpo(page)
