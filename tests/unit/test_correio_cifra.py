"""Cifra da senha SMTP (item L0-07-d-smtp-convites): AES-GCM roundtrip, prefixo, rótulo (AAD) diferente do
TOTP (mesmo PLAT_SECRET nunca decifra um segredo do outro)."""

import pytest

from app.auth import totp
from app.correio import cifra

SEGREDO = "ab" * 32


def test_roundtrip():
    c = cifra.cifrar("senha-super-secreta", SEGREDO)
    assert c.startswith(cifra.PREFIXO_CIFRA)
    assert cifra.decifrar(c, SEGREDO) == "senha-super-secreta"


def test_cada_cifra_e_diferente_mesmo_com_a_mesma_senha():
    a = cifra.cifrar("x", SEGREDO)
    b = cifra.cifrar("x", SEGREDO)
    assert a != b  # nonce aleatório


def test_chave_errada_nao_decifra():
    c = cifra.cifrar("x", SEGREDO)
    with pytest.raises(Exception):  # noqa: B017 — AESGCM levanta InvalidTag, tipo interno da lib
        cifra.decifrar(c, "cd" * 32)


def test_sem_prefixo_e_erro():
    with pytest.raises(ValueError, match="enc:v1:"):
        cifra.decifrar("qualquer coisa", SEGREDO)


def test_rotulo_diferente_do_totp_mesmo_plat_secret():
    """Cifrado pelo módulo do TOTP não decifra pelo do SMTP e vice-versa, mesmo com o MESMO PLAT_SECRET —
    prova que o AAD (`plat-smtp` vs `plat-totp`) isola os dois, não só o prefixo textual."""
    cifrado_totp = totp.cifrar("SEGREDOTOTPBASE32", SEGREDO)
    with pytest.raises(Exception):  # noqa: B017
        cifra.decifrar(cifrado_totp, SEGREDO)
    cifrado_smtp = cifra.cifrar("senha-smtp", SEGREDO)
    with pytest.raises(Exception):  # noqa: B017
        totp.decifrar(cifrado_smtp, SEGREDO)
