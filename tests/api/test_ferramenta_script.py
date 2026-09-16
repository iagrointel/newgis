"""Ferramenta de script (item L2-16-c-script-vira-ferramenta) — cláusula por cláusula do portão:

 1. exemplo `buffer_por_campo` publicado (POST /api/ferramentas/script), aparece no catálogo
    (GET /api/itens?tipo=ferramenta_script) e o formulário sai do cabeçalho (GET /formulario);
    a tela /ferramentas?item= renderiza o formulário no navegador de verdade (e2e com captura
    do playwright contra o servidor desta suíte);
 2. executa como job (`ferramentas.executar_script`) DENTRO do contêiner do inquilino (o mesmo
    do L2-16-b, levantado pelo worker) e a saída é item `ferramenta_resultado` com a
    procedência contendo o sha256 do script e a versão executada;
 3. parâmetro fora do tipo/da faixa/desconhecido/entrada inexistente = 422 ANTES de executar
    (nenhum job é criado);
 4. script que tenta acessar a rede falha (isolamento do L2-16-b: rede interna sem saída);
 5. chamada pelo GPServer submitJob — PENDENTE (dependência L2-05-a, wt/cx205 não é ancestral;
    registrada no handoff, o vocabulário GP já é o mesmo para colar depois);
 6. versão nova publicada depois não muda execução passada: a execução congelou versão+sha256
    no pedido do job e a procedência do item antigo continua apontando a versão 1.

Refutações do adversário (rodadas pela porta da frente, publicar + executar): ler /etc/shadow,
abrir socket para fora, rodar 24 h (morre no teto declarado no pedido), gravar camada com o
token de leitura (403) e executar com sha256 adulterado (o worker recusa).

A suíte sobe a app num uvicorn em porta efêmera e um worker da fila (mesmo padrão da suíte do
notebook); o contêiner é levantado PELO WORKER, nunca pelo processo de teste.
"""

import hashlib
import json
import mimetypes
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("PLAT_AMBIENTE", "dev")

from tests.api.conftest import credenciais, totp_guardado  # noqa: E402

SLUG = "demo"
SLUG_OUTRO = "demo2"
NOME = f"plat-nb-{SLUG}"
EXEMPLO = ROOT / "examples" / "ferramentas" / "buffer_por_campo.py"
TETO_JOB_S = 300.0  # teto de espera por job (o teto do script é declarado no pedido)


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _login_http(base: str, slug: str, login: str, senha: str, segredo_totp: str | None = None):
    """Sessão HTTP com cookie pela rota pública (com 2FA quando ligado) — mesma da suíte do notebook."""
    s = requests.Session()
    r = s.post(f"{base}/api/login", json={"inquilino": slug, "login": login, "senha": senha}, timeout=15)
    if r.status_code == 200 and r.json().get("exige_2fa"):
        from app.auth import totp

        assert segredo_totp, "usuário exige 2FA e o segredo não é conhecido"
        desafio = r.json()["desafio"]

        def _tentar():
            return s.post(f"{base}/api/login/2fa",
                          json={"desafio": desafio, "codigo": totp.codigo(segredo_totp)}, timeout=15)

        r = _tentar()
        if r.status_code != 200:
            time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
            r = _tentar()
    r.raise_for_status()
    return s


def _sessao(base: str, slug: str):
    creds = credenciais()
    assert slug in creds, f"trilha sem credencial do admin {slug} (PLAT_CREDENCIAIS_ARQUIVO)"
    login, senha = creds[slug]
    return _login_http(base, slug, login, senha, totp_guardado(slug))


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    """A app inteira em subprocesso (uvicorn em porta efêmera); /saude decide quando está de pé."""
    from tests.api.test_notebooks import _limpar_gateway

    _limpar_gateway()
    porta = porta_livre()
    ambiente = dict(os.environ)
    ambiente["PYTHONNOUSERSITE"] = "1"
    registro = tmp_path_factory.mktemp("fe-servidor") / "uvicorn.log"
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                             "--port", str(porta), "--log-level", "warning"], cwd=ROOT, env=ambiente,
                            stdout=open(registro, "w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{base}/saude", timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("servidor da ferramenta morreu na subida")
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("servidor da ferramenta não respondeu /saude em 30 s")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def worker(servidor):
    """Worker da fila em subprocesso (o job ferramentas.executar_script roda nele, com docker CLI)."""
    porta = porta_livre()
    ambiente = dict(os.environ)
    ambiente.update({"PYTHONNOUSERSITE": "1", "PLAT_WORKER_NOME": f"fe-{os.getpid()}",
                     "PLAT_WORKER_PROCESSOS": "1", "PLAT_WORKER_URL": f"http://127.0.0.1:{porta}"})
    proc = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], cwd=ROOT, env=ambiente,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("worker da ferramenta morreu na subida")
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("worker da ferramenta não respondeu em 10 s")
    yield
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def demo(servidor):
    return _sessao(servidor, SLUG)


@pytest.fixture(scope="session")
def demo2(servidor):
    return _sessao(servidor, SLUG_OUTRO)


def _docker(*args: str, timeout: int = 90, entrada: bytes | None = None):
    return subprocess.run(["docker", *args], capture_output=True, input=entrada, timeout=timeout)


@pytest.fixture(scope="session")
def _limpeza_final(request):
    """Encerra contêiner e gateway ao fim da suíte (recursos de máquina não podem ficar de pé)."""
    def _limpar():
        _docker("rm", "-f", NOME)
        _docker("volume", "rm", f"plat-nb-{SLUG}-trabalho")
        from tests.api.test_notebooks import _limpar_gateway
        _limpar_gateway()
    request.addfinalizer(_limpar)


def _publicar(base, sessao, codigo: str, comentario: str | None = None) -> dict:
    corpo = {"codigo": codigo, "tags": ["prova"]}
    if comentario:
        corpo["comentario"] = comentario
    return sessao.post(f"{base}/api/ferramentas/script", json=corpo, timeout=30)


def _script_rede() -> str:
    return (
        '"""\nnome: prova_rede_fora\ntitulo: Prova de rede\n'
        'parametros:\n  - nome: alvo\n    tipo: texto\n    padrao: "1.1.1.1"\n'
        'saidas:\n  - nome: estado\n    tipo: texto\n"""\n'
        'import socket\nfrom plat_geo import saidas\n'
        's = socket.create_connection(("1.1.1.1", 443), timeout=4.0)\n'
        's.close()\nsaidas.gravar("estado", "conectou")\n'
    )


def _script_etc() -> str:
    return (
        '"""\nnome: prova_etc_shadow\ntitulo: Prova de arquivo do sistema\n'
        'parametros: []\nsaidas:\n  - nome: lido\n    tipo: texto\n"""\n'
        'from plat_geo import saidas\n'
        'with open("/etc/shadow", encoding="utf-8") as arq:\n'
        '    conteudo = arq.read()\n'
        'saidas.gravar("lido", f"{len(conteudo)} bytes")\n'
    )


def _script_laco() -> str:
    return (
        '"""\nnome: prova_laco_infinito\ntitulo: Prova de laço\n'
        'parametros: []\nsaidas:\n  - nome: fim\n    tipo: texto\n"""\n'
        'import time\nwhile True:\n    time.sleep(1)\n'
    )


def _script_escrita() -> str:
    return (
        '"""\nnome: prova_escrita_sem_permissao\ntitulo: Prova de escrita\n'
        'parametros: []\nsaidas:\n  - nome: criado\n    tipo: texto\n"""\n'
        'from plat_geo import saidas\nfrom plat_geo.cliente import Plataforma\n'
        'pla = Plataforma.do_ambiente()\n'
        'novo = pla.catalogo.criar(tipo="ferramenta_resultado", titulo="escrito de dentro",\n'
        '                          dados={"ferramenta": "prova", "parametros": {}, "resultado": {}})\n'
        'saidas.gravar("criado", novo["id"])\n'
    )


def _esperar_job(base, sessao, job_id: str, teto_s: float = TETO_JOB_S) -> dict:
    inicio = time.monotonic()
    while time.monotonic() - inicio < teto_s:
        r = sessao.get(f"{base}/api/jobs/{job_id}", timeout=15)
        if r.status_code == 200:
            j = r.json()
            if j.get("estado") in ("concluido", "falhou", "cancelado"):
                return j
        time.sleep(2.0)
    pytest.fail(f"job {job_id} não terminou em {teto_s:.0f} s")


def _total_execucoes(base, sessao, ferramenta_id: str) -> int:
    r = sessao.get(f"{base}/api/ferramentas/script/{ferramenta_id}/execucoes", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["total"]


# ============================================================ cláusula 1: publicar e catálogo
def _servir_estatico(contexto, base_url: str) -> None:
    """Em produção o nginx serve web/ em /static direto do disco (ADR 0001 seção 4.3) e a API
    nunca serve estático. O navegador do teste aponta para o uvicorn da suíte, então o teste
    faz o papel do nginx: entrega os MESMOS arquivos de web/, sem montar rota nenhuma na app."""
    raiz = ROOT / "web"

    def rotear(rota):
        caminho = rota.request.url.split("?", 1)[0][len(base_url):].removeprefix("/static/")
        arquivo = (raiz / caminho).resolve()
        if arquivo.is_file() and str(arquivo).startswith(str(raiz)):
            tipo = mimetypes.guess_type(str(arquivo))[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo in ("application/javascript", "image/svg+xml"):
                tipo += "; charset=utf-8"
            rota.fulfill(path=str(arquivo), content_type=tipo)
        else:
            rota.fulfill(status=404, content_type="text/plain", body="")

    contexto.route(f"{base_url}/static/**", rotear)


@pytest.fixture(scope="session")
def exemplo(servidor, demo, _limpeza_final):
    """O exemplo da casa publicado pela porta da frente; apagado ao fim da suíte."""
    codigo = EXEMPLO.read_text(encoding="utf-8")
    r = _publicar(servidor, demo, codigo)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["tipo"] == "ferramenta_script"
    assert item["titulo"] == "Buffer por campo"
    assert item["dados"]["versao"] == 1
    assert item["dados"]["sha256"] == hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    assert item["dados"]["cabecalho"]["nome"] == "buffer_por_campo"
    yield item
    try:
        demo.delete(f"{servidor}/api/itens/{item['id']}", timeout=15)
    except Exception:
        pass


def test_clausula1_exemplo_aparece_no_catalogo(servidor, demo, exemplo):
    r = demo.get(f"{servidor}/api/itens", params={"tipo": "ferramenta_script"}, timeout=15)
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["itens"]]
    assert str(exemplo["id"]) in ids, "ferramenta publicada não aparece no catálogo"
    # e o item do catálogo carrega o corpo (GET direto)
    r = demo.get(f"{servidor}/api/itens/{exemplo['id']}", timeout=15)
    assert r.status_code == 200 and r.json()["dados"]["codigo"] == EXEMPLO.read_text(encoding="utf-8")


def test_clausula1_formulario_gerado_do_cabecalho(servidor, demo, exemplo):
    r = demo.get(f"{servidor}/api/ferramentas/script/{exemplo['id']}/formulario", timeout=15)
    assert r.status_code == 200, r.text
    ficha = r.json()
    assert ficha["nome"] == "buffer_por_campo"
    assert ficha["titulo_item"] == "Buffer por campo"
    assert ficha["versao"] == 1 and ficha["sha256"] == exemplo["dados"]["sha256"]
    por_nome = {p["nome"]: p for p in ficha["parametros"]}
    assert set(por_nome) == {"entrada", "distancia_m", "srid"}
    assert por_nome["entrada"]["tipo_gp"] == "GPFeatureRecordSetLayer"
    assert por_nome["entrada"]["obrigatorio"] is True
    assert por_nome["distancia_m"]["esquema"]["minimum"] == 0
    assert por_nome["distancia_m"]["esquema"]["maximum"] == 100000
    assert por_nome["srid"]["padrao"] == 31983
    assert [s["nome"] for s in ficha["saidas"]] == ["buffer", "resumo"]
    # o formulário não vaza o corpo do script
    assert "shapely" not in json.dumps(ficha)


def test_clausula1_e2e_captura_da_tela(servidor, demo, exemplo):
    """A tela /ferramentas?item= renderiza o formulário no navegador de verdade (captura gravada)."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    capturas = ROOT / "tests" / "medidas" / "capturas"
    capturas.mkdir(parents=True, exist_ok=True)
    alvo = capturas / "L2-16-c_formulario_ferramenta.png"
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(locale="pt-BR", viewport={"width": 1280, "height": 800})
        # sessão do demo injetada como cookie (o mesmo caminho do login pela tela, sem 2FA na tela)
        cookies = [{"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": "/"}
                   for c in demo.cookies]
        contexto.add_cookies(cookies)
        _servir_estatico(contexto, servidor)
        pagina = contexto.new_page()
        erros_console: list[str] = []
        pagina.on("pageerror", lambda e: erros_console.append(str(e)))
        pagina.goto(f"{servidor}/ferramentas?item={exemplo['id']}", wait_until="domcontentloaded")
        pagina.wait_for_selector("input#f-entrada", timeout=20000)
        assert pagina.locator("h1").inner_text().strip() == "Buffer por campo"
        assert pagina.locator("#f-distancia_m").input_value() == "100"
        assert pagina.locator("#f-distancia_m").get_attribute("min") == "0"
        assert pagina.locator("#f-distancia_m").get_attribute("max") == "100000"
        assert pagina.locator("#f-srid").input_value() == "31983"
        assert pagina.locator("button#executar").count() == 1
        assert "sha256" in pagina.locator("#ferramenta-cartao").inner_text()
        assert "análise / beta privado" in pagina.content()
        pagina.screenshot(path=str(alvo), full_page=True)
        navegador.close()
    assert not erros_console, f"erros de página: {erros_console}"
    assert alvo.is_file() and alvo.stat().st_size > 10_000, "captura vazia"


# ============================================================ cláusula 3: 422 antes de executar
def test_clausula3_parametro_fora_do_tipo_e_422_sem_job(servidor, demo, exemplo):
    id_f = str(exemplo["id"])
    antes = _total_execucoes(servidor, demo, id_f)
    entrada_alheia = "11111111-1111-1111-1111-111111111111"  # uuid válido que não é um item daqui
    recusas = [
        ({"entrada": entrada_alheia, "distancia_m": "muito"}, "distancia_m"),
        ({"entrada": entrada_alheia, "distancia_m": -1}, "distancia_m"),
        ({"entrada": entrada_alheia, "distancia_m": 100001}, "distancia_m"),
        ({"entrada": entrada_alheia, "srid": 31983.5}, "srid"),
        ({"entrada": entrada_alheia, "nao_declarado": 1}, "nao_declarado"),
        ({"entrada": "nao-e-uuid"}, "entrada"),
        ({"entrada": entrada_alheia}, "entrada"),  # uuid válido, item de outro inquilino
    ]
    for parametros, campo in recusas:
        r = demo.post(f"{servidor}/api/ferramentas/script/{id_f}/executar",
                      json={"parametros": parametros}, timeout=15)
        assert r.status_code == 422, (parametros, r.status_code, r.text)
        detalhe = r.json()["detalhe"]
        assert any(d["campo"] == campo for d in detalhe), (parametros, detalhe)
    depois = _total_execucoes(servidor, demo, id_f)
    assert antes == depois == 0, "recusa de parâmetro enfileirou job"


def test_clausula3_cabecalho_invalido_nao_publica_nada(servidor, demo):
    r = _publicar(servidor, demo, "def sem_cabecalho():\n    return 1\n")
    assert r.status_code == 422
    corpo = r.json()
    assert corpo["erro"] == "cabecalho_invalido"


# ============================================================ cláusula 2: execução no contêiner
@pytest.fixture(scope="session")
def entrada_geo(servidor, demo, _limpeza_final):
    """Item de entrada com GeoJSON de 2 'campos' (polígonos) nos dados — o exemplo procura em
    dados.resultado.* (o tipo `ferramenta_resultado` aceita esse formato)."""
    campos = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"campo": "A"},
             "geometry": {"type": "Polygon", "coordinates": [[[-46.6, -23.5], [-46.59, -23.5],
                                                              [-46.59, -23.49], [-46.6, -23.49],
                                                              [-46.6, -23.5]]]}},
            {"type": "Feature", "properties": {"campo": "B"},
             "geometry": {"type": "Polygon", "coordinates": [[[-46.58, -23.52], [-46.57, -23.52],
                                                              [-46.57, -23.51], [-46.58, -23.51],
                                                              [-46.58, -23.52]]]}},
        ],
    }
    corpo = {"tipo": "ferramenta_resultado", "titulo": "zt-ferramenta-entrada",
             "dados": {"ferramenta": "prova", "parametros": {}, "resultado": {"campos": campos}}}
    r = demo.post(f"{servidor}/api/itens", json=corpo, timeout=15)
    assert r.status_code == 201, r.text
    item = r.json()
    yield item
    try:
        demo.delete(f"{servidor}/api/itens/{item['id']}", timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="session")
def execucao_1(servidor, demo, worker, exemplo, entrada_geo):
    """Execução da versão 1 pela porta da frente; devolve (job, item de resultado)."""
    r = demo.post(f"{servidor}/api/ferramentas/script/{exemplo['id']}/executar",
                  json={"parametros": {"entrada": str(entrada_geo["id"]), "distancia_m": 250}}, timeout=15)
    assert r.status_code == 202, r.text
    saida = r.json()
    assert saida["versao"] == 1
    job = _esperar_job(servidor, demo, saida["job_id"])
    assert job["estado"] == "concluido", (job.get("erro"), job)
    item_id = job["resultado"]["item_id"]
    r = demo.get(f"{servidor}/api/itens/{item_id}", timeout=15)
    assert r.status_code == 200, r.text
    return job, r.json()


def test_clausula2_executa_no_conteiner_e_item_com_procedencia(servidor, demo, exemplo, execucao_1,
                                                               entrada_geo):
    job, item = execucao_1
    assert job["tipo"] == "ferramentas.executar_script"
    assert item["tipo"] == "ferramenta_resultado"
    # o contêiner do inquilino executou de verdade (é o mesmo nome do L2-16-b)
    r = _docker("inspect", "-f", "{{.State.Running}}", NOME)
    assert r.returncode == 0 and r.stdout.decode().strip() == "true", "resultado sem contêiner de execução"
    dados = item["dados"]
    proc = dados["procedencia"]
    assert proc["origem"] == "script"
    assert proc["ferramenta_id"] == str(exemplo["id"])
    assert proc["versao"] == 1
    assert proc["sha256_script"] == exemplo["dados"]["sha256"] == hashlib.sha256(
        EXEMPLO.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    # a saída declarada no cabeçalho virou conteúdo do item
    buffer = dados["resultado"]["buffer"]
    assert buffer["type"] == "FeatureCollection" and len(buffer["features"]) == 2
    for feicao, _campo in zip(buffer["features"], ("A", "B"), strict=True):
        assert feicao["properties"]["area_m2"] > 0, "buffer de 250 m com área nula"
    resumo = json.loads(dados["resultado"]["resumo"])
    assert resumo["campos"] == 2 and resumo["distancia_m"] == 250.0
    assert dados["parametros"]["entrada"] == str(entrada_geo["id"])
    assert dados["parametros"]["distancia_m"] == 250.0  # padrão aplicado e congelado no item


def test_clausula2_log_de_execucao_visivel(servidor, demo, exemplo, execucao_1):
    r = demo.get(f"{servidor}/api/ferramentas/script/{exemplo['id']}/execucoes", timeout=15)
    assert r.status_code == 200, r.text
    log = r.json()
    assert log["total"] >= 1
    linha = next(e for e in log["execucoes"] if e["job_id"] == str(execucao_1[0]["id"]))
    assert linha["estado"] == "concluido"
    assert linha["versao"] == 1
    assert linha["sha256"] == exemplo["dados"]["sha256"]


# ============================================================ refutações do adversário
def test_refuta_rede_fora(servidor, demo, worker, _limpeza_final):
    r = _publicar(servidor, demo, _script_rede())
    assert r.status_code == 201, r.text
    ferramenta = r.json()
    r = demo.post(f"{servidor}/api/ferramentas/script/{ferramenta['id']}/executar",
                  json={"parametros": {}, "timeout_s": 60}, timeout=15)
    assert r.status_code == 202, r.text
    job = _esperar_job(servidor, demo, r.json()["job_id"])
    assert job["estado"] == "falhou", job
    assert "create_connection" in (job.get("erro") or "") or "connect" in (job.get("erro") or ""), \
        f"falha não é a tentativa de rede: {job.get('erro')}"
    demo.delete(f"{servidor}/api/itens/{ferramenta['id']}", timeout=15)


def test_refuta_leitura_de_etc(servidor, demo, worker, _limpeza_final):
    r = _publicar(servidor, demo, _script_etc())
    assert r.status_code == 201, r.text
    ferramenta = r.json()
    r = demo.post(f"{servidor}/api/ferramentas/script/{ferramenta['id']}/executar",
                  json={"parametros": {}, "timeout_s": 60}, timeout=15)
    assert r.status_code == 202, r.text
    job = _esperar_job(servidor, demo, r.json()["job_id"])
    assert job["estado"] == "falhou", job
    assert "Permission" in (job.get("erro") or "") or "permiss" in (job.get("erro") or "").lower(), \
        f"leitura de /etc/shadow não barrou: {job.get('erro')}"
    demo.delete(f"{servidor}/api/itens/{ferramenta['id']}", timeout=15)


def test_refuta_laco_infinito_no_teto(servidor, demo, worker, _limpeza_final):
    r = _publicar(servidor, demo, _script_laco())
    assert r.status_code == 201, r.text
    ferramenta = r.json()
    r = demo.post(f"{servidor}/api/ferramentas/script/{ferramenta['id']}/executar",
                  json={"parametros": {}, "timeout_s": 6}, timeout=15)
    assert r.status_code == 202, r.text
    job = _esperar_job(servidor, demo, r.json()["job_id"])
    assert job["estado"] == "falhou", job
    assert "6 s" in (job.get("erro") or ""), f"teto de 6 s não foi o motivo: {job.get('erro')}"
    demo.delete(f"{servidor}/api/itens/{ferramenta['id']}", timeout=15)


def test_refuta_escrita_sem_permissao(servidor, demo, worker, _limpeza_final):
    r = demo.get(f"{servidor}/api/itens", params={"tipo": "ferramenta_resultado", "limite": 200},
                 timeout=15)
    assert r.status_code == 200, r.text
    antes = {i["id"] for i in r.json()["itens"]}
    r = _publicar(servidor, demo, _script_escrita())
    assert r.status_code == 201, r.text
    ferramenta = r.json()
    r = demo.post(f"{servidor}/api/ferramentas/script/{ferramenta['id']}/executar",
                  json={"parametros": {}, "timeout_s": 60}, timeout=15)
    assert r.status_code == 202, r.text
    job = _esperar_job(servidor, demo, r.json()["job_id"])
    assert job["estado"] == "falhou", job
    assert "403" in (job.get("erro") or "") or "permiss" in (job.get("erro") or "").lower(), \
        f"escrita com token de leitura não barrou: {job.get('erro')}"
    r = demo.get(f"{servidor}/api/itens", params={"tipo": "ferramenta_resultado", "limite": 200},
                 timeout=15)
    depois = {i["id"] for i in r.json()["itens"]}
    assert not (depois - antes), "script sem permissão deixou item gravado"
    demo.delete(f"{servidor}/api/itens/{ferramenta['id']}", timeout=15)


def test_refuta_sha256_adulterado(servidor, demo, worker, exemplo):
    """Job montado à mão com sha256 que não é o da versão: o worker recusa rodar (procedência
    duvidosa nunca executa) — a metade forte da cláusula 6."""
    r = demo.post(f"{servidor}/api/jobs",
                  json={"tipo": "ferramentas.executar_script",
                        "parametros": {"ferramenta_id": str(exemplo["id"]), "versao": 1,
                                       "sha256": "0" * 64, "parametros": {},
                                       "timeout_s": 60}}, timeout=15)
    assert r.status_code in (201, 202), r.text
    job = _esperar_job(servidor, demo, r.json()["id"])
    assert job["estado"] == "falhou", job
    assert "sha256" in (job.get("erro") or ""), job.get("erro")


# ============================================================ cláusula 6: versão não reescreve passado
def test_clausula6_versao_nova_nao_muda_execucao_passada(servidor, demo, worker, exemplo,
                                                         entrada_geo, execucao_1):
    id_f = str(exemplo["id"])
    job1, item1 = execucao_1
    sha_v1 = exemplo["dados"]["sha256"]
    codigo_v2 = EXEMPLO.read_text(encoding="utf-8").replace("titulo: Buffer por campo",
                                                            "titulo: Buffer por campo (v2)")
    assert codigo_v2 != EXEMPLO.read_text(encoding="utf-8")
    r = demo.post(f"{servidor}/api/ferramentas/script/{id_f}/versao",
                  json={"codigo": codigo_v2, "comentario": "prova da cláusula 6"}, timeout=30)
    assert r.status_code == 200, r.text
    versao2 = r.json()
    sha_v2 = versao2["dados"]["sha256"]
    assert versao2["dados"]["versao"] == 2 and sha_v2 != sha_v1
    # o item da execução PASSADA continua com a procedência da versão 1
    r = demo.get(f"{servidor}/api/itens/{item1['id']}", timeout=15)
    proc1 = r.json()["dados"]["procedencia"]
    assert proc1["versao"] == 1 and proc1["sha256_script"] == sha_v1
    # o log da execução passada continua apontando a versão 1 (mesmo com o item em v2)
    r = demo.get(f"{servidor}/api/ferramentas/script/{id_f}/execucoes", timeout=15)
    linha = next(e for e in r.json()["execucoes"] if e["job_id"] == str(job1["id"]))
    assert linha["versao"] == 1 and linha["sha256"] == sha_v1
    # execução NOVA congela a versão 2 e a procedência dela aponta a versão 2
    r = demo.post(f"{servidor}/api/ferramentas/script/{id_f}/executar",
                  json={"parametros": {"entrada": str(entrada_geo["id"])}}, timeout=15)
    assert r.status_code == 202, r.text
    assert r.json()["versao"] == 2
    job2 = _esperar_job(servidor, demo, r.json()["job_id"])
    assert job2["estado"] == "concluido", job2.get("erro")
    r = demo.get(f"{servidor}/api/itens/{job2['resultado']['item_id']}", timeout=15)
    proc2 = r.json()["dados"]["procedencia"]
    assert proc2["versao"] == 2 and proc2["sha256_script"] == sha_v2


# ============================================================ outro inquilino
def test_outro_inquilino_nao_ve_nem_executa(servidor, demo, demo2, exemplo):
    id_f = str(exemplo["id"])
    assert demo2.get(f"{servidor}/api/ferramentas/script/{id_f}/formulario", timeout=15).status_code == 404
    r = demo2.post(f"{servidor}/api/ferramentas/script/{id_f}/executar",
                   json={"parametros": {}}, timeout=15)
    assert r.status_code == 404, r.text
    assert demo2.get(f"{servidor}/api/itens/{id_f}", timeout=15).status_code == 404


# ============================================================ cláusula 5: GPServer (pendente)
@pytest.mark.xfail(strict=False, reason="PENDENTE: depende da junção do L2-05-a (wt/cx205, "
                                        "não ancestral); registrado no handoff")
def test_clausula5_gpserver_pendente():
    """Chamada pelo GPServer submitJob: PENDENTE de propósito. O serviço GP do L2-05-a vive no
    worktree wt/cx205, que NÃO é ancestral deste ramo (fila é só fast-forward): colar aqui antes
    da junção seria reimplementar por cima. O vocabulário de tipos GP já é o mesmo
    (GPFeatureRecordSetLayer, GPString, GPDouble, GPLong, GPBoolean), documentado no handoff."""
    pytest.fail("cláusula 5 (GPServer submitJob) é PENDENTE declarada: depende da junção do "
                "L2-05-a (wt/cx205)")
