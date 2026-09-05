"""Hash de senha pbkdf2_sha256 da biblioteca padrão, formato `pbkdf2_sha256$<iterações>$<salt>$<hex>`
(ADR 0001 seção 6, item 6: 600.000 iterações). Usado pelo install.sh para semear os administradores
de demonstração e pelo item L0-02 no login."""

import hashlib
import hmac
import secrets

ITERACOES = 600_000
ALGORITMO = "pbkdf2_sha256"


def gerar_hash(senha: str, iteracoes: int = ITERACOES) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("ascii"), iteracoes).hex()
    return f"{ALGORITMO}${iteracoes}${salt}${digest}"


def verificar(senha: str, armazenado: str) -> bool:
    try:
        algoritmo, iteracoes, salt, digest = armazenado.split("$")
        if algoritmo != ALGORITMO:
            return False
        calculado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("ascii"), int(iteracoes)).hex()
        return hmac.compare_digest(calculado, digest)
    except (ValueError, AttributeError):
        return False
