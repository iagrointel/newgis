"""Cifra da senha SMTP por inquilino (item L0-07-d-smtp-convites): AES-GCM com chave derivada de PLAT_SECRET,
mesmo desenho de `app.auth.totp` (prefixo `enc:v1:`), com rótulo (AAD) próprio `plat-smtp` — nunca o mesmo
`_chave_cifra` do TOTP: derivar com um sufixo diferente evita que um segredo cifrado aqui seja decifrável (ou
substituível) ali, mesmo que os dois vazassem juntos. A senha em claro nunca é gravada em lugar nenhum além
do valor cifrado desta coluna; `app/correio/cliente.py` só a decifra em memória, no momento do envio."""

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIXO_CIFRA = "enc:v1:"
_AAD = b"plat-smtp"


def _chave_cifra(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"smtp").digest()


def cifrar(senha: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave_cifra(plat_secret)).encrypt(nonce, senha.encode("utf-8"), _AAD)
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("senha SMTP sem o prefixo enc:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA):])
    return AESGCM(_chave_cifra(plat_secret)).decrypt(bruto[:12], bruto[12:], _AAD).decode("utf-8")
