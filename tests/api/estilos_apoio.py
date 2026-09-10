"""Bancada do item L2-02-c (editor de simbologia): três camadas pequenas do inquilino demo no schema de dado,
com função de tile (`plat.camada_tile_garantir`) e de agrupamento (`plat.camada_tile_agrupado_garantir`) —
assim o Martin da trilha, ligado DEPOIS da bancada, serve as três. Idempotente por marca no título: os testes
de API e o e2e (processos diferentes) reusam a mesma bancada; `apagar` limpa no fim do item.

  pontos  1.000 pontos, campo `categoria` com 300 valores distintos (prova do 'outros'), `valor` numérico
  poligonos  200 polígonos, `uso` (5 valores) e `area_ha`
  linhas  100 linhas, `classe` e `extensao_km`
Dado sintético e declarado (nunca nome de cliente). Região: Guarulhos e entorno (onde a tela abre)."""

import random
import uuid

from app.catalogo import destruidores
from tests import jobs_sessao
from tests.api.test_rls import contexto, ids_por_slug

MARCA = "bancada estilo L2-02-c"
X0, Y0 = -46.60, -23.50


def _admin(con, slug):
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    return ids[slug], adm


def existentes(env, slug: str = "demo") -> dict:
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        tid, adm = _admin(con, slug)
        contexto(con, tid, usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT id, titulo, dados FROM plat.item WHERE tipo = 'camada_vetorial' AND apagado_em IS NULL "
                        "AND titulo LIKE %s", (MARCA + "%",))
            saida = {}
            for r in cur.fetchall():
                chave = r["titulo"].split(" ")[-1]
                saida[chave] = {"id": str(r["id"]), "titulo": r["titulo"], "schema": r["dados"]["schema"],
                                "tabela": r["dados"]["tabela"], "geometria": r["dados"]["geometria"],
                                "campos": [c["nome"] for c in r["dados"]["campos"]]}
            return saida
    finally:
        con.close()


def _publicar(cur, tid, adm, schema, tabela, titulo, geometria, campos, extent):
    dados = {"schema": schema, "tabela": tabela, "geometria": geometria, "srid": 4326,
             "campos": [{"nome": n, "tipo": t} for n, t in campos], "fonte": "hospedada",
             "estatisticas": {"feicoes": None, "extent_nativo": extent}}
    cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)", (schema, tabela, geometria, adm))
    import json
    cur.execute("INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, criado_por, modificado_por, dados, "
                "extent, extent_origem) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, %s::jsonb, "
                "ST_MakeEnvelope(%s, %s, %s, %s, 4326), 'dado') RETURNING id",
                (str(uuid.UUID(bytes=bytes.fromhex(tabela[2:]) + bytes(8))), tid, titulo, adm, adm, adm,
                 json.dumps(dados), *extent))
    item = str(cur.fetchone()["id"])
    cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s::uuid)", (schema, tabela, item))
    if geometria == "Point":
        cur.execute("SELECT plat.camada_tile_agrupado_garantir(%s, %s, %s::uuid)", (schema, tabela, item))
    return item


def criar(env, slug: str = "demo") -> dict:
    """Cria (ou devolve) a bancada; {pontos|poligonos|linhas: {id, schema, tabela, geometria, campos}}."""
    ja = existentes(env, slug)
    if len(ja) == 3:
        return ja
    rnd = random.Random(2026)
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        tid, adm = _admin(con, slug)
        contexto(con, tid, usuario_id=adm, login="admin")
        schema = f"d_{slug}"
        with con.cursor() as cur:
            cur.execute("SELECT to_regnamespace(%s) IS NULL AS falta", (schema,))
            if cur.fetchone()["falta"]:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            if "pontos" not in ja:
                t = "c_" + uuid.uuid4().hex[:16]
                cur.execute(f'CREATE TABLE "{schema}"."{t}" (fid bigserial PRIMARY KEY, categoria text, valor double '
                            f'precision, geom geometry(Point, 4326))')
                for i in range(1000):
                    cur.execute(f'INSERT INTO "{schema}"."{t}"(categoria, valor, geom) VALUES (%s, %s, '
                                f'ST_SetSRID(ST_MakePoint(%s, %s), 4326))',
                                (f"c{i % 300:03d}", rnd.lognormvariate(3, 1), X0 + rnd.random() * 0.4,
                                 Y0 + rnd.random() * 0.3))
                _publicar(cur, tid, adm, schema, t, f"{MARCA} pontos", "Point",
                          [("categoria", "text"), ("valor", "double precision")], [X0, Y0, X0 + 0.4, Y0 + 0.3])
            if "poligonos" not in ja:
                t = "c_" + uuid.uuid4().hex[:16]
                cur.execute(f'CREATE TABLE "{schema}"."{t}" (fid bigserial PRIMARY KEY, uso text, area_ha double '
                            f'precision, geom geometry(MultiPolygon, 4326))')
                usos = ["lavoura", "pastagem", "floresta", "urbano", "agua"]
                for i in range(200):
                    x = X0 + (i % 20) * 0.02
                    y = Y0 + (i // 20) * 0.03
                    cur.execute(f'INSERT INTO "{schema}"."{t}"(uso, area_ha, geom) VALUES (%s, %s, '
                                f'ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326)))',
                                (usos[i % 5], rnd.uniform(1, 1000), x, y, x + 0.018, y + 0.027))
                _publicar(cur, tid, adm, schema, t, f"{MARCA} poligonos", "MultiPolygon",
                          [("uso", "text"), ("area_ha", "double precision")], [X0, Y0, X0 + 0.4, Y0 + 0.3])
            if "linhas" not in ja:
                t = "c_" + uuid.uuid4().hex[:16]
                cur.execute(f'CREATE TABLE "{schema}"."{t}" (fid bigserial PRIMARY KEY, classe text, extensao_km '
                            f'double precision, geom geometry(MultiLineString, 4326))')
                for i in range(100):
                    x = X0 + rnd.random() * 0.4
                    y = Y0 + rnd.random() * 0.3
                    cur.execute(f'INSERT INTO "{schema}"."{t}"(classe, extensao_km, geom) VALUES (%s, %s, '
                                f'ST_Multi(ST_MakeLine(ST_SetSRID(ST_MakePoint(%s, %s), 4326), '
                                f'ST_SetSRID(ST_MakePoint(%s, %s), 4326))))',
                                (["rodovia", "vicinal", "ferrovia"][i % 3], rnd.uniform(0.5, 30), x, y,
                                 x + rnd.uniform(-0.05, 0.05), y + rnd.uniform(-0.05, 0.05)))
                _publicar(cur, tid, adm, schema, t, f"{MARCA} linhas", "MultiLineString",
                          [("classe", "text"), ("extensao_km", "double precision")], [X0, Y0, X0 + 0.4, Y0 + 0.3])
        con.commit()
    finally:
        con.close()
    return existentes(env, slug)


def apagar(env, slug: str = "demo") -> int:
    """Remove a bancada e os estilos ligados a ela (lixeira + destruidor + expurgo, como plat_app)."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    n = 0
    try:
        tid, adm = _admin(con, slug)
        contexto(con, tid, usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            cur.execute("SELECT id FROM plat.item WHERE apagado_em IS NULL AND (titulo LIKE %s OR (tipo = 'estilo' "
                        "AND titulo LIKE 'estilo · bancada estilo%%'))", (MARCA + "%",))
            ids = [str(r["id"]) for r in cur.fetchall()]
            for iid in ids:
                cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                item = cur.fetchone()
                if item is None:
                    continue
                if item["tipo"] == "camada_vetorial":
                    cur.execute("SELECT plat.camada_tile_apagar(%s, %s)",
                                (item["dados"]["schema"], item["dados"]["tabela"]))
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                try:
                    destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"], lambda *_a: None)
                except destruidores.Recusado:
                    pass
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
                n += 1
        con.commit()
    finally:
        con.close()
    return n


if __name__ == "__main__":
    import sys

    from tests.conftest import valores_env

    acao = sys.argv[1] if len(sys.argv) > 1 else "criar"
    if acao == "apagar":
        print("apagados:", apagar(valores_env()))
    else:
        for nome, c in criar(valores_env()).items():
            print(nome, c["id"], c["schema"], c["tabela"])
