#!/usr/bin/env python3
"""Publicador SEM CÓPIA das camadas do acervo (item L6-01-b-view-so-leitura; migração
20260906T15521aa_acervo_publicacao.sql). Roda como `postgres` (mesma identidade de `db/migrar.sh` e de
`scripts/acervo_sync.py`), com o psycopg2 do sistema — nunca como `plat_app`, que só LÊ.

    sudo -u postgres python3 scripts/acervo_publicar.py [--banco iagro_sat] [--schema plat] [--limite N]

Para cada linha de `plat.acervo_camada` com `estado = 'exposta'` e cujo servidor/banco é o desta máquina:

  1. GRANT SELECT da TABELA DE ORIGEM para `plat_acervo_publicador` (só dessa tabela; nada de ALL TABLES).
  2. CREATE OR REPLACE VIEW `plat_acervo.<nome>` com as colunas de `colunas_expostas` mais a coluna de
     geometria, e `WHERE plat.acervo_pode_ler('<acervo_camada_id>')`.
  3. ALTER VIEW ... OWNER TO plat_acervo_publicador  — é o privilégio DELE que a view usa na tabela de base.
  4. GRANT SELECT da view para `plat_app`. Nunca INSERT/UPDATE/DELETE: a view é só de leitura no BANCO, não
     só na aplicação (a prova negativa está em tests/api/test_acervo_publicacao.py).
  5. UPSERT em `plat.acervo_publicacao`.

Camada que saiu de 'exposta' (bloqueada, pendente de licença, ou sumiu do registro) tem a view DERRUBADA e a
linha de publicação apagada — é assim que a despublicação acontece, sem passo manual.

Por que a view é `security definer` (padrão) e não `security_invoker`, e por que não leva `security_barrier`:
está escrito no cabeçalho da migração, com as duas medidas que sustentam a decisão.

Nenhum nome de tabela é digitado aqui: tudo vem do registro. Identificadores vão para o SQL por
`psycopg2.sql.Identifier` (nunca formatação de string), e o `acervo_camada_id` vai como LITERAL citado por
`sql.Literal` porque precisa ser constante dentro do corpo da view.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime

import psycopg2
import psycopg2.extras
from psycopg2 import sql

PAPEL_PUBLICADOR = "plat_acervo_publicador"

SQL_EXPOSTAS = """
SELECT acervo_camada_id, servidor, banco, schema_nome, tabela, coluna_geom, srid, colunas_expostas
  FROM {schema}.acervo_camada
 WHERE estado = 'exposta' AND banco = %s
 ORDER BY acervo_camada_id
"""


def _log(msg: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {msg}", flush=True)


def nome_de_view(acervo_camada_id: str) -> str:
    """'<fonte_id>/<schema>.<tabela>' -> identificador estável, minúsculo, <= 63 bytes.

    Só o schema e a tabela entram no nome (o fonte_id é longo e já é chave em plat.acervo_publicacao); o que
    não é [a-z0-9_] vira '_'. Colisão é impossível na prática porque (schema, tabela) é único por banco, e o
    UNIQUE de plat.acervo_publicacao.view_nome reprova em voz alta se um dia deixar de ser.
    """
    alvo = acervo_camada_id.split("/", 1)[1] if "/" in acervo_camada_id else acervo_camada_id
    nome = re.sub(r"[^a-z0-9_]+", "_", alvo.lower()).strip("_")
    return nome[:63]


def publicar_uma(cur, schema: str, schema_views: str, papel_pub: str, papel_app: str, linha: dict) -> str:
    colunas = [c for c in (linha["colunas_expostas"] or []) if c != linha["coluna_geom"]]
    colunas_view = colunas + [linha["coluna_geom"]]
    view = nome_de_view(linha["acervo_camada_id"])
    ident_view = sql.Identifier(schema_views, view)
    ident_origem = sql.Identifier(linha["schema_nome"], linha["tabela"])

    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
        sql.Identifier(linha["schema_nome"]), sql.Identifier(papel_pub)))
    cur.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(ident_origem, sql.Identifier(papel_pub)))

    # DROP antes de CREATE: CREATE OR REPLACE VIEW recusa mudança de lista de colunas, e a lista branca muda
    # a cada varredura da casa (é o ponto do item L6-01-f endurecer essa lista depois).
    cur.execute(sql.SQL("DROP VIEW IF EXISTS {}").format(ident_view))
    cur.execute(
        sql.SQL("CREATE VIEW {} AS SELECT {} FROM {} WHERE {}.acervo_pode_ler({})").format(
            ident_view,
            sql.SQL(", ").join(sql.Identifier(c) for c in colunas_view),
            ident_origem,
            sql.Identifier(schema),
            sql.Literal(linha["acervo_camada_id"]),
        )
    )
    cur.execute(sql.SQL("ALTER VIEW {} OWNER TO {}").format(ident_view, sql.Identifier(papel_pub)))
    cur.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(ident_view, sql.Identifier(papel_app)))
    cur.execute(
        sql.SQL("""
            INSERT INTO {}.acervo_publicacao(acervo_camada_id, view_nome, schema_origem, tabela_origem,
                                             coluna_geom, srid, colunas, security_invoker, security_barrier,
                                             publicado_em)
            VALUES (%s, %s, %s, %s, %s, %s, %s, false, false, now())
            ON CONFLICT (acervo_camada_id) DO UPDATE SET
              view_nome = EXCLUDED.view_nome, schema_origem = EXCLUDED.schema_origem,
              tabela_origem = EXCLUDED.tabela_origem, coluna_geom = EXCLUDED.coluna_geom,
              srid = EXCLUDED.srid, colunas = EXCLUDED.colunas, publicado_em = EXCLUDED.publicado_em
        """).format(sql.Identifier(schema)),
        (linha["acervo_camada_id"], view, linha["schema_nome"], linha["tabela"], linha["coluna_geom"],
         linha["srid"], colunas_view),
    )
    return view


def despublicar(cur, schema: str, schema_views: str, camada_id: str, view: str) -> None:
    cur.execute(sql.SQL("DROP VIEW IF EXISTS {}").format(sql.Identifier(schema_views, view)))
    cur.execute(sql.SQL("DELETE FROM {}.acervo_publicacao WHERE acervo_camada_id = %s").format(
        sql.Identifier(schema)), (camada_id,))


def publicar(dsn_kwargs: dict, schema: str, banco: str, limite: int | None = None) -> dict:
    schema_views = f"{schema}_acervo"
    papel_pub = PAPEL_PUBLICADOR if schema == "plat" else f"{schema}_acervo_publicador"
    papel_app = "plat_app" if schema == "plat" else f"{schema}_app"
    conn = psycopg2.connect(**dsn_kwargs)
    conn.autocommit = False
    publicadas, removidas = [], []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql.SQL(SQL_EXPOSTAS).format(schema=sql.Identifier(schema)), (banco,))
            expostas = cur.fetchall()
            if limite:
                expostas = expostas[:limite]
            alvo = {li["acervo_camada_id"] for li in expostas}

            cur.execute(sql.SQL("SELECT acervo_camada_id, view_nome FROM {}.acervo_publicacao").format(
                sql.Identifier(schema)))
            ja = {r["acervo_camada_id"]: r["view_nome"] for r in cur.fetchall()}

            for camada_id, view in ja.items():
                if camada_id not in alvo and not limite:
                    despublicar(cur, schema, schema_views, camada_id, view)
                    removidas.append(camada_id)

            for linha in expostas:
                if not (linha["colunas_expostas"] or []):
                    continue  # lista branca vazia: não existe view sem coluna; fica fora do registro
                publicadas.append(publicar_uma(cur, schema, schema_views, papel_pub, papel_app, linha))
        conn.commit()
    finally:
        conn.close()
    _log(f"publicadas {len(publicadas)} · despublicadas {len(removidas)}")
    return {"publicadas": publicadas, "removidas": removidas}


def main() -> int:
    p = argparse.ArgumentParser(description="publica as camadas expostas do acervo como view só-leitura")
    p.add_argument("--banco", default="iagro_sat")
    p.add_argument("--schema", default="plat", help="schema do plat (plat, plat_homolog, plat_t<trilha>)")
    p.add_argument("--limite", type=int, default=None)
    a = p.parse_args()
    r = publicar({"dbname": a.banco}, a.schema, a.banco, a.limite)
    for v in r["publicadas"]:
        _log(f"  + {a.schema}_acervo.{v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
