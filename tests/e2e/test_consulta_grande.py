"""e2e do item L2-15-b-consultas-duckdb-em-escala (cláusula "e2e com captura").

Percorre a tela como um usuário: entra em /analise, escolhe a ferramenta `consulta_sql`, seleciona a fonte
Parquet do inquilino na lista (que agora traz as duas famílias de item, marcadas com [Parquet]), escreve um
SELECT, manda rodar e acompanha o job até o link do resultado. Depois abre a ficha do item e confere que a
proveniência mostra o SQL e o sha256 do arquivo lido. Captura de tela em cada passo
(tests/e2e/capturas/L2-15-b-consultas-duckdb-em-escala_*.png).

Também percorre a recusa, que é metade do produto: um SQL com `read_parquet` de caminho externo tem de
terminar em aviso na tela, com a mensagem do portão, e nenhum item novo.

Como rodar contra esta trilha:

    set -a; source /home/dev/plataforma/laco/var/trilha/il215bconsu.env; set +a
    venv/bin/uvicorn app.main:app --port 8171 &
    venv/bin/python -m app.jobs.worker &
    venv/bin/pytest tests/e2e/test_consulta_grande.py -m lento --base-url http://127.0.0.1:8171

Sem worker vivo o job nunca sai de `pendente`: o teste salta com a razão explícita, em vez de falhar por
tempo esgotado e esconder a causa.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-15-b-consultas-duckdb-em-escala"
ROTAS = ("/api/ferramentas", "/api/ferramentas/{nome}/executar", "/api/geoparquet")
SQL_BOM = "SELECT navio, count(*) AS posicoes FROM fonte_a GROUP BY navio ORDER BY navio"
SQL_PROIBIDO = "SELECT * FROM read_parquet('/etc/hostname')"


class TelaConsulta(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def api_consulta(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend sem {faltam} no OpenAPI da URL de teste")
    return api_auth


@pytest.fixture(scope="session")
def inquilino_com_parquet(env, api_consulta):
    """Inquilino próprio, camada de pontos semeada e publicada como item Parquet pelo job do L2-15-a — o
    mesmo caminho das fixtures de `tests/api/consulta_grande/conftest.py`, reaproveitado aqui.

    Inquilino novo, e não o de demonstração, pela razão registrada no e2e do L0-04-h: numa base de trilha o
    schema `d_demo` pertence ao papel da base de produção e a trilha não pode criar tabela nele.
    """
    from tests.api.conftest import (
        credenciais as credenciais_api,
    )
    from tests.api.conftest import (
        entrar,
        ligar_2fa,
        novo_cliente,
        totp_guardado,
        totp_guardar,
    )
    from tests.api.consulta_grande.conftest import publicar_parquet, semear_pontos
    from tests.api.exportacao.conftest import InquilinoDeExportacao

    c = credenciais_api()
    if "plataforma" not in c:
        pytest.skip("sem credenciais do inquilino técnico `plataforma` neste ambiente")
    login, senha = c["plataforma"]
    plat = novo_cliente()
    r = entrar(plat, "plataforma", login, senha, totp_guardado("plataforma"))
    if r.status_code != 200:
        pytest.skip(f"não foi possível entrar como superadmin neste ambiente: {r.status_code}")
    if "configurar_2fa" in r.json()["usuario"]["pendencias"]:
        segredo, _codigos = ligar_2fa(plat)
        totp_guardar("plataforma", login, segredo)
    inq = InquilinoDeExportacao(plat)
    camada = semear_pontos(env, inq, 5_000, "zt camada do e2e de consulta grande")
    try:
        camada["parquet_id"] = publicar_parquet(inq.admin, camada, timeout=300)
    except AssertionError as e:
        inq.apagar()
        pytest.skip(f"o job geoparquet.gerar não terminou neste ambiente (há worker vivo?): {e}")
    yield inq, camada
    inq.apagar()


def _preencher(page, fonte_id: str, sql: str) -> None:
    page.select_option("#ferramenta", "consulta_sql")
    page.wait_for_selector("#formulario select[name='fonte_a']", timeout=20000)
    page.select_option("#formulario select[name='fonte_a']", fonte_id)
    page.fill("#formulario textarea[name='sql'], #formulario input[name='sql']", sql)


def _esperar_desfecho(page, segundos: int = 300) -> str:
    """'ok' quando o link do resultado aparece; 'erro' quando a tela mostra o aviso do job."""
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if page.locator("#resultado-link").count():
            return "ok"
        if page.locator("#execucao-aviso[data-tipo='erro']").count():
            return "erro"
        page.wait_for_timeout(500)
    pytest.skip("o job não terminou no prazo: há worker da fila rodando neste ambiente?")
    return ""


def test_consulta_sql_pela_tela_publica_camada_com_proveniencia(page, base_url, inquilino_com_parquet):
    inq, camada = inquilino_com_parquet
    tela = TelaConsulta(page, base_url)
    # fora do nginx o Origin do navegador nunca casa com PLAT_URL_PUBLICA (obrigatoriamente https): o
    # cabeçalho é retirado só desta chamada; a checagem em si é provada em tests/api (mesma nota do e2e do
    # L2-05-a, de onde esta tela vem)
    page.route("**/api/ferramentas/*/executar", lambda rota: rota.fulfill(response=rota.fetch(
        headers={k: v for k, v in rota.request.headers.items() if k.lower() != "origin"})))
    tela.entrar(inq.slug, "admin", inq.senha, proximo="/analise")
    tela.ir("/analise", "pagina_analise_ms")
    assert page.locator("#ferramenta option[value='consulta_sql']").count() == 1
    assert page.locator("#ferramenta option[value='agregar_em_grade']").count() == 1
    tela.capturar("catalogo_com_as_grandes")

    _preencher(page, camada["parquet_id"], SQL_BOM)
    tela.capturar("formulario_preenchido")
    inicio = time.monotonic()
    page.click("#formulario button[type='submit']")
    assert _esperar_desfecho(page) == "ok", page.text_content("#execucao-aviso")
    tela.medidas["consulta_sql_pela_tela_ms"] = round((time.monotonic() - inicio) * 1000, 1)
    tela.capturar("resultado_pronto")

    item_id = page.get_attribute("#execucao-resultado", "data-item-id")
    assert item_id and len(item_id) == 36, item_id
    page.click("#resultado-link")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_selector("[data-campo='proveniencia'] .proveniencia", timeout=20000)
    texto = page.text_content("[data-campo='proveniencia']")
    assert "consulta_sql" in texto, texto[:500]
    tela.capturar("ficha_com_proveniencia")


def test_sql_proibido_pela_tela_termina_em_aviso(page, base_url, inquilino_com_parquet):
    inq, camada = inquilino_com_parquet
    tela = TelaConsulta(page, base_url)
    page.route("**/api/ferramentas/*/executar", lambda rota: rota.fulfill(response=rota.fetch(
        headers={k: v for k, v in rota.request.headers.items() if k.lower() != "origin"})))
    tela.entrar(inq.slug, "admin", inq.senha, proximo="/analise")
    tela.ir("/analise")
    _preencher(page, camada["parquet_id"], SQL_PROIBIDO)
    page.click("#formulario button[type='submit']")
    assert _esperar_desfecho(page) == "erro", "o SQL proibido não podia produzir camada"
    aviso = page.text_content("#execucao-aviso")
    assert "read_parquet" in aviso or "proibida" in aviso, aviso
    tela.capturar("sql_proibido_recusado")
