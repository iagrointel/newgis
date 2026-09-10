"""Gera os arquivos de teste da ingestão vetorial (item L0-04-ingest-vetor; ADR 0005 seção 19) a partir de DADO
REAL já no repositório (`web/dados/basemap/guarulhos.pmtiles`, OSM/ODbL, cobertura do solo e lugares de
Guarulhos) — sem baixar nada novo (disco a 91%). Roda sem rede e sem banco; escreve em `tests/dados/gerados/`
(no .gitignore).

Cobre os 9 formatos do portão do L0-04-d (shapefile zipado, GeoPackage, GeoJSON, GeoJSONSeq, KML, KMZ, CSV,
GPX, XLSX) mais os 4 que o portão do L0-04-b pede a mais (GML, FlatGeobuf, DXF, File Geodatabase zipada), e os
arquivos de ataque exigidos: shapefile sem `.prj`, GeoJSON com polígono auto-intersectado, CSV com vírgula
decimal, CSV com aspas desbalanceadas, GeoPackage com 3 camadas, KMZ com 3 pastas, XLSX com 2 planilhas,
CSV de 300 colunas e 0 linhas."""

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



def gerar_geojsonseq(cobertura_geojson: Path) -> None:
    """GeoJSONSeq: uma feição por linha. Formato do portão do L0-04-d (GeoJSON/GeoJSONSeq)."""
    destino = SAIDA / "cobertura.geojsonl"
    destino.unlink(missing_ok=True)
    _ogr2ogr("-f", "GeoJSONSeq", str(destino), str(cobertura_geojson))


def gerar_kml_e_kmz(cobertura_geojson: Path) -> None:
    """KML de uma camada e KMZ com TRÊS pastas (cláusula literal do portão do L0-04-d: 'KMZ com 3 pastas gera
    3 camadas'). O driver LIBKML escreve uma pasta por camada."""
    kml = SAIDA / "cobertura.kml"
    kml.unlink(missing_ok=True)
    _ogr2ogr("-f", "LIBKML", str(kml), str(cobertura_geojson), "-nln", "cobertura")

    # KMZ com 3 PASTAS. O `-update -append` do LIBKML sobre .kmz SUBSTITUI o documento em vez de acrescentar
    # (medido: sai 1 camada, a última). O KMZ é escrito à mão: um doc.kml com três <Folder>, que é exatamente
    # o que o driver lê como três camadas. Coordenadas reais de lugares de Guarulhos (OSM), não inventadas.
    lugares = json.loads((SAIDA / "_lugares_subset.geojson").read_text(encoding="utf-8"))["features"]
    pontos = []
    for f in lugares:
        g = f.get("geometry") or {}
        if g.get("type") == "Point":
            pontos.append((f["properties"].get("name") or "sem nome", g["coordinates"]))
        elif g.get("type") == "MultiPoint" and g["coordinates"]:
            pontos.append((f["properties"].get("name") or "sem nome", g["coordinates"][0]))
    if len(pontos) < 3:
        raise RuntimeError("o subconjunto de lugares não tem pontos suficientes para as 3 pastas do KMZ")
    partes = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for i, nome_pasta in enumerate(("pasta_um", "pasta_dois", "pasta_tres")):
        partes.append(f"<Folder><name>{nome_pasta}</name>")
        for nome, (lon, lat) in pontos[i::3]:
            seguro = str(nome).replace("&", "e").replace("<", "(").replace(">", ")")
            partes.append(f"<Placemark><name>{seguro}</name>"
                          f"<Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>")
        partes.append("</Folder>")
    partes.append("</Document></kml>")
    kmz = SAIDA / "tres_pastas.kmz"
    kmz.unlink(missing_ok=True)
    with zipfile.ZipFile(kmz, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", "\n".join(partes))


def gerar_gpx(lugares_geojson: Path) -> None:
    """GPX de pontos (o driver do GDAL grava waypoints). O GPX declara sempre WGS 84."""
    destino = SAIDA / "lugares.gpx"
    destino.unlink(missing_ok=True)
    # o driver GPX só aceita Point/LineString: o subconjunto de lugares do OSM vem como MultiPoint
    _ogr2ogr("-f", "GPX", str(destino), str(lugares_geojson), "-t_srs", "EPSG:4326", "-nln", "waypoints",
             "-nlt", "POINT", "-explodecollections")


def gerar_xlsx(lugares_geojson: Path) -> None:
    """XLSX com DUAS planilhas (cláusula literal do portão do L0-04-b: 'XLSX com 2 planilhas'). Planilha é
    tabela sem geometria: serve para provar que a recusa da carga é explícita, não silenciosa."""
    destino = SAIDA / "duas_planilhas.xlsx"
    destino.unlink(missing_ok=True)
    _ogr2ogr("-f", "XLSX", str(destino), str(lugares_geojson), "-nln", "planilha_um")
    _ogr2ogr("-f", "XLSX", "-update", "-append", str(destino), str(lugares_geojson), "-nln", "planilha_dois")


def gerar_gml(cobertura_geojson: Path) -> None:
    destino = SAIDA / "cobertura.gml"
    for sufixo in (".gml", ".xsd"):
        (SAIDA / f"cobertura{sufixo}").unlink(missing_ok=True)
    _ogr2ogr("-f", "GML", str(destino), str(cobertura_geojson), "-nln", "cobertura")


def gerar_flatgeobuf(cobertura_geojson: Path) -> None:
    destino = SAIDA / "cobertura.fgb"
    destino.unlink(missing_ok=True)
    _ogr2ogr("-f", "FlatGeobuf", str(destino), str(cobertura_geojson), "-nln", "cobertura")


def gerar_dxf(cobertura_geojson: Path) -> None:
    """DXF de polilinhas. O DXF não carrega CRS: a inspeção tem de PERGUNTAR o sistema de coordenadas."""
    destino = SAIDA / "cobertura.dxf"
    destino.unlink(missing_ok=True)
    _ogr2ogr("-f", "DXF", str(destino), str(cobertura_geojson))


def gerar_gdb_zip(cobertura_geojson: Path) -> None:
    """File Geodatabase zipada (uma `.gdb` é uma PASTA; o upload é sempre do zip)."""
    dir_gdb = SAIDA / "_teste.gdb"
    shutil.rmtree(dir_gdb, ignore_errors=True)
    _ogr2ogr("-f", "OpenFileGDB", str(dir_gdb), str(cobertura_geojson), "-nln", "cobertura")
    destino = SAIDA / "cobertura_gdb.zip"
    destino.unlink(missing_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for arq in sorted(dir_gdb.rglob("*")):
            if arq.is_file():
                zf.write(arq, f"_teste.gdb/{arq.name}")
    shutil.rmtree(dir_gdb, ignore_errors=True)


def gerar_gpkg_tres_camadas(cobertura_geojson: Path) -> None:
    """GeoPackage com 3 camadas (cláusula literal do portão do L0-04-b). Antes do turno 3 a inspeção tomava
    `camadas[0]` e as outras duas sumiam sem aviso."""
    caminho = SAIDA / "tres_camadas.gpkg"
    caminho.unlink(missing_ok=True)
    _ogr2ogr("-f", "GPKG", str(caminho), str(cobertura_geojson), "-nln", "camada_um")
    for nome in ("camada_dois", "camada_tres"):
        _ogr2ogr("-f", "GPKG", "-update", "-append", str(caminho), str(cobertura_geojson), "-nln", nome)


def gerar_csv_300_colunas_0_linhas() -> None:
    """Refutação literal do L0-04-b: 'CSV com 300 colunas e 0 linhas'. A inspeção tem de DIZER o que
    aconteceu (a tabela sairia vazia), nunca terminar em silêncio."""
    (SAIDA / "largo_300_colunas.csv").write_text(
        ",".join(f"col_{i}" for i in range(300)) + "\n", encoding="utf-8")


def gerar_zips_malformados() -> None:
    """Entrada malformada tem de virar 422 com mensagem, nunca 500 com rastro."""
    bons = (SAIDA / "cobertura_shp.zip").read_bytes()
    (SAIDA / "zip_corrompido.zip").write_bytes(bons[: len(bons) // 2])  # diretório central destruído
    with zipfile.ZipFile(SAIDA / "zip_aninhado.zip", "w") as z:
        z.writestr("dentro.zip", bons)

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
    gerar_geojsonseq(cobertura)
    gerar_kml_e_kmz(cobertura)
    gerar_gpx(lugares)
    gerar_xlsx(lugares)
    gerar_gml(cobertura)
    gerar_flatgeobuf(cobertura)
    gerar_dxf(cobertura)
    gerar_gdb_zip(cobertura)
    gerar_gpkg_tres_camadas(cobertura)
    gerar_csv_300_colunas_0_linhas()
    gerar_zips_malformados()
    cobertura.unlink()
    lugares.unlink()
    shutil.rmtree(SAIDA / "_shp_tmp", ignore_errors=True)
    print("gerado:", sorted(p.name for p in SAIDA.iterdir()))


if __name__ == "__main__":
    main()
