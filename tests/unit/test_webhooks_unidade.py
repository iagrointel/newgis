"""Unidade do L7-08-a-webhooks-eventos: segredo/assinatura contra a BIBLIOTECA DE REFERÊNCIA
(standardwebhooks — a mesma que o receptor de exemplo usa), cifra do segredo com rotação, parse de
esquemas, guarda de URL e o clamp de desativação. Nada aqui precisa de banco."""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from standardwebhooks import Webhook, WebhookVerificationError

from app import limites
from app.webhooks import assinatura


def _verificar(segredo: str, corpo: bytes, cabecalhos: dict[str, str]):
    """A verificação do receptor de exemplo: a biblioteca de referência, com o corpo EXATO recebido."""
    return Webhook(segredo).verify(corpo.decode("utf-8"), dict(cabecalhos))


def test_segredo_gerado_assina_e_a_referencia_verifica():
    segredo = assinatura.gerar_segredo()
    assert segredo.startswith("whsec_")
    # decodifica: 24 bytes de entropia (o mesmo tamanho do exemplo da especificação)
    assert len(base64.b64decode(segredo[len("whsec_"):])) == 24
    entrega_id = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
    corpo = b'{"id":"7","op":"created"}'
    cab = assinatura.cabecalhos(segredo, entrega_id, corpo)
    assert cab["webhook-id"] == entrega_id
    assert cab["webhook-signature"].startswith("v1,")
    # a prova do portão: a biblioteca de referência aceita o que a casa assinou
    assert _verificar(segredo, corpo, cab)["op"] == "created"


def test_corpo_forjado_sem_reassinar_e_recusado():
    segredo = assinatura.gerar_segredo()
    cab = assinatura.cabecalhos(segredo, "id-1", b'{"op":"created"}')
    forjado = b'{"op":"deleted"}'  # adversário troca o corpo, mantém id/timestamp/assinatura
    with pytest.raises(WebhookVerificationError):
        _verificar(segredo, forjado, cab)


def test_assinatura_de_outro_segredo_e_recusada():
    """Refutação do item: entrega assinada com segredo DE OUTRO webhook — o receptor de exemplo recusa."""
    corpo = b'{"x":1}'
    cab = assinatura.cabecalhos(assinatura.gerar_segredo(), "id-2", corpo)
    with pytest.raises(WebhookVerificationError):
        _verificar(assinatura.gerar_segredo(), corpo, cab)  # receptor conhece outro segredo


def test_entrega_sem_assinatura_e_recusada():
    segredo = assinatura.gerar_segredo()
    corpo = b'{"x":1}'
    cab = assinatura.cabecalhos(segredo, "id-3", corpo)
    sem_assinatura = {"webhook-id": cab["webhook-id"], "webhook-timestamp": cab["webhook-timestamp"]}
    with pytest.raises(WebhookVerificationError):
        _verificar(segredo, corpo, sem_assinatura)


def test_replay_com_timestamp_fora_de_5_min_e_recusado():
    """Refutação do item: adversário repete uma entrega antiga — o timestamp a mais de 5 min cai na
    tolerância da biblioteca de referência, antes mesmo da conferência da assinatura."""
    segredo = assinatura.gerar_segredo()
    corpo = b'{"x":1}'
    agora = datetime.now(timezone.utc)
    for deslocamento, _ in ((-10, "too old"), (10, "too new")):
        velho = assinatura.cabecalhos(segredo, "id-4", corpo, agora=agora + timedelta(minutes=deslocamento))
        with pytest.raises(WebhookVerificationError):
            _verificar(segredo, corpo, velho)
    # dentro da tolerância (4 min), a MESMA entrega passa: o reenvio legítimo não é confundido com replay
    limite = assinatura.cabecalhos(segredo, "id-5", corpo, agora=agora - timedelta(minutes=4))
    assert _verificar(segredo, corpo, limite) == {"x": 1}


def test_cifra_do_segredo_em_repouso(monkeypatch):
    plat_secret = "ab" * 32
    segredo = assinatura.gerar_segredo()
    armazenado = assinatura.cifrar(segredo, plat_secret)
    assert armazenado.startswith("encwebhook:v1:")
    assert segredo not in armazenado  # nunca em claro
    assert assinatura.decifrar(armazenado, plat_secret) == segredo
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        assinatura.decifrar(armazenado, "cd" * 32)  # chave errada: AEAD InvalidTag
    # rotação (L7-19): o segredo anterior ainda lê o que foi cifrado com ele
    fake = type("S", (), {"PLAT_SECRET": "cd" * 32, "PLAT_SECRET_ANTERIOR": plat_secret})
    monkeypatch.setattr(__import__("app.settings", fromlist=["settings"]), "settings", fake)
    assert assinatura.decifrar_segredo(armazenado) == segredo


class _SoEsquemas:
    def __init__(self, valor):
        self.PLAT_WEBHOOK_ESQUEMAS = valor
        self.PLAT_SECRET = "ab" * 32
        self.PLAT_SECRET_ANTERIOR = None


def test_esquemas_parse(monkeypatch):
    import app.settings

    for bruto, esperado in (
        (None, ("https",)),
        ("", ("https",)),
        ("https", ("https",)),
        ("https,http", ("https", "http")),
        (" HTTPS , http , ftp , gopher ", ("https", "http")),  # fora de http/https é descartado
        ("ftp", ("https",)),  # nada admitido: cai no padrão, nunca numa lista vazia
    ):
        monkeypatch.setattr(app.settings, "settings", _SoEsquemas(bruto))
        assert assinatura.esquemas() == esperado


def test_validar_url_recusa_ip_privado_e_esquema_fora_da_lista(monkeypatch):
    import app.settings

    monkeypatch.setattr(app.settings, "settings", _SoEsquemas("https,http"))
    with pytest.raises(assinatura.seguranca.ErroURLInsegura) as e:
        assinatura.validar_url("http://127.0.0.1:9/hook")
    assert e.value.motivo.startswith("ip_bloqueado")
    with pytest.raises(assinatura.seguranca.ErroURLInsegura) as e:
        assinatura.validar_url("http://169.254.169.254/latest/meta-data/")
    assert "link_local" in e.value.motivo
    # 8.8.8.8 é global (IP literal, sem DNS): passa na guarda de IP, mas http não está na lista
    monkeypatch.setattr(app.settings, "settings", _SoEsquemas("https"))
    with pytest.raises(assinatura.seguranca.ErroURLInsegura) as e:
        assinatura.validar_url("http://8.8.8.8/hook")
    assert e.value.motivo == "esquema_nao_permitido"
    with pytest.raises(assinatura.seguranca.ErroURLInsegura) as e:
        assinatura.validar_url("x" * (limites.WEBHOOK_URL_MAX + 1))
    assert e.value.motivo == "url_vazia_ou_longa_demais"


def test_clamp_da_desativacao_por_inquilino():
    assert assinatura_e_clamp(None) == limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO
    assert assinatura_e_clamp({}) == limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO
    assert assinatura_e_clamp({"webhooks": {}}) == limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO
    assert assinatura_e_clamp({"webhooks": {"desativar_apos": 1}}) == limites.WEBHOOK_FALHAS_DESATIVAR_MIN
    assert assinatura_e_clamp({"webhooks": {"desativar_apos": 7}}) == 7
    assert assinatura_e_clamp({"webhooks": {"desativar_apos": 10_000}}) == limites.WEBHOOK_FALHAS_DESATIVAR_MAX
    assert assinatura_e_clamp({"webhooks": {"desativar_apos": "lixo"}}) == limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO
    assert assinatura_e_clamp({"webhooks": {"desativar_apos": None}}) == limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO


def assinatura_e_clamp(config):
    from app.webhooks.tarefas import _desativar_apos

    return _desativar_apos(config)


def test_tipos_registrados_e_agenda_do_periodico():
    """webhooks.entregar é somente_sistema (nenhum POST /api/jobs cria) e o expurgo está na agenda do
    worker no inquilino técnico; a importação de app.jobs.tipos basta para ambos."""
    from app.jobs import periodicos as base
    from app.jobs import tipos as _tipos  # noqa: F401 — efeito: registra tudo
    from app.jobs.registro import REGISTRO

    entregar = REGISTRO["webhooks.entregar"]
    assert entregar.somente_sistema is True
    assert entregar.tentativas == limites.WEBHOOK_TENTATIVAS_MAX
    assert entregar.executor == "local" and entregar.pesado is False
    expurgar = REGISTRO["webhooks.expurgar"]
    assert expurgar.parametros.model_fields["dias"].default == limites.WEBHOOK_ENTREGA_RETENCAO_DIAS
    assert any(p[2] == "webhooks.expurgar" and p[1] == "17 4 * * *" for p in base.PERIODICOS)
