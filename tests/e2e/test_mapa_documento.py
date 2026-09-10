"""e2e do documento de mapa (item L2-01-a-documento-mapa): abrir /mapa?id=<uuid>, reordenar as camadas
arrastando, salvar, recarregar a página e conferir que a ordem que voltou do banco é a que ficou na tela — com
captura em tests/e2e/capturas/L2-01-a-documento-mapa_painel_camadas.png.

O que este teste prova: que a ordem VIAJA (tela → PUT /api/mapas → banco → GET /completo → tela) e que a lista
é a do documento do mapa, não uma lista fixa na página. O que NÃO prova: desenho de camada no canvas — nesta
máquina não há servidor de tiles vetoriais (item L2-01-b), a API diz isso em `tiles.pronto` e o painel mostra o
selo "sem tiles" em vez de fingir um desenho.

Como rodar a partir de um worktree (a mesma armadilha do e2e do L2-08-a, que já está escrita lá): a defesa de
CSRF compara o `Origin` do navegador com `PLAT_URL_PUBLICA`, que só aceita `https://` — sem TLS todo PUT feito
PELA TELA volta 403, e é justamente o botão da tela que se quer provar. Daí o TLS local, o contexto de
navegador com `ignore_https_errors` e as fixtures próprias:

    openssl req -x509 -newkey rsa:2048 -nodes -keyout var/e2e/chave.pem -out var/e2e/cert.pem \\
        -days 2 -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1"
    set -a; source /home/dev/plataforma/laco/var/trilha/stac.env; set +a
    PLAT_URL_PUBLICA=https://127.0.0.1:8172 venv/bin/python -m uvicorn tests.e2e.servidor_local:app \\
        --host 127.0.0.1 --port 8172 --ssl-keyfile var/e2e/chave.pem --ssl-certfile var/e2e/cert.pem
    venv/bin/pytest tests/e2e/test_mapa_documento.py --base-url https://127.0.0.1:8172
"""

import httpx
import pytest

from tests.e2e.apoio import CAPTURAS, Tela, credenciais, sufixo

ITEM = "L2-01-a-documento-mapa"
ROTA = "/api/mapas"
CAMADAS_ULID = ["01J0000000000000000000000A", "01J0000000000000000000000B", "01J0000000000000000000000C"]

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


class TelaMapa(Tela):
    def capturar(self, nome: str):
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="module")
def api_no_ar(base_url) -> str:
    try:
        r = httpx.get(f"{base_url}/api/openapi.json", timeout=15, verify=False)  # noqa: S501 — certificado próprio
    except httpx.HTTPError as e:
        pytest.skip(f"{base_url}/api/openapi.json inacessível ({e}); veja o cabeçalho deste arquivo")
    if r.status_code != 200 or ROTA not in r.json().get("paths", {}):
        pytest.skip(f"{base_url} sem {ROTA} no OpenAPI")
    return base_url


@pytest.fixture
def pagina(browser, api_no_ar):
    ctx = browser.new_context(
        base_url=api_no_ar, locale="pt-BR", viewport={"width": 1280, "height": 900}, ignore_https_errors=True
    )
    p = ctx.new_page()
    yield p
    ctx.close()


def _criar(tela: TelaMapa, caminho: str, corpo: dict) -> dict:
    r = tela.api("POST", caminho, corpo)
    assert r.status == 201, (caminho, r.status, r.text())
    return r.json()


def _ordem_na_tela(page) -> list[str]:
    return page.eval_on_selector_all("#camadas-lista li", "els => els.map(e => e.dataset.id)")


def test_ordenar_camadas_arrastando_salvar_e_recarregar(pagina, base_url, medida):
    cred = credenciais()
    if "demo" not in cred:
        pytest.skip("credenciais do inquilino demo ausentes (tests/credenciais.txt ou PLAT_CREDENCIAIS_ARQUIVO)")
    login, senha = cred["demo"]
    s = sufixo()
    tela = TelaMapa(pagina, base_url)
    tela.entrar("demo", login, senha)

    camadas = [
        _criar(
            tela,
            "/api/itens",
            {
                "tipo": "camada_vetorial",
                "titulo": f"zt camada {n} {s}",
                "dados": {
                    "schema": "plat_trabalho",
                    "tabela": "zt_inexistente",
                    "geometria": "Point",
                    "srid": 4326,
                    "campos": [{"nome": "a", "tipo": "text"}],
                    "fonte": "hospedada",
                },
            },
        )
        for n in (1, 2, 3)
    ]
    a, b, c = CAMADAS_ULID
    mapa = _criar(
        tela,
        "/api/mapas",
        {
            "titulo": f"zt mapa e2e {s}",
            "dados": {
                "esquema_versao": 1,
                "corpo": {
                    "camadas": [{"id": u, "ref": cam["id"]} for u, cam in zip(CAMADAS_ULID, camadas, strict=True)]
                },
            },
        },
    )
    try:
        tela.ir(f"/mapa?id={mapa['id']}", "pagina_pronta_ms_mapa_documento")
        pagina.wait_for_selector("#camadas-lista li", timeout=20000)
        # o painel lista do topo para o fundo: o documento tem [a, b, c] (fundo -> topo), a tela mostra [c, b, a]
        assert _ordem_na_tela(pagina) == [c, b, a]
        # sem servidor de tiles nesta máquina, e a tela diz isso em vez de fingir desenho
        assert pagina.locator("#camadas-lista li .camada-selo").count() == 3
        # o título da camada aparece na linha (é o título do ITEM do catálogo, resolvido pelo servidor)
        titulos = pagina.eval_on_selector_all("#camadas-lista li .camada-titulo", "els => els.map(e => e.textContent)")
        assert titulos == [f"zt camada {n} {s}" for n in (3, 2, 1)], titulos

        pagina.locator(f'#camadas-lista li[data-id="{c}"]').drag_to(
            pagina.locator(f'#camadas-lista li[data-id="{a}"]')
        )
        depois_do_arrasto = _ordem_na_tela(pagina)
        assert depois_do_arrasto != [c, b, a], "o arrasto não mudou a ordem na tela"

        pagina.click("#salvar-mapa")
        pagina.wait_for_function("() => !document.getElementById('salvar-mapa').dataset.sujo", timeout=10000)
        captura = tela.capturar("painel_camadas")

        pagina.reload()
        pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
        pagina.wait_for_selector("#camadas-lista li", timeout=20000)
        assert _ordem_na_tela(pagina) == depois_do_arrasto, "a ordem recarregada não é a que foi salva"

        # e o documento no banco (lido pela API, sem passar pela tela) tem a mesma ordem invertida
        doc = tela.api("GET", f"/api/mapas/{mapa['id']}").json()["dados"]
        assert [x["id"] for x in doc["corpo"]["camadas"]] == list(reversed(depois_do_arrasto))
        assert captura.stat().st_size > 5000
        tela.verificar()
        medida(ITEM)(
            "ordem_apos_recarga_igual_a_salva",
            1,
            "booleano",
            "venv/bin/pytest tests/e2e/test_mapa_documento.py --base-url https://127.0.0.1:8172",
        )
    finally:
        tela.api("DELETE", f"/api/itens/{mapa['id']}")
        for cam in camadas:
            tela.api("DELETE", f"/api/itens/{cam['id']}")
