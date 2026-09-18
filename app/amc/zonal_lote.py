"""Estatística zonal em LOTE (item L3-16-desempenho-escala): a mesma conta de `app.amc.zonal`, mas para grades
REGULARES (quadrada/hexagonal, `app.amc.unidades.gerar_grade`) em vez de polígono arbitrário — o caso do motor AMC
em escala (1 milhão de células).

Por que este módulo existe: `app.amc.zonal.extrair` abre uma janela e chama `rasterio.features.rasterize` UMA VEZ
POR UNIDADE (ver `pesos()`). Medido no item L3-01-c-extracao-fator (`tests/unit/test_amc_zonal.py`,
`tests/medidas/L3-01-c-extracao-fator.json`): ~0,62 ms/unidade nesta máquina, o que projeta ~9 min só para 12
fatores em 73 mil unidades — muito acima do orçamento de 30 min para 1 milhão de unidades × 15 fatores (a conta
projetada seria ~2,6 h). O caminho registrado como pendência naquele item (ADR 0017) é este: rasterizar a grade
INTEIRA de uma vez (uma única chamada a `rasterize`, O(pixels), não O(unidades)) e agregar por rótulo com
`numpy.bincount` — O(pixels) uma vez, não O(unidades) chamadas.

Diferença DECLARADA e deliberada em relação a `app.amc.zonal` (decisão deste item, não um bug):

- `zonal.py` pesa a borda por FRAÇÃO DE ÁREA exata (shapely) — o padrão para poucas unidades/polígono arbitrário;
- este módulo classifica cada pixel pelo CENTRO dele (a célula da grade cujo interior contém o centro do pixel
  vence o pixel inteiro) — a regra "por blocos" que faz o cálculo custar O(pixels), não O(unidades × borda). Para
  uma grade cujo lado é grande frente ao pixel (o caso de uso do item: 1 mi de células sobre uma área de estudo),
  o viés de borda introduzido é pequeno, da mesma ordem do próprio pixel do raster; ver
  `tests/unit/test_amc_zonal_lote.py::test_bate_com_zonal_dentro_da_tolerancia_declarada` para o número medido.
  Isso é a troca honesta: caminho RÁPIDO e aproximado para escala, caminho EXATO e mais lento para poucas unidades
  (a grade pequena/interativa continua usando `zonal.py`).
- só os extratores que fazem sentido como uma soma/média por rótulo em uma única passada: `raster_media`,
  `raster_minimo`, `raster_maximo`, `raster_contagem_valida` (fração de pixels válidos = cobertura). Mediana,
  percentil, moda e fração de classe exigiriam ordenar/contar por rótulo — mais caro e fora do escopo medido deste
  item (ficam only em `zonal.py`, para N pequeno); pedir um desses aqui é `ErroExtracao('extrator_nao_suportado')`.
- processamento POR BLOCOS de linhas do raster (`ALTURA_BLOCO_PADRAO` linhas por vez): a grade inteira nunca
  precisa caber em memória de uma vez, só o bloco de pixels e o bloco de rótulos correspondente — é isto que
  mantém o guardrail de RAM ≤ 4 GB independente do tamanho da área de estudo. Cada unidade entra SÓ nos blocos
  que ela toca (intervalo de linha pré-calculado uma vez, `_blocos_por_unidade`) — sem isso, `rasterize()`
  receberia a lista INTEIRA de 1 milhão de formas a cada bloco, e foi exatamente isso que consumiu ~94 % do
  tempo medido antes desta correção (achado ao medir a escala real: 100 mil unidades em 1 bloco já levavam
  ~9,4 s por fator; o item L3-16 exige que blocos MÚLTIPLOS não paguem esse custo outra vez por bloco).

Sem banco de dados: só rasterio, numpy e shapely/pyproj (as mesmas de `zonal.py`, sem dependência nova). Mesma regra
de `zonal.py`: raster sem CRS aborta a extração inteira
(nunca produz coluna de zeros)."""

from __future__ import annotations

import numpy as np
import pyproj
import rasterio
from rasterio import features, windows
from shapely.geometry import shape
from shapely.ops import transform as _transformar_geom

from app.amc.zonal import ErroExtracao

TIPOS = ("raster_media", "raster_minimo", "raster_maximo", "raster_contagem_valida")
ALTURA_BLOCO_PADRAO = 2048  # linhas de raster por bloco; ~2048*largura*4 bytes cabe folgado no guardrail de 4 GB


def _transformador(crs_raster) -> pyproj.Transformer:
    return pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326), crs_raster, always_xy=True)


def _para_crs(geom, transformador):
    return _transformar_geom(lambda x, y, z=None: transformador.transform(x, y), geom)


class GradePreparada:
    """Grade reprojetada e pré-rotulada UMA VEZ, reaproveitada por vários fatores/rasters do MESMO CRS de
    trabalho. Medido no item L3-16-desempenho-escala: reprojetar 100 mil polígonos (`shapely.ops.transform`
    ponto a ponto) custa ~5 s — pagar isso a cada fator (o que `extrair_em_lote` faz sozinho, por comodidade
    de API igual a `app.amc.zonal.extrair`) multiplicaria por 15 o custo de um modelo com 15 fatores raster,
    a maior parte do tempo gasta em algo que não muda entre fatores. `preparar_grade` faz a reprojeção e o
    envelope uma vez; `extrair_em_lote_preparado` reaproveita para cada `(caminho, banda, tipo)`."""

    __slots__ = ("ids", "formas", "envelope")

    def __init__(self, ids: list[str], formas: list, envelope: tuple[float, float, float, float]):
        self.ids = ids
        self.formas = formas
        self.envelope = envelope


def preparar_grade(unidades: list[tuple[str, dict]], crs_trabalho) -> GradePreparada:
    """Reprojeta `unidades` (GeoJSON 4326) para `crs_trabalho` (o CRS do raster) uma única vez."""
    ids = [u for u, _ in unidades]
    if len(set(ids)) != len(ids):
        raise ErroExtracao("unidade_id_duplicado", "unidade_id repetido na grade")
    transformador = _transformador(crs_trabalho)
    geoms_crs = [_para_crs(shape(g), transformador) for _u, g in unidades]
    formas = [(g, i + 1) for i, g in enumerate(geoms_crs) if not g.is_empty]
    envelope = _envelope(geoms_crs) if formas else None
    return GradePreparada(ids, formas, envelope)


def extrair_em_lote(
    caminho: str, banda: int, unidades: list[tuple[str, dict]], tipo: str,
    altura_bloco: int = ALTURA_BLOCO_PADRAO,
) -> dict:
    """`unidades`: [(unidade_id, geojson 4326)] de uma grade REGULAR (células não sobrepostas — o resultado não
    tem sentido definido para unidades sobrepostas, porque o pixel só pode pertencer a UM rótulo). Devolve
    {unidade_id: {'valor': float|None, 'cobertura': float}}, na mesma forma de `app.amc.zonal.extrair`.

    Reprojeta a grade a cada chamada (conveniência de API, igual a `app.amc.zonal.extrair`). Quem extrai VÁRIOS
    fatores raster para a MESMA grade deve usar `preparar_grade` + `extrair_em_lote_preparado` uma vez só — ver
    o ganho medido na classe `GradePreparada`."""
    if tipo not in TIPOS:
        raise ErroExtracao("extrator_nao_suportado",
                           f"{tipo!r} não tem caminho em lote; extratores em lote: {sorted(TIPOS)} "
                           f"(mediana/percentil/moda/fração de classe continuam só em app.amc.zonal, para N pequeno)")
    if not unidades:
        return {}
    try:
        ds = rasterio.open(caminho)
    except Exception as e:
        raise ErroExtracao("raster_ilegivel", f"não foi possível abrir o raster: {e}", {"caminho": caminho}) from e
    with ds:
        if ds.crs is None:
            raise ErroExtracao("raster_sem_crs", "o raster não declara CRS", {"caminho": caminho})
        grade = preparar_grade(unidades, ds.crs)
        return _extrair_com_grade_preparada(ds, banda, grade, tipo, altura_bloco)


def extrair_em_lote_preparado(
    caminho: str, banda: int, grade: GradePreparada, tipo: str, altura_bloco: int = ALTURA_BLOCO_PADRAO,
) -> dict:
    """Mesma extração de `extrair_em_lote`, mas recebendo uma `GradePreparada` (`preparar_grade`) já reprojetada
    — o caminho rápido para N fatores sobre a MESMA grade. `grade` foi preparada para o CRS do raster de
    `caminho`; usar com um raster de outro CRS dá resultado sem sentido (não há checagem aqui: quem prepara a
    grade sabe o CRS que passou)."""
    if tipo not in TIPOS:
        raise ErroExtracao("extrator_nao_suportado",
                           f"{tipo!r} não tem caminho em lote; extratores em lote: {sorted(TIPOS)} "
                           f"(mediana/percentil/moda/fração de classe continuam só em app.amc.zonal, para N pequeno)")
    if not grade.ids:
        return {}
    try:
        ds = rasterio.open(caminho)
    except Exception as e:
        raise ErroExtracao("raster_ilegivel", f"não foi possível abrir o raster: {e}", {"caminho": caminho}) from e
    with ds:
        if ds.crs is None:
            raise ErroExtracao("raster_sem_crs", "o raster não declara CRS", {"caminho": caminho})
        return _extrair_com_grade_preparada(ds, banda, grade, tipo, altura_bloco)


def _extrair_com_grade_preparada(ds, banda: int, grade: GradePreparada, tipo: str, altura_bloco: int) -> dict:
    if banda < 1 or banda > ds.count:
        raise ErroExtracao("banda_inexistente", f"banda {banda} fora do raster (bandas: 1..{ds.count})")
    ids, formas = grade.ids, grade.formas
    if not formas:
        return {u: {"valor": None, "cobertura": 0.0} for u in ids}
    minx, miny, maxx, maxy = grade.envelope
    janela = windows.from_bounds(minx, miny, maxx, maxy, transform=ds.transform)
    col_off = max(0, int(janela.col_off))
    row_off = max(0, int(janela.row_off))
    largura = max(0, min(ds.width - col_off, int(janela.width) + 2))
    altura = max(0, min(ds.height - row_off, int(janela.height) + 2))
    if largura <= 0 or altura <= 0 or col_off >= ds.width or row_off >= ds.height:
        return {u: {"valor": None, "cobertura": 0.0} for u in ids}
    janela = windows.Window(col_off, row_off, largura, altura)
    transform_janela = windows.transform(janela, ds.transform)
    formas_por_bloco = _blocos_por_unidade(formas, transform_janela, int(janela.height), altura_bloco)
    n = len(ids)
    soma = np.zeros(n + 1, dtype="float64")
    conta = np.zeros(n + 1, dtype="int64")
    minimo = np.full(n + 1, np.inf, dtype="float64")
    maximo = np.full(n + 1, -np.inf, dtype="float64")
    total_pixels = np.zeros(n + 1, dtype="int64")
    for topo in range(0, int(janela.height), altura_bloco):
        formas_bloco = formas_por_bloco.get(topo // altura_bloco)
        if not formas_bloco:
            continue  # nenhuma unidade toca este bloco: nem lê o raster nem rasteriza
        h = min(altura_bloco, int(janela.height) - topo)
        bloco = windows.Window(janela.col_off, janela.row_off + topo, janela.width, h)
        transform_bloco = windows.transform(bloco, ds.transform)
        rotulos = features.rasterize(
            formas_bloco, out_shape=(h, int(janela.width)), transform=transform_bloco,
            all_touched=False, dtype="int32", fill=0,
        )
        if not np.any(rotulos):
            continue
        dados = ds.read(banda, window=bloco, masked=True).astype("float64")
        valido = ~np.ma.getmaskarray(dados) & ~np.isnan(np.ma.filled(dados, np.nan)) & (rotulos > 0)
        total_pixels += np.bincount(rotulos[rotulos > 0], minlength=n + 1)
        if not np.any(valido):
            continue
        r = rotulos[valido]
        v = np.ma.filled(dados, 0.0)[valido]
        soma += np.bincount(r, weights=v, minlength=n + 1)
        conta += np.bincount(r, minlength=n + 1)
        if tipo in ("raster_minimo", "raster_maximo"):
            for rot in np.unique(r):
                vs = v[r == rot]
                if vs.min() < minimo[rot]:
                    minimo[rot] = vs.min()
                if vs.max() > maximo[rot]:
                    maximo[rot] = vs.max()
    saida = {}
    for i, uid in enumerate(ids):
        rot = i + 1
        n_validos = int(conta[rot])
        total = int(total_pixels[rot])
        cobertura = (n_validos / total) if total > 0 else 0.0
        if n_validos == 0:
            saida[uid] = {"valor": None, "cobertura": cobertura}
            continue
        if tipo == "raster_media":
            valor = float(soma[rot] / n_validos)
        elif tipo == "raster_minimo":
            valor = float(minimo[rot])
        elif tipo == "raster_maximo":
            valor = float(maximo[rot])
        else:  # raster_contagem_valida
            valor = float(n_validos)
        saida[uid] = {"valor": valor, "cobertura": cobertura}
    return saida


def _blocos_por_unidade(formas, transform_janela, altura_janela: int, altura_bloco: int) -> dict[int, list]:
    """{índice_do_bloco: [(geom, rótulo), ...]} — cada forma só entra nos blocos cujo intervalo de linha ela
    realmente toca (quase sempre 1 bloco só, já que a célula da grade é pequena frente a `altura_bloco`; o
    caso raro de uma unidade cortando a fronteira de dois blocos entra nos dois, o que conta o pixel na
    fronteira duas vezes no MÁXIMO — mesma ordem de grandeza do viés de borda já declarado no módulo)."""
    inv = ~transform_janela
    buckets: dict[int, list] = {}
    for g, rotulo in formas:
        minx, miny, maxx, maxy = g.bounds
        linhas = [inv * (x, y) for x, y in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy))]
        linha_min = max(0, int(min(r for _c, r in linhas)))
        linha_max = min(altura_janela - 1, int(max(r for _c, r in linhas)))
        if linha_max < 0 or linha_min > altura_janela - 1:
            continue  # forma fora da janela (não deveria acontecer: já entrou no envelope; defesa mesmo assim)
        for bidx in range(linha_min // altura_bloco, linha_max // altura_bloco + 1):
            buckets.setdefault(bidx, []).append((g, rotulo))
    return buckets


def _envelope(geoms) -> tuple[float, float, float, float]:
    xs = [g.bounds[0] for g in geoms if not g.is_empty] + [g.bounds[2] for g in geoms if not g.is_empty]
    ys = [g.bounds[1] for g in geoms if not g.is_empty] + [g.bounds[3] for g in geoms if not g.is_empty]
    if not xs:
        raise ErroExtracao("grade_vazia", "nenhuma unidade com geometria não vazia")
    return min(xs), min(ys), max(xs), max(ys)
