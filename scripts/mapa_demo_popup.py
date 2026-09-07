"""Bancada de camadas do item L2-01-d-popup-runtime na base da TRILHA (nunca produção).

Cria, no inquilino `demo`, o material que o portão do item exige medir — cenários que a bancada de
L2-01-mapa-web (`mapa_demo_camadas.py`) não cobre porque ela é da tela, não do popup:

  1. `mapa-popup (L2-01-d)` — 30 pontos, com TRÊS deles (fid 1, 2, 3) na MESMA coordenada exata, para a
     paginação "1 de 3" entre feições coincidentes. Campos com todo tipo de formato do portão: número
     grande com casas configuradas, data (convenção de milissegundos desde a época — a mesma do item
     L2-10-c, `docs/EXPRESSAO.md`), moeda, URL, imagem, e um campo com HTML/script bruto (a refutação do
     item: tem de aparecer como TEXTO). Campo nulo em 1 de cada 5. Uma tabela COMPANHEIRA
     (`<tabela>_x`) guarda um campo que o MVT nunca carrega — a rota do popup faz o JOIN só quando o
     cliente pede aquela feição, o "consulta ao servidor por fid para campos não incluídos no tile" da
     hipótese do item.
  2. `mapa-popup-area (L2-01-d)` — 5 multipolígonos de duas peças com área DIFERENTE cada, e a
     configuração do popup traz uma expressão (`$area_m2 / 10000`, avaliada no servidor pelo núcleo do
     item L2-10-c) para a cláusula "expressão de área bate com ST_Area geográfica em 5 feições".

Uso:  set -a; source <env da trilha>; set +a
      venv/bin/python scripts/mapa_demo_popup.py criar|apagar
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
MARCA = "mapa-web-l2-01-d"

# uma data fixa e conhecida (2026-03-01 09:00:00 UTC), na convenção de milissegundos desde a época que
# o núcleo de expressão já usa (app/expressao/avaliador_py.py) — o mesmo número em qualquer fuso; quem
# muda com o fuso é só a FORMATAÇÃO na tela, nunca o valor gravado.
DATA_EVENTO_MS = 1772614800000
VALOR_GRANDE = 1234567.891  # a cláusula literal do portão: "1234567.891" -> "1.234.567,89" (2 casas)


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


def _publicar(cur, adm, titulo, tabela, tipo, campos, popup, simbologia=None):
    esquema = "d_demo"
    cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)",
                (esquema, tabela, tipo, adm["usuario_id"]))
    cur.execute(f'SELECT ST_Extent(geom)::text AS e, count(*) AS n FROM "{esquema}"."{tabela}"')
    r = cur.fetchone()
    caixa = r["e"] or ""
    nums = [float(v) for v in caixa.replace("BOX(", "").replace(")", "").replace(",", " ").split()] if caixa else []
    dados = {"schema": esquema, "tabela": tabela, "geometria": tipo, "srid": 4326, "campos": campos,
             "fonte": "hospedada", "marca": MARCA, "n_feicoes": r["n"],
             "extensao": nums if len(nums) == 4 else None, "popup": popup}
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

            # 1. pontos — pager, formatos e campo de servidor
            t = "c_" + _hex16()
            cur.execute(
                f'CREATE TABLE "d_demo"."{t}" (fid bigserial PRIMARY KEY, nome text, valor_numero '
                f'double precision, data_evento_ms double precision, preco double precision, '
                f'site text, foto text, obs_bruta text, geom geometry(Point, 4326))')
            # três feições EXATAMENTE coincidentes (fid 1, 2, 3) — a paginação "1 de 3"
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, valor_numero, data_evento_ms, preco, site, foto, '
                f'obs_bruta, geom) VALUES '
                f"('coincidente 1', %s, %s, 199.9, 'https://exemplo.iagrointel.com/ficha/1', "
                f"'https://exemplo.iagrointel.com/imagem/1.jpg', "
                f"'texto normal, sem marcação', ST_SetSRID(ST_MakePoint(-46.633, -23.55), 4326)), "
                f"('coincidente 2', 50.5, %s, 10.0, NULL, NULL, "
                f"'<script>alert(1)</script> nunca deve executar', "
                f"ST_SetSRID(ST_MakePoint(-46.633, -23.55), 4326)), "
                f"(NULL, NULL, %s, NULL, NULL, NULL, NULL, "
                f"ST_SetSRID(ST_MakePoint(-46.633, -23.55), 4326))",
                (VALOR_GRANDE, float(DATA_EVENTO_MS), float(DATA_EVENTO_MS), float(DATA_EVENTO_MS)))
            # mais 27 pontos espalhados, campo nulo em 1 de cada 5
            cur.execute(
                f'INSERT INTO "d_demo"."{t}" (nome, valor_numero, data_evento_ms, preco, site, foto, '
                f'obs_bruta, geom) '
                f"SELECT CASE WHEN g % 5 = 0 THEN NULL ELSE 'ponto ' || g END, "
                f"round((random() * 9000)::numeric, 2)::double precision, "
                f"{DATA_EVENTO_MS} + g::bigint * 86400000, "
                f"round((random() * 500)::numeric, 2)::double precision, "
                f"'https://exemplo.iagrointel.com/ficha/' || g, "
                f"'https://exemplo.iagrointel.com/imagem/' || g || '.jpg', "
                f"'observação ' || g, "
                f"ST_SetSRID(ST_MakePoint(-60.0 + (g % 30) * 0.5, -25.0 + (g % 20) * 0.5), 4326) "
                f"FROM generate_series(1, 27) g")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t}" USING gist(geom)')
            # tabela companheira: campo que o MVT NUNCA carrega (não é coluna da tabela tilada); a rota
            # do popup faz LEFT JOIN por fid só quando o campo está marcado "servidor" na configuração
            t_x = t + "_x"
            cur.execute(f'CREATE TABLE "d_demo"."{t_x}" (fid bigint PRIMARY KEY, nota_servidor text)')
            cur.execute(f'INSERT INTO "d_demo"."{t_x}" (fid, nota_servidor) '
                        f"SELECT fid, 'nota do servidor para o fid ' || fid "
                        f'FROM "d_demo"."{t}" WHERE fid <= 5')
            popup = {
                "titulo": "{nome}",
                "campos": [
                    {"nome": "nome", "rotulo": "Nome"},
                    {"nome": "valor_numero", "rotulo": "Valor", "formato": {"tipo": "numero", "decimais": 2}},
                    {"nome": "data_evento_ms", "rotulo": "Data do evento", "formato": {"tipo": "data"}},
                    {"nome": "preco", "rotulo": "Preço", "formato": {"tipo": "moeda"}},
                    {"nome": "site", "rotulo": "Site", "formato": {"tipo": "url"}},
                    {"nome": "foto", "rotulo": "Foto", "formato": {"tipo": "imagem"}},
                    {"nome": "obs_bruta", "rotulo": "Observação"},
                    {"nome": "nota_servidor", "rotulo": "Nota do servidor", "servidor": True},
                ],
            }
            saida["pontos"] = _publicar(
                cur, adm, "mapa-popup (L2-01-d, sintética)", t, "Point",
                [{"nome": "nome", "tipo": "text"}, {"nome": "valor_numero", "tipo": "double precision"},
                 {"nome": "data_evento_ms", "tipo": "double precision"}, {"nome": "preco", "tipo": "double precision"},
                 {"nome": "site", "tipo": "text"}, {"nome": "foto", "tipo": "text"}, {"nome": "obs_bruta", "tipo": "text"}],
                popup)
            saida["pontos"]["tabela_x"] = t_x

            # 2. multipolígonos com área conhecida — expressão de área do servidor
            t2 = "c_" + _hex16()
            cur.execute(f'CREATE TABLE "d_demo"."{t2}" (fid bigserial PRIMARY KEY, nome text, '
                        f'geom geometry(MultiPolygon, 4326))')
            cur.execute(
                f'INSERT INTO "d_demo"."{t2}" (nome, geom) '
                f"SELECT 'gleba ' || g, ST_Multi(ST_Union(ARRAY[ "
                f"  ST_Buffer(ST_SetSRID(ST_MakePoint(-55.0 + g * 0.4, -22.0), 4326), 0.01 * g), "
                f"  ST_Buffer(ST_SetSRID(ST_MakePoint(-55.0 + g * 0.4 + 0.05, -22.0 + 0.05), 4326), 0.01 * g)])) "
                f"FROM generate_series(1, 5) g")
            cur.execute(f'CREATE INDEX ON "d_demo"."{t2}" USING gist(geom)')
            popup2 = {
                "titulo": "{nome}",
                "campos": [{"nome": "nome", "rotulo": "Nome"}],
                "expressoes": [{"nome": "area_ha", "rotulo": "Área (ha)", "expressao": "$area_m2 / 10000",
                                "formato": {"tipo": "numero", "decimais": 4}}],
            }
            saida["poligonos"] = _publicar(
                cur, adm, "mapa-popup-area (L2-01-d, sintética)", t2, "MultiPolygon",
                [{"nome": "nome", "tipo": "text"}], popup2)
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
                cur.execute(f'DROP TABLE IF EXISTS "{it["e"]}"."{it["t"]}_x"')
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
        print("uso: mapa_demo_popup.py <criar|apagar>", file=sys.stderr)
        sys.exit(2)
