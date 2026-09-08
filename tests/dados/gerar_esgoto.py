"""Rede de esgoto SINTÉTICA com cotas, e o GeoPackage no esquema TEKSI que a carrega (item
L4-05-e-gas-e-esgoto).

Nenhum dado de cliente entra no repositório: esta é uma rede fictícia determinística (as coordenadas saem de
uma fórmula, não de sorteio, e nunca mudam). São **200 elementos**: 101 estruturas (99 poços de visita e 2
pontos de lançamento, um por bacia) e 99 coletores, em duas árvores que escoam cada uma para o seu lançamento.

A cota manda na construção: o lançamento de cada bacia é o ponto mais baixo e cada estrutura filha nasce mais
alta que a mãe. O coletor sempre vai da estrutura mais alta para a mais baixa, e as suas cotas
(`rp_from_level`, `rp_to_level`) são as das duas estruturas que ele liga. Por construção, portanto, a direção
declarada (ordem dos vértices) e a direção calculada pela cota concordam nos 99 trechos — é isso que o teste
mede, e é isso que a inversão de uma cota tem de quebrar.

O GeoPackage é escrito com o `sqlite3` da biblioteca padrão, sem GDAL: só as tabelas que o padrão OGC exige
(`gpkg_spatial_ref_sys`, `gpkg_contents`, `gpkg_geometry_columns`) mais as duas camadas do TEKSI."""

import sqlite3
import struct
from pathlib import Path

LON0, LAT0 = -46.6300, -23.5300  # referência arbitrária, não é endereço de ninguém
PASSO_GRAU = 0.0016  # ~160 m entre estruturas vizinhas
COTA_LANCAMENTO = 700.0
DEGRAU_M = 0.42  # desnível entre uma estrutura e a sua mãe
N_ESTRUTURAS = 101
N_TRECHOS = 99
CAMADA_ESTRUTURA = "vw_tww_wastewater_structure"
CAMADA_TRECHO = "vw_tww_reach"

COLUNAS_ESTRUTURA = [
    ("obj_id", "TEXT"), ("identifier", "TEXT"), ("ws_type", "TEXT"), ("status", "TEXT"),
    ("year_of_construction", "INTEGER"), ("co_level", "REAL"), ("wn_bottom_level", "REAL"),
    ("ma_depth", "REAL"), ("ma_material", "TEXT"), ("ma_dimension1", "REAL"), ("ma_function", "TEXT"),
    ("dp_terrain_level", "REAL"),
]
COLUNAS_TRECHO = [
    ("obj_id", "TEXT"), ("identifier", "TEXT"), ("rp_from_obj_id", "TEXT"), ("rp_to_obj_id", "TEXT"),
    ("rp_from_level", "REAL"), ("rp_to_level", "REAL"), ("length_effective", "REAL"),
    ("clear_height", "REAL"), ("material", "TEXT"), ("ch_function_hierarchic", "TEXT"), ("ws_status", "TEXT"),
]


def _mae(i: int) -> int:
    """Árvore determinística: a estrutura i desce para (i - 1) // 2, o que dá duas árvores binárias quando as
    raízes (0 e 1) são os dois lançamentos."""
    return (i - 1) // 2 if i > 1 else -1


def _posicao(i: int) -> tuple[float, float]:
    return (LON0 + PASSO_GRAU * (i % 11), LAT0 + PASSO_GRAU * (i // 11))


def _profundidade(i: int) -> int:
    """Quantos degraus a estrutura i está acima da raiz da sua bacia."""
    n = 0
    while i > 1:
        i = _mae(i)
        n += 1
    return n


def rede_sintetica() -> dict:
    """As duas camadas do TEKSI como listas de dicionários (coluna → valor), mais a geometria de cada linha."""
    estruturas = []
    for i in range(N_ESTRUTURAS):
        lon, lat = _posicao(i)
        cota = COTA_LANCAMENTO + DEGRAU_M * _profundidade(i)
        lancamento = i < 2
        estruturas.append({
            "obj_id": f"sin{i:05d}",
            "identifier": f"EST-{i:03d}",
            "ws_type": "discharge_point" if lancamento else "manhole",
            "status": "in_operation",
            "year_of_construction": 1998 + (i % 20),
            "co_level": round(cota + 3.0, 3),
            "wn_bottom_level": round(cota, 3),
            "ma_depth": None if lancamento else 3.0,
            "ma_material": None if lancamento else "concreto",
            "ma_dimension1": None if lancamento else 1000.0,
            "ma_function": None if lancamento else "inspecao",
            "dp_terrain_level": round(cota + 3.0, 3) if lancamento else None,
            "_lon": lon, "_lat": lat, "_cota": round(cota, 3),
        })
    trechos = []
    for i in range(2, N_ESTRUTURAS):
        mae = _mae(i)
        montante, jusante = estruturas[i], estruturas[mae]
        trechos.append({
            "obj_id": f"tre{i:05d}",
            "identifier": f"COL-{i:03d}",
            "rp_from_obj_id": montante["obj_id"],
            "rp_to_obj_id": jusante["obj_id"],
            "rp_from_level": montante["_cota"],
            "rp_to_level": jusante["_cota"],
            "length_effective": 160.0,
            "clear_height": 200.0,
            "material": "pvc",
            "ch_function_hierarchic": "secondary",
            "ws_status": "in_operation",
            "_caminho": [[montante["_lon"], montante["_lat"]], [jusante["_lon"], jusante["_lat"]]],
        })
    assert len(estruturas) + len(trechos) == 200, (len(estruturas), len(trechos))
    assert len(trechos) == N_TRECHOS
    return {"estruturas": estruturas, "trechos": trechos}


def _blob_ponto(lon: float, lat: float) -> bytes:
    wkb = struct.pack("<BIdd", 1, 1, lon, lat)
    return b"GP" + bytes([0, 0x01]) + struct.pack("<i", 4326) + wkb


def _blob_linha(caminho: list) -> bytes:
    wkb = struct.pack("<BII", 1, 2, len(caminho))
    for lon, lat in caminho:
        wkb += struct.pack("<dd", lon, lat)
    return b"GP" + bytes([0, 0x01]) + struct.pack("<i", 4326) + wkb


def _criar_tabelas_gpkg(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA application_id = 1196444487")  # 'GPKG'
    con.execute("PRAGMA user_version = 10300")
    con.execute("""CREATE TABLE gpkg_spatial_ref_sys (
        srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
        organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT)""")
    con.execute("INSERT INTO gpkg_spatial_ref_sys VALUES ('WGS 84', 4326, 'EPSG', 4326, 'GEOGCS', NULL)")
    con.execute("""CREATE TABLE gpkg_contents (
        table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
        description TEXT DEFAULT '', last_change TEXT NOT NULL DEFAULT (datetime('now')),
        min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER)""")
    con.execute("""CREATE TABLE gpkg_geometry_columns (
        table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL,
        srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
        PRIMARY KEY (table_name, column_name))""")


def _criar_camada(con: sqlite3.Connection, tabela: str, colunas: list, tipo_geom: str) -> None:
    campos = ", ".join(f'"{nome}" {tipo}' for nome, tipo in colunas)
    con.execute(f'CREATE TABLE "{tabela}" (fid INTEGER PRIMARY KEY AUTOINCREMENT, {campos}, geom BLOB)')
    con.execute("INSERT INTO gpkg_contents(table_name, data_type, identifier, srs_id) VALUES (?, ?, ?, 4326)",
                (tabela, "features", tabela))
    con.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, 4326, 0, 0)", (tabela, tipo_geom))


def escrever_geopackage(caminho: str | Path, rede: dict | None = None) -> dict:
    """Escreve o GeoPackage no esquema TEKSI e devolve a rede que foi escrita."""
    rede = rede or rede_sintetica()
    caminho = Path(caminho)
    if caminho.exists():
        caminho.unlink()
    con = sqlite3.connect(caminho)
    try:
        _criar_tabelas_gpkg(con)
        _criar_camada(con, CAMADA_ESTRUTURA, COLUNAS_ESTRUTURA, "POINT")
        _criar_camada(con, CAMADA_TRECHO, COLUNAS_TRECHO, "LINESTRING")
        nomes_e = [n for n, _ in COLUNAS_ESTRUTURA]
        con.executemany(
            f'INSERT INTO "{CAMADA_ESTRUTURA}" ({", ".join(nomes_e)}, geom) '
            f'VALUES ({", ".join("?" * len(nomes_e))}, ?)',
            [[e[n] for n in nomes_e] + [_blob_ponto(e["_lon"], e["_lat"])] for e in rede["estruturas"]],
        )
        nomes_t = [n for n, _ in COLUNAS_TRECHO]
        con.executemany(
            f'INSERT INTO "{CAMADA_TRECHO}" ({", ".join(nomes_t)}, geom) '
            f'VALUES ({", ".join("?" * len(nomes_t))}, ?)',
            [[t[n] for n in nomes_t] + [_blob_linha(t["_caminho"])] for t in rede["trechos"]],
        )
        con.commit()
    finally:
        con.close()
    return rede
