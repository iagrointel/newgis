"""TOTP contra o vetor da RFC 6238 (T=59 → 287082), janela ±1, anti-replay, cifra AES-GCM ida-e-volta com
prefixo enc:v1:, códigos de recuperação e QR em SVG (ADR 0002 seção 7)."""

import base64
import re

import pytest

from app.auth import totp

SEGREDO_RFC = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
CHAVE = "ab" * 32


def test_vetor_da_rfc_6238():
    assert totp.codigo(SEGREDO_RFC, t=59) == "287082"
    assert totp.codigo(SEGREDO_RFC, t=1111111109) == "081804"
    assert totp.codigo(SEGREDO_RFC, t=1234567890) == "005924"


def test_janela_mais_menos_um_passo():
    t = 1_700_000_000
    passo = totp.passo_atual(t)
    assert totp.verificar(SEGREDO_RFC, totp.codigo(SEGREDO_RFC, passo=passo), None, t=t) == passo
    assert totp.verificar(SEGREDO_RFC, totp.codigo(SEGREDO_RFC, passo=passo - 1), None, t=t) == passo - 1
    assert totp.verificar(SEGREDO_RFC, totp.codigo(SEGREDO_RFC, passo=passo + 1), None, t=t) == passo + 1
    assert totp.verificar(SEGREDO_RFC, totp.codigo(SEGREDO_RFC, passo=passo + 2), None, t=t) is None
    assert totp.verificar(SEGREDO_RFC, totp.codigo(SEGREDO_RFC, passo=passo + 10), None, t=t) is None


def test_replay_recusado():
    t = 1_700_000_000
    passo = totp.passo_atual(t)
    cod = totp.codigo(SEGREDO_RFC, passo=passo)
    assert totp.verificar(SEGREDO_RFC, cod, ultimo_passo=passo, t=t) is None
    assert totp.verificar(SEGREDO_RFC, cod, ultimo_passo=passo - 1, t=t) == passo
    # o código anterior também não vale depois que o atual foi usado
    assert totp.verificar(SEGREDO_RFC, totp.codigo(SEGREDO_RFC, passo=passo - 1), ultimo_passo=passo, t=t) is None


@pytest.mark.parametrize("ruim", ["", "12345", "1234567", "abcdef", None, "12 34 5"])
def test_formato_invalido_nao_verifica(ruim):
    assert totp.verificar(SEGREDO_RFC, ruim, None) is None


def test_cifra_ida_e_volta_com_prefixo():
    segredo = totp.gerar_segredo()
    assert re.fullmatch(r"[A-Z2-7]{32}", segredo)
    cifrado = totp.cifrar(segredo, CHAVE)
    assert cifrado.startswith("enc:v1:") and segredo not in cifrado
    assert totp.decifrar(cifrado, CHAVE) == segredo
    assert totp.cifrar(segredo, CHAVE) != cifrado  # nonce novo a cada vez
    with pytest.raises(Exception):  # noqa: B017 — chave errada = InvalidTag da cryptography
        totp.decifrar(cifrado, "cd" * 32)
    with pytest.raises(ValueError):
        totp.decifrar(segredo, CHAVE)


def test_codigos_de_recuperacao_formato_e_hash():
    codigos = totp.codigos_recuperacao()
    assert len(codigos) == 8 and len(set(codigos)) == 8
    for c in codigos:
        assert re.fullmatch(r"[a-z2-7]{4}-[a-z2-7]{4}-[a-z2-7]{2}", c)
    assert totp.hash_recuperacao(codigos[0]) == totp.hash_recuperacao(codigos[0].upper().replace("-", " "))
    assert totp.hash_recuperacao(codigos[0]) != totp.hash_recuperacao(codigos[1])


def test_uri_e_qr_svg():
    u = totp.uri("ABC234", "demo", "maria")
    assert u == "otpauth://totp/plat:demo/maria?secret=ABC234&issuer=plat&digits=6&period=30"
    svg = totp.qr_svg(u)
    assert svg.startswith("<svg") and "<script" not in svg and "<image" not in svg
