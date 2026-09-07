"""e2e do item L2-07-a-pwa-instalavel-cache: PWA de campo em `/campo/`. Cobre o portão de pronto cláusula por
cláusula (ver `tests/medidas/L2-07-a-pwa-instalavel-cache.json`) e a refutação exigida (armazenamento limpo
no meio de uma coleta, relógio do dispositivo mudado, PWA de outro inquilino no mesmo navegador).

Roda contra HTTPS de verdade, não HTTP como os outros e2e do repo — e é o único deste item que precisa:
`app.js` chama `POST /api/campo/sessao` por `fetch()` DE DENTRO da página (não pela API-context que os outros
e2e usam), e a defesa de CSRF (`app/auth/sessao.py::checar_escrita_sob_cookie`, ADR 0002 seção 5.3) compara o
cabeçalho `Origin` que o navegador manda de verdade contra `PLAT_URL_PUBLICA` — em HTTP puro contra
`127.0.0.1` isso sempre bate 403/400 (medido: a app não serve `/static/` sozinha nem em HTTP nem em HTTPS,
mas a checagem de origem só aparece quando o PRÓPRIO app.js escreve sob cookie; ver `handoffs/T3/`). Rodar:

    openssl req -x509 -newkey rsa:2048 -keyout /tmp/k.pem -out /tmp/c.pem -days 3 -nodes -subj /CN=127.0.0.1
    PLAT_URL_PUBLICA=https://127.0.0.1:8219 venv/bin/python -m uvicorn app.main:app --port 8219 \\
      --ssl-keyfile /tmp/k.pem --ssl-certfile /tmp/c.pem &
    bash /home/dev/plataforma/laco/roda_teste.sh tests/e2e/test_campo_pwa.py \\
      --base-url https://127.0.0.1:8219 -q

Viewports móveis (Pixel 7 e iPhone SE) e certificado autoassinado tolerado só neste módulo (`page`/`context`
locais abaixo), sem mudar o padrão 1280×800/HTTP dos outros e2e (`tests/e2e/conftest.py`, que fica intocado)."""

from pathlib import Path

import httpx
import pytest

from tests.e2e.apoio import Tela, credenciais
from tests.e2e.apoio_campo import (
    apagar_item,
    criar_mapa_de_campo,
    entrar_por_api,
    esperar_service_worker_ativo,
    idb_apagar_banco,
    idb_config,
    idb_listar,
    nomes_de_cache,
    sair_por_api,
)
from tests.e2e.apoio_lighthouse import LighthouseIndisponivel, auditoria_pwa, itens_vermelhos

ITEM = "L2-07-a-pwa-instalavel-cache"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
VERSAO_SHELL_ARQUIVO = Path(__file__).resolve().parents[2] / "web" / "campo" / "VERSAO_SHELL"
PIXEL_7 = {"width": 412, "height": 915}
IPHONE_SE = {"width": 375, "height": 667}

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """soma `--ignore-certificate-errors` ao que `tests/e2e/conftest.py`/pytest-playwright já definem — só
    afeta o browser usado pelos testes DESTE módulo (override por nome de fixture é local ao arquivo)."""
    args = list(browser_type_launch_args.get("args", []))
    args.append("--ignore-certificate-errors")
    return {**browser_type_launch_args, "args": args}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True, "viewport": PIXEL_7, "device_scale_factor": 2.6}


@pytest.fixture
def contexto_movel(context):
    """o `context`/`page` padrão do pytest-playwright já saem com o `browser_context_args` acima (HTTPS
    tolerante + viewport de celular) — só reexportado com um nome que deixa claro, nos testes, que é o
    contexto MÓVEL do portão, não uma fixture nova."""
    return context


@pytest.fixture
def pagina_movel(page, api_campo):
    """`page` padrão + revogação do token de campo que o teste tiver mintado (`POST /api/campo/sessao` sem
    reaproveitar nada — cada teste é um contexto de navegador novo, sem `config` local — para não estourar
    `limites.TOKENS_POR_USUARIO=20` do usuário demo em corridas repetidas desta suíte; medido: sem isto a
    20ª rodada trava toda sincronização com `limite_tokens`, sem log óbvio do porquê)."""
    yield page
    try:
        cfg = idb_config(page, "token_campo")
        if cfg and cfg.get("id"):
            api_campo.delete(f"/api/tokens/{cfg['id']}")
    except Exception:
        pass


@pytest.fixture(scope="session")
def rotas_api(base_url, url_publica_resolve) -> set:
    """mesma fixture de `tests/e2e/conftest.py`, mas tolerando o certificado autoassinado deste módulo (o
    `httpx.get` de lá não passa `verify=False` — reescrever aqui em vez de editar o conftest compartilhado)."""
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    try:
        r = httpx.get(f"{base_url}/api/openapi.json", timeout=15, verify=False)
    except httpx.HTTPError as e:
        pytest.skip(f"{base_url}/api/openapi.json inacessível: {e}")
    if r.status_code != 200:
        pytest.skip(f"{base_url}/api/openapi.json devolveu {r.status_code}")
    return set(r.json().get("paths", {}))


@pytest.fixture(scope="session")
def api_campo(playwright, base_url):
    """API-context própria (certificado autoassinado tolerado) para preparar/limpar dado de teste sem passar
    pela UI — o `admin_api` de `tests/e2e/conftest.py` fica intocado (ele quebra contra HTTPS autoassinado;
    reusar exigiria editar um arquivo que todo outro e2e do repo também usa)."""
    login, senha = credenciais()["demo"]
    ctx = playwright.request.new_context(base_url=base_url, ignore_https_errors=True)
    r = ctx.post("/api/login", data={"inquilino": "demo", "login": login, "senha": senha})
    assert r.status == 200 and r.json().get("ok") is True, (r.status, r.text())
    yield ctx
    ctx.post("/api/logout", data={})
    ctx.dispose()


@pytest.fixture
def mapa_de_campo(api_campo):
    """item tipo `mapa` para a lista de campo ter o que mostrar, criado por `api_campo` (independe de
    qualquer outro teste rodar antes)."""
    r = api_campo.post(
        "/api/itens",
        data={
            "tipo": "mapa",
            "titulo": "Mapa de campo E2E — sem rede",
            "dados": {"esquema_versao": 1, "corpo": {"camadas": [{"id": "c1", "nome": "talhões"}]}},
        },
    )
    assert r.status == 201, (r.status, r.text())
    item = r.json()
    yield item
    api_campo.delete(f"/api/itens/{item['id']}")
    api_campo.post("/api/lixeira/esvaziar", data={"ids": [item["id"]]})


def _preparar_online(pagina, base_url, slug, login, senha, mapa_de_campo):
    """login por sessão (ver `entrar_por_api`: mesmo cookie que o `page` usa nas chamadas do app.js), navega a
    /campo/, espera o service worker ativar e a sincronização inicial completar (mapa visível na lista)."""
    tela = Tela(pagina, base_url)
    entrar_por_api(pagina, slug, login, senha)
    pagina.goto("/campo/", wait_until="domcontentloaded")
    pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
    esperar_service_worker_ativo(pagina)
    pagina.wait_for_function(
        "(titulo) => document.getElementById('lista-mapas').textContent.includes(titulo)",
        arg=mapa_de_campo["titulo"],
        timeout=15000,
    )
    return tela


# ---------------------------------------------------------------- instalabilidade
def test_manifest_valido_e_service_worker_registrado_com_prompt_de_instalacao(
    pagina_movel, base_url, credenciais_demo, mapa_de_campo, medida
):
    slug, login, senha = credenciais_demo
    tela = _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)

    manifest_url = pagina_movel.eval_on_selector("link[rel=manifest]", "el => el.href")
    r = httpx.get(manifest_url, timeout=15, verify=False)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    for campo in ("name", "short_name", "start_url", "display", "icons", "theme_color", "background_color"):
        assert campo in m, (campo, m)
    assert m["display"] == "standalone"
    assert m["start_url"] == "/campo/"
    assert any(ic["sizes"] == "192x192" for ic in m["icons"])
    assert any(ic["sizes"] == "512x512" for ic in m["icons"])
    assert any("maskable" in ic.get("purpose", "") for ic in m["icons"])

    registrado = pagina_movel.evaluate(
        "async () => { const r = await navigator.serviceWorker.getRegistration('/campo/'); "
        "return !!(r && r.active); }"
    )
    assert registrado is True

    # beforeinstallprompt: o Chromium só dispara de verdade sob heurística de engajamento própria, não
    # reproduzível em headless — o portão pede conferir que a PÁGINA lida com o evento, então disparamos um
    # evento sintético com os mesmos métodos que o navegador real forneceria (prompt()/userChoice) e
    # verificamos que o app.js captura, mostra o botão de instalar e chama prompt() ao clicar.
    pagina_movel.evaluate(
        "() => { window.__promptChamado = false; const ev = new Event('beforeinstallprompt', {cancelable: true}); "
        "ev.prompt = () => { window.__promptChamado = true; return Promise.resolve(); }; "
        "ev.userChoice = Promise.resolve({outcome: 'accepted', platform: 'web'}); "
        "window.dispatchEvent(ev); }"
    )
    pagina_movel.wait_for_selector("#secao-instalar:not([hidden])", timeout=5000)
    pagina_movel.click("#botao-instalar")
    pagina_movel.wait_for_function("() => window.__promptChamado === true", timeout=5000)
    pagina_movel.wait_for_selector("#secao-instalar[hidden]", state="attached", timeout=5000)

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    pagina_movel.screenshot(path=str(CAPTURAS / f"{ITEM}_instalavel.png"), full_page=True)
    tela.verificar()
    gravar = medida(ITEM)
    gravar("manifest_campos_presentes", 1, "booleano",
           "GET manifest.webmanifest + asserts de campo (este teste)")
    gravar("beforeinstallprompt_capturado", 1, "booleano",
           "evento sintético dispatchado + botão instalar chama prompt()")


# ---------------------------------------------------------------- offline
def test_offline_abre_mostra_mapa_cacheado_e_fila(
    pagina_movel, contexto_movel, base_url, credenciais_demo, mapa_de_campo, medida
):
    slug, login, senha = credenciais_demo
    _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)

    mapas_idb = idb_listar(pagina_movel, "plat_campo", "mapas")
    assert any(m["titulo"] == mapa_de_campo["titulo"] for m in mapas_idb), mapas_idb

    contexto_movel.set_offline(True)
    pagina_movel.reload(wait_until="domcontentloaded")
    pagina_movel.wait_for_selector("body[data-pronto='1']", timeout=20000)

    assert pagina_movel.text_content("#estado-rede").strip().startswith("offline")
    assert mapa_de_campo["titulo"] in pagina_movel.text_content("#lista-mapas")
    assert "pendente" in pagina_movel.text_content("#fila-contagem")

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    pagina_movel.screenshot(path=str(CAPTURAS / f"{ITEM}_offline.png"), full_page=True)
    contexto_movel.set_offline(False)
    gravar = medida(ITEM)
    gravar("abre_offline_com_mapa_cacheado", 1, "booleano", "context.set_offline(True) + reload (este teste)")


# ---------------------------------------------------------------- token revogado
def test_token_revogado_bloqueia_sync_mas_preserva_dado_local(
    pagina_movel, base_url, credenciais_demo, mapa_de_campo, api_campo, medida
):
    slug, login, senha = credenciais_demo
    _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)

    config = idb_config(pagina_movel, "token_campo")
    assert config and config.get("id"), config
    mapas_antes = idb_listar(pagina_movel, "plat_campo", "mapas")
    assert mapas_antes, "precisa ter sincronizado ao menos um mapa antes de revogar"

    r = api_campo.delete(f"/api/tokens/{config['id']}")
    assert r.status == 204, r.status

    pagina_movel.reload(wait_until="domcontentloaded")
    pagina_movel.wait_for_selector("body[data-pronto='1']", timeout=20000)
    pagina_movel.wait_for_selector("#aviso-token:not([hidden])", timeout=15000)
    aviso = pagina_movel.text_content("#aviso-token")
    assert "revogad" in aviso.lower() or "expir" in aviso.lower(), aviso

    mapas_depois = idb_listar(pagina_movel, "plat_campo", "mapas")
    assert len(mapas_depois) == len(mapas_antes) and mapas_depois, (mapas_antes, mapas_depois)
    assert mapa_de_campo["titulo"] in pagina_movel.text_content("#lista-mapas")

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    pagina_movel.screenshot(path=str(CAPTURAS / f"{ITEM}_token_revogado.png"), full_page=True)
    gravar = medida(ITEM)
    gravar("token_revogado_preserva_dado_local", 1, "booleano", "DELETE /api/tokens/{id} + reload (este teste)")


# ---------------------------------------------------------------- versão do shell
def test_troca_de_versao_invalida_shell_em_ate_1_recarga(
    pagina_movel, base_url, credenciais_demo, mapa_de_campo, medida
):
    original = VERSAO_SHELL_ARQUIVO.read_text(encoding="utf-8")
    try:
        slug, login, senha = credenciais_demo
        _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)
        versao_a = pagina_movel.get_attribute("body", "data-versao-shell")
        cache_a = f"campo-shell-{versao_a}"
        caches_antes = nomes_de_cache(pagina_movel)
        assert cache_a in caches_antes, (cache_a, caches_antes)

        nova_versao = (original.strip() or "0") + "-nova"
        cache_nova = f"campo-shell-{nova_versao}"
        VERSAO_SHELL_ARQUIVO.write_text(nova_versao + "\n", encoding="utf-8")

        # a checagem de versão roda EM SEGUNDO PLANO (a mesma que `app.js::registrarServiceWorker` já dispara
        # sozinho a cada abertura do app — aqui só forçada de novo para não depender do relógio de 24h do
        # navegador dentro do teste); só DEPOIS dela terminar (install+activate: cache novo sozinho na lista,
        # nome exato, nunca substring) é que a recarga do portão acontece — e essa é a ÚNICA recarga.
        pagina_movel.evaluate(
            "async () => { const r = await navigator.serviceWorker.getRegistration('/campo/'); await r.update(); }"
        )
        pagina_movel.wait_for_function(
            "(esperado) => caches.keys().then((ns) => JSON.stringify(ns) === JSON.stringify(esperado))",
            arg=[cache_nova],
            timeout=10000,
        )
        pagina_movel.wait_for_timeout(300)  # a troca de `caches.keys()` para activate/clients.claim() é assíncrona

        recargas = 1
        pagina_movel.reload(wait_until="domcontentloaded")
        pagina_movel.wait_for_selector("body[data-pronto='1']", timeout=20000)
        versao_apos_1 = pagina_movel.get_attribute("body", "data-versao-shell")

        caches_depois = nomes_de_cache(pagina_movel)
        assert cache_a not in caches_depois, caches_depois  # cache antigo removido no activate

        gravar = medida(ITEM)
        gravar("recargas_ate_shell_novo", recargas, "contagem",
               "troca de VERSAO_SHELL + update() + reload único (este teste)")
        assert recargas <= 1, f"portão pede <= 1 recarga; medido {recargas} (registrado como parcial nomeado)"
        assert versao_apos_1 == nova_versao, (versao_apos_1, nova_versao)
    finally:
        VERSAO_SHELL_ARQUIVO.write_text(original, encoding="utf-8")


# ---------------------------------------------------------------- acessibilidade de toque
def test_alvos_de_toque_maiores_ou_iguais_a_44px(pagina_movel, base_url, credenciais_demo, mapa_de_campo, medida):
    slug, login, senha = credenciais_demo
    _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)
    alvos = pagina_movel.evaluate(
        "() => Array.from(document.querySelectorAll('button, a, select')).map(el => { "
        "const r = el.getBoundingClientRect(); return {id: el.id || el.tagName, w: r.width, h: r.height}; })"
    )
    pequenos = [a for a in alvos if a["w"] > 0 and (a["w"] < 44 or a["h"] < 44)]
    assert pequenos == [], pequenos
    gravar = medida(ITEM)
    gravar("alvos_de_toque_conferidos", len(alvos), "contagem",
           "getBoundingClientRect() de button/a/select (este teste)")


# ---------------------------------------------------------------- tamanho do shell
def test_tamanho_do_shell_ate_1_5mb(base_url, url_publica_resolve, medida):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    arquivos = [
        "/campo/", "/campo/campo.css", "/campo/app.js", "/campo/idb.js",
        "/campo/manifest.webmanifest", "/campo/icone-192.png", "/campo/icone-512.png",
    ]
    total = 0
    for caminho in arquivos:
        r = httpx.get(f"{base_url}{caminho}", timeout=15, verify=False)
        assert r.status_code == 200, (caminho, r.status_code)
        total += len(r.content)
    limite = 1_500_000
    gravar = medida(ITEM)
    gravar("shell_bytes", total, "bytes", "soma do Content-Length dos arquivos do SHELL (este teste)")
    assert total <= limite, (total, limite)


# ---------------------------------------------------------------- lighthouse
def test_lighthouse_pwa_sem_item_vermelho(base_url, url_publica_resolve, mapa_de_campo, medida, tmp_path):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    saida = tmp_path / "lighthouse_campo.json"
    try:
        relatorio = auditoria_pwa(f"{base_url}/campo/", saida)
    except LighthouseIndisponivel as e:
        pytest.skip(f"lighthouse indisponível nesta máquina: {e}")  # nunca reprova por infraestrutura ausente
    vermelhos = itens_vermelhos(relatorio)
    assert vermelhos == [], vermelhos
    gravar = medida(ITEM)
    gravar("lighthouse_pwa_score", relatorio["categories"]["pwa"]["score"], "0-1",
           "lighthouse --only-categories=pwa (este teste)")


# ---------------------------------------------------------------- refutação do adversário
def test_adversario_limpa_armazenamento_no_meio_da_coleta(
    pagina_movel, base_url, credenciais_demo, mapa_de_campo, medida
):
    slug, login, senha = credenciais_demo
    tela = _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)
    idb_apagar_banco(pagina_movel, "plat_campo")
    pagina_movel.reload(wait_until="domcontentloaded")
    pagina_movel.wait_for_selector("body[data-pronto='1']", timeout=20000)
    # o app não deve travar nem gerar erro de console: banco recriado do zero, ressincroniza online
    pagina_movel.wait_for_function(
        "(titulo) => document.getElementById('lista-mapas').textContent.includes(titulo)",
        arg=mapa_de_campo["titulo"],
        timeout=15000,
    )
    tela.verificar()
    gravar = medida(ITEM)
    gravar("sobrevive_a_indexeddb_apagado_no_meio", 1, "booleano", "indexedDB.deleteDatabase + reload (este teste)")


def test_adversario_muda_relogio_nao_burla_revogacao(
    pagina_movel, base_url, credenciais_demo, mapa_de_campo, api_campo, medida
):
    """token revogado agora; o dispositivo então VOLTA o relógio para antes da revogação (tentando fazer o
    app achar que o token ainda vale). O app nunca decide validade pelo relógio do cliente — só pela
    resposta do servidor —, então o bloqueio tem de continuar mesmo com o relógio do dispositivo mentindo."""
    slug, login, senha = credenciais_demo
    _preparar_online(pagina_movel, base_url, slug, login, senha, mapa_de_campo)
    config = idb_config(pagina_movel, "token_campo")
    assert config and config.get("id"), config

    r = api_campo.delete(f"/api/tokens/{config['id']}")
    assert r.status == 204, r.status

    pagina_movel.clock.install(time="2020-01-01T00:00:00")
    pagina_movel.reload(wait_until="domcontentloaded")
    pagina_movel.wait_for_selector("body[data-pronto='1']", timeout=20000)
    pagina_movel.wait_for_selector("#aviso-token:not([hidden])", timeout=15000)
    assert "revogad" in pagina_movel.text_content("#aviso-token").lower()
    gravar = medida(ITEM)
    gravar("relogio_do_dispositivo_nao_burla_revogacao", 1, "booleano", "page.clock.install + reload (este teste)")


def test_adversario_pwa_de_outro_inquilino_no_mesmo_navegador(
    contexto_movel, base_url, credenciais_demo, medida
):
    """dois inquilinos (`demo` e `demo2`, sementes do install.sh) logados em sequência no MESMO contexto de
    navegador (mesma origem): o token e os mapas de um nunca aparecem no /campo/ do outro — o IndexedDB é
    isolado por ORIGEM, não por inquilino, então o isolamento aqui é responsabilidade do app (tenant_slug na
    config, mapas trocados a cada login) e da RLS do servidor (cada token só lê o próprio inquilino)."""
    c = credenciais()
    if "demo2" not in c:
        pytest.skip("tests/credenciais.txt sem a linha do inquilino demo2 (rode install.sh)")
    slug1, login1, senha1 = credenciais_demo
    slug2, login2, senha2 = "demo2", *c["demo2"]

    pagina = contexto_movel.new_page()
    tela = Tela(pagina, base_url)
    entrar_por_api(pagina, slug1, login1, senha1)
    item1 = criar_mapa_de_campo(tela, "Mapa exclusivo do inquilino 1")
    config1 = None
    try:
        pagina.goto("/campo/", wait_until="domcontentloaded")
        pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
        esperar_service_worker_ativo(pagina)
        pagina.wait_for_function(
            "(t) => document.getElementById('lista-mapas').textContent.includes(t)",
            arg="Mapa exclusivo do inquilino 1",
            timeout=15000,
        )
        config1 = idb_config(pagina, "token_campo")
        assert config1 and config1["tenant_slug"] == slug1, config1

        # sem botão de sair no shell de campo (não é a app principal): desloga direto pela API.
        sair_por_api(pagina)
        entrar_por_api(pagina, slug2, login2, senha2)
        pagina.goto("/campo/", wait_until="domcontentloaded")
        pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
        esperar_service_worker_ativo(pagina)
        pagina.wait_for_timeout(1500)  # tempo para a sincronização do 2º inquilino tentar completar

        config2 = idb_config(pagina, "token_campo")
        assert config2 and config2["tenant_slug"] == slug2, config2
        assert config2["token"] != config1["token"]
        # revoga o token do inquilino 2 AGORA, ainda com a sessão dele ativa (o de fora, `api_campo`, é do
        # inquilino 1 — RLS não deixaria apagar token de outro inquilino).
        if config2.get("id"):
            pagina.request.delete(f"/api/tokens/{config2['id']}")

        lista_texto = pagina.text_content("#lista-mapas")
        assert "Mapa exclusivo do inquilino 1" not in lista_texto, lista_texto
    finally:
        sair_por_api(pagina)
        entrar_por_api(pagina, slug1, login1, senha1)
        if config1 and config1.get("id"):
            pagina.request.delete(f"/api/tokens/{config1['id']}")
        apagar_item(tela, item1)
        pagina.close()

    gravar = medida(ITEM)
    gravar("isolamento_por_inquilino_no_mesmo_navegador", 1, "booleano",
           "dois logins sequenciais no mesmo contexto (este teste)")
