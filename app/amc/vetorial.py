"""Extratores sobre vetor (item L3-01-c-extracao-fator; hipótese do item, além da estatística zonal de
`app.amc.zonal`): polígono (fração de área intersectada, área, contagem, atributo ponderado por área), linha
(comprimento dentro, distância à mais próxima) e ponto (contagem em raio, densidade kernel com largura declarada,
distância ao mais próximo, atributo do mais próximo).

Projeção: tudo entra em EPSG:4326 e é reprojetado UMA VEZ para o `srid_trabalho` do conjunto de unidades (a mesma
zona UTM SIRGAS 2000 escolhida em `app.amc.crs`, decisão A7 — nunca graus, nunca Web Mercator) antes de qualquer
área, comprimento, raio ou distância. `srid_trabalho` vem de quem chama (o conjunto já o gravou ao ser criado).

Ausência de dado: a CAMADA sem nenhuma feição aborta a extração inteira (`ErroExtracao('camada_vazia', ...)`),
igual ao raster sem CRS de `zonal.py` — nunca produz coluna de zeros. Já a unidade sem interseção com uma camada
não vazia tem resposta real e legítima (fração 0, área 0, contagem 0): isso é dado, não ausência. Geometria
inválida (auto-interseção) é reparada com `shapely.make_valid` antes de qualquer operação booleana, nunca ignorada
e nunca derruba o job silenciosamente — a reparação fica registrada em `avisos`.
"""

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from app.amc.zonal import ErroExtracao

TIPOS = (
    "vetor_fracao_area", "vetor_area", "vetor_contagem", "vetor_atributo_ponderado_area",
    "vetor_comprimento_dentro", "vetor_distancia_mais_proxima",
    "vetor_contagem_raio", "vetor_densidade_kernel", "vetor_atributo_mais_proximo",
)
_TIPOS_POLIGONO = ("vetor_fracao_area", "vetor_area", "vetor_contagem", "vetor_atributo_ponderado_area")
_TIPOS_LINHA_OU_PONTO_DIST = ("vetor_comprimento_dentro", "vetor_distancia_mais_proxima", "vetor_atributo_mais_proximo")
_TIPOS_PONTO_RAIO = ("vetor_contagem_raio", "vetor_densidade_kernel")


def _gpd():
    """geopandas entra tarde de propósito: hoje ele vem do site do usuário, não do venv da aplicação
    (`requirements.txt`, nota do shapely), e um import no topo deste arquivo chega a `app.main` pelo registro de
    jobs — o que fazia `app.main` deixar de importar sem o site do usuário (tests/unit/test_dependencias.py).
    Quem EXTRAI vetor precisa de geopandas; quem só sobe a aplicação, não."""
    import geopandas as gpd

    return gpd


def _reparar(serie_geom):
    """`shapely.make_valid` nas geometrias inválidas; devolve a série reparada e quantas foram tocadas."""
    invalidas = ~serie_geom.is_valid
    n = int(invalidas.sum())
    if n == 0:
        return serie_geom, 0
    reparada = serie_geom.copy()
    reparada.loc[invalidas] = serie_geom.loc[invalidas].apply(shapely.make_valid)
    return reparada, n


def _gdf(feicoes, srid_trabalho: int):
    gpd = _gpd()
    if not feicoes:
        return gpd.GeoDataFrame(columns=["id"], geometry=gpd.GeoSeries([], crs=f"EPSG:{srid_trabalho}"))
    ids = [f[0] for f in feicoes]
    geoms = [shape(f[1]) for f in feicoes]
    atributos = [f[2] if len(f) > 2 and f[2] else {} for f in feicoes]
    g = gpd.GeoDataFrame({"id": ids, **_transpor(atributos)}, geometry=gpd.GeoSeries(geoms, crs="EPSG:4326"))
    return g.to_crs(epsg=srid_trabalho)


def _transpor(atributos: list[dict]) -> dict:
    chaves: set[str] = set()
    for a in atributos:
        chaves |= set(a.keys())
    return {c: [a.get(c) for a in atributos] for c in chaves}


def validar_parametros(tipo: str, parametros: dict) -> None:
    if tipo == "vetor_contagem_raio":
        r = parametros.get("raio_m")
        if not isinstance(r, int | float) or isinstance(r, bool) or r <= 0:
            raise ErroExtracao("parametro_invalido", "vetor_contagem_raio exige 'raio_m' > 0",
                               {"parametros": parametros})
    if tipo == "vetor_densidade_kernel":
        largura = parametros.get("largura_m")
        if not isinstance(largura, int | float) or isinstance(largura, bool) or largura <= 0:
            raise ErroExtracao("parametro_invalido", "vetor_densidade_kernel exige 'largura_m' > 0",
                               {"parametros": parametros})
    if tipo == "vetor_atributo_ponderado_area" or tipo == "vetor_atributo_mais_proximo":
        if not parametros.get("campo"):
            raise ErroExtracao("parametro_invalido", f"{tipo} exige 'campo' (nome do atributo na camada)",
                               {"parametros": parametros})


def extrair(unidades, camada, tipo: str, srid_trabalho: int, parametros: dict | None = None) -> dict:
    """unidades: [(unidade_id, geojson 4326)]; camada: [(feicao_id, geojson 4326, atributos|None)].
    Devolve {unidade_id: {'valor': float|None, 'cobertura': float, 'avisos': [str]}}."""
    parametros = parametros or {}
    if tipo not in TIPOS:
        raise ErroExtracao("extrator_desconhecido", f"extrator de vetor desconhecido: {tipo!r}")
    validar_parametros(tipo, parametros)
    if not camada:
        raise ErroExtracao("camada_vazia", "a camada não tem nenhuma feição: a extração é abortada, nunca produz "
                           "coluna de zeros", {"tipo": tipo})
    gu = _gdf(unidades, srid_trabalho)
    gu["_area_unidade"] = gu.geometry.area
    gu_geom, n_u = _reparar(gu.geometry)
    gu["geometry"] = gu_geom
    gc = _gdf(camada, srid_trabalho)
    gc_geom, n_c = _reparar(gc.geometry)
    gc["geometry"] = gc_geom
    avisos = []
    if n_u:
        avisos.append(f"{n_u} unidade(s) com geometria inválida reparada por shapely.make_valid")
    if n_c:
        avisos.append(f"{n_c} feição(ões) da camada com geometria inválida reparada por shapely.make_valid")

    if tipo in _TIPOS_POLIGONO:
        saida = _extrair_poligono(gu, gc, tipo, parametros)
    elif tipo == "vetor_comprimento_dentro":
        saida = _comprimento_dentro(gu, gc)
    elif tipo in ("vetor_distancia_mais_proxima", "vetor_atributo_mais_proximo"):
        saida = _mais_proximo(gu, gc, tipo, parametros)
    elif tipo == "vetor_contagem_raio":
        saida = _contagem_raio(gu, gc, float(parametros["raio_m"]))
    elif tipo == "vetor_densidade_kernel":
        saida = _densidade_kernel(gu, gc, float(parametros["largura_m"]))
    else:  # pragma: no cover — TIPOS já filtrou
        raise ErroExtracao("extrator_desconhecido", tipo)
    for v in saida.values():
        v["avisos"] = list(avisos)
    return saida


# ---------------------------------------------------------------- polígono
def _extrair_poligono(gu, gc, tipo: str, parametros: dict) -> dict:
    inter = gu[["id", "geometry", "_area_unidade"]].overlay(
        gc[["id", "geometry"] + ([parametros["campo"]] if tipo == "vetor_atributo_ponderado_area" else [])],
        how="intersection", keep_geom_type=False)
    inter = inter[inter.geometry.notna() & ~inter.geometry.is_empty]
    inter["_area_inter"] = inter.geometry.area
    saida = {}
    if tipo == "vetor_fracao_area":
        soma = inter.groupby("id_1")["_area_inter"].sum()
        for uid, geom in zip(gu["id"], gu.geometry, strict=True):
            au = geom.area
            valor = float(soma.get(uid, 0.0) / au) if au > 0 else None
            saida[uid] = {"valor": valor, "cobertura": 1.0 if au > 0 else 0.0}
    elif tipo == "vetor_area":
        soma = inter.groupby("id_1")["_area_inter"].sum()
        for uid in gu["id"]:
            saida[uid] = {"valor": float(soma.get(uid, 0.0)), "cobertura": 1.0}
    elif tipo == "vetor_contagem":
        n = inter.groupby("id_1")["id_2"].nunique()
        for uid in gu["id"]:
            saida[uid] = {"valor": float(n.get(uid, 0)), "cobertura": 1.0}
    else:  # vetor_atributo_ponderado_area
        campo = parametros["campo"]
        inter["_num"] = pd.to_numeric(inter[campo], errors="coerce") * inter["_area_inter"]
        num = inter.groupby("id_1")["_num"].sum()
        den = inter.dropna(subset=["_num"]).groupby("id_1")["_area_inter"].sum()
        for uid in gu["id"]:
            d = den.get(uid, 0.0)
            saida[uid] = {"valor": float(num.get(uid, np.nan) / d) if d > 0 else None,
                          "cobertura": 1.0 if uid in den.index else 0.0}
    return saida


# ---------------------------------------------------------------- linha
def _comprimento_dentro(gu, gc) -> dict:
    inter = gu[["id", "geometry"]].overlay(gc[["id", "geometry"]], how="intersection", keep_geom_type=False)
    inter = inter[inter.geometry.notna() & ~inter.geometry.is_empty]
    comprimento = inter.geometry.length
    soma = comprimento.groupby(inter["id_1"]).sum()
    return {uid: {"valor": float(soma.get(uid, 0.0)), "cobertura": 1.0} for uid in gu["id"]}


# ---------------------------------------------------------------- distância / atributo do mais próximo
def _mais_proximo(gu, gc, tipo: str, parametros: dict) -> dict:
    j = gu[["id", "geometry"]].sjoin_nearest(gc, distance_col="_dist", how="left")
    j = j.drop_duplicates(subset="id_left", keep="first")
    j = j.set_index("id_left")
    saida = {}
    for uid in gu["id"]:
        if uid not in j.index:
            saida[uid] = {"valor": None, "cobertura": 0.0}
            continue
        linha = j.loc[uid]
        if tipo == "vetor_distancia_mais_proxima":
            valor = float(linha["_dist"])
        else:
            valor = linha.get(parametros["campo"])
            valor = float(valor) if isinstance(valor, int | float) and not isinstance(valor, bool) else valor
        saida[uid] = {"valor": valor, "cobertura": 1.0}
    return saida


# ---------------------------------------------------------------- ponto: raio e densidade
def _contagem_raio(gu, gc, raio_m: float) -> dict:
    buf = gu[["id", "geometry"]].copy()
    buf["geometry"] = gu.geometry.buffer(raio_m)
    j = buf.sjoin(gc[["id", "geometry"]], how="left", predicate="intersects")
    n = j.groupby("id_left")["id_right"].apply(lambda s: s.notna().sum())
    return {uid: {"valor": float(n.get(uid, 0)), "cobertura": 1.0} for uid in gu["id"]}


def _densidade_kernel(gu, gc, largura_m: float) -> dict:
    from sklearn.neighbors import KernelDensity
    coords = np.column_stack([gc.geometry.x.to_numpy(), gc.geometry.y.to_numpy()])
    kde = KernelDensity(kernel="gaussian", bandwidth=largura_m).fit(coords)
    centros = gu.geometry.representative_point()
    xy = np.column_stack([centros.x.to_numpy(), centros.y.to_numpy()])
    log_dens = kde.score_samples(xy)
    dens = np.exp(log_dens) * len(gc)  # devolve intensidade (pontos por unidade de área), não densidade normalizada
    return {uid: {"valor": float(v), "cobertura": 1.0} for uid, v in zip(gu["id"], dens, strict=True)}
