#!/usr/bin/env python3
"""Gera o SQL que compõe por (tenant_id, ...) toda FK simples do schema `plat` entre tabelas que TÊM
`tenant_id` (item F2-FK151, lote 2; achado A1 do L4-01-a, mesma classe de 20260906T1815 e 20260906T1847).

Fonte ÚNICA do que NÃO compor: importa `PERMITIDAS` de
`tests/api/test_fk_composta_por_inquilino.py` — a mesma trava que reprova o produto reprova este
gerador (ele nunca emite composição para uma entrada listada lá), e um módulo novo que precisar da
mesma exceção (autoria com ator possivelmente de outro inquilino, D20) só adiciona uma linha em
PERMITIDAS; não precisa editar este arquivo.

Reexecutável: lê `pg_constraint` ao vivo (ambiente corrente — produção, homologação ou uma trilha,
via a mesma reescrita de schema que o resto do produto usa) e sempre emite DROP/ADD idempotente. Rodar
de novo depois que uma migração já compôs tudo não imprime nada (a varredura não acha mais achados).

Uso:
    set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
    venv/bin/python db/gerar_fk_composta.py > db/migracoes/<carimbo>_fk_composta_por_inquilino_loteN.sql
"""

import os
import sys
from pathlib import Path

import psycopg2

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.schema_ambiente import CursorSchemaAmbiente  # noqa: E402
from tests.api.test_fk_composta_por_inquilino import PERMITIDAS  # noqa: E402

DELETE_SQL = {"a": None, "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}

CONSULTA = """
    SELECT
      nc.nspname AS schema_filha, tc.relname AS tabela_filha, con.conname AS nome,
      tf.relname AS tabela_alvo, con.confdeltype AS del_tipo,
      (SELECT array_agg(a.attname ORDER BY u.ord)
         FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
         JOIN pg_attribute a ON a.attrelid = tc.oid AND a.attnum = u.attnum) AS colunas_filha,
      (SELECT array_agg(a.attname ORDER BY u.ord)
         FROM unnest(con.confkey) WITH ORDINALITY AS u(attnum, ord)
         JOIN pg_attribute a ON a.attrelid = tf.oid AND a.attnum = u.attnum) AS colunas_alvo,
      EXISTS (SELECT 1 FROM pg_attribute x
                WHERE x.attrelid = tc.oid AND x.attname = 'tenant_id' AND NOT x.attisdropped) AS filha_tem_tenant,
      EXISTS (SELECT 1 FROM pg_attribute y
                WHERE y.attrelid = tf.oid AND y.attname = 'tenant_id' AND NOT y.attisdropped) AS alvo_tem_tenant
    FROM pg_constraint con
    JOIN pg_class tc ON tc.oid = con.conrelid
    JOIN pg_namespace nc ON nc.oid = tc.relnamespace
    JOIN pg_class tf ON tf.oid = con.confrelid
    WHERE con.contype = 'f' AND nc.nspname = 'plat'
    ORDER BY tc.relname, con.conname
"""


def achados(cur) -> list[dict]:
    cur.execute(CONSULTA)
    out = []
    for r in cur.fetchall():
        if not (r["filha_tem_tenant"] and r["alvo_tem_tenant"]):
            continue
        colunas_filha = list(r["colunas_filha"] or [])
        if "tenant_id" in colunas_filha:
            continue  # já composta (ou é o próprio tenant_id)
        chave = (r["tabela_filha"], colunas_filha[0] if colunas_filha else "")
        if chave in PERMITIDAS:
            continue  # exceção nomeada — nunca recompor aqui
        out.append({
            "filha": r["tabela_filha"], "nome": r["nome"], "alvo": r["tabela_alvo"],
            "del_tipo": r["del_tipo"], "colunas_filha": colunas_filha,
            "colunas_alvo": list(r["colunas_alvo"] or []),
        })
    return out


def emitir(lista: list[dict]) -> str:
    linhas: list[str] = []

    # 1. UNIQUE (tenant_id, <colunas do alvo>) em cada tabela-alvo — porta para a FK composta.
    alvos: dict[str, set[tuple[str, ...]]] = {}
    for a in lista:
        alvos.setdefault(a["alvo"], set()).add(tuple(a["colunas_alvo"]))
    for alvo in sorted(alvos):
        for cols in sorted(alvos[alvo]):
            nome_u = f"{alvo}_tenant_id_{'_'.join(cols)}_key"
            cols_sql = ", ".join(("tenant_id",) + cols)
            linhas.append(
                "DO $$ BEGIN\n"
                "  IF NOT EXISTS (\n"
                "    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid\n"
                "      JOIN pg_namespace n ON n.oid = t.relnamespace\n"
                f"    WHERE n.nspname = 'plat' AND t.relname = '{alvo}' AND c.conname = '{nome_u}'\n"
                "  ) THEN\n"
                f"    EXECUTE 'ALTER TABLE plat.{alvo} ADD CONSTRAINT {nome_u} UNIQUE ({cols_sql})';\n"
                "  END IF;\n"
                "END $$;"
            )

    # 2. cada FK: DROP da simples + ADD da composta, preservando a ação de ON DELETE original.
    for a in sorted(lista, key=lambda x: (x["filha"], x["nome"])):
        filha, alvo = a["filha"], a["alvo"]
        cf, ca = a["colunas_filha"], a["colunas_alvo"]
        novo_nome = f"{filha}_tenant_{'_'.join(cf)}_fkey"
        cols_filha_sql = ", ".join(("tenant_id",) + tuple(cf))
        cols_alvo_sql = ", ".join(("tenant_id",) + tuple(ca))
        del_clause = DELETE_SQL.get(a["del_tipo"])
        sufixo = ""
        if del_clause == "SET NULL":
            sufixo = f" ON DELETE SET NULL ({', '.join(cf)})"
        elif del_clause:
            sufixo = f" ON DELETE {del_clause}"
        linhas.append(f"ALTER TABLE plat.{filha} DROP CONSTRAINT IF EXISTS {a['nome']};")
        linhas.append(f"ALTER TABLE plat.{filha} DROP CONSTRAINT IF EXISTS {novo_nome};")
        linhas.append(
            f"ALTER TABLE plat.{filha} ADD CONSTRAINT {novo_nome}\n"
            f"  FOREIGN KEY ({cols_filha_sql}) REFERENCES plat.{alvo} ({cols_alvo_sql}){sufixo};"
        )
    return "\n".join(linhas)


def main() -> None:
    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        print("sem PLAT_DSN no ambiente — source a trilha primeiro (ver docstring)", file=sys.stderr)
        sys.exit(2)
    con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            lista = achados(cur)
    finally:
        con.close()
    if not lista:
        print("-- nenhum achado: nada para compor (varredura de pg_constraint vazia)", file=sys.stderr)
        return
    sys.stdout.write(emitir(lista) + "\n")


if __name__ == "__main__":
    main()
