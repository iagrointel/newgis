"""Gera `docs/CLI.md` a partir do próprio `argparse` (item L0-14-cli-admin).

Nada aqui é escrito à mão: o texto de cada comando é a ajuda que o operador vê no terminal. Se a ajuda
mudar e o arquivo não for regenerado, `tests/api/test_cli_admin.py` reprova — mesma disciplina do
`docs/openapi.json` e do `docs/LIMITES.md`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

CABECALHO = """# Linha de comando `plat`

Gerado por `plat docs` a partir de `app/cli/principal.py` (não editar à mão).

`plat` administra a plataforma pelo terminal: inquilino, usuário, token, camada, job, evento, segredo e
saúde. Todo comando fala com a mesma API que o navegador usa, com a mesma sessão e os mesmos privilégios,
e por isso grava os mesmos eventos de auditoria que a tela gravaria.

- Ponto de entrada: `scripts/plat` no repositório; `venv/bin/plat` depois do `install.sh`.
- Credenciais: arquivo modo 600 com linhas `inquilino login senha` (`--credenciais`, padrão
  `tests/credenciais.txt`; variável `PLAT_CREDENCIAIS_ARQUIVO`).
- Segundo fator: arquivo modo 600 com `inquilino login segredo` (`--totp-arquivo`).
- **Senha nunca entra por argumento** — `--senha` e parentes são recusados de propósito, porque
  argumento aparece em `ps` e no journal do `sudo`. Use `--senha-stdin` ou `--senha-arquivo`.
- `--json` imprime a resposta da API como ela é, para uso em script.
- Saída: 0 sucesso, 2 falha prevista (mensagem em uma linha, sem rastro de pilha), 130 interrupção.
"""


def _bloco(titulo: str, parser: argparse.ArgumentParser, nivel: int) -> str:
    ajuda = parser.format_help().strip()
    return f"{'#' * nivel} `{titulo}`\n\n```\n{ajuda}\n```\n"


def _subparsers(parser: argparse.ArgumentParser):
    for acao in parser._actions:  # noqa: SLF001 - argparse não expõe isto de outro jeito
        if isinstance(acao, argparse._SubParsersAction):  # noqa: SLF001
            return acao
    return None


def gerar(parser: argparse.ArgumentParser) -> str:
    partes = [CABECALHO, _bloco("plat", parser, 2)]
    grupos = _subparsers(parser)
    if grupos is not None:
        for nome, sub in grupos.choices.items():
            partes.append(_bloco(f"plat {nome}", sub, 2))
            acoes = _subparsers(sub)
            if acoes is not None:
                for nome_acao, folha in acoes.choices.items():
                    partes.append(_bloco(f"plat {nome} {nome_acao}", folha, 3))
    return "\n".join(partes)


def escrever(destino: Path) -> str:
    from app.cli.principal import montar_parser

    texto = gerar(montar_parser())
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return texto
