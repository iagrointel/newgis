"""Grades, densidade, padrões espaciais e interpolação (item L2-05-d), no MESMO registro `@ferramenta` do
L2-05-a e executadas pelo MESMO executor: tesselação (quadrada, hexagonal e H3), densidade de kernel de pontos
e de linhas, hot spot Getis-Ord Gi*, centro médio / distância padrão / elipse de desvio padrão, vizinho mais
próximo médio, I de Moran global, interpolação por inverso da distância (IDW) e isolinhas.

Divisão de trabalho, para não haver duas implementações da mesma conta:

* o que é DESENHO de grade regular é PostGIS (`ST_SquareGrid`/`ST_HexagonGrid`), o mesmo caminho que
  `agregar_pontos` do L2-05-c já usa, sempre em UTM local (`relacao.utm_da_camada`);
* o que é ESTATÍSTICA é `app/ferramentas/estatistica_espacial.py` (numpy/scipy, sem banco), conferido no teste
  do item contra `esda`/`libpysal` e contra fórmula fechada;
* o que é ISOLINHA é GDAL (`gdal.ContourGenerateEx`), sobre a superfície interpolada em memória.

Saída raster: as superfícies de densidade e de IDW saem aqui como CAMADA DE CÉLULAS (um polígono por célula com
o valor no centro), que é o que o executor do L2-05-a sabe publicar e o que o Map Viewer da Esri também devolve
em "Calculate Density". A mesma conta em array (`estatistica_espacial.densidade_kernel` / `.idw`) é o que vai
virar GeoTIFF COG quando o caminho de ingestão de raster do item L1-01 estiver em master: quando isso acontecer,
o COG entra por LÁ, e não por um segundo mecanismo criado aqui (ADR do item).

Unidade da tesselação: `tamanho` é a distância entre lados opostos da célula — lado do quadrado, e distância
entre lados paralelos do hexágono (a "grade de 250 m" da casa é o hexágono de 250 m entre lados, área
54.126,588 m², aresta 250/raiz(3) = 144,3376 m).
"""

from __future__ import annotations

import math

import numpy as np
import psycopg2.extras
from shapely import wkb as swkb
from shapely.geometry import LineString, MultiLineString, Point, Polygon

from app import limites
from app.ferramentas import estatistica_espacial as ee
from app.ferramentas.registro import Parametro, ferramenta
from app.ferramentas.relacao import (
    ErroFerramenta,
    familia,
    ident,
    no_srid_de,
    tabela_de,
    tipos_de,
    utm_da_camada,
    verificar_tamanho,
)
from app.ferramentas.vetor import NUMERICAS, escrever

TIPOS_GRADE = ("quadrada", "hexagonal", "h3")
FORMAS_CENTRO = ("centro", "circulo_distancia_padrao", "elipse")
METODOS_SUPERFICIE = ("idw", "tin")
# faixas do Gi* no vocabulário do ArcGIS (Gi_Bin): 3 = 99 %, 2 = 95 %, 1 = 90 % de confiança
FAIXAS_GI = ((2.576, 3), (1.960, 2), (1.645, 1))


# ---------------------------------------------------------------- apoio comum
def escrever_linhas(ctx, destino: dict, colunas: list[tuple[str, str]], linhas: list[tuple],
                    tipo_geom: str, srid_origem: int, srid_saida: int) -> list[dict]:
    """Cria a tabela de destino com colunas declaradas e insere as linhas já calculadas (a geometria vem como
    WKB em hexadecimal no último campo de cada tupla, no SRID métrico em que a conta foi feita) e, num único
    comando, reprojeta a coluna inteira para o SRID de saída. É o par de `vetor.escrever`, para o caso em que o
    resultado nasce em numpy e não em SQL."""
    alvo = tabela_de(destino)
    nomes = ", ".join(ident(n) for n, _ in colunas)
    tipos = ", ".join(f"{ident(n)} {t}" for n, t in colunas)
    modelo = ("(" + ", ".join(["%s"] * len(colunas))
              + f", ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), {int(srid_origem)}))")
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} (fid bigserial PRIMARY KEY, {tipos}, "
                    f"geom geometry({tipo_geom}, {int(srid_origem)}))")
        if linhas:
            psycopg2.extras.execute_values(cur, f"INSERT INTO {alvo} ({nomes}, geom) VALUES %s", linhas,
                                           template=modelo, page_size=500)
        if int(srid_saida) != int(srid_origem):
            cur.execute(f"ALTER TABLE {alvo} ALTER COLUMN geom TYPE geometry({tipo_geom}, {int(srid_saida)}) "
                        f"USING ST_Transform(geom, {int(srid_saida)})")
        campos = [{"nome": n, "tipo": t, "alias": n} for n, t in colunas]
    return campos


def coordenadas(ctx, camada: dict, srid_metrico: int, campo: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(xy em metros no SRID métrico dado, valores do campo). Ponto usa a própria geometria; linha e polígono
    usam o centro de massa — é o que as estatísticas de padrão de ponto medem."""
    coluna = f"ST_Transform(ST_Centroid(geom), {int(srid_metrico)})"
    seleto = f", {ident(campo)}::double precision AS v" if campo else ", 1.0::double precision AS v"
    with ctx.db() as cur:
        cur.execute(f"SELECT ST_X({coluna}) AS x, ST_Y({coluna}) AS y{seleto} FROM {tabela_de(camada)} "
                    f"WHERE geom IS NOT NULL ORDER BY fid")
        linhas = cur.fetchall()
    if not linhas:
        raise ErroFerramenta("camada_vazia", f"camada {camada['titulo']!r} sem feições com geometria")
    xy = np.array([[float(r["x"]), float(r["y"])] for r in linhas], dtype=float)
    valores = np.array([float(r["v"]) if r["v"] is not None else np.nan for r in linhas], dtype=float)
    if campo and not np.isfinite(valores).all():
        raise ErroFerramenta("campo_com_nulo",
                             f"campo: {campo!r} tem valor nulo em {int((~np.isfinite(valores)).sum())} feição(ões)")
    return xy, valores


def campo_numerico(ctx, camada: dict, campo: str) -> str:
    tipos = None
    with ctx.db() as cur:
        tipos = tipos_de(cur, camada["schema"], camada["tabela"])
    if campo not in tipos:
        raise ErroFerramenta("campo_inexistente", f"campo: {campo!r} não existe em {camada['titulo']!r}")
    if tipos[campo] not in NUMERICAS:
        raise ErroFerramenta("campo_nao_numerico", f"campo: {campo!r} é {tipos[campo]}, esperado numérico")
    return campo


def limitar_feicoes(camada: dict, teto: int) -> None:
    if camada["feicoes"] > teto:
        raise ErroFerramenta("camada_grande_demais",
                             f"{camada['titulo']!r}: {camada['feicoes']} feições acima do limite de {teto} "
                             f"desta ferramenta", {"feicoes": camada["feicoes"], "maximo": teto})


def metros(parametros: dict, nome: str, padrao: float) -> float:
    v = parametros.get(nome) or {}
    return float(v.get("metros") or padrao)


def wkb(geometria) -> str:
    return geometria.wkb_hex


def extensao(ctx, camada: dict, utm: int) -> tuple[float, float, float, float]:
    with ctx.db() as cur:
        cur.execute(f"SELECT ST_XMin(e) AS x0, ST_YMin(e) AS y0, ST_XMax(e) AS x1, ST_YMax(e) AS y1 FROM "
                    f"(SELECT ST_Transform(ST_SetSRID(ST_Extent(geom)::geometry, {int(camada['srid'])}), {utm}) "
                    f"AS e FROM {tabela_de(camada)}) t")
        r = cur.fetchone()
    if r is None or r["x0"] is None:
        raise ErroFerramenta("camada_vazia", f"camada {camada['titulo']!r} sem extensão")
    return float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"])


def grade_de(x0: float, y0: float, x1: float, y1: float, celula: float, folga: float = 0.0) -> tuple:
    """Centros de célula que cobrem a extensão dilatada por `folga`; devolve (gx, gy, x_min, y_min)."""
    x0, y0, x1, y1 = x0 - folga, y0 - folga, x1 + folga, y1 + folga
    nx = max(1, int(math.ceil((x1 - x0) / celula)))
    ny = max(1, int(math.ceil((y1 - y0) / celula)))
    if nx * ny > limites.GRADE_CELULAS_MAX:
        raise ErroFerramenta("grade_grande_demais",
                             f"tamanho_celula: a grade teria {nx * ny} células, acima do limite de "
                             f"{limites.GRADE_CELULAS_MAX}; aumente o tamanho da célula",
                             {"campo": "tamanho_celula", "celulas": nx * ny,
                              "maximo": limites.GRADE_CELULAS_MAX})
    gx = x0 + (np.arange(nx) + 0.5) * celula
    gy = y0 + (np.arange(ny) + 0.5) * celula
    return gx, gy, x0, y0


# ---------------------------------------------------------------- tesselação
@ferramenta(
    nome="tesselacao", titulo="Tesselação (grade)", categoria="gestao", versao=1,
    descricao="Cobre a área de uma camada com células regulares: quadrado, hexágono (tamanho medido entre lados "
              "opostos, em metros, desenhado no UTM local) ou célula H3 do nível pedido. Opcionalmente recorta as "
              "células pela área.",
    parametros=(
        Parametro("camada_area", "GPFeatureRecordSetLayer", "camada que define a área"),
        Parametro("tipo", "GPString", "tipo de célula", obrigatorio=False, padrao="hexagonal",
                  opcoes=TIPOS_GRADE),
        Parametro("tamanho", "GPLinearUnit", "tamanho da célula", obrigatorio=False,
                  padrao={"distance": 1, "units": "esriKilometers"}, minimo=1,
                  descricao="lado do quadrado ou distância entre lados opostos do hexágono; ignorado no H3"),
        Parametro("nivel_h3", "GPLong", "nível H3", obrigatorio=False, padrao=8,
                  minimo=limites.H3_NIVEL_MIN, maximo=limites.H3_NIVEL_MAX),
        Parametro("recortar", "GPBoolean", "recortar pela área", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada_area"]["feicoes"] * 5,
    limites={"celulas_max": limites.GRADE_CELULAS_MAX, "h3_nivel": (limites.H3_NIVEL_MIN, limites.H3_NIVEL_MAX)},
)
def tesselacao(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    area = entradas["camada_area"]
    if familia(area)[2] != 2:
        raise ErroFerramenta("camada_nao_poligonal", "camada_area precisa ser de polígonos")
    tipo = parametros.get("tipo") or "hexagonal"
    recortar = parametros.get("recortar", True) is not False
    srid = area["srid"]
    utm = utm_da_camada(ctx, area)
    if tipo == "h3":
        return _tesselacao_h3(ctx, area, int(parametros.get("nivel_h3") or 8), recortar, destino)
    lado = metros(parametros, "tamanho", 1000.0)
    # ST_HexagonGrid recebe a ARESTA; o parâmetro da ferramenta é a distância entre lados opostos
    passo = lado if tipo == "quadrada" else lado / math.sqrt(3.0)
    x0, y0, x1, y1 = extensao(ctx, area, utm)
    celulas = math.ceil((x1 - x0) / lado + 1) * math.ceil((y1 - y0) / lado + 1)
    if celulas > limites.GRADE_CELULAS_MAX:
        raise ErroFerramenta("grade_grande_demais",
                             f"tamanho: a grade teria cerca de {celulas} células, acima do limite de "
                             f"{limites.GRADE_CELULAS_MAX}; aumente o tamanho da célula",
                             {"campo": "tamanho", "celulas": celulas, "maximo": limites.GRADE_CELULAS_MAX})
    funcao = "ST_SquareGrid" if tipo == "quadrada" else "ST_HexagonGrid"
    ctx.progresso(20, f"desenhando a grade {tipo} de {lado} m em EPSG:{utm}")
    geom = ("ST_Multi(ST_Intersection(g.geom, a.g))" if recortar else "ST_Multi(g.geom)")
    select = (
        f"WITH a AS (SELECT ST_Union(ST_MakeValid(ST_Transform(geom, {utm}))) AS g FROM {tabela_de(area)}), "
        f"e AS (SELECT ST_SetSRID(ST_Extent(g)::geometry, {utm}) AS ext FROM a), "
        f"g AS (SELECT (c).i AS coluna, (c).j AS linha, (c).geom AS geom FROM e, "
        f"LATERAL {funcao}({passo!r}, e.ext) AS c) "
        f"SELECT g.coluna, g.linha, ST_Area({geom}) AS area_m2, "
        f"ST_Transform({geom}, {int(srid)}) AS geom "
        f"FROM g JOIN a ON ST_Intersects(g.geom, a.g) ORDER BY g.coluna, g.linha"
    )
    campos = escrever(ctx, destino, select, "MultiPolygon", srid)
    return {"geometria": "MultiPolygon", "srid": srid, "campos": campos,
            "metodo": (f"{funcao} com {lado} m entre lados opostos (aresta {passo:.4f} m) desenhada em "
                       f"EPSG:{utm} sobre a união da área"
                       + ("; células recortadas pela área" if recortar else "; células inteiras")
                       + f" e trazidas de volta para EPSG:{srid}")}


def _tesselacao_h3(ctx, area: dict, nivel: int, recortar: bool, destino: dict) -> dict:
    """Células H3 do nível pedido que cobrem a área. A biblioteca h3 trabalha em graus (WGS 84), então a área
    vai a 4326 e volta; `recortar` corta a célula pela área com PostGIS depois de inserida."""
    import h3

    if not limites.H3_NIVEL_MIN <= nivel <= limites.H3_NIVEL_MAX:
        raise ErroFerramenta("nivel_h3_invalido",
                             f"nivel_h3: fora da faixa {limites.H3_NIVEL_MIN}-{limites.H3_NIVEL_MAX}")
    srid = area["srid"]
    with ctx.db() as cur:
        cur.execute(f"SELECT ST_AsBinary(ST_Transform(ST_Union(ST_MakeValid(geom)), 4326)) AS g "
                    f"FROM {tabela_de(area)}")
        bruto = cur.fetchone()["g"]
    forma = swkb.loads(bytes(bruto))
    celulas = sorted(h3.geo_to_cells(forma.__geo_interface__, nivel))
    if not celulas:
        raise ErroFerramenta("h3_sem_celula",
                             f"nivel_h3: nenhuma célula de nível {nivel} tem centro dentro da área; use um "
                             f"nível mais fino", {"campo": "nivel_h3"})
    if len(celulas) > limites.GRADE_CELULAS_MAX:
        raise ErroFerramenta("grade_grande_demais",
                             f"nivel_h3: {len(celulas)} células acima do limite de {limites.GRADE_CELULAS_MAX}",
                             {"campo": "nivel_h3", "celulas": len(celulas),
                              "maximo": limites.GRADE_CELULAS_MAX})
    ctx.progresso(30, f"{len(celulas)} células H3 de nível {nivel}")
    linhas = []
    for celula in celulas:
        borda = h3.cell_to_boundary(celula)
        anel = [(lng, lat) for lat, lng in borda]
        anel.append(anel[0])
        linhas.append((celula, nivel, float(h3.cell_area(celula, unit="m^2")),
                       wkb(Polygon(anel).buffer(0))))
    campos = escrever_linhas(ctx, destino, [("h3", "text"), ("nivel", "integer"), ("area_m2", "double precision")],
                             linhas, "Polygon", 4326, srid)
    if recortar:
        with ctx.db() as cur:
            cur.execute(f"WITH a AS (SELECT ST_Union(ST_MakeValid(ST_Transform(geom, {int(srid)}))) AS g "
                        f"FROM {tabela_de(area)}) "
                        f"UPDATE {tabela_de(destino)} d SET geom = ST_CollectionExtract("
                        f"ST_Intersection(d.geom, a.g), 3) FROM a")
            cur.execute(f"DELETE FROM {tabela_de(destino)} WHERE geom IS NULL OR ST_IsEmpty(geom)")
            cur.execute(f"ALTER TABLE {tabela_de(destino)} ALTER COLUMN geom TYPE geometry(MultiPolygon, "
                        f"{int(srid)}) USING ST_Multi(geom)")
        return {"geometria": "MultiPolygon", "srid": srid, "campos": campos,
                "metodo": (f"h3.geo_to_cells nível {nivel} sobre a área em WGS 84, células recortadas pela área "
                           f"em EPSG:{srid}; area_m2 é a área da célula INTEIRA (h3.cell_area)")}
    return {"geometria": "Polygon", "srid": srid, "campos": campos,
            "metodo": f"h3.geo_to_cells nível {nivel} sobre a área em WGS 84, células inteiras"}


# ---------------------------------------------------------------- densidade de kernel
@ferramenta(
    nome="densidade_kernel", titulo="Densidade de kernel", categoria="resumo", versao=1,
    descricao="Densidade de pontos ou de linhas por unidade de área, em células quadradas: cada feição espalha "
              "massa até o raio segundo a função escolhida. A soma do valor das células vezes a área da célula "
              "devolve o número de pontos (ou o comprimento total das linhas).",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de pontos ou de linhas"),
        Parametro("campo_peso", "GPString", "campo de peso", obrigatorio=False,
                  descricao="campo numérico; sem ele cada ponto pesa 1 e cada linha pesa o próprio comprimento"),
        Parametro("raio", "GPLinearUnit", "raio de busca", obrigatorio=False,
                  padrao={"distance": 1, "units": "esriKilometers"}, minimo=1,
                  maximo=limites.DENSIDADE_RAIO_M_MAX),
        Parametro("funcao", "GPString", "função de kernel", obrigatorio=False, padrao="quartica",
                  opcoes=ee.FUNCOES_KERNEL),
        Parametro("tamanho_celula", "GPLinearUnit", "tamanho da célula", obrigatorio=False,
                  padrao={"distance": 100, "units": "esriMeters"}, minimo=1),
        Parametro("manter_zeros", "GPBoolean", "manter células de valor zero", obrigatorio=False, padrao=False),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 10,
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX, "celulas_max": limites.GRADE_CELULAS_MAX,
             "raio_m_max": limites.DENSIDADE_RAIO_M_MAX},
)
def densidade_kernel(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    dimensao = familia(camada)[2]
    if dimensao == 2:
        raise ErroFerramenta("camada_poligonal", "camada precisa ser de pontos ou de linhas")
    campo = parametros.get("campo_peso")
    if campo:
        campo_numerico(ctx, camada, campo)
    raio = metros(parametros, "raio", 1000.0)
    celula = metros(parametros, "tamanho_celula", 100.0)
    funcao = parametros.get("funcao") or "quartica"
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    if dimensao == 0:
        xy, pesos = coordenadas(ctx, camada, utm, campo)
        unidade = "feições por m²" if not campo else f"soma de {campo} por m²"
        amostras = xy.shape[0]
    else:
        xy, pesos, amostras = _pontos_de_linhas(ctx, camada, utm, celula, campo)
        unidade = "metros de linha por m²" if not campo else f"soma de {campo} por m²"
    x0, y0, x1, y1 = extensao(ctx, camada, utm)
    gx, gy, _, _ = grade_de(x0, y0, x1, y1, celula, folga=raio)
    ctx.progresso(30, f"densidade {funcao} com raio {raio} m em {gx.size}x{gy.size} células de {celula} m")
    valores = ee.densidade_kernel(xy, gx, gy, raio, funcao, pesos)
    linhas = _linhas_de_celulas(gx, gy, valores, celula, parametros.get("manter_zeros", False) is True)
    campos = escrever_linhas(ctx, destino, [("coluna", "integer"), ("linha", "integer"), ("x", "double precision"),
                                            ("y", "double precision"), ("densidade", "double precision")],
                             linhas, "Polygon", utm, srid)
    total = float(valores.sum() * celula * celula)
    ctx.log("INFO", f"densidade: {amostras} amostras, soma do campo x área da célula = {total:.6f} "
                    f"(peso total {float(np.sum(pesos)):.6f})")
    return {"geometria": "Polygon", "srid": srid, "campos": campos,
            "metodo": (f"densidade de kernel {funcao}, raio {raio} m, célula {celula} m, calculada em EPSG:{utm} "
                       f"(numpy) sobre {amostras} amostra(s); valor em {unidade}; a integral do campo sobre a "
                       f"grade vale {total:.6f} contra peso total {float(np.sum(pesos)):.6f}")}


def _pontos_de_linhas(ctx, camada: dict, utm: int, celula: float, campo: str | None):
    """Linhas viram pontos de amostragem a cada meia célula, com peso igual ao comprimento representado (ou ao
    campo, distribuído pelo comprimento)."""
    seleto = f", {ident(campo)}::double precision AS v" if campo else ", NULL::double precision AS v"
    with ctx.db() as cur:
        cur.execute(f"SELECT ST_AsBinary(ST_Transform(geom, {int(utm)})) AS g{seleto} "
                    f"FROM {tabela_de(camada)} WHERE geom IS NOT NULL ORDER BY fid")
        registros = cur.fetchall()
    partes, pesos, feicoes = [], [], 0
    for r in registros:
        g = swkb.loads(bytes(r["g"]))
        linhas = list(g.geoms) if isinstance(g, MultiLineString) else [g]
        coordenadas_linha = [list(x.coords) for x in linhas if isinstance(x, LineString)]
        xy, w = ee.amostrar_linhas(coordenadas_linha, max(celula / 2.0, 1.0))
        if xy.shape[0] == 0:
            continue
        if r["v"] is not None:
            w = w * (float(r["v"]) / w.sum())
        partes.append(xy)
        pesos.append(w)
        feicoes += 1
    if not partes:
        raise ErroFerramenta("camada_vazia", f"camada {camada['titulo']!r} sem linha com comprimento")
    return np.vstack(partes), np.concatenate(pesos), feicoes


def _linhas_de_celulas(gx, gy, valores, celula: float, manter_zeros: bool) -> list[tuple]:
    """Uma linha por célula: (coluna, linha, x, y, valor, WKB do quadrado da célula) no SRID métrico."""
    meio = celula / 2.0
    saida = []
    for j, y in enumerate(gy):
        linha_valores = valores[j]
        for i, x in enumerate(gx):
            v = float(linha_valores[i])
            if not manter_zeros and (v == 0.0 or not math.isfinite(v)):
                continue
            quadro = Polygon([(x - meio, y - meio), (x + meio, y - meio), (x + meio, y + meio),
                              (x - meio, y + meio), (x - meio, y - meio)])
            saida.append((i, j, float(x), float(y), v if math.isfinite(v) else None, wkb(quadro)))
    return saida


# ---------------------------------------------------------------- hot spot Getis-Ord Gi*
@ferramenta(
    nome="hot_spot", titulo="Pontos quentes (Getis-Ord Gi*)", categoria="resumo", versao=1,
    descricao="Escore z e p de Getis-Ord Gi* por feição, com vizinhança por distância fixa: diz onde valores "
              "altos (ou baixos) se agrupam mais do que o acaso explicaria. A geometria de entrada é copiada.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada com o valor"),
        Parametro("campo", "GPString", "campo numérico analisado"),
        Parametro("distancia", "GPLinearUnit", "distância da vizinhança", obrigatorio=False,
                  padrao={"distance": 1, "units": "esriKilometers"}, minimo=1),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 8,
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX},
)
def hot_spot(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    campo = campo_numerico(ctx, camada, parametros["campo"])
    raio = metros(parametros, "distancia", 1000.0)
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    xy, valores = coordenadas(ctx, camada, utm, campo)
    ctx.progresso(30, f"Gi* em {xy.shape[0]} feições, vizinhança de {raio} m")
    r = ee.gi_estrela(valores, xy, raio)
    faixas = _faixa_gi(r["z"])
    with ctx.db() as cur:
        cur.execute(f"SELECT fid FROM {tabela_de(camada)} WHERE geom IS NOT NULL ORDER BY fid")
        fids = [x["fid"] for x in cur.fetchall()]
    tipo_saida = familia(camada)[1]
    select = (
        f"WITH r(fid_origem, valor, z, p, vizinhos, faixa) AS (VALUES "
        + ", ".join(
            f"({int(f)}, {float(v)!r}::double precision, "
            f"{('NULL' if not math.isfinite(float(z)) else repr(float(z)))}::double precision, "
            f"{('NULL' if not math.isfinite(float(p)) else repr(float(p)))}::double precision, {int(n)}, {int(b)})"
            for f, v, z, p, n, b in zip(fids, valores, r["z"], r["p"], r["vizinhos"], faixas, strict=True))
        + f") SELECT r.fid_origem, r.valor, r.z, r.p, r.vizinhos, r.faixa, ST_Multi(c.geom) AS geom "
          f"FROM {tabela_de(camada)} c JOIN r ON r.fid_origem = c.fid ORDER BY r.fid_origem"
    )
    campos = escrever(ctx, destino, select, tipo_saida, srid)
    return {"geometria": tipo_saida, "srid": srid, "campos": campos,
            "metodo": (f"Getis-Ord Gi* sobre {campo!r} com pesos binários e vizinhança de distância fixa de "
                       f"{raio} m medida em EPSG:{utm} (o próprio ponto entra na vizinhança); z é o Gi* "
                       f"padronizado, p é bilateral pela normal; faixa segue o Gi_Bin (+-3 = 99 %, +-2 = 95 %, "
                       f"+-1 = 90 %); média {r['media']:.6f}, desvio {r['desvio']:.6f}, n = {r['n']}")}


def _faixa_gi(z) -> list[int]:
    saida = []
    for valor in np.asarray(z, dtype=float):
        if not math.isfinite(valor):
            saida.append(0)
            continue
        faixa = 0
        for corte, nivel in FAIXAS_GI:
            if abs(valor) >= corte:
                faixa = nivel if valor > 0 else -nivel
                break
        saida.append(faixa)
    return saida


# ---------------------------------------------------------------- centro médio, distância padrão e elipse
@ferramenta(
    nome="centro_medio", titulo="Centro médio, distância padrão e elipse", categoria="resumo", versao=1,
    descricao="Centro médio (opcionalmente ponderado), círculo da distância padrão ou elipse de desvio padrão "
              "(distribuição direcional) do conjunto de feições.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada analisada"),
        Parametro("forma", "GPString", "forma de saída", obrigatorio=False, padrao="elipse",
                  opcoes=FORMAS_CENTRO),
        Parametro("campo_peso", "GPString", "campo de peso", obrigatorio=False),
        Parametro("desvios", "GPDouble", "número de desvios padrão", obrigatorio=False, padrao=1.0,
                  minimo=0.5, maximo=3.0),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX},
)
def centro_medio(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    forma = parametros.get("forma") or "elipse"
    campo = parametros.get("campo_peso")
    if campo:
        campo_numerico(ctx, camada, campo)
    desvios = float(parametros.get("desvios") or 1.0)
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    xy, pesos = coordenadas(ctx, camada, utm, campo)
    if campo and (pesos < 0).any():
        raise ErroFerramenta("peso_negativo", f"campo_peso: {campo!r} tem valor negativo")
    c = ee.centro_medio(xy, pesos)
    colunas = [("n", "integer"), ("peso_total", "double precision"), ("centro_x", "double precision"),
               ("centro_y", "double precision"), ("distancia_padrao", "double precision"),
               ("eixo_maior", "double precision"), ("eixo_menor", "double precision"),
               ("rotacao_graus", "double precision"), ("desvios", "double precision")]
    if forma == "centro":
        geometria, tipo, elipse = Point(c["x"], c["y"]), "Point", None
    elif forma == "circulo_distancia_padrao":
        geometria = Point(c["x"], c["y"]).buffer(c["distancia_padrao"] * desvios, quad_segs=64)
        tipo, elipse = "Polygon", None
    else:
        elipse = ee.elipse_desvio_padrao(xy, desvios, pesos)
        geometria, tipo = Polygon(ee.pontos_da_elipse(elipse)), "Polygon"
    linha = (c["n"], c["peso_total"], c["x"], c["y"], c["distancia_padrao"],
             (elipse or {}).get("eixo_maior"), (elipse or {}).get("eixo_menor"),
             (elipse or {}).get("rotacao_graus"), desvios, wkb(geometria))
    campos = escrever_linhas(ctx, destino, colunas, [linha], tipo, utm, srid)
    return {"geometria": tipo, "srid": srid, "campos": campos,
            "metodo": (f"{forma} de {c['n']} feição(ões) calculada em EPSG:{utm}"
                       + (f", ponderada por {campo!r}" if campo else "")
                       + f"; distância padrão {c['distancia_padrao']:.4f} m, {desvios} desvio(s); "
                       f"a rotação da elipse é o azimute do eixo maior, em graus a partir do Norte")}


# ---------------------------------------------------------------- vizinho mais próximo médio
@ferramenta(
    nome="vizinho_mais_proximo_medio", titulo="Vizinho mais próximo médio", categoria="proximidade", versao=1,
    descricao="Índice R de Clark & Evans: compara a distância média ao vizinho mais próximo com a esperada num "
              "processo aleatório de mesma densidade. Saída = uma feição com a área de referência e o resultado.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de pontos"),
        Parametro("camada_area", "GPFeatureRecordSetLayer", "área de referência", obrigatorio=False,
                  descricao="sem ela, a área é a do casco convexo dos próprios pontos"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 3,
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX},
)
def vizinho_mais_proximo_medio(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    if familia(camada)[2] != 0:
        raise ErroFerramenta("camada_nao_pontual", "camada precisa ser de pontos")
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    xy, _ = coordenadas(ctx, camada, utm)
    area_geom, area_m2, origem = _area_de_referencia(ctx, entradas.get("camada_area"), camada, utm)
    r = ee.vizinho_mais_proximo_medio(xy, area_m2)
    colunas = [("n", "integer"), ("area_m2", "double precision"), ("observada_m", "double precision"),
               ("esperada_m", "double precision"), ("razao", "double precision"), ("z", "double precision"),
               ("p", "double precision")]
    linha = (r["n"], r["area"], r["observada"], r["esperada"], r["razao"], r["z"], r["p"], wkb(area_geom))
    campos = escrever_linhas(ctx, destino, colunas, [linha], "Polygon", utm, srid)
    return {"geometria": "Polygon", "srid": srid, "campos": campos,
            "metodo": (f"índice R de Clark & Evans sobre {r['n']} pontos em EPSG:{utm}, área de referência = "
                       f"{origem} ({r['area']:.2f} m²); razão {r['razao']:.6f}, z {r['z']:.6f}, p {r['p']:.6g}; "
                       f"razão abaixo de 1 indica agrupamento, acima de 1 indica dispersão")}


def _area_de_referencia(ctx, camada_area, camada, utm: int):
    """(geometria em EPSG:utm, área em m², texto de origem). Sem camada de área, o casco convexo dos pontos."""
    if camada_area:
        alvo, origem = camada_area, f"união da camada {camada_area['titulo']!r}"
        sql = (f"SELECT ST_AsBinary(g) AS g, ST_Area(g) AS a FROM (SELECT ST_Union(ST_MakeValid("
               f"ST_Transform(geom, {int(utm)}))) AS g FROM {tabela_de(alvo)}) t")
    else:
        origem = "casco convexo dos pontos"
        sql = (f"SELECT ST_AsBinary(g) AS g, ST_Area(g) AS a FROM (SELECT ST_ConvexHull(ST_Collect("
               f"ST_Transform(geom, {int(utm)}))) AS g FROM {tabela_de(camada)}) t")
    with ctx.db() as cur:
        cur.execute(sql)
        r = cur.fetchone()
    if r is None or r["g"] is None or not r["a"] or float(r["a"]) <= 0:
        raise ErroFerramenta("area_invalida", "área de referência com área zero: informe camada_area")
    return swkb.loads(bytes(r["g"])), float(r["a"]), origem


# ---------------------------------------------------------------- I de Moran global
@ferramenta(
    nome="moran_global", titulo="Autocorrelação espacial (I de Moran)", categoria="resumo", versao=1,
    descricao="I de Moran global com vizinhança por distância fixa e teste de significância sob normalidade. "
              "Saída = uma feição com a área analisada e o resultado.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada com o valor"),
        Parametro("campo", "GPString", "campo numérico analisado"),
        Parametro("distancia", "GPLinearUnit", "distância da vizinhança", obrigatorio=False,
                  padrao={"distance": 1, "units": "esriKilometers"}, minimo=1),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 6,
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX},
)
def moran_global(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    campo = campo_numerico(ctx, camada, parametros["campo"])
    raio = metros(parametros, "distancia", 1000.0)
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    xy, valores = coordenadas(ctx, camada, utm, campo)
    r = ee.moran_global(valores, xy, raio)
    area_geom, _area, _origem = _area_de_referencia(ctx, None, camada, utm)
    colunas = [("n", "integer"), ("campo", "text"), ("distancia_m", "double precision"), ("i", "double precision"),
               ("esperado", "double precision"), ("variancia", "double precision"), ("z", "double precision"),
               ("p", "double precision"), ("pares", "double precision")]
    linha = (r["n"], campo, raio, r["i"], r["esperado"], r["variancia"], r["z"], r["p"], r["s0"], wkb(area_geom))
    campos = escrever_linhas(ctx, destino, colunas, [linha], "Polygon", utm, srid)
    return {"geometria": "Polygon", "srid": srid, "campos": campos,
            "metodo": (f"I de Moran global de {campo!r} com pesos binários por distância fixa de {raio} m em "
                       f"EPSG:{utm} (sem o próprio ponto), {int(r['s0'])} pares; I = {r['i']:.6f}, esperado "
                       f"{r['esperado']:.6f}, z = {r['z']:.6f}, p = {r['p']:.6g} sob normalidade")}


# ---------------------------------------------------------------- superfícies: IDW e TIN
def superficie(ctx, camada: dict, campo: str, metodo: str, celula: float, potencia: float, vizinhos: int,
               utm: int, folga: float = 0.0):
    """(gx, gy, array) da superfície interpolada nos centros de célula, em EPSG:`utm`. `idw` = inverso da
    distância (Shepard); `tin` = triangulação de Delaunay com interpolação linear (o mesmo método do
    `gdal_grid -a linear`, aqui pela triangulação do scipy, que é a mesma Qhull que o GDAL usa)."""
    xy, valores = coordenadas(ctx, camada, utm, campo)
    x0, y0, x1, y1 = extensao(ctx, camada, utm)
    gx, gy, _, _ = grade_de(x0, y0, x1, y1, celula, folga=folga)
    malha_x, malha_y = np.meshgrid(gx, gy)
    alvos = np.column_stack([malha_x.ravel(), malha_y.ravel()])
    if metodo == "idw":
        z = ee.idw(xy, valores, alvos, potencia, vizinhos)
    elif metodo == "tin":
        from scipy.interpolate import LinearNDInterpolator

        if xy.shape[0] < 3:
            raise ErroFerramenta("amostras_insuficientes", "a triangulação exige pelo menos três amostras")
        z = LinearNDInterpolator(xy, valores)(alvos)
    else:
        raise ErroFerramenta("metodo_invalido", f"metodo: {metodo!r} fora de {list(METODOS_SUPERFICIE)}")
    return gx, gy, np.asarray(z, dtype=float).reshape(malha_x.shape), xy.shape[0]


@ferramenta(
    nome="interpolacao_idw", titulo="Interpolação por inverso da distância (IDW)", categoria="resumo", versao=1,
    descricao="Superfície contínua a partir de pontos amostrados, em células quadradas: cada célula recebe a "
              "média dos vizinhos mais próximos ponderada pelo inverso da distância elevada à potência. Célula "
              "sobre uma amostra recebe o valor da amostra.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de pontos amostrados"),
        Parametro("campo", "GPString", "campo numérico interpolado"),
        Parametro("potencia", "GPDouble", "potência", obrigatorio=False, padrao=2.0, minimo=0.1, maximo=10.0),
        Parametro("vizinhos", "GPLong", "amostras por célula", obrigatorio=False, padrao=12, minimo=1,
                  maximo=limites.IDW_VIZINHOS_MAX),
        Parametro("tamanho_celula", "GPLinearUnit", "tamanho da célula", obrigatorio=False,
                  padrao={"distance": 100, "units": "esriMeters"}, minimo=1),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 10,
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX, "celulas_max": limites.GRADE_CELULAS_MAX,
             "vizinhos_max": limites.IDW_VIZINHOS_MAX},
)
def interpolacao_idw(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    if familia(camada)[2] != 0:
        raise ErroFerramenta("camada_nao_pontual", "camada precisa ser de pontos")
    campo = campo_numerico(ctx, camada, parametros["campo"])
    celula = metros(parametros, "tamanho_celula", 100.0)
    potencia = float(parametros.get("potencia") or 2.0)
    vizinhos = int(parametros.get("vizinhos") or 12)
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    ctx.progresso(30, f"IDW potência {potencia} com {vizinhos} vizinhos, célula {celula} m")
    gx, gy, z, amostras = superficie(ctx, camada, campo, "idw", celula, potencia, vizinhos, utm)
    linhas = _linhas_de_celulas(gx, gy, z, celula, manter_zeros=True)
    campos = escrever_linhas(ctx, destino, [("coluna", "integer"), ("linha", "integer"), ("x", "double precision"),
                                            ("y", "double precision"), ("valor", "double precision")],
                             linhas, "Polygon", utm, srid)
    return {"geometria": "Polygon", "srid": srid, "campos": campos,
            "metodo": (f"IDW de {campo!r} com potência {potencia} e {vizinhos} vizinho(s) mais próximo(s), "
                       f"célula {celula} m, calculado em EPSG:{utm} sobre {amostras} amostra(s); célula cujo "
                       f"centro cai exatamente sobre uma amostra recebe o valor da amostra")}


# ---------------------------------------------------------------- isolinhas
@ferramenta(
    nome="contorno", titulo="Isolinhas (contorno)", categoria="resumo", versao=1,
    descricao="Isolinhas de uma superfície interpolada a partir de pontos amostrados, no intervalo pedido. A "
              "superfície sai por IDW ou por triangulação (TIN) e as linhas saem do gerador de contorno do GDAL.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de pontos amostrados"),
        Parametro("campo", "GPString", "campo numérico interpolado"),
        Parametro("intervalo", "GPDouble", "intervalo entre isolinhas", minimo=1e-9),
        Parametro("metodo", "GPString", "método de superfície", obrigatorio=False, padrao="idw",
                  opcoes=METODOS_SUPERFICIE),
        Parametro("potencia", "GPDouble", "potência do IDW", obrigatorio=False, padrao=2.0, minimo=0.1,
                  maximo=10.0),
        Parametro("vizinhos", "GPLong", "amostras por célula", obrigatorio=False, padrao=12, minimo=1,
                  maximo=limites.IDW_VIZINHOS_MAX),
        Parametro("tamanho_celula", "GPLinearUnit", "tamanho da célula", obrigatorio=False,
                  padrao={"distance": 100, "units": "esriMeters"}, minimo=1),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 12,
    limites={"feicoes_max": limites.PADROES_FEICOES_MAX, "linhas_max": limites.CONTORNO_LINHAS_MAX},
)
def contorno(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    limitar_feicoes(camada, limites.PADROES_FEICOES_MAX)
    if familia(camada)[2] != 0:
        raise ErroFerramenta("camada_nao_pontual", "camada precisa ser de pontos")
    campo = campo_numerico(ctx, camada, parametros["campo"])
    intervalo = float(parametros["intervalo"])
    metodo = parametros.get("metodo") or "idw"
    celula = metros(parametros, "tamanho_celula", 100.0)
    srid, utm = camada["srid"], utm_da_camada(ctx, camada)
    gx, gy, z, amostras = superficie(ctx, camada, campo, metodo, celula,
                                     float(parametros.get("potencia") or 2.0),
                                     int(parametros.get("vizinhos") or 12), utm)
    ctx.progresso(50, f"contorno de {intervalo} em grade {gx.size}x{gy.size}")
    linhas = _isolinhas(gx, gy, z, celula, intervalo)
    if len(linhas) > limites.CONTORNO_LINHAS_MAX:
        raise ErroFerramenta("intervalo_pequeno_demais",
                             f"intervalo: {len(linhas)} isolinhas acima do limite de "
                             f"{limites.CONTORNO_LINHAS_MAX}; aumente o intervalo",
                             {"campo": "intervalo", "linhas": len(linhas)})
    if not linhas:
        raise ErroFerramenta("sem_isolinha",
                             f"intervalo: nenhuma isolinha de {intervalo} cruza a faixa de valores "
                             f"({float(np.nanmin(z)):.6g} a {float(np.nanmax(z)):.6g}); use intervalo menor",
                             {"campo": "intervalo"})
    campos = escrever_linhas(ctx, destino, [("valor", "double precision")], linhas, "MultiLineString", utm, srid)
    return {"geometria": "MultiLineString", "srid": srid, "campos": campos,
            "metodo": (f"superfície {metodo} de {campo!r} em célula de {celula} m sobre {amostras} amostra(s) em "
                       f"EPSG:{utm} e isolinhas de {intervalo} por gdal.ContourGenerateEx; "
                       f"{len(linhas)} isolinha(s)")}


def _isolinhas(gx, gy, z, celula: float, intervalo: float) -> list[tuple]:
    """Isolinhas pelo gerador do GDAL sobre a superfície em memória; devolve [(valor, WKB da linha)]."""
    from osgeo import gdal, ogr

    gdal.UseExceptions()
    ogr.UseExceptions()
    ny, nx = z.shape
    raster = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Float64)
    # o array tem a linha 0 no MENOR y; o GeoTransform do GDAL parte do canto superior esquerdo
    raster.SetGeoTransform([float(gx[0] - celula / 2.0), float(celula), 0.0,
                            float(gy[-1] + celula / 2.0), 0.0, -float(celula)])
    banda = raster.GetRasterBand(1)
    banda.SetNoDataValue(float("nan"))
    # WriteRaster com o buffer bruto: o WriteArray do GDAL passa por `osgeo.gdal_array`, que nesta máquina
    # está compilado contra numpy 1.x e não importa sob numpy 2.x
    banda.WriteRaster(0, 0, nx, ny, np.ascontiguousarray(z[::-1], dtype=np.float64).tobytes(),
                      buf_type=gdal.GDT_Float64)
    fonte = ogr.GetDriverByName("Memory").CreateDataSource("contorno")
    camada_ogr = fonte.CreateLayer("contorno", geom_type=ogr.wkbLineString)
    camada_ogr.CreateField(ogr.FieldDefn("valor", ogr.OFTReal))
    gdal.ContourGenerateEx(banda, camada_ogr, options=[f"LEVEL_INTERVAL={intervalo!r}", "ELEV_FIELD=0",
                                                       "NODATA=nan", "POLYGONIZE=NO"])
    saida = []
    for feicao in camada_ogr:
        g = feicao.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        linha = swkb.loads(bytes(g.ExportToWkb()))
        if isinstance(linha, LineString):
            linha = MultiLineString([linha])
        saida.append((float(feicao.GetField("valor")), wkb(linha)))
    del camada_ogr, fonte, banda, raster
    return saida
