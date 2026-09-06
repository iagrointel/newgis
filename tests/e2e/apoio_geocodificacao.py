"""Apoio do e2e da geocodificação de tabela (item L2-11-a-geocodificacao-csv): contexto de job MÍNIMO para
rodar a tarefa `geocodificacao.lote` no processo do teste.

Por que existe: o e2e roda contra a URL interna real, mas a trilha em worktree não tem worker no ar. O mesmo
padrão já está em `tests/e2e/test_migracao.py`. O que este contexto NÃO faz é fingir: `progresso`, `log` e
`entrada` são silenciosos porque o e2e não afere nenhum deles — a prova da fila com worker de verdade está em
`tests/api/geocodificador/test_geocodificacao_csv.py`, que sobe um worker em subprocesso.
"""

from __future__ import annotations

import uuid

import psycopg2

from app import db as banco
from app.schema_ambiente import CursorSchemaAmbiente


def conexao_direta(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)


class CtxLocal:
    """Contexto de job com a mesma superfície que `app.geocodificador.lote` usa: db(), progresso(), log(),
    entrada(), verificar(), tenant_id, usuario_id, job_id."""

    def __init__(self, env, tenant_id: int, usuario_id: int, job_id: str):
        self.env = env
        self.tenant_id = int(tenant_id)
        self.usuario_id = int(usuario_id)
        self.job_id = uuid.UUID(str(job_id))
        self.entradas: list[dict] = []

    def db(self):
        return banco.db(banco.Contexto(self.tenant_id, self.usuario_id, "e2e"))

    def progresso(self, pct, mensagem=""):
        pass

    def log(self, nivel, mensagem):
        pass

    def verificar(self):
        pass

    def entrada(self, item_id, sha256: str, descricao: str = ""):
        self.entradas.append({"item_id": str(item_id) if item_id else None, "sha256": sha256,
                               "descricao": descricao})
