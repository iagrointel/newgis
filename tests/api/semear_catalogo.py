"""Semeadura de itens para medidas (ADR 0004 seção 7.6): N itens (padrão 10.000) no inquilino demo com títulos
acentuados, 3 tags, resumo e descrição, 1/7 de cada tipo, parte compartilhada com o inquilino; 1.000 em demo2.
Escreve direto como plat_app no contexto do admin (um INSERT com generate_series: o gatilho grava a versão de cada
um). Reutilizável pelo e2e. Uso: venv/bin/python -m tests.api.semear_catalogo [n_demo] [n_demo2]."""

import os
import sys
import time

import psycopg2
import psycopg2.extras

from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)
from tests.api.test_rls import contexto, ids_por_slug
from tests.conftest import valores_env

PREFIXO = "zt-semente"
TIPOS = ["mapa", "app", "arquivo", "camada_vetorial", "conexao", "painel", "modelo_amc"]
DADOS = {
    "mapa": '{"esquema_versao":1,"corpo":{}}',
    "app": '{"tipo":"app","esquema_versao":1,"corpo":{}}',
    "painel": '{"tipo":"painel","esquema_versao":1,"corpo":{}}',
    "arquivo": '{"chave":"arquivo/00000000-0000-0000-0000-000000000000/'
    + "a" * 64
    + '.bin","sha256":"'
    + "a" * 64
    + '","bytes":10,"content_type":"application/octet-stream","nome_original":"x.bin"}',
    "camada_vetorial": '{"schema":"' + os.environ.get("PLAT_SCHEMA_TRABALHO", "plat_trabalho")
    + '","tabela":"zt_semente","geometria":"Point","srid":4326,"campos":[],"fonte":"hospedada"}',
    "conexao": '{"protocolo":"wms","url":"https://exemplo.gov.br/wms"}',
    "modelo_amc": '{"esquema_versao":1,"fatores":[],"metodo":"soma_ponderada"}',
}
TITULOS = ["Município", "Rodovia", "Setor censitário", "Bacia hidrográfica", "Área de proteção", "Hexágono", "Ferrovia"]
SUFIXOS = ["norte", "sul", "leste", "oeste", "centro"]


def semear(con, slug: str, n: int) -> int:
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE titulo LIKE %s", (PREFIXO + "%",))
        existentes = cur.fetchone()["n"]
        if existentes >= n:
            return 0
        faltam = n - existentes
        cur.execute(
            """
            INSERT INTO plat.item(tenant_id, tipo, titulo, resumo, descricao, tags, dono_id, extent, extent_origem,
                                  dados, acesso)
            SELECT %s, t.tipo, %s || ' ' || tit.t || ' ' || suf.s || ' ' || g,
                   'Resumo do item ' || g || ' sobre ' || tit.t,
                   repeat('Descrição longa do item ' || g || ' com palavras como ' || tit.t || '. ', 12),
                   ARRAY['ibge', 'semente', lower(tit.t)],
                   %s,
                   ST_MakeEnvelope(-60 + (g %% 20), -30 + (g %% 15), -59 + (g %% 20), -29 + (g %% 15), 4326), 'dado',
                   t.dados::jsonb,
                   CASE WHEN g %% 4 = 0 THEN 'inquilino' ELSE 'privado' END
            FROM generate_series(1, %s) g
            JOIN LATERAL (SELECT (%s::text[])[1 + g %% 7] AS tipo) tp ON true
            JOIN LATERAL (SELECT tp.tipo, (%s::text[])[1 + g %% 7] AS dados) t ON true
            JOIN LATERAL (SELECT (%s::text[])[1 + g %% 7] AS t) tit ON true
            JOIN LATERAL (SELECT (%s::text[])[1 + g %% 5] AS s) suf ON true
            """,
            (ids[slug], PREFIXO, adm, faltam, TIPOS, [DADOS[t] for t in TIPOS], TITULOS, SUFIXOS),
        )
    con.commit()
    with con.cursor() as cur:  # sem estatística o planejador ignora o índice de texto (p95 medido: 2,8 s -> ms)
        cur.execute("ANALYZE plat.item")
    return faltam


def main(n_demo: int = 10_000, n_demo2: int = 1_000) -> None:
    env = valores_env()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        t0 = time.perf_counter()
        a = semear(con, "demo", n_demo)
        b = semear(con, "demo2", n_demo2)
        print(f"semeados demo={a} demo2={b} em {time.perf_counter() - t0:.1f} s")
    finally:
        con.close()


def apagar(con, slug: str) -> int:
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")
    with con.cursor() as cur:
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute("SELECT id FROM plat.item WHERE titulo LIKE %s", (PREFIXO + "%",))
        n = 0
        for r in cur.fetchall():
            cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (r["id"],))
            cur.execute("SELECT plat.item_expurgar(%s::uuid)", (r["id"],))
            n += 1
    con.commit()
    return n


if __name__ == "__main__":
    args = [int(x) for x in sys.argv[1:]]
    if args and args[0] == 0:
        env = valores_env()
        con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        print("apagados", apagar(con, "demo") + apagar(con, "demo2"))
    else:
        main(*args)
