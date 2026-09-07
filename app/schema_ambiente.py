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


def reescrever_schema(sql: str, schema: str = SCHEMA_PADRAO, schema_trabalho: str = SCHEMA_TRABALHO_PADRAO) -> str:
    """Troca todo `plat`/`plat_trabalho` que é schema (não GUC) pelo nome do ambiente atual. No-op
    quando os dois já são o padrão — é isso que garante custo zero em produção."""
    if schema != SCHEMA_PADRAO:
        sql = _SCHEMA.sub(schema, sql)
    if schema_trabalho != SCHEMA_TRABALHO_PADRAO:
        sql = _TRABALHO.sub(schema_trabalho, sql)
    return sql


class CursorSchemaAmbiente(psycopg2.extras.RealDictCursor):
    """RealDictCursor que reescreve o texto da consulta para settings.PLAT_SCHEMA/PLAT_SCHEMA_TRABALHO
    antes de mandar ao servidor. Import de app.settings é tardio (dentro do método) para não criar
    ciclo — app/settings.py não importa este módulo."""

    def execute(self, query, *args, **kwargs):
        # `psycopg2.extras.execute_values` (usado pelos importadores em lote da rede de utilidades,
        # L4-01-modelo-rede/L4-05-g-osm-power) monta a consulta em BYTES antes de chamar cur.execute
        # -- isinstance(query, str) nunca batia para essas chamadas, então o schema de homologação/
        # trilha nunca era aplicado nelas e o INSERT ia parar no `plat` de produção com permissão
        # negada (achado do item L4-05-g-osm-power). Decodifica na codificação da conexão, reescreve
        # e devolve como texto -- psycopg2 aceita str no lugar de bytes sem custo extra.
        if isinstance(query, (bytes, bytearray)):
            from psycopg2 import extensions as _ext

            query = bytes(query).decode(_ext.encodings[self.connection.encoding])
        if isinstance(query, str):
            query = self._reescrever(query)
        return super().execute(query, *args, **kwargs)

    def executemany(self, query, vars_list):
        # mesma classe de defeito do bytes/`execute_values` acima, achada agora em `cur.executemany`
        # (usado por `POST /api/papeis` para `plat.papel_privilegio`, app/auth/rotas_usuarios.py):
        # psycopg2 implementa executemany em C chamando pq_execute diretamente por linha, NUNCA
        # através do `self.execute()` Python — subclassificar só `execute()` não intercepta nada aqui.
        # Sem esta sobrecarga, o INSERT ia com o literal `plat.` para o schema de PRODUÇÃO em qualquer
        # ambiente isolado (trilha/homologação), e a permissão negada aparecia traduzida como "operação
        # fora do inquilino da sessão" — não uma checagem de inquilino, um schema errado na consulta.
        if isinstance(query, (bytes, bytearray)):
            from psycopg2 import extensions as _ext

            query = bytes(query).decode(_ext.encodings[self.connection.encoding])
        if isinstance(query, str):
            query = self._reescrever(query)
        return super().executemany(query, vars_list)

    def callproc(self, procname, *args, **kwargs):
        if isinstance(procname, str):
            procname = self._reescrever(procname)
        return super().callproc(procname, *args, **kwargs)

    @staticmethod
    def _reescrever(sql: str) -> str:
        from app.settings import settings  # tardio: evita ciclo settings <-> schema_ambiente

        if settings.PLAT_SCHEMA == SCHEMA_PADRAO and settings.PLAT_SCHEMA_TRABALHO == SCHEMA_TRABALHO_PADRAO:
            return sql  # caminho de produção: nenhuma regex roda
        return reescrever_schema(sql, settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO)
