"""Bancada da cena 3D (item L2-09-b-cena-extrusao-slides) na base da TRILHA, nunca em produção.

Cria, no inquilino `demo`:

  1. `cena-edificacoes` — 4.000 pegadas de edificação SINTÉTICAS em quadra regular perto de Guarulhos,
     com `altura_m` (metros, de 3 a 60), `pavimentos` (inteiro, altura/3) e `uso` (texto). Sintética e
     declarada como tal: o portão do item confere que a caixa desenhada tem a altura DO ATRIBUTO, e
     para isso é preciso saber o valor esperado de cada feição — o que um recorte de dado real também
     daria, com muito mais tempo de máquina e nenhuma prova a mais.
     Três feições de propósito fora da curva, para a conferência de caso ruim: altura nula, altura
     negativa e altura ausente (NULL).
  2. `cena-demonstracao` — o item do tipo `cena` que aponta para a camada acima, com extrusão por
     `altura_m`, cor por faixa de altura e câmera inclinada.

Uso:  set -a; source <env da trilha>; set +a
      venv/bin/python scripts/cena_demo.py criar|apagar
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
MARCA = "cena-l2-09-b"
CENTRO = (-46.593018, -23.493476)
LADO_GRAU = 0.00025  # ~28 m de lado; quadra de 4.000 edificações cabe no campo de visão inclinado
N_EDIF = int(os.environ.get("CENA_DEMO_N", "4000"))
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    return secrets.choice("01234567") + "".join(secrets.choice(_CROCKFORD) for _ in range(25))


def _contexto(cur, slug):
    cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
    r = cur.fetchone()
    assert r, f"admin de {slug} não semeado"
    cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(r["tenant_id"]),))
    cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(r["usuario_id"]),))
    cur.execute("SELECT set_config('plat.login', 'admin', false)")
    return r


def criar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    saida, t0 = {}, time.perf_counter()
    try:
        with con.cursor() as cur:
            adm = _contexto(cur, "demo")
            tabela = "c_" + secrets.token_hex(8)
            cur.execute(f'CREATE TABLE "d_demo"."{tabela}" (fid bigserial PRIMARY KEY, nome text, uso text, '
                        f'altura_m double precision, pavimentos integer, geom geometry(Polygon, 4326))')
            lado = LADO_GRAU
            cur.execute(
                f'INSERT INTO "d_demo"."{tabela}" (nome, uso, altura_m, pavimentos, geom) '
                f"SELECT 'edificacao ' || g, (ARRAY['residencial','comercial','industrial'])[1 + (g % 3)], "
                f"alt, (alt / 3.0)::int, "
                f"ST_SetSRID(ST_MakeEnvelope(x, y, x + {lado * 0.7}, y + {lado * 0.7}, 4326), 4326) "
                f"FROM (SELECT g, {CENTRO[0]} + (g % 40) * {lado} AS x, "
                f"       {CENTRO[1]} + ((g / 40) % 100) * {lado} AS y, "
                f"       (3 + (g % 20) * 3)::double precision AS alt "
                f"      FROM generate_series(1, {N_EDIF}) g) s")
            # três casos ruins declarados: altura zero, negativa e ausente (o desenho tem de prendê-las em 0)
            cur.execute(
                f'INSERT INTO "d_demo"."{tabela}" (nome, uso, altura_m, pavimentos, geom) VALUES '
                f"('caso-altura-zero', 'residencial', 0, 0, ST_SetSRID(ST_MakeEnvelope("
                f"{CENTRO[0] - 3 * lado}, {CENTRO[1] - 3 * lado}, {CENTRO[0] - 2.3 * lado}, {CENTRO[1] - 2.3 * lado}, 4326), 4326)), "
                f"('caso-altura-negativa', 'residencial', -12, -4, ST_SetSRID(ST_MakeEnvelope("
                f"{CENTRO[0] - 5 * lado}, {CENTRO[1] - 3 * lado}, {CENTRO[0] - 4.3 * lado}, {CENTRO[1] - 2.3 * lado}, 4326), 4326)), "
                f"('caso-altura-nula', 'residencial', NULL, NULL, ST_SetSRID(ST_MakeEnvelope("
                f"{CENTRO[0] - 7 * lado}, {CENTRO[1] - 3 * lado}, {CENTRO[0] - 6.3 * lado}, {CENTRO[1] - 2.3 * lado}, 4326), 4326))")
            cur.execute(f'CREATE INDEX ON "d_demo"."{tabela}" USING gist(geom)')
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)",
                        ("d_demo", tabela, "Polygon", adm["usuario_id"]))
            cur.execute(f'SELECT ST_Extent(geom)::text AS e, count(*) AS n FROM "d_demo"."{tabela}"')
            r = cur.fetchone()
            caixa = (r["e"] or "").replace("BOX(", "").replace(")", "").replace(",", " ").split()
            campos = [{"nome": "nome", "tipo": "text"}, {"nome": "uso", "tipo": "text"},
                      {"nome": "altura_m", "tipo": "double precision"},
                      {"nome": "pavimentos", "tipo": "integer"}]
            dados = {"schema": "d_demo", "tabela": tabela, "geometria": "Polygon", "srid": 4326,
                     "campos": campos, "fonte": "hospedada", "marca": MARCA, "n_feicoes": r["n"],
                     "extensao": [float(v) for v in caixa] if len(caixa) == 4 else None,
                     "simbologia": {"tipo": "simples", "cor": "#c8b89a", "opacidade": 0.9, "contorno": "#6b5f4c"}}
            cur.execute("INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) "
                        "VALUES (%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                        (adm["tenant_id"], "cena-edificacoes (L2-09-b, sintética)", adm["usuario_id"],
                         adm["usuario_id"], json.dumps(dados)))
            camada_id = str(cur.fetchone()["id"])
            cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", ("d_demo", tabela, camada_id))
            funcao = cur.fetchone()["f"]

            corpo = {
                "camera": {"centro": [CENTRO[0] + 0.005, CENTRO[1] + 0.006], "zoom": 15.5,
                           "inclinacao": 60, "rotacao": 20},
                "terreno": {"ligado": False, "codificacao": "terrain-rgb", "tamanho_tile": 256,
                            "zoom_maximo": 14, "exagero": 1},
                "iluminacao": {"modo": "data_hora", "instante": "2026-06-21T12:00:00-03:00",
                               "intensidade": 0.35, "cor": "#ffffff"},
                "atmosfera": {"ceu": True, "cor_horizonte": "#a8c6dd",
                              "nevoa": {"ligada": True, "inicio": 0.7, "fim": 1, "cor": "#c9d6de"}},
                "camadas": [{
                    "id": _ulid(), "camada_id": camada_id, "titulo": "edificações (sintética)",
                    "visivel": True, "desenho": "extrusao", "opacidade": 0.95,
                    "cor_por_campo": {"campo": "altura_m", "paradas": [
                        {"valor": 0, "cor": "#e8ded0"}, {"valor": 30, "cor": "#c08a4a"},
                        {"valor": 60, "cor": "#7c3f18"}]},
                    "extrusao": {"campo_altura": "altura_m", "base_fixa": 0, "escala": 1,
                                 "gradiente_vertical": True},
                }],
                "slides": [],
            }
            cur.execute("INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) "
                        "VALUES (%s, 'cena', %s, %s, %s, %s::jsonb) RETURNING id",
                        (adm["tenant_id"], "cena-demonstracao (L2-09-b)", adm["usuario_id"], adm["usuario_id"],
                         json.dumps({"esquema_versao": 1, "corpo": corpo, "marca": MARCA})))
            cena_id = str(cur.fetchone()["id"])
        con.commit()
        saida = {"camada": {"item": camada_id, "tabela": tabela, "funcao": funcao, "n": r["n"]},
                 "cena": {"item": cena_id}, "segundos_total": round(time.perf_counter() - t0, 1)}
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
            cur.execute("SELECT id, tipo, dados->>'schema' AS e, dados->>'tabela' AS t FROM plat.item "
                        "WHERE dados->>'marca' = %s AND apagado_em IS NULL", (MARCA,))
            itens = cur.fetchall()
            for it in itens:
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (it["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (it["id"],))
                if it["tipo"] == "camada_vetorial" and it["e"] and it["t"]:
                    cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (it["e"], it["t"]))
                    cur.execute(f'DROP TABLE IF EXISTS "{it["e"]}"."{it["t"]}"')
        con.commit()
        print(f"apagados {len(itens)} item(ns) da bancada da cena")
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
        print("uso: cena_demo.py <criar|apagar>", file=sys.stderr)
        sys.exit(2)
