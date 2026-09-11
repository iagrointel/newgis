"""Cifra da credencial ArcGIS Online por inquilino (item L2-08-migracao-agol): AES-GCM com chave derivada de
PLAT_SECRET, mesmo desenho de `app.correio.cifra` (senha SMTP) e `app.auth.totp` — prefixo próprio
(`encagol:v1:`) e rótulo (AAD) próprio `plat-agol`, nunca os mesmos das outras cifras: derivar com um sufixo
diferente evita que um segredo cifrado aqui seja decifrável (ou substituível) por outro módulo, mesmo que os
dois vazassem juntos (mesma razão documentada em `app/seguranca_rotacao.py`). A credencial em claro (senha da
organização OU token) nunca é gravada em lugar nenhum além do valor cifrado desta coluna; só
`app/agol/config.py::decifrar_credencial` a decifra, em memória, no momento de falar com o AGOL."""

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIXO_CIFRA = "encagol:v1:"
_AAD = b"plat-agol"


def _chave(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"agol").digest()


def cifrar(credencial: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave(plat_secret)).encrypt(nonce, credencial.encode("utf-8"), _AAD)
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("credencial AGOL sem o prefixo encagol:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA):])
    return AESGCM(_chave(plat_secret)).decrypt(bruto[:12], bruto[12:], _AAD).decode("utf-8")
