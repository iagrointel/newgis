"""Cláusula 3 do portão: "regeneração do cliente a partir do OpenAPI atual não deixa diff (o
gerado é reproduzível)". Roda `scripts/gerar_sdk.sh` de novo num diretório temporário e compara
árvore a árvore com `sdk/python/src/plat_gerado/` comitado."""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
COMITADO = RAIZ / "sdk" / "python" / "src" / "plat_gerado"


def _arvore_de_arquivos(base: Path) -> set[str]:
    # .ruff_cache é o cache do post-hook `ruff format`/`ruff check` do próprio gerador (git-ignorado,
    # nunca comitado) — não faz parte do SDK gerado, é ruído de ambiente entre uma rodada e outra.
    return {
        str(p.relative_to(base))
        for p in base.rglob("*")
        if p.is_file() and ".ruff_cache" not in p.relative_to(base).parts
    }


def test_regeneracao_do_sdk_e_reproducivel():
    # o destino tem de ficar DENTRO do repositório: o post-hook `ruff format .`/`ruff check .` do
    # próprio gerador busca o pyproject.toml subindo diretórios a partir do destino — gerar num
    # /tmp qualquer (fora da árvore) faz o ruff cair nos padrões embutidos dele (outro
    # target-version, `Self` de `typing` em vez de `type[T]`/`TypeVar`) e o diff vira ruído do
    # ambiente, não do gerador. Gerado numa pasta irmã, git-ignorada, apagada ao final.
    destino = RAIZ / f".regeneracao_teste_{uuid.uuid4().hex[:8]}"
    try:
        resultado = subprocess.run(
            ["bash", str(RAIZ / "scripts" / "gerar_sdk.sh"), str(destino)],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        baixo = ("unable to parse", "duplicate", "traceback")
        saida = (resultado.stdout + resultado.stderr).lower()
        assert not any(m in saida for m in baixo), resultado.stdout + resultado.stderr

        arquivos_comitados = _arvore_de_arquivos(COMITADO)
        arquivos_gerados = _arvore_de_arquivos(destino)
        assert arquivos_comitados == arquivos_gerados, (
            f"só no comitado: {arquivos_comitados - arquivos_gerados}; "
            f"só na regeneração: {arquivos_gerados - arquivos_comitados}"
        )
        _, diferentes, erro = filecmp.cmpfiles(COMITADO, destino, sorted(arquivos_comitados), shallow=False)
        assert not diferentes and not erro, f"diff em: {diferentes}; erro ao comparar: {erro}"
    finally:
        shutil.rmtree(destino, ignore_errors=True)
