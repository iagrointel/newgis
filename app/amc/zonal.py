"""Estatística zonal sobre raster com peso de ÁREA na borda da unidade (item L3-01-c-extracao-fator).

O que este módulo faz: dado o caminho de um raster legível pelo GDAL e uma lista de unidades de análise em EPSG:4326,
devolve, por unidade, o valor bruto pedido (média, mínimo, máximo, mediana, percentil, moda ou fração de classe) e a
cobertura — a fração da área da unidade que tem célula com dado válido.

Peso de área, não centróide. Uma célula que a unidade corta pela metade entra com peso 0,5. O cálculo é feito assim:

1. a unidade é reprojetada do EPSG:4326 para o CRS do raster (pyproj, sempre com eixo x = longitude);
2. `rasterio.features.rasterize` marca as células TOCADAS pela unidade (`all_touched=True`) e, num segundo passe, as
   células cortadas pela BORDA da unidade;
3. célula tocada e não cortada pela borda está inteiramente dentro: peso 1. Célula cortada pela borda recebe peso
   igual a área(interseção célula × unidade) / área(célula), calculada com shapely — o número exato, não a
   aproximação por centróide nem por superamostragem.

Célula sem dado (nodata ou NaN) entra no denominador da cobertura e sai do valor: a unidade que só tem célula sem
dado sai com valor NULL e cobertura 0, nunca com zero.

Definição do percentil ponderado (a mediana é o percentil 50): ordenados os valores válidos, o percentil p é o
primeiro valor cujo peso acumulado alcança p/100 da soma dos pesos. É a definição de percentil "inferior", a mesma
que a recomputação independente do teste usa.

Sem banco de dados: só rasterio, numpy, shapely e pyproj. O raster sem CRS declarado não é lido — levanta
`ErroExtracao('raster_sem_crs')`, e quem chama aborta o job (o portão do item: nunca produzir coluna de zeros)."""

import math

import numpy as np
import pyproj
import rasterio
from rasterio import features, windows
from shapely.geometry import box, shape
from shapely.ops import transform as _transformar_geom

TIPOS = (
    "raster_media", "raster_minimo", "raster_maximo", "raster_mediana", "raster_percentil", "raster_moda",
    "raster_fracao_classe",
)
CELULAS_MAX_POR_UNIDADE = 4_000_000  # ~16 MB em float32: unidade maior que isto é erro de escala, não trabalho


class ErroExtracao(Exception):
    """Falha que aborta a extração do fator inteiro (raster sem CRS, banda inexistente, arquivo ilegível)."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.detalhe = codigo, mensagem, detalhe or {}


def _transformador(crs_raster) -> pyproj.Transformer:
    return pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326), crs_raster, always_xy=True)


def _para_crs(geom, transformador):
    return _transformar_geom(lambda x, y, z=None: transformador.transform(x, y), geom)


def _janela(ds, limites_geom) -> windows.Window | None:
    """Janela inteira que cobre a unidade, recortada ao raster. None quando a unidade não toca o raster."""
    minx, miny, maxx, maxy = limites_geom
    j = windows.from_bounds(minx, miny, maxx, maxy, transform=ds.transform)
    j = windows.Window(math.floor(j.col_off), math.floor(j.row_off),
                       math.ceil(j.width) + 1, math.ceil(j.height) + 1)
    j = j.intersection(windows.Window(0, 0, ds.width, ds.height)) if _cruza(j, ds) else None
    return j


def _cruza(j: windows.Window, ds) -> bool:
    return not (j.col_off >= ds.width or j.row_off >= ds.height or j.col_off + j.width <= 0
                or j.row_off + j.height <= 0)


def pesos(geom, transform, altura: int, largura: int) -> np.ndarray:
    """Matriz (altura × largura) com a fração da área de cada célula coberta pela unidade. Célula inteiramente
    dentro = 1,0; célula cortada pela borda = fração exata calculada com shapely; fora = 0,0."""
    if altura <= 0 or largura <= 0:
        return np.zeros((max(altura, 0), max(largura, 0)), dtype="float64")
    # UMA só chamada a `rasterize` (não duas): "tocadas" (valor 1) e depois "borda" (valor 2, sobrepõe) no mesmo
    # array — a borda está sempre contida no conjunto de células tocadas, então o valor 2 identifica sem ambiguidade
    # as células que precisam da fração exata. Reduz a chamada mais cara (medida: ~0,53 ms de overhead de ambiente
    # GDAL por chamada) pela metade — necessário para o portão de tempo (12 fatores × 73 mil unidades).
    borda_geom = geom.boundary
    formas = [(geom, 1)] if borda_geom.is_empty else [(geom, 1), (borda_geom, 2)]
    marcado = features.rasterize(formas, out_shape=(altura, largura), transform=transform,
                                 all_touched=True, dtype="uint8")
    p = (marcado > 0).astype("float64")
    area_celula = abs(transform.a * transform.e - transform.b * transform.d)
    if area_celula <= 0:
        raise ErroExtracao("raster_sem_resolucao", "raster com célula de área zero (geotransform degenerado)")
    for i, j in zip(*np.nonzero(marcado == 2), strict=True):
        x0, y0 = transform * (j, i)
        x1, y1 = transform * (j + 1, i + 1)
        celula = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        inter = celula.intersection(geom)
        p[i, j] = 0.0 if inter.is_empty else min(1.0, inter.area / area_celula)
    return p


def _percentil_ponderado(valores: np.ndarray, ps: np.ndarray, percentil: float) -> float:
    ordem = np.argsort(valores, kind="stable")
    v, w = valores[ordem], ps[ordem]
    acumulado = np.cumsum(w)
    alvo = (percentil / 100.0) * acumulado[-1]
    return float(v[int(np.searchsorted(acumulado, alvo - 1e-12, side="left"))])


def estatistica(valores: np.ndarray, ps: np.ndarray, tipo: str, parametros: dict) -> float | None:
    """Valor bruto sobre as células VÁLIDAS já filtradas (valores e pesos do mesmo tamanho, pesos > 0)."""
    if valores.size == 0:
        return None
    if tipo == "raster_media":
        return float(np.sum(valores * ps) / np.sum(ps))
    if tipo == "raster_minimo":
        return float(np.min(valores))
    if tipo == "raster_maximo":
        return float(np.max(valores))
    if tipo == "raster_mediana":
        return _percentil_ponderado(valores, ps, 50.0)
    if tipo == "raster_percentil":
        return _percentil_ponderado(valores, ps, float(parametros["percentil"]))
    if tipo == "raster_moda":
        classes, inverso = np.unique(valores, return_inverse=True)
        acumulado = np.zeros(classes.size, dtype="float64")
        np.add.at(acumulado, inverso, ps)
        return float(classes[int(np.argmax(acumulado))])
    if tipo == "raster_fracao_classe":
        alvo = np.asarray(parametros["classes"], dtype="float64")
        dentro = np.isin(valores, alvo)
        return float(np.sum(ps[dentro]) / np.sum(ps))
    raise ErroExtracao("extrator_desconhecido", f"extrator de raster desconhecido: {tipo!r}")


def validar_parametros(tipo: str, parametros: dict) -> None:
    if tipo == "raster_percentil":
        p = parametros.get("percentil")
        if not isinstance(p, int | float) or isinstance(p, bool) or not (0.0 <= float(p) <= 100.0):
            raise ErroExtracao("parametro_invalido", "raster_percentil exige 'percentil' entre 0 e 100",
                               {"parametros": parametros})
    if tipo == "raster_fracao_classe":
        classes = parametros.get("classes")
        if not isinstance(classes, list) or not classes or not all(
                isinstance(c, int | float) and not isinstance(c, bool) for c in classes):
            raise ErroExtracao("parametro_invalido",
                               "raster_fracao_classe exige 'classes' com ao menos um valor numérico",
                               {"parametros": parametros})


def extrair(caminho: str, banda: int, unidades, tipo: str, parametros: dict | None = None) -> dict:
    """{unidade_id: {'valor': float|None, 'cobertura': float}} para as unidades dadas como (id, geometria GeoJSON em
    EPSG:4326). Abre o raster uma vez; lê só a janela de cada unidade."""
    parametros = parametros or {}
    validar_parametros(tipo, parametros)
    try:
        ds = rasterio.open(caminho)
    except Exception as e:  # rasterio levanta RasterioIOError e derivados de CPLE_*
        raise ErroExtracao("raster_ilegivel", f"não foi possível abrir o raster: {e}", {"caminho": caminho}) from e
    with ds:
        if ds.crs is None:
            raise ErroExtracao("raster_sem_crs", "o raster não declara CRS: sem isso a interseção com a unidade de "
                               "análise não tem significado e a extração é abortada", {"caminho": caminho})
        if banda < 1 or banda > ds.count:
            raise ErroExtracao("banda_inexistente", f"banda {banda} fora do raster (bandas: 1..{ds.count})",
                               {"caminho": caminho, "bandas": ds.count})
        transformador = _transformador(ds.crs)
        saida = {}
        for uid, geojson in unidades:
            saida[uid] = _uma_unidade(ds, banda, transformador, geojson, tipo, parametros)
        return saida


def _uma_unidade(ds, banda: int, transformador, geojson: dict, tipo: str, parametros: dict) -> dict:
    geom = _para_crs(shape(geojson), transformador)
    if geom.is_empty:
        return {"valor": None, "cobertura": 0.0}
    j = _janela(ds, geom.bounds)
    if j is None or j.width <= 0 or j.height <= 0:
        return {"valor": None, "cobertura": 0.0}
    if j.width * j.height > CELULAS_MAX_POR_UNIDADE:
        raise ErroExtracao("unidade_grande_demais",
                           f"a unidade cobre {int(j.width * j.height):,} células do raster, acima do teto de "
                           f"{CELULAS_MAX_POR_UNIDADE:,}", {"celulas": int(j.width * j.height)})
    transform = windows.transform(j, ds.transform)
    p = pesos(geom, transform, int(j.height), int(j.width))
    soma_pesos = float(p.sum())
    if soma_pesos <= 0:
        return {"valor": None, "cobertura": 0.0}
    dados = ds.read(banda, window=j, masked=True).astype("float64")
    valida = ~np.ma.getmaskarray(dados) & ~np.isnan(np.ma.filled(dados, np.nan))
    usar = valida & (p > 0)
    cobertura = float(p[usar].sum() / soma_pesos)
    valor = estatistica(np.ma.filled(dados, 0.0)[usar], p[usar], tipo, parametros)
    return {"valor": valor, "cobertura": cobertura}
