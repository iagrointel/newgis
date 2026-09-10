"""e2e do portal de API (item L7-08-d), contra um uvicorn próprio em 127.0.0.1:8173.

O portão de pronto do item é uma frase só, e cada pedaço dela é um passo daqui:
  navegar o portal · executar um GET com a chave de demonstração e ver a resposta · chave expirada 401 em
  Problem Details · chave de escopo leitura em rota de escrita 403 · revogar e ser negado em menos de 5 s ·
  nenhum recurso externo carregado.

O "nenhum recurso externo" é medido de verdade: `page.on("request")` guarda TODA requisição que o navegador
faz, inclusive as que a CSP bloquearia, e o teste reprova se alguma sair para host que não seja o do
servidor. Contar só o que está escrito no HTML não bastaria — módulo ES pode buscar em tempo de execução.

O servidor é subido e derrubado por este arquivo, pelo PID, e serve `/static/` de dentro da própria
aplicação (PLAT_SERVIR_ESTATICO=1): sem nginx na frente, é o único jeito de a folha e o módulo da página
chegarem ao navegador. Ver o comentário em app/main.py.
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L7-08-d-portal-api-chaves"
RAIZ = Path(__file__).resolve().parents[2]
CAPTURAS = Path(__file__).resolve().parent / "capturas"
PORTA = 8173
ESCOPOS_LEITURA = ["catalogo:ler", "camada:ler", "tiles:ler"]
RECURSO_FALHOU = re.compile(r"Failed to load resource: the server responded with a status of (\d{3})")


def _porta_livre(porta: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


@pytest.fixture(scope="module")
def servidor(env):
    """uvicorn do worktree em :8173, com /static/ servido pela própria aplicação. Derrubado pelo PID."""
    if not _porta_livre(PORTA):
        pytest.skip(f"porta {PORTA} já ocupada nesta máquina")
    ambiente = dict(os.environ, PLAT_SERVIR_ESTATICO="1", PLAT_POOL_MIN="1", PLAT_POOL_MAX="2")
    processo = subprocess.Popen(
        [str(RAIZ / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORTA), "--no-access-log"],
        cwd=str(RAIZ), env=ambiente, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{PORTA}"
    for _ in range(80):
        if processo.poll() is not None:
            saida = (processo.stdout.read() or b"").decode("utf-8", "replace")
            pytest.fail(f"uvicorn morreu na partida:\n{saida[-3000:]}")
        try:
            if httpx.get(f"{url}/saude", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        processo.send_signal(signal.SIGTERM)
        pytest.fail(f"uvicorn não respondeu /saude em {url}")
    yield url
    processo.send_signal(signal.SIGTERM)  # só pelo PID deste processo; nunca pkill
    try:
        processo.wait(timeout=15)
    except subprocess.TimeoutExpired:
        processo.kill()


@pytest.fixture(scope="module")
def sessao_http(servidor):
    """Cliente HTTP autenticado como admin de demo, para criar e revogar as chaves do teste."""
    from tests.e2e.apoio import credenciais

    c = credenciais()
    if "demo" not in c:
        pytest.skip("tests/credenciais.txt sem a linha do inquilino demo")
    login, senha = c["demo"]
    cliente = httpx.Client(base_url=servidor, timeout=30)
    r = cliente.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
    if r.status_code != 200 or not r.json().get("ok"):
        pytest.skip(f"login do admin de demo falhou nesta base: {r.status_code} {r.text[:200]}")
    yield cliente
    cliente.post("/api/logout", json={})
    cliente.close()


def criar_chave(sessao_http, nome, escopos=None, dias=1):
    r = sessao_http.post(
        "/api/tokens", json={"nome": nome, "escopos": escopos or ESCOPOS_LEITURA, "validade_dias": dias}
    )
    assert r.status_code == 201, r.text
    return r.json()


class Observador:
    """Guarda console, erros de página e TODA requisição feita pelo navegador (inclusive as bloqueadas)."""

    def __init__(self, page, url_base):
        self.host = urlsplit(url_base).netloc
        self.console: list[str] = []
        self.pedidos: list[str] = []
        self.respostas: list[tuple[str, int]] = []
        self.esperados: set[int] = set()
        page.on("console", lambda m: self.console.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: self.console.append(f"pageerror: {e}"))
        page.on("request", lambda r: self.pedidos.append(r.url))
        page.on("response", lambda r: self.respostas.append((r.url, r.status)))

    @property
    def externos(self) -> list[str]:
        return [u for u in self.pedidos
                if not u.startswith("data:") and not u.startswith("blob:")
                and urlsplit(u).netloc not in ("", self.host)]

    def conferir(self, esperados=()):
        self.esperados.update(esperados)
        graves = []
        for linha in self.console:
            m = RECURSO_FALHOU.search(linha)
            if m and int(m.group(1)) in self.esperados:
                continue
            graves.append(linha)
        assert graves == [], graves
        ruins = [(u, s) for u, s in self.respostas if s >= 400 and s not in self.esperados]
        assert ruins == [], ruins


def abrir_portal(page, servidor):
    obs = Observador(page, servidor)
    page.goto(f"{servidor}/portal", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=25000)
    return obs


def escolher_rota(page, verbo, caminho):
    page.fill("#filtro", caminho)
    page.locator(f'button.portal-rota[data-id="{verbo} {caminho}"]').first.click()
    page.wait_for_selector("#cartao-rota:not([hidden])", timeout=10000)


def executar(page):
    page.click("#executar")
    page.wait_for_selector("#resposta:not([hidden])", timeout=20000)
    return int(page.get_attribute("#resposta", "data-status"))


def test_portal_navega_executa_e_recusa(page, servidor, sessao_http, medida):
    chave = criar_chave(sessao_http, "zt-e2e-portal-leitura")
    obs = abrir_portal(page, servidor)

    # --- o índice veio do OpenAPI e mostra o escopo de cada rota
    assert page.locator("button.portal-rota").count() > 100
    assert "de 197 rotas" in page.text_content("#contagem") or "rotas" in page.text_content("#contagem")
    page.fill("#chave", chave["token"])
    page.dispatch_event("#chave", "input")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_indice.png"), full_page=True)

    # --- 1. executar um GET com a chave de demonstração e ver a resposta
    escolher_rota(page, "get", "/api/eu")
    assert page.text_content("#rota-escopo").startswith("token:qualquer")
    assert executar(page) == 200
    corpo = page.text_content("#resp-corpo")
    assert '"escopos"' in corpo and "catalogo:ler" in corpo, corpo[:400]
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_experimentar_200.png"), full_page=True)

    escolher_rota(page, "get", "/api/itens")
    assert page.text_content("#rota-escopo").startswith("catalogo:ler")
    assert executar(page) == 200

    # --- 2. chave de escopo leitura em rota de escrita -> 403
    escolher_rota(page, "post", "/api/itens")
    assert page.text_content("#rota-escopo").startswith("admin:inquilino")
    assert executar(page) == 403
    corpo = json.loads(page.text_content("#resp-corpo"))
    assert corpo["erro"] == "escopo_insuficiente" and corpo["status"] == 403, corpo
    assert corpo["type"] == "urn:plat:erro:escopo_insuficiente", corpo
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_escopo_403.png"), full_page=True)

    # --- 3. chave expirada -> 401 em Problem Details
    expirada = criar_chave(sessao_http, "zt-e2e-portal-expirada", dias=0)
    page.fill("#chave", expirada["token"])
    escolher_rota(page, "get", "/api/itens")
    assert executar(page) == 401
    corpo = json.loads(page.text_content("#resp-corpo"))
    for campo in ("type", "title", "status", "detail", "instance", "erro", "mensagem", "req_id"):
        assert campo in corpo, (campo, sorted(corpo))
    assert corpo["erro"] == "token_expirado" and corpo["status"] == 401, corpo
    assert "application/problem+json" in page.text_content("#resp-tipo")
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_expirada_401.png"), full_page=True)
    sessao_http.delete(f"/api/tokens/{expirada['id']}")

    # --- 4. revogar e ser negado (prazo medido; o código é 401 token_revogado, ver o handoff)
    page.fill("#chave", chave["token"])
    escolher_rota(page, "get", "/api/itens")
    assert executar(page) == 200
    t0 = time.perf_counter()
    assert sessao_http.delete(f"/api/tokens/{chave['id']}").status_code == 204
    status = executar(page)
    segundos = time.perf_counter() - t0
    assert status == 401, status
    assert json.loads(page.text_content("#resp-corpo"))["erro"] == "token_revogado"
    assert segundos < 5, segundos
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_revogada.png"), full_page=True)

    # --- 5. nenhum recurso externo em nenhuma das navegações acima
    assert obs.externos == [], obs.externos
    obs.conferir(esperados=(401, 403))

    gravar = medida(ITEM)
    gravar("recursos_externos_carregados_pelo_portal", len(obs.externos), "requisições",
           "page.on('request') no chromium do playwright; conta host != 127.0.0.1:8173")
    gravar("requisicoes_do_portal", len(obs.pedidos), "requisições", "mesma coleta, total de requisições")
    gravar("segundos_revogar_ate_negar_no_portal", round(segundos, 3), "s",
           "tests/e2e/test_portal.py; DELETE /api/tokens/{id} até o botão Experimentar receber 401")


def test_portal_lista_os_vinte_exemplos(page, servidor, medida):
    obs = abrir_portal(page, servidor)
    page.click("#aba-python")
    python = page.locator("#lista-exemplos li").count()
    page.click("#aba-js")
    js = page.locator("#lista-exemplos li").count()
    assert (python, js) == (10, 10), (python, js)
    assert "20 no total" in page.text_content("#contagem-exemplos")
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_exemplos.png"), full_page=True)
    assert obs.externos == [], obs.externos
    obs.conferir()


def test_os_vinte_exemplos_rodam_de_verdade(servidor, sessao_http, medida):
    """Executa os 20 arquivos de exemplos/ como programa, contra o servidor deste teste."""
    chave = criar_chave(sessao_http, "zt-e2e-exemplos")
    ambiente = dict(os.environ, PLAT_URL=servidor, PLAT_CHAVE=chave["token"])
    falhas, rodados = [], 0
    try:
        for pasta, comando in (("python", [sys.executable]), ("js", ["node"])):
            for arquivo in sorted((RAIZ / "exemplos" / pasta).glob("*.py" if pasta == "python" else "*.mjs")):
                if arquivo.name.startswith("_"):
                    continue
                rodados += 1
                r = subprocess.run([*comando, str(arquivo)], cwd=str(arquivo.parent), env=ambiente,
                                   capture_output=True, text=True, timeout=120, check=False)
                if r.returncode != 0:
                    falhas.append((arquivo.name, r.returncode, (r.stderr or r.stdout)[-500:]))
    finally:
        sessao_http.delete(f"/api/tokens/{chave['id']}")
    assert rodados == 20, rodados
    assert falhas == [], falhas
    gravar = medida(ITEM)
    gravar("exemplos_executados_com_sucesso", rodados - len(falhas), "programas",
           "tests/e2e/test_portal.py::test_os_vinte_exemplos_rodam_de_verdade; python3 e node contra :8173")
    gravar("exemplos_que_falharam", len(falhas), "programas", "mesma execução; contrato: zero")
