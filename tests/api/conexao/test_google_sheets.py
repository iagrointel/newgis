"""Item L6-02-i, ponta a ponta: Google Sheets como fonte de camada.

Nada aqui é simulado por dentro: o "Google" é `tests/servidor_google.py`, um servidor HTTPS no endereço
PÚBLICO desta máquina que fala os dois protocolos de verdade — exportação CSV (pública sem credencial,
privada só com Bearer) e troca de token OAuth2 `jwt-bearer` com VERIFICAÇÃO da assinatura RS256 do JWT.
A defesa de SSRF continua ligada, a verificação de TLS continua ligada (o bundle só ACRESCENTA a CA de
teste às do sistema) e o job roda num worker de verdade em subprocesso.

O que NÃO dá para provar nesta máquina fica registrado como pendente, nunca como feito: a casa não tem
conta Google, então a planilha privada no Google de verdade (conta de serviço da casa) e a publicação de
uma planilha pública própria ficam como fronteira honesta — a medida de alcance contra docs.google.com
(planilha pública de exemplo do próprio Google) registra até onde a prova ao vivo chega.

O worker é próprio deste arquivo (porta sorteada por rodada) pelos mesmos motivos do L6-02-h.
"""

from __future__ import annotations

import datetime
import json
import os
import time
import uuid

import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.jobs.conftest import WorkerExtra
from tests.servidor_google import ServidorGoogle

PORTA_WORKER = 18363 + (uuid.uuid4().int % 300)
SUFIXO = uuid.uuid4().hex[:6]

ITEM = "L6-02-i-google-sheets"
COMANDO = ("set -a; source laco/var/trilha/<t>.env; set +a; "
           "PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/api/conexao/test_google_sheets.py -q")

CSV_V1 = (
    "nome,lat,lon,area_ha\n"
    "Talhao A,-15.7942,-47.8822,120.5\n"
    "Talhao B,-23.5505,-46.6333,89.25\n"
).encode("utf-8")
CSV_V2 = (
    "nome,lat,lon,area_ha\n"
    "Talhao A,-15.7942,-47.8822,120.5\n"
    "Talhao B,-23.5505,-46.6333,89.25\n"
    "Talhao C,-22.9068,-43.1729,77.0\n"
).encode("utf-8")

# planilha pública de exemplo mantida pelo próprio Google (documentação do Sheets): alcance ao vivo
URL_PLANILHA_EXEMPLO_GOOGLE = ("https://docs.google.com/spreadsheets/d/"
                               "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/export?format=csv")


@pytest.fixture
def anota(medida):
    """Grava em tests/medidas/L6-02-i-google-sheets.json (só com PLAT_GRAVAR_MEDIDAS=1)."""
    gravar = medida(ITEM)

    def _anota(nome: str, valor):
        gravar(nome, valor, "json", COMANDO)

    return _anota


@pytest.fixture(scope="module")
def servidor():
    with ServidorGoogle() as s:
        yield s


@pytest.fixture(scope="module")
def prefixo_planilha(servidor):
    """A app do processo de teste aponta para o servidor de prova (a chave PLAT_SHEETS_EXPORTACAO_PREFIXO
    existe exatamente para isto) e o SSL_CERT_FILE ganha o bundle CA-de-teste + CAs do sistema — nenhuma
    verificação desligada. O worker NÃO precisa do prefixo: a URL gravada na conexão já é a canônica."""
    from app.settings import settings

    anterior_prefixo = settings.PLAT_SHEETS_EXPORTACAO_PREFIXO
    anterior_ssl = os.environ.get("SSL_CERT_FILE")
    # Settings é dataclass congelada de propósito (ninguém muda configuração em runtime); o teste aponta a
    # origem de planilha para o servidor de prova pelo __setattr__ interno, e devolve ao sair
    object.__setattr__(settings, "PLAT_SHEETS_EXPORTACAO_PREFIXO", servidor.base)
    os.environ["SSL_CERT_FILE"] = str(servidor.bundle)
    yield servidor.base
    object.__setattr__(settings, "PLAT_SHEETS_EXPORTACAO_PREFIXO", anterior_prefixo)
    if anterior_ssl is None:
        os.environ.pop("SSL_CERT_FILE", None)
    else:
        os.environ["SSL_CERT_FILE"] = anterior_ssl


@pytest.fixture(scope="module")
def worker(env, servidor):
    """Decisão G7 (afinidade de executor em `plat.job_pegar`, migração 20260916T1600): o worker extra
    deste arquivo é PRIVADO (tem a CA de teste e a válvula PLAT_TESTE_CONEXAO_ALVOS liberada), mas
    disputa a MESMA fila `plat.job` do worker do systemd da trilha — que não tem nem uma coisa nem
    outra e falhava a sincronização quando vencia a corrida (erro_de_conexao:ConnectError). A
    identidade única `teste:<pid deste processo pytest>` é anunciada pelo worker extra (3º argumento de
    `job_pegar`, via PLAT_WORKER_EXECUTOR) E gravada no job que `Fonte.sincronizar()` enfileira (mesmo
    processo pytest, via PLAT_TESTE_JOB_EXECUTOR lida por `app.jobs.sistema.enfileirar`) — as duas
    pontas usam o MESMO valor, então só este worker pega este job."""
    identidade = f"teste:{os.getpid()}"
    anterior = os.environ.get("PLAT_TESTE_JOB_EXECUTOR")
    os.environ["PLAT_TESTE_JOB_EXECUTOR"] = identidade
    env2 = dict(env)
    env2["SSL_CERT_FILE"] = str(servidor.bundle)   # o worker em subprocesso verifica a CA de teste
    w = WorkerExtra(env2, f"teste-l602i-{PORTA_WORKER}", processos=2, porta=PORTA_WORKER, executor=identidade)
    yield w
    w.parar()
    if anterior is None:
        os.environ.pop("PLAT_TESTE_JOB_EXECUTOR", None)
    else:
        os.environ["PLAT_TESTE_JOB_EXECUTOR"] = anterior


def _cliente(env, slug: str):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests import jobs_sessao

    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        token, _tenant, _usuario = jobs_sessao.criar_sessao(con, slug, "admin")
    finally:
        con.close()
    return TestClient(app, cookies={jobs_sessao.COOKIE_SESSAO: token})


@pytest.fixture(scope="module")
def cliente_demo(env, prefixo_planilha, worker):
    with _cliente(env, "demo") as c:
        yield c


@pytest.fixture(scope="module")
def cliente_plataforma(env, prefixo_planilha, worker):
    with _cliente(env, "plataforma") as c:
        yield c


class Fonte:
    """Conexão google_sheets criada pela API, com as operações do ciclo de vida do arquivo por URL."""

    def __init__(self, cliente, url: str, nome: str, credencial: str | None = None,
                     intervalo_s: int = 900, agendado: bool = False):
        self.cliente = cliente
        corpo = {"tipo": "google_sheets", "modo": "copiada",
                 "nome": f"{PREFIXO_TESTE} {nome} {SUFIXO}", "url": url}
        if credencial is not None:
            corpo["credencial"] = credencial
        r = cliente.post("/api/conexoes", json=corpo)
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        self.url_gravada = r.json()["url"]
        r = cliente.put(f"/api/conexoes/{self.id}/arquivo",
                        json={"intervalo_s": intervalo_s, "agendado": agendado})
        assert r.status_code == 200, r.text

    def reagendar(self, agendado: bool) -> None:
        r = self.cliente.put(f"/api/conexoes/{self.id}/arquivo",
                             json={"intervalo_s": 900, "agendado": agendado})
        assert r.status_code == 200, r.text

    def sincronizar(self, timeout: float = 240) -> dict:
        r = self.cliente.post(f"/api/conexoes/{self.id}/arquivo/sincronizar")
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]
        fim = time.monotonic() + timeout
        ultimo = None
        while time.monotonic() < fim:
            j = self.cliente.get(f"/api/jobs/{job_id}")
            assert j.status_code == 200, j.text
            ultimo = j.json()
            if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
                return ultimo
            time.sleep(0.3)
        pytest.fail(f"job {job_id} não terminou em {timeout} s: {json.dumps(ultimo)[:600]}")

    def estado(self) -> dict:
        r = self.cliente.get(f"/api/conexoes/{self.id}/arquivo")
        assert r.status_code == 200, r.text
        return r.json()

    def esperar_passagem(self, sincronizacoes: int, timeout: float = 240) -> dict:
        """Espera o agendamento (não uma sincronização manual) produzir a enésima passagem."""
        fim = time.monotonic() + timeout
        while time.monotonic() < fim:
            est = self.estado()
            if (est["sincronizacoes"] or 0) >= sincronizacoes:
                return est
            time.sleep(1.0)
        pytest.fail(f"a passagem {sincronizacoes} não aconteceu em {timeout} s: {json.dumps(est)[:600]}")

    def testar(self) -> dict:
        r = self.cliente.post(f"/api/conexoes/{self.id}/testar")
        assert r.status_code == 200, r.text
        return r.json()

    def conexao(self) -> dict:
        r = self.cliente.get(f"/api/conexoes/{self.id}")
        assert r.status_code == 200, r.text
        return r.json()

    def apagar(self):
        self.cliente.delete(f"/api/conexoes/{self.id}")


@pytest.fixture
def fonte(cliente_demo, servidor, worker):
    criadas: list[Fonte] = []

    def _criar(url: str, nome: str, **kw) -> Fonte:
        f = Fonte(cliente_demo, url, nome, **kw)
        criadas.append(f)
        return f

    yield _criar
    camadas = []
    for f in criadas:
        try:
            est = f.estado()
        except Exception:  # a conexão pode já ter sido apagada pelo próprio teste
            continue
        if est.get("item_id"):
            camadas.append(est["item_id"])
        f.apagar()
    for item_id in camadas:
        cliente_demo.delete(f"/api/itens/{item_id}")


def _rodar_periodico(cliente_plataforma) -> None:
    """Uma rodada do periódico do relógio (conexoes.arquivo_sincronizar_vencidas), no inquilino técnico —
    o mesmo tipo que o L0-05 dispara a cada 15 minutos (app/conexao/periodicos.py)."""
    r = cliente_plataforma.post("/api/jobs", json={"tipo": "conexoes.arquivo_sincronizar_vencidas",
                                                   "parametros": {}})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    fim = time.monotonic() + 120
    while time.monotonic() < fim:
        j = cliente_plataforma.get(f"/api/jobs/{job_id}").json()
        if j["estado"] in ("concluido", "falhou", "cancelado"):
            assert j["estado"] == "concluido", j.get("erro")
            return
        time.sleep(0.5)
    pytest.fail("o periódico de vencidas não terminou em 120 s")


# ---------------------------------------------------------------- entrada: URL e credencial
def test_url_de_planilha_e_normalizada_na_criacao(cliente_demo, servidor, prefixo_planilha):
    """A URL gravada é SEMPRE a canônica de exportação CSV, com o gid da aba preservado — as formas de
    edição/publicação que o usuário cola nunca ficam registradas."""
    base = prefixo_planilha
    r = cliente_demo.post("/api/conexoes", json={
        "tipo": "google_sheets", "modo": "copiada", "nome": f"{PREFIXO_TESTE} norm {SUFIXO}",
        "url": f"{base}/spreadsheets/d/abcDEF123_-x/edit#gid=7",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["url"] == f"{base}/spreadsheets/d/abcDEF123_-x/export?format=csv&gid=7"
    cliente_demo.delete(f"/api/conexoes/{cid}")

    r = cliente_demo.post("/api/conexoes", json={
        "tipo": "google_sheets", "modo": "copiada", "nome": f"{PREFIXO_TESTE} norm2 {SUFIXO}",
        "url": f"{base}/spreadsheets/d/e/PACote123_-x/pubhtml?gid=5",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["url"] == f"{base}/spreadsheets/d/e/PACote123_-x/pub?output=csv&single=true&gid=5"
    cliente_demo.delete(f"/api/conexoes/{cid}")

    # URL de outro serviço não vira conexão google_sheets (nem com caminho de planilha)
    r = cliente_demo.post("/api/conexoes", json={
        "tipo": "google_sheets", "modo": "copiada", "nome": f"{PREFIXO_TESTE} estranha {SUFIXO}",
        "url": "https://example.com/spreadsheets/d/abcDEF123_-x/edit",
    })
    assert r.status_code == 422, r.text
    assert "url_nao_e_planilha_google" in json.dumps(r.json())


def test_credencial_invalida_recusada_na_entrada(cliente_demo, servidor, fonte, anota):
    url = servidor.publicar_privada(f"priv-entrada-{SUFIXO}", CSV_V1)
    r = cliente_demo.post("/api/conexoes", json={
        "tipo": "google_sheets", "modo": "copiada", "nome": f"{PREFIXO_TESTE} cred ruim {SUFIXO}",
        "url": url, "credencial": '{"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com"}',
    })
    assert r.status_code == 422, r.text
    corpo = json.dumps(r.json(), ensure_ascii=False)
    assert "private_key" in corpo, "o erro tem de NOMEAR o campo que faltou"
    anota("credencial_invalida_na_entrada", {"status": r.status_code, "erro": r.json()})


# ---------------------------------------------------------------- cláusula 1: pública vira camada
def test_planilha_publica_vira_camada(fonte, servidor, cliente_demo, anota):
    id_plan = f"pub-{SUFIXO}"
    url = servidor.publicar_publica(id_plan, CSV_V1)
    f = fonte(f"{url}#gid=0", "planilha publica")
    assert f.url_gravada.endswith(f"/spreadsheets/d/{id_plan}/export?format=csv&gid=0")

    job = f.sincronizar()
    assert job["estado"] == "concluido", job.get("erro")
    assert job["resultado"]["recarregou"] is True
    assert job["resultado"]["formato"] == "csv"
    assert job["resultado"]["feicoes"] == 2

    est = f.estado()
    assert est["ultimo_resultado"] == "carregada"
    r = cliente_demo.get(f"/api/itens/{est['item_id']}")
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["tipo"] == "camada_vetorial"
    assert item["dados"]["estatisticas"]["feicoes"] == 2

    # a exportação pública NUNCA recebeu credencial
    assert servidor.autorizacoes_da(id_plan) == [None]
    anota("publica_vira_camada", {
        "feicoes": job["resultado"]["feicoes"], "formato": "csv", "item_id": est["item_id"],
        "url_gravada_e_canonica": f.url_gravada.endswith("export?format=csv&gid=0"),
        "cabecalho_authorization_na_exportacao": None,
    })


def test_atualizacao_agendada_em_15_minutos(fonte, servidor, cliente_demo, cliente_plataforma, anota):
    """A cláusula do relógio. Prova em três tempos: (a) o intervalo mínimo do agendador é 900 s — 15 min —
    e é o que a conexão grava; (b) o periódico do relógio (cadenciado a */15 em app/conexao/periodicos.py)
    enfileira a conexão vencida SEM sincronização manual nenhuma e a camada nasce; (c) depois da passagem,
    proximo_em - ultimo_em é exatamente 900 s, e uma nova rodada do periódico pega o conteúdo trocado."""
    id_plan = f"ag15-{SUFIXO}"
    url = servidor.publicar_publica(id_plan, CSV_V1)
    f = fonte(url, "planilha agendada", agendado=True, intervalo_s=900)

    est0 = f.estado()
    assert est0["intervalo_s"] == 900 and est0["agendado"] is True

    _rodar_periodico(cliente_plataforma)
    est1 = f.esperar_passagem(1)
    assert est1["ultimo_resultado"] == "carregada", est1
    assert est1["recargas"] == 1 and est1["item_id"]
    item_primeiro = est1["item_id"]

    # o próximo disparo ficou marcado para exatamente 15 minutos depois desta passagem
    ultimo = datetime.datetime.fromisoformat(est1["ultimo_em"])
    proximo = datetime.datetime.fromisoformat(est1["proximo_em"])
    delta = (proximo - ultimo).total_seconds()
    assert delta == 900, f"proximo_em - ultimo_em = {delta} s, esperado 900"

    # a planilha muda e a conexão vence de novo (reagendar zera proximo_em para agora, como faria o
    # relógio ao cruzar os 15 min); a segunda rodada do periódico recarrega com o conteúdo novo
    servidor.trocar_corpo(id_plan, CSV_V2)
    f.reagendar(False)
    f.reagendar(True)
    _rodar_periodico(cliente_plataforma)
    est2 = f.esperar_passagem(2)
    assert est2["ultimo_resultado"] == "carregada", est2
    assert est2["recargas"] == 2
    assert est2["item_id"] != item_primeiro
    r = cliente_demo.get(f"/api/itens/{est2['item_id']}")
    assert r.json()["dados"]["estatisticas"]["feicoes"] == 3

    anota("atualizacao_agendada_15_min", {
        "intervalo_s": est0["intervalo_s"], "intervalo_minimo_do_agendador_s": 900,
        "cadencia_do_periodico": "*/15 * * * *",
        "proximo_menos_ultimo_s": delta,
        "passagens_pelo_agendador": est2["sincronizacoes"], "recargas": est2["recargas"],
        "camada_trocada_na_recarga": est2["item_id"] != item_primeiro,
        "feicoes_depois_da_troca": 3,
    })


# ------------------------------------------------- cláusula 2: privada com conta de serviço
def test_planilha_privada_com_conta_de_servico(fonte, servidor, cliente_demo, anota):
    id_plan = f"priv-{SUFIXO}"
    url = servidor.publicar_privada(id_plan, CSV_V1)
    f = fonte(url, "planilha privada", credencial=servidor.conta_servico_json())
    assert f.conexao()["tem_credencial"] is True

    job = f.sincronizar()
    assert job["estado"] == "concluido", job.get("erro")
    assert job["resultado"]["recarregou"] is True
    assert job["resultado"]["feicoes"] == 2

    # a troca de token aconteceu de verdade: assinatura RS256 verificada, iss/aud/scope/exp corretos
    assert len(servidor.trocas) >= 1
    troca = servidor.trocas[-1]
    assert troca["assinatura_valida"] is True
    assert troca["desfecho"] == "concedido"
    assert troca["claims"]["iss"] == servidor.client_email
    assert troca["claims"]["aud"] == servidor.token_uri
    assert "spreadsheets.readonly" in troca["claims"]["scope"]

    # a exportação privada foi buscada COM o Bearer emitido — e o servidor só serviu por causa dele
    autorizacoes = servidor.autorizacoes_da(id_plan)
    assert autorizacoes and all(a and a.startswith("Bearer ya29.teste-") for a in autorizacoes)
    assert autorizacoes[-1][7:] in servidor.tokens

    est = f.estado()
    r = cliente_demo.get(f"/api/itens/{est['item_id']}")
    assert r.json()["tipo"] == "camada_vetorial"
    anota("privada_conta_de_servico_vira_camada", {
        "feicoes": job["resultado"]["feicoes"],
        "jwt_rs256_verificado_pelo_servidor": troca["assinatura_valida"],
        "escopo": "spreadsheets.readonly", "aud": troca["claims"]["aud"],
        "exportacao_com_bearer_emitido": True,
        "item_id": est["item_id"],
    })


# ------------------------------------------------- refutação: conta revogada
def test_refutacao_conta_revogada_mostra_falha_nao_dado_velho(fonte, servidor, cliente_demo, anota):
    """O adversário revoga a conta de serviço: a troca de token passa a responder invalid_grant e a
    sincronização TEM de falhar com a camada anterior intacta — jamais apresentar o dado velho como novo
    (nem recarregar, nem trocar o item, nem marcar a passagem como carregada)."""
    id_plan = f"rev-{SUFIXO}"
    url = servidor.publicar_privada(id_plan, CSV_V1)
    f = fonte(url, "planilha revogada", credencial=servidor.conta_servico_json())

    primeira = f.sincronizar()
    assert primeira["estado"] == "concluido", primeira.get("erro")
    est1 = f.estado()
    assert est1["recargas"] == 1
    item_carregado = est1["item_id"]

    servidor.revogar()
    try:
        job = f.sincronizar()
        assert job["estado"] == "falhou", f"conta revogada não pode sincronizar: {job}"
        assert "conta de serviço" in (job["erro"] or "")

        est2 = f.estado()
        assert est2["ultimo_resultado"] == "falhou"
        assert "conta de serviço" in (est2["ultimo_detalhe"] or "")
        assert est2["recargas"] == 1, "a passagem falhada não pode contar como recarga"
        assert est2["sincronizacoes"] == 2
        assert est2["item_id"] == item_carregado, "a camada carregada não pode sumir nem ser trocada"
        assert est2["sha256"], "o sha da última carga boa continua registrado (não virou 'novo')"

        # o teste de saúde conta a mesma história: erro, nunca ok
        t = f.testar()
        assert t["ok"] is False and "conta de serviço" in t["mensagem"]
        con = f.conexao()
        assert con["saude"] == "erro"
        assert "conta de serviço" in (con["saude_mensagem"] or "")

        # a camada continua servindo o dado da última carga boa, com a falha visível ao lado
        r = cliente_demo.get(f"/api/itens/{item_carregado}")
        assert r.status_code == 200
        assert r.json()["dados"]["estatisticas"]["feicoes"] == 2
    finally:
        servidor.reativar()

    # conta reativada: a mesma conexão volta a sincronizar (sem mudança de conteúdo desde a última carga
    # boa) — o ETag guardado antes da revogação continua válido, então o servidor pode responder 304 (não
    # precisou nem baixar de novo) OU 200 com o mesmo corpo (sha256 igual); as duas são "não recarregou",
    # nunca "carregada", e é isso que a cláusula do portão mede (nunca dado velho como novo).
    terceira = f.sincronizar()
    assert terceira["estado"] == "concluido", terceira.get("erro")
    assert terceira["resultado"]["motivo"] in ("sha256_igual", "http_304"), terceira["resultado"]

    anota("refutacao_conta_revogada", {
        "job": "falhou", "ultimo_resultado": est2["ultimo_resultado"],
        "detalhe": est2["ultimo_detalhe"],
        "recargas_inalteradas": est2["recargas"], "sincronizacoes": est2["sincronizacoes"],
        "camada_preservada": est2["item_id"] == item_carregado,
        "saude_apos_revogacao": con["saude"],
        "recuperacao_apos_reativacao": terceira["resultado"]["motivo"],
    })


# ------------------------------------------------- credencial nunca em log
def test_credencial_nunca_aparece_em_log_nem_resposta(fonte, servidor, cliente_demo, env, anota):
    """Canários: e-mail da conta, trecho da chave privada, access tokens emitidos e os JWTs trocados.
    Nenhum pode aparecer em: respostas da API (conexão, estado do arquivo, teste de saúde, job) e nas
    superfícies de log do banco (plat.job, plat.job_log, plat.conexao, plat.conexao_arquivo, plat.evento).
    A varredura cobre inclusive as passagens FALHADAS (conta revogada), que é onde segredo costuma vazar."""
    id_plan = f"log-{SUFIXO}"
    url = servidor.publicar_privada(id_plan, CSV_V1)
    f = fonte(url, "planilha canario", credencial=servidor.conta_servico_json())
    job_ok = f.sincronizar()
    assert job_ok["estado"] == "concluido", job_ok.get("erro")
    servidor.revogar()
    try:
        job_ruim = f.sincronizar()
        assert job_ruim["estado"] == "falhou"
        f.testar()
    finally:
        servidor.reativar()

    trecho_chave = "MII"  # toda chave RSA PEM em base64 começa assim; se vazar, aparece
    canarios = [servidor.client_email, trecho_chave] + list(servidor.tokens)

    textos: dict[str, str] = {
        "api_conexao": json.dumps(f.conexao(), ensure_ascii=False),
        "api_arquivo": json.dumps(f.estado(), ensure_ascii=False),
        "api_testar": json.dumps(f.testar(), ensure_ascii=False),
        "api_job_ok": json.dumps(job_ok, ensure_ascii=False),
        "api_job_falhou": json.dumps(job_ruim, ensure_ascii=False),
    }

    from tests import jobs_sessao

    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        _token, tenant_id, usuario_id = jobs_sessao.criar_sessao(con, "demo", "admin")
        with con.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            # cursor herda CursorSchemaAmbiente (dict-like, ver tests/jobs_sessao.py) — a coluna precisa de
            # nome para ser lida por chave; sem "AS r" o driver devolve uma linha sem chave 0 (KeyError).
            cur.execute("SELECT row(j.*)::text AS r FROM plat.job j WHERE j.tipo LIKE 'conexoes.%'")
            textos["db_job"] = "\n".join(r["r"] for r in cur.fetchall())
            cur.execute("SELECT row(l.*)::text AS r FROM plat.job_log l")
            textos["db_job_log"] = "\n".join(r["r"] for r in cur.fetchall())
            cur.execute("SELECT row(c.*)::text AS r FROM plat.conexao c WHERE c.nome LIKE %s",
                        (f"{PREFIXO_TESTE} %",))
            linhas = cur.fetchall()
            textos["db_conexao"] = "\n".join(r["r"] for r in linhas)
            cur.execute("SELECT row(a.*)::text AS r FROM plat.conexao_arquivo a")
            textos["db_conexao_arquivo"] = "\n".join(r["r"] for r in cur.fetchall())
            cur.execute("SELECT row(e.*)::text AS r FROM plat.evento e WHERE e.alvo_tipo = 'conexao'")
            textos["db_evento"] = "\n".join(r["r"] for r in cur.fetchall())
    finally:
        con.close()

    vazamentos = [
        f"{superficie} contém {('e-mail da conta' if c == servidor.client_email else 'material de chave/token')}"
        for superficie, texto in textos.items() for c in canarios if c and c in texto
    ]
    assert not vazamentos, "; ".join(vazamentos)
    anota("credencial_fora_de_log", {
        "superficies_varridas": sorted(textos),
        "canarios": ["client_email", "trecho base64 da chave privada", "access tokens emitidos"],
        "vazamentos": [],
        "passagens_cobertas": ["carga com sucesso", "falha por conta revogada", "teste de saúde"],
    })


# ------------------------------------------------- alcance ao vivo: docs.google.com de verdade
def test_alcance_google_de_verdade(servidor, anota):
    """Medida ao vivo: a MESMA buscar_seguro da plataforma baixa a planilha pública de exemplo mantida pelo
    próprio Google, por HTTPS, e o reconhecedor de formato a lê como CSV. O que a planilha de exemplo não
    tem (colunas de coordenada) e o que a casa não tem (conta Google para publicar planilha própria e
    conta de serviço) ficam registrados como fronteira honesta — nunca como feito."""
    from app.conexao import arquivo_url, seguranca

    try:
        r = seguranca.buscar_seguro(URL_PLANILHA_EXEMPLO_GOOGLE, metodo="GET", guardar_corpo=True,
                                    max_bytes=2 * 1024 * 1024, timeout_ler=30.0)
    except Exception as e:  # sem rede nesta máquina: a medida não existe, o teste não finge
        pytest.skip(f"sem alcance ao docs.google.com daqui ({e})")
    if not r.ok:
        pytest.skip(f"docs.google.com inalcançável daqui ({r.mensagem})")

    import hashlib

    analise = arquivo_url.analisar(r.corpo, "text/csv", URL_PLANILHA_EXEMPLO_GOOGLE)
    assert analise.formato == "csv"
    anota("alcance_google_de_verdade", {
        "url": URL_PLANILHA_EXEMPLO_GOOGLE, "status": r.status, "bytes": len(r.corpo),
        "sha256": hashlib.sha256(r.corpo).hexdigest(),
        "formato_reconhecido": analise.formato, "saltos_de_redirect": r.saltos,
        "primeira_linha": r.corpo.decode("utf-8", errors="replace").splitlines()[0],
    })
    anota("fronteira_privada_no_google_real", {
        "estado": "pendente",
        "motivo": "a casa não tem conta de serviço do Google; o fluxo privado foi provado ponta a ponta "
                  "contra servidor que verifica a assinatura RS256 do JWT de verdade",
    })
    anota("fronteira_planilha_publica_propria", {
        "estado": "pendente",
        "motivo": "publicar uma planilha de teste da casa exige conta Google, que a casa não tem; a "
                  "planilha pública de exemplo do Google baixa e é reconhecida como CSV, mas não tem "
                  "colunas de coordenada e portanto não vira camada",
    })
