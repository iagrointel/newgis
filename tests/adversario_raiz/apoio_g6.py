"""Apoio comum aos testes do adversário G6: raiz do repositório e execução de script sem herdar
segredo nenhum do ambiente de quem chama."""

import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def rodar(argv, cwd=None, env=None, entrada=None):
    """Roda um comando e devolve (codigo, saida, erro). `env` é ACRESCENTADO ao ambiente atual."""
    amb = dict(os.environ)
    if env:
        amb.update(env)
    p = subprocess.run(
        argv, cwd=str(cwd or RAIZ), env=amb, input=entrada, capture_output=True, text=True, timeout=600
    )
    return p.returncode, p.stdout, p.stderr


def ler_env(caminho: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    if not caminho.exists():
        return d
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            d[chave.strip()] = valor
    return d
