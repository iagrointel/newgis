"""Apoio dos testes do item L2-05-a: uma camada vetorial pequena criada direto no schema de dado do inquilino
(como plat_app, no contexto do inquilino, com `plat.camada_preparar` — o mesmo caminho que a ingestão usa), o item
de catálogo correspondente pela API, e a limpeza pelo destruidor do tipo (mesmo padrão de tests/api/ingestao)."""

import uuid

from app.catalogo import destruidores
from tests import jobs_sessao
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

PONTOS = [("A", 1, -46.50, -23.40), ("B", 2, -46.51, -23.41), ("C", 3, -46.52, -23.42), ("D", 4, -46.53, -23.43),
          ("E", 5, -46.54, -23.44)]


def criar_camada(env, sessao, slug: str = "demo", pontos=PONTOS) -> dict:
    """Cria tabela d_<slug>.c_<16 hex> com campos nome/valor e geom Point 4326, e o item camada_vetorial."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids[slug], usuario_id=adm, login="admin")
        item_id = str(uuid.uuid4())
        tabela = "c_" + uuid.UUID(item_id).hex[:16]
        schema = f"d_{slug}"
        with con.cursor() as cur:
            cur.execute("SELECT to_regnamespace(%s) IS NULL AS falta", (schema,))
            if cur.fetchone()["falta"]:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, nome text, valor int, '
                        f'geom geometry(Point, 4326))')
            for nome, valor, x, y in pontos:
                cur.execute(f'INSERT INTO "{schema}"."{tabela}"(nome, valor, geom) VALUES (%s, %s, '
                            f'ST_SetSRID(ST_MakePoint(%s, %s), 4326))', (nome, valor, x, y))
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)", (schema, tabela, adm))
        con.commit()
    finally:
        con.close()
    r = sessao.post("/api/itens", json={
        "id": item_id, "tipo": "camada_vetorial", "titulo": f"{PREFIXO_TESTE} pontos {tabela[-6:]}",
        "dados": {"schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4326,
                  "campos": [{"nome": "nome", "tipo": "text"}, {"nome": "valor", "tipo": "integer"}],
                  "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    j = r.json()
    if j["id"] != item_id:  # a API pode ignorar o id pedido: a tabela segue válida, só o nome não deriva do id
        pass
    return {"id": j["id"], "schema": schema, "tabela": tabela, "titulo": j["titulo"], "feicoes": len(pontos)}


def apagar_itens(env, slug: str, ids: list[str]) -> None:
    """Lixeira + destruidor do tipo (apaga a tabela física) + expurgo, como plat_app no contexto do admin."""
    if not ids:
        return
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        tid = ids_por_slug(con)[slug]
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
            adm = cur.fetchone()["usuario_id"]
        contexto(con, tid, usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            for iid in ids:
                cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                item = cur.fetchone()
                if item is None:
                    continue
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                try:
                    destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"], lambda *_a: None)
                except destruidores.Recusado:
                    pass
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
        con.commit()
    finally:
        con.close()


def sha256_independente(env, slug: str, schema: str, tabela: str, campos: list[str]) -> str:
    """Recalcula o hash de conteúdo da camada com SQL escrito aqui (não o do executor): fid, campos e WKB da
    geometria em ordem de fid — a fórmula documentada em app/ferramentas/executor.py::sha256_camada."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        tid = ids_por_slug(con)[slug]
        contexto(con, tid, usuario_id=0, login="teste")
        cols = ", ".join(["fid"] + [f'"{c}"' for c in campos] + ["ST_AsBinary(geom)"])
        with con.cursor() as cur:
            cur.execute(f"SELECT encode(sha256(convert_to(coalesce(string_agg(md5(row({cols})::text), ',' "
                        f"ORDER BY fid), ''), 'UTF8')), 'hex') AS h FROM \"{schema}\".\"{tabela}\"")
            return cur.fetchone()["h"]
    finally:
        con.close()


def tabela_existe(env, schema: str, tabela: str) -> bool:
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        with con.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL AS e", (f'"{schema}"."{tabela}"',))
            return bool(cur.fetchone()["e"])
    finally:
        con.close()
