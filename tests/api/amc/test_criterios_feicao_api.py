"""API do item L3-06-criterios-de-feicao: `/api/amc/criterios-feicao` e `/api/amc/criterios-feicao/exportar`.

Sem tabela própria (o pedido traz as feições e as camadas), então basta sessão autenticada com o privilégio
`analise.amc` — `sessao_a` (admin do inquilino demo) tem todos.

Aqui fica também a cláusula do portão que exige BANCO: **a contagem em raio conferida contra `ST_DWithin`**.
O motor mede em EPSG:31983 com geopandas/shapely; o Postgres refaz a mesma pergunta com PostGIS, sobre as
MESMAS 1.000 feições e os MESMOS 212 pontos de dado aberto, e as duas contagens têm de bater feição a feição.
"""

import csv
import io
import json
from pathlib import Path

import pytest

DADOS = Path(__file__).resolve().parents[2] / "dados"
SRID = 31983
RAIO_M = 1_000.0


def _carregar(nome: str) -> list[dict]:
    return json.loads((DADOS / nome).read_text(encoding="utf-8"))["features"]


@pytest.fixture(scope="module")
def feicoes() -> list[dict]:
    return _carregar("l3_06_feicoes.geojson")


@pytest.fixture(scope="module")
def pontos() -> list[dict]:
    return _carregar("l3_06_camada_pontos.geojson")


def _pedido(feicoes, pontos, **extra) -> dict:
    return {
        "feicoes": feicoes,
        "camadas": {"lugares": pontos},
        "criterios": [
            {"id": "area", "tipo": "atributo", "campo": "area_m2", "influencia": "positiva", "peso": 3,
             "minimo": 0, "maximo": 1000},
            {"id": "lugares_1km", "tipo": "contagem_raio", "camada": "lugares", "raio_m": RAIO_M,
             "influencia": "positiva", "peso": 2},
            {"id": "dist_lugar", "tipo": "distancia_mais_proxima", "camada": "lugares", "influencia": "inversa",
             "peso": 2},
            {"id": "area_ideal", "tipo": "atributo", "campo": "area_m2", "influencia": "ideal", "alvo": 200,
             "alcance": 200, "peso": 1},
        ],
        **extra,
    }


def test_mil_pontos_quatro_criterios_pela_api(sessao_a, feicoes, pontos):
    r = sessao_a.post("/api/amc/criterios-feicao", json=_pedido(feicoes, pontos))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["n_feicoes"] == 1_000 and corpo["n_incluidas"] == 1_000
    assert corpo["crs"]["srid_trabalho"] == SRID, "a zona UTM SIRGAS 2000 do centróide do recorte é a 23S"
    assert len(corpo["histogramas"]) == 4
    assert len(corpo["correlacao"]["matriz"]) == 4
    assert corpo["aviso_pesos"] == "pesos escolhidos pelo usuário, não medidos"
    posicoes = sorted(linha["posicao"] for linha in corpo["linhas"] if linha["posicao"] is not None)
    assert posicoes == list(range(1, 1_001))


def test_contagem_em_raio_confere_com_st_dwithin(sessao_a, conexao_plat_app, feicoes, pontos):
    """Cláusula do portão: a contagem em raio do motor contra `ST_DWithin` do PostGIS, feição a feição."""
    r = sessao_a.post("/api/amc/criterios-feicao", json=_pedido(feicoes, pontos))
    assert r.status_code == 200, r.text
    do_motor = {linha["id"]: linha["valores"]["lugares_1km"] for linha in r.json()["linhas"]}

    unidades = [(f["properties"]["id"], json.dumps(f["geometry"])) for f in feicoes]
    camada = [json.dumps(f["geometry"]) for f in pontos]
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "WITH u AS (SELECT id, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(g), 4326), %s) AS geom "
            "           FROM unnest(%s::text[], %s::text[]) AS t(id, g)), "
            "     c AS (SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(g), 4326), %s) AS geom "
            "           FROM unnest(%s::text[]) AS t(g)) "
            "SELECT u.id, count(c.geom) AS n "
            "FROM u LEFT JOIN c ON ST_DWithin(u.geom, c.geom, %s) GROUP BY u.id",
            (SRID, [i for i, _ in unidades], [g for _, g in unidades], SRID, camada, RAIO_M),
        )
        do_postgis = {linha["id"]: float(linha["n"]) for linha in cur.fetchall()}

    assert set(do_motor) == set(do_postgis)
    divergentes = {k: (do_motor[k], do_postgis[k]) for k in do_motor if do_motor[k] != do_postgis[k]}
    assert divergentes == {}, f"{len(divergentes)} feições divergem de ST_DWithin"
    assert sum(do_postgis.values()) > 0, "a conferência só vale se alguma feição realmente tem ponto no raio"


def test_export_csv_pela_api(sessao_a, feicoes, pontos):
    r = sessao_a.post("/api/amc/criterios-feicao/exportar?formato=csv", json=_pedido(feicoes, pontos))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    linhas = list(csv.reader(io.StringIO(r.text)))
    assert len(linhas) == 1_001
    assert linhas[0][:5] == ["id", "estado", "motivo_filtro", "posicao", "nota"]


def test_filtro_de_inclusao_marca_filtrada_pela_api(sessao_a, feicoes, pontos):
    pedido = _pedido(feicoes, pontos)
    pedido["criterios"][0]["faixa_inclusao"] = {"minimo": 100.0, "maximo": 400.0}
    r = sessao_a.post("/api/amc/criterios-feicao", json=pedido)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["n_filtradas"] > 0
    assert corpo["n_incluidas"] + corpo["n_filtradas"] == 1_000
    filtrada = next(linha for linha in corpo["linhas"] if linha["estado"] == "filtrada")
    assert filtrada["posicao"] is None and "fora da faixa de inclusão" in filtrada["motivo_filtro"]


def test_raio_zero_e_422(sessao_a):
    feicao = {"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {}}
    r = sessao_a.post("/api/amc/criterios-feicao", json={
        "feicoes": [feicao], "camadas": {"c": [feicao]},
        "criterios": [{"id": "x", "tipo": "contagem_raio", "camada": "c", "raio_m": 0, "influencia": "positiva"}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "raio_invalido"


def test_raio_de_mil_quilometros_e_422(sessao_a):
    feicao = {"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {}}
    r = sessao_a.post("/api/amc/criterios-feicao", json={
        "feicoes": [feicao], "camadas": {"c": [feicao]},
        "criterios": [{"id": "x", "tipo": "contagem_raio", "camada": "c", "raio_m": 1_000_000,
                       "influencia": "positiva"}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "raio_acima_do_teto"


def test_atributo_de_texto_e_422(sessao_a):
    r = sessao_a.post("/api/amc/criterios-feicao", json={
        "feicoes": [{"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]},
                     "properties": {"a": "grande"}}],
        "criterios": [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "atributo_nao_numerico"


def test_feicao_sem_geometria_e_422(sessao_a):
    r = sessao_a.post("/api/amc/criterios-feicao", json={
        "feicoes": [{"id": "f1", "geometry": None, "properties": {"a": 1.0}}],
        "criterios": [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "feicao_sem_geometria"


def test_acima_do_teto_sincrono_e_recusado(sessao_a):
    from app import limites
    feicao = {"geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {"a": 1.0}}
    r = sessao_a.post("/api/amc/criterios-feicao", json={
        "feicoes": [{**feicao, "id": f"f{i}"} for i in range(limites.AMC_CRITERIOS_FEICAO_MAX + 1)],
        "criterios": [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}]})
    assert r.status_code == 422, r.text


def test_sem_autenticacao_e_401():
    from tests.api.conftest import novo_cliente

    r = novo_cliente().post("/api/amc/criterios-feicao", json={
        "feicoes": [{"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]},
                     "properties": {"a": 1.0}}],
        "criterios": [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}]})
    assert r.status_code == 401, r.text
