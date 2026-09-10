"""Apoio dos testes do item L2-05-b: cria camadas de teste a partir de WKT (polígono, linha, ponto), lê de
volta o resultado de uma ferramenta como WKT e roda SQL solto na base da trilha para conferir número contra
número. Mesmo caminho de `apoio.criar_camada` (plat.camada_preparar como plat_app no contexto do inquilino);
o que muda é que aqui a geometria vem escrita no teste, para o mesmo dado poder ir ao shapely."""

import uuid

from tests import jobs_sessao
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

TIPOS = {"Polygon": "MultiPolygon", "LineString": "MultiLineString", "Point": "Point"}


def _conectar(env, slug: str):
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")
    return con, adm


def criar_camada_wkt(env, sessao, feicoes: list[dict], tipo: str = "Polygon", slug: str = "demo",
                     srid: int = 4326, rotulo: str = "camada") -> dict:
    """`feicoes` = [{"nome": str, "valor": int, "wkt": str}]. Grava a geometria como Multi quando o tipo pede."""
    tipo_col = TIPOS[tipo]
    con, adm = _conectar(env, slug)
    item_id = str(uuid.uuid4())
    tabela = "c_" + uuid.UUID(item_id).hex[:16]
    schema = f"d_{slug}"
    try:
        with con.cursor() as cur:
            cur.execute("SELECT to_regnamespace(%s) IS NULL AS falta", (schema,))
            if cur.fetchone()["falta"]:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, nome text, valor int, '
                        f'geom geometry({tipo_col}, {srid}))')
            envolver = "ST_Multi" if tipo_col.startswith("Multi") else ""
            for f in feicoes:
                cur.execute(f'INSERT INTO "{schema}"."{tabela}"(nome, valor, geom) VALUES (%s, %s, '
                            f'{envolver}(ST_GeomFromText(%s, {srid})))', (f["nome"], f["valor"], f["wkt"]))
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)", (schema, tabela, srid, tipo_col, adm))
        con.commit()
    finally:
        con.close()
    r = sessao.post("/api/itens", json={
        "id": item_id, "tipo": "camada_vetorial", "titulo": f"{PREFIXO_TESTE} {rotulo} {tabela[-6:]}",
        "dados": {"schema": schema, "tabela": tabela, "geometria": tipo_col, "srid": srid,
                  "campos": [{"nome": "nome", "tipo": "text"}, {"nome": "valor", "tipo": "integer"}],
                  "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    return {"id": r.json()["id"], "schema": schema, "tabela": tabela, "srid": srid,
            "titulo": r.json()["titulo"], "feicoes": len(feicoes)}


def consultar(env, slug: str, sql: str, parametros=()):
    """SQL de conferência na base da trilha, no contexto do inquilino (a RLS continua valendo)."""
    con, _ = _conectar(env, slug)
    try:
        with con.cursor() as cur:
            cur.execute(sql, parametros)
            return cur.fetchall()
    finally:
        con.close()


def ler_saida(env, slug: str, schema: str, tabela: str, colunas=()) -> list[dict]:
    """Feições da camada de saída em ordem de fid: {colunas pedidas} + wkt."""
    extra = "".join(f', "{c}"' for c in colunas)
    linhas = consultar(env, slug, f'SELECT fid{extra}, ST_AsText(geom) AS wkt FROM "{schema}"."{tabela}" '
                                  f'ORDER BY fid')
    return [dict(li) for li in linhas]


def tabela_do_item(env, slug: str, item_id: str) -> tuple[str, str]:
    r = consultar(env, slug, "SELECT dados->>'schema' AS s, dados->>'tabela' AS t FROM plat.item WHERE id = %s::uuid",
                  (item_id,))
    return r[0]["s"], r[0]["t"]


def criar_camada_grade(env, sessao, n_col: int, n_lin: int, passo: float, desloca: float = 0.0,
                       slug: str = "demo", rotulo: str = "grade") -> dict:
    """Malha de quadrados de lado `passo` a partir de (-46,6; -23,5), gerada no próprio banco (INSERT ... SELECT):
    serve às medidas de volume sem trafegar milhares de WKT pelo Python."""
    con, adm = _conectar(env, slug)
    item_id = str(uuid.uuid4())
    tabela = "c_" + uuid.UUID(item_id).hex[:16]
    schema = f"d_{slug}"
    try:
        with con.cursor() as cur:
            cur.execute("SELECT to_regnamespace(%s) IS NULL AS falta", (schema,))
            if cur.fetchone()["falta"]:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, nome text, valor int, '
                        f'geom geometry(MultiPolygon, 4326))')
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}"(nome, valor, geom) '
                f"SELECT 'q' || i || '_' || j, i * 1000 + j, ST_Multi(ST_MakeEnvelope("
                f"-46.6 + %(d)s + i * %(p)s, -23.5 + %(d)s + j * %(p)s, "
                f"-46.6 + %(d)s + (i + 1) * %(p)s, -23.5 + %(d)s + (j + 1) * %(p)s, 4326)) "
                f"FROM generate_series(0, %(c)s - 1) i, generate_series(0, %(l)s - 1) j",
                {"d": desloca, "p": passo, "c": n_col, "l": n_lin},
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'MultiPolygon', %s)", (schema, tabela, adm))
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
        con.commit()
    finally:
        con.close()
    r = sessao.post("/api/itens", json={
        "id": item_id, "tipo": "camada_vetorial", "titulo": f"{PREFIXO_TESTE} {rotulo} {tabela[-6:]}",
        "dados": {"schema": schema, "tabela": tabela, "geometria": "MultiPolygon", "srid": 4326,
                  "campos": [{"nome": "nome", "tipo": "text"}, {"nome": "valor", "tipo": "integer"}],
                  "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    return {"id": r.json()["id"], "schema": schema, "tabela": tabela, "srid": 4326,
            "titulo": r.json()["titulo"], "feicoes": n_col * n_lin}


def executar(env, slug: str, sql: str, parametros=()) -> None:
    """SQL de ESCRITA na base da trilha, com commit (o `consultar` acima abre e fecha sem gravar).
    Serve para semear camada de volume sem trafegar milhares de WKT pelo Python."""
    con, _ = _conectar(env, slug)
    try:
        with con.cursor() as cur:
            cur.execute(sql, parametros)
        con.commit()
    finally:
        con.close()
