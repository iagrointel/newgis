"""Bancada de camadas do item L2-01-mapa-web na base da TRILHA (nunca produção).

Cria, no inquilino `demo`, o conjunto que o portão do item exige medir:

  1. `mapa-1mi`      1.000.000 de pontos SINTÉTICOS espalhados uniformemente pelo Brasil. Sintético de
                     propósito e declarado como tal: distribuição uniforme é o caso PIOR para tile de zoom
                     baixo (no z0 o milhão inteiro cai num tile só), enquanto dado real é agrupado em
                     cidade e deixa a maioria dos tiles vazia. A medida do portão ("carrega 1 mi de
                     feições sem travar") sai daqui.
  2. `mapa-poligonos` 5.000 MULTIpolígonos com campos deliberadamente NULOS em 1 de cada 4 feições — é o
                     caso da refutação do item ("popup em feição com campo nulo e geometria multi").
  3. `mapa-linhas`    20.000 linhas, para a legenda e a medição de comprimento terem uma camada de linha.
  4. `mapa-extra-1..7` 1.000 pontos cada, só para a refutação "10 camadas ao mesmo tempo" ter 10 camadas.

Uso:  set -a; source <env da trilha>; set +a
      venv/bin/python scripts/mapa_demo_camadas.py criar|apagar
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
MARCA = "mapa-web-l2-01"
N_MI = int(os.environ.get("MAPA_DEMO_N", "1000000"))


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


def _publicar(cur, adm, titulo, tabela, tipo, campos, simbologia=None):
    """DDL já feita pelo chamador; aqui: camada_preparar + item no catálogo + função de tile."""
    esquema = "d_demo"
    cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)",
                (esquema, tabela, tipo, adm["usuario_id"]))
    cur.execute(f'SELECT ST_Extent(geom)::text AS e, count(*) AS n FROM "{esquema}"."{tabela}"')
    r = cur.fetchone()
    caixa = r["e"] or ""
    nums = [float(v) for v in caixa.replace("BOX(", "").replace(")", "").replace(",", " ").split()] if caixa else []
    dados = {"schema": esquema, "tabela": tabela, "geometria": tipo, "srid": 4326, "campos": campos,
             "fonte": "hospedada", "marca": MARCA, "n_feicoes": r["n"],
             "extensao": nums if len(nums) == 4 else None}
    if simbologia:
        dados["simbologia"] = simbologia
    cur.execute("INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) "
                "VALUES (%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], titulo, adm["usuario_id"], adm["usuario_id"], json.dumps(dados)))
    item = cur.fetchone()["id"]
    cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema, tabela, item))
    return {"item": str(item), "tabela": tabela, "funcao": cur.fetchone()["f"], "n": r["n"], "titulo": titulo}


def criar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    saida, t0 = {}, time.perf_counter()
    try:
        with con.cursor() as cur:
            adm = _contexto(cur, "demo")

            # 1. 1 milhão de pontos
            t = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, rotulo text, '
                        f'categoria text, valor double precision, geom geometry(Point, 4326))')
            ini = time.perf_counter()
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (rotulo, categoria, valor, geom) '
                f"SELECT 'ponto ' || g, (ARRAY['norte','sul','leste','oeste'])[1 + (g % 4)], "
                f"round((random() * 100)::numeric, 2)::double precision, "
                f"ST_SetSRID(ST_MakePoint(-73.0 + random() * 39.0, -33.0 + random() * 28.0), 4326) "
                f"FROM generate_series(1, {N_MI}) g")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
            seg_carga = round(time.perf_counter() - ini, 1)
            saida["um_milhao"] = _publicar(
                cur, adm, "mapa-1mi (L2-01, sintética)", t, "Point",
                [{"nome": "rotulo", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
                 {"nome": "valor", "tipo": "double precision"}],
                simbologia={"tipo": "valores_unicos", "campo": "categoria",
                            "valores": ["norte", "sul", "leste", "oeste"], "tamanho": 3})
            saida["um_milhao"]["segundos_carga"] = seg_carga

            # 2. 5.000 multipolígonos com campo nulo em 1 de cada 4
            t = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, nome text, '
                        f'classe text, area_ha double precision, geom geometry(MultiPolygon, 4326))')
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, classe, area_ha, geom) '
                f"SELECT CASE WHEN g % 4 = 0 THEN NULL ELSE 'gleba ' || g END, "
                f"CASE WHEN g % 4 = 0 THEN NULL ELSE (ARRAY['a','b','c'])[1 + (g % 3)] END, "
                f"CASE WHEN g % 4 = 0 THEN NULL ELSE round((random() * 500)::numeric, 1)::double precision END, "
                f"ST_Multi(ST_Union(ARRAY[ "
                f"  ST_Buffer(ST_SetSRID(ST_MakePoint(x, y), 4326), 0.02), "
                f"  ST_Buffer(ST_SetSRID(ST_MakePoint(x + 0.08, y + 0.08), 4326), 0.02)])) "
                f"FROM (SELECT g, -60.0 + (g % 100) * 0.35 AS x, -25.0 + ((g / 100) % 50) * 0.35 AS y "
                f"      FROM generate_series(1, 5000) g) s")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
            saida["poligonos"] = _publicar(
                cur, adm, "mapa-poligonos (L2-01, sintética, campos nulos)", t, "MultiPolygon",
                [{"nome": "nome", "tipo": "text"}, {"nome": "classe", "tipo": "text"},
                 {"nome": "area_ha", "tipo": "double precision"}],
                simbologia={"tipo": "simples", "cor": "#2f7f6f", "opacidade": 0.55, "contorno": "#0b3b33"})

            # 3. 20.000 linhas
            t = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, nome text, '
                        f'geom geometry(LineString, 4326))')
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, geom) '
                f"SELECT 'trecho ' || g, ST_SetSRID(ST_MakeLine("
                f"ST_MakePoint(-60.0 + (g % 200) * 0.2, -25.0 + ((g / 200) % 100) * 0.2), "
                f"ST_MakePoint(-60.0 + (g % 200) * 0.2 + 0.15, -25.0 + ((g / 200) % 100) * 0.2 + 0.1)), 4326) "
                f"FROM generate_series(1, 20000) g")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
            saida["linhas"] = _publicar(
                cur, adm, "mapa-linhas (L2-01, sintética)", t, "LineString",
                [{"nome": "nome", "tipo": "text"}],
                simbologia={"tipo": "simples", "cor": "#d98a2b", "largura": 1.5})

            # 4. sete camadas pequenas, só para a refutação das 10 camadas simultâneas
            saida["extras"] = []
            for i in range(1, 8):
                t = "c_" + _hex16()
                cur.execute(f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, rotulo text, '
                            f'geom geometry(Point, 4326))')
                cur.execute(
                    f'INSERT INTO "d_demo"."{t}" (rotulo, geom) '
                    f"SELECT 'e{i}-' || g, ST_SetSRID(ST_MakePoint("
                    f"-70.0 + random() * 35.0, -30.0 + random() * 25.0), 4326) "
                    f"FROM generate_series(1, 1000) g")
                cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
                saida["extras"].append(_publicar(
                    cur, adm, f"mapa-extra-{i} (L2-01, sintética)", t, "Point",
                    [{"nome": "rotulo", "tipo": "text"}]))
        con.commit()
        saida["segundos_total"] = round(time.perf_counter() - t0, 1)
        print(json.dumps(saida, indent=1, ensure_ascii=False))
    finally:
        con.close()
    return saida


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
                cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (it["e"], it["t"]))
                cur.execute(f'DROP TABLE IF EXISTS "{it["e"]}"."{it["t"]}"')
        con.commit()
        print(f"apagadas {len(itens)} camada(s) da bancada")
    finally:
        con.close()


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "criar"
    if acao == "criar":
        apagar()
        criar()
    elif acao == "apagar":
        apagar()
    else:
        print("uso: mapa_demo_camadas.py <criar|apagar>", file=sys.stderr)
        sys.exit(2)
