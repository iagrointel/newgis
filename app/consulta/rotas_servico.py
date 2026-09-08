"""Diretório e metadados do FeatureServer (item L2-04-servicos-esri-ogc, que fecha ao redor da operação
`query` já construída no item L2-04-c/ADR 0018 — REUSADA aqui sem reescrita: `campos_da_camada`,
`GEOM_PG_PARA_ESRI`, `_autenticar` do mesmo módulo `app.consulta.rotas_query`).

Cobre a parte "o cliente descobre o serviço" que faltava para o FeatureServer ser navegável por
ArcGIS Pro/QGIS/AGOL sem a URL exata da camada de antemão: o descritor do serviço (`.../FeatureServer
?f=json`, com `layers`/`tables`/`fullExtent`/`spatialReference`/`capabilities`) e o descritor da
camada (`.../FeatureServer/0?f=json`, com `fields`/`geometryType`/`drawingInfo`/`capabilities`).

Esta implementação publica UMA camada por item (id fixo "0"), mesma restrição já declarada em
`rotas_query._query`; por isso `layers` tem sempre 0 ou 1 elemento e `tables` é sempre vazio (a
plataforma não tem, ainda, o conceito de tabela sem geometria publicada por este caminho — registrado
como fora em docs/PARIDADE.md).

`applyEdits`, `attachments`, `queryRelatedRecords` e `relationships` dependem do item L2-03-edicao
(escrita transacional) e do L2-10-b (relacionamentos), NENHUM dos dois construído ainda — por isso
`capabilities` nunca anuncia "Create,Update,Delete,Uploads,Editing" e a lista de `relationships` da
camada é sempre `[]`, nunca inventada. Ver `docs/PARIDADE.md` para a linha viva."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import db
from app.catalogo.tipos import TIPOS_CAMADA
from app.consulta import campos as campos_mod
from app.consulta import renderizador
from app.consulta.rotas_query import PREFIXO as PREFIXO_CAMADA
from app.consulta.rotas_query import _autenticar, _item_id_valido
from app.consulta.serializar import GEOM_PG_PARA_ESRI
from app.erros import ErroAPI

router = APIRouter(tags=["consulta-esri"])
PREFIXO_SERVICO = "/rest/services/{item_id}/FeatureServer"
CURRENT_VERSION = 11.4  # 11.4 é o que a query já entrega (fullText, returnEnvelope, DateOnly/TimeOnly/BigInteger)


def _camada_e_titulo(cur, item_id: str) -> tuple[dict, str]:
    """Igual a `rotas_query._camada_do_item`, mas também traz `titulo` — que vive na coluna
    `plat.item.titulo`, não dentro de `dados` (conferido em `app/ingestao/carregar.py`). Valida o
    formato de `item_id` ANTES do banco (mesmo achado/conserto do adversário em `rotas_query.py`)."""
    _item_id_valido(item_id)
    cur.execute(
        "SELECT dados, titulo FROM plat.item WHERE id = %s::uuid AND tipo = ANY(%s)",
        (item_id, list(TIPOS_CAMADA)),
    )
    r = cur.fetchone()
    if r is None or not (r["dados"] or {}).get("tabela"):  # ver rotas_query._camada_do_item (item L5-32)
        raise ErroAPI(404, "camada_nao_encontrada", "item inexistente, não é camada vetorial, ou sem permissão")
    return r["dados"], r["titulo"]


def _extent_nativo(cur, schema: str, tabela: str, srid: int) -> dict | None:
    """`fullExtent` na referência espacial NATIVA da camada (C11 do L2_CONCEITO: SRID nunca convertido
    na ingestão). `ST_Extent` sozinho, sem filtro: custo aceitável para um descritor chamado raramente
    (não está no caminho de `query`/tile); tabela vazia devolve None, nunca um envelope inventado."""
    cur.execute(f'SELECT ST_Extent("geom") AS caixa FROM "{schema}"."{tabela}"')  # noqa: S608 — schema/tabela vêm de plat.item, nunca do cliente
    r = cur.fetchone()
    caixa = r["caixa"] if r else None
    if not caixa:
        return None
    # formato "BOX(xmin ymin,xmax ymax)"
    miolo = caixa[4:-1] if caixa.startswith("BOX(") else caixa
    (xmin, ymin), (xmax, ymax) = (
        tuple(float(v) for v in par.split()) for par in miolo.split(",")
    )
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "spatialReference": {"wkid": srid}}


def _indices(cur, schema: str, tabela: str, nomes: set[str]) -> list[dict]:
    """`indexes` do descritor lidos de `pg_index` — índice de verdade da tabela, não lista decorativa.
    Só entram os índices de UMA coluna cujo nome de coluna é campo publicado (é o que o cliente Esri
    usa para saber se `orderByFields`/`where` naquele campo é barato); o índice espacial entra como
    o índice de `geom`, que a Esri chama pelo nome do campo de forma (`Shape`)."""
    cur.execute(
        "SELECT c.relname AS nome, i.indisunique AS unico, "
        "       array_agg(a.attname ORDER BY k.ord) AS colunas "
        "FROM pg_index i "
        "JOIN pg_class c ON c.oid = i.indexrelid "
        "JOIN pg_class t ON t.oid = i.indrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(att, ord) ON true "
        "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.att "
        "WHERE n.nspname = %s AND t.relname = %s "
        "GROUP BY c.relname, i.indisunique",
        (schema, tabela),
    )
    saida = []
    for r in cur.fetchall():
        colunas = [c for c in r["colunas"] if c]
        if len(colunas) != 1:
            continue
        coluna = colunas[0]
        if coluna != "geom" and coluna not in nomes:
            continue
        saida.append({
            "name": r["nome"],
            "fields": coluna,
            "isAscending": True,
            "isUnique": bool(r["unico"]),
            "description": "índice espacial" if coluna == "geom" else "",
        })
    return sorted(saida, key=lambda d: d["name"])


def _edit_fields_info(meta: list[dict]) -> dict | None:
    """`editFieldsInfo` só existe se as colunas de autoria existirem de fato na tabela (é o que a
    `plat.camada_preparar` cria); tabela sem elas devolve None, nunca um bloco com nome de coluna
    inventado — o Pro tentaria ler a coluna e falharia."""
    nomes = {c["nome"] for c in meta if c["papel"] == "editField"}
    if not nomes:
        return None
    d = {}
    for chave, coluna in (("creationDateField", "criado_em"), ("editDateField", "atualizado_em"),
                          ("creatorField", "criado_por"), ("editorField", "atualizado_por")):
        if coluna in nomes:
            d[chave] = coluna
    return d or None


def _campo_json(c: dict) -> dict:
    d = {
        "name": c["nome"],
        "type": c["tipo_esri"],
        "alias": c["nome"],
        "nullable": c["nullable"],
        "editable": c["papel"] not in ("oid", "globalid"),
        "defaultValue": None,
        # sem a linha L2-10-a (domínios e subtipos) nesta base, nenhum campo tem domínio declarado;
        # `null` é o que a Esri lê como "campo sem domínio", e é a verdade aqui
        "domain": None,
    }
    if c["comprimento"]:
        d["length"] = c["comprimento"]
    if c["papel"] == "globalid":
        d["sqlType"] = "sqlTypeOther"
    return d


def _estilo_da_camada(cur, item_id: str) -> dict | None:
    """Estilo MapLibre ligado à camada pela relação `estilo_de_camada` (item de tipo `estilo`,
    `dados.corpo`). Sem estilo declarado devolve None, e o `drawingInfo` sai no cinza padrão — o
    cliente Esri desenha, e o JSON diz que não houve conversão."""
    cur.execute(
        "SELECT e.dados FROM plat.item_relacao r JOIN plat.item e ON e.id = r.origem "
        "WHERE r.destino = %s::uuid AND r.tipo = 'estilo_de_camada' AND e.tipo = 'estilo' "
        "AND e.apagado_em IS NULL ORDER BY r.criado_em LIMIT 1",
        (item_id,),
    )
    r = cur.fetchone()
    return (r["dados"] or {}).get("corpo") if r else None


def descritor_da_camada(cur, item_id: str, dados: dict, titulo: str | None) -> dict:
    """Descritor completo de `.../FeatureServer/0`. Público no módulo porque o diretório por token
    (item L2-04-b, `app/consulta/rotas_diretorio.py`) monta `/layers` com ele — a mesma função,
    nunca uma segunda cópia que envelhece sozinha."""
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    meta = campos_mod.campos_da_camada(cur, schema, tabela)
    geom_pg = dados.get("geometria")
    tipo_esri = GEOM_PG_PARA_ESRI.get(geom_pg)
    oid_campo = next((c["nome"] for c in meta if c["papel"] == "oid"), "fid")
    globalid_campo = next((c["nome"] for c in meta if c["papel"] == "globalid"), None)
    nomes = {c["nome"] for c in meta}
    return {
        "currentVersion": CURRENT_VERSION,
        "id": 0,
        "name": titulo or item_id,
        "type": "Feature Layer",
        "description": "",
        "geometryType": tipo_esri,
        "sourceSpatialReference": {"wkid": srid},
        "extent": _extent_nativo(cur, schema, tabela, srid),
        "objectIdField": oid_campo,
        "globalIdField": globalid_campo or "",
        "displayField": next((c["nome"] for c in meta if c["papel"] == "atributo"), oid_campo),
        "fields": [_campo_json(c) for c in meta],
        # sem L2-03-a/L2-10-b: nunca anunciar Create/Update/Delete/Uploads (P2 — anúncio sem
        # mecanismo é o mesmo defeito que um botão que não faz nada)
        "capabilities": "Query",
        "supportedQueryFormats": "JSON,geoJSON,PBF",
        "hasAttachments": False,
        "hasStaticData": False,
        "isDataVersioned": False,
        "syncCanReturnChanges": False,
        "relationships": [],
        # subtipos são a linha L2-10-a; typeIdField vazio e types vazio é exatamente como a Esri
        # descreve uma camada SEM subtipo, e é o estado real desta base
        "typeIdField": "",
        "types": [],
        "subtypes": [],
        "timeInfo": None,
        "ownershipBasedAccessControlForFeatures": None,
        "editFieldsInfo": _edit_fields_info(meta),
        "indexes": _indices(cur, schema, tabela, nomes),
        "advancedQueryCapabilities": {
            "supportsPagination": True,
            "supportsStatistics": True,
            "supportsDistinct": True,
            "supportsOrderBy": True,
            "supportsQueryWithDistance": True,
            "supportsReturningQueryExtent": True,
            "supportsSqlExpression": False,
            "supportsHavingClause": True,
        },
        "maxRecordCount": 2000,
        "standardMaxRecordCount": 2000,
        "tileMaxRecordCount": 2000,
        "supportsCoordinatesQuantization": True,
        "drawingInfo": renderizador.para_drawing_info(_estilo_da_camada(cur, item_id)),
    }




def descritor_do_servico(cur, item_id: str) -> dict:
    """Raiz do FeatureServer. Uma camada por item (ver docstring do módulo), então `layers` tem 0 ou
    1 elemento e `tables` é sempre vazio."""
    dados, titulo = _camada_e_titulo(cur, item_id)
    camada = descritor_da_camada(cur, item_id, dados, titulo)
    return {
        "currentVersion": CURRENT_VERSION,
        "serviceDescription": titulo or "",
        "serviceItemId": item_id,
        "hasVersionedData": False,
        "supportsDisconnectedEditing": False,
        "syncEnabled": False,
        "hasStaticData": False,
        "maxRecordCount": 2000,
        "supportedQueryFormats": "JSON,geoJSON,PBF",
        "capabilities": "Query",
        "description": "",
        "copyrightText": "",
        "spatialReference": camada["sourceSpatialReference"],
        "initialExtent": camada["extent"],
        "fullExtent": camada["extent"],
        "allowGeometryUpdates": False,
        "units": "esriDecimalDegrees" if int(dados["srid"]) == 4326 else "esriMeters",
        "layers": [{"id": 0, "name": camada["name"], "parentLayerId": -1, "defaultVisibility": True,
                    "subLayerIds": None, "minScale": 0, "maxScale": 0, "type": "Feature Layer",
                    "geometryType": camada["geometryType"]}],
        "tables": [],
        "relationships": [],
    }


@router.get(PREFIXO_SERVICO, openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="consulta_esri_servico_descritor")
def descritor_servico(item_id: str, request: Request):
    """`.../FeatureServer?f=json` — raiz do diretório. `f` diferente de json/pjson não é servido aqui
    (html é a UI da Esri, servida pelo diretório por token do item L2-04-b)."""
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        return descritor_do_servico(cur, item_id)


@router.get(f"{PREFIXO_CAMADA}", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="consulta_esri_camada_descritor")
def descritor_camada(item_id: str, camada_id: str, request: Request):
    """`.../FeatureServer/0?f=json` — descritor da camada. `camada_id` diferente de "0" cai no mesmo
    404 já usado pela `query` (uma camada publicada por item, ver docstring do módulo)."""
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        return _camada_por_id(cur, item_id, camada_id)


def _camada_por_id(cur, item_id: str, camada_id: str) -> dict:
    if camada_id != "0":
        raise ErroAPI(404, "camada_nao_encontrada", "esta implementação publica uma camada só (id 0) por item")
    dados, titulo = _camada_e_titulo(cur, item_id)
    return descritor_da_camada(cur, item_id, dados, titulo)


# ------------------------------------------------------------------ usado pelo diretório por token
def montar_descritor_servico(auth, item_id: str) -> dict:
    with db.db(auth.contexto()) as cur:
        return descritor_do_servico(cur, item_id)


def montar_descritor_camada(auth, item_id: str, camada_id: str) -> dict:
    with db.db(auth.contexto()) as cur:
        return _camada_por_id(cur, item_id, camada_id)


def montar_layers(auth, item_id: str) -> dict:
    with db.db(auth.contexto()) as cur:
        dados, titulo = _camada_e_titulo(cur, item_id)
        return {"layers": [descritor_da_camada(cur, item_id, dados, titulo)], "tables": []}


def montar_item_info(auth, item_id: str) -> dict:
    """`/info/itemInfo` — a ficha do item como o portal a devolve. Vem do catálogo (`plat.item`),
    que é onde o metadado da casa mora; nada é copiado para um segundo lugar."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT titulo, resumo, descricao, tags, creditos, termos_de_uso, acesso "
            "FROM plat.item WHERE id = %s::uuid AND tipo = ANY(%s)", (item_id, list(TIPOS_CAMADA)))
        r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "camada_nao_encontrada", "item inexistente, não é camada vetorial, ou sem permissão")
    return {
        "id": item_id,
        "title": r["titulo"],
        "snippet": r["resumo"] or "",
        "description": r["descricao"] or "",
        "tags": list(r["tags"] or []),
        "accessInformation": r["creditos"] or "",
        "licenseInfo": r["termos_de_uso"] or "",
        "access": "public" if r["acesso"] == "publico" else "private",
        "type": "Feature Service",
        "culture": "pt-br",
    }


def montar_metadata_iso(auth, item_id: str) -> str:
    """`/info/metadata` no perfil ISO 19139 mínimo (título, resumo, palavras-chave, restrição de
    uso). É o que o ArcGIS Pro e o QGIS leem neste caminho; XML, não JSON."""
    from xml.sax.saxutils import escape

    ficha = montar_item_info(auth, item_id)
    chaves = "".join(
        f"<gmd:keyword><gco:CharacterString>{escape(t)}</gco:CharacterString></gmd:keyword>"
        for t in ficha["tags"]
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd" '
        'xmlns:gco="http://www.isotc211.org/2005/gco">'
        f"<gmd:fileIdentifier><gco:CharacterString>{escape(item_id)}</gco:CharacterString>"
        "</gmd:fileIdentifier>"
        "<gmd:identificationInfo><gmd:MD_DataIdentification><gmd:citation><gmd:CI_Citation>"
        f"<gmd:title><gco:CharacterString>{escape(ficha['title'])}</gco:CharacterString></gmd:title>"
        "</gmd:CI_Citation></gmd:citation>"
        f"<gmd:abstract><gco:CharacterString>{escape(ficha['snippet'])}</gco:CharacterString></gmd:abstract>"
        f"<gmd:descriptiveKeywords><gmd:MD_Keywords>{chaves}</gmd:MD_Keywords></gmd:descriptiveKeywords>"
        "<gmd:resourceConstraints><gmd:MD_LegalConstraints><gmd:useLimitation>"
        f"<gco:CharacterString>{escape(ficha['licenseInfo'])}</gco:CharacterString>"
        "</gmd:useLimitation></gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        "</gmd:MD_DataIdentification></gmd:identificationInfo></gmd:MD_Metadata>"
    )
