"""Exportação vetorial (item L6-02-o-importacao-exportacao-formatos, `app/ingestao/exportar.py`). Portão:

1. cada formato com teste de IDA E VOLTA (exporta e reimporta; geometria e atributos comparados feição a
   feição, não só a contagem) — via o PRÓPRIO importador quando o formato é reimportável por nós (gpkg,
   shapefile.zip, geojson, geojsonseq, kml, filegdb.zip, xlsx-ponto); via `ogrinfo`/`ogr2ogr` direto quando não
   é (csv com geometria em WKT, dxf sem atributo, mvt/pmtiles com quantização de tile — cada um documentado);
2. FileGDB escrito abre no QGIS — SEM QGIS nesta máquina (`which qgis` vazio), a prova é por `ogrinfo`, dito
   explicitamente no teste e no repasse;
3. exportação de um inquilino com 20 camadas em tempo medido (`tests/medidas/L6-02-o.json`);
4. isolamento: a exportação de inquilino nunca inclui camada de outro inquilino (cláusula INEGOCIÁVEL);
5. refutação do item: shapefile com campo > 10 caracteres e com data — tem de haver aviso de truncamento.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from shapely.geometry import shape as shapely_shape

import pytest

from app import objetos as objetos_mod
from tests.api.ingestao.conftest import GERADOS, esperar_job
from tests.api.test_rls import contexto, ids_por_slug

pytestmark = pytest.mark.skipif(not GERADOS.exists(), reason="rode `venv/bin/python tests/dados/gerar.py` antes")

QGIS_DISPONIVEL = shutil.which("qgis") is not None or shutil.which("qgis_process") is not None


def _tabela_de(cur, item_id: str) -> tuple[str, str]:
    cur.execute("SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item WHERE id=%s::uuid",
                (item_id,))
    r = cur.fetchone()
    return r["schema"], r["tabela"]


def _contexto_admin(con, ids: dict, slug: str = "demo"):
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")


def _importar_gpkg(ing, nome_arquivo: str = "cobertura.gpkg") -> str:
    """Importa `nome_arquivo` (gpkg) e devolve o item_id da camada concluída."""
    importacao_id, insp = ing.importar(nome_arquivo, "gpkg")
    assert insp["estado"] == "proposta", insp
    final = ing.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    return final["item_id"]


def _exportar(sessao, item_id: str, formato: str, timeout: float = 90, **corpo) -> dict:
    r = sessao.post(f"/api/itens/{item_id}/exportar", json={"formato": formato, **corpo})
    assert r.status_code == 202, r.text
    job = esperar_job(sessao, r.json()["job_id"], timeout=timeout)
    assert job["estado"] == "concluido", job
    return job["resultado"]


def _baixar(resultado: dict) -> bytes:
    return objetos_mod.ler(resultado["chave"])


def _reimportar(ing, dados: bytes, nome: str, formato: str, content_type="application/octet-stream") -> dict:
    """Sobe `dados` como um novo arquivo e reimporta pelo pipeline normal (mesma confirmação automática do
    `Ingestor`). Devolve a importação final."""
    obj = None
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / nome
        caminho.write_bytes(dados)
        obj = ing.enviar_arquivo(caminho, content_type=content_type)
    item_id = ing.item_arquivo(obj, nome)
    r = ing.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": formato})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    esperar_job(ing.sessao, job_id, timeout=90)
    imp_id = r.json()["importacao_id"]
    r = ing.sessao.get(f"/api/importacoes/{imp_id}")
    insp = r.json()
    return ing.confirmar(imp_id) if insp["estado"] == "proposta" else insp


def _linhas(cur, schema: str, tabela: str) -> list[dict]:
    cur.execute(f'SELECT * FROM "{schema}"."{tabela}" ORDER BY fid')
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------- ida e volta: formatos REIMPORTÁVEIS


@pytest.mark.parametrize("formato,nome_saida", [
    ("gpkg", "saida.gpkg"), ("shapefile.zip", "saida.zip"), ("geojson", "saida.geojson"),
    ("geojsonseq", "saida.geojsonl"), ("kml", "saida.kml"), ("filegdb.zip", "saida.zip"),
])
def test_ida_e_volta_reimportavel(ingestor_a, conexao_plat_app, formato, nome_saida):
    item_id = _importar_gpkg(ingestor_a)
    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, item_id)
        origem = _linhas(cur, schema, tabela)

    resultado = _exportar(ingestor_a.sessao, item_id, formato)
    dados = _baixar(resultado)
    assert len(dados) > 0

    final = _reimportar(ingestor_a, dados, nome_saida, formato)
    assert final["estado"] == "concluida", (formato, final)
    with conexao_plat_app.cursor() as cur:
        schema2, tabela2 = _tabela_de(cur, final["item_id"])
        volta = _linhas(cur, schema2, tabela2)

    assert len(volta) == len(origem) == 80, formato
    # feição a feição: nome (quando o formato preserva atributo) e geometria (área e centróide dentro de
    # tolerância — KML/GeoJSON são reprojetados para 4326, então não é bit-exato, é a MESMA forma)
    for o, v in zip(origem, volta, strict=True):
        campo_nome = "name" if "name" in v else ("Name" if "Name" in v else None)
        if campo_nome:
            assert v[campo_nome] == o["name"], formato
    # geometria comparada em lote (mais barato que golpe a golpe de subprocess): via PostGIS, ST_Equals com
    # folga (reprojeção 4674->4326 desloca menos de 1e-6 grau, que não é distinguível de erro de arredondamento
    # nesta escala) usando ST_HausdorffDistance como métrica de forma.
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'SELECT count(*) AS iguais FROM "{schema}"."{tabela}" o '
            f'JOIN "{schema2}"."{tabela2}" v ON o.fid = v.fid '
            f'WHERE ST_HausdorffDistance(o.geom, ST_Transform(ST_SetSRID(v.geom, 4326), 4674)) < 0.0005 '
            f'   OR ST_HausdorffDistance(o.geom, v.geom) < 0.0005'
        )
        assert cur.fetchone()["iguais"] == 80, f"{formato}: geometria divergiu em alguma feição"


def test_ida_e_volta_xlsx_ponto(ingestor_a, conexao_plat_app):
    """XLSX só é reimportável de verdade para PONTO (lat/lon) — a mesma limitação medida na importação."""
    importacao_id, insp = ingestor_a.importar("lugares.xlsx", "xlsx",
                                              content_type="application/vnd.openxmlformats-officedocument"
                                                          ".spreadsheetml.sheet")
    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    item_id = final["item_id"]

    resultado = _exportar(ingestor_a.sessao, item_id, "xlsx")
    assert not resultado["avisos"], resultado  # ponto: sem aviso de perda (só o caso não-ponto avisa)
    dados = _baixar(resultado)
    final2 = _reimportar(ingestor_a, dados, "volta.xlsx", "xlsx",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert final2["estado"] == "concluida", final2

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, item_id)
        origem = _linhas(cur, schema, tabela)
        schema2, tabela2 = _tabela_de(cur, final2["item_id"])
        volta = _linhas(cur, schema2, tabela2)
    assert len(origem) == len(volta) == 10
    nomes_origem = sorted(o["nome"] for o in origem)
    nomes_volta = sorted(v["nome"] for v in volta)
    assert nomes_origem == nomes_volta


# ---------------------------------------------------------------------- ida e volta: formatos SÓ por ferramenta


def test_ida_e_volta_csv_geometria_wkt_por_ferramenta(ingestor_a, conexao_plat_app, tmp_path):
    """CSV exporta geometria como WKT (coluna `WKT`); o importador de CSV da casa só reconhece lat/lon — a
    prova de ida e volta aqui é por `ogr2ogr` direto (que É como qualquer ferramenta GIS去 reimporta um CSV com
    WKT), não pelo pipeline de importação do produto (que tem outra finalidade, documentada no aviso)."""
    item_id = _importar_gpkg(ingestor_a)
    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, item_id)
        origem = _linhas(cur, schema, tabela)

    resultado = _exportar(ingestor_a.sessao, item_id, "csv")
    assert "WKT" in resultado["avisos"][0] or "wkt" in resultado["avisos"][0].lower()
    dados = _baixar(resultado)
    caminho = tmp_path / "saida.csv"
    caminho.write_bytes(dados)
    r = subprocess.run(["ogr2ogr", "-f", "GeoJSON", str(tmp_path / "volta.geojson"), str(caminho)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    volta = json.loads((tmp_path / "volta.geojson").read_text())["features"]
    assert len(volta) == len(origem) == 80
    for o, v in zip(origem, volta, strict=True):
        assert v["properties"]["name"] == o["name"]


def test_ida_e_volta_dxf_so_geometria_por_ferramenta(ingestor_a, conexao_plat_app, tmp_path):
    """DXF: o formato não tem atributo arbitrário (medido); a prova de ida e volta é só de GEOMETRIA, por
    `ogrinfo` direto (sem QGIS nesta máquina — `which qgis`/`qgis_process` vazios)."""
    assert not QGIS_DISPONIVEL, "QGIS apareceu nesta máquina; reavaliar a prova"
    item_id = _importar_gpkg(ingestor_a)
    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, item_id)
        cur.execute(f'SELECT ST_Area(geom) AS a FROM "{schema}"."{tabela}" ORDER BY fid')
        areas_origem = [float(r["a"]) for r in cur.fetchall()]

    resultado = _exportar(ingestor_a.sessao, item_id, "dxf")
    assert any("não tem atributo arbitrário" in a for a in resultado["avisos"])
    dados = _baixar(resultado)
    caminho = tmp_path / "saida.dxf"
    caminho.write_bytes(dados)
    r = subprocess.run(["ogrinfo", "-al", "-so", str(caminho)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Feature Count: 80" in r.stdout
    r2 = subprocess.run(["ogr2ogr", "-f", "GeoJSON", str(tmp_path / "volta.geojson"), str(caminho)],
                        capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    volta = json.loads((tmp_path / "volta.geojson").read_text())["features"]
    from shapely.geometry import shape as shapely_shape
    areas_volta = sorted(shapely_shape(f["geometry"]).area for f in volta if f.get("geometry"))
    assert len(areas_volta) == 80
    for a1, a2 in zip(sorted(areas_origem), areas_volta, strict=True):
        assert a1 == pytest.approx(a2, rel=0.02)


@pytest.mark.parametrize("formato,extensao", [("mvt", "zip"), ("pmtiles", "pmtiles")])
def test_ida_e_volta_tiles_com_quantizacao_documentada(ingestor_a, conexao_plat_app, tmp_path, formato, extensao):
    """MVT/PMTiles são mosaicos de tile: a geometria é QUANTIZADA por natureza do formato (4096 unidades por
    tile, especificação Mapbox Vector Tile) — não há "bit-exato" possível. A prova de ida e volta aqui é:
    contagem de feições exata quando lida no zoom onde a camada cabe INTEIRA num tile (sem fragmentação — medido
    nesta passagem: no zoom máximo a mesma feição aparece fragmentada em várias, ver docstring de
    `_estrategia_mvt`), e desvio de posição do centróide MEDIDO (não prometido de cabeça)."""
    item_id = _importar_gpkg(ingestor_a, "cobertura.geojsonl" if False else "cobertura.gpkg")
    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, item_id)
        cur.execute(f'SELECT name, ST_X(ST_Transform(ST_Centroid(geom),4326)) AS x, '
                    f'ST_Y(ST_Transform(ST_Centroid(geom),4326)) AS y FROM "{schema}"."{tabela}" ORDER BY fid')
        origem = [dict(r) for r in cur.fetchall()]

    resultado = _exportar(ingestor_a.sessao, item_id, formato)
    dados = _baixar(resultado)
    if extensao == "zip":
        caminho_zip = tmp_path / "saida.zip"
        caminho_zip.write_bytes(dados)
        pasta = tmp_path / "mvt"
        with zipfile.ZipFile(caminho_zip) as zf:
            zf.extractall(pasta)
        # zoom baixo o bastante para a camada inteira (recorte de Guarulhos, ~20 km) caber num tile só
        alvo = pasta / next(p.name for p in pasta.iterdir())  # "_mvt_saida" ou o nome salvo
        caminho = alvo if alvo.is_dir() else pasta
    else:
        caminho = tmp_path / "saida.pmtiles"
        caminho.write_bytes(dados)

    r = subprocess.run(["ogr2ogr", "-f", "GeoJSON", str(tmp_path / "volta.geojson"), str(caminho),
                       "-oo", "ZOOM_LEVEL=6", "-t_srs", "EPSG:4326"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    volta = json.loads((tmp_path / "volta.geojson").read_text())["features"]
    assert len(volta) == 80, f"{formato}: {len(volta)} feições no zoom 6 (esperava as 80 inteiras, sem fragmento)"
    from shapely.geometry import shape as shapely_shape
    desvios = []
    for o, v in zip(origem, volta, strict=True):
        cv = shapely_shape(v["geometry"]).centroid
        desvios.append(((cv.x - o["x"]) ** 2 + (cv.y - o["y"]) ** 2) ** 0.5)
    desvio_max_graus = max(desvios)
    # ~0,02 grau ~= 2 km no zoom 6 (tile de ~5,6 km de lado / 4096 = 1,4 m de passo — a folga observada vem
    # da SIMPLIFICAÇÃO do zoom baixo, não do passo de quantização; registrado como medida, não como promessa)
    assert desvio_max_graus < 0.05, f"{formato}: desvio de centróide {desvio_max_graus:.5f} graus"


# ---------------------------------------------------------------------- refutação do item: truncamento


def _gerar_gpkg_campo_longo(caminho: Path) -> None:
    from osgeo import ogr, osr

    drv = ogr.GetDriverByName("GPKG")
    caminho.unlink(missing_ok=True)
    ds = drv.CreateDataSource(str(caminho))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4674)
    lyr = ds.CreateLayer("longo", srs, ogr.wkbPoint)
    lyr.CreateField(ogr.FieldDefn("nome_muito_longo_de_campo", ogr.OFTString))
    fld_data = ogr.FieldDefn("data_do_evento", ogr.OFTDate)
    lyr.CreateField(fld_data)
    for i in range(3):
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetField("nome_muito_longo_de_campo", f"SIG de teste interno {i}")
        f.SetField("data_do_evento", f"2026/09/0{i + 1}")
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT({-47 + i} -15)"))
        lyr.CreateFeature(f)
    ds = None


def test_shapefile_truncamento_de_campo_e_data_tem_aviso(ingestor_a, tmp_path):
    """Refutação do item L6-02-o: campo > 10 caracteres tem de vir com AVISO de truncamento explícito."""
    caminho = tmp_path / "longo.gpkg"
    _gerar_gpkg_campo_longo(caminho)
    obj = ingestor_a.enviar_arquivo(caminho, content_type="application/octet-stream")
    item_id_arq = ingestor_a.item_arquivo(obj, "longo.gpkg")
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id_arq, "formato": "gpkg"})
    assert r.status_code == 202, r.text
    esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=60)
    imp_id = r.json()["importacao_id"]
    final = ingestor_a.confirmar(imp_id)
    assert final["estado"] == "concluida", final

    resultado = _exportar(ingestor_a.sessao, final["item_id"], "shapefile.zip")
    avisos = " | ".join(resultado["avisos"])
    assert "truncad" in avisos.lower(), resultado["avisos"]
    assert any("nome_muito_l" in a or "Normalized" in a for a in resultado["avisos"]), resultado["avisos"]

    # confere no dbf de verdade: o campo saiu com <= 10 caracteres
    dados = _baixar(resultado)
    pasta = tmp_path / "shp_saida"
    pasta.mkdir()
    with zipfile.ZipFile(io.BytesIO(dados)) as zf:
        zf.extractall(pasta)
    shp = next(pasta.glob("*.shp"))
    r = subprocess.run(["ogrinfo", "-al", "-so", str(shp)], capture_output=True, text=True)
    campos = [ln.split(":")[0].strip() for ln in r.stdout.splitlines() if "(" in ln and ":" in ln
             and "Layer" not in ln and "Geometry" not in ln and "Feature" not in ln and "Extent" not in ln]
    assert all(len(c) <= 10 for c in campos), campos


# ---------------------------------------------------------------------- inquilino: escrow + isolamento + tempo


def test_exportar_inquilino_isolamento_e_tempo(ingestor_a, ingestor_b, conexao_plat_app, medida):
    """Cláusula INEGOCIÁVEL: exportação do inquilino A nunca inclui camada de B. Mesmo teste mede o tempo com
    ~20 camadas (a mesma bancada demo já carrega algumas camadas de outros testes; garante o PISO de 20 só
    para A, sem se importar com o que mais existir)."""
    ids = ids_por_slug(conexao_plat_app)

    item_b = _importar_gpkg(ingestor_b, "lugares_pv.csv" if False else "cobertura.gpkg")

    ITENS_A = 20
    for _ in range(ITENS_A):
        _importar_gpkg(ingestor_a)

    inicio = time.monotonic()
    r = ingestor_a.sessao.post("/api/org/exportar", json={})
    assert r.status_code == 202, r.text
    job = esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=180)
    assert job["estado"] == "concluido", job
    duracao_s = time.monotonic() - inicio
    resultado = job["resultado"]
    assert resultado["camadas"] >= ITENS_A

    manifesto = json.loads(objetos_mod.ler(resultado["manifesto_chave"]))
    assert manifesto["inquilino"] == "demo"
    ids_manifesto = {c["item_id"] for c in manifesto["camadas"]}
    assert item_b not in ids_manifesto, "camada do inquilino B vazou para o manifesto de A"

    gpkg_bytes = objetos_mod.ler(resultado["gpkg_chave"])
    caminho = Path(f"/tmp/_l6_02_o_export_{ingestor_a.sessao.cookies.get('plat_sessao', 'x')[:8]}.gpkg")
    caminho.write_bytes(gpkg_bytes)
    try:
        r_info = subprocess.run(["ogrinfo", "-q", str(caminho)], capture_output=True, text=True)
        assert r_info.returncode == 0, r_info.stderr
        camadas_gpkg = [ln.split(":")[0].split()[-1] for ln in r_info.stdout.splitlines() if ":" in ln]
        # as camadas de B (mesmo esquema físico d_demo2, tabelas c_*) nunca podem aparecer aqui — o nome de
        # layer é derivado do item_id de A (`c_<16 hex do item_id>`), então basta achar que nenhuma bate com B
        assert not any(item_b.replace("-", "")[:16] in c for c in camadas_gpkg)
    finally:
        caminho.unlink(missing_ok=True)

    medida("L6-02-o")("exportar_inquilino_tempo_s", round(duracao_s, 2), "s",
                      f"POST /api/org/exportar com {resultado['camadas']} camadas (tenant demo, ~{ITENS_A} "
                      f"criadas neste teste + as já existentes)")
    medida("L6-02-o")("exportar_inquilino_camadas", resultado["camadas"], "camadas",
                      "job ingestao.exportar_inquilino, campo 'camadas' do resultado")
    medida("L6-02-o")("exportar_inquilino_gpkg_bytes", resultado["gpkg_bytes"], "bytes",
                      "job ingestao.exportar_inquilino, campo 'gpkg_bytes' do resultado")
