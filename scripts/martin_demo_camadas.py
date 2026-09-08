"""Cria as duas camadas de demonstração do item L2-01-b-martin-tiles-vetoriais na base da TRILHA.

Camada A ("demo-100k"): 100.000 pontos sintéticos dentro do Brasil, no inquilino demo. Serve para medir
latência de tile z8 frio/quente (p95 de 200 pedidos).

Camada B ("censo-1mi"): cópia SIMPLIFICADA de public.amc_setores_censitarios_2022 (dado aberto já na casa,
IBGE, 472.780 setores — o item fala em "1 mi de feições" mas a base real da casa tem 472.780; usamos o
número real, registrado honestamente na medida). Simplificada com ST_SimplifyPreserveTopology(0.0005 grau,
~50 m) para caber no orçamento de disco da trilha (D21, <=3 GB novos) sem descaracterizar a malha nacional.

Uso:  venv/bin/python scripts/martin_demo_camadas.py criar   (idempotente: apaga e recria se já existir)
      venv/bin/python scripts/martin_demo_camadas.py apagar
"""
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

DSN = os.environ["PLAT_DSN"]
MARCA = "martin-demo-l2-01-b"


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


def _criar_item(cur, tenant_id, usuario_id, titulo, esquema, tabela, campos):
    cur.execute(
        "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
        "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
        (tenant_id, titulo, usuario_id, usuario_id,
         json.dumps({"schema": esquema, "tabela": tabela, "geometria": "auto", "srid": 4326,
                     "campos": campos, "fonte": "hospedada", "marca": MARCA})),
    )
    return cur.fetchone()["id"]


def _token(cur, tenant_id, usuario_id, item_id, nome):
    import hashlib
    valor = "plat_" + secrets.token_urlsafe(64).replace("-", "x").replace("_", "y")[:43]
    hash_ = hashlib.sha256(valor.encode("utf-8")).hexdigest()
    cur.execute(
        "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (tenant_id, usuario_id, nome, hash_, valor[:8], ["camada:ler:" + str(item_id)]),
    )
    return valor, cur.fetchone()["id"]


def criar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    saida = {}
    try:
        with con.cursor() as cur:
            adm = _admin(cur, "demo")
            adm2 = _admin(cur, "demo2")
            _contexto(cur, adm["tenant_id"], adm["usuario_id"], "admin")

            # --- camada A: 100 mil pontos sintéticos, inquilino demo ---
            esquema_a, tabela_a = "d_demo", "c_" + _hex16()
            cur.execute(
                f'CREATE TABLE "{esquema_a}"."{tabela_a}" '
                f'(fid bigserial PRIMARY KEY, rotulo text, geom geometry(Point, 4326))'
            )
            cur.execute(
                f'INSERT INTO "{esquema_a}"."{tabela_a}" (rotulo, geom) '
                f"SELECT 'p' || g, ST_SetSRID(ST_MakePoint("
                f"-73.0 + random() * 39.0, -33.0 + random() * 28.0), 4326) "
                f"FROM generate_series(1, 100000) g"
            )
            cur.execute(f'CREATE INDEX ON "{esquema_a}"."{tabela_a}" USING gist(geom)')
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)",
                        (esquema_a, tabela_a, adm["usuario_id"]))
            item_a = _criar_item(cur, adm["tenant_id"], adm["usuario_id"], "demo-100k (L2-01-b)",
                                  esquema_a, tabela_a, [{"nome": "rotulo", "tipo": "text"}])
            cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema_a, tabela_a, item_a))
            funcao_a = cur.fetchone()["f"]
            token_a, token_a_id = _token(cur, adm["tenant_id"], adm["usuario_id"], item_a, "zt-demo100k")
            cur.execute("SELECT count(*) AS n FROM \"%s\".\"%s\"" % (esquema_a, tabela_a))
            n_a = cur.fetchone()["n"]

            # --- camada B: setores censitários simplificados, inquilino demo (marcada 'estática') ---
            esquema_b, tabela_b = "d_demo", "c_" + _hex16()
            cur.execute(
                f'CREATE TABLE "{esquema_b}"."{tabela_b}" '
                f'(fid bigserial PRIMARY KEY, cd_setor text, cd_uf text, nm_mun text, '
                f'geom geometry(MultiPolygon, 4326))'
            )
            cur.execute(
                f'INSERT INTO "{esquema_b}"."{tabela_b}" (cd_setor, cd_uf, nm_mun, geom) '
                f'SELECT cd_setor, cd_uf, nm_mun, '
                f'ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SimplifyPreserveTopology('
                f'ST_Transform(geom, 4326), 0.0005)), 3)) '
                f'FROM public.amc_setores_censitarios_2022'
            )
            cur.execute(f'DELETE FROM "{esquema_b}"."{tabela_b}" WHERE geom IS NULL OR ST_IsEmpty(geom)')
            cur.execute(f'CREATE INDEX ON "{esquema_b}"."{tabela_b}" USING gist(geom)')
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'MultiPolygon', %s)",
                        (esquema_b, tabela_b, adm["usuario_id"]))
            item_b = _criar_item(cur, adm["tenant_id"], adm["usuario_id"], "censo-setores (L2-01-b, estática)",
                                  esquema_b, tabela_b,
                                  [{"nome": "cd_setor", "tipo": "text"}, {"nome": "cd_uf", "tipo": "text"},
                                   {"nome": "nm_mun", "tipo": "text"}])
            cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema_b, tabela_b, item_b))
            funcao_b = cur.fetchone()["f"]
            token_b, token_b_id = _token(cur, adm["tenant_id"], adm["usuario_id"], item_b, "zt-censo")
            cur.execute('SELECT count(*) AS n FROM "%s"."%s"' % (esquema_b, tabela_b))
            n_b = cur.fetchone()["n"]

            # token do OUTRO inquilino (demo2), sem camada nenhuma lá — usado para o teste de RLS cruzada
            _contexto(cur, adm2["tenant_id"], adm2["usuario_id"], "admin")
            valor_b2 = "plat_" + secrets.token_urlsafe(64).replace("-", "x").replace("_", "y")[:43]
            import hashlib
            hash_b2 = hashlib.sha256(valor_b2.encode("utf-8")).hexdigest()
            cur.execute(
                "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (adm2["tenant_id"], adm2["usuario_id"], "zt-outro-inquilino", hash_b2, valor_b2[:8],
                 ["camada:ler"]),
            )
            token_b2_id = cur.fetchone()["id"]

        con.commit()
        saida = {
            "demo100k": {"esquema": esquema_a, "tabela": tabela_a, "funcao": funcao_a, "item": str(item_a),
                         "token": token_a, "token_id": token_a_id, "n": n_a,
                         "tenant_id": adm["tenant_id"], "usuario_id": adm["usuario_id"]},
            "censo": {"esquema": esquema_b, "tabela": tabela_b, "funcao": funcao_b, "item": str(item_b),
                      "token": token_b, "token_id": token_b_id, "n": n_b,
                      "tenant_id": adm["tenant_id"], "usuario_id": adm["usuario_id"]},
            "outro_inquilino": {"token": valor_b2, "token_id": token_b2_id, "tenant_id": adm2["tenant_id"],
                                 "usuario_id": adm2["usuario_id"]},
        }
        print(json.dumps(saida, indent=2))
    finally:
        con.close()
    return saida


def apagar():
    from app.schema_ambiente import CursorSchemaAmbiente
    con = psycopg2.connect(DSN, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        with con.cursor() as cur:
            adm = _admin(cur, "demo")
            _admin(cur, "demo2")
            _contexto(cur, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute("SELECT id, dados->>'schema' AS esquema, dados->>'tabela' AS tabela FROM plat.item "
                        "WHERE dados->>'marca' = %s AND apagado_em IS NULL", (MARCA,))
            itens = cur.fetchall()
            cur.execute("DELETE FROM plat.token_servico WHERE nome IN "
                        "('zt-demo100k', 'zt-censo', 'zt-outro-inquilino')")
            for it in itens:
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (it["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (it["id"],))
                cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (it["esquema"], it["tabela"]))
                cur.execute(f'DROP TABLE IF EXISTS "{it["esquema"]}"."{it["tabela"]}"')
        con.commit()
        print(f"apagadas {len(itens)} camada(s) de demonstração")
    finally:
        con.close()


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "criar"
    if acao == "criar":
        criar()
    elif acao == "apagar":
        apagar()
    else:
        print("uso: martin_demo_camadas.py <criar|apagar>", file=sys.stderr)
        sys.exit(2)
