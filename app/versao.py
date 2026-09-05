"""Versão do produto (arquivo VERSAO) e sha do git lido sem subprocesso (ADR 0001 seção 7)."""

import os
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HEX = re.compile(r"^[0-9a-f]{7,40}$")


def _ler(caminho: Path) -> str | None:
    try:
        return caminho.read_text(encoding="utf-8").strip()
    except OSError:
        return None


@lru_cache(maxsize=1)
def versao() -> str:
    """Conteúdo de VERSAO (uma linha, semver)."""
    return _ler(ROOT / "VERSAO") or "0.0.0"


def _sha_do_git() -> str | None:
    git = ROOT / ".git"
    head = _ler(git / "HEAD")
    if not head:
        return None
    if not head.startswith("ref:"):
        return head if _HEX.match(head) else None
    ref = head.split(":", 1)[1].strip()
    direto = _ler(git / ref)
    if direto and _HEX.match(direto):
        return direto
    empacotadas = _ler(git / "packed-refs") or ""
    for linha in empacotadas.splitlines():
        partes = linha.split()
        if len(partes) == 2 and partes[1] == ref and _HEX.match(partes[0]):
            return partes[0]
    return None


@lru_cache(maxsize=1)
def git_sha() -> str:
    """Sha completo do commit atual; fora de um clone, lê PLAT_GIT_SHA do ambiente (.env)."""
    sha = _sha_do_git()
    if sha:
        return sha
    alternativa = os.environ.get("PLAT_GIT_SHA", "").strip().lower()
    if _HEX.match(alternativa):
        return alternativa
    raise RuntimeError("git_sha indisponível: sem .git legível e sem PLAT_GIT_SHA no ambiente")


def git_sha_curto(tamanho: int = 12) -> str:
    return git_sha()[:tamanho]
