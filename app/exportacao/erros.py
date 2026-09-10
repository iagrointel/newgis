"""Saneamento do erro do banco antes de ele virar corpo de resposta 400 (item L0-04-h-exportar).

O portão do item pede: "export com where inválido devolve 400 com o erro do banco saneado". Devolver o erro do
banco cru é o que o cliente PRECISA (sem ele, "filtro inválido" não diz o que corrigir) e ao mesmo tempo é o
que um atacante USA: a mensagem do PostgreSQL entrega o nome real do schema e da tabela interna
(`d_<inquilino>.c_<uuid>`), o texto do comando, a posição do caractere e, em alguns casos, valor de outra
linha. Saneado quer dizer: fica a primeira linha do `message_primary` e o SQLSTATE; some o nome interno da
tabela, o texto do comando (`LINE 1: ...`, `QUERY`, `CONTEXT`, `DETAIL`, `HINT`), caminho de arquivo e
qualquer coisa depois da primeira quebra de linha.

Não é um filtro de palavra: o que sai é montado a partir de UM campo conhecido (`diag.message_primary`), nunca
a partir do `str(excecao)` inteiro — lista de bloqueio erra por omissão, lista de permissão não.
"""

from __future__ import annotations

import re

from app import limites

MAX = limites.EXPORTACAO_ERRO_BANCO_MAX
_CAMINHO = re.compile(r"(/[\w.\-]+){2,}")
_TABELA_INTERNA = re.compile(r"\bd_[a-z0-9_\-]+\.c_[0-9a-f]+\b|\bc_[0-9a-f]{8,}\b|\bd_[a-z0-9_\-]{2,}\b")
_ESPACO = re.compile(r"\s+")


def sanear_erro_banco(excecao: Exception, *, apelido: str = "a camada") -> tuple[str, str | None]:
    """`(mensagem, sqlstate)` pronta para o corpo do 400. `apelido` substitui o nome interno da tabela."""
    diag = getattr(excecao, "diag", None)
    primaria = getattr(diag, "message_primary", None) if diag is not None else None
    sqlstate = getattr(diag, "sqlstate", None) if diag is not None else None
    if not primaria:
        # exceção que não é do psycopg2 (ou sem diagnóstico): só a classe, nunca o texto — o texto pode
        # carregar o comando inteiro (psycopg2 põe o SQL em str(e) quando não há diag)
        return (f"o banco recusou o filtro ({type(excecao).__name__})", sqlstate)
    texto = str(primaria).splitlines()[0]
    texto = _TABELA_INTERNA.sub(apelido, texto)
    texto = _CAMINHO.sub("(caminho)", texto)
    texto = _ESPACO.sub(" ", texto).strip()
    if len(texto) > MAX:
        texto = texto[: MAX - 1].rstrip() + "…"
    return (texto, sqlstate)
