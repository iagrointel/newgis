"""Estatísticas zonais (item L2-05-e): compara com o `rasterstats` — a implementação de referência da
literatura para esta conta — e mede o que a fração de pixel muda.

Por que o `rasterstats` e não o `exactextract`: o `exactextract` (fração de pixel exata) não está
instalado nesta máquina, e a ferramenta usa fração por sub-amostragem. O `rasterstats` fica como
referência do critério CLÁSSICO (pixel entra inteiro quando o centro cai no polígono), que é o modo
`fracao=False` da ferramenta; nesse modo a exigência é igualdade, não aproximação.
"""

import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.raster import zonal

rasterstats = pytest.importorskip("rasterstats", reason="referência de estatísticas zonais")

LADO = 200
RESOLUCAO = 10.0
X0, Y0 = 300_000.0, 7_400_000.0


@pytest.fixture(scope="module")
def raster(tmp_path_factory):
    """Raster contínuo de 200x200 (float32, EPSG:32723) com padrão determinístico e nodata declarado."""
    caminho = tmp_path_factory.mktemp("zonal") / "continuo.tif"
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    arr = (10.0 + xx * 0.5 + yy * 0.25 + 3.0 * np.sin(xx / 7.0)).astype("float32")
    arr[0:5, 0:5] = -9999.0
    with rasterio.open(caminho, "w", driver="GTiff", height=LADO, width=LADO, count=1, dtype="float32",
                       crs="EPSG:32723", nodata=-9999.0, transform=from_origin(X0, Y0, RESOLUCAO, RESOLUCAO),
                       tiled=True, blockxsize=64, blockysize=64) as ds:
        ds.write(arr, 1)
    return caminho


@pytest.fixture(scope="module")
def raster_classes(tmp_path_factory):
    """Raster categórico (uint8) com quatro classes — o caso do mapa de uso do solo."""
    caminho = tmp_path_factory.mktemp("zonal") / "classes.tif"
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    arr = (((xx // 20) + (yy // 30)) % 4 + 1).astype("uint8")
    with rasterio.open(caminho, "w", driver="GTiff", height=LADO, width=LADO, count=1, dtype="uint8",
                       crs="EPSG:32723", nodata=0, transform=from_origin(X0, Y0, RESOLUCAO, RESOLUCAO)) as ds:
        ds.write(arr, 1)
    return caminho


def quadrado(col: float, lin: float, largura_px: float, altura_px: float) -> dict:
    """Polígono em coordenadas de mapa, dado em pixels a partir do canto superior esquerdo."""
    x0 = X0 + col * RESOLUCAO
    y0 = Y0 - (lin + altura_px) * RESOLUCAO
    x1 = X0 + (col + largura_px) * RESOLUCAO
    y1 = Y0 - lin * RESOLUCAO
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def limites(g: dict):
    pontos = g["coordinates"][0]
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


ZONAS = [
    quadrado(10, 10, 40, 30),
    quadrado(60.5, 20.3, 25.4, 18.7),   # bordas fora da grade: é aqui que a fração muda alguma coisa
    quadrado(120, 100, 60, 60),
    quadrado(2, 2, 8, 8),               # sobre o bloco de nodata
]


def _minhas(caminho, geometrias, pedidas, **kw):
    with rasterio.open(caminho) as ds:
        return [zonal.estatisticas_da_zona(ds, 1, g, limites(g), pedidas, **kw) for g in geometrias]


def test_modo_classico_igual_ao_rasterstats(raster):
    """`fracao=False` reproduz o rasterstats — mesma contagem, mesma soma, mesma média."""
    pedidas = ("contagem", "soma", "media", "minimo", "maximo", "desvio", "mediana")
    meus = _minhas(raster, ZONAS, pedidas, fracao=False)
    deles = rasterstats.zonal_stats(
        [{"type": "Feature", "properties": {}, "geometry": g} for g in ZONAS], str(raster),
        stats=["count", "sum", "mean", "min", "max", "std", "median"], all_touched=False, nodata=-9999.0)
    for meu, dele in zip(meus, deles, strict=True):
        assert meu["contagem"] == dele["count"], (meu, dele)
        if dele["count"] == 0:
            continue
        # rel=1e-6 e não zero: o rasterstats soma em float32 (o tipo do raster) e aqui a soma é
        # acumulada em float64, então as duas contas divergem na última casa do float32 — a diferença
        # medida é da ordem de 4e-8, quatro ordens de grandeza abaixo da cláusula de 0,5 %.
        assert meu["soma"] == pytest.approx(dele["sum"], rel=1e-6)
        assert meu["media"] == pytest.approx(dele["mean"], rel=1e-6)
        assert meu["minimo"] == pytest.approx(dele["min"], rel=1e-9)
        assert meu["maximo"] == pytest.approx(dele["max"], rel=1e-9)
        assert meu["desvio"] == pytest.approx(dele["std"], rel=1e-6)
        # convenção declarada: a mediana da ferramenta é PONDERADA — o valor em que o peso acumulado
        # cruza a metade — e por isso, num conjunto de contagem par, ela devolve o valor central de
        # baixo em vez da média dos dois centrais (que é o que o numpy faz e não se define com peso).
        # A diferença medida fica na casa de 1e-5 relativo.
        assert meu["mediana"] == pytest.approx(dele["median"], rel=1e-3)


def test_fracao_fica_a_meio_por_cento_do_rasterstats(raster):
    """A ponderação por fração de pixel muda a média por muito pouco em zona de tamanho razoável: é a
    cláusula do portão (0,5 %). A diferença aparece na BORDA, e por isso encolhe com a zona maior."""
    pedidas = ("contagem", "media")
    meus = _minhas(raster, ZONAS[:3], pedidas, fracao=True)
    deles = rasterstats.zonal_stats(
        [{"type": "Feature", "properties": {}, "geometry": g} for g in ZONAS[:3]], str(raster),
        stats=["mean"], all_touched=False, nodata=-9999.0)
    for meu, dele in zip(meus, deles, strict=True):
        erro = abs(meu["media"] - dele["mean"]) / abs(dele["mean"])
        assert erro <= 0.005, f"média com fração {meu['media']} vs rasterstats {dele['mean']} ({erro:.5f})"


def test_fracao_da_peso_parcial_ao_pixel_de_borda(raster):
    """Zona de 1x1 pixel fora da grade: quatro pixels são TOCADOS e a soma dos pesos vale ~1 pixel.
    A tolerância é a quantização declarada da amostragem: com SUBPIXEL=5 o peso de cada pixel de borda
    anda de 1/25 em 1/25, e a zona toca quatro deles."""
    g = quadrado(50.37, 50.61, 1, 1)
    with rasterio.open(raster) as ds:
        r = zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("contagem", "media"), fracao=True)
    assert r["contagem"] == 4
    assert r["peso"] == pytest.approx(1.0, abs=4 / zonal.SUBPIXEL**2)


def test_zona_fora_da_extensao_devolve_zero_e_nao_erro(raster):
    g = quadrado(-500, -500, 10, 10)
    with rasterio.open(raster) as ds:
        r = zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("contagem", "media", "soma"))
    assert r["contagem"] == 0 and r["media"] is None and r["soma"] is None


def test_nodata_nao_entra_na_conta(raster):
    """A zona 4 cai sobre o bloco de nodata: a contagem tem de excluir esses pixels."""
    g = ZONAS[3]
    with rasterio.open(raster) as ds:
        r = zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("contagem", "media"), fracao=False)
    # a zona cobre 8x8 pixels (colunas 2 a 9, linhas 2 a 9); o bloco de nodata (linhas e colunas 0 a 4)
    # entra nela num quadrado de 3x3 — sobram 55 pixels válidos
    assert r["contagem"] == 55
    assert r["media"] is not None


def test_majoritario_e_percentual_por_classe(raster_classes):
    g = quadrado(0, 0, 40, 60)
    with rasterio.open(raster_classes) as ds:
        r = zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("contagem", "majoritario", "classes", "mediana"),
                                       fracao=False)
    soma = sum(r["classes"].values())
    assert soma == pytest.approx(100.0, abs=1e-6)
    assert str(int(r["majoritario"])) in r["classes"]
    deles = rasterstats.zonal_stats([{"type": "Feature", "properties": {}, "geometry": g}], str(raster_classes),
                                    stats=["majority", "median"], nodata=0)[0]
    assert r["majoritario"] == pytest.approx(float(deles["majority"]))
    assert r["mediana"] == pytest.approx(float(deles["median"]))


def test_teto_de_mediana_em_ponto_flutuante(raster, monkeypatch):
    """Zona grande demais em raster de ponto flutuante recusa a mediana em vez de encher a memória."""
    monkeypatch.setattr(zonal, "PIXELS_MEDIANA_MAX", 10)
    g = ZONAS[2]
    with rasterio.open(raster) as ds, pytest.raises(zonal.ZonaGrande):
        zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("mediana",), fracao=False)


def test_leitura_e_por_faixa_e_nao_pelo_arquivo_inteiro(raster, monkeypatch):
    """Nenhuma leitura pede mais que FAIXA_LINHAS linhas: é a garantia de memória constante."""
    alturas = []
    original = rasterio.DatasetReader.read

    def espiao(self, *a, **kw):
        janela = kw.get("window")
        if janela is not None:
            alturas.append(int(janela.height))
        return original(self, *a, **kw)

    monkeypatch.setattr(rasterio.DatasetReader, "read", espiao)
    g = ZONAS[2]
    with rasterio.open(raster) as ds:
        zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("media",))
    assert alturas and max(alturas) <= zonal.FAIXA_LINHAS


def test_geometria_em_geojson_de_multipoligono(raster):
    """A zona pode ser MultiPolygon (é o que sai da camada do inquilino)."""
    g = {"type": "MultiPolygon", "coordinates": [quadrado(10, 10, 20, 20)["coordinates"],
                                                 quadrado(100, 100, 20, 20)["coordinates"]]}
    caixa = limites({"coordinates": [sum([anel[0] for anel in g["coordinates"]], [])]})
    with rasterio.open(raster) as ds:
        r = zonal.estatisticas_da_zona(ds, 1, json.loads(json.dumps(g)), caixa, ("contagem", "media"),
                                       fracao=False)
    assert r["contagem"] == 800
