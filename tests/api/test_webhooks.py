"""Item L7-08-a-webhooks-eventos: portão e refutação contra o worker REAL da trilha (os testes esperam a
entrega de verdade, no mesmo padrão de test_smtp_convites.py — nada simula o worker). O receptor é um
http.server de captura em stdlib amarrado ao IP GLOBAL da máquina (nunca loopback: a guarda SSRF recusa
loopback por definição, então um receptor em 127.0.0.1 provaria só o erro). A assinatura é conferida pela
BIBLIOTECA DE REFERÊNCIA (standardwebhooks), que é o "receptor de exemplo" do portão e da refutação."""

import http.server
import json
import secrets
import threading
import time
import uuid

import pytest
from standardwebhooks import Webhook, WebhookVerificationError

from tests.api.conftest import InquilinoTemporario
from tests.api.util_smtp_captura import ServidorSMTPCaptura

TICK_S = 0.1
ENTREGA_TIMEOUT_S = 30.0  # fila + worker real (o mesmo teto do teste de e-mail)
PORTAO_ENTREGA_S = 5.0  # cláusula do portão: "recebe em ≤ 5 s"


def _ip_publico_desta_maquina() -> str | None:
    """Mesma régua de tests/unit/test_conexao_seguranca.py (IP global real, nunca docker/loopback)."""
    import ipaddress
    import subprocess

    try:
        saida = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) < 4:
            continue
        ip = partes[3].split("/")[0]
        try:
            if ipaddress.ip_address(ip).is_global:
                return ip
        except ValueError:
            continue
    return None


def _url_qualquer() -> str:
    """URL válida para os testes de ciclo de vida: literal IP global desta máquina (a criação resolve
    DNS na hora — hostname de exemplo não resolve e viraria 422 dns_falhou; porta fechada: nunca há
    conexão de verdade nestes testes)."""
    ip = _ip_publico_desta_maquina()
    if ip is None:
        pytest.skip("máquina sem IP global roteável (sem interface global IPv4)")
    return f"http://{ip}:9/qualquer"


class _Manipulador(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        corpo = self.rfile.read(int(self.headers.get("content-length") or 0))
        registro = {
            "em": time.monotonic(),
            "cabecalhos": {k.lower(): v for k, v in self.headers.items()},
            "corpo": corpo,
        }
        with self.server.trava:
            self.server.registros.append(registro)
        self.send_response(self.server.status_resposta)
        self.end_headers()

    def log_message(self, *a):
        pass


class ReceptorWebhook:
    """Receptor de teste: responde sempre `status_resposta` (200 no caminho feliz, 500 na refutação de
    retentativa) e guarda CADA POST com cabeçalhos (minúsculos, como a biblioteca lê), corpo e horário."""

    def __init__(self, ip: str, status_resposta: int = 200):
        self.servidor = http.server.ThreadingHTTPServer((ip, 0), _Manipulador)
        self.servidor.status_resposta = status_resposta
        self.servidor.registros: list[dict] = []
        self.servidor.trava = threading.Lock()
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()

    @property
    def registros(self) -> list[dict]:
        return self.servidor.registros

    def url(self, ip: str) -> str:
        return f"http://{ip}:{self.servidor.server_address[1]}/hook"

    def esperar(self, n: int, timeout: float = ENTREGA_TIMEOUT_S) -> bool:
        fim = time.monotonic() + timeout
        while time.monotonic() < fim:
            with self.servidor.trava:
                if len(self.servidor.registros) >= n:
                    return True
            time.sleep(TICK_S)
        return False

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.thread.join(timeout=2)


def _criar_webhook(inq, url: str, eventos: list[str] | None = None) -> dict:
    r = inq.admin.post(
        "/api/webhooks",
        json={"nome": f"zt-wh {secrets.token_hex(3)}", "url": url,
              "eventos": eventos or ["usuarios/criar"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _entregas(inq, wid: str, **params) -> list[dict]:
    r = inq.admin.get(f"/api/webhooks/{wid}/entregas", params=params)
    assert r.status_code == 200, r.text
    return r.json()["itens"]


def _esperar_estado(inq, wid: str, campo: str, valor, timeout: float = 90.0):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        r = inq.admin.get(f"/api/webhooks/{wid}")
        if r.status_code == 200 and r.json()[campo] == valor:
            return r.json()
        time.sleep(0.5)
    raise AssertionError(f"webhook {wid}: {campo} nunca chegou a {valor!r}")


# ---------------------------------------------------------------- rápido: ciclo de vida e guardas
def test_criar_devolve_segredo_uma_unicamente(inquilino_temporario):
    inq = inquilino_temporario
    j = _criar_webhook(inq, _url_qualquer())
    segredo = j["segredo"]
    assert segredo.startswith("whsec_")
    wid = j["id"]
    # nem a listagem nem o detalhe devolvem o segredo de novo
    assert all("segredo" not in w for w in inq.admin.get("/api/webhooks").json()["itens"])
    assert "segredo" not in inq.admin.get(f"/api/webhooks/{wid}").json()
    assert inq.admin.get(f"/api/webhooks/{wid}").json()["ativo"] is True


def test_url_privada_e_esquema_fora_da_lista_recusados_na_entrada(inquilino_temporario):
    inq = inquilino_temporario
    casos = (
        ("http://127.0.0.1:9/hook", "ip_bloqueado"),  # refutação: URL interna (loopback)
        ("http://169.254.169.254/latest/meta-data/", "link_local"),  # refutação: metadado de nuvem
        ("http://172.16.0.1/hook", "ip_bloqueado"),  # rede privada RFC 1918
        ("http://10.0.0.5/hook", "ip_bloqueado"),
    )
    for url, _motivo in casos:
        r = inq.admin.post("/api/webhooks", json={"nome": "zt-wh ruim", "url": url,
                                                  "eventos": ["usuarios/criar"]})
        assert r.status_code == 422, (url, r.text)
        assert r.json()["erro"] == "url_insegura", (url, r.text)
        assert "motivo" in r.json()["detalhe"]
    # PATCH não serve para escorrer URL privada numa edição
    j = _criar_webhook(inq, _url_qualquer())
    r = inq.admin.patch(f"/api/webhooks/{j['id']}", json={"url": "http://127.0.0.1:9/hook"})
    assert r.status_code == 422 and r.json()["erro"] == "url_insegura"


def test_eventos_desconhecido_repetido_ou_vazio_recusados(inquilino_temporario):
    inq = inquilino_temporario
    base = {"nome": "zt-wh eventos", "url": _url_qualquer()}
    r = inq.admin.post("/api/webhooks", json={**base, "eventos": ["tipos/nao_existe"]})
    assert r.status_code == 422 and r.json()["erro"] == "evento_desconhecido"
    assert r.json()["detalhe"]["desconhecidos"] == ["tipos/nao_existe"]
    r = inq.admin.post("/api/webhooks", json={**base, "eventos": ["usuarios/criar", "usuarios/criar"]})
    assert r.status_code == 422 and r.json()["erro"] == "evento_repetido"
    r = inq.admin.post("/api/webhooks", json={**base, "eventos": []})
    assert r.status_code == 422  # modelo: mínimo 1
    r = inq.admin.post("/api/webhooks", json={**base, "nome": "ab", "eventos": ["usuarios/criar"]})
    assert r.status_code == 422  # modelo: nome 3-120


def test_job_de_entrega_nunca_nasce_da_api(inquilino_temporario):
    """`webhooks.entregar` é somente_sistema: a entrega nasce do gatilho (transação do fato) e do
    reenvio manual — POST /api/jobs com este tipo é 403, como correio.enviar (L0-07-d)."""
    r = inquilino_temporario.admin.post(
        "/api/jobs", json={"tipo": "webhooks.entregar", "parametros": {"entrega_id": str(uuid.uuid4())}}
    )
    assert r.status_code == 403 and r.json()["erro"] == "tipo_somente_sistema"


def test_inquilino_nao_ve_webhook_nem_entrega_do_outro(inquilino_temporario, sessao_a):
    """RLS de plat.webhook/plat.webhook_entrega: o admin de OUTRO inquilino leva 404 no id alheio."""
    inq = inquilino_temporario
    wid = _criar_webhook(inq, _url_qualquer())["id"]
    r = sessao_a.get(f"/api/webhooks/{wid}")
    assert r.status_code == 404 and r.json()["erro"] == "webhook_inexistente"
    assert wid not in [w["id"] for w in sessao_a.get("/api/webhooks").json()["itens"]]
    r = sessao_a.post(f"/api/webhooks/{wid}/entregas/{uuid.uuid4()}/reenviar")
    assert r.status_code == 404 and r.json()["erro"] == "webhook_inexistente"


def test_editar_rotacionar_apagar_reativar_e_entrega_inexistente(inquilino_temporario):
    inq = inquilino_temporario
    j = _criar_webhook(inq, _url_qualquer())
    wid = j["id"]

    # editar: resposta sem segredo; o evento webhooks/atualizar traz antes/depois
    r = inq.admin.patch(f"/api/webhooks/{wid}", json={"nome": "zt-wh renomeado",
                                                      "eventos": ["usuarios/criar", "webhooks/criar"]})
    assert r.status_code == 200 and "segredo" not in r.json()
    assert r.json()["eventos"] == ["usuarios/criar", "webhooks/criar"]
    r = inq.admin.patch(f"/api/webhooks/{wid}", json={})
    assert r.status_code == 422 and r.json()["erro"] == "nada_para_mudar"
    eventos = inq.admin.get("/api/eventos?limite=20").json()["itens"]
    at = next(e for e in eventos if e["tipo"] == "webhooks/atualizar" and e["alvo_id"] == wid)
    assert at["propriedades"]["antes"]["nome"] == j["nome"]
    assert at["propriedades"]["depois"]["nome"] == "zt-wh renomeado"

    # rotacionar: segredo NOVO (o antigo deixa de verificar); evento webhooks/rotacionar
    r = inq.admin.post(f"/api/webhooks/{wid}/rotacionar")
    assert r.status_code == 200
    novo = r.json()["segredo"]
    assert novo != j["segredo"]
    corpo = b'{"x":1}'
    antigo = Webhook(j["segredo"])
    with pytest.raises(WebhookVerificationError):
        antigo.verify(corpo, {"webhook-id": "t1", "webhook-timestamp": str(int(time.time())),
                              "webhook-signature": "v1," + "A" * 44})
    from app.webhooks import assinatura

    verificado = Webhook(novo).verify(corpo, assinatura.cabecalhos(novo, "t1", corpo))
    assert verificado == {"x": 1}

    # reenvio de entrega inexistente = 404; reativar webhook ativo = 409
    r = inq.admin.post(f"/api/webhooks/{wid}/entregas/{uuid.uuid4()}/reenviar")
    assert r.status_code == 404 and r.json()["erro"] == "entrega_inexistente"
    r = inq.admin.post(f"/api/webhooks/{wid}/reativar")
    assert r.status_code == 409 and r.json()["erro"] == "webhook_ativo"

    # apagar: 204, some da lista; entregas cascadam
    assert inq.admin.delete(f"/api/webhooks/{wid}").status_code == 204
    assert all(w["id"] != wid for w in inq.admin.get("/api/webhooks").json()["itens"])
    eventos = inq.admin.get("/api/eventos?limite=20").json()["itens"]
    assert any(e["tipo"] == "webhooks/apagar" and e["alvo_id"] == wid for e in eventos)


# ---------------------------------------------------------------- e2e com worker real (rápido)
def test_entrega_assinada_reenvio_manual_e_rotacao(inquilino_temporario):
    """Portão: criar webhook → editar (o fato de domínio aqui é usuarios/criar — a API de feições é o
    L2-03, pendente em master; a assinatura é por NOME DE TIPO em plat.evento_tipo, então eventos de
    feição entram por configuração, sem código novo) → receptor recebe em ≤ 5 s com assinatura válida
    pela biblioteca de referência → reenvio manual repete o MESMO webhook-id (idempotência)."""
    ip = _ip_publico_desta_maquina()
    if ip is None:
        pytest.skip("máquina sem IP global roteável (sem interface global IPv4)")
    inq = inquilino_temporario
    receptor = ReceptorWebhook(ip, status_resposta=200)
    try:
        j = _criar_webhook(inq, receptor.url(ip))
        segredo, wid = j["segredo"], j["id"]

        t0 = time.monotonic()
        login = f"zt{secrets.token_hex(4)}"
        r = inq.admin.post("/api/usuarios", json={"login": login, "nome": f"Teste {login}",
                                                  "perfil": "visualizador"})
        assert r.status_code == 201, r.text
        uid = r.json()["usuario"]["id"]
        assert receptor.esperar(1), "nenhuma entrega chegou ao receptor"
        latencia = time.monotonic() - t0
        assert latencia <= PORTAO_ENTREGA_S, f"entrega levou {latencia:.1f}s (portão: ≤ {PORTAO_ENTREGA_S}s)"

        # o receptor de exemplo verifica: biblioteca de referência, corpo EXATO recebido
        reg = receptor.registros[0]
        payload = Webhook(segredo).verify(reg["corpo"], reg["cabecalhos"])
        assert payload["type"] == "usuarios/criar" and payload["op"] == "created"
        assert payload["source"] == "plataforma"
        assert payload["alvo"] == {"tipo": "usuario", "id": str(uid)}
        assert payload["name"] == j["nome"]
        entrega_id = reg["cabecalhos"]["webhook-id"]

        entregas = _entregas(inq, wid)
        assert len(entregas) == 1 and entregas[0]["estado"] == "entregue"
        assert entregas[0]["id"] == entrega_id  # webhook-id do Standard Webhooks = id da entrega
        assert entregas[0]["tentativas"] == 1 and entregas[0]["ultima_status"] == 200

        # reenvio manual: MESMA entrega (mesmo webhook-id, mesmo payload), reenvios = 1
        r = inq.admin.post(f"/api/webhooks/{wid}/entregas/{entrega_id}/reenviar")
        assert r.status_code == 200, r.text
        assert r.json()["reenvios"] == 1
        assert receptor.esperar(2), "o reenvio não chegou ao receptor"
        reg2 = receptor.registros[1]
        assert reg2["cabecalhos"]["webhook-id"] == entrega_id
        assert json.loads(reg2["corpo"]) == json.loads(reg["corpo"])

        # rotação: a entrega seguinte sai assinada com o segredo NOVO (o antigo não verifica mais)
        r = inq.admin.post(f"/api/webhooks/{wid}/rotacionar")
        assert r.status_code == 200
        segredo2 = r.json()["segredo"]
        r = inq.admin.post("/api/usuarios", json={"login": f"zt{secrets.token_hex(4)}",
                                                  "nome": "Depois da rotação", "perfil": "visualizador"})
        assert r.status_code == 201, r.text
        assert receptor.esperar(3), "entrega pós-rotação não chegou"
        reg3 = receptor.registros[2]
        payload3 = Webhook(segredo2).verify(reg3["corpo"], reg3["cabecalhos"])
        assert payload3["op"] == "created"
        with pytest.raises(WebhookVerificationError):
            Webhook(segredo).verify(reg3["corpo"], reg3["cabecalhos"])
    finally:
        receptor.fechar()


# ---------------------------------------------------------------- lento: 5 tentativas + desativação + aviso
@pytest.fixture
def inquilino_desativacao_rapida(sessao_plat):
    """Inquilino com desativação após 2 entregas seguidas falhadas (padrão da casa: 20; aqui 2 para o
    teste caber) e SMTP de captura para provar o aviso ao admin."""
    inq = InquilinoTemporario(sessao_plat, config={"webhooks": {"desativar_apos": 2}})
    yield inq
    inq.apagar()


@pytest.mark.lento
def test_cinco_tentativas_intervalos_crescentes_desativacao_e_aviso(inquilino_desativacao_rapida):
    """Portão/refutação: receptor que devolve 500 vê 5 tentativas com intervalos crescentes (espera
    2**tentativa s do worker) e, após 2 entregas seguidas sem sucesso, o webhook DESATIVA com aviso ao
    admin por e-mail; reativar zera a conta."""
    from tests.api.test_smtp_convites import _configurar_smtp

    ip = _ip_publico_desta_maquina()
    if ip is None:
        pytest.skip("máquina sem IP global roteável (sem interface global IPv4)")
    inq = inquilino_desativacao_rapida
    email_admin = f"adm-{secrets.token_hex(3)}@teste.exemplo"
    r = inq.admin.put(f"/api/usuarios/{inq.admin_id}", json={"email": email_admin})
    assert r.status_code == 200, r.text

    with ServidorSMTPCaptura() as smtp:
        _configurar_smtp(inq.admin, smtp.porta)
        receptor = ReceptorWebhook(ip, status_resposta=500)
        try:
            j = _criar_webhook(inq, receptor.url(ip))
            wid = j["id"]

            # dois fatos → duas entregas → 5 tentativas cada, sempre 500
            for _ in range(2):
                r = inq.admin.post("/api/usuarios", json={"login": f"zt{secrets.token_hex(4)}",
                                                          "nome": "Fato com falha", "perfil": "visualizador"})
                assert r.status_code == 201, r.text
            assert receptor.esperar(10, timeout=240), "as 10 tentativas (2 x 5) não aconteceram"

            # intervalos crescentes DENTRO de cada entrega (espera 2**tentativa: 2, 4, 8, 16 s)
            por_entrega: dict[str, list[float]] = {}
            for reg in receptor.registros:
                por_entrega.setdefault(reg["cabecalhos"]["webhook-id"], []).append(reg["em"])
            assert len(por_entrega) == 2, "entregas misturadas no receptor"
            for eid, instantes in por_entrega.items():
                assert len(instantes) == 5, (eid, len(instantes))
                lacunas = [b - a for a, b in zip(instantes, instantes[1:], strict=False)]
                for i, lacuna in enumerate(lacunas):
                    esperado = float(2 ** (i + 1))
                    assert lacuna >= esperado - 0.5, (eid, i, lacuna)
                assert lacunas == sorted(lacunas), (eid, lacunas)

            # cada entrega terminou 'falhou' com 5 tentativas e a última resposta registrada
            entregas = _entregas(inq, wid)
            assert len(entregas) == 2
            assert all(e["estado"] == "falhou" and e["tentativas"] == 5 and e["ultima_status"] == 500
                       for e in entregas)
        finally:
            receptor.fechar()

        # desativação automática: 2 falhas seguidas >= limite do inquilino
        estado = _esperar_estado(inq, wid, "ativo", False)
        assert estado["falhas_consecutivas"] == 2
        assert estado["desativada_motivo"] and "2" in estado["desativada_motivo"]
        eventos = inq.admin.get("/api/eventos?limite=50").json()["itens"]
        desat = [e for e in eventos if e["tipo"] == "webhooks/desativar" and e["alvo_id"] == wid]
        assert desat and desat[0]["propriedades"]["motivo"] == "falhas_consecutivas"

        # aviso ao admin com e-mail (a MESMA fila: correio.enviar, worker real)
        assert smtp.esperar(1, timeout=30), "aviso de desativação não chegou ao receptor SMTP"
        msg = smtp.mensagens[-1]
        assert email_admin in " ".join(msg.rcpt_to)
        assert "desativado" in msg.assunto.lower() and j["nome"] in msg.assunto

        # reativar: volta a ativo, zera a conta de falhas e narra o fato
        r = inq.admin.post(f"/api/webhooks/{wid}/reativar")
        assert r.status_code == 200 and r.json()["ativo"] is True
        assert r.json()["falhas_consecutivas"] == 0
        assert r.json()["desativada_motivo"] is None
        eventos = inq.admin.get("/api/eventos?limite=50").json()["itens"]
        assert any(e["tipo"] == "webhooks/reativar" and e["alvo_id"] == wid for e in eventos)
