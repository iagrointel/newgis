"""MapServer compatível com Esri, sob o diretório de serviços por token (item L2-04-f).

Rotas, todas abaixo de `/svc/{token}/rest/services/{item_id}/MapServer`, onde `item_id` é um item de
tipo `mapa` do catálogo (ver `app/consulta/mapserver.py` para o porquê de o serviço ser o MAPA):

    (raiz)          descritor do serviço: layers, spatialReference, initialExtent, capabilities
    /layers         descritores completos de todas as camadas, de uma vez
    /{id}           descritor de UMA camada — o mesmo do FeatureServer, sem segunda cópia
    /legend         uma amostra PNG por classe do estilo (f=json com imageData, ou f=image)
    /export         imagem desenhada no servidor (bbox, size, dpi, format, layers, layerDefs, ...)
    /identify       feições sob um ponto/geometria, com tolerância em PIXELS
    /find           feições cujo texto casa com searchText
    /generateKml    o mesmo conteúdo em KML, para o Google Earth

Quem publica é o diretório do item L2-04-b: a credencial é o token do CAMINHO, a segregação é a RLS
do banco, e este módulo não reimplementa nem uma nem outra — chama `rotas_diretorio._auth_do_caminho`.

Referência: developers.arcgis.com, "Map service", "Export map", "Identify (map service)",
"Legend (map service)", "Find" (acesso em 2026-09-08)."""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Request, Response

from app import db, limites
from app.consulta import campos as campos_mod
from app.consulta import mapserver, rotas_diretorio, rotas_servico
from app.consulta.formato_esri import resposta_esri, resposta_imagem
from app.erros import ErroAPI
from app.tiles.exportacao import _kml_texto

router = APIRouter(tags=["consulta-esri"])
MAPSERVER = f"{rotas_diretorio.SERVICOS}/{{item_id}}/MapServer"
LER = rotas_diretorio.LER
CURRENT_VERSION = rotas_servico.CURRENT_VERSION
CAPACIDADES = "Map,Query,Data"
# unidade do serviço pela referência espacial de exibição do documento (mesma regra do FeatureServer)
UNIDADE = {4326: "esriDecimalDegrees"}


async def _parametros(request: Request) -> dict:
    """Querystring e, no POST, o corpo do cliente Esri (urlencoded ou JSON) — mesma leitura que a
    operação `query` faz (`rotas_query._parametros`), repetida aqui só porque o corpo do POST do
    export chega com `layerDefs` como objeto JSON aninhado, que vira texto para o mesmo analisador."""
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


def _f(p: dict) -> tuple[str | None, str | None]:
    return p.get("f"), p.get("callback")


def _abrir(request: Request, token: str):
    """Autentica pelo token do CAMINHO (a credencial do diretório do item L2-04-b). O que o mapa
    mostra depois é decidido pela RLS, não por filtro aqui."""
    return rotas_diretorio._auth_do_caminho(request, token)  # noqa: SLF001 — mesma família


def _extensao_do_mapa(mapa: dict) -> dict:
    """Extensão inicial declarada no documento; sem ela, o mundo em WGS 84 reprojetado é enganoso, e
    por isso a resposta traz a extensão do DOCUMENTO ou nada — nunca uma caixa inventada."""
    corpo = ((mapa.get("dados") or {}).get("corpo")) or {}
    ext = corpo.get("extensao_inicial")
    if isinstance(ext, dict) and all(k in ext for k in ("oeste", "sul", "leste", "norte")):
        return {"xmin": ext["oeste"], "ymin": ext["sul"], "xmax": ext["leste"], "ymax": ext["norte"],
                "spatialReference": {"wkid": 4326, "latestWkid": 4326}}
    if isinstance(ext, (list, tuple)) and len(ext) == 4:
        return {"xmin": ext[0], "ymin": ext[1], "xmax": ext[2], "ymax": ext[3],
                "spatialReference": {"wkid": 4326, "latestWkid": 4326}}
    return {"xmin": -180.0, "ymin": -90.0, "xmax": 180.0, "ymax": 90.0,
            "spatialReference": {"wkid": 4326, "latestWkid": 4326}}


def _srid_exibicao(mapa: dict) -> int:
    corpo = ((mapa.get("dados") or {}).get("corpo")) or {}
    try:
        return int(corpo.get("crs_exibicao") or 3857)
    except (TypeError, ValueError):
        return 3857


def _descritor_de_camada(cur, camada: dict) -> dict:
    """O descritor da camada é o MESMO do FeatureServer (`rotas_servico.descritor_da_camada`), com o
    identificador e o nome trocados pelos do documento de mapa — a cláusula "mesmos metadados do
    FeatureServer" do item é literal: uma função só, nunca uma segunda cópia que envelhece."""
    dados = {"schema": camada["schema"], "tabela": camada["tabela"], "srid": camada["srid"],
             "geometria": camada["geometria"]}
    d = rotas_servico.descritor_da_camada(cur, camada["ref"], dados, camada["nome"])
    d["id"] = camada["id"]
    d["name"] = camada["nome"]
    d["defaultVisibility"] = camada["visivel"]
    d["parentLayerId"] = -1
    d["subLayerIds"] = None
    d["drawingInfo"] = camada["drawing_info"]
    return d


# ------------------------------------------------------------------ descritores
@router.get(MAPSERVER, openapi_extra=LER, operation_id="svc_mapserver_raiz")
def mapserver_raiz(token: str, item_id: str, request: Request):
    auth = _abrir(request, token)
    f, cb = _f(dict(request.query_params))
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        camadas = mapserver.camadas_do_mapa(cur, mapa)
    srid = _srid_exibicao(mapa)
    extensao = _extensao_do_mapa(mapa)
    return resposta_esri({
        "currentVersion": CURRENT_VERSION,
        "serviceDescription": mapa["resumo"] or "",
        "mapName": mapa["titulo"] or item_id,
        "description": "",
        "copyrightText": "",
        "supportsDynamicLayers": False,
        "layers": [{"id": c["id"], "name": c["nome"], "parentLayerId": -1, "defaultVisibility": c["visivel"],
                    "subLayerIds": None, "minScale": 0, "maxScale": 0, "type": "Feature Layer"}
                   for c in camadas],
        "tables": [],
        "spatialReference": {"wkid": srid, "latestWkid": srid},
        "singleFusedMapCache": False,
        "initialExtent": extensao,
        "fullExtent": extensao,
        "units": UNIDADE.get(srid, "esriMeters"),
        "supportedImageFormatTypes": ",".join(sorted(mapserver.FORMATOS_IMAGEM)).upper(),
        "documentInfo": {"Title": mapa["titulo"] or "", "Author": "", "Comments": "", "Subject": "",
                         "Category": "", "Keywords": "", "AntialiasingMode": "None", "TextAntialiasingMode": "Force"},
        "capabilities": CAPACIDADES,
        "maxRecordCount": 2000,
        "maxImageHeight": limites.MAPSERVER_LADO_MAX,
        "maxImageWidth": limites.MAPSERVER_LADO_MAX,
        "supportedQueryFormats": "JSON",
        "exportTilesAllowed": False,
    }, f, cb)


@router.get(f"{MAPSERVER}/layers", openapi_extra=LER, operation_id="svc_mapserver_layers")
def mapserver_layers(token: str, item_id: str, request: Request):
    auth = _abrir(request, token)
    f, cb = _f(dict(request.query_params))
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        camadas = mapserver.camadas_do_mapa(cur, mapa)
        corpo = {"layers": [_descritor_de_camada(cur, c) for c in camadas], "tables": []}
    return resposta_esri(corpo, f, cb)


# ------------------------------------------------------------------ legenda
@router.get(f"{MAPSERVER}/legend", openapi_extra=LER, operation_id="svc_mapserver_legend")
def mapserver_legend(token: str, item_id: str, request: Request):
    """Uma entrada por CLASSE do estilo, com a amostra em PNG (`imageData`, base64). `f=image`
    devolve a amostra da primeira classe da primeira camada, que é como o ArcGIS Server responde a
    um pedido de imagem única na legenda."""
    p = dict(request.query_params)
    auth = _abrir(request, token)
    f, cb = _f(p)
    from app.consulta.formato_esri import formato_de

    formato = formato_de(f, extras=("image",))
    dpi = mapserver.dpi_do_pedido(p.get("dpi"))
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        camadas = mapserver.camadas_do_mapa(cur, mapa)
    saida = []
    for c in camadas:
        entradas = []
        for classe in mapserver.classes(c["drawing_info"]):
            png = mapserver.amostra_de_legenda(classe["symbol"], c["geometria"], dpi)
            entradas.append({
                "label": classe["label"],
                "url": "",
                "imageData": base64.b64encode(png).decode("ascii"),
                "contentType": "image/png",
                "height": mapserver.LEGENDA_LADO,
                "width": mapserver.LEGENDA_LADO,
                "values": [classe["valor"]] if classe["valor"] is not None else [],
            })
        saida.append({"layerId": c["id"], "layerName": c["nome"], "layerType": "Feature Layer",
                      "minScale": 0, "maxScale": 0, "legend": entradas})
    if formato == "image":
        if not saida or not saida[0]["legend"]:
            raise ErroAPI(404, "legenda_vazia", "mapa sem camada legível para gerar amostra")
        return resposta_imagem(base64.b64decode(saida[0]["legend"][0]["imageData"]), "image/png")
    return resposta_esri({"layers": saida}, f, cb)


# ------------------------------------------------------------------ export
def _formato_de_imagem(valor: str | None) -> str:
    nome = (valor or "png").strip().lower()
    if nome not in mapserver.FORMATOS_IMAGEM:
        raise ErroAPI(400, "format_nao_suportado",
                      f"format={nome} não é suportado; use {', '.join(sorted(mapserver.FORMATOS_IMAGEM))}")
    return nome


def _bool(valor, padrao=False) -> bool:
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("true", "1", "yes", "sim")


async def _export(request: Request, token: str, item_id: str) -> Response:
    p = await _parametros(request)
    auth = _abrir(request, token)
    from app.consulta.formato_esri import formato_de

    formato_saida = formato_de(p.get("f"), extras=("image",))
    formato_img = _formato_de_imagem(p.get("format"))
    largura, altura = mapserver.tamanho_do_pedido(p.get("size"))
    dpi = mapserver.dpi_do_pedido(p.get("dpi"))
    transparente = _bool(p.get("transparent"))
    if p.get("time"):
        raise ErroAPI(422, "time_fora",
                      "nenhuma camada deste mapa declara timeInfo; o filtro temporal não tem sobre o que agir")
    defs = mapserver.defs_por_camada(p.get("layerDefs"))
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        todas = mapserver.camadas_do_mapa(cur, mapa)
        srid_saida = _sr_pedido(p.get("imageSR")) or _sr_pedido(p.get("bboxSR")) or _srid_exibicao(mapa)
        bbox = mapserver.bbox_do_pedido(p.get("bbox") or _bbox_padrao(mapa, srid_saida))
        escolhidas = mapserver.selecao_de_camadas(todas, p.get("layers"))
        if len(escolhidas) > limites.MAPSERVER_CAMADAS_MAX:
            raise ErroAPI(400, "camadas_demais",
                          f"pedido com {len(escolhidas)} camadas (teto {limites.MAPSERVER_CAMADAS_MAX})")
        desconhecidas = sorted(set(defs) - {c["id"] for c in todas})
        if desconhecidas:
            raise ErroAPI(400, "layerdefs_invalido", f"layerDefs aponta camada inexistente: {desconhecidas}")
        tela = mapserver.Tela(bbox, largura, altura)
        pacotes = []
        for c in escolhidas:
            feicoes = mapserver.feicoes_para_desenho(
                cur, c, tela, srid_saida, defs.get(c["id"]), limites.MAPSERVER_FEICOES_POR_CAMADA)
            pacotes.append((c, feicoes))
    imagem = mapserver.desenhar(pacotes, tela, dpi, transparente)
    dados, tipo_conteudo = mapserver.bytes_da_imagem(imagem, formato_img)
    if formato_saida == "image":
        return resposta_imagem(dados, tipo_conteudo)
    return resposta_esri({
        "href": str(request.url.include_query_params(f="image")),
        "width": largura,
        "height": altura,
        "extent": {"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
                   "spatialReference": {"wkid": srid_saida, "latestWkid": srid_saida}},
        "scale": 0,
        "contentType": tipo_conteudo,
        "imageData": base64.b64encode(dados).decode("ascii"),
    }, p.get("f") if p.get("f") != "image" else None, p.get("callback"))


def _bbox_padrao(mapa: dict, srid: int) -> str:
    if srid == 4326:
        ext = _extensao_do_mapa(mapa)
        return f"{ext['xmin']},{ext['ymin']},{ext['xmax']},{ext['ymax']}"
    raise ErroAPI(400, "bbox_ausente", "bbox é obrigatório: informe 'xmin,ymin,xmax,ymax'")


def _sr_pedido(valor) -> int | None:
    from app.consulta.geometria_esri import sr_wkid

    return sr_wkid(valor) if valor not in (None, "") else None


@router.get(f"{MAPSERVER}/export", openapi_extra=LER, operation_id="svc_mapserver_export_get")
async def mapserver_export_get(token: str, item_id: str, request: Request):
    return await _export(request, token, item_id)


@router.post(f"{MAPSERVER}/export", openapi_extra=LER, operation_id="svc_mapserver_export_post")
async def mapserver_export_post(token: str, item_id: str, request: Request):
    return await _export(request, token, item_id)


# ------------------------------------------------------------------ identify e find
def _camadas_do_identify(camadas: list[dict], layers: str | None) -> list[dict]:
    """`layers` do identify: `top`, `visible`, `all` — sozinhos ou com `:0,1` na frente."""
    bruto = (layers or "top").strip()
    modo, _, lista = bruto.partition(":")
    modo = modo.strip().lower()
    if modo not in ("top", "visible", "all"):
        raise ErroAPI(400, "layers_invalido", "layers do identify é 'top', 'visible' ou 'all' (com ':0,1' opcional)")
    escolhidas = camadas
    if lista.strip():
        ids = set()
        for parte in lista.split(","):
            parte = parte.strip()
            if parte == "":
                continue
            if not parte.isdigit():
                raise ErroAPI(400, "layers_invalido", "identificador de camada precisa ser inteiro")
            ids.add(int(parte))
        escolhidas = [c for c in camadas if c["id"] in ids]
    if modo == "visible":
        escolhidas = [c for c in escolhidas if c["visivel"]]
    elif modo == "top":
        visiveis = [c for c in escolhidas if c["visivel"]]
        escolhidas = visiveis[:1]
    return escolhidas


def _tolerancia_em_unidades(p: dict) -> tuple[float, tuple[float, float, float, float] | None]:
    """A tolerância do identify vem em PIXELS; vira unidade de mapa pela razão entre a largura da
    extensão exibida (`mapExtent`) e a largura da tela (`imageDisplay`). Tolerância 0 é legítima e
    significa "o que a geometria toca de verdade" — nunca vira divisão por zero aqui."""
    try:
        tolerancia_px = float(p.get("tolerance") or 0)
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "tolerance_invalida", "tolerance precisa ser número de pixels") from e
    if tolerancia_px < 0:
        raise ErroAPI(400, "tolerance_invalida", "tolerance não pode ser negativa")
    if tolerancia_px == 0:
        return 0.0, None
    extensao = p.get("mapExtent")
    display = p.get("imageDisplay")
    if not extensao or not display:
        raise ErroAPI(400, "identify_sem_tela",
                      "tolerance > 0 exige mapExtent e imageDisplay (a tolerância é medida em pixels)")
    bbox = mapserver.bbox_do_pedido(extensao)
    partes = str(display).split(",")
    if len(partes) < 2:
        raise ErroAPI(400, "imagedisplay_invalido", "imageDisplay precisa ser 'largura,altura,dpi'")
    try:
        largura_px = float(partes[0])
    except ValueError as e:
        raise ErroAPI(400, "imagedisplay_invalido", "imageDisplay precisa começar com a largura em pixels") from e
    if largura_px <= 0:
        raise ErroAPI(400, "imagedisplay_invalido", "largura de imageDisplay precisa ser positiva")
    return tolerancia_px * (bbox[2] - bbox[0]) / largura_px, bbox


async def _identify(request: Request, token: str, item_id: str) -> Response:
    from app.consulta import geometria_esri as geo

    p = await _parametros(request)
    auth = _abrir(request, token)
    f, cb = _f(p)
    if not p.get("geometry"):
        raise ErroAPI(400, "geometria_ausente", "identify exige geometry")
    obj, tipo = geo.parse_geometry(p["geometry"], p.get("geometryType") or "esriGeometryPoint")
    n_vert = geo.contar_vertices(obj, tipo)
    if n_vert > geo.MAX_VERTICES:
        raise ErroAPI(413, "geometria_grande_demais", f"geometria com {n_vert} vértices (teto {geo.MAX_VERTICES})")
    tolerancia, _ = _tolerancia_em_unidades(p)
    sr_entrada = geo.sr_wkid(p.get("sr")) or geo.sr_wkid(p.get("inSR"))
    devolver_geometria = _bool(p.get("returnGeometry"), True)
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        todas = mapserver.camadas_do_mapa(cur, mapa)
        sr_entrada = sr_entrada or _srid_exibicao(mapa)
        wkt = geo.para_ewkt(obj, tipo, sr_entrada)
        resultados = []
        for c in _camadas_do_identify(todas, p.get("layers")):
            resultados += _feicoes_sob(cur, c, wkt, tolerancia, sr_entrada, devolver_geometria)
            if len(resultados) >= limites.MAPSERVER_IDENTIFY_MAX:
                resultados = resultados[: limites.MAPSERVER_IDENTIFY_MAX]
                break
    return resposta_esri({"results": resultados}, f, cb)


def _alvo_sql(tolerancia: float) -> str:
    """Geometria de teste na referência NATIVA da camada. A tolerância é aplicada na referência de
    ENTRADA (onde ela foi medida em pixels) e só depois reprojetada — o contrário mudaria a distância."""
    alvo = "ST_GeomFromEWKT(%s)"
    if tolerancia > 0:
        alvo = f"ST_Buffer({alvo}, %s)"
    return f"ST_Transform({alvo}, %s)"


def _feicoes_sob(cur, camada: dict, wkt: str, tolerancia: float, sr_entrada: int,
                 devolver_geometria: bool) -> list[dict]:
    meta = campos_mod.campos_da_camada(cur, camada["schema"], camada["tabela"])
    atributos = [c["nome"] for c in meta]
    colunas = ", ".join(f'"{n}"' for n in atributos)
    geom_sel = ('ST_AsGeoJSON(ST_Transform("geom", %s), 8) AS __gj, ' if devolver_geometria else "")
    params_geom = [sr_entrada] if devolver_geometria else []
    alvo = _alvo_sql(tolerancia)
    params_alvo = [wkt] + ([tolerancia] if tolerancia > 0 else []) + [camada["srid"]]
    sql = (
        f'SELECT {geom_sel}{colunas} FROM "{camada["schema"]}"."{camada["tabela"]}" '
        f'WHERE "geom" IS NOT NULL AND ST_Intersects("geom", {alvo}) LIMIT %s'
    )  # noqa: S608 — só nomes de coluna vindos de information_schema; valores sempre por parâmetro
    cur.execute(sql, [*params_geom, *params_alvo, limites.MAPSERVER_IDENTIFY_MAX])
    rotulo = next((c["nome"] for c in meta if c["papel"] == "atributo"), "fid")
    saida = []
    for r in cur.fetchall():
        gj = r.pop("__gj", None) if devolver_geometria else None
        item = {
            "layerId": camada["id"],
            "layerName": camada["nome"],
            "displayFieldName": rotulo,
            "value": str(r.get(rotulo)) if r.get(rotulo) is not None else "",
            "attributes": {k: (None if v is None else str(v)) for k, v in r.items()},
        }
        if gj:
            item["geometryType"] = rotas_servico.GEOM_PG_PARA_ESRI.get(camada["geometria"])
            item["geometry"] = _esri_de_geojson(gj, sr_entrada)
        saida.append(item)
    return saida


def _esri_de_geojson(gj: str, wkid: int) -> dict:
    from app.consulta.motor import _geojson_para_esri

    forma = _geojson_para_esri(gj, None, lambda x, y: [x, y])  # noqa: SLF001 — mesma conversão da query
    forma["spatialReference"] = {"wkid": wkid, "latestWkid": wkid}
    return forma


@router.get(f"{MAPSERVER}/identify", openapi_extra=LER, operation_id="svc_mapserver_identify_get")
async def mapserver_identify_get(token: str, item_id: str, request: Request):
    return await _identify(request, token, item_id)


@router.post(f"{MAPSERVER}/identify", openapi_extra=LER, operation_id="svc_mapserver_identify_post")
async def mapserver_identify_post(token: str, item_id: str, request: Request):
    return await _identify(request, token, item_id)


async def _find(request: Request, token: str, item_id: str) -> Response:
    p = await _parametros(request)
    auth = _abrir(request, token)
    f, cb = _f(p)
    texto = (p.get("searchText") or "").strip()
    if not texto:
        raise ErroAPI(400, "searchtext_ausente", "find exige searchText")
    if len(texto) > limites.BUSCA_Q_MAX:
        raise ErroAPI(400, "searchtext_grande", f"searchText acima de {limites.BUSCA_Q_MAX} caracteres")
    exato = _bool(p.get("contains"), True) is False
    campos_pedidos = [c.strip() for c in (p.get("searchFields") or "").split(",") if c.strip()]
    devolver_geometria = _bool(p.get("returnGeometry"), False)
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        todas = mapserver.camadas_do_mapa(cur, mapa)
        alvo = _camadas_do_identify(todas, p.get("layers") or "all")
        srid_saida = _srid_exibicao(mapa)
        resultados = []
        for c in alvo:
            resultados += _achar_texto(cur, c, texto, exato, campos_pedidos, devolver_geometria, srid_saida)
            if len(resultados) >= limites.MAPSERVER_FIND_MAX:
                resultados = resultados[: limites.MAPSERVER_FIND_MAX]
                break
    return resposta_esri({"results": resultados}, f, cb)


def _achar_texto(cur, camada: dict, texto: str, exato: bool, campos_pedidos: list[str],
                 devolver_geometria: bool, srid_saida: int) -> list[dict]:
    meta = campos_mod.campos_da_camada(cur, camada["schema"], camada["tabela"])
    textuais = campos_mod.campos_texto(meta)
    if campos_pedidos:
        desconhecidos = [c for c in campos_pedidos if c not in {m["nome"] for m in meta}]
        if desconhecidos:
            raise ErroAPI(400, "searchfields_invalido", f"campo inexistente em searchFields: {desconhecidos}")
        textuais = [c for c in campos_pedidos if c in textuais]
    if not textuais:
        return []
    colunas = ", ".join(f'"{c["nome"]}"' for c in meta)
    geom_sel = ('ST_AsGeoJSON(ST_Transform("geom", %s), 8) AS __gj, ' if devolver_geometria else "")
    params_geom = [srid_saida] if devolver_geometria else []
    alvo = texto if exato else f"%{texto}%"
    condicoes = " OR ".join(f'"{n}" {"=" if exato else "ILIKE"} %s' for n in textuais)
    sql = (
        f'SELECT {geom_sel}{colunas} FROM "{camada["schema"]}"."{camada["tabela"]}" '
        f"WHERE {condicoes} LIMIT %s"
    )  # noqa: S608 — nomes de coluna de information_schema; o texto procurado vai sempre por parâmetro
    cur.execute(sql, [*params_geom, *([alvo] * len(textuais)), limites.MAPSERVER_FIND_MAX])
    saida = []
    for r in cur.fetchall():
        gj = r.pop("__gj", None) if devolver_geometria else None
        casou = next((n for n in textuais if r.get(n) is not None
                      and (str(r[n]) == texto if exato else texto.lower() in str(r[n]).lower())), textuais[0])
        item = {
            "layerId": camada["id"],
            "layerName": camada["nome"],
            "displayFieldName": casou,
            "foundFieldName": casou,
            "value": str(r.get(casou)) if r.get(casou) is not None else "",
            "attributes": {k: (None if v is None else str(v)) for k, v in r.items()},
        }
        if gj:
            item["geometryType"] = rotas_servico.GEOM_PG_PARA_ESRI.get(camada["geometria"])
            item["geometry"] = _esri_de_geojson(gj, srid_saida)
        saida.append(item)
    return saida


@router.get(f"{MAPSERVER}/find", openapi_extra=LER, operation_id="svc_mapserver_find_get")
async def mapserver_find_get(token: str, item_id: str, request: Request):
    return await _find(request, token, item_id)


@router.post(f"{MAPSERVER}/find", openapi_extra=LER, operation_id="svc_mapserver_find_post")
async def mapserver_find_post(token: str, item_id: str, request: Request):
    return await _find(request, token, item_id)


# ------------------------------------------------------------------ generateKml
@router.get(f"{MAPSERVER}/generateKml", openapi_extra=LER, operation_id="svc_mapserver_generate_kml")
def mapserver_generate_kml(token: str, item_id: str, request: Request):
    """KML do mapa inteiro: uma `<Folder>` por camada, feições em WGS 84 (`ST_AsKML`, o mesmo caminho
    da exportação KML do item de tiles). Teto por camada igual ao do desenho, para que um mapa grande
    não vire um documento sem fim."""
    p = dict(request.query_params)
    auth = _abrir(request, token)
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        camadas = mapserver.selecao_de_camadas(mapserver.camadas_do_mapa(cur, mapa), p.get("layers"))
        partes = ['<?xml version="1.0" encoding="UTF-8"?>',
                  '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>'
                  f"{_kml_texto(mapa['titulo'] or item_id)}</name>"]
        for c in camadas:
            meta = campos_mod.campos_da_camada(cur, c["schema"], c["tabela"])
            rotulo = next((m["nome"] for m in meta if m["papel"] == "atributo"), "fid")
            partes.append(f"<Folder><name>{_kml_texto(c['nome'])}</name>")
            cur.execute(
                f'SELECT ST_AsKML(ST_Transform("geom", 4326)) AS __kml, "{rotulo}" AS __nome '
                f'FROM "{c["schema"]}"."{c["tabela"]}" WHERE "geom" IS NOT NULL LIMIT %s',  # noqa: S608
                (limites.MAPSERVER_FEICOES_POR_CAMADA,),
            )
            for r in cur.fetchall():
                partes.append(f"<Placemark><name>{_kml_texto(r['__nome'])}</name>{r['__kml'] or ''}</Placemark>")
            partes.append("</Folder>")
        partes.append("</Document></kml>")
    return Response("".join(partes), media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": f'attachment; filename="{item_id}.kml"'})


# ------------------------------------------------------------------ descritor de UMA camada
@router.get(f"{MAPSERVER}/{{camada_id}}", openapi_extra=LER, operation_id="svc_mapserver_camada")
def mapserver_camada(token: str, item_id: str, camada_id: str, request: Request):
    auth = _abrir(request, token)
    f, cb = _f(dict(request.query_params))
    if not camada_id.isdigit():
        raise ErroAPI(404, "camada_nao_encontrada", "identificador de camada do MapServer é inteiro")
    with db.db(auth.contexto()) as cur:
        mapa = mapserver.mapa_do_item(cur, item_id)
        camadas = mapserver.camadas_do_mapa(cur, mapa)
        alvo = next((c for c in camadas if c["id"] == int(camada_id)), None)
        if alvo is None:
            raise ErroAPI(404, "camada_nao_encontrada", "este mapa não publica camada com esse identificador")
        return resposta_esri(_descritor_de_camada(cur, alvo), f, cb)
