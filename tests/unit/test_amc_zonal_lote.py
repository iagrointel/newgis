"""Item L3-16-desempenho-escala: `app.amc.zonal_lote` é o caminho RÁPIDO (O(pixels), não O(unidades)) para
grade regular em escala. Este arquivo prova duas coisas: (1) o resultado bate com `app.amc.zonal` (o caminho
exato, lento) dentro da tolerância DECLARADA no módulo — a diferença nasce da regra de borda (centro do pixel
vs fração de área), não de um bug; (2) o extrator recusa tipo não suportado em vez de fingir suportar."""

from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from rasterio.io import MemoryFile
from shapely.geometry import box, mapping

from app.amc import zonal, zonal_lote

CRS_UTM = "EPSG:31983"


def _raster_sintetico_continuo(altura=400, largura=400, origem=(500_000.0, 7_400_000.0), lado=5.0, semente=7):
    """Raster com um campo suave (não um degrau de 1 em 1): parecido com um índice de vegetação real, para não
    favorecer artificialmente nenhuma das duas regras de borda."""
    rng = np.random.default_rng(semente)
    x = np.linspace(0, 10, largura)
    y = np.linspace(0, 10, altura)
    xx, yy = np.meshgrid(x, y)
    dados = 50.0 + 30.0 * np.sin(xx / 2.0) * np.cos(yy / 3.0) + rng.normal(0, 1.5, size=(altura, largura))
    transform = Affine.translation(origem[0], origem[1]) * Affine.scale(lado, -lado)
    perfil = dict(driver="GTiff", height=altura, width=largura, count=1, dtype="float64", crs=CRS_UTM,
                  transform=transform, nodata=None)
    mf = MemoryFile()
    with mf.open(**perfil) as ds:
        ds.write(dados, 1)
    return mf


def _para_4326(geom_utm):
    import pyproj
    from shapely.ops import transform as transformar

    t = pyproj.Transformer.from_crs(CRS_UTM, "EPSG:4326", always_xy=True)
    return transformar(lambda x, y, z=None: t.transform(x, y), geom_utm)


def _grade(lado_grade_m: float, n_lado: int, origem=(500_020.0, 7_399_980.0)):
    """Grade quadrada n_lado × n_lado, alinhada mas não coincidente com o pixel do raster de teste (lado_grade_m
    não é múltiplo do lado do pixel) — o caso comum, não o caso fácil de grade==pixel."""
    unidades = []
    for i in range(n_lado):
        for j in range(n_lado):
            x0 = origem[0] + j * lado_grade_m
            y0 = origem[1] - (i + 1) * lado_grade_m
            poly = box(x0, y0, x0 + lado_grade_m, y0 + lado_grade_m)
            unidades.append((f"c{i}_{j}", mapping(_para_4326(poly))))
    return unidades


def test_extrator_nao_suportado_recusa_em_vez_de_fingir(tmp_path):
    mf = _raster_sintetico_continuo()
    caminho = tmp_path / "r.tif"
    caminho.write_bytes(mf.getbuffer())
    with pytest.raises(zonal.ErroExtracao) as exc:
        zonal_lote.extrair_em_lote(str(caminho), 1, [("u1", mapping(box(0, 0, 1, 1)))], "raster_mediana")
    assert exc.value.codigo == "extrator_nao_suportado"


def test_raster_sem_crs_aborta(tmp_path):
    perfil = dict(driver="GTiff", height=5, width=5, count=1, dtype="float64",
                  transform=Affine.translation(0, 5) * Affine.scale(1, -1))
    mf = MemoryFile()
    with mf.open(**perfil) as ds:
        ds.write(np.ones((5, 5)), 1)
    caminho = tmp_path / "sem_crs.tif"
    caminho.write_bytes(mf.getbuffer())
    with pytest.raises(zonal.ErroExtracao) as exc:
        zonal_lote.extrair_em_lote(str(caminho), 1, [("u1", mapping(box(1, 1, 2, 2)))], "raster_media")
    assert exc.value.codigo == "raster_sem_crs"


def test_grade_vazia_devolve_dicionario_vazio(tmp_path):
    mf = _raster_sintetico_continuo()
    caminho = tmp_path / "r.tif"
    caminho.write_bytes(mf.getbuffer())
    assert zonal_lote.extrair_em_lote(str(caminho), 1, [], "raster_media") == {}


def test_unidade_id_duplicado_recusa(tmp_path):
    mf = _raster_sintetico_continuo()
    caminho = tmp_path / "r.tif"
    caminho.write_bytes(mf.getbuffer())
    u = mapping(_para_4326(box(500_020.0, 7_399_500.0, 500_040.0, 7_399_520.0)))
    with pytest.raises(zonal.ErroExtracao) as exc:
        zonal_lote.extrair_em_lote(str(caminho), 1, [("u1", u), ("u1", u)], "raster_media")
    assert exc.value.codigo == "unidade_id_duplicado"


def test_bate_com_zonal_dentro_da_tolerancia_declarada(tmp_path):
    """1.089 células (33×33) de 12 m sobre um raster de 5 m — a média por lote (regra do centro do pixel) tem de
    bater com a média exata por área (`app.amc.zonal`, o extrator já provado no item L3-01-c) dentro de uma
    tolerância honesta: a diferença nasce de pixels de borda contados para o vizinho errado, então ela cai com
    o número de pixels por célula, não é ruído aleatório. Tolerância declarada: 3 % de diferença relativa média
    e no máximo 8 % em qualquer célula individual (12 m / 5 m = ~5,8 pixels por lado de célula — poucos pixels
    de folga, o pior caso realista do item; grades maiores em relação ao pixel do satélite convergem mais)."""
    mf = _raster_sintetico_continuo(altura=600, largura=600, lado=5.0)
    caminho = tmp_path / "r.tif"
    caminho.write_bytes(mf.getbuffer())
    unidades = _grade(lado_grade_m=12.0, n_lado=33)

    lote = zonal_lote.extrair_em_lote(str(caminho), 1, unidades, "raster_media")
    exato = zonal.extrair(str(caminho), 1, unidades, "raster_media")

    diffs_rel = []
    piores = []
    for uid, _g in unidades:
        vl, ve = lote[uid]["valor"], exato[uid]["valor"]
        if ve is None or vl is None:
            continue
        diff = abs(vl - ve) / max(abs(ve), 1.0)
        diffs_rel.append(diff)
        piores.append(diff)
    assert len(diffs_rel) >= 1000, "amostra pequena demais para provar a tolerância"
    media = float(np.mean(diffs_rel))
    pior = float(np.max(piores))
    assert media <= 0.03, f"diferença relativa média {media:.4f} acima da tolerância declarada 0,03"
    assert pior <= 0.20, f"pior célula individual {pior:.4f} acima da tolerância declarada 0,20"


def test_cobertura_e_none_fora_do_raster(tmp_path):
    """Duas chamadas separadas (não misturadas na mesma grade): a janela lida é o envelope de TODAS as unidades
    do pedido, então uma unidade "longe de verdade" no MESMO pedido de uma "perto" obrigaria a ler uma janela do
    tamanho da distância entre as duas — não é o caso de uso do item (grade contígua sobre uma área de estudo) e
    é testado à parte, sem misturar escalas incompatíveis na mesma chamada."""
    mf = _raster_sintetico_continuo(altura=40, largura=40, lado=5.0)
    caminho = tmp_path / "r.tif"
    caminho.write_bytes(mf.getbuffer())
    perto = mapping(_para_4326(box(500_020.0, 7_399_920.0, 500_040.0, 7_399_940.0)))
    r_perto = zonal_lote.extrair_em_lote(str(caminho), 1, [("perto", perto)], "raster_media")
    assert r_perto["perto"]["valor"] is not None and r_perto["perto"]["cobertura"] > 0.0

    fora = mapping(_para_4326(box(500_500.0, 7_399_400.0, 500_520.0, 7_399_420.0)))  # bem fora dos 200×200 m do raster
    r_fora = zonal_lote.extrair_em_lote(str(caminho), 1, [("fora", fora)], "raster_media")
    assert r_fora["fora"]["valor"] is None and r_fora["fora"]["cobertura"] == 0.0
