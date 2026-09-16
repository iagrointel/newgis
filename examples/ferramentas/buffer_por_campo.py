"""nome: buffer_por_campo
titulo: Buffer por campo
descricao: >
  Ferramenta de exemplo (item L2-16-c): lê um item do catálogo cujo dado carrega GeoJSON, desenha
  um buffer em torno de cada feição (cada "campo") e declara as saídas. A leitura do item usa o
  SDK da plataforma (o token do contêiner é de leitura, L2-16-b) e a saída é declarada com
  plat_geo.saidas, para o job registrar o item com a procedência. O buffer é calculado no SRID
  métrico informado; a entrada e a saída GeoJSON ficam em WGS 84 (EPSG:4326), convenção do
  catálogo.
parametros:
  - nome: entrada
    tipo: item
    rotulo: Item de entrada
    descricao: id de um item do catálogo que carrega GeoJSON em 4326 (geometria ou coleção de feições)
  - nome: distancia_m
    tipo: numero
    rotulo: Distância do buffer (m)
    padrao: 100
    minimo: 0
    maximo: 100000
  - nome: srid
    tipo: inteiro
    rotulo: SRID métrico
    padrao: 31983
    descricao: SRID MÉTRICO (metros) do cálculo; 31983 é SIRGAS 2000 UTM 23S
saidas:
  - nome: buffer
    tipo: item
    rotulo: Buffers por campo (GeoJSON em 4326)
  - nome: resumo
    tipo: texto
    rotulo: Resumo da execução
"""

import json
import os

import pyproj
from plat_geo import saidas
from plat_geo.cliente import Plataforma
from shapely.geometry import mapping, shape
from shapely.ops import transform as transformar_forma

DIRETORIO = os.environ.get("PLAT_SAIDA_DIR") or "."
with open(os.path.join(DIRETORIO, "entradas.json"), encoding="utf-8") as _arq:
    PARAMETROS = json.load(_arq)["parametros"]

GEOJSON_FORMAS = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon",
                  "MultiPolygon", "GeometryCollection", "Feature", "FeatureCollection"}


def _geojson_do_item(item: dict) -> dict:
    """Procura GeoJSON nos dados do item (a chave varia com o tipo que o produziu)."""
    dados = item.get("dados") or {}
    candidato = dados.get("geometria")
    if isinstance(candidato, dict) and candidato.get("type") in GEOJSON_FORMAS:
        return candidato
    resultado = dados.get("resultado")
    if isinstance(resultado, dict):
        for valor in resultado.values():
            if isinstance(valor, dict) and valor.get("type") in GEOJSON_FORMAS:
                return valor
    raise SystemExit(f"o item {item.get('id')} não carrega GeoJSON nos dados "
                     "(procurado em dados.geometria e dados.resultado.*)")


def _feicoes(geojson: dict) -> list[dict]:
    """Geometrias de entrada: cada feição (cada campo) ou a geometria única."""
    if geojson["type"] == "FeatureCollection":
        return [f.get("geometry") for f in geojson.get("features", []) if f.get("geometry")]
    if geojson["type"] == "Feature":
        return [geojson["geometry"]]
    return [geojson]


def main() -> None:
    pla = Plataforma.do_ambiente()
    item = pla.catalogo.abrir(PARAMETROS["entrada"])
    geojson = _geojson_do_item(item)
    srid = int(PARAMETROS["srid"])
    para_metrico = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326), pyproj.CRS.from_user_input(srid),
                                               always_xy=True)
    para_4326 = pyproj.Transformer.from_crs(pyproj.CRS.from_user_input(srid), pyproj.CRS.from_epsg(4326),
                                            always_xy=True)
    distancia = float(PARAMETROS["distancia_m"])
    features = []
    area_total = 0.0
    for geometria in _feicoes(geojson):
        metrica = transformar_forma(para_metrico.transform, shape(geometria))
        bruto = metrica.buffer(distancia)
        geografico = transformar_forma(para_4326.transform, bruto)
        features.append({"type": "Feature", "properties": {"area_m2": bruto.area},
                         "geometry": mapping(geografico)})
        area_total += bruto.area
    saidas.gravar("buffer", {"type": "FeatureCollection", "features": features})
    saidas.gravar("resumo", json.dumps({"campos": len(features), "area_total_m2": round(area_total, 2),
                                        "distancia_m": distancia, "srid": srid},
                                       ensure_ascii=False))


if __name__ == "__main__":
    main()
