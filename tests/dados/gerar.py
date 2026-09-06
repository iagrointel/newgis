"""Gera os arquivos de teste da ingestão vetorial (item L0-04-ingest-vetor; ADR 0005 seção 19) a partir de DADO
REAL já no repositório (`web/dados/basemap/guarulhos.pmtiles`, OSM/ODbL, cobertura do solo e lugares de
Guarulhos) — sem baixar nada novo (disco a 98%). Roda sem rede e sem banco; escreve em `tests/dados/gerados/`
(no .gitignore). Os 4 formatos desta passagem (shapefile.zip, gpkg, geojson, csv) mais os 3 ataques exigidos:
shapefile sem `.prj`, GeoJSON com polígono auto-intersectado, CSV com vírgula decimal."""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PMTILES = RAIZ / "web" / "dados" / "basemap" / "guarulhos.pmtiles"
SAIDA = Path(__file__).resolve().parent / "gerados"
N_POLIGONOS = 80
N_PONTOS = 40


def _ogr2ogr(*args: str) -> None:
    r = subprocess.run(["ogr2ogr", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ogr2ogr falhou: {' '.join(args)}\n{r.stderr}")


def _zip(caminho_zip: Path, membros: list[Path], renomear: dict[str, str] | None = None) -> None:
    renomear = renomear or {}
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for m in membros:
            zf.write(m, renomear.get(m.name, m.name))


def gerar_cobertura_subset() -> Path:
    """80 polígonos de uso do solo de Guarulhos, reprojetados para SIRGAS 2000 (EPSG:4674), campos originais do
    OSM (landuse/leisure/natural/name) — cabe um `select` sintético para testar a palavra reservada (seção 8)."""
    destino = SAIDA / "_cobertura_subset.geojson"
    _ogr2ogr(
        "-f", "GeoJSON", str(destino), str(PMTILES), "cobertura", "-t_srs", "EPSG:4674",
        "-dialect", "OGRSQL", "-sql",
        f'SELECT landuse, leisure, "natural", name, landuse AS "select" '
        f'FROM cobertura WHERE landuse IS NOT NULL OR leisure IS NOT NULL OR "natural" IS NOT NULL '
        f'ORDER BY mvt_id LIMIT {N_POLIGONOS}',
    )
    return destino


def gerar_lugares_subset() -> Path:
    destino = SAIDA / "_lugares_subset.geojson"
    _ogr2ogr(
        "-f", "GeoJSON", str(destino), str(PMTILES), "lugares", "-t_srs", "EPSG:4674",
        "-dialect", "OGRSQL", "-sql", f"SELECT name, place FROM lugares ORDER BY mvt_id LIMIT {N_PONTOS}",
    )
    return destino


def gerar_shapefiles(cobertura_geojson: Path) -> None:
    dir_tmp = SAIDA / "_shp_tmp"
    dir_tmp.mkdir(exist_ok=True)
    for f in dir_tmp.glob("cobertura.*"):
        f.unlink()
    _ogr2ogr("-f", "ESRI Shapefile", str(dir_tmp / "cobertura.shp"), str(cobertura_geojson), "-nln", "cobertura",
             "-lco", "ENCODING=UTF-8")

    membros = sorted(dir_tmp.glob("cobertura.*"))
    _zip(SAIDA / "cobertura_shp.zip", membros)  # shapefile completo (com .prj e .cpg)

    sem_prj = [m for m in membros if m.suffix != ".prj"]
    _zip(SAIDA / "cobertura_semprj.zip", sem_prj)  # ATAQUE 1: shapefile sem .prj


def gerar_gpkg(cobertura_geojson: Path) -> None:
    caminho = SAIDA / "cobertura.gpkg"
    caminho.unlink(missing_ok=True)
    _ogr2ogr("-f", "GPKG", str(caminho), str(cobertura_geojson), "-nln", "cobertura")


def gerar_geojson(cobertura_geojson: Path) -> None:
    shutil.copyfile(cobertura_geojson, SAIDA / "cobertura.geojson")


def gerar_gravata() -> None:
    """ATAQUE 2: polígono auto-intersectado (laço em "8") + anel não fechado — mesmo padrão de teste do ADR 0005
    (seção 0.2/0.3: 3 feições, a 3ª é a gravata; MakeValid devolve MultiPolygon de 2 partes)."""
    quadrado = [[-46.50, -23.45], [-46.49, -23.45], [-46.49, -23.44], [-46.50, -23.44], [-46.50, -23.45]]
    anel_aberto = [[-46.48, -23.45], [-46.47, -23.45], [-46.47, -23.44], [-46.48, -23.44]]
    gravata = [[-46.46, -23.45], [-46.45, -23.44], [-46.45, -23.45], [-46.46, -23.44], [-46.46, -23.45]]
    colecao = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"nome": "quadrado valido"},
             "geometry": {"type": "Polygon", "coordinates": [quadrado]}},
            {"type": "Feature", "properties": {"nome": "anel nao fechado"},
             "geometry": {"type": "Polygon", "coordinates": [anel_aberto]}},
            {"type": "Feature", "properties": {"nome": "gravata"},
             "geometry": {"type": "Polygon", "coordinates": [gravata]}},
        ],
    }
    (SAIDA / "gravata.geojson").write_text(json.dumps(colecao, ensure_ascii=False), encoding="utf-8")


def gerar_csv(lugares_geojson: Path) -> None:
    """ATAQUE 3: CSV com `;` de separador e vírgula decimal (latitude/longitude com casas decimais reais de
    Guarulhos), BOM UTF-8, campo `nome` com acento (dado real: nome de lugar do OSM)."""
    dados = json.loads(lugares_geojson.read_text(encoding="utf-8"))
    linhas = ["nome;place;latitude;longitude"]
    for f in dados["features"]:
        geom = f.get("geometry")
        if not geom or geom.get("type") not in ("Point", "MultiPoint"):
            continue
        coords = geom["coordinates"]
        lon, lat = (coords[0][0], coords[0][1]) if geom["type"] == "MultiPoint" else (coords[0], coords[1])
        nome = (f["properties"].get("name") or "sem nome").replace(";", " ")
        place = f["properties"].get("place") or ""
        lat_v = f"{lat:.6f}".replace(".", ",")
        lon_v = f"{lon:.6f}".replace(".", ",")
        linhas.append(f"{nome};{place};{lat_v};{lon_v}")
    texto = "﻿" + "\n".join(linhas) + "\n"
    (SAIDA / "lugares_pv.csv").write_bytes(texto.encode("utf-8"))


def gerar_csv_aspas_desbalanceadas() -> None:
    texto = 'nome;place\n"Escola Municipal;school\n"Praça da Sé";square\n'
    (SAIDA / "csv_aspas.csv").write_text(texto, encoding="utf-8")


N_FORMATOS_NOVOS = 10  # item L6-02-o: recortes pequenos de propósito (disco apertado, ver bancada)


def gerar_cobertura_nomeada(cobertura_geojson: Path) -> Path:
    """`N_FORMATOS_NOVOS` feições do recorte de cobertura que TÊM `name` preenchido (achado: as 10 primeiras da
    ordem original só têm `natural` — GeoJSON omite chave com valor nulo, então o teste de ida e volta dos
    formatos novos precisa de um recorte com atributo garantido para comparar, não só geometria)."""
    destino = SAIDA / "_cobertura_nomeada.geojson"
    _ogr2ogr("-f", "GeoJSON", str(destino), str(cobertura_geojson), "-t_srs", "EPSG:4674",
             "-dialect", "OGRSQL", "-sql",
             f'SELECT * FROM cobertura WHERE name IS NOT NULL ORDER BY name LIMIT {N_FORMATOS_NOVOS}')
    return destino


def gerar_geojsonseq(cobertura_nomeada: Path) -> None:
    """GeoJSONSeq/NDJSON, `N_FORMATOS_NOVOS` feições COM `name` (item L6-02-o)."""
    destino = SAIDA / "cobertura.geojsonl"
    _ogr2ogr("-f", "GeoJSONSeq", str(destino), str(cobertura_nomeada))


def gerar_kml(cobertura_nomeada: Path) -> None:
    """KML, mesmo recorte nomeado; campo `select` (palavra reservada) tirado porque o LIBKML não aceita ponto no
    nome do jeito que a proposta espera — mantém só os campos "normais" para o teste de ida e volta."""
    destino = SAIDA / "cobertura.kml"
    _ogr2ogr("-f", "LIBKML", str(destino), str(cobertura_nomeada), "-select", "landuse,leisure,natural,name")


def gerar_dxf(cobertura_nomeada: Path) -> None:
    """DXF: só geometria sobrevive (o driver não aceita campo arbitrário, ver docstring de `_preparar_dxf`)."""
    destino = SAIDA / "cobertura.dxf"
    _ogr2ogr("-f", "DXF", str(destino), str(cobertura_nomeada))


def gerar_xlsx(lugares_geojson: Path) -> None:
    """XLSX com colunas `latitude`/`longitude` (reconhecidas por `csv_normalizar.NOMES_LAT/NOMES_LON`) — mesmo
    recorte de lugares do CSV, convertido via CSV intermediário (o próprio `_preparar_xlsx` faz o caminho
    inverso: XLSX -> CSV -> `_preparar_csv`)."""
    dados = json.loads(lugares_geojson.read_text(encoding="utf-8"))
    linhas_csv = ["nome,place,latitude,longitude"]
    for f in dados["features"][:N_FORMATOS_NOVOS]:
        geom = f.get("geometry")
        if not geom or geom.get("type") not in ("Point", "MultiPoint"):
            continue
        coords = geom["coordinates"]
        lon, lat = (coords[0][0], coords[0][1]) if geom["type"] == "MultiPoint" else (coords[0], coords[1])
        nome = (f["properties"].get("name") or "sem nome").replace(",", " ")
        place = f["properties"].get("place") or ""
        linhas_csv.append(f"{nome},{place},{lat:.6f},{lon:.6f}")
    csv_tmp = SAIDA / "_xlsx_tmp.csv"
    csv_tmp.write_text("\n".join(linhas_csv) + "\n", encoding="utf-8")
    destino = SAIDA / "lugares.xlsx"
    destino.unlink(missing_ok=True)
    _ogr2ogr("-f", "XLSX", str(destino), str(csv_tmp), "-oo", "AUTODETECT_TYPE=YES")
    csv_tmp.unlink()


def gerar_filegdb(cobertura_nomeada: Path) -> None:
    """File Geodatabase zipada (driver OpenFileGDB, escrita): gera a pasta `.gdb` num tmp e zipa — mesmo padrão
    do `cobertura_shp.zip` (a pasta em si não vai para o git, só o zip)."""
    dir_tmp = SAIDA / "_gdb_tmp"
    shutil.rmtree(dir_tmp, ignore_errors=True)
    dir_tmp.mkdir()
    caminho_gdb = dir_tmp / "cobertura.gdb"
    _ogr2ogr("-f", "OpenFileGDB", str(caminho_gdb), str(cobertura_nomeada), "-nln", "cobertura")
    caminho_zip = SAIDA / "cobertura_gdb.zip"
    caminho_zip.unlink(missing_ok=True)
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for arq in sorted(caminho_gdb.rglob("*")):
            if arq.is_file():
                zf.write(arq, arq.relative_to(dir_tmp))
    shutil.rmtree(dir_tmp)


def main() -> None:
    if not PMTILES.exists():
        raise SystemExit(f"ausente: {PMTILES} (dado da casa, não deveria faltar)")
    SAIDA.mkdir(parents=True, exist_ok=True)
    cobertura = gerar_cobertura_subset()
    lugares = gerar_lugares_subset()
    gerar_shapefiles(cobertura)
    gerar_gpkg(cobertura)
    gerar_geojson(cobertura)
    gerar_gravata()
    gerar_csv(lugares)
    gerar_csv_aspas_desbalanceadas()
    cobertura_nomeada = gerar_cobertura_nomeada(cobertura)
    gerar_geojsonseq(cobertura_nomeada)
    gerar_kml(cobertura_nomeada)
    gerar_dxf(cobertura_nomeada)
    gerar_xlsx(lugares)
    gerar_filegdb(cobertura_nomeada)
    cobertura_nomeada.unlink()
    cobertura.unlink()
    lugares.unlink()
    shutil.rmtree(SAIDA / "_shp_tmp", ignore_errors=True)
    print("gerado:", sorted(p.name for p in SAIDA.iterdir()))


if __name__ == "__main__":
    main()
