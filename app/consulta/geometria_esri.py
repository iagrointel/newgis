"""Geometria Esri (envelope/ponto/multiponto/polilinha/polígono em JSON, ou string `xmin,ymin,xmax,ymax`
para envelope) <-> PostGIS, para o filtro espacial da operação `query` (item L2-04-c). Sem `eval`; a
entrada vira `ST_GeomFromText`/`ST_MakeEnvelope` sempre por parâmetro, nunca por concatenação de texto
do cliente no SQL — coordenadas viajam como `ARRAY[...]::float8[]` bindado, o WKT é montado só com
`%s` e dígitos formatados pelo próprio Python (nunca copiados do JSON de entrada)."""

from __future__ import annotations

import json

from app.erros import ErroAPI

# 9 esriSpatialRel -> operador PostGIS (hipótese do item; ADR do L2-04-c documenta a aproximação de
# esriSpatialRelIndexIntersects, que o PostGIS não expõe separado do teste exato)
SPATIAL_REL = {
    "esriSpatialRelIntersects": "ST_Intersects",
    "esriSpatialRelContains": "ST_Contains",
    "esriSpatialRelCrosses": "ST_Crosses",
    "esriSpatialRelEnvelopeIntersects": "ST_Intersects",  # aplicado sobre ST_Envelope(geom) — ver geom_col()
    "esriSpatialRelIndexIntersects": "ST_Intersects",  # aproximação declarada: sem acesso ao índice cru
    "esriSpatialRelOverlaps": "ST_Overlaps",
    "esriSpatialRelTouches": "ST_Touches",
    "esriSpatialRelWithin": "ST_Within",
    "esriSpatialRelRelation": "ST_Relate",  # usa relationParam (DE-9IM), tratado à parte
}

UNIDADES_METROS = {
    "esriSRUnit_Meter": 1.0,
    "esriSRUnit_Kilometer": 1000.0,
    "esriSRUnit_Foot": 0.3048,
    "esriSRUnit_StatuteMile": 1609.344,
    "esriSRUnit_NauticalMile": 1852.0,
    "esriSRUnit_USNauticalMile": 1852.0,
}

GEOM_TIPO_ESRI = {
    "esriGeometryPoint": "point",
    "esriGeometryMultipoint": "multipoint",
    "esriGeometryPolyline": "polyline",
    "esriGeometryPolygon": "polygon",
    "esriGeometryEnvelope": "envelope",
}


def _num(v, campo="coordenada") -> float:
    """Só aceita `int`/`float` JÁ decodificados (por `json.loads`, nunca texto do usuário) — usado
    nas coordenadas de dentro do JSON de `geometry`. Texto (form csv) passa por `_num_texto`."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErroAPI(400, "geometria_invalida", f"{campo} não numérica: {v!r}")
    return float(v)


def _num_texto(v: str, campo="coordenada") -> float:
    """Converte um número escrito em texto (forma csv de `geometry`, ex. `xmin,ymin,xmax,ymax`) —
    só aceita o que `float()` aceita como número; qualquer outra coisa é `geometria_invalida`, nunca
    processada como SQL (o valor vira parâmetro, nunca é colado no texto da consulta)."""
    try:
        return float(str(v).strip())
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "geometria_invalida", f"{campo} não numérica: {v!r}") from e


def sr_wkid(sr) -> int | None:
    """`inSR`/`outSR`/`spatialReference` aceitam wkid inteiro puro ou `{"wkid":...}`/`{"latestWkid":...}`."""
    if sr is None:
        return None
    if isinstance(sr, (int, float)):
        return int(sr)
    if isinstance(sr, str):
        s = sr.strip()
        if s.lstrip("-").isdigit():
            return int(s)
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "sr_invalido", f"spatial reference inválida: {sr!r}") from e
        return sr_wkid(obj)
    if isinstance(sr, dict):
        return int(sr.get("latestWkid") or sr.get("wkid"))
    raise ErroAPI(400, "sr_invalido", f"spatial reference inválida: {sr!r}")


def _parse_envelope_csv(texto: str) -> dict:
    partes = texto.split(",")
    if len(partes) != 4:
        raise ErroAPI(400, "geometria_invalida", "envelope csv precisa de 4 números: xmin,ymin,xmax,ymax")
    xmin, ymin, xmax, ymax = (_num_texto(p, "envelope") for p in partes)
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}


def parse_geometry(bruto: str, geometry_type: str | None) -> tuple[dict, str]:
    """`geometry` (string) + `geometryType` declarado (ou inferido para envelope csv) -> (obj, tipo).
    `tipo` é uma chave de `GEOM_TIPO_ESRI` invertida ("point","envelope",...)."""
    bruto = (bruto or "").strip()
    if not bruto:
        raise ErroAPI(400, "geometria_ausente", "geometry vazio")
    tipo = GEOM_TIPO_ESRI.get(geometry_type or "esriGeometryEnvelope")
    if tipo is None:
        raise ErroAPI(400, "geometry_type_invalido", f"geometryType não suportado: {geometry_type!r}")
    if bruto.startswith("{"):
        try:
            obj = json.loads(bruto)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "geometria_invalida", "geometry não é JSON válido") from e
        if not isinstance(obj, dict):
            raise ErroAPI(400, "geometria_invalida", "geometry JSON precisa ser um objeto")
        return obj, tipo
    if tipo == "envelope":
        return _parse_envelope_csv(bruto), tipo
    if tipo == "point":
        xy = bruto.split(",")
        if len(xy) < 2:
            raise ErroAPI(400, "geometria_invalida", "ponto csv precisa de x,y")
        return {"x": _num_texto(xy[0]), "y": _num_texto(xy[1])}, tipo
    raise ErroAPI(400, "geometria_invalida", f"forma csv não suportada para {geometry_type}; use JSON")


def _wkt_ponto(p: list) -> str:
    return f"{_num(p[0])} {_num(p[1])}"


def _wkt_anel(anel: list) -> str:
    return "(" + ", ".join(_wkt_ponto(p) for p in anel) + ")"


def para_ewkt(obj: dict, tipo: str, wkid: int) -> str:
    """Constrói o WKT a partir de números já validados como float (nunca texto colado do JSON de
    entrada) — todo valor passa por `_num` antes de entrar na string."""
    if tipo == "envelope":
        xmin, ymin, xmax, ymax = _num(obj["xmin"]), _num(obj["ymin"]), _num(obj["xmax"]), _num(obj["ymax"])
        anel = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]
        return f"SRID={wkid};POLYGON({_wkt_anel(anel)})"
    if tipo == "point":
        return f"SRID={wkid};POINT({_num(obj['x'])} {_num(obj['y'])})"
    if tipo == "multipoint":
        pontos = obj.get("points") or []
        if not pontos:
            raise ErroAPI(400, "geometria_invalida", "multiponto sem points")
        return f"SRID={wkid};MULTIPOINT(" + ", ".join(_wkt_ponto(p) for p in pontos) + ")"
    if tipo == "polyline":
        paths = obj.get("paths") or []
        if not paths:
            raise ErroAPI(400, "geometria_invalida", "polilinha sem paths")
        return f"SRID={wkid};MULTILINESTRING(" + ", ".join(_wkt_anel(p) for p in paths) + ")"
    if tipo == "polygon":
        rings = obj.get("rings") or []
        if not rings:
            raise ErroAPI(400, "geometria_invalida", "polígono sem rings")
        return f"SRID={wkid};POLYGON(" + ", ".join(_wkt_anel(r) for r in rings) + ")"
    raise ErroAPI(400, "geometria_invalida", f"tipo interno desconhecido: {tipo}")  # pragma: no cover


MAX_VERTICES = 200_000  # negação-de-serviço: geometria de filtro absurdamente grande é recusada, não processada


def contar_vertices(obj: dict, tipo: str) -> int:
    if tipo == "envelope" or tipo == "point":
        return 1
    if tipo == "multipoint":
        return len(obj.get("points") or [])
    if tipo == "polyline":
        return sum(len(p) for p in (obj.get("paths") or []))
    if tipo == "polygon":
        return sum(len(r) for r in (obj.get("rings") or []))
    return 0
