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

import os
import re

import psycopg2.extras

SCHEMA_PADRAO = "plat"
SCHEMA_TRABALHO_PADRAO = "plat_trabalho"

# "plat" só aparece como GUC (não como schema) logo depois de current_setting(' ou set_config(' — os
# dois únicos pontos do código (app e migrações) que abrem uma dessas chamadas com esse prefixo exato,
# sem espaço entre o parêntese e a aspa (conferido: as 16+12 ocorrências da árvore batem 1 a 1).
_SCHEMA = re.compile(r"(?<!current_setting\(')(?<!set_config\(')\bplat\b")
_TRABALHO = re.compile(r"\bplat_trabalho\b")


def esquemas_do_ambiente() -> tuple[str, str]:
    """Par (schema, schema_trabalho) do ambiente atual — fonte ÚNICA para quem roda FORA do processo da
    aplicação (script solto de `scripts/`, gerador de `docs/`, tarefa agendada). Dentro do processo o valor
    vem de `app.settings`, como sempre; quando `app.settings` não é importável (script rodado como
    `postgres` com o psycopg2 do sistema, sem venv e sem leitura do `.env`) cai nas variáveis de ambiente
    PLAT_SCHEMA/PLAT_SCHEMA_TRABALHO, que é como `laco/trilha_ambiente.sh` e `make homolog` passam o schema.
    Sem esta segunda porta, todo script solto ignora PLAT_SCHEMA e escreve no `plat` de produção (achado F9
    do adversário do reescritor de schema, 07/09/2026)."""
    try:
        from app.settings import settings
    except Exception:  # noqa: BLE001 — sem venv/.env: o ambiente é a única fonte que resta
        return (
            os.environ.get("PLAT_SCHEMA") or SCHEMA_PADRAO,
            os.environ.get("PLAT_SCHEMA_TRABALHO") or SCHEMA_TRABALHO_PADRAO,
        )
    return settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO


def reescrever_schema(sql: str, schema: str = SCHEMA_PADRAO, schema_trabalho: str = SCHEMA_TRABALHO_PADRAO) -> str:
    """Troca todo `plat`/`plat_trabalho` que é schema (não GUC) pelo nome do ambiente atual. No-op
    quando os dois já são o padrão — é isso que garante custo zero em produção."""
    if schema != SCHEMA_PADRAO:
        sql = _SCHEMA.sub(schema, sql)
    if schema_trabalho != SCHEMA_TRABALHO_PADRAO:
        sql = _TRABALHO.sub(schema_trabalho, sql)
    return sql


class MixinReescritaSchema:
    """Reescrita de schema em TODOS os pontos de entrada do cursor que carregam comando SQL.

    Por que um mixin com lista declarada, e não quatro métodos soltos: em 06/09/2026 o MESMO defeito apareceu
    três vezes num dia (o `bytes` que `psycopg2.extras.execute_values` manda ao cursor; o `executemany` que
    `POST`/`PUT /api/papeis` usa para gravar os privilégios do papel; o `copy_expert` da carga do
    geocodificador). Nos três casos a consulta escapou da reescrita e foi para o schema `plat` de PRODUÇÃO
    com PLAT_SCHEMA apontando para outro lugar, e o 42501 que voltava chegava ao cliente como 403 "operação
    fora do inquilino da sessão" — não uma checagem de inquilino, um schema errado na consulta. Tapar buraco
    por buraco deixava o próximo caminho aberto; a lista abaixo é confrontada com a API do driver em
    tests/unit/test_schema_ambiente.py, então um ponto de entrada novo sem decisão ESCRITA reprova a suíte.

    O import de app.settings é tardio (dentro da função) para não criar ciclo: app/settings.py não importa
    este módulo."""

    PONTOS_COM_CONSULTA = ("execute", "executemany", "callproc", "mogrify", "copy_expert")
    PONTOS_FORA_DE_COBERTURA = {
        "copy_from": "recebe NOME de tabela e a casa não usa este caminho em lugar nenhum; no dia em que usar, "
                     "o teste da trava reprova e obriga a cobrir antes de a homologação descobrir sozinha",
        "copy_to": "mesma razão do copy_from: só nome de tabela, sem uso em app/, scripts/ ou db/",
    }

    def execute(self, query, *args, **kwargs):
        return super().execute(self._reescrever(query), *args, **kwargs)

    def executemany(self, query, vars_list):
        return super().executemany(self._reescrever(query), vars_list)

    def callproc(self, procname, *args, **kwargs):
        return super().callproc(self._reescrever(procname), *args, **kwargs)

    def mogrify(self, query, *args, **kwargs):
        return super().mogrify(self._reescrever(query), *args, **kwargs)

    def copy_expert(self, sql, *args, **kwargs):
        return super().copy_expert(self._reescrever(sql), *args, **kwargs)

    @staticmethod
    def _reescrever(consulta):
        """Reescreve texto OU bytes, devolvendo o MESMO tipo que entrou; qualquer outro tipo (por exemplo um
        `psycopg2.sql.Composed`, que a casa não usa) passa cru, como sempre passou. No-op quando os dois
        schemas já são o padrão: é o que garante que produção não paga nem uma regex.

        O caminho de bytes existe porque `psycopg2.extras.execute_values` monta o comando final com
        `b"".join(...)` e chama `cur.execute(bytes)` — foi por aí que a carga em lote da rede de utilidades
        (itens L4-01/L4-05-g) escapou da reescrita."""
        schema, trabalho = esquemas_do_ambiente()  # tardio: evita ciclo settings <-> schema_ambiente
        if schema == SCHEMA_PADRAO and trabalho == SCHEMA_TRABALHO_PADRAO:
            return consulta  # caminho de produção: nenhuma regex roda, nem sobre texto nem sobre bytes
        if isinstance(consulta, str):
            return reescrever_schema(consulta, schema, trabalho)
        if isinstance(consulta, (bytes, bytearray)):
            try:
                texto = bytes(consulta).decode("utf-8")
            except UnicodeDecodeError:
                return consulta  # não é SQL em UTF-8: melhor mandar cru do que corromper o comando
            return reescrever_schema(texto, schema, trabalho).encode("utf-8")
        return consulta


class CursorSchemaAmbiente(MixinReescritaSchema, psycopg2.extras.RealDictCursor):
    """RealDictCursor que reescreve o texto da consulta para o schema do ambiente antes de mandar ao servidor,
    em todos os pontos de `MixinReescritaSchema.PONTOS_COM_CONSULTA`. O mixin vem PRIMEIRO na ordem de
    resolução para que `super()` caia no cursor do psycopg2."""
