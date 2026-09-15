"""Foto de visita (item L2-07-campo): decodifica, corrige orientação por EXIF, redimensiona e reencoda como
JPEG limpo — MESMA técnica de app/catalogo/miniatura.py::normalizar (o reencode por Pillow É a fronteira de
segurança de conteúdo: um arquivo que não é imagem de verdade nunca sobrevive ao Image.open+save; nenhum
metadado do aparelho — EXIF, GPS embutido no arquivo — sobrevive ao reencode, mesma prática do sistema de
origem do SIG anterior)."""

from __future__ import annotations

import base64
import binascii
import io
import warnings

from PIL import Image, ImageOps

from app import limites
from app.erros import ErroAPI

Image.MAX_IMAGE_PIXELS = limites.CAMPO_FOTO_PIXELS_MAX
FORMATOS = {"JPEG", "PNG", "WEBP", "HEIF"}


def decodificar_base64(conteudo: str) -> bytes:
    if len(conteudo) * 3 // 4 > limites.CAMPO_FOTO_BYTES_MAX + 4:
        raise ErroAPI(413, "foto_grande", f"foto acima de {limites.CAMPO_FOTO_BYTES_MAX // (1024 * 1024)} MB")
    if conteudo.startswith("data:"):
        conteudo = conteudo.split(",", 1)[-1]
    try:
        dados = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "validacao", "conteudo precisa ser base64 válido", {"campo": "conteudo"}) from e
    if len(dados) > limites.CAMPO_FOTO_BYTES_MAX:
        raise ErroAPI(413, "foto_grande", f"foto acima de {limites.CAMPO_FOTO_BYTES_MAX // (1024 * 1024)} MB")
    return dados


def normalizar(dados: bytes) -> dict:
    """`{dados, largura, altura}`: bytes -> JPEG (maior lado <= CAMPO_FOTO_LADO_MAX, qualidade 88, sem
    metadado). Levanta ErroAPI 415/422 (mesmos códigos de app.catalogo.miniatura, para o front reusar a
    mesma mensagem)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(dados))
            formato = (im.format or "").upper()
            if formato not in FORMATOS:
                raise ErroAPI(415, "formato_nao_aceito", "só JPEG, PNG, WEBP ou HEIF", {"formato": formato or None})
            largura, altura = im.size
            if largura * altura > limites.CAMPO_FOTO_PIXELS_MAX:
                raise ErroAPI(
                    422, "imagem_grande", "imagem com pixels demais",
                    {"largura": largura, "altura": altura, "maximo_px": limites.CAMPO_FOTO_PIXELS_MAX},
                )
            im.load()
            im = ImageOps.exif_transpose(im).convert("RGB")
    except ErroAPI:
        raise
    except Exception as e:  # noqa: BLE001 — qualquer falha de decodificação é "não é imagem", não 500
        raise ErroAPI(400, "nao_e_imagem", "o conteúdo enviado não é uma imagem válida") from e
    if max(im.size) > limites.CAMPO_FOTO_LADO_MAX:
        im.thumbnail((limites.CAMPO_FOTO_LADO_MAX, limites.CAMPO_FOTO_LADO_MAX))
    saida = io.BytesIO()
    im.save(saida, "JPEG", quality=88, optimize=True)
    return {"dados": saida.getvalue(), "largura": im.size[0], "altura": im.size[1]}


__all__ = ["decodificar_base64", "normalizar"]
