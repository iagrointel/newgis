"""Bancada de camadas do item L2-01-h-selecao-filtros na base da TRILHA (nunca produção).

Cria, no inquilino `demo`, duas camadas hospedadas para medir o portão de pronto:

  1. `selecao-pontos`  200 pontos com campos nome(text)/area_m2(double)/situacao(text)/ativo(bool)/
                       criado_em(timestamptz) — cobre filtro CQL2 com AND/OR aninhado, data com fuso e
                       nulos (1 em cada 10 tem `situacao` nula). 20 desses pontos caem DENTRO de um
                       polígono conhecido (o quadrado [-50.05,-15.05]-[-49.95,-14.95]), os outros 180
                       ficam fora — é a base da cláusula "seleção por polígono de 20 feições".
  2. `selecao-alvo`    1 ponto único a ~300 m do centro do quadrado acima, para a seleção espacial
                       "A que está a <= 500 m de B" (deve entrar) e "<= 100 m" (não deve entrar).

Uso:  set -a; source <env da trilha>; set +a
      venv/bin/python scripts/selecao_demo_camadas.py criar|apagar
Idempotente: `criar` apaga a bancada anterior (mesma marca) antes de recriar.
"""
import json
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

DSN = os.environ["PLAT_DSN"]
MARCA = "selecao-filtro-l2-01-h"


def _hex16():
    return secrets.token_hex(8)


def _contexto(cur, slug):
    cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
    r = cur.fetchone()
    assert r, f"admin de {slug} não semeado"
    cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(r["tenant_id"]),))
    cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(r["usuario_id"]),))
    cur.execute("SELECT set_config('plat.login', 'admin', false)")
    return r


def _publicar(cur, adm, titulo, tabela, tipo, campos):
    esquema = "d_demo"
    cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)",
                (esquema, tabela, tipo, adm["usuario_id"]))
    cur.execute(f'SELECT count(*) AS n FROM "{esquema}"."{tabela}"')
    n = cur.fetchone()["n"]
    dados = {"schema": esquema, "tabela": tabela, "geometria": tipo, "srid": 4326, "campos": campos,
              "fonte": "hospedada", "marca": MARCA, "n_feicoes": n}
    cur.execute("INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) "
                "VALUES (%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], titulo, adm["usuario_id"], adm["usuario_id"], json.dumps(dados)))
    item = cur.fetchone()["id"]
    return {"item": str(item), "tabela": tabela, "n": n, "titulo": titulo}


def apagar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        with con.cursor() as cur:
            _contexto(cur, "demo")
            cur.execute("SELECT id, dados->>'schema' AS e, dados->>'tabela' AS t FROM plat.item "
                        "WHERE dados->>'marca' = %s AND apagado_em IS NULL", (MARCA,))
            itens = cur.fetchall()
            for it in itens:
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (it["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (it["id"],))
                cur.execute(f'DROP TABLE IF EXISTS "{it["e"]}"."{it["t"]}" CASCADE')
        con.commit()
        print(f"apagadas {len(itens)} camada(s) da bancada")
    finally:
        con.close()


def criar():
    from app.schema_ambiente import CursorSchemaAmbiente
    apagar()
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    saida = {}
    try:
        with con.cursor() as cur:
            adm = _contexto(cur, "demo")

            # 1. 200 pontos, 20 dentro do quadrado-alvo, campos com nulo e datas espalhadas
            t = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, nome text, '
                        f'area_m2 double precision, situacao text, ativo boolean, '
                        f'criado_em timestamptz, geom geometry(Point, 4326))')
            # 20 dentro do quadrado [-50.05,-15.05]-[-49.95,-14.95] (área 0.1° x 0.1°)
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, area_m2, situacao, ativo, criado_em, geom) '
                f"SELECT 'dentro ' || g, round((100 + random() * 400)::numeric, 1)::double precision, "
                f"CASE WHEN g % 10 = 0 THEN NULL ELSE (ARRAY['disponível','ocupado'])[1 + (g % 2)] END, "
                f"(g % 2 = 0), now() - (g || ' days')::interval, "
                f"ST_SetSRID(ST_MakePoint(-50.05 + random() * 0.1, -15.05 + random() * 0.1), 4326) "
                f"FROM generate_series(1, 20) g")
            # 180 fora, espalhados longe do quadrado-alvo
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, area_m2, situacao, ativo, criado_em, geom) '
                f"SELECT 'fora ' || g, round((100 + random() * 400)::numeric, 1)::double precision, "
                f"CASE WHEN g % 10 = 0 THEN NULL ELSE (ARRAY['disponível','ocupado'])[1 + (g % 2)] END, "
                f"(g % 2 = 0), now() - (g || ' days')::interval, "
                f"ST_SetSRID(ST_MakePoint(-60.0 + random() * 20.0, -25.0 + random() * 15.0), 4326) "
                f"FROM generate_series(1, 180) g")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
            saida["pontos"] = _publicar(
                cur, adm, "selecao-pontos (L2-01-h, sintética)", t, "Point",
                [{"nome": "nome", "tipo": "text"}, {"nome": "area_m2", "tipo": "double precision"},
                 {"nome": "situacao", "tipo": "text"}, {"nome": "ativo", "tipo": "boolean"},
                 {"nome": "criado_em", "tipo": "timestamp with time zone"}])
            saida["quadrado_alvo"] = {
                "type": "Polygon",
                "coordinates": [[[-50.05, -15.05], [-49.95, -15.05], [-49.95, -14.95],
                                  [-50.05, -14.95], [-50.05, -15.05]]],
            }

            # 2. um ponto-alvo a ~300 m do centro do quadrado (centro = -50.00,-15.00)
            t2 = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t2}" (fid bigserial PRIMARY KEY, nome text, '
                        f'geom geometry(Point, 4326))')
            # ~0.0027 graus de latitude ~= 300 m
            cur.execute(
                f'INSERT INTO "d_demo"."{t2}" (nome, geom) VALUES '
                f"('alvo-300m', ST_SetSRID(ST_MakePoint(-50.00, -15.00 + 0.0027), 4326))")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t2}" USING gist(geom)')
            saida["alvo"] = _publicar(cur, adm, "selecao-alvo (L2-01-h, sintética)", t2, "Point",
                                       [{"nome": "nome", "tipo": "text"}])
        con.commit()
    except Exception:
        con.rollback()
        raise
    print(json.dumps(saida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "criar"
    {"criar": criar, "apagar": apagar}[acao]()
