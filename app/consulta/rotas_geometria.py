"""GeometryServer compatível com Esri (item L2-04-f), em `/svc/{token}/rest/services/Utilities/
Geometry/GeometryServer`.

É o serviço que a JS API da Esri e o ArcGIS Pro chamam para projetar, medir e combinar geometria sem
ter a biblioteca localmente. Aqui **toda operação é uma chamada ao PostGIS** — nenhuma geometria é
calculada em Python. Duas consequências que valem declarar:

* `project` é `ST_Transform`, com o mesmo PROJ que o resto da plataforma usa; então a coordenada que o
  cliente recebe é a MESMA que uma consulta espacial devolveria, e não uma segunda aproximação.
* `buffer` com `geodesic=true` (ou `unit` em metros sobre coordenada geográfica) é
  `ST_Buffer(geografia, metros)`, que mede sobre o elipsoide. `ST_Buffer` planar sobre grau daria um
  círculo achatado longe do equador; por isso o geodésico é o padrão quando a referência de entrada é
  geográfica, e o planar só acontece quando o cliente pede explicitamente numa projeção métrica.

A credencial é o token do CAMINHO, como no resto do diretório de serviços (item L2-04-b). O serviço
não lê nenhuma tabela: só usa o banco como calculadora geométrica, dentro da mesma conexão com o
contexto de inquilino — nenhuma geometria do cliente é gravada.

Referência: developers.arcgis.com, "Geometry service", "Project", "Buffer", "Areas and lengths"
(acesso em 2026-09-08)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request

from app import db, limites
from app.consulta import geometria_esri as geo
from app.consulta import rotas_diretorio
from app.consulta.formato_esri import resposta_esri
from app.erros import ErroAPI

router = APIRouter(tags=["consulta-esri"])
GEOMETRY = f"{rotas_diretorio.SERVICOS}/Utilities/Geometry/GeometryServer"
LER = rotas_diretorio.LER
# `geometryType` -> chave interna de app/consulta/geometria_esri.py
TIPOS = geo.GEOM_TIPO_ESRI
# `esriSRUnit_*` que a doc aceita em buffer/areasAndLengths/lengths/distance, em metros
UNIDADES = geo.UNIDADES_METROS


async def _parametros(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        ct = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
        elif "application/json" in ct:
            corpo = await request.json()
            if isinstance(corpo, dict):
                p.update({k: (v if isinstance(v, str) else json.dumps(v)) for k, v in corpo.items()})
    return p


def _lista_de_geometrias(bruto, tipo_declarado: str | None) -> tuple[list[dict], str]:
    """`geometries` do protocolo: `{"geometryType":..., "geometries":[...]}` ou a lista solta. O tipo
    declarado vale para TODAS as geometrias do lote, como manda a doc."""
    if bruto in (None, ""):
        raise ErroAPI(400, "geometrias_ausentes", "informe geometries")
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "geometrias_invalidas", "geometries não é JSON válido") from e
    tipo_esri = tipo_declarado
    if isinstance(bruto, dict):
        tipo_esri = bruto.get("geometryType") or tipo_esri
        bruto = bruto.get("geometries")
    if not isinstance(bruto, list):
        raise ErroAPI(400, "geometrias_invalidas", "geometries precisa ser lista (ou objeto com 'geometries')")
    if not bruto:
        raise ErroAPI(400, "geometrias_ausentes", "geometries vazio")
    if len(bruto) > limites.GEOMETRIA_FEICOES_MAX:
        raise ErroAPI(413, "geometrias_demais",
                      f"{len(bruto)} geometrias (teto {limites.GEOMETRIA_FEICOES_MAX})")
    tipo = TIPOS.get(tipo_esri or "esriGeometryPoint")
    if tipo is None:
        raise ErroAPI(400, "geometry_type_invalido", f"geometryType não suportado: {tipo_esri!r}")
    saida = []
    vertices = 0
    for g in bruto:
        if not isinstance(g, dict):
            raise ErroAPI(400, "geometrias_invalidas", "cada geometria precisa ser um objeto JSON")
        vertices += geo.contar_vertices(g, tipo)
        saida.append(g)
    if vertices > limites.GEOMETRIA_VERTICES_MAX:
        raise ErroAPI(413, "geometria_grande_demais",
                      f"{vertices} vértices no lote (teto {limites.GEOMETRIA_VERTICES_MAX})")
    return saida, tipo


def _uma_geometria(bruto, tipo_declarado: str | None) -> tuple[dict, str]:
    if bruto in (None, ""):
        raise ErroAPI(400, "geometria_ausente", "informe geometry")
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "geometria_invalida", "geometry não é JSON válido") from e
    if not isinstance(bruto, dict):
        raise ErroAPI(400, "geometria_invalida", "geometry precisa ser objeto JSON")
    tipo = TIPOS.get(tipo_declarado or "esriGeometryPolygon")
    if tipo is None:
        raise ErroAPI(400, "geometry_type_invalido", f"geometryType não suportado: {tipo_declarado!r}")
    return bruto, tipo


def _wkid_obrigatorio(valor, campo: str) -> int:
    wkid = geo.sr_wkid(valor)
    if not wkid:
        raise ErroAPI(400, "sr_ausente", f"{campo} é obrigatório (wkid da referência espacial)")
    return int(wkid)


def _unidade_em_metros(valor) -> float:
    if valor in (None, ""):
        return 1.0
    if isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
        valor = int(valor)
    if isinstance(valor, int) and not isinstance(valor, bool):
        # a doc também aceita o código numérico do wkid de unidade linear; só os que a casa usa
        codigos = {9001: "esriSRUnit_Meter", 9036: "esriSRUnit_Kilometer", 9002: "esriSRUnit_Foot"}
        valor = codigos.get(valor)
    fator = UNIDADES.get(valor)
    if fator is None:
        raise ErroAPI(400, "unidade_invalida", f"unit não reconhecido: {valor!r}")
    return fator


def _esri_de_geojson(gj: str, wkid: int) -> dict:
    from app.consulta.motor import _geojson_para_esri

    forma = _geojson_para_esri(gj, None, lambda x, y: [x, y])  # noqa: SLF001 — mesma conversão da query
    forma["spatialReference"] = {"wkid": wkid, "latestWkid": wkid}
    return forma


def _autenticar(request: Request, token: str):
    return rotas_diretorio._auth_do_caminho(request, token)  # noqa: SLF001 — mesma família


def _bool(valor, padrao=False) -> bool:
    if valor in (None, ""):
        return padrao
    return str(valor).strip().lower() in ("true", "1", "yes", "sim")


# ------------------------------------------------------------------ descritor
@router.get(GEOMETRY, openapi_extra=LER, operation_id="svc_geometry_server")
@router.post(GEOMETRY, openapi_extra=LER, operation_id="svc_geometry_server_post")
def geometry_server(token: str, request: Request):
    _autenticar(request, token)
    p = dict(request.query_params)
    return resposta_esri({
        "currentVersion": rotas_diretorio.CURRENT_VERSION,
        "serviceDescription": "operações de geometria sobre PostGIS",
        "capabilities": "Project,Buffer,AreasAndLengths,Lengths,Simplify,Union,Intersect,Difference,"
                        "ConvexHull,Distance",
    }, p.get("f"), p.get("callback"))


# ------------------------------------------------------------------ project
@router.get(f"{GEOMETRY}/project", openapi_extra=LER, operation_id="svc_geometry_project_get")
@router.post(f"{GEOMETRY}/project", openapi_extra=LER, operation_id="svc_geometry_project")
async def project(token: str, request: Request):
    """`ST_Transform` geometria a geometria. É a mesma transformação que a consulta espacial usa; um
    ponto projetado aqui e o mesmo ponto projetado numa consulta não podem divergir."""
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, tipo = _lista_de_geometrias(p.get("geometries"), p.get("geometryType"))
    entrada = _wkid_obrigatorio(p.get("inSR"), "inSR")
    saida = _wkid_obrigatorio(p.get("outSR"), "outSR")
    resultado = []
    with db.db(auth.contexto()) as cur:
        for g in geometrias:
            wkt = geo.para_ewkt(g, tipo, entrada)
            cur.execute("SELECT ST_AsGeoJSON(ST_Transform(ST_GeomFromEWKT(%s), %s), 12) AS gj", (wkt, saida))
            resultado.append(_esri_de_geojson(cur.fetchone()["gj"], saida))
    return resposta_esri({"geometries": resultado}, p.get("f"), p.get("callback"))


# ------------------------------------------------------------------ buffer
@router.get(f"{GEOMETRY}/buffer", openapi_extra=LER, operation_id="svc_geometry_buffer_get")
@router.post(f"{GEOMETRY}/buffer", openapi_extra=LER, operation_id="svc_geometry_buffer")
async def buffer(token: str, request: Request):
    """Envoltória. Geodésica por padrão quando a referência de saída é geográfica: o raio é medido
    sobre o elipsoide (`geography`), não em graus. `bufferSR` projeta antes de medir, como na doc."""
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, tipo = _lista_de_geometrias(p.get("geometries"), p.get("geometryType"))
    entrada = _wkid_obrigatorio(p.get("inSR"), "inSR")
    saida = geo.sr_wkid(p.get("outSR")) or entrada
    medida = geo.sr_wkid(p.get("bufferSR")) or saida
    distancias = _distancias(p.get("distances"), len(geometrias))
    fator = _unidade_em_metros(p.get("unit"))
    geodesico = _bool(p.get("geodesic"), medida == 4326)
    unir = _bool(p.get("unionResults"))
    resultado = []
    with db.db(auth.contexto()) as cur:
        for g, d in zip(geometrias, distancias, strict=True):
            wkt = geo.para_ewkt(g, tipo, entrada)
            if geodesico:
                sql = ("SELECT ST_AsGeoJSON(ST_Transform("
                       "ST_Buffer(ST_Transform(ST_GeomFromEWKT(%s), 4326)::geography, %s)::geometry, %s), 12) AS gj")
                params = (wkt, d * fator, saida)
            else:
                sql = ("SELECT ST_AsGeoJSON(ST_Transform(ST_Buffer("
                       "ST_Transform(ST_GeomFromEWKT(%s), %s), %s), %s), 12) AS gj")
                params = (wkt, medida, d * fator, saida)
            cur.execute(sql, params)
            resultado.append(_esri_de_geojson(cur.fetchone()["gj"], saida))
        if unir and len(resultado) > 1:
            resultado = [_unir(cur, resultado, saida)]
    return resposta_esri({"geometries": resultado}, p.get("f"), p.get("callback"))


def _unir(cur, formas: list[dict], wkid: int) -> dict:
    wkts = [geo.para_ewkt(f, "polygon", wkid) for f in formas]
    cur.execute("SELECT ST_AsGeoJSON(ST_Union(ARRAY(SELECT ST_GeomFromEWKT(unnest(%s::text[])))), 12) AS gj",
                (wkts,))
    return _esri_de_geojson(cur.fetchone()["gj"], wkid)


def _distancias(bruto, quantas: int) -> list[float]:
    if bruto in (None, ""):
        raise ErroAPI(400, "distancias_ausentes", "informe distances")
    if isinstance(bruto, str):
        partes = [x for x in bruto.replace("[", "").replace("]", "").split(",") if x.strip() != ""]
    elif isinstance(bruto, list):
        partes = bruto
    else:
        raise ErroAPI(400, "distancias_invalidas", "distances precisa ser lista de números")
    try:
        valores = [float(x) for x in partes]
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "distancias_invalidas", "distances precisa ser lista de números") from e
    if any(v < 0 for v in valores):
        raise ErroAPI(400, "distancias_invalidas", "distância negativa não é envoltória")
    if len(valores) == 1:
        return valores * quantas
    if len(valores) != quantas:
        raise ErroAPI(400, "distancias_invalidas",
                      "distances precisa ter uma distância, ou uma por geometria")
    return valores


# ------------------------------------------------------------------ medidas
@router.get(f"{GEOMETRY}/areasAndLengths", openapi_extra=LER, operation_id="svc_geometry_areas_get")
@router.post(f"{GEOMETRY}/areasAndLengths", openapi_extra=LER, operation_id="svc_geometry_areas")
async def areas_and_lengths(token: str, request: Request):
    """Área e perímetro de polígonos. `calculationType=geodesic|preserveShape` mede sobre o elipsoide
    (`geography`); `planar` mede na projeção declarada — a diferença entre os dois é enorme em grau,
    e por isso o padrão é geodésico quando a referência é geográfica."""
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, _ = _lista_de_geometrias(p.get("polygons") or p.get("geometries"), "esriGeometryPolygon")
    entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
    fator = _unidade_em_metros(p.get("lengthUnit"))
    fator_area = _unidade_em_metros(p.get("areaUnit")) ** 2 if p.get("areaUnit") else fator ** 2
    geodesico = (p.get("calculationType") or ("geodesic" if entrada == 4326 else "planar")).lower() != "planar"
    areas, comprimentos = [], []
    with db.db(auth.contexto()) as cur:
        for g in geometrias:
            wkt = geo.para_ewkt(g, "polygon", entrada)
            if geodesico:
                cur.execute("SELECT ST_Area(ST_Transform(ST_GeomFromEWKT(%s), 4326)::geography) AS a, "
                            "ST_Perimeter(ST_Transform(ST_GeomFromEWKT(%s), 4326)::geography) AS c", (wkt, wkt))
            else:
                cur.execute("SELECT ST_Area(ST_GeomFromEWKT(%s)) AS a, ST_Perimeter(ST_GeomFromEWKT(%s)) AS c",
                            (wkt, wkt))
            r = cur.fetchone()
            areas.append(float(r["a"]) / fator_area)
            comprimentos.append(float(r["c"]) / fator)
    return resposta_esri({"areas": areas, "lengths": comprimentos}, p.get("f"), p.get("callback"))


@router.get(f"{GEOMETRY}/lengths", openapi_extra=LER, operation_id="svc_geometry_lengths_get")
@router.post(f"{GEOMETRY}/lengths", openapi_extra=LER, operation_id="svc_geometry_lengths")
async def lengths(token: str, request: Request):
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, _ = _lista_de_geometrias(p.get("polylines") or p.get("geometries"), "esriGeometryPolyline")
    entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
    fator = _unidade_em_metros(p.get("lengthUnit"))
    geodesico = (p.get("calculationType") or ("geodesic" if entrada == 4326 else "planar")).lower() != "planar"
    saida = []
    with db.db(auth.contexto()) as cur:
        for g in geometrias:
            wkt = geo.para_ewkt(g, "polyline", entrada)
            if geodesico:
                cur.execute("SELECT ST_Length(ST_Transform(ST_GeomFromEWKT(%s), 4326)::geography) AS c", (wkt,))
            else:
                cur.execute("SELECT ST_Length(ST_GeomFromEWKT(%s)) AS c", (wkt,))
            saida.append(float(cur.fetchone()["c"]) / fator)
    return resposta_esri({"lengths": saida}, p.get("f"), p.get("callback"))


@router.get(f"{GEOMETRY}/distance", openapi_extra=LER, operation_id="svc_geometry_distance_get")
@router.post(f"{GEOMETRY}/distance", openapi_extra=LER, operation_id="svc_geometry_distance")
async def distance(token: str, request: Request):
    p = await _parametros(request)
    auth = _autenticar(request, token)
    g1, t1 = _uma_geometria(p.get("geometry1"), p.get("geometryType1") or p.get("geometryType"))
    g2, t2 = _uma_geometria(p.get("geometry2"), p.get("geometryType2") or p.get("geometryType"))
    entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
    fator = _unidade_em_metros(p.get("distanceUnit"))
    geodesico = _bool(p.get("geodesic"), entrada == 4326)
    with db.db(auth.contexto()) as cur:
        w1, w2 = geo.para_ewkt(g1, t1, entrada), geo.para_ewkt(g2, t2, entrada)
        if geodesico:
            cur.execute("SELECT ST_Distance(ST_Transform(ST_GeomFromEWKT(%s), 4326)::geography, "
                        "ST_Transform(ST_GeomFromEWKT(%s), 4326)::geography) AS d", (w1, w2))
        else:
            cur.execute("SELECT ST_Distance(ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s)) AS d", (w1, w2))
        valor = float(cur.fetchone()["d"]) / fator
    return resposta_esri({"distance": valor}, p.get("f"), p.get("callback"))


# ------------------------------------------------------------------ combinações
def _operacao_binaria(nome_sql: str):
    async def _rodar(token: str, request: Request):
        p = await _parametros(request)
        auth = _autenticar(request, token)
        geometrias, tipo = _lista_de_geometrias(p.get("geometries"), p.get("geometryType"))
        entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
        outra, tipo2 = _uma_geometria(p.get("geometry"), p.get("geometryType") or "esriGeometryPolygon")
        resultado = []
        with db.db(auth.contexto()) as cur:
            w2 = geo.para_ewkt(outra, tipo2, entrada)
            for g in geometrias:
                w1 = geo.para_ewkt(g, tipo, entrada)
                cur.execute(
                    f"SELECT ST_AsGeoJSON({nome_sql}(ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s)), 12) AS gj",
                    (w1, w2),
                )
                gj = cur.fetchone()["gj"]
                resultado.append(_esri_de_geojson(gj, entrada) if gj else {})
        return resposta_esri({"geometries": resultado}, p.get("f"), p.get("callback"))

    return _rodar


_intersect = _operacao_binaria("ST_Intersection")
_difference = _operacao_binaria("ST_Difference")


@router.get(f"{GEOMETRY}/intersect", openapi_extra=LER, operation_id="svc_geometry_intersect_get")
@router.post(f"{GEOMETRY}/intersect", openapi_extra=LER, operation_id="svc_geometry_intersect")
async def intersect(token: str, request: Request):
    return await _intersect(token, request)


@router.get(f"{GEOMETRY}/difference", openapi_extra=LER, operation_id="svc_geometry_difference_get")
@router.post(f"{GEOMETRY}/difference", openapi_extra=LER, operation_id="svc_geometry_difference")
async def difference(token: str, request: Request):
    return await _difference(token, request)


@router.get(f"{GEOMETRY}/union", openapi_extra=LER, operation_id="svc_geometry_union_get")
@router.post(f"{GEOMETRY}/union", openapi_extra=LER, operation_id="svc_geometry_union")
async def union(token: str, request: Request):
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, tipo = _lista_de_geometrias(p.get("geometries"), p.get("geometryType"))
    entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
    with db.db(auth.contexto()) as cur:
        wkts = [geo.para_ewkt(g, tipo, entrada) for g in geometrias]
        cur.execute("SELECT ST_AsGeoJSON(ST_Union(ARRAY(SELECT ST_GeomFromEWKT(unnest(%s::text[])))), 12) AS gj",
                    (wkts,))
        gj = cur.fetchone()["gj"]
    return resposta_esri({"geometry": _esri_de_geojson(gj, entrada) if gj else {}},
                         p.get("f"), p.get("callback"))


@router.get(f"{GEOMETRY}/convexHull", openapi_extra=LER, operation_id="svc_geometry_convex_hull_get")
@router.post(f"{GEOMETRY}/convexHull", openapi_extra=LER, operation_id="svc_geometry_convex_hull")
async def convex_hull(token: str, request: Request):
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, tipo = _lista_de_geometrias(p.get("geometries"), p.get("geometryType"))
    entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
    with db.db(auth.contexto()) as cur:
        wkts = [geo.para_ewkt(g, tipo, entrada) for g in geometrias]
        cur.execute("SELECT ST_AsGeoJSON(ST_ConvexHull(ST_Collect("
                    "ARRAY(SELECT ST_GeomFromEWKT(unnest(%s::text[]))))), 12) AS gj", (wkts,))
        gj = cur.fetchone()["gj"]
    return resposta_esri({"geometry": _esri_de_geojson(gj, entrada) if gj else {}},
                         p.get("f"), p.get("callback"))


@router.get(f"{GEOMETRY}/simplify", openapi_extra=LER, operation_id="svc_geometry_simplify_get")
@router.post(f"{GEOMETRY}/simplify", openapi_extra=LER, operation_id="svc_geometry_simplify")
async def simplify(token: str, request: Request):
    """`simplify` da Esri CONSERTA a geometria (topologia válida, anéis na ordem certa); não é
    generalização por tolerância. `ST_MakeValid` + `ST_ForcePolygonCCW` é a leitura fiel disso —
    generalizar por tolerância aqui devolveria ao cliente uma geometria com menos vértices do que ele
    mandou, que é outra operação (e a que o desenho do MapServer usa, lá com o pixel como tolerância)."""
    p = await _parametros(request)
    auth = _autenticar(request, token)
    geometrias, tipo = _lista_de_geometrias(p.get("geometries"), p.get("geometryType"))
    entrada = _wkid_obrigatorio(p.get("sr") or p.get("inSR"), "sr")
    resultado = []
    with db.db(auth.contexto()) as cur:
        for g in geometrias:
            wkt = geo.para_ewkt(g, tipo, entrada)
            cur.execute("SELECT ST_AsGeoJSON(ST_MakeValid(ST_GeomFromEWKT(%s)), 12) AS gj", (wkt,))
            resultado.append(_esri_de_geojson(cur.fetchone()["gj"], entrada))
    return resposta_esri({"geometries": resultado}, p.get("f"), p.get("callback"))
