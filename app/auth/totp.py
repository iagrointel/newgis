"""TOTP RFC 6238 (HMAC-SHA1, 30 s, 6 dígitos) em biblioteca padrão, conferido contra o vetor da RFC
(segredo `12345678901234567890`, T=59 → 287082); segredo cifrado com AES-GCM (`enc:v1:`) e chave derivada de
PLAT_SECRET; códigos de recuperação; QR em SVG (qrcode 8.2, sem Pillow). ADR 0002 seção 7."""

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import limites

PASSO_S = 30
DIGITOS = 6
PREFIXO_CIFRA = "enc:v1:"
_ALFABETO_RECUPERACAO = "abcdefghijklmnopqrstuvwxyz234567"


def gerar_segredo() -> str:
    """20 bytes aleatórios em base32 sem `=` (32 caracteres)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _chave(segredo_b32: str) -> bytes:
    faltam = (-len(segredo_b32)) % 8
    return base64.b32decode(segredo_b32.upper() + "=" * faltam, casefold=True)


def codigo(segredo_b32: str, t: float | None = None, passo: int | None = None) -> str:
    """Código de 6 dígitos para o instante `t` (segundos) ou para o passo de tempo `passo`."""
    if passo is None:
        passo = int((time.time() if t is None else t) // PASSO_S)
    mac = hmac.new(_chave(segredo_b32), struct.pack(">Q", passo), hashlib.sha1).digest()
    desloc = mac[-1] & 0x0F
    numero = (struct.unpack(">I", mac[desloc : desloc + 4])[0] & 0x7FFFFFFF) % (10**DIGITOS)
    return f"{numero:0{DIGITOS}d}"


def passo_atual(t: float | None = None) -> int:
    return int((time.time() if t is None else t) // PASSO_S)


def verificar(segredo_b32: str, codigo_informado: str, ultimo_passo: int | None, t: float | None = None) -> int | None:
    """Devolve o passo aceito (para gravar como `totp_ultimo_passo`) ou None. Janela ±1 passo; nunca aceita passo
    menor ou igual ao último usado (anti-replay)."""
    informado = (codigo_informado or "").strip().replace(" ", "")
    if len(informado) != DIGITOS or not informado.isdigit():
        return None
    agora = passo_atual(t)
    for desvio in range(-limites.TOTP_JANELA_PASSOS, limites.TOTP_JANELA_PASSOS + 1):
        p = agora + desvio
        if ultimo_passo is not None and p <= ultimo_passo:
            continue
        if hmac.compare_digest(codigo(segredo_b32, passo=p), informado):
            return p
    return None


def _chave_cifra(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"totp").digest()


def cifrar(segredo_b32: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave_cifra(plat_secret)).encrypt(nonce, segredo_b32.encode("ascii"), b"plat-totp")
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("segredo TOTP sem o prefixo enc:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA) :])
    return AESGCM(_chave_cifra(plat_secret)).decrypt(bruto[:12], bruto[12:], b"plat-totp").decode("ascii")


def codigos_recuperacao(quantos: int = limites.CODIGOS_RECUPERACAO) -> list[str]:
    """8 códigos `xxxx-xxxx-xx` (10 caracteres de [a-z2-7], 50 bits)."""
    saida = []
    for _ in range(quantos):
        letras = "".join(secrets.choice(_ALFABETO_RECUPERACAO) for _ in range(10))
        saida.append(f"{letras[:4]}-{letras[4:8]}-{letras[8:]}")
    return saida


def hash_recuperacao(codigo_recuperacao: str) -> str:
    normal = (codigo_recuperacao or "").strip().lower().replace("-", "").replace(" ", "")
    return hashlib.sha256(normal.encode("ascii", "ignore")).hexdigest()


def uri(segredo_b32: str, slug: str, login: str, emissor: str = "plat") -> str:
    return f"otpauth://totp/{emissor}:{slug}/{login}?secret={segredo_b32}&issuer={emissor}&digits={DIGITOS}&period={PASSO_S}"


def qr_svg(texto: str) -> str:
    """SVG do QR (caminho vetorial, sem script, sem imagem embutida)."""
    import qrcode
    import qrcode.image.svg

    q = qrcode.QRCode(image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    q.add_data(texto)
    q.make(fit=True)
    return q.make_image().to_string(encoding="unicode")
