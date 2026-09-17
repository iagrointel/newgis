"""Segredo e assinatura do webhook (item L7-08-a): o segredo nasce no formato do Standard Webhooks
(`whsec_` + base64 de 24 bytes aleatórios), dorme cifrado (mesmo padrão AES-GCM de
`app/conexao/credencial.py` — prefixo próprio e AAD fixo para nunca confundir com as outras cifras do
mesmo PLAT_SECRET) e a assinatura é feita pela biblioteca de referência `standardwebhooks`, que também
faz a verificação no receptor de exemplo dos testes (portão do item). A URL passa pela MESMA guarda SSRF
do master (`app/conexao/seguranca.validar_url`, item L6-02-a) em TODA admissão e de novo em cada
despacho — recusa de IP privado/loopback/link-local vale para http e https por igual."""

import base64
import hashlib
import secrets
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from standardwebhooks import Webhook

from app import limites
from app.conexao import seguranca
from app.seguranca_rotacao import decifrar_com_rotacao

PREFIXO_CIFRA = "encwebhook:v1:"
_AAD = b"plat-webhook-segredo"
BYTES_SEGREDO = 24  # o mesmo tamanho do exemplo da especificação Standard Webhooks
CAB_ID = "webhook-id"
CAB_TS = "webhook-timestamp"
CAB_ASSINATURA = "webhook-signature"


def _chave(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"webhook-segredo").digest()


def gerar_segredo() -> str:
    """`whsec_` + base64; é isto que o receptor coloca em `Webhook(secret)` para verificar."""
    return "whsec_" + base64.b64encode(secrets.token_bytes(BYTES_SEGREDO)).decode("ascii")


def cifrar(segredo: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave(plat_secret)).encrypt(nonce, segredo.encode("utf-8"), _AAD)
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("segredo sem o prefixo encwebhook:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA):])
    return AESGCM(_chave(plat_secret)).decrypt(bruto[:12], bruto[12:], _AAD).decode("utf-8")


def decifrar_segredo(armazenado: str) -> str:
    """Leitura com rotação de PLAT_SECRET (L7-19): tenta o segredo atual e, falhando, o anterior."""
    from app.settings import settings

    return decifrar_com_rotacao(decifrar, armazenado, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)



def esquemas() -> tuple[str, ...]:
    """Esquemas admitidos na URL de um webhook (settings.PLAT_WEBHOOK_ESQUEMAS, vírgula-separado). O padrão
    é só https; a trilha de homologação declara "https,http" para receptor local de teste. Qualquer coisa
    fora de http/https é descartada — a guarda de IP do master vale sempre, mas texto claro não tem defesa."""
    from app.settings import settings

    vistos: list[str] = []
    for bruto in (settings.PLAT_WEBHOOK_ESQUEMAS or "https").split(","):
        e = bruto.strip().lower()
        if e in ("http", "https") and e not in vistos:
            vistos.append(e)
    return tuple(vistos) or ("https",)


def validar_url(url: str) -> seguranca.URLValidada:
    """Admissão da URL: guarda SSRF do master + o teto de tamanho em limites. Levanta
    `seguranca.ErroURLInsegura` (as rotas mapeiam para 422 url_insegura)."""
    if not url or len(url) > limites.WEBHOOK_URL_MAX:
        raise seguranca.ErroURLInsegura("url_vazia_ou_longa_demais", url or "")
    validada = seguranca.validar_url(url)  # esquema http/https, sem userinfo, IP público, DNS resolvendo
    if validada.esquema not in esquemas():
        raise seguranca.ErroURLInsegura("esquema_nao_permitido", url)
    return validada


def cabecalhos(segredo: str, entrega_id: str, corpo: bytes, agora: datetime | None = None) -> dict[str, str]:
    """Os três cabeçalhos do Standard Webhooks para um corpo exato. `entrega_id` é o `webhook-id` —
    reenvio repete a MESMA entrega (logo o MESMO id) e o receptor deduplica por ele."""
    momento = agora or datetime.now(timezone.utc)
    assinante = Webhook(segredo)
    valor = assinante.sign(entrega_id, momento, corpo.decode("utf-8"))
    return {
        CAB_ID: entrega_id,
        CAB_TS: str(int(momento.timestamp())),
        CAB_ASSINATURA: valor,
        "content-type": "application/json",
    }
