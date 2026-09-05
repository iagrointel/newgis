"""Adaptador local de armazenamento de objetos com o contrato que o L0-11 fixa (ADR 0004 seção 11.3):
guardar(classe, item_id, dados, content_type) -> {chave, sha256, bytes}; ler(chave) -> bytes; url_assinada(chave, s)
-> str; apagar(chave). Grava de verdade em PLAT_DADOS_DIR (padrão <repo>/var/dados, fora do git) com a chave
<classe>/<uuid>/<sha256>.<ext>; mesma chave = mesmo conteúdo = nunca sobrescreve. O L0-11 troca este módulo pelo
cliente do Garage sem mudar chamador e migra os arquivos com o job objetos.migrar_local.
A URL assinada é servida por GET /api/objetos/{chave} com HMAC-SHA256 do PLAT_SECRET e validade em segundos."""

import hashlib
import hmac
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSOES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "application/json": "json",
    "text/csv": "csv",
    "application/octet-stream": "bin",
}
CHAVE = re.compile(r"^[a-z0-9_]{1,40}/[0-9a-f-]{36}/[0-9a-f]{64}\.[a-z0-9]{1,8}$")


class ChaveInvalida(ValueError):
    """Chave fora do padrão <classe>/<uuid>/<sha256>.<ext>: nunca chega ao disco."""


def raiz() -> Path:
    return Path(os.environ.get("PLAT_DADOS_DIR") or (ROOT / "var" / "dados")) / "objetos"


def _caminho(chave: str) -> Path:
    if not CHAVE.match(chave):
        raise ChaveInvalida(chave)
    return raiz() / chave


def guardar(classe: str, item_id, dados: bytes, content_type: str) -> dict:
    sha = hashlib.sha256(dados).hexdigest()
    ext = EXTENSOES.get(content_type, "bin")
    chave = f"{classe}/{item_id}/{sha}.{ext}"
    destino = _caminho(chave)
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".parcial")
        temporario.write_bytes(dados)
        os.replace(temporario, destino)
    return {"chave": chave, "sha256": sha, "bytes": len(dados)}


def existe(chave: str) -> bool:
    return _caminho(chave).is_file()


def ler(chave: str) -> bytes:
    return _caminho(chave).read_bytes()


def apagar(chave: str) -> bool:
    p = _caminho(chave)
    if p.is_file():
        p.unlink()
        return True
    return False


def _assinar(chave: str, ate: int, segredo: str) -> str:
    return hmac.new(segredo.encode(), f"{chave}|{ate}".encode(), hashlib.sha256).hexdigest()


def url_assinada(chave: str, segundos: int, segredo: str | None = None) -> str:
    from app.settings import settings

    _caminho(chave)  # valida
    ate = int(time.time()) + max(1, int(segundos))
    return f"/api/objetos/{chave}?ate={ate}&assinatura={_assinar(chave, ate, segredo or settings.PLAT_SECRET)}"


def assinatura_valida(chave: str, ate: int, assinatura: str, segredo: str | None = None) -> bool:
    from app.settings import settings

    if not CHAVE.match(chave) or ate < int(time.time()):
        return False
    esperada = _assinar(chave, ate, segredo or settings.PLAT_SECRET)
    return hmac.compare_digest(esperada, assinatura or "")
