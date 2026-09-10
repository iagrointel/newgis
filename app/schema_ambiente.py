"""Faz o app (e o aplicador de migrações de homologação, `db/reescrever_homolog.py`, item L7-31) falarem
com um schema diferente de `plat`/`plat_trabalho` sem editar as dezenas de rotas que hoje escrevem
`plat.` na mão. Produção nunca paga custo: `reescrever_schema` devolve a mesma string quando o schema já
é o padrão (nenhuma consulta de produção passa pela regex). docs/HOMOLOGACAO.md explica o fluxo inteiro.

Por que uma reescrita de texto e não um refactor de cada rota: o hardcode "plat." está espalhado em
dezenas de arquivos (auth/, acervo/, catalogo/, jobs/) e crescendo a cada item novo; centralizar a troca
no cursor é o único jeito de a homologação nunca ficar um turno atrás da produção.

O que fica de fora de propósito: `current_setting('plat.tenant_id', ...)` e `set_config('plat.usuario_id',
...)` (e as demais ~10 chaves de mesmo padrão) são GUC customizado — um nome de configuração de SESSÃO,
global ao processo do Postgres, não um objeto dentro de um schema. O app usa o literal fixo nesses dois
pontos (app/db.py, app/jobs/worker.py, app/jobs/tarefas.py) em QUALQUER ambiente; reescrevê-los quebraria
a leitura porque quem grava (set_config) e quem lê (current_setting) deixariam de bater."""

import re

import psycopg2.extras

SCHEMA_PADRAO = "plat"
SCHEMA_TRABALHO_PADRAO = "plat_trabalho"

# "plat" só aparece como GUC (não como schema) logo depois de current_setting(' ou set_config(' — os
# dois únicos pontos do código (app e migrações) que abrem uma dessas chamadas com esse prefixo exato,
# sem espaço entre o parêntese e a aspa (conferido: as 16+12 ocorrências da árvore batem 1 a 1).
_SCHEMA = re.compile(r"(?<!current_setting\(')(?<!set_config\(')\bplat\b")
_TRABALHO = re.compile(r"\bplat_trabalho\b")
# item L6-01-b: as views de publicação sem cópia moram no schema `plat_acervo` e são de
# `plat_acervo_publicador`. Nenhum dos dois casa com `\bplat\b` (o `_` seguinte mata a fronteira de palavra),
# então sem esta linha uma trilha/homologação escreveria no `plat_acervo` de PRODUÇÃO. O grupo opcional
# mantém o sufixo do papel: plat_acervo_publicador -> <schema>_acervo_publicador.
_ACERVO = re.compile(r"\bplat_acervo(_publicador)?\b")


def reescrever_schema(sql: str, schema: str = SCHEMA_PADRAO, schema_trabalho: str = SCHEMA_TRABALHO_PADRAO) -> str:
    """Troca todo `plat`/`plat_trabalho` que é schema (não GUC) pelo nome do ambiente atual. No-op
    quando os dois já são o padrão — é isso que garante custo zero em produção."""
    if schema != SCHEMA_PADRAO:
        sql = _ACERVO.sub(lambda m: f"{schema}_acervo{m.group(1) or ''}", sql)
        sql = _SCHEMA.sub(schema, sql)
    if schema_trabalho != SCHEMA_TRABALHO_PADRAO:
        sql = _TRABALHO.sub(schema_trabalho, sql)
    return sql


class CursorSchemaAmbiente(psycopg2.extras.RealDictCursor):
    """RealDictCursor que reescreve o texto da consulta para settings.PLAT_SCHEMA/PLAT_SCHEMA_TRABALHO
    antes de mandar ao servidor. Import de app.settings é tardio (dentro do método) para não criar
    ciclo — app/settings.py não importa este módulo.

    `execute` também reescreve consulta em BYTES, não só `str` (achado do item L4-01-modelo-rede,
    06-07/09/2026): `psycopg2.extras.execute_values` monta a consulta final em bytes e chama
    `cur.execute(bytes)` por dentro — sem este ramo, qualquer `execute_values` contra uma tabela
    `plat.*` ia direto ao schema de PRODUÇÃO mesmo rodando numa base de trilha/homologação, porque
    o `isinstance(query, str)` original nunca via essas consultas. `app/rede_utilidades/topologia.py`
    (item L4-01-b) já tinha contornado o mesmo problema reimplementando `execute_values` à mão; o
    conserto aqui é no cursor, então nenhum chamador de `execute_values` (presente ou futuro) precisa
    saber disso."""

    def execute(self, query, *args, **kwargs):
        if isinstance(query, str):
            query = self._reescrever(query)
        elif isinstance(query, (bytes, bytearray)):
            query = self._reescrever_bytes(bytes(query))
        return super().execute(query, *args, **kwargs)

    def callproc(self, procname, *args, **kwargs):
        if isinstance(procname, str):
            procname = self._reescrever(procname)
        return super().callproc(procname, *args, **kwargs)

    @staticmethod
    def _schema_e_padrao() -> bool:
        from app.settings import settings  # tardio: evita ciclo settings <-> schema_ambiente

        return settings.PLAT_SCHEMA == SCHEMA_PADRAO and settings.PLAT_SCHEMA_TRABALHO == SCHEMA_TRABALHO_PADRAO

    @classmethod
    def _reescrever(cls, sql: str) -> str:
        if cls._schema_e_padrao():
            return sql  # caminho de produção: nenhuma regex roda
        from app.settings import settings

        return reescrever_schema(sql, settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO)

    @classmethod
    def _reescrever_bytes(cls, sql: bytes) -> bytes:
        if cls._schema_e_padrao():
            return sql  # caminho de produção: nenhuma decodificação roda
        return cls._reescrever(sql.decode("utf-8")).encode("utf-8")
