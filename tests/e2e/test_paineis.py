"""Item L7-06-d-paineis — os cinco painéis carregam de verdade, sem 'No data', e voltam sozinhos
depois de apagados pela interface.

Precisa da pilha de homologação no ar:
    bash deploy/paineis_homologacao.sh subir
    set -a; source /tmp/plat_paineis_homolog/ambiente; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh tests/e2e/test_paineis.py -q

Não usa as fixtures do e2e do produto (base_url, sessão da plataforma): o alvo aqui é o Grafana, que
tem login próprio. As capturas ficam em tests/e2e/capturas/L7-06-d-paineis_<uid>.png.
"""

import json
import os
import time
from pathlib import Path

import httpx
import pytest

ITEM = "L7-06-d-paineis"
RAIZ = Path(__file__).resolve().parents[2]
CAPTURAS = Path(__file__).resolve().parent / "capturas"
PAINEIS = RAIZ / "deploy/grafana/paineis"
GRAFANA = os.environ.get("PLAT_PAINEIS_GRAFANA")
SENHA = os.environ.get("PLAT_PAINEIS_GRAFANA_SENHA", "")
UIDS = sorted(json.loads(c.read_text())["uid"] for c in PAINEIS.glob("*.json"))
# "No data" (inglês) e "Sem dados" (pt-BR): o idioma da tela depende do usuário do Grafana, e a
# cláusula é sobre o quadro estar vazio, não sobre a língua em que ele avisa.
VAZIO = ("No data", "Sem dados", "Datasource not found", "Fonte de dados não encontrada")


@pytest.fixture(scope="module")
def grafana() -> str:
    if not GRAFANA:
        pytest.skip("PLAT_PAINEIS_GRAFANA não definido (rode deploy/paineis_homologacao.sh subir)")
    try:
        httpx.get(f"{GRAFANA}/api/health", timeout=5).raise_for_status()
    except httpx.HTTPError as e:
        pytest.skip(f"{GRAFANA} não responde: {e}")
    return GRAFANA


@pytest.fixture(scope="module")
def api(grafana) -> httpx.Client:
    c = httpx.Client(base_url=grafana, auth=("admin", SENHA), timeout=30)
    yield c
    c.close()


@pytest.fixture(scope="module")
def pagina_logada(grafana, browser):
    ctx = browser.new_context(locale="pt-BR", viewport={"width": 1600, "height": 1200})
    p = ctx.new_page()
    p.goto(f"{grafana}/login", wait_until="domcontentloaded")
    p.fill("input[name=user]", "admin")
    p.fill("input[name=password]", SENHA)
    p.click("button[type=submit]")
    p.wait_for_url(lambda u: "/login" not in u, timeout=30000)
    yield p
    ctx.close()


def _abrir(p, grafana: str, uid: str) -> None:
    p.goto(f"{grafana}/d/{uid}?kiosk&from=now-30m&to=now&refresh=", wait_until="networkidle")
    # os quadros só ficam prontos quando a consulta volta; sem esta espera a captura pega o esqueleto
    p.wait_for_selector("[data-testid^='data-testid Panel header']", timeout=60000)
    for _ in range(30):
        if p.locator(".panel-loading, [aria-label='Panel loading bar']").count() == 0:
            break
        time.sleep(1)
    time.sleep(3)


@pytest.mark.parametrize("uid", UIDS)
def test_painel_carrega_sem_quadro_vazio(pagina_logada, grafana, uid):
    p = pagina_logada
    _abrir(p, grafana, uid)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{uid}.png"
    p.screenshot(path=str(caminho), full_page=True)
    assert caminho.stat().st_size > 10_000, f"captura vazia: {caminho}"
    texto = p.locator("body").inner_text()
    achados = [v for v in VAZIO if v in texto]
    assert not achados, f"{uid}: quadro sem dado na tela ({achados}); captura em {caminho}"


def test_provisionamento_e_idempotente(api, grafana):
    """Subir 2× = mesmo uid. Prova pelo lado que importa: o identificador interno (`id`) e a versão do
    painel também não mudam quando o provisionador relê o mesmo arquivo — se mudassem, cada reinício
    criaria um painel novo e os favoritos, alertas e links de quem usa apontariam para o antigo."""
    antes = {}
    for uid in UIDS:
        r = api.get(f"/api/dashboards/uid/{uid}")
        assert r.status_code == 200, (uid, r.status_code, r.text[:200])
        d = r.json()
        antes[uid] = (d["dashboard"]["uid"], d["dashboard"]["id"], d["meta"]["provisioned"])
        assert d["meta"]["provisioned"] is True, f"{uid} não está marcado como provisionado por arquivo"

    assert os.system("docker restart plat-paineis-homolog >/dev/null 2>&1") == 0
    for _ in range(90):
        try:
            if httpx.get(f"{grafana}/api/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    time.sleep(25)  # updateIntervalSeconds do provedor

    depois = {}
    for uid in UIDS:
        r = api.get(f"/api/dashboards/uid/{uid}")
        assert r.status_code == 200, (uid, r.status_code)
        d = r.json()
        depois[uid] = (d["dashboard"]["uid"], d["dashboard"]["id"], d["meta"]["provisioned"])
    assert antes == depois, {"antes": antes, "depois": depois}


def test_painel_apagado_pela_interface_volta_sozinho(api, grafana):
    """Refutação exigida pelo item. Apagar pela API do Grafana é o MESMO caminho que o botão da
    interface usa (DELETE /api/dashboards/uid/...) — é o que o adversário faria com o mouse."""
    alvo = "plat-visao-geral"
    r = api.delete(f"/api/dashboards/uid/{alvo}")
    assert r.status_code in (200, 412), (r.status_code, r.text[:300])
    if r.status_code == 412:
        pytest.fail("o Grafana recusou apagar; a refutação precisa que o painel realmente suma")
    assert api.get(f"/api/dashboards/uid/{alvo}").status_code == 404, "o painel não chegou a sumir"

    voltou = None
    for _ in range(60):
        time.sleep(2)
        if api.get(f"/api/dashboards/uid/{alvo}").status_code == 200:
            voltou = True
            break
    assert voltou, "o provisionamento não recriou o painel apagado em 120 s"
