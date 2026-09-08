"""Calculadora, reclassificação e amostragem (item L2-05-e).

A cláusula do portão que este arquivo mede é a da calculadora: o NDVI de uma cena Sentinel-2 tem de sair
IGUAL, pixel a pixel, ao que o TiTiler devolveria para a mesma expressão. A comparação é feita contra
`rio_tiler.expression.apply_expression` — a função que o TiTiler chama para avaliar expressão — sobre os
mesmos arrays lidos do mesmo arquivo, com tolerância 1e-6.
"""

import subprocess
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.raster import calculo

CENA_S2 = Path("/home/dev/plataforma/pipeline/data/raw")
B04 = CENA_S2 / "S2B_23KLQ_20260818_0_L2A_B04.tif"   # vermelho, 10 m
B08 = CENA_S2 / "S2B_23KLQ_20260818_0_L2A_B08.tif"   # infravermelho próximo, 10 m
JANELA = 512


def _recorte(origem: Path, destino: Path) -> Path:
    subprocess.run(["gdal_translate", "-q", "-srcwin", "4000", "4000", str(JANELA), str(JANELA),
                    str(origem), str(destino)], check=True)
    return destino


@pytest.fixture(scope="module")
def cena_s2(tmp_path_factory):
    """Duas bandas de uma cena Sentinel-2 real da casa, num recorte de 512x512 (nada de dado de cliente:
    é uma cena aberta do acervo de teste do pipeline)."""
    if not (B04.exists() and B08.exists()):
        pytest.skip("cena Sentinel-2 do acervo da casa ausente nesta máquina")
    tmp = tmp_path_factory.mktemp("s2")
    v = _recorte(B04, tmp / "b04.tif")
    n = _recorte(B08, tmp / "b08.tif")
    juntas = tmp / "s2_2bandas.tif"
    # empilhado com rasterio, e não com gdal_merge.py: os utilitários do GDAL escritos em Python usam
    # `osgeo.gdal_array`, que nesta máquina não carrega com numpy 2 ("numpy.core.multiarray failed to
    # import"). Os utilitários em C (gdalwarp, gdaldem, gdal_contour, gdal_viewshed) não dependem dele.
    with rasterio.open(v) as a, rasterio.open(n) as b:
        perfil = a.profile.copy()
        perfil.update(count=2)
        with rasterio.open(juntas, "w", **perfil) as dst:
            dst.write(a.read(1), 1)
            dst.write(b.read(1), 2)
    return juntas


def test_ndvi_igual_ao_titiler(cena_s2, tmp_path):
    """(b2-b1)/(b2+b1) sobre a cena real: a diferença máxima contra o avaliador do TiTiler tem de ficar
    abaixo de 1e-6."""
    from rio_tiler.expression import apply_expression

    expressao = "(b2-b1)/(b2+b1)"
    saida = tmp_path / "ndvi.tif"
    with rasterio.open(cena_s2) as ds:
        info = calculo.calcular([ds], expressao, saida, dtype="float64", nodata=None)
        pilha = ds.read()
    referencia = apply_expression([expressao], ["b1", "b2"], pilha)[0]
    with rasterio.open(saida) as ds:
        meu = ds.read(1)
    assert meu.shape == referencia.shape
    diferenca = float(np.nanmax(np.abs(meu - np.asarray(referencia, dtype="float64"))))
    assert diferenca <= 1e-6, f"diferença máxima {diferenca} contra a expressão do TiTiler"
    assert info["bandas_usadas"] == [1, 2]


def test_calculo_escreve_bloco_a_bloco(cena_s2, tmp_path, monkeypatch):
    """A saída é escrita janela por janela: nenhuma leitura pede o raster inteiro."""
    formas = []
    original = rasterio.DatasetReader.read

    def espiao(self, *a, **kw):
        janela = kw.get("window")
        if janela is not None:
            formas.append((int(janela.height), int(janela.width)))
        return original(self, *a, **kw)

    monkeypatch.setattr(rasterio.DatasetReader, "read", espiao)
    with rasterio.open(cena_s2) as ds:
        calculo.calcular([ds], "b1+b2", tmp_path / "soma.tif", dtype="float32", nodata=-9999.0)
        maior = max(ds.block_shapes[0])
    assert formas, "a calculadora leu sem janela"
    assert max(max(f) for f in formas) <= maior


def _raster(caminho, arr, *, crs="EPSG:32723", nodata=None, res=10.0, x0=300000.0, y0=7400000.0):
    with rasterio.open(caminho, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=str(arr.dtype), crs=crs, nodata=nodata,
                       transform=from_origin(x0, y0, res, res)) as ds:
        ds.write(arr, 1)
    return caminho


def test_expressao_fora_da_gramatica_e_recusada(tmp_path):
    a = _raster(tmp_path / "a.tif", np.ones((8, 8), dtype="float32"))
    with rasterio.open(a) as ds:
        for ruim in ("__import__('os')", "b1; drop", "1+1", "eval(b1)"):
            with pytest.raises(calculo.ErroCalculo):
                calculo.calcular([ds], ruim, tmp_path / "x.tif")


def test_rasters_desalinhados_sao_recusados_com_o_motivo(tmp_path):
    a = _raster(tmp_path / "a.tif", np.ones((8, 8), dtype="float32"))
    b = _raster(tmp_path / "b.tif", np.ones((8, 9), dtype="float32"))
    c = _raster(tmp_path / "c.tif", np.ones((8, 8), dtype="float32"), crs="EPSG:31983")
    with rasterio.open(a) as da, rasterio.open(b) as db, rasterio.open(c) as dc:
        with pytest.raises(calculo.ErroCalculo, match="diferente do primeiro"):
            calculo.conferir_alinhamento([da, db])
        with pytest.raises(calculo.ErroCalculo, match="CRS"):
            calculo.conferir_alinhamento([da, dc])


def test_bandas_numeradas_em_sequencia_sobre_os_rasters(tmp_path):
    a = _raster(tmp_path / "a.tif", np.full((4, 4), 2.0, dtype="float32"))
    b = _raster(tmp_path / "b.tif", np.full((4, 4), 5.0, dtype="float32"))
    saida = tmp_path / "soma.tif"
    with rasterio.open(a) as da, rasterio.open(b) as db:
        assert calculo.mapa_de_bandas([da, db]) == [(0, 1), (1, 1)]
        calculo.calcular([da, db], "b1*10+b2", saida, dtype="float32")
    with rasterio.open(saida) as ds:
        assert float(ds.read(1).min()) == pytest.approx(25.0)


def test_nodata_de_entrada_vira_nodata_de_saida(tmp_path):
    arr = np.ones((4, 4), dtype="float32")
    arr[0, 0] = -9999.0
    a = _raster(tmp_path / "a.tif", arr, nodata=-9999.0)
    saida = tmp_path / "s.tif"
    with rasterio.open(a) as ds:
        calculo.calcular([ds], "b1*2", saida, dtype="float32", nodata=-1.0)
    with rasterio.open(saida) as ds:
        lido = ds.read(1)
    assert lido[0, 0] == pytest.approx(-1.0)
    assert lido[1, 1] == pytest.approx(2.0)


def test_tabela_de_reclassificacao():
    faixas = calculo.tabela_de_reclassificacao("0-10:1; 10-20:2; 20-*:3")
    assert faixas[0] == (0.0, 10.0, 1.0)
    assert faixas[2][1] == float("inf")
    assert calculo.tabela_de_reclassificacao("*-0:nodata")[0][2] is None
    for ruim in ("0-10", "10-0:1", "abc", ""):
        with pytest.raises(calculo.ErroCalculo):
            calculo.tabela_de_reclassificacao(ruim)


def test_reclassificar_respeita_faixa_fechada_no_inicio(tmp_path):
    arr = np.array([[0, 5, 10, 15], [20, 25, 30, 35]], dtype="float32")
    a = _raster(tmp_path / "a.tif", arr)
    saida = tmp_path / "classes.tif"
    with rasterio.open(a) as ds:
        info = calculo.reclassificar(ds, calculo.tabela_de_reclassificacao("0-10:1;10-20:2"), saida,
                                     dtype="int16", nodata=-1)
    with rasterio.open(saida) as ds:
        lido = ds.read(1)
    assert lido[0].tolist() == [1, 1, 2, 2]
    assert lido[1].tolist() == [-1, -1, -1, -1]   # 20 em diante fica fora das faixas
    assert info["fora_das_faixas"] == 4


def test_amostrar_em_pontos_dentro_e_fora(tmp_path):
    arr = np.arange(16, dtype="float32").reshape(4, 4)
    arr[0, 0] = -9999.0
    a = _raster(tmp_path / "a.tif", arr, nodata=-9999.0, res=10.0)
    with rasterio.open(a) as ds:
        r = calculo.amostrar(ds, [(300005.0, 7399995.0), (300015.0, 7399995.0), (0.0, 0.0)], [1])
    assert r[0] == [None]           # nodata
    assert r[1] == [1.0]
    assert r[2] == [None]           # fora da extensão
