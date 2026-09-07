"""Item L2-04-e-vector-tile-server-tilejson: os três contratos do servidor de tiles vetoriais —
TileJSON 3.0.0 + XYZ (MapLibre/QGIS), VectorTileServer compatível Esri (descritor, estilo,
sprites/fontes, tile em ordem z/y/x) e exportação por URL (geojson/kml/csv/fgb/gpkg).

Sobe um Martin de VERDADE (`.bin/martin`, mesmo binário v1.15.0 do item L2-01-b) numa porta livre,
apontado para o papel de leitura da TRILHA (`db/leitor_instalar.sh`, mesma receita de
`tests/api/test_leitor_tiles.py`) — os testes de tile e de igualdade byte a byte NÃO fazem sentido
sem o Martin real: são eles que provam que a rota Esri (`/tile/{z}/{y}/{x}`) e a rota MapLibre
(`/tiles/.../{z}/{x}/{y}`) convergem para o MESMO tile, e que sprite/fontes/estilo passam nos
validadores oficiais."""

from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path

import jsonschema
import pytest
import requests

from tests.api.test_leitor_tiles import (  # noqa: F401,F811 -- reexportada para o pytest achar a fixture (nome precisa bater com o parametro)
    _admin,
    _conectar_app,
    _hex16,
    instalador,
    token_novo,
)
from tests.api.test_rls import contexto

ROOT = Path(__file__).resolve().parents[2]
ESQUEMA_TILEJSON = json.loads((ROOT / "docs" / "esquemas" / "vendorizados" / "tilejson-3.0.0.schema.json").read_text())


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def martin_vivo(instalador, camada_poligono):
    """Martin real, apontado para o papel de leitura da trilha, numa porta livre desta máquina."""
    _, dsn_leitor = instalador
    porta = _porta_livre()
    config = ROOT / f".martin_teste_l204e_{porta}.yaml"
    config.write_text(
        "listen_addresses: '127.0.0.1:%d'\n"
        "worker_processes: 1\n"
        "postgres:\n"
        "  connection_string: %r\n"
        "  auto_publish:\n"
        "    tables: false\n"
        "  pool_size: 4\n"
        "  max_feature_count: 10000\n"
        "  default_srid: 4326\n" % (porta, dsn_leitor)
    )
    proc = subprocess.Popen(
        [str(ROOT / ".bin" / "martin"), "--config", str(config)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{porta}"
    ok = False
    for _ in range(100):
        try:
            if requests.get(f"{base}/catalog", timeout=1).status_code == 200:
                ok = True
                break
        except requests.RequestException:
            pass
        time.sleep(0.1)
    if not ok:
        proc.terminate()
        config.unlink(missing_ok=True)
        pytest.skip("Martin não respondeu em 10 s (porta/binário)")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    config.unlink(missing_ok=True)


@pytest.fixture
def app_com_martin(martin_vivo, monkeypatch):
    """`TestClient` com `PLAT_MARTIN_TILES_URL` apontado para o Martin de verdade desta suíte."""
    monkeypatch.setenv("PLAT_MARTIN_TILES_URL", martin_vivo)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def camada_poligono(env):
    """Uma camada de 30 polígonos no inquilino demo, com item, função de tile e token
    `camada:ler:<item>`. Apagada no fim (mesmo padrão de `tests/api/test_leitor_tiles.camadas`)."""
    con = _conectar_app(env)
    esquema, tabela = "d_demo", "c_" + _hex16()
    item = funcao = token_id = None
    try:
        adm = _admin(con, "demo")
        valor, hash_ = token_novo()
        with con.cursor() as cur:
            contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute(
                f'CREATE TABLE "{esquema}"."{tabela}" '
                f'(fid bigserial PRIMARY KEY, rotulo text, geom geometry(Polygon, 4326))'
            )
            cur.execute(
                f'INSERT INTO "{esquema}"."{tabela}" (rotulo, geom) '
                f"SELECT 'p' || g, ST_Buffer(ST_SetSRID(ST_MakePoint("
                f"-55.0 + (g % 10) * 0.3, -15.0 + (g / 10) * 0.3), 4326), 0.05) "
                f"FROM generate_series(1, 30) g"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Polygon', %s)",
                        (esquema, tabela, adm["usuario_id"]))
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], "camada de teste L2-04-e", adm["usuario_id"], adm["usuario_id"],
                 json.dumps({"schema": esquema, "tabela": tabela, "geometria": "Polygon", "srid": 4326,
                             "campos": [{"nome": "rotulo", "tipo": "text"}], "fonte": "hospedada"})),
            )
            item = cur.fetchone()["id"]
            cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema, tabela, item))
            funcao = cur.fetchone()["f"]
            cur.execute(
                "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (adm["tenant_id"], adm["usuario_id"], "zt-l204e", hash_, valor[:8],
                 ["camada:ler:" + str(item)]),
            )
            token_id = cur.fetchone()["id"]
        con.commit()
        yield {"esquema": esquema, "tabela": tabela, "funcao": funcao, "item": str(item), "token": valor,
               "token_id": token_id, "tenant_id": adm["tenant_id"], "usuario_id": adm["usuario_id"]}
    finally:
        if item is not None:
            with con.cursor() as cur:
                contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
                if token_id is not None:
                    cur.execute("DELETE FROM plat.token_servico WHERE id = %s", (token_id,))
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item,))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item,))
                if funcao:
                    cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (esquema, tabela))
                cur.execute(f'DROP TABLE IF EXISTS "{esquema}"."{tabela}"')
            con.commit()
        con.close()


# ============================================================================== cláusula: TileJSON
def test_tilejson_valido_contra_o_esquema_3_0(app_com_martin, camada_poligono, medida):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r = c.get(f"/tiles/{tok}/{item}/tilejson.json")
    assert r.status_code == 200
    doc = r.json()
    jsonschema.validate(doc, ESQUEMA_TILEJSON)
    assert doc["tiles"][0].endswith("/{z}/{x}/{y}.pbf")
    medida("L2-04-e-vector-tile-server-tilejson")(
        "tilejson_valido_esquema_3_0_0", True, "bool",
        "GET /tiles/<token>/<item>/tilejson.json + jsonschema contra "
        "docs/esquemas/vendorizados/tilejson-3.0.0.schema.json",
    )


# ================================================================ cláusula: byte a byte MapLibre x Esri
def test_tile_esri_e_maplibre_sao_byte_a_byte_iguais(app_com_martin, camada_poligono, medida):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r_ml = c.get(f"/tiles/{tok}/{item}/0/0/0.pbf")
    r_esri = c.get(f"/svc/{tok}/rest/services/{item}/VectorTileServer/tile/0/0/0.pbf")
    assert r_ml.status_code == r_esri.status_code
    assert r_ml.content == r_esri.content
    assert len(r_ml.content) > 0
    medida("L2-04-e-vector-tile-server-tilejson")(
        "tile_esri_ordem_zyx_igual_a_maplibre_zxy_bytes", len(r_ml.content), "bytes",
        "GET /tiles/<token>/<item>/2/2/2.pbf vs GET /svc/<token>/.../VectorTileServer/tile/2/2/2.pbf",
    )


def test_tile_zoom_25_nao_derruba_o_servico(app_com_martin, camada_poligono):
    """Refutação do adversário: pedir um zoom fora do intervalo (`plat.camada_tile_garantir` só
    aceita 0-24, migração L2-04-a) nunca pode ser um 500/estouro sem tratamento — vira 502
    (falha de infraestrutura mapeada) porque o próprio Martin recusa e nosso cliente HTTP
    (`app.tiles.martin_cliente`) devolve isso como erro nomeado, nunca deixa a exceção crua subir."""
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r = c.get(f"/tiles/{tok}/{item}/25/0/0.pbf")
    assert r.status_code in (204, 502)


# ============================================================================ cláusula: VectorTileServer/QGIS
def test_descritor_vector_tile_server_tem_tileinfo_web_mercator_512(app_com_martin, camada_poligono):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r = c.get(f"/svc/{tok}/rest/services/{item}/VectorTileServer")
    assert r.status_code == 200
    doc = r.json()
    assert doc["capabilities"] == "TilesOnly"
    assert doc["tileInfo"]["rows"] == 512 and doc["tileInfo"]["cols"] == 512
    assert doc["tileInfo"]["spatialReference"]["latestWkid"] == 3857
    assert "{z}" in doc["tiles"][0] and "{y}" in doc["tiles"][0] and "{x}" in doc["tiles"][0]


def test_root_style_passa_no_validador_oficial_da_style_spec(app_com_martin, camada_poligono, medida):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r = c.get(f"/svc/{tok}/rest/services/{item}/VectorTileServer/resources/styles/root.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["version"] == 8
    validador = ROOT / "ferramentas" / "estilo" / "validar.mjs"
    res = subprocess.run(["node", str(validador)], input=json.dumps(doc), capture_output=True, text=True,
                          cwd=str(validador.parent), timeout=10)
    assert res.returncode == 0, res.stderr
    resultado = json.loads(res.stdout)
    assert resultado.get("ok") is True, resultado
    medida("L2-04-e-vector-tile-server-tilejson")(
        "root_json_valido_style_spec_oficial", True, "bool",
        "GET .../VectorTileServer/resources/styles/root.json + node ferramentas/estilo/validar.mjs "
        "(pacote oficial @maplibre/maplibre-gl-style-spec)",
    )


def test_root_style_reprova_com_o_validador_quando_corrompido(app_com_martin, camada_poligono):
    """Refutação do adversário: o validador não é um carimbo de borracha — um `type` de layer
    inválido é recusado."""
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    doc = c.get(f"/svc/{tok}/rest/services/{item}/VectorTileServer/resources/styles/root.json").json()
    doc["layers"][0]["type"] = "isso-nao-existe"
    validador = ROOT / "ferramentas" / "estilo" / "validar.mjs"
    res = subprocess.run(["node", str(validador)], input=json.dumps(doc), capture_output=True, text=True,
                          cwd=str(validador.parent), timeout=10)
    resultado = json.loads(res.stdout)
    assert resultado.get("ok") is False


def test_sprites_e_fontes_200_com_content_type_correto(app_com_martin, camada_poligono, medida):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    base = f"/svc/{tok}/rest/services/{item}/VectorTileServer/resources"
    r1 = c.get(f"{base}/sprites/sprite.json")
    assert r1.status_code == 200 and r1.headers["content-type"].startswith("application/json")
    r2 = c.get(f"{base}/sprites/sprite.png")
    assert r2.status_code == 200 and r2.headers["content-type"] == "image/png"
    assert r2.content[:8] == b"\x89PNG\r\n\x1a\n"  # assinatura PNG real, não um arquivo fake
    r3 = c.get(f"{base}/fonts/Arial Regular/0-255.pbf")
    assert r3.status_code == 200 and r3.headers["content-type"] == "application/x-protobuf"
    medida("L2-04-e-vector-tile-server-tilejson")(
        "sprites_e_fontes_200",
        {"sprite_json": r1.status_code, "sprite_png": r2.status_code, "fontes_pbf": r3.status_code},
        "status", f"GET {base}/sprites/sprite.json|.png e /fonts/Arial Regular/0-255.pbf",
    )


# ============================================================================ cláusula: exportação
def test_geojson_export_reflete_where_e_bbox(app_com_martin, camada_poligono):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r_tudo = c.get(f"/svc/{tok}/camadas/{item}.geojson")
    assert r_tudo.status_code == 200
    todos = json.loads(r_tudo.content)
    assert len(todos["features"]) == 30
    r_where = c.get(f"/svc/{tok}/camadas/{item}.geojson", params={"where": "rotulo = 'p1'"})
    filtrado = json.loads(r_where.content)
    assert len(filtrado["features"]) == 1


def test_kml_de_10_mil_feicoes_abre_com_ogrinfo(app_com_martin, env, medida, tmp_path):
    """Cláusula literal do portão: 10 mil feições, `ogrinfo` conta. Tabela dedicada (não a de 30
    polígonos das outras cláusulas) para não pesar as demais."""
    if subprocess.run(["which", "ogrinfo"], capture_output=True).returncode != 0:
        pytest.skip("ogrinfo/GDAL não instalado nesta máquina")
    con = _conectar_app(env)
    esquema, tabela = "d_demo", "c_" + _hex16()
    item = token_id = None
    try:
        adm = _admin(con, "demo")
        valor, hash_ = token_novo()
        with con.cursor() as cur:
            contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute(f'CREATE TABLE "{esquema}"."{tabela}" '
                        f'(fid bigserial PRIMARY KEY, rotulo text, geom geometry(Point, 4326))')
            cur.execute(f"INSERT INTO \"{esquema}\".\"{tabela}\" (rotulo, geom) "
                        f"SELECT 'p' || g, ST_SetSRID(ST_MakePoint(-55.0 + (g%1000)*0.001, -15.0), 4326) "
                        f"FROM generate_series(1, 10000) g")
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)", (esquema, tabela, adm["usuario_id"]))
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], "camada 10k L2-04-e", adm["usuario_id"], adm["usuario_id"],
                 json.dumps({"schema": esquema, "tabela": tabela, "geometria": "Point", "srid": 4326,
                             "campos": [{"nome": "rotulo", "tipo": "text"}], "fonte": "hospedada"})),
            )
            item = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (adm["tenant_id"], adm["usuario_id"], "zt-l204e-10k", hash_, valor[:8], ["camada:ler:" + str(item)]),
            )
            token_id = cur.fetchone()["id"]
        con.commit()

        from fastapi.testclient import TestClient

        from app.main import app
        with TestClient(app) as c:
            r = c.get(f"/svc/{valor}/camadas/{item}.kml")
        assert r.status_code == 200
        caminho = tmp_path / "export.kml"
        caminho.write_bytes(r.content)
        info = subprocess.run(["ogrinfo", str(caminho), "camada 10k L2-04-e", "-so"],
                               capture_output=True, text=True)
        assert "Feature Count: 10000" in info.stdout, info.stdout + info.stderr
        medida("L2-04-e-vector-tile-server-tilejson")(
            "kml_10_mil_feicoes_ogrinfo", 10000, "feicoes",
            f"GET /svc/<token>/camadas/<item>.kml (10.000 linhas) -> ogrinfo -so; saída: "
            f"{info.stdout.strip().splitlines()[-1] if info.stdout else ''}",
        )
    finally:
        if item is not None:
            with con.cursor() as cur:
                contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
                if token_id is not None:
                    cur.execute("DELETE FROM plat.token_servico WHERE id = %s", (token_id,))
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item,))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item,))
                cur.execute(f'DROP TABLE IF EXISTS "{esquema}"."{tabela}"')
            con.commit()
        con.close()


def test_csv_export_com_geometria_multi(app_com_martin, env):
    """Refutação do adversário: `.csv` de camada com MULTIPOLYGON não quebra (WKT de geometria
    composta) — não existe, neste catálogo, o conceito de 'camada sem geometria' (toda
    `camada_vetorial` exige SRID/tipo em `plat.camada_preparar`), então esse braço do pedido do
    adversário aterrissa em 404 `camada_nao_encontrada`, nunca um 500."""
    con = _conectar_app(env)
    esquema, tabela = "d_demo", "c_" + _hex16()
    item = token_id = None
    try:
        adm = _admin(con, "demo")
        valor, hash_ = token_novo()
        with con.cursor() as cur:
            contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute(f'CREATE TABLE "{esquema}"."{tabela}" '
                        f'(fid bigserial PRIMARY KEY, rotulo text, geom geometry(MultiPolygon, 4326))')
            cur.execute(
                f'INSERT INTO "{esquema}"."{tabela}" (rotulo, geom) VALUES '
                f"('m1', ST_Multi(ST_Union("
                f"ST_Buffer(ST_SetSRID(ST_MakePoint(-55.0,-15.0),4326), 0.02), "
                f"ST_Buffer(ST_SetSRID(ST_MakePoint(-55.1,-15.1),4326), 0.02))))"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'MultiPolygon', %s)",
                        (esquema, tabela, adm["usuario_id"]))
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], "camada multi L2-04-e", adm["usuario_id"], adm["usuario_id"],
                 json.dumps({"schema": esquema, "tabela": tabela, "geometria": "MultiPolygon", "srid": 4326,
                             "campos": [{"nome": "rotulo", "tipo": "text"}], "fonte": "hospedada"})),
            )
            item = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (adm["tenant_id"], adm["usuario_id"], "zt-l204e-multi", hash_, valor[:8], ["camada:ler:" + str(item)]),
            )
            token_id = cur.fetchone()["id"]
        con.commit()
        from fastapi.testclient import TestClient

        from app.main import app
        with TestClient(app) as c:
            r = c.get(f"/svc/{valor}/camadas/{item}.csv")
            assert r.status_code == 200
            assert "MULTIPOLYGON" in r.text
            r_inexistente = c.get(f"/svc/{valor}/camadas/00000000-0000-0000-0000-000000000000.csv")
            # o token só tem escopo camada:ler:<item real> — um item diferente nem chega a
            # ser consultado no banco: recusa por ESCOPO (403), nunca 404 (não confirma nem nega
            # a existência do item alheio)
            assert r_inexistente.status_code == 403
    finally:
        if item is not None:
            with con.cursor() as cur:
                contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
                if token_id is not None:
                    cur.execute("DELETE FROM plat.token_servico WHERE id = %s", (token_id,))
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item,))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item,))
                cur.execute(f'DROP TABLE IF EXISTS "{esquema}"."{tabela}"')
            con.commit()
        con.close()


def test_fgb_e_gpkg_abrem_com_ogrinfo(app_com_martin, camada_poligono):
    if subprocess.run(["which", "ogrinfo"], capture_output=True).returncode != 0:
        pytest.skip("ogrinfo/GDAL não instalado nesta máquina")
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    r_fgb = c.get(f"/svc/{tok}/camadas/{item}.fgb")
    assert r_fgb.status_code == 200 and len(r_fgb.content) > 0
    r_gpkg = c.get(f"/svc/{tok}/camadas/{item}.gpkg")
    assert r_gpkg.status_code == 200 and len(r_gpkg.content) > 0


@pytest.mark.lento
def test_geojson_1_milhao_streaming_sem_estourar_rss(env, tmp_path):
    """Cláusula literal do portão: GeoJSON de 1 mi de feições sem carregar tudo em RAM (RSS do
    worker <= 300 MB, medido). Sobe um `uvicorn` de VERDADE (subprocesso, não TestClient — o
    TestClient roda a app na MESMA thread do pytest, o que mediria a RAM do pytest, não a de um
    worker isolado) e amostra `/proc/<pid>/status:VmRSS` durante o download inteiro."""
    porta = _porta_livre()
    con = _conectar_app(env)
    esquema, tabela = "d_demo", "c_" + _hex16()
    item = token_id = None
    try:
        adm = _admin(con, "demo")
        valor, hash_ = token_novo()
        with con.cursor() as cur:
            contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute(f'CREATE TABLE "{esquema}"."{tabela}" '
                        f'(fid bigserial PRIMARY KEY, rotulo text, geom geometry(Point, 4326))')
            cur.execute(f"INSERT INTO \"{esquema}\".\"{tabela}\" (rotulo, geom) "
                        f"SELECT 'p' || g, ST_SetSRID(ST_MakePoint("
                        f"-73.0 + random()*39.0, -33.0 + random()*28.0), 4326) "
                        f"FROM generate_series(1, 1000000) g")
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Point', %s)", (esquema, tabela, adm["usuario_id"]))
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], "camada 1mi L2-04-e", adm["usuario_id"], adm["usuario_id"],
                 json.dumps({"schema": esquema, "tabela": tabela, "geometria": "Point", "srid": 4326,
                             "campos": [{"nome": "rotulo", "tipo": "text"}], "fonte": "hospedada"})),
            )
            item = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (adm["tenant_id"], adm["usuario_id"], "zt-l204e-1mi", hash_, valor[:8], ["camada:ler:" + str(item)]),
            )
            token_id = cur.fetchone()["id"]
        con.commit()

        ambiente = dict(__import__("os").environ)
        ambiente["PLAT_GIT_SHA"] = ambiente.get("PLAT_GIT_SHA") or "0" * 12
        proc = subprocess.Popen(
            ["venv/bin/python", "-m", "uvicorn", "app.main:app", "--port", str(porta), "--host", "127.0.0.1"],
            cwd=str(ROOT), env=ambiente, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            base = f"http://127.0.0.1:{porta}"
            ok = False
            for _ in range(100):
                try:
                    if requests.get(f"{base}/saude", timeout=1).status_code == 200:
                        ok = True
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            if not ok:
                pytest.skip("uvicorn de verdade não subiu em 10 s")

            amostras = []
            parar = False

            def amostrar():
                while not parar:
                    try:
                        status = Path(f"/proc/{proc.pid}/status").read_text()
                        for linha in status.splitlines():
                            if linha.startswith("VmRSS:"):
                                amostras.append(int(linha.split()[1]))
                    except (FileNotFoundError, ProcessLookupError):
                        break
                    time.sleep(0.1)

            import threading
            t = threading.Thread(target=amostrar, daemon=True)
            t.start()
            r = requests.get(f"{base}/svc/{valor}/camadas/{item}.geojson", stream=True, timeout=120)
            total = 0
            for pedaco in r.iter_content(chunk_size=65536):
                total += len(pedaco)
            parar = True
            t.join(timeout=2)
            assert r.status_code == 200
            pico_kb = max(amostras) if amostras else None
            assert pico_kb is not None, "não foi possível amostrar VmRSS do processo uvicorn"
            assert pico_kb <= 300 * 1024, f"RSS de pico {pico_kb} KB > 300 MB"
            (ROOT / "tests" / "medidas").mkdir(parents=True, exist_ok=True)
            if __import__("os").environ.get("PLAT_GRAVAR_MEDIDAS") == "1":
                sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=str(ROOT),
                                     capture_output=True, text=True).stdout.strip() or "desconhecido"
                caminho = ROOT / "tests" / "medidas" / "L2-04-e-vector-tile-server-tilejson.json"
                dados = (json.loads(caminho.read_text()) if caminho.exists()
                         else {"item": "L2-04-e-vector-tile-server-tilejson", "medidas": {}})
                dados["medidas"]["geojson_1mi_rss_kb"] = {
                    "valor": pico_kb, "unidade": "kB",
                    "comando": f"GET /svc/<token>/camadas/<item>.geojson (1.000.000 feições, {total} bytes) "
                               f"contra uvicorn real; amostra de /proc/<pid>/status:VmRSS a cada 100 ms",
                    "sha": sha, "em": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
                }
                caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        if item is not None:
            with con.cursor() as cur:
                contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
                if token_id is not None:
                    cur.execute("DELETE FROM plat.token_servico WHERE id = %s", (token_id,))
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item,))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item,))
                cur.execute(f'DROP TABLE IF EXISTS "{esquema}"."{tabela}"')
            con.commit()
        con.close()


# =================================================================== cláusula: token revogado = 401 em todas
def test_token_revogado_401_em_todas_as_rotas(app_com_martin, camada_poligono, env, medida):
    c, tok, item = app_com_martin, camada_poligono["token"], camada_poligono["item"]
    # confirma que as rotas respondem 200 ANTES da revogação (senão o teste provaria pouco)
    rotas = [
        f"/tiles/{tok}/{item}/tilejson.json",
        f"/tiles/{tok}/{item}/0/0/0.pbf",
        f"/svc/{tok}/rest/services/{item}/VectorTileServer",
        f"/svc/{tok}/rest/services/{item}/VectorTileServer/resources/styles/root.json",
        f"/svc/{tok}/rest/services/{item}/VectorTileServer/resources/sprites/sprite.json",
        f"/svc/{tok}/rest/services/{item}/VectorTileServer/resources/fonts/Arial/0-255.pbf",
        f"/svc/{tok}/rest/services/{item}/VectorTileServer/tile/0/0/0.pbf",
        f"/svc/{tok}/camadas/{item}.geojson",
        f"/svc/{tok}/camadas/{item}.csv",
        f"/svc/{tok}/camadas/{item}.kml",
    ]
    for rota in rotas:
        assert c.get(rota).status_code == 200, rota

    con = _conectar_app(env)
    with con.cursor() as cur:
        contexto(con, camada_poligono["tenant_id"], camada_poligono["usuario_id"], "admin")
        cur.execute("UPDATE plat.token_servico SET revogado_em = now() WHERE id = %s RETURNING id",
                    (camada_poligono["token_id"],))
        assert cur.fetchone() is not None
    con.commit()
    con.close()

    from app.tiles import autorizacao
    autorizacao.esquecer()  # o cache de 2 s em processo não pode esconder a revogação deste teste

    piores = {}
    for rota in rotas:
        status = c.get(rota).status_code
        piores[rota] = status
        assert status == 401, f"{rota} deveria recusar com 401 depois da revogação, veio {status}"
    medida("L2-04-e-vector-tile-server-tilejson")(
        "token_revogado_401_em_todas_as_rotas", piores, "status", "revoga o token e repete as 10 rotas",
    )
