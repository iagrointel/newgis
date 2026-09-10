"""Extrato BDGD SINTÉTICO com a unidade do arquivo escolhida por quem chama (item L4-01-e).

Por que sintético, se a família L4 tem o extrato real da casa. Porque a cláusula deste item é uma
comparação entre DOIS arquivos que só diferem na unidade — o mesmo trecho em metro e em quilômetro, a mesma
energia em quilowatt-hora e em megawatt-hora — e isso não existe no arquivo real, tem de ser construído. O
extrato real continua sendo a régua do item irmão L4-01-c (contagem conferida contra o arquivo), e este
gerador não o substitui: ele constrói o par de arquivos que a refutação exige, com geometria de verdade
(comprimento geodésico medido, não declarado) e ordem de grandeza de rede de distribuição real.

O que sai: um GPKG (o GDAL lê GPKG e FileGDB pela mesma porta; o importador não sabe a diferença) com as
camadas SUB, CTMT, PONNOT, SSDMT, UNTRMT e UCBT_tab. Os números são pequenos de propósito — 12 trechos,
3 transformadores, 30 unidades consumidoras — para caber no orçamento de tempo de uma trilha.

Uso:
    caminho_m = escrever(tmp_path / "metros.gpkg", unidade_comp="m", unidade_ene="kWh")
    caminho_km = escrever(tmp_path / "km.gpkg", unidade_comp="km", unidade_ene="MWh")
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString, Point

SRID = 4674  # SIRGAS 2000, o datum da BDGD
LON0, LAT0 = -51.30, -29.60   # sul do Brasil, longe de qualquer cadastro real
TRECHOS = 12
TRAFOS = 3
UCS_POR_TRAFO = 10
# energia de uma unidade consumidora de baixa tensão, em quilowatt-hora por mês: ordem de grandeza de
# residência brasileira (Anuário Estatístico de Energia Elétrica: média nacional próxima de 160 kWh/mês)
ENE_MES_KWH = 180.0
POT_NOM_KVA = 45.0   # transformador de distribuição pequeno

_GEOD = Geod(ellps="WGS84")


def _linha(i: int) -> LineString:
    """Trecho i: um segmento leste-oeste de ~200 m, encadeado com o anterior."""
    passo = 0.002  # ≈ 195 m nesta latitude
    return LineString([(LON0 + i * passo, LAT0), (LON0 + (i + 1) * passo, LAT0)])


def comprimento_geodesico_m(i: int) -> float:
    return _GEOD.geometry_length(_linha(i))


def energia_anual_kwh() -> float:
    """A energia anual que o arquivo declara, em quilowatt-hora — a régua contra a qual o teste compara os
    dois arquivos (o de kWh e o de MWh têm de dar este mesmo número depois da conversão)."""
    return TRAFOS * UCS_POR_TRAFO * ENE_MES_KWH * 12.0


def escrever(destino: str | Path, unidade_comp: str = "m", unidade_ene: str = "kWh") -> str:
    """Escreve o extrato e devolve o caminho. `unidade_comp` em {'m','km'}, `unidade_ene` em
    {'kWh','MWh'} — é só a unidade em que os MESMOS valores são escritos no arquivo."""
    if unidade_comp not in ("m", "km"):
        raise ValueError("unidade_comp tem de ser 'm' ou 'km'")
    if unidade_ene not in ("kWh", "MWh"):
        raise ValueError("unidade_ene tem de ser 'kWh' ou 'MWh'")
    destino = Path(destino)
    if destino.exists():
        destino.unlink()
    destino.parent.mkdir(parents=True, exist_ok=True)
    divisor_comp = 1.0 if unidade_comp == "m" else 1000.0
    divisor_ene = 1.0 if unidade_ene == "kWh" else 1000.0

    def gravar(df, camada: str) -> None:
        df.to_file(destino, layer=camada, driver="GPKG")

    # subestação e alimentador
    gravar(gpd.GeoDataFrame(
        {"COD_ID": ["SUB1"], "NOME": ["subestacao de teste"]},
        geometry=[Point(LON0 - 0.002, LAT0)], crs=f"EPSG:{SRID}"), "SUB")
    gravar(gpd.GeoDataFrame(
        {"COD_ID": ["CTMT1"], "NOME": ["alimentador de teste"], "SUB": ["SUB1"]},
        geometry=[None], crs=f"EPSG:{SRID}"), "CTMT")

    # pontos de conexão: uma ponta por trecho, mais a ponta final
    pontos = [f"PN{i}" for i in range(TRECHOS + 1)]
    gravar(gpd.GeoDataFrame(
        {"COD_ID": pontos, "TIP_PN": ["P"] * len(pontos)},
        geometry=[Point(LON0 + i * 0.002, LAT0) for i in range(TRECHOS + 1)],
        crs=f"EPSG:{SRID}"), "PONNOT")

    # trechos de média tensão: COMP é o comprimento geodésico REAL do segmento, escrito na unidade pedida
    gravar(gpd.GeoDataFrame(
        {
            "COD_ID": [f"SSDMT{i}" for i in range(TRECHOS)],
            "PN_CON_1": [f"PN{i}" for i in range(TRECHOS)],
            "PN_CON_2": [f"PN{i + 1}" for i in range(TRECHOS)],
            "CTMT": ["CTMT1"] * TRECHOS,
            "FAS_CON": ["ABC"] * TRECHOS,
            "COMP": [round(comprimento_geodesico_m(i) / divisor_comp, 9) for i in range(TRECHOS)],
        },
        geometry=[_linha(i) for i in range(TRECHOS)], crs=f"EPSG:{SRID}"), "SSDMT")

    # transformadores: a potência instalada é a âncora da detecção da unidade de energia
    gravar(gpd.GeoDataFrame(
        {
            "COD_ID": [f"TRAFO{t}" for t in range(TRAFOS)],
            "PAC_1": [f"PN{2 + t * 3}" for t in range(TRAFOS)],
            "CTMT": ["CTMT1"] * TRAFOS,
            "POT_NOM": [POT_NOM_KVA] * TRAFOS,
            "TIP_TRAFO": ["1"] * TRAFOS,
        },
        geometry=[Point(LON0 + (2 + t * 3) * 0.002, LAT0) for t in range(TRAFOS)],
        crs=f"EPSG:{SRID}"), "UNTRMT")

    # unidades consumidoras: os doze meses na unidade pedida
    linhas = []
    for t in range(TRAFOS):
        for u in range(UCS_POR_TRAFO):
            linha = {
                "PN_CON": f"PN{2 + t * 3}",
                "UNI_TR_MT": f"TRAFO{t}",
                "CTMT": "CTMT1",
                "CLAS_SUB": "RE1",
                "SIT_ATIV": "AT",
                "COD_ID": f"UC{t}_{u}",
            }
            for m in range(1, 13):
                linha[f"ENE_{m:02d}"] = round(ENE_MES_KWH / divisor_ene, 9)
            linhas.append(linha)
    gpd.GeoDataFrame(pd.DataFrame(linhas), geometry=[None] * len(linhas), crs=f"EPSG:{SRID}").to_file(
        destino, layer="UCBT_tab", driver="GPKG")
    return str(destino)


if __name__ == "__main__":  # pragma: no cover - conferência à mão
    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        for uc, ue in (("m", "kWh"), ("km", "MWh")):
            caminho = escrever(Path(pasta) / f"{uc}_{ue}.gpkg", uc, ue)
            print(caminho, "comprimento geodésico total (m):",
                  round(sum(comprimento_geodesico_m(i) for i in range(TRECHOS)), 3),
                  "energia anual (kWh):", energia_anual_kwh())
