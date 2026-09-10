"""Esquema de uma camada hospedada da Esri (`/FeatureServer/{id}?f=json`) -> o que a clonagem precisa para criar a
tabela e o item (item L2-08-b): campos com tipo PostgreSQL, alias, tamanho, nulabilidade e padrão; nome
original -> nome saneado (mesma regra da ingestão); domínios codificados/intervalo e subtipos (`typeIdField`)
no formato que `app.dominios` importa; relacionamentos (cardinalidade, papel, chave); geometria/SRID; anexos;
`editingInfo.lastEditDate` (re-execução incremental). Nada aqui toca banco ou rede."""

from __future__ import annotations

from typing import Any

from app.dominios.esri import TIPO_PG
from app.ingestao import nomes

GEOMETRIA_PG = {
    "esriGeometryPoint": "Point",
    "esriGeometryMultipoint": "MultiPoint",
    "esriGeometryPolyline": "MultiLineString",
    "esriGeometryPolygon": "MultiPolygon",
    "esriGeometryEnvelope": "MultiPolygon",
}
# campos que a Esri mantém e que aqui já existem com outro nome/papel (fid, globalid, rastreio) ou não têm sentido
# (área/comprimento calculados pela Esri sobre a geometria do serviço)
RESERVADOS = {
    "objectid",
    "fid",
    "globalid",
    "shape",
    "shape__area",
    "shape__length",
    "shape.starea()",
    "shape.stlength()",
    "shape_area",
    "shape_length",
    "st_area(shape)",
    "st_length(shape)",
}
CARDINALIDADE = {
    "esriRelCardinalityOneToOne": "1:1",
    "esriRelCardinalityOneToMany": "1:N",
    "esriRelCardinalityManyToMany": "N:M",
}


def _tipo_pg(campo: dict) -> str | None:
    tipo = str(campo.get("type") or "")
    if tipo in (
        "esriFieldTypeOID",
        "esriFieldTypeGlobalID",
        "esriFieldTypeGeometry",
        "esriFieldTypeRaster",
        "esriFieldTypeBlob",
        "esriFieldTypeXML",
    ):
        return None
    if tipo == "esriFieldTypeGUID":
        return "uuid"
    if tipo == "esriFieldTypeDate":
        return "timestamptz"
    if tipo in ("esriFieldTypeDateOnly",):
        return "date"
    if tipo in ("esriFieldTypeTimeOnly",):
        return "time"
    if tipo in ("esriFieldTypeBigInteger",):
        return "bigint"
    return TIPO_PG.get(tipo, "text")


def esquema_de(descritor: dict) -> dict:
    """Descritor Esri -> {nome, tipo_esri, geometria, srid, campos, mapa_nomes, campo_oid, campo_globalid,
    dominios (fields/types prontos para app.dominios), relacionamentos, tem_anexos, edit_date, avisos}."""
    avisos: list[str] = []
    usados: set[str] = set()
    campos: list[dict] = []
    mapa: dict[str, str] = {}
    campo_oid = descritor.get("objectIdField") or next(
        (f["name"] for f in descritor.get("fields") or [] if f.get("type") == "esriFieldTypeOID"), "OBJECTID"
    )
    campo_globalid = descritor.get("globalIdField") or next(
        (f["name"] for f in descritor.get("fields") or [] if f.get("type") == "esriFieldTypeGlobalID"), None
    )
    edit_fields = {str(v).lower() for v in (descritor.get("editFieldsInfo") or {}).values() if v}
    for posicao, f in enumerate(descritor.get("fields") or []):
        nome_orig = str(f.get("name") or "")
        if nome_orig.lower() in RESERVADOS or nome_orig == campo_oid or nome_orig == campo_globalid:
            if nome_orig.lower().startswith("shape"):
                avisos.append(f"campo calculado pela Esri descartado: {nome_orig}")
            continue
        tipo = _tipo_pg(f)
        if tipo is None:
            avisos.append(f"campo sem equivalente descartado: {nome_orig} ({f.get('type')})")
            continue
        nome, motivo = nomes.normalizar(nome_orig, usados, posicao=posicao)
        if nome_orig.lower() in edit_fields:
            nome = "origem_" + nome  # rastreio da Esri vira atributo comum: o nosso criado_em/criado_por é outro
            usados.add(nome)
        if motivo:
            avisos.append(f"campo renomeado: {nome_orig} -> {nome} ({motivo})")
        mapa[nome_orig] = nome
        campos.append(
            {
                "nome": nome,
                "tipo": tipo,
                "alias": f.get("alias") or nome_orig,
                "tamanho": f.get("length") if tipo == "text" else None,
                "nulavel": bool(f.get("nullable", True)),
                "padrao": f.get("defaultValue"),
                "original": nome_orig,
                "tipo_esri": f.get("type"),
            }
        )
    tipo_esri = descritor.get("geometryType")
    geometria = GEOMETRIA_PG.get(tipo_esri or "", None)
    if descritor.get("type") == "Table" or not tipo_esri:
        geometria = None
    if geometria and descritor.get("hasZ"):
        geometria += "Z"
    # a referência do SERVIÇO (extent.spatialReference) é a que `query` devolve; sourceSpatialReference é a do dado
    # de origem no banco da Esri e só vale quando a do serviço não vem
    sr = (descritor.get("extent") or {}).get("spatialReference") or descritor.get("sourceSpatialReference") or {}
    srid = sr.get("latestWkid") or sr.get("wkid") or 4326
    if srid == 102100:
        srid = 3857
    # domínios e subtipos no formato que a rota /api/dominios/importar já entende (campo_subtipo = typeIdField)
    fields_dom = []
    for f in descritor.get("fields") or []:
        if f.get("domain") and f.get("name") in mapa:
            fields_dom.append({"name": mapa[f["name"]], "type": f.get("type"), "domain": f["domain"]})
    types_dom = []
    campo_subtipo = descritor.get("typeIdField")
    tipos = descritor.get("types") or []
    # subtipo da Esri é código INTEIRO (plat.camada_subtipo idem); `types` com id texto são "tipos de feição" sobre um
    # campo de texto — ficam de fora, com aviso, e o domínio do próprio campo continua valendo
    if tipos and not all(isinstance(t.get("id"), int) and not isinstance(t.get("id"), bool) for t in tipos):
        avisos.append(f"tipos de feição com id texto em {campo_subtipo!r} não são subtipos; ignorados")
        tipos = []
    if campo_subtipo and campo_subtipo in mapa:
        for t in tipos:
            dominios = {mapa[c]: d for c, d in (t.get("domains") or {}).items() if c in mapa}
            templates = []
            for tpl in t.get("templates") or []:
                atrs = ((tpl or {}).get("prototype") or {}).get("attributes") or {}
                templates.append({"prototype": {"attributes": {mapa[c]: v for c, v in atrs.items() if c in mapa}}})
            types_dom.append(
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "campo_subtipo": mapa[campo_subtipo],
                    "domains": dominios,
                    "templates": templates,
                }
            )
    relacionamentos = []
    for r in descritor.get("relationships") or []:
        relacionamentos.append(
            {
                "id": r.get("id"),
                "nome": r.get("name"),
                "camada_relacionada": r.get("relatedTableId"),
                "cardinalidade": CARDINALIDADE.get(r.get("cardinality") or "", "1:N"),
                "papel": "origem" if r.get("role") == "esriRelRoleOrigin" else "destino",
                "chave": mapa.get(r.get("keyField") or "", (r.get("keyField") or "").lower() or None),
                "chave_original": r.get("keyField"),
                "composto": bool(r.get("composite")),
            }
        )
    edit_date = (descritor.get("editingInfo") or {}).get("lastEditDate")
    return {
        "nome": descritor.get("name") or f"camada_{descritor.get('id', 0)}",
        "id_origem": descritor.get("id"),
        "tipo_esri": tipo_esri,
        "e_tabela": geometria is None,
        "geometria": geometria,
        "srid": int(srid),
        "campos": campos,
        "mapa_nomes": mapa,
        "campo_oid": campo_oid,
        "campo_globalid": campo_globalid,
        "dominios": {"fields": fields_dom, "types": types_dom},
        "relacionamentos": relacionamentos,
        "tem_anexos": bool(descritor.get("hasAttachments")),
        "edit_date": edit_date,
        "avisos": avisos,
        "e_vista": bool(descritor.get("isView")),
    }


def valor_para_coluna(campo: dict, valor: Any) -> Any:
    """Valor de atributo Esri -> valor da coluna: datas em ms desde a época (podem ser negativas = antes de
    1970) viram ISO UTC; o resto passa como veio (o Postgres confere o tipo)."""
    if valor is None:
        return None
    if campo["tipo"] == "timestamptz" and isinstance(valor, (int, float)) and not isinstance(valor, bool):
        import datetime as dt

        return dt.datetime.fromtimestamp(valor / 1000, dt.UTC).isoformat()
    if campo["tipo"] == "date" and isinstance(valor, (int, float)) and not isinstance(valor, bool):
        import datetime as dt

        return dt.datetime.fromtimestamp(valor / 1000, dt.UTC).date().isoformat()
    if campo["tipo"] == "text" and not isinstance(valor, str):
        return str(valor)
    return valor
