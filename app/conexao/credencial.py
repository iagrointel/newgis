"""Cifra da credencial de `plat.conexao` (item L6-02-a-modelo-conexao-e-seguranca). Mesmo padrão de
`app/auth/totp.py` e `app/auth/ldap.py`: AES-GCM com chave derivada de PLAT_SECRET (nunca a chave crua), prefixo
próprio (`encconexao:v1:`) para nunca confundir com as outras cifras do mesmo segredo, e AAD fixo (liga o texto
cifrado ao seu propósito — decifrar com o AAD errado falha, mesmo com a chave certa). Nunca loga a credencial em
claro nem cifrada (app/log.py não recebe este campo — as rotas nunca o colocam em log.info/log.error)."""

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIXO_CIFRA = "encconexao:v1:"
_AAD = b"plat-conexao-credencial"


def _chave(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"conexao-credencial").digest()


def cifrar(credencial: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave(plat_secret)).encrypt(nonce, credencial.encode("utf-8"), _AAD)
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("credencial sem o prefixo encconexao:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA) :])
    return AESGCM(_chave(plat_secret)).decrypt(bruto[:12], bruto[12:], _AAD).decode("utf-8")
