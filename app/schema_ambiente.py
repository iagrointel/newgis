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
    """Reescrita de schema em cada ponto de entrada do cursor que carrega um comando SQL, e não só no `execute`
    com texto. Fica separada do cursor do psycopg2 de propósito: assim `tests/unit/test_schema_ambiente.py`
    monta a mesma reescrita sobre uma base espiã, sem banco, e confere método a método o que chegou ao driver.

    Por que a classe inteira e não um método de cada vez: em 06/09/2026 o mesmo defeito apareceu três vezes num
    dia (o `bytes` de `psycopg2.extras.execute_values`, as conexões de teste e o `executemany` de
    `POST`/`PUT /api/papeis`), e nas três a consequência foi a mesma — a consulta ia para o schema `plat` de
    produção mesmo com `PLAT_SCHEMA` apontando para outro lugar, e o 42501 que voltava chegava ao cliente
    disfarçado de "operação fora do inquilino da sessão". Uma prova de isolamento entre inquilinos que roda
    contra o schema errado não prova nada.

    `PONTOS_COM_CONSULTA` é a lista fechada do que é coberto; `PONTOS_FORA_DE_COBERTURA` diz o que ficou de
    fora e por quê. O teste de unidade reprova se aparecer um ponto de entrada novo que não esteja num dos dois."""

    # nome do método -> posição do argumento que carrega o comando (todos são o primeiro depois de self)
    PONTOS_COM_CONSULTA = ("execute", "executemany", "callproc", "mogrify", "copy_expert")
    PONTOS_FORA_DE_COBERTURA = {
        "copy_from": "recebe NOME de tabela (e a casa não usa: varrido em 06/09/2026 em app/, scripts/, db/ e "
                     "tests/). Se passar a usar, cobrir aqui — o nome também leva o prefixo do schema.",
        "copy_to": "recebe NOME de tabela e a casa não usa (mesma varredura de copy_from, 06/09/2026).",
        "stream_factory": "não existe no psycopg2 2.x; anotado para o caso de troca de driver.",
    }

    def execute(self, query, *args, **kwargs):
        # `psycopg2.extras.execute_values` (usado pelos importadores em lote da rede de utilidades,
        # L4-01-modelo-rede/L4-05-g-osm-power) monta a consulta em BYTES antes de chamar cur.execute
        # -- isinstance(query, str) nunca batia para essas chamadas, então o schema de homologação/
        # trilha nunca era aplicado nelas e o INSERT ia parar no `plat` de produção com permissão
        # negada (achado do item L4-05-g-osm-power). `_reescrever` trata texto e bytes e devolve o mesmo
        # tipo que entrou, então nada aqui precisa saber de codificação.
        return super().execute(self._reescrever(query), *args, **kwargs)

    def executemany(self, query, vars_list):
        # mesma classe de defeito do bytes/`execute_values` acima, achada agora em `cur.executemany`
        # (usado por `POST /api/papeis` para `plat.papel_privilegio`, app/auth/rotas_usuarios.py):
        # psycopg2 implementa executemany em C chamando pq_execute diretamente por linha, NUNCA
        # através do `self.execute()` Python — subclassificar só `execute()` não intercepta nada aqui.
        # Sem esta sobrecarga, o INSERT ia com o literal `plat.` para o schema de PRODUÇÃO em qualquer
        # ambiente isolado (trilha/homologação), e a permissão negada aparecia traduzida como "operação
        # fora do inquilino da sessão" — não uma checagem de inquilino, um schema errado na consulta.
        return super().executemany(self._reescrever(query), vars_list)

    def callproc(self, procname, *args, **kwargs):
        return super().callproc(self._reescrever(procname), *args, **kwargs)

    def mogrify(self, query, *args, **kwargs):
        return super().mogrify(self._reescrever(query), *args, **kwargs)

    def copy_expert(self, sql, *args, **kwargs):
        return super().copy_expert(self._reescrever(sql), *args, **kwargs)

    @staticmethod
    def _reescrever(consulta):
        """Reescreve texto OU bytes, devolvendo o mesmo tipo que entrou; qualquer outro tipo (por exemplo um
        `psycopg2.sql.Composed`, que a casa não usa) passa cru, como sempre passou. No-op quando os dois schemas
        já são o padrão: é o que garante que produção não paga nem uma regex.

        O caminho de bytes existe porque `psycopg2.extras.execute_values` monta o comando final com
        `b"".join(...)` e chama `cur.execute(bytes)`; o de `executemany` porque o `POST`/`PUT /api/papeis` grava
        os privilégios do papel por essa via."""
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
    """RealDictCursor que reescreve o texto da consulta para settings.PLAT_SCHEMA/PLAT_SCHEMA_TRABALHO antes de
    mandar ao servidor, em todos os pontos de entrada listados em `MixinReescritaSchema.PONTOS_COM_CONSULTA`.
    O mixin vem primeiro na MRO para que `super()` caia no cursor do psycopg2."""
