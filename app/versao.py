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


def _diretorio_git() -> Path:
    """Num clone comum `.git` é diretório; num WORKTREE do git é um ARQUIVO com a linha
    `gitdir: /caminho/.git/worktrees/<nome>`. Sem seguir essa linha, toda árvore de trabalho paralela
    fica sem sha e o worker recusa a subir — foi o que aconteceu na banca do item L7-06-c."""
    git = ROOT / ".git"
    if git.is_file():
        conteudo = (_ler(git) or "")
        if conteudo.startswith("gitdir:"):
            apontado = Path(conteudo.split(":", 1)[1].strip())
            return apontado if apontado.is_absolute() else (ROOT / apontado)
    return git


def _sha_do_git() -> str | None:
    git = _diretorio_git()
    head = _ler(git / "HEAD")
    if not head:
        return None
    if not head.startswith("ref:"):
        return head if _HEX.match(head) else None
    ref = head.split(":", 1)[1].strip()
    direto = _ler(git / ref)
    if direto and _HEX.match(direto):
        return direto
    comum = _ler(git / "commondir")
    raiz_comum = (git / comum).resolve() if comum else git
    direto = direto or _ler(raiz_comum / ref)
    if direto and _HEX.match(direto):
        return direto
    empacotadas = _ler(raiz_comum / "packed-refs") or ""
    for linha in empacotadas.splitlines():
        partes = linha.split()
        if len(partes) == 2 and partes[1] == ref and _HEX.match(partes[0]):
            return partes[0]
    return None


def _sha_configurado() -> str | None:
    """PLAT_GIT_SHA do ambiente do processo ou do .env (que o install.sh grava a cada execução)."""
    valor = os.environ.get("PLAT_GIT_SHA", "")
    if not valor.strip():
        from app import settings as configuracao  # importação tardia: evita ciclo e dispensa .env nos testes de unidade

        try:
            valor = configuracao.obter().PLAT_GIT_SHA or ""
        except configuracao.ErroConfiguracao:
            valor = ""
    valor = valor.strip().lower()
    return valor if _HEX.match(valor) else None


@lru_cache(maxsize=1)
def git_sha() -> str:
    """Sha completo do commit atual; fora de um clone (instalação por tarball), PLAT_GIT_SHA do .env ou do ambiente."""
    return _sha_do_git() or _sha_configurado() or _sem_sha()


def _sem_sha() -> str:
    raise RuntimeError("git_sha indisponível: sem .git legível e sem PLAT_GIT_SHA no .env ou no ambiente")


def git_sha_curto(tamanho: int = 12) -> str:
    return git_sha()[:tamanho]
