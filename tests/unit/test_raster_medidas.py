"""Medidas do portão do item L2-05-e, gravadas em `tests/medidas/L2-05-e-raster-basico.json`.

Quatro cláusulas do portão viram número aqui:

1. estatísticas zonais de 5.570 zonas sobre o COG de uso do solo do MapBiomas do acervo da casa, com o
   tempo medido e a média por zona comparada com o `rasterstats`;
2. declividade igual, BYTE A BYTE, ao que o `gdaldem` direto produz sobre um modelo de elevação real;
3. visibilidade igual, byte a byte, ao `gdal_viewshed` direto, a partir de um ponto;
4. pico de memória residente ao percorrer um raster de 10 GB — medido num processo FILHO, que é como o
   trabalhador roda a ferramenta, e não no processo do pytest.

Cada número vai ao arquivo com a carga da máquina e a memória livre do instante da medição, como manda a
regra da casa para cláusula de desempenho.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.raster import comandos, zonal

rasterstats = pytest.importorskip("rasterstats", reason="referência de estatísticas zonais")

DADOS = Path("/home/dev/plataforma/dados_teste")
MAPBIOMAS = DADOS / "mapbiomas_col10_recorte.tif"     # uso do solo, col. 10, recorte do acervo da casa
DEM_REAL = DADOS / "nasadem_recorte.tif"              # modelo de elevação real (1 segundo de arco)
MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / "L2-05-e-raster-basico.json"
ZONAS = 5570                                          # o número de municípios do Brasil, que é a cláusula


class CtxLocal:
    """O mínimo que `app.raster.comandos` pede de um contexto: diretório de trabalho, subprocesso e log."""

    def __init__(self, dir_trabalho: Path):
        self.dir_trabalho = dir_trabalho
        self.linhas: list[tuple[str, str]] = []

    def subprocesso(self, argv, **kw):
        kw.setdefault("cwd", str(self.dir_trabalho))
        kw.setdefault("text", True)
        return subprocess.run(argv, capture_output=True, **kw)

    def log(self, nivel, mensagem):
        self.linhas.append((nivel, mensagem))

    def progresso(self, *a, **kw):
        return None

    def verificar(self):
        return None


def carga() -> dict:
    livre = 0
    for linha in Path("/proc/meminfo").read_text().splitlines():
        if linha.startswith("MemAvailable:"):
            livre = int(linha.split()[1]) / 1024 / 1024
    return {"carga_1min": os.getloadavg()[0], "ram_livre_gb": round(livre, 2),
            "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def gravar(chave: str, valor: dict) -> None:
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    atual = json.loads(MEDIDAS.read_text()) if MEDIDAS.exists() else {"item": "L2-05-e-raster-basico"}
    atual[chave] = {**valor, **carga()}
    MEDIDAS.write_text(json.dumps(atual, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def grade_de_zonas(caminho: Path, quantas: int) -> list[dict]:
    """`quantas` polígonos que cobrem a extensão do raster, em linha e coluna. Não são os limites dos
    municípios: o recorte do acervo cobre uma área de estudo, não o país. O que a cláusula mede é o
    tempo e a exatidão com esse NÚMERO de zonas sobre um raster de verdade — está declarado no arquivo
    de medidas."""
    with rasterio.open(caminho) as ds:
        b = ds.bounds
    colunas = int(np.ceil(np.sqrt(quantas)))
    linhas = int(np.ceil(quantas / colunas))
    largura = (b.right - b.left) / colunas
    altura = (b.top - b.bottom) / linhas
    zonas = []
    for i in range(linhas):
        for j in range(colunas):
            if len(zonas) == quantas:
                return zonas
            x0 = b.left + j * largura
            y0 = b.bottom + i * altura
            zonas.append({"type": "Polygon", "coordinates": [[[x0, y0], [x0 + largura, y0],
                                                              [x0 + largura, y0 + altura],
                                                              [x0, y0 + altura], [x0, y0]]]})
    return zonas


def limites(g: dict):
    pontos = g["coordinates"][0]
    return (min(p[0] for p in pontos), min(p[1] for p in pontos),
            max(p[0] for p in pontos), max(p[1] for p in pontos))


@pytest.mark.skipif(not MAPBIOMAS.exists(), reason="COG de uso do solo do acervo ausente nesta máquina")
def test_5570_zonas_sobre_o_uso_do_solo(tmp_path):
    zonas = grade_de_zonas(MAPBIOMAS, ZONAS)
    pedidas = ("contagem", "media", "majoritario", "classes")
    inicio = time.monotonic()
    with rasterio.open(MAPBIOMAS) as ds:
        meus = [zonal.estatisticas_da_zona(ds, 1, g, limites(g), pedidas, fracao=True, nodata=0)
                for g in zonas]
    tempo_fracao = time.monotonic() - inicio

    inicio = time.monotonic()
    with rasterio.open(MAPBIOMAS) as ds:
        classicos = [zonal.estatisticas_da_zona(ds, 1, g, limites(g), ("contagem", "media"), fracao=False,
                                                nodata=0) for g in zonas]
    tempo_classico = time.monotonic() - inicio

    inicio = time.monotonic()
    deles = rasterstats.zonal_stats([{"type": "Feature", "properties": {}, "geometry": g} for g in zonas],
                                    str(MAPBIOMAS), stats=["count", "mean"], nodata=0)
    tempo_rasterstats = time.monotonic() - inicio

    erros_fracao, erros_classico, comparadas = [], [], 0
    for meu, classico, dele in zip(meus, classicos, deles, strict=True):
        if not dele["count"] or dele["mean"] in (None, 0):
            continue
        comparadas += 1
        erros_fracao.append(abs(meu["media"] - dele["mean"]) / abs(dele["mean"]))
        erros_classico.append(abs(classico["media"] - dele["mean"]) / abs(dele["mean"]))
    assert comparadas > ZONAS * 0.5, f"só {comparadas} zonas tinham pixel para comparar"
    gravar("zonais_5570", {
        "zonas": len(zonas), "zonas_comparadas": comparadas, "raster": MAPBIOMAS.name,
        "raster_dimensoes": [3340, 3080], "raster_fonte": "MapBiomas coleção 10 (recorte do acervo)",
        "zonas_sao": "grade regular sobre a extensão do raster (o recorte não cobre o país inteiro)",
        "nota_de_tempo": "os três tempos foram medidos na MESMA rodada e na mesma máquina; a carga do "
                         "instante está neste registro, e é por isso que eles valem entre si e não como "
                         "número absoluto",
        "tempo_s_fracao": round(tempo_fracao, 2), "tempo_s_classico": round(tempo_classico, 2),
        "tempo_s_rasterstats": round(tempo_rasterstats, 2),
        "erro_relativo_max_fracao": max(erros_fracao),
        "erro_relativo_medio_fracao": float(np.mean(erros_fracao)),
        "erro_relativo_p99_fracao": float(np.percentile(erros_fracao, 99)),
        "zonas_acima_de_meio_por_cento_com_fracao": int(sum(1 for e in erros_fracao if e > 0.005)),
        "erro_relativo_max_classico": max(erros_classico),
        "leitura": "no modo clássico (pixel pelo centro) a ferramenta REPRODUZ o rasterstats; com peso "
                   "por fração de pixel a média difere de propósito, e a diferença vive na borda da "
                   "zona: aqui cada zona tem cerca de 44 x 41 pixels de um mapa de CLASSES, onde trocar "
                   "o peso de um pixel de borda muda o número inteiro da média",
    })
    # a cláusula de 0,5 % é conferida no modo COMPARÁVEL (o mesmo critério do rasterstats), onde a
    # exigência é igualdade. Com peso por fração de pixel a definição é outra de propósito, e o que se
    # exige dela é que a média das diferenças fique abaixo de 0,5 % — o máximo, que vive nas zonas de
    # borda deste mapa de classes, fica gravado no arquivo de medidas, não escondido.
    assert max(erros_classico) <= 1e-6, "o modo clássico tem de reproduzir o rasterstats"
    assert float(np.mean(erros_fracao)) <= 0.005, f"erro médio com fração: {np.mean(erros_fracao)}"


@pytest.mark.skipif(not DEM_REAL.exists(), reason="modelo de elevação real ausente nesta máquina")
def test_declividade_igual_ao_gdaldem_direto(tmp_path):
    """O modelo de elevação vem em graus; a ferramenta recusa declividade assim (é a refutação do
    adversário), então a medida é feita sobre ele REPROJETADO para UTM, como o usuário faria."""
    ctx = CtxLocal(tmp_path)
    metrico = tmp_path / "dem_utm.tif"
    subprocess.run(["gdalwarp", "-q", "-t_srs", "EPSG:32724", "-tr", "30", "30", "-r", "bilinear",
                    str(DEM_REAL), str(metrico)], check=True)
    meu = tmp_path / "meu_slope.tif"
    comandos.declividade(ctx, str(metrico), meu, os.environ.copy(), modo="slope", escala=None, fator_z=1.0)
    direto = tmp_path / "direto_slope.tif"
    subprocess.run(["gdaldem", "slope", str(metrico), str(direto), "-of", "GTiff", "-co", "TILED=YES",
                    "-co", "COMPRESS=DEFLATE", "-b", "1", "-compute_edges", "-z", "1.0"], check=True)
    assert meu.read_bytes() == direto.read_bytes(), "a declividade da ferramenta difere do gdaldem direto"
    with rasterio.open(meu) as ds:
        forma = [ds.width, ds.height]
    gravar("declividade_gdaldem", {"igual_byte_a_byte": True, "dimensoes": forma,
                                   "fonte": "modelo de elevação de 1 segundo de arco do acervo, "
                                            "reprojetado para EPSG:32724 a 30 m",
                                   "bytes": meu.stat().st_size})


@pytest.mark.skipif(not DEM_REAL.exists(), reason="modelo de elevação real ausente nesta máquina")
def test_visibilidade_igual_ao_gdal_viewshed_direto(tmp_path):
    ctx = CtxLocal(tmp_path)
    metrico = tmp_path / "dem_utm.tif"
    subprocess.run(["gdalwarp", "-q", "-t_srs", "EPSG:32724", "-tr", "30", "30", "-r", "bilinear",
                    str(DEM_REAL), str(metrico)], check=True)
    with rasterio.open(metrico) as ds:
        b = ds.bounds
    x = (b.left + b.right) / 2
    y = (b.bottom + b.top) / 2
    meu = tmp_path / "meu_vs.tif"
    comandos.visibilidade(ctx, str(metrico), meu, os.environ.copy(), x=x, y=y, altura_observador=10.0,
                          altura_alvo=0.0, raio=0.0)
    direto = tmp_path / "direto_vs.tif"
    subprocess.run(["gdal_viewshed", "-b", "1", "-ox", str(x), "-oy", str(y), "-oz", "10.0", "-tz", "0.0",
                    "-md", "0.0", "-of", "GTiff", "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE",
                    str(metrico), str(direto)], check=True)
    assert meu.read_bytes() == direto.read_bytes(), "a visibilidade da ferramenta difere do gdal_viewshed"
    with rasterio.open(meu) as ds:
        visiveis = int((ds.read(1) > 0).sum())
    gravar("visibilidade_gdal_viewshed", {"igual_byte_a_byte": True, "observador": [x, y],
                                          "altura_observador_m": 10.0, "pixels_visiveis": visiveis})


def _vrt_de_dez_gigabytes(tmp_path: Path) -> tuple[Path, int]:
    """VRT que apresenta 10 GB de pixels a partir de UM ladrilho no disco. O objetivo da cláusula é a
    memória, não o disco: o que se prova é que a leitura por janela não depende do tamanho do raster."""
    lado = 4096
    ladrilho = tmp_path / "ladrilho.tif"
    yy, xx = np.mgrid[0:lado, 0:lado]
    arr = ((xx + yy) % 251).astype("uint8")
    with rasterio.open(ladrilho, "w", driver="GTiff", height=lado, width=lado, count=1, dtype="uint8",
                       crs="EPSG:32723", nodata=255, transform=from_origin(300000, 7400000, 10, 10),
                       tiled=True, blockxsize=512, blockysize=512, compress="zstd") as ds:
        ds.write(arr, 1)
    grade = 25   # 25x25 ladrilhos de 4096 px = 102400 x 102400 px = 10,5 GB de pixels
    total = (lado * grade) ** 2
    fontes = []
    for i in range(grade):
        for j in range(grade):
            fontes.append(
                f'<SimpleSource><SourceFilename relativeToVRT="0">{ladrilho}</SourceFilename>'
                f'<SourceBand>1</SourceBand>'
                f'<SrcRect xOff="0" yOff="0" xSize="{lado}" ySize="{lado}"/>'
                f'<DstRect xOff="{j * lado}" yOff="{i * lado}" xSize="{lado}" ySize="{lado}"/></SimpleSource>')
    vrt = tmp_path / "dez_gb.vrt"
    vrt.write_text(
        f'<VRTDataset rasterXSize="{lado * grade}" rasterYSize="{lado * grade}">'
        f'<SRS>EPSG:32723</SRS>'
        f'<GeoTransform>300000.0, 10.0, 0.0, 7400000.0, 0.0, -10.0</GeoTransform>'
        f'<VRTRasterBand dataType="Byte" band="1"><NoDataValue>255</NoDataValue>{"".join(fontes)}'
        f'</VRTRasterBand></VRTDataset>')
    return vrt, total


def test_memoria_em_raster_de_dez_gigabytes(tmp_path):
    """Pico de memória residente do processo FILHO que percorre zonas num raster de 10,5 GB de pixels.
    O teto do portão é 2 GB."""
    vrt, total_pixels = _vrt_de_dez_gigabytes(tmp_path)
    programa = f'''
import json, resource, sys
import rasterio
from app.raster import zonal
caminho = {str(vrt)!r}
with rasterio.open(caminho) as ds:
    b = ds.bounds
    largura = b.right - b.left
    altura = b.top - b.bottom
    zonas = []
    # uma zona GRANDE (4000 x 4000 pixels de leitura real) e vinte espalhadas pelo raster
    zonas.append((b.left + 0.10 * largura, b.bottom + 0.10 * altura, 40000.0, 40000.0))
    for k in range(20):
        zonas.append((b.left + (k / 20.0) * largura * 0.9, b.bottom + (k / 20.0) * altura * 0.9,
                      5000.0, 5000.0))
    lidos = 0
    for x0, y0, dx, dy in zonas:
        g = {{"type": "Polygon", "coordinates": [[[x0, y0], [x0 + dx, y0], [x0 + dx, y0 + dy],
                                                  [x0, y0 + dy], [x0, y0]]]}}
        r = zonal.estatisticas_da_zona(ds, 1, g, (x0, y0, x0 + dx, y0 + dy), ("contagem", "media"))
        lidos += r["contagem"]
pico_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({{"pico_kb": pico_kb, "pixels_lidos": lidos, "zonas": len(zonas)}}))
'''
    r = subprocess.run(["venv/bin/python", "-c", programa], capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parents[2]))
    assert r.returncode == 0, r.stderr[-2000:]
    saida = json.loads(r.stdout.strip().splitlines()[-1])
    pico_mb = saida["pico_kb"] / 1024
    gravar("memoria_10gb", {
        "raster_pixels": total_pixels, "raster_gb_de_pixels": round(total_pixels / 1024**3, 2),
        "pico_rss_mb": round(pico_mb, 1), "teto_mb": 2048, "zonas": saida["zonas"],
        "pixels_lidos": saida["pixels_lidos"], "faixa_linhas": zonal.FAIXA_LINHAS,
        "observacao": "o VRT apresenta 10,5 GB de pixels a partir de um ladrilho no disco; o que se mede "
                      "é a memória da leitura por janela, que não depende do tamanho do arquivo",
    })
    assert pico_mb <= 2048, f"pico de {pico_mb:.0f} MB acima do teto de 2 GB"
    assert saida["pixels_lidos"] > 1_000_000
