"""Camada de TESTE do item L2-01-j-comparacao-cortina-tempo (controle de tempo do painel Comparar).

Nenhuma das três camadas reais do inquilino demo (Municípios de SP, Linhas de transmissão SP, Subestações
SP) tem campo de data/hora TIPADO: "Subestações SP (ONS SINDAT)" tem `dt_entrada`, mas guardado como
`text` (não `date`/`timestamp`), então BETWEEN nele seria comparação de string, não de data — o próprio
item pede, nesse caso, semear uma camada de teste (e apagá-la ao terminar).

100.000 pontos sintéticos no Brasil (mesmo bbox de `scripts/martin_demo_camadas.py`), com `data_evento
timestamptz` espalhado por 2020-01-01..2025-12-31: ~3% NULL (o portão exige provar que nulo nunca aparece
em nenhuma janela) e 1/4 das linhas gravadas via `AT TIME ZONE` de fusos diferentes (UTC, America/Sao_Paulo,
Asia/Kolkata, Etc/GMT+5) para provar que o filtro (sempre em UTC, sessão do Postgres é Etc/UTC — conferido
`SHOW TIME ZONE`) dá o mesmo resultado não importa o fuso de ORIGEM do dado — a comparação é sempre feita
sobre o instante armazenado (timestamptz normaliza na gravação), nunca sobre o texto.

Uso:  venv/bin/python scripts/comparar_demo_tempo.py criar   (idempotente: apaga e recria se já existir)
      venv/bin/python scripts/comparar_demo_tempo.py apagar
"""
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

DSN = os.environ["PLAT_DSN"]
MARCA = "comparar-demo-l2-01-j"
FUSOS = ["UTC", "America/Sao_Paulo", "Asia/Kolkata", "Etc/GMT+5"]


def _hex16():
    return secrets.token_hex(8)


def _admin(cur, slug):
    cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
    r = cur.fetchone()
    assert r, f"admin de {slug} não semeado"
    return r


def _contexto(cur, tenant_id, usuario_id, login):
    cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id),))
    cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(usuario_id),))
    cur.execute("SELECT set_config('plat.login', %s, false)", (login,))


def criar():
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        with con.cursor() as cur:
            adm = _admin(cur, "demo")
            _contexto(cur, adm["tenant_id"], adm["usuario_id"], "admin")

            esquema, tabela = "d_demo", "c_" + _hex16()
            cur.execute(
                f'CREATE TABLE "{esquema}"."{tabela}" '
                f'(fid bigserial PRIMARY KEY, rotulo text, data_evento timestamptz, '
                f'geom geometry(Point, 4326))'
            )
            fusos_sql = "ARRAY[" + ",".join(f"'{f}'" for f in FUSOS) + "]::text[]"
            cur.execute(
                f'INSERT INTO "{esquema}"."{tabela}" (rotulo, data_evento, geom) '
                f"SELECT 'p' || g, "
                f"  CASE WHEN random() < 0.03 THEN NULL ELSE "
                f"    (timestamp '2020-01-01' "
                f"     + (random() * (365 * 6))::int * interval '1 day' "
                f"     + (random() * 86400)::int * interval '1 second') "
                f"    AT TIME ZONE ({fusos_sql})[1 + (g % {len(FUSOS)})] "
                f"  END AS data_evento, "
                f"  ST_SetSRID(ST_MakePoint(-73.0 + random() * 39.0, -33.0 + random() * 28.0), 4326) "
                f"FROM generate_series(1, 100000) g"
            )
            cur.execute(f'CREATE INDEX ON "{esquema}"."{tabela}" USING gist(geom)')
            cur.execute(f'CREATE INDEX ON "{esquema}"."{tabela}" (data_evento)')
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)",
                        (esquema, tabela, adm["usuario_id"]))
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], "comparar-tempo-100k (L2-01-j, TESTE — apagar ao terminar)",
                 adm["usuario_id"], adm["usuario_id"],
                 json.dumps({
                     "schema": esquema, "tabela": tabela, "geometria": "Point", "srid": 4326,
                     "campos": [
                         {"nome": "rotulo", "tipo": "text", "alias": "rótulo"},
                         {"nome": "data_evento", "tipo": "timestamp with time zone", "alias": "data do evento"},
                     ],
                     "fonte": "hospedada", "marca": MARCA,
                 })),
            )
            item_id = cur.fetchone()["id"]
            cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema, tabela, item_id))
            funcao = cur.fetchone()["f"]
            cur.execute(f'SELECT count(*) AS n, count(data_evento) AS n_com_data FROM "{esquema}"."{tabela}"')
            n = cur.fetchone()

        con.commit()
        saida = {
            "esquema": esquema, "tabela": tabela, "funcao": funcao, "item": str(item_id),
            "n": n["n"], "n_com_data": n["n_com_data"], "tenant_id": adm["tenant_id"],
        }
        print(json.dumps(saida, indent=2))
        return saida
    finally:
        con.close()


def apagar():
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        with con.cursor() as cur:
            adm = _admin(cur, "demo")
            _contexto(cur, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute("SELECT id, dados->>'schema' AS esquema, dados->>'tabela' AS tabela FROM plat.item "
                        "WHERE dados->>'marca' = %s AND apagado_em IS NULL", (MARCA,))
            itens = cur.fetchall()
            for it in itens:
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (it["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (it["id"],))
                cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (it["esquema"], it["tabela"]))
                cur.execute(f'DROP TABLE IF EXISTS "{it["esquema"]}"."{it["tabela"]}"')
        con.commit()
        print(f"apagadas {len(itens)} camada(s) de teste do L2-01-j")
    finally:
        con.close()


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "criar"
    if acao == "criar":
        criar()
    elif acao == "apagar":
        apagar()
    else:
        print("uso: comparar_demo_tempo.py <criar|apagar>", file=sys.stderr)
        sys.exit(2)
