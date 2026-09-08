"""Portão do item L2-04-g-ogc-api-features-crs-cql2: Part 2 (CRS by reference), Part 3
(filtro CQL2-text/CQL2-JSON) e Part 4 (Create/Replace/Update/Delete) sobre o Part 1 já entregue
(item L2-04-servicos-esri-ogc). Reusa a mesma `FabricaCamada` de `test_edicao_transacional.py`
(tabela real, mesma `plat.camada_preparar`) em vez de duplicar a fixture."""

from __future__ import annotations

import json
import time

import psycopg2.errors
import psycopg2.extras
import pytest

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import contexto, ids_por_slug

SRID = 4674


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


def _criar_com_retentativa(fabrica, con, *args, **kwargs):
    """`plat.camada_schema_garantir` grava no MESMO schema físico `d_demo`/`d_demo2` que outras
    trilhas do laço (não isolado por trilha — confirmado em `trilha_ambiente.sh`, seção c2); o
    trinco de aconselhamento (ADR 0025, migração 20260907T0240) só protege contra contenção quando
    TODA sessão concorrente já carrega o trinco, e nem toda trilha em execução simultânea neste
    laço aplicou o mesmo commit ainda. Repetir com `rollback()` é a mitigação honesta do LADO do
    cliente: não esconde erro de código, só absorve uma corrida de infraestrutura que este item não
    controla — sem isto o portão fica refém do relógio de OUTRAS trilhas."""
    ultimo = None
    for tentativa in range(6):
        try:
            return fabrica.criar(*args, **kwargs)
        except psycopg2.errors.InternalError_ as e:
            if "concurrently updated" not in str(e):
                raise
            ultimo = e
            con.rollback()
            time.sleep(0.2 * (tentativa + 1))
    raise ultimo


@pytest.fixture
def camada(fabrica, conexao_plat_app):
    """Camada de pontos em `demo`: nome (text), area (double precision), quando (timestamp),
    categoria (text) — cobre comparação, temporal e IN/LIKE do portão CQL2."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = _criar_com_retentativa(
        fabrica, conexao_plat_app,
        "demo", ids["demo"], admin_id,
        campos=[
            {"nome": "nome", "tipo": "text"}, {"nome": "area", "tipo": "double precision"},
            {"nome": "quando", "tipo": "timestamp without time zone"}, {"nome": "categoria", "tipo": "text"},
        ],
        geometria="Point",
        edicao={"habilitada": True},
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


def _ponto(lon=-49.1, lat=-27.1):
    return {"type": "Point", "coordinates": [lon, lat]}


def _semear(sessao_a, camada_id, linhas):
    """Insere feições via a mesma porta de escrita (`/api/camadas/{id}/edicoes`) — nunca SQL direto,
    para o teste também confirmar que o dado semeado é visível pela rota OGC (RLS real)."""
    ids = []
    for nome, area, categoria, lon in linhas:
        r = sessao_a.post(f"/api/camadas/{camada_id}/edicoes", json={
            "adicionar": [{"atributos": {"nome": nome, "area": area, "categoria": categoria},
                           "geometria": _ponto(lon)}],
        })
        assert r.status_code == 200, r.text
        ids.append(r.json()["adicionar"][0])
    return ids


# ---------------------------------------------------------------------------------- Part 2: CRS by reference
def test_crs_31982_bate_com_st_transform(sessao_a, camada, conexao_plat_app):
    _semear(sessao_a, camada["id"], [("um", 10.0, "A", -49.1)])
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items")
    assert r.status_code == 200, r.text
    lon, lat = r.json()["features"][0]["geometry"]["coordinates"]

    contexto(conexao_plat_app, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s), 4326), 31982)) x, "
            "ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s), 4326), 31982)) y",
            [lon, lat, lon, lat],
        )
        esperado = cur.fetchone()
    conexao_plat_app.commit()

    r2 = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                       params={"crs": "http://www.opengis.net/def/crs/EPSG/0/31982"})
    assert r2.status_code == 200, r2.text
    assert r2.headers["Content-Crs"] == "<http://www.opengis.net/def/crs/EPSG/0/31982>"
    x, y = r2.json()["features"][0]["geometry"]["coordinates"]
    assert abs(x - esperado["x"]) < 0.01
    assert abs(y - esperado["y"]) < 0.01


def test_crs_epsg_curto_e_crs84_sao_aceitos(sessao_a, camada):
    _semear(sessao_a, camada["id"], [("um", 10.0, "A", -49.1)])
    for valor in ("EPSG:4326", "http://www.opengis.net/def/crs/OGC/1.3/CRS84", "CRS84"):
        r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"crs": valor})
        assert r.status_code == 200, (valor, r.text)


def test_crs_invalido_e_400(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"crs": "lixo-nenhum"})
    assert r.status_code == 400, r.text


def test_storage_crs_na_colecao(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0")
    assert r.status_code == 200, r.text
    assert r.json()["storageCrs"] == "http://www.opengis.net/def/crs/EPSG/0/4674"


def test_bbox_invertido_e_400(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"bbox": "10,10,0,0"})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------------- Part 3: CQL2
def test_filter_cql2_text_e_cql2_json_mesma_contagem(sessao_a, camada):
    _semear(sessao_a, camada["id"],
            [("um", 50.0, "A", -49.0), ("dois", 150.0, "B", -49.1), ("tres", 250.0, "A", -49.2)])
    r_text = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                           params={"filter": "area > 100"})
    assert r_text.status_code == 200, r_text.text
    r_json = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                           params={"filter": json.dumps({"op": ">", "args": [{"property": "area"}, 100]}),
                                    "filter-lang": "cql2-json"})
    assert r_json.status_code == 200, r_json.text
    assert r_text.json()["numberMatched"] == r_json.json()["numberMatched"] == 2


def test_filter_bate_com_sql_escrito_a_mao(sessao_a, camada, conexao_plat_app):
    _semear(sessao_a, camada["id"], [("um", 50.0, "A", -49.0), ("dois", 150.0, "B", -49.1)])
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"filter": "categoria = 'A'"})
    assert r.status_code == 200, r.text
    assert r.json()["numberMatched"] == 1

    contexto(conexao_plat_app, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(f'SELECT count(*) n FROM "{camada["dados"]["schema"]}"."{camada["dados"]["tabela"]}" '
                    f"WHERE categoria = 'A'")
        n = cur.fetchone()["n"]
    conexao_plat_app.commit()
    assert n == r.json()["numberMatched"]


def test_filter_in_like_between(sessao_a, camada):
    _semear(sessao_a, camada["id"], [("aaa", 5.0, "X", -49.0), ("abb", 15.0, "Y", -49.1), ("zzz", 25.0, "Z", -49.2)])
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                      params={"filter": "categoria IN ('X', 'Y')"})
    assert r.json()["numberMatched"] == 2
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"filter": "nome LIKE 'a%'"})
    assert r.json()["numberMatched"] == 2
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                      params={"filter": "area BETWEEN 10 AND 20"})
    assert r.json()["numberMatched"] == 1


def test_filter_espacial_s_dwithin(sessao_a, camada):
    _semear(sessao_a, camada["id"], [("perto", 1.0, "A", -49.1), ("longe", 1.0, "A", -10.0)])
    geom = json.dumps({"type": "Point", "coordinates": [-49.1, -27.1]})
    filtro = f"S_DWITHIN(geometria, '{geom}', 5000)"
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"filter": filtro})
    assert r.status_code == 200, r.text
    assert r.json()["numberMatched"] == 1
    assert r.json()["features"][0]["properties"]["nome"] == "perto"


def test_filter_temporal_datetime_aberto_na_query_param(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"datetime": "../2026-01-01"})
    assert r.status_code == 200, r.text
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"datetime": "2026-01-01/.."})
    assert r.status_code == 200, r.text
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"datetime": "nao-e-uma-data"})
    assert r.status_code == 400, r.text


def test_filter_funcao_desconhecida_400_nunca_500(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                      params={"filter": "FUNCAO_QUE_NAO_EXISTE(nome, 'x')"})
    assert r.status_code == 400, r.text
    assert r.status_code != 500


def test_filter_mil_clausulas_400_nunca_500(sessao_a, camada):
    filtro = " AND ".join("area > 1" for _ in range(1000))
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items", params={"filter": filtro})
    assert r.status_code == 400, r.text


def test_filter_campo_inexistente_400(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                      params={"filter": "campo_que_nao_existe = 1"})
    assert r.status_code == 400, r.text


def test_queryables_lista_campos_da_camada(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/queryables")
    assert r.status_code == 200, r.text
    props = r.json()["properties"]
    for campo in ("nome", "area", "categoria", "quando"):
        assert campo in props, props.keys()


def test_conformance_declara_crs_e_cql2(sessao_a, camada):
    r = sessao_a.get(f"/ogc/features/{camada['id']}/conformance")
    assert r.status_code == 200, r.text
    conf = r.json()["conformsTo"]
    assert any("crs" in c for c in conf)
    assert any("cql2-text" in c for c in conf)
    assert any("cql2-json" in c for c in conf)


# ---------------------------------------------------------------------------------- Part 4: CRUD transacional
def test_post_cria_feicao_e_devolve_location_e_etag(sessao_a, camada):
    r = sessao_a.post(f"/ogc/features/{camada['id']}/collections/0/items",
                       json={"type": "Feature", "properties": {"nome": "criada-ogc", "area": 42.0},
                             "geometry": _ponto()})
    assert r.status_code == 201, r.text
    assert "Location" in r.headers
    assert r.headers.get("ETag") == '"1"'
    fid = r.json()["id"]

    r2 = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items/{fid}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["properties"]["nome"] == "criada-ogc"
    assert r2.headers.get("ETag") == '"1"'


def test_put_substitui_com_if_match_correto(sessao_a, camada):
    r = sessao_a.post(f"/ogc/features/{camada['id']}/collections/0/items",
                       json={"type": "Feature", "properties": {"nome": "original", "area": 1.0},
                             "geometry": _ponto()})
    fid = r.json()["id"]
    etag = r.headers["ETag"]

    rput = sessao_a.put(f"/ogc/features/{camada['id']}/collections/0/items/{fid}",
                         headers={"If-Match": etag},
                         json={"type": "Feature", "properties": {"nome": "substituida", "area": 2.0},
                               "geometry": _ponto(-49.2)})
    assert rput.status_code == 204, rput.text
    novo_etag = rput.headers.get("ETag")
    assert novo_etag == '"2"'

    r2 = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items/{fid}")
    assert r2.json()["properties"]["nome"] == "substituida"


def test_put_com_if_match_desatualizado_e_412(sessao_a, camada):
    r = sessao_a.post(f"/ogc/features/{camada['id']}/collections/0/items",
                       json={"type": "Feature", "properties": {"nome": "original", "area": 1.0},
                             "geometry": _ponto()})
    fid = r.json()["id"]

    rput = sessao_a.put(f"/ogc/features/{camada['id']}/collections/0/items/{fid}",
                         headers={"If-Match": '"999"'},
                         json={"type": "Feature", "properties": {"nome": "x"}, "geometry": _ponto()})
    assert rput.status_code == 412, rput.text


def test_patch_atualiza_parcial(sessao_a, camada):
    r = sessao_a.post(f"/ogc/features/{camada['id']}/collections/0/items",
                       json={"type": "Feature", "properties": {"nome": "original", "area": 1.0, "categoria": "A"},
                             "geometry": _ponto()})
    fid = r.json()["id"]
    etag = r.headers["ETag"]

    rpatch = sessao_a.patch(f"/ogc/features/{camada['id']}/collections/0/items/{fid}",
                             headers={"If-Match": etag},
                             json={"type": "Feature", "properties": {"area": 99.0}})
    assert rpatch.status_code == 204, rpatch.text

    r2 = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items/{fid}")
    assert r2.json()["properties"]["area"] == 99.0
    assert r2.json()["properties"]["nome"] == "original"  # não mexido no PATCH parcial


def test_delete_apaga_feicao(sessao_a, camada):
    r = sessao_a.post(f"/ogc/features/{camada['id']}/collections/0/items",
                       json={"type": "Feature", "properties": {"nome": "para-apagar"}, "geometry": _ponto()})
    fid = r.json()["id"]
    etag = r.headers["ETag"]

    rdel = sessao_a.delete(f"/ogc/features/{camada['id']}/collections/0/items/{fid}", headers={"If-Match": etag})
    assert rdel.status_code == 204, rdel.text

    r2 = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items/{fid}")
    assert r2.status_code == 404, r2.text


# ---------------------------------------------------------------------------------- isolamento entre inquilinos
def test_colecao_de_b_ausente_para_token_de_a(sessao_a, sessao_b, camada):
    """Cláusula do portão: coleção de B ausente para token de A — aqui via SESSÃO de outro
    inquilino (B), que é o mecanismo de isolamento real desta plataforma (RLS por `plat.item`)."""
    r = sessao_b.get(f"/ogc/features/{camada['id']}/collections/0/items")
    assert r.status_code == 404, r.text
