"""Serialização do resultado da operação `query` (item L2-04-c) nos 4 formatos que a doc Esri lista
em `output-formats`: json (padrão), pjson (mesmo corpo, `f=pjson` só pede indentação — decidido pelo
`JSONResponse` do FastAPI, que já não indenta por padrão; tratado como alias de json), geojson
(RFC 7946, sem o vocabulário Esri) e pbf (`FeatureCollectionPBuffer`, `app/consulta/proto`)."""

from __future__ import annotations

import datetime as _dt
import decimal as _dec

from app.consulta import motor
from app.consulta.proto import FeatureCollection_pb2 as fcpb

GEOM_PG_PARA_ESRI = {
    "Point": "esriGeometryPoint",
    "MultiPoint": "esriGeometryMultipoint",
    "LineString": "esriGeometryPolyline",
    "MultiLineString": "esriGeometryPolyline",
    "Polygon": "esriGeometryPolygon",
    "MultiPolygon": "esriGeometryPolygon",
    "Geometry": None,  # camada de geometria mista — sem geometryType único (declarado no L2-04-b)
}

_GEOM_ESRI_PARA_PB = {
    "esriGeometryPoint": fcpb.FeatureCollectionPBuffer.esriGeometryTypePoint,
    "esriGeometryMultipoint": fcpb.FeatureCollectionPBuffer.esriGeometryTypeMultipoint,
    "esriGeometryPolyline": fcpb.FeatureCollectionPBuffer.esriGeometryTypePolyline,
    "esriGeometryPolygon": fcpb.FeatureCollectionPBuffer.esriGeometryTypePolygon,
}
_FIELDTYPE_ESRI_PARA_PB = {
    "esriFieldTypeSmallInteger": fcpb.FeatureCollectionPBuffer.esriFieldTypeSmallInteger,
    "esriFieldTypeInteger": fcpb.FeatureCollectionPBuffer.esriFieldTypeInteger,
    "esriFieldTypeSingle": fcpb.FeatureCollectionPBuffer.esriFieldTypeSingle,
    "esriFieldTypeDouble": fcpb.FeatureCollectionPBuffer.esriFieldTypeDouble,
    "esriFieldTypeString": fcpb.FeatureCollectionPBuffer.esriFieldTypeString,
    "esriFieldTypeDate": fcpb.FeatureCollectionPBuffer.esriFieldTypeDate,
    "esriFieldTypeOID": fcpb.FeatureCollectionPBuffer.esriFieldTypeOID,
    "esriFieldTypeGUID": fcpb.FeatureCollectionPBuffer.esriFieldTypeGUID,
    "esriFieldTypeGlobalID": fcpb.FeatureCollectionPBuffer.esriFieldTypeGlobalID,
    "esriFieldTypeBigInteger": fcpb.FeatureCollectionPBuffer.esriFieldTypeBigInteger,
    "esriFieldTypeDateOnly": fcpb.FeatureCollectionPBuffer.esriFieldTypeDateOnly,
    "esriFieldTypeTimeOnly": fcpb.FeatureCollectionPBuffer.esriFieldTypeTimeOnly,
    "esriFieldTypeBlob": fcpb.FeatureCollectionPBuffer.esriFieldTypeBlob,
}


def _v(x):
    """Data/hora vira epoch em milissegundos — é o formato de atributo `esriFieldTypeDate` no
    protocolo REST Esri (verificado no `output-formats`/`feature-object` da doc), nunca ISO 8601."""
    if isinstance(x, _dt.datetime):
        dt = x if x.tzinfo else x.replace(tzinfo=_dt.timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(x, _dt.date):
        return int(_dt.datetime(x.year, x.month, x.day, tzinfo=_dt.timezone.utc).timestamp() * 1000)
    if isinstance(x, _dec.Decimal):
        # sum()/avg() etc. sobre bigint/numeric voltam Decimal do psycopg2 — vira número JSON de
        # verdade (int quando exato, senão float), nunca string (json.dumps(default=str) faria isso
        # e o cliente Esri esperaria um número em outStatistics)
        return int(x) if x == x.to_integral_value() else float(x)
    return x


def como_json(res) -> dict:
    """Corpo `f=json`/`f=pjson`: vocabulário Esri (attributes/geometry em rings/paths/x,y)."""
    if isinstance(res, motor.ResultadoCount):
        return {"count": res.count}
    if isinstance(res, motor.ResultadoIds):
        return {"objectIdFieldName": res.objectIdFieldName, "objectIds": res.objectIds}
    if isinstance(res, motor.ResultadoExtent):
        corpo = {"extent": res.extent}
        if res.count is not None:
            corpo["count"] = res.count
        return corpo
    corpo = {
        "objectIdFieldName": res.objectIdFieldName,
        "globalIdFieldName": res.globalIdFieldName or "",
        "geometryType": res.geometryType,
        "spatialReference": {"wkid": res.spatialReference},
        "fields": [
            {"name": c["nome"], "type": c["tipo_esri"], "alias": c.get("alias", c["nome"])} for c in res.campos_saida
        ],
        "features": [
            {k: v for k, v in {
                "attributes": {n: _v(v) for n, v in f["attributes"].items()},
                "geometry": f["geometry"],
                "centroid": f["centroid"],
            }.items() if v is not None or k == "attributes"}
            for f in res.features
        ],
        "exceededTransferLimit": res.exceededTransferLimit,
    }
    if res.transform:
        corpo["transform"] = {
            "originPosition": "upperLeft",
            "scale": {"xScale": res.transform.tolerance, "yScale": res.transform.tolerance},
            "translate": {"xTranslate": res.transform.origin_x, "yTranslate": res.transform.origin_y},
        }
    if res.resultPaginationToken:
        corpo["resultPaginationToken"] = res.resultPaginationToken
    if res.extent is not None:
        # `returnEnvelope` (11.4): extensão do CONJUNTO filtrado inteiro, não só da página devolvida
        corpo["extent"] = res.extent
    return corpo


def _esri_geom_para_geojson(g: dict | None, tipo_esri: str | None) -> dict | None:
    if g is None:
        return None
    if "x" in g:
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if "points" in g:
        return {"type": "MultiPoint", "coordinates": g["points"]}
    if "paths" in g:
        paths = g["paths"]
        return {"type": "LineString", "coordinates": paths[0]} if len(paths) == 1 else {
            "type": "MultiLineString", "coordinates": paths}
    if "rings" in g:
        return {"type": "Polygon", "coordinates": g["rings"]}
    return None  # pragma: no cover


def como_geojson(res) -> dict:
    """`f=geojson`: RFC 7946 puro — sem `attributes`/objectIdFieldName Esri; erro se o modo não
    produz feições (count/ids/extent não têm forma GeoJSON — a rota recusa antes de chamar isto)."""
    features = []
    for f in res.features:
        features.append({
            "type": "Feature",
            "id": f["attributes"].get(res.objectIdFieldName) if res.objectIdFieldName else None,
            "geometry": _esri_geom_para_geojson(f["geometry"], res.geometryType),
            "properties": {n: _v(v) for n, v in f["attributes"].items()},
        })
    return {"type": "FeatureCollection", "features": features}


def _pb_valor(v):
        val = fcpb.FeatureCollectionPBuffer.Value()
        if v is None:
            val.null_value = True
        elif isinstance(v, bool):
            val.uint_value = 1 if v else 0
        elif isinstance(v, int):
            if v >= 0:
                val.uint64_value = v
            else:
                val.sint64_value = v
        elif isinstance(v, float):
            val.double_value = v
        elif hasattr(v, "isoformat"):
            val.string_value = v.isoformat()
        else:
            val.string_value = str(v)
        return val


def _pontos_de(g: dict) -> list[tuple[float, float]] | None:
    """Achata qualquer forma esri (point/multipoint/paths/rings) numa lista plana de (x,y) — usada
    tanto para descobrir a extensão (auto-quantização) quanto para gerar `lengths`/`coords`."""
    if "x" in g:
        return [(g["x"], g["y"])]
    if "points" in g:
        return [(p[0], p[1]) for p in g["points"]]
    aneis = g.get("paths") or g.get("rings")
    if aneis is None:
        return None
    pts = []
    for anel in aneis:
        pts.extend((p[0], p[1]) for p in anel)
    return pts


def _quantizador_automatico(res) -> tuple[float, float, float] | None:
    """O schema PBF da Esri (`Geometry.coords` é `sint64`) só aceita coordenada INTEIRA — por isso
    `quantizationParameters` é obrigatório para o Pro (hipótese do item). Quando o cliente pede
    `f=pbf` sem declarar quantização, este motor deriva uma própria a partir da extensão REAL das
    feições devolvidas nesta página: tolerância de 1e-7 unidade de mapa (grau ou metro — ambos cabem
    em `sint64` até ~9,2×10^11 unidades de amplitude) e origem no canto superior esquerdo da página,
    igual ao que `quantizationParameters.mode=view` faria manualmente. Declarado, não escondido: a
    resposta ainda traz `transform` (é o que o cliente PBF usa para desquantizar)."""
    xs, ys = [], []
    for f in res.features:
        for g in (f["geometry"], f["centroid"]):
            if not g:
                continue
            pts = _pontos_de(g)
            if pts:
                xs.extend(p[0] for p in pts)
                ys.extend(p[1] for p in pts)
    if not xs:
        return None
    return min(xs), max(ys), 1e-7


def _pb_geometria(g: dict | None, tipo_esri: str | None, quant):
    """`quant` é `None` quando o pedido já trazia `quantizationParameters` — nesse caso `g["x"]`/
    `g["y"]` JÁ SÃO os inteiros quantizados (o motor quantizou antes de montar a geometria esri) e
    só arredondamos por segurança de tipo; quando `quant` é a tupla `(origin_x, origin_y, tol)` da
    auto-quantização desta função, `g` ainda tem coordenada float e é dividido aqui."""
    if g is None:
        return None
    geo = fcpb.FeatureCollectionPBuffer.Geometry()
    geo.geometryType = _GEOM_ESRI_PARA_PB.get(tipo_esri, fcpb.FeatureCollectionPBuffer.esriGeometryTypePoint)

    if quant is None:
        def _q(x, y):
            return round(x), round(y)
    else:
        origin_x, origin_y, tol = quant

        def _q(x, y):
            return round((x - origin_x) / tol), round((origin_y - y) / tol)

    if "x" in g:
        qx, qy = _q(g["x"], g["y"])
        geo.coords.extend([qx, qy])
        return geo
    aneis = [g["points"]] if "points" in g else (g.get("paths") or g.get("rings"))
    if aneis is None:
        return geo
    for anel in aneis:
        geo.lengths.append(len(anel))
        for pt in anel:
            qx, qy = _q(pt[0], pt[1])
            geo.coords.extend([qx, qy])
    return geo


def como_pbf(res) -> bytes:
    """`f=pbf`: `FeatureCollectionPBuffer` (proto3 oficial do repositório Esri/arcgis-pbf, compilado
    em `app/consulta/proto/FeatureCollection_pb2.py` — a MESMA definição que o item declara)."""
    msg = fcpb.FeatureCollectionPBuffer()
    msg.version = "1.0"
    if isinstance(res, motor.ResultadoCount):
        msg.queryResult.countResult.count = res.count
        return msg.SerializeToString()
    if isinstance(res, motor.ResultadoIds):
        msg.queryResult.idsResult.objectIdFieldName = res.objectIdFieldName
        msg.queryResult.idsResult.objectIds.extend(res.objectIds)
        return msg.SerializeToString()
    if isinstance(res, motor.ResultadoExtent):
        if res.extent:
            e = msg.queryResult.extentCountResult.extent
            e.XMin, e.YMin = res.extent["xmin"], res.extent["ymin"]
            e.XMax, e.YMax = res.extent["xmax"], res.extent["ymax"]
        if res.count is not None:
            msg.queryResult.extentCountResult.count = res.count
        return msg.SerializeToString()
    fr = msg.queryResult.featureResult
    fr.objectIdFieldName = res.objectIdFieldName or ""
    if res.globalIdFieldName:
        fr.globalIdFieldName = res.globalIdFieldName
    if res.geometryType:
        fr.geometryType = _GEOM_ESRI_PARA_PB.get(res.geometryType, fcpb.FeatureCollectionPBuffer.esriGeometryTypeNone)
    fr.spatialReference.wkid = res.spatialReference
    fr.exceededTransferLimit = res.exceededTransferLimit
    fr.hasZ = res.hasZ
    fr.hasM = res.hasM

    # `Geometry.coords` do proto é `sint64`: só aceita inteiro. Se o pedido já trazia
    # `quantizationParameters`, a geometria em `res.features` já está quantizada (motor.py) e
    # `quant=None` diz a `_pb_geometria` para só arredondar; senão, deriva e declara uma própria.
    if res.transform:
        quant = None
        t = fr.transform
        t.quantizeOriginPostion = fcpb.FeatureCollectionPBuffer.upperLeft
        t.scale.xScale = t.scale.yScale = res.transform.tolerance
        t.translate.xTranslate = res.transform.origin_x
        t.translate.yTranslate = res.transform.origin_y
    else:
        auto = _quantizador_automatico(res)
        quant = auto
        if auto:
            origin_x, origin_y, tol = auto
            t = fr.transform
            t.quantizeOriginPostion = fcpb.FeatureCollectionPBuffer.upperLeft
            t.scale.xScale = t.scale.yScale = tol
            t.translate.xTranslate = origin_x
            t.translate.yTranslate = origin_y

    nomes_campo = [c["nome"] for c in res.campos_saida]
    for c in res.campos_saida:
        campo_pb = fr.fields.add()
        campo_pb.name = c["nome"]
        campo_pb.fieldType = _FIELDTYPE_ESRI_PARA_PB.get(
            c["tipo_esri"], fcpb.FeatureCollectionPBuffer.esriFieldTypeString
        )
        campo_pb.alias = c.get("alias", c["nome"])
    for f in res.features:
        feat = fr.features.add()
        for nome in nomes_campo:
            feat.attributes.append(_pb_valor(f["attributes"].get(nome)))
        if f["geometry"] is not None:
            g = _pb_geometria(f["geometry"], res.geometryType, quant)
            if g is not None:
                feat.geometry.CopyFrom(g)
        if f["centroid"] is not None:
            c = _pb_geometria(f["centroid"], "esriGeometryPoint", quant)
            if c is not None:
                feat.centroid.CopyFrom(c)
    return msg.SerializeToString()
