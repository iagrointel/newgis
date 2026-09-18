"""`ImageServer` compatível Esri por token no caminho (item L1-25-servico-de-imagem-esri-compativel).

Pedido de abertura do dono: o cliente do canal Esri mantém o ArcGIS Enterprise/Online dele e ACRESCENTA
a imagem desta plataforma como camada — sem pagar crédito de hospedagem de imagem no AGOL. `ImageServer`
é o único tipo de serviço para o qual o Pro/AGOL guarda credencial de terceiro (stored credentials só
valem para um tipo de serviço que o protocolo reconhece) e é o que o Pro chama de "Imagery Layer" ao
apontar para um raster hospedado fora da conta AGOL do cliente.

Contrato mínimo implementado — o que faz o Pro/AGOL ACEITAR adicionar a camada:

    GET /svc/<token>/rest/services/<item>/ImageServer                     documento do serviço (f=json)
    GET /svc/<token>/rest/services/<item>/ImageServer/exportImage         bbox -> PNG/JPEG
    GET /svc/<token>/rest/services/<item>/ImageServer/identify            ponto -> valor de pixel por banda
    GET /svc/<token>/rest/services/<item>/ImageServer/tile/<z>/<y>/<x>    ladrilho (mesma grade do L1-02)

Reuso, não reescrita (regra do turno): autorização é a MESMA porta do item L1-02-tiles-token —
`app.imagens.rotas_tiles._autorizar`/`_fonte_do_item`, token no caminho, escopo `imagens:ler` OU
`tiles:ler`, com o mesmo cache de 2 s e a mesma regra de nunca confirmar a existência de item alheio
(403, nunca 404). A leitura de pixel é o MESMO motor do L1-02 (rio-tiler sobre o COG no Garage por
`/vsis3`, `app.imagens.tiles`); `/tile` chama `rotas_tiles._servir` sem reescrever nada. O que este
módulo acrescenta é só a CASCA do protocolo ImageServer: o documento de serviço, `exportImage`
(recorte por bbox arbitrário — `rio_tiler.io.Reader.part`, que `tiles.ladrilho` não expõe porque só
serve ladrilho de grade) e `identify` (`Reader.point`).

Asset servido por padrão: `cientifico` (dtype original, com as estatísticas por banda que a ingestão
grava em `raster:bands`/`statistics` — item L1-01-ingest-raster), não `visual` como o L1-02: um
ImageServer descreve o DADO, e só o asset científico carrega estatística medida; `?asset=visual` pede
o outro perfil quando ele existir (mesma convenção de `app/imagens/rotas_tiles.py`).

PARIDADE com o ArcGIS Image Service (declarada aqui porque é onde o código vive; a matriz gerada pelo
item L2-04-j — `tests/esri/conformidade.py`/`docs/PARIDADE.md` — ainda não cobre este item, ver relatório
do turno):

  suportado — documento do serviço (`f=json/pjson/html`, `callback`); `exportImage` com `bbox`, `bboxSR`
              (EPSG ou os alias Esri 102100/102113 de Web Mercator), `size`, `imageSR`, `format=png|jpg`
              (aceita também png8/png24/png32 como sinônimo de png), `f=image|json`; `identify` por ponto
              (`geometry`/`geometryType=esriGeometryPoint`/`sr`), devolvendo o valor de cada banda ou
              "NoData"; `tile/<z>/<y>/<x>` (mesma grade WebMercatorQuad do L1-02, service renomeado para
              o padrão level/row/col do ArcGIS); `renderingRule` na forma `{"rasterFunction": "<nome>"}`
              (item L1-02-f), onde `<nome>` é uma predefinição de renderização (fábrica ou custom do
              inquilino) — `exportImage` e `tile/<z>/<y>/<x>` aplicam; `format=tiff` (GeoTIFF no dtype
              nativo, sem esticamento); `mosaicRule` LIMITADA aos métodos do L1-08 — esriMosaicNone,
              esriMosaicLockRaster e esriMosaicAttribute, mais `mosaicOperation` MT_FIRST/LAST/MIN/MAX/
              MEAN/MEDIAN (tabela em `app/imagens/mosaico.py::METODOS_ESRI`); num ImageServer de ITEM a
              regra só pode citar a própria cena, e citar outra é erro Esri nomeado; `allowRasterFunction` no documento
              do serviço vira `true` quando o item tem ao menos 1 predefinição de fábrica compatível.
  fora      — `mosaicRule` com esriMosaicSeamline, esriMosaicViewpoint, esriMosaicNorthwest ou
              esriMosaicCenter (motivo de cada um em `mosaico.METODOS_ESRI_FORA`).
              `renderingRule` em qualquer OUTRA forma (encadeada, com `rasterFunctionArguments`, funções
              nativas do Pro como Stretch/Colormap/NDVI cruas): recusado com erro Esri explícito, nunca
              interpretado parcialmente — anunciar uma capacidade que não existe do jeito que o cliente
              pediu é o mesmo defeito de um botão que não faz nada. `mosaicRule`: as regras L1-08 estão
              disponíveis nos mosaicos STAC; exportImage ainda recusa qualquer valor não-vazio.
              `computeStatisticsHistograms`/histograma em geral: depende do item L1-02-h;
              `hasHistograms` é sempre `false`, nunca inventado. `rasterAttributeTable`: esta plataforma
              não tem RAT. `query` de pegadas/catálogo de mosaico: cada item é um raster único, não um
              mosaico multi-cena — `capabilities` nunca anuncia "Catalog". Download de pixel, measure,
              edição: fora.
  parcial   — `tile`: serve o ladrilho, mas não tem cache dedicado do lado do servidor além do que o
              L1-02 já tem (TTL de 60 s em processo) — não há `tileInfo` de serviço cacheado à parte.

Teste com ArcGIS Pro/AGOL de verdade: PENDENTE (decisão D20 do backlog) — o que este módulo prova é a
FORMA do protocolo (campos do documento de serviço contra o esquema descrito na doc Esri, alinhamento
de pixel do exportImage contra o XYZ do L1-02), não a compatibilidade final com o cliente de verdade."""

from __future__ import annotations

import json as _json
from typing import Any

import rasterio
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from rasterio.crs import CRS
from rio_tiler.errors import PointOutsideBounds
from rio_tiler.io import Reader

from app import db, limites
from app.consulta.formato_esri import resposta_esri
from app.consulta.rotas_servico import CURRENT_VERSION
from app.erros import ErroAPI
from app.imagens import mosaico as mos
from app.imagens import predefinicoes as pred
from app.imagens import tiles
from app.imagens.rotas_tiles import _autorizar, _fonte_do_item, _servir

router = APIRouter(tags=["imagens-esri"])
X = {"x-auth": "T", "x-privilegio": "proprio"}
SERVICOS = "/svc/{token}/rest/services"
BASE = f"{SERVICOS}/{{item}}/ImageServer"

CAPACIDADES = "Image"  # só exportImage/identify/tile funcionam de fato; ver docstring do módulo
ASSET_PADRAO = "cientifico"

# tipo GDAL/rasterio (o que `Reader.dataset.dtypes` devolve, sempre nome numpy) -> código Esri de pixelType.
# Sem entrada = UNKNOWN, nunca um chute (dtype complexo/inteiro de 64 bits não tem código Esri equivalente
# direto e esta plataforma também não os aceita na ingestão — app/imagens/validacao.py).
_PIXEL_TYPE = {
    "uint8": "U8", "int8": "S8", "uint16": "U16", "int16": "S16",
    "uint32": "U32", "int32": "S32", "float32": "F32", "float64": "F64",
}
# alias que o AGOL/Pro mandam para Web Mercator em vez do EPSG padrão (102100 é o wkid Esri "clássico";
# 102113 é a variante antiga que ainda aparece em cliente velho) — os dois SÃO EPSG:3857 na prática.
_ALIAS_WKID = {"102100": "3857", "102113": "3857"}

FORMATOS_EXPORT: dict[str, tuple[str, str]] = {
    "png": ("PNG", "image/png"), "png8": ("PNG", "image/png"), "png24": ("PNG", "image/png"),
    "png32": ("PNG", "image/png"), "jpg": ("JPEG", "image/jpeg"), "jpeg": ("JPEG", "image/jpeg"),
    # (conserto L1-25, 17/09) TIFF é cláusula literal do portão ("devolve PNG/JPEG/TIFF alinhado ao
    # XYZ") e é o formato que o analista usa quando quer o VALOR, não a figura: sai no dtype nativo do
    # recorte, sem o esticamento automático que PNG/JPEG precisam para virar 8 bits.
    "tiff": ("GTiff", "image/tiff"), "tif": ("GTiff", "image/tiff"),
}
TAMANHO_PADRAO = limites.IMAGESERVER_EXPORT_LADO_PADRAO
TAMANHO_MAX = limites.IMAGESERVER_EXPORT_LADO_MAX  # refutação do item: 20.000x20.000 tem de ser recusado


class _ErroParametro(Exception):
    """Parâmetro do cliente rejeitado — sempre vira corpo no formato Esri (`error.code/message`),
    nunca uma exceção crua (portão do item)."""

    def __init__(self, mensagem: str, detalhes: list[str] | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or []


def _erro_esri(status: int, mensagem: str, detalhes: list[str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": status, "message": mensagem, "details": detalhes or []}},
                        status_code=status)


def _f_callback(request: Request) -> tuple[str | None, str | None]:
    p = request.query_params
    return p.get("f"), p.get("callback")


def _asset(pedido: str | None) -> str:
    if pedido is None:
        return ASSET_PADRAO
    if pedido not in ("visual", "cientifico"):
        raise ErroAPI(422, "asset_invalido", "asset tem de ser 'visual' ou 'cientifico'", {"asset": pedido})
    return pedido


def _pixel_type(dtype: str | None) -> str:
    return _PIXEL_TYPE.get(dtype or "", "UNKNOWN")


def _leitura_nativa(fonte: tiles.Fonte) -> dict[str, Any]:
    """Extensão, referência espacial nativa, tamanho de pixel, nº de bandas, dtype e nodata — SEMPRE
    lidos do COG aberto agora (GDAL), nunca de propriedade STAC opcional (`proj:transform` não existe
    em todo item, ex.: o COG sintético de teste). É o mesmo `rasterio.Env`/sessão S3 que `tiles.py` usa,
    só que aqui se olha `Reader.dataset` (rasterio puro) em vez de `Reader.info()` (que devolve os
    limites já reprojetados para 4326 — bom para o TileJSON, errado para o `extent` nativo do Esri)."""
    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=tiles.TMS) as src:
            ds = src.dataset
            b = ds.bounds
            resx, resy = ds.res
            return {
                "extent": {"xmin": b.left, "ymin": b.bottom, "xmax": b.right, "ymax": b.top},
                "wkid": ds.crs.to_epsg() if ds.crs else None,
                "pixelSizeX": resx,
                "pixelSizeY": abs(resy),
                "bandCount": ds.count,
                "dtype": ds.dtypes[0] if ds.dtypes else None,
                "nodata": ds.nodata,
            }


def _estatisticas(stac: dict, asset: str) -> dict[str, list[float]] | None:
    """min/max/mean/stddev por banda, só quando TODA banda do asset carrega `statistics` (raster
    extension) — a ingestão de hoje grava isso no asset `cientifico` (app/imagens/ingestao.py); um
    asset sem estatística devolve None e o documento do serviço OMITE os campos, nunca inventa."""
    bandas = ((stac.get("assets") or {}).get(asset) or {}).get("raster:bands") or []
    if not bandas:
        return None
    minimos, maximos, medias, desvios = [], [], [], []
    for b in bandas:
        st = b.get("statistics") or {}
        if st.get("minimum") is None or st.get("maximum") is None or st.get("mean") is None:
            return None
        minimos.append(st["minimum"])
        maximos.append(st["maximum"])
        medias.append(st["mean"])
        desvios.append(st.get("stddev"))
    saida: dict[str, list[float]] = {"minValues": minimos, "maxValues": maximos, "meanValues": medias}
    if all(d is not None for d in desvios):
        saida["stdvValues"] = desvios
    return saida


def _crs_de(valor: str | None, wkid_padrao: int | None) -> tuple[int, CRS]:
    """wkid Esri/EPSG (string simples, `EPSG:<n>`, ou JSON `{"wkid": n}`/`{"latestWkid": n}`) -> (wkid,
    CRS). Sem valor, cai no wkid nativo do raster; sem os dois, é erro de parâmetro (não há para onde
    reprojetar)."""
    texto = (valor or "").strip()
    if not texto:
        if wkid_padrao is None:
            raise _ErroParametro("referência espacial ausente e o item não tem uma nativa conhecida",
                                 ["informe bboxSR"])
        return wkid_padrao, CRS.from_epsg(wkid_padrao)
    if texto.startswith("{"):
        try:
            corpo = _json.loads(texto)
            wkid_txt = str(corpo.get("wkid") or corpo.get("latestWkid") or "")
        except (ValueError, AttributeError) as e:
            raise _ErroParametro(f"referência espacial malformada: {valor!r}") from e
    else:
        wkid_txt = texto.split(":")[-1]
    wkid_txt = _ALIAS_WKID.get(wkid_txt, wkid_txt)
    try:
        wkid = int(wkid_txt)
        return wkid, CRS.from_epsg(wkid)
    except Exception as e:
        raise _ErroParametro(f"referência espacial desconhecida: {valor!r}") from e


# ---------------------------------------------------------------------------- renderingRule (item L1-02-f)
def _nome_da_rendering_rule(valor: str) -> str:
    """`renderingRule` só é aceito na forma MÍNIMA `{"rasterFunction": "<nome>"}` — nada de
    `rasterFunctionArguments`, funções encadeadas (`"rasterFunction": "Stretch", "rasterFunctionArguments":
    {"Raster": {...}}`) nem os nomes nativos do Pro (Stretch/Colormap/NDVI): `<nome>` é sempre uma
    predefinição desta plataforma (fábrica ou custom do inquilino), resolvida do MESMO jeito que
    `predef=`/`STYLES=` nas outras portas (rotas_tiles.py/rotas_wms.py). Levanta ValueError com o motivo
    em português quando a forma não bate — quem chama traduz para erro Esri."""
    texto = (valor or "").strip()
    if not texto:
        raise ValueError("renderingRule vazio")
    try:
        corpo = _json.loads(texto)
    except ValueError as e:
        raise ValueError(f"renderingRule não é JSON: {valor!r}") from e
    if not isinstance(corpo, dict) or set(corpo) != {"rasterFunction"}:
        raise ValueError(
            "só a forma {'rasterFunction': '<nome-da-predefinição>'} é aceita nesta implementação "
            "(sem rasterFunctionArguments nem encadeamento)")
    nome = corpo["rasterFunction"]
    if not isinstance(nome, str) or not nome:
        raise ValueError("rasterFunction precisa ser o nome (texto) de uma predefinição")
    return nome


def _resolver_rendering_rule(auth, item: str, valor: str, asset: str):
    """(nome, `Resolvido`) a partir de `renderingRule=`, ou levanta `ErroAPI` já pronta para
    `_erro_esri`. `asset` já chega resolvido (`_asset()` default é `cientifico` — o único asset com
    estatística medida, o que uma predefinição precisa para o esticamento)."""
    try:
        nome = _nome_da_rendering_rule(valor)
    except ValueError as e:
        raise ErroAPI(400, "renderingRule_nao_suportado", str(e)) from e
    _, stac = _fonte_do_item(auth, item, asset)
    with db.db(auth.contexto_leitura()) as cur:
        resolvido = pred.resolver(cur, auth.tenant_id, item, nome, stac, asset)
    return nome, resolvido


# ---------------------------------------------------------------------------- documento do serviço
def _documento_servico(auth, item: str, asset: str) -> dict:
    fonte, stac = _fonte_do_item(auth, item, asset)
    nativo = _leitura_nativa(fonte)
    props = stac.get("properties") or {}
    titulo = props.get("title") or item
    doc: dict[str, Any] = {
        "currentVersion": CURRENT_VERSION,
        "serviceDescription": titulo,
        "name": titulo,
        "description": props.get("description") or "",
        "bandCount": nativo["bandCount"],
        "pixelType": _pixel_type(nativo["dtype"]),
        "hasHistograms": False,  # depende do item L1-02-h, ainda não construído — nunca "true" sem ele
        "hasColormap": False,
        "hasRasterAttributeTable": False,  # esta plataforma não tem RAT
        # allowRasterFunction (item L1-02-f): true quando há ao menos 1 predefinição de fábrica compatível
        # com o nº de bandas do asset — só a FORMA mínima {"rasterFunction":"<nome>"}, ver docstring do módulo.
        "allowRasterFunction": pred.n_bandas(stac, asset) >= min(e["min_bandas"] for e in pred.FABRICA.values()),
        "capabilities": CAPACIDADES,
        "copyrightText": props.get("plat:atribuicao") or "",
    }
    if nativo["wkid"] is not None:
        extent = {**nativo["extent"], "spatialReference": {"wkid": nativo["wkid"]}}
        doc["extent"] = extent
        doc["initialExtent"] = extent
        doc["fullExtent"] = extent
        doc["spatialReference"] = {"wkid": nativo["wkid"]}
    if nativo["pixelSizeX"]:
        doc["pixelSizeX"] = nativo["pixelSizeX"]
        doc["pixelSizeY"] = nativo["pixelSizeY"]
    if nativo["nodata"] is not None:
        doc["noDataValues"] = [nativo["nodata"]] * (nativo["bandCount"] or 1)
    stats = _estatisticas(stac, asset)
    if stats:
        doc.update(stats)
    return doc


@router.get(BASE, openapi_extra=X, summary="documento do serviço ImageServer (f=json)")
def image_server(token: str, item: str, request: Request, asset: str | None = Query(None)):
    auth = _autorizar(request, token, item)
    f, cb = _f_callback(request)
    doc = _documento_servico(auth, item, _asset(asset))
    return resposta_esri(doc, f, cb)


# ---------------------------------------------------------------------------- exportImage
def _indices_de_exibicao(band_count: int) -> tuple[int, ...] | None:
    # mesma regra do C3 (tiles.ladrilho): PNG/JPEG não carregam mais de 3 bandas + máscara.
    return (1, 2, 3) if band_count > 3 else None


@router.get(f"{BASE}/exportImage", openapi_extra=X, summary="recorte por bbox (equivalente ao Export Image)")
def export_image(  # noqa: PLR0911 — operação com muitos parâmetros Esri para validar; cada um é uma saída cedo clara
    token: str, item: str, request: Request,
    bbox: str = Query(..., description="xmin,ymin,xmax,ymax na referência de bboxSR"),
    bboxSR: str | None = Query(None),
    size: str | None = Query(None, description="largura,altura em pixels"),
    imageSR: str | None = Query(None),
    format: str = Query("png"),
    f: str = Query("image", pattern="^(image|json)$"),
    asset: str | None = Query(None),
):
    auth = _autorizar(request, token, item)
    asset_final = _asset(asset)
    fmt = FORMATOS_EXPORT.get((format or "png").strip().lower())
    if fmt is None:
        return _erro_esri(400, "'format' não é suportado por este serviço",
                          [f"aceitos: {', '.join(sorted(FORMATOS_EXPORT))}", f"recebido: {format!r}"])
    # (conserto L1-25, 17/09) `mosaicRule` LIMITADA às regras do L1-08 (portão do item), traduzida em
    # `app/imagens/mosaico.py::traduzir_regra_esri` — a mesma tabela que a paridade publica. Num
    # ImageServer de ITEM o serviço serve uma cena só: `lockRasterIds` que cite outra (de outro item ou
    # de outro inquilino) é recusado ali, com erro Esri nomeado, nunca aceito e ignorado.
    regra_mosaico = None
    bruto_mosaico = request.query_params.get("mosaicRule")
    if bruto_mosaico:
        try:
            regra_mosaico = mos.traduzir_regra_esri(_json.loads(bruto_mosaico), [item])
        except _json.JSONDecodeError:
            return _erro_esri(400, "'mosaicRule' não é um JSON válido", [])
        except ErroAPI as e:
            return _erro_esri(400, e.mensagem, [str(e.detalhe)] if e.detalhe else [])
    resolvido = None
    rendering_rule = request.query_params.get("renderingRule")
    if rendering_rule:
        try:
            _, resolvido = _resolver_rendering_rule(auth, item, rendering_rule, asset_final)
        except ErroAPI as e:
            return _erro_esri(400 if e.status_code == 400 else 422, e.mensagem, [str(e.detalhe)] if e.detalhe else [])
    try:
        partes = [p.strip() for p in bbox.split(",")]
        if len(partes) != 4:
            raise ValueError("bbox sem 4 números")
        xmin, ymin, xmax, ymax = (float(p) for p in partes)
        if not (xmax > xmin and ymax > ymin):
            raise ValueError("xmax/ymax têm de ser maiores que xmin/ymin")
        largura, altura = TAMANHO_PADRAO, TAMANHO_PADRAO
        if size:
            partes_t = [p.strip() for p in size.split(",")]
            if len(partes_t) != 2:
                raise ValueError("size sem 2 números")
            largura, altura = (int(p) for p in partes_t)
        if not (0 < largura <= TAMANHO_MAX and 0 < altura <= TAMANHO_MAX):
            raise ValueError(f"size: cada lado tem de estar entre 1 e {TAMANHO_MAX} px")
    except ValueError as e:
        return _erro_esri(400, "'bbox' ou 'size' inválido", [str(e)])

    fonte, stac = _fonte_do_item(auth, item, asset_final)
    try:
        nativo_wkid = _leitura_nativa(fonte)["wkid"]
        bbox_wkid, bbox_crs = _crs_de(bboxSR, nativo_wkid)
        img_wkid, img_crs = _crs_de(imageSR, bbox_wkid)
    except _ErroParametro as e:
        return _erro_esri(400, e.mensagem, e.detalhes)

    if resolvido and resolvido.hillshade:
        corpo = pred.renderizar_hillshade(
            fonte, banda=(resolvido.bandas or [1])[0], formato=("jpg" if fmt[0] == "JPEG" else "png"),
            resampling=resolvido.resampling, nodata_transparente=resolvido.nodata_transparente,
            parte=((xmin, ymin, xmax, ymax), img_crs, largura, altura),
        )
        if f == "json":
            href = str(request.url.include_query_params(f="image"))
            return JSONResponse({"href": href, "width": largura, "height": altura,
                                 "extent": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                                            "spatialReference": {"wkid": img_wkid}}})
        return Response(content=corpo, media_type=fmt[1], headers={"Cache-Control": "no-store"})

    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=tiles.TMS) as src:
            expressao = resolvido.expressao if resolvido else None
            if expressao:
                indices = None  # expressão lê as bandas dela mesma (numexpr) — indexes e expression são
                                # mutuamente exclusivos no rio-tiler, mesma regra de tiles.ladrilho/recorte
            elif resolvido and resolvido.bandas:
                indices = tuple(resolvido.bandas)
            else:
                indices = _indices_de_exibicao(src.dataset.count)
            img = src.part((xmin, ymin, xmax, ymax), bounds_crs=bbox_crs, dst_crs=img_crs,
                           width=largura, height=altura, indexes=indices, expression=expressao,
                           resampling_method=(resolvido.resampling if resolvido else "nearest"))
            if resolvido and resolvido.rescale:
                img.rescale(resolvido.rescale)
            elif fmt[0] == "GTiff":
                pass  # TIFF carrega o VALOR: nunca esticar por conta própria (ver FORMATOS_EXPORT)
            elif img.array.dtype != "uint8":
                # sem rescale explícito no contrato mínimo: estica pelo mínimo/máximo do próprio
                # recorte, mesma regra que tiles.ladrilho usa para o ladrilho (C3 do conceito L1)
                dados = img.array
                lo = float(dados.min()) if dados.size else 0.0
                hi = float(dados.max()) if dados.size else 1.0
                img.rescale([(lo, hi if hi > lo else lo + 1e-9)])
            cm = tiles.colormap_de(resolvido.colormap) if resolvido else None
            nodata_transparente = resolvido.nodata_transparente if resolvido else True
            if fmt[0] == "GTiff":
                # GeoTIFF sai georreferenciado (o `crs`/`transform` da própria ImageData) e sem banda
                # alfa: quem pede TIFF quer a matriz, e uma alfa extra desalinha a contagem de bandas.
                corpo = img.render(img_format="GTiff", add_mask=False)
            else:
                corpo = img.render(img_format=fmt[0], colormap=cm,
                                   add_mask=(fmt[0] != "JPEG") and nodata_transparente)
    if resolvido and resolvido.opacidade < 1.0:
        corpo = pred.aplicar_opacidade(corpo, ("jpg" if fmt[0] == "JPEG" else "png"), resolvido.opacidade)

    if f == "json":
        href = str(request.url.include_query_params(f="image"))
        return JSONResponse({
            "href": href, "width": largura, "height": altura,
            "extent": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                       "spatialReference": {"wkid": img_wkid}},
        })
    cabecalhos = {"Cache-Control": "no-store"}
    if regra_mosaico is not None:
        # Um ImageServer de ITEM serve UMA cena: a regra foi entendida e validada, mas não há segunda
        # candidata para ordenar ou compor. Dizer isso no cabeçalho é mais honesto que aceitar em
        # silêncio (o cliente consegue distinguir "aplicada" de "sem efeito" sem ler a paridade).
        # cabeçalho HTTP é latin-1 no protocolo: texto ASCII, sempre (acento aqui derrubava a resposta
        # inteira com UnicodeDecodeError no cliente — medido nesta bancada em 17/09).
        cabecalhos["X-Plat-Mosaic-Rule"] = (
            f"entendida; sem efeito em servico de item unico (lock={regra_mosaico['lock'] or '-'}; "
            f"pixel_selection={regra_mosaico['pixel_selection'] or '-'})"
        )
    return Response(content=corpo, media_type=fmt[1], headers=cabecalhos)


# ---------------------------------------------------------------------------- identify
@router.get(f"{BASE}/identify", openapi_extra=X, summary="valor de pixel num ponto")
def identify(
    token: str, item: str, request: Request,
    geometry: str = Query(..., description='"x,y" ou {"x":..,"y":..,"spatialReference":{"wkid":..}}'),
    geometryType: str = Query("esriGeometryPoint"),
    sr: str | None = Query(None, alias="sr"),
    f: str | None = Query(None),
    callback: str | None = Query(None),
    asset: str | None = Query(None),
):
    auth = _autorizar(request, token, item)
    if geometryType != "esriGeometryPoint":
        return _erro_esri(400, "'geometryType' não suportado", ["só esriGeometryPoint"])
    texto = geometry.strip()
    wkid_geom = None
    try:
        if texto.startswith("{"):
            corpo = _json.loads(texto)
            x, y = float(corpo["x"]), float(corpo["y"])
            sr_bloco = corpo.get("spatialReference") or {}
            wkid_geom = sr_bloco.get("wkid") or sr_bloco.get("latestWkid")
        else:
            x_s, y_s = (p.strip() for p in texto.split(","))
            x, y = float(x_s), float(y_s)
    except (ValueError, KeyError, AttributeError):
        return _erro_esri(400, "'geometry' inválida", ['use "x,y" ou {"x":..,"y":..}'])

    asset_final = _asset(asset)
    fonte, _ = _fonte_do_item(auth, item, asset_final)
    try:
        nativo_wkid = _leitura_nativa(fonte)["wkid"]
        ponto_wkid, ponto_crs = _crs_de(sr or (str(wkid_geom) if wkid_geom else None), nativo_wkid)
    except _ErroParametro as e:
        return _erro_esri(400, e.mensagem, e.detalhes)

    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=tiles.TMS) as src:
            try:
                pt = src.point(x, y, coord_crs=ponto_crs)
                valor = ",".join(str(v) for v in pt.array.tolist())
            except PointOutsideBounds:
                valor = "NoData"
    corpo = {
        "objectId": 1, "name": "Pixel",
        "value": valor,
        "location": {"x": x, "y": y, "spatialReference": {"wkid": ponto_wkid}},
        "properties": None,
        "catalogItems": None,
    }
    f_norm, cb = f, callback
    return resposta_esri(corpo, f_norm, cb)


# ---------------------------------------------------------------------------- tile (level/row/col Esri)
@router.get(f"{BASE}/tile/{{level}}/{{row}}/{{col}}", openapi_extra=X,
            summary="ladrilho no padrão de caminho do ArcGIS (level/row/col == z/y/x)")
def tile_esri(token: str, item: str, level: int, row: int, col: int, request: Request,
              asset: str | None = Query(None)):
    """Mesmo ladrilho do item L1-02 (`rotas_tiles._servir`, sem reescrever nada) — só o caminho muda
    para o padrão que o Pro usa ao pedir ladrilho de um `ImageServer` (`level/row/col`, sempre PNG,
    sempre grade WebMercatorQuad). `renderingRule` (item L1-02-f) é repassado para `_servir` como
    `predef=` na forma mínima `{"rasterFunction":"<nome>"}` (a MESMA validação de `export_image`, ver
    `_nome_da_rendering_rule`); `bandIds` continua fora (não é o mesmo mecanismo de `bandas=`)."""
    if request.query_params.get("bandIds"):
        return _erro_esri(400, "'bandIds' não é suportado por este serviço", [])
    auth = _autorizar(request, token, item)
    asset_final = _asset(asset)
    rendering_rule = request.query_params.get("renderingRule")
    predef = None
    if rendering_rule:
        try:
            predef = _nome_da_rendering_rule(rendering_rule)
        except ValueError as e:
            return _erro_esri(400, "renderingRule_nao_suportado", [str(e)])
    try:
        return _servir(request, auth, item, level, col, row, "png", None, None, None, None, asset_final,
                       predef=predef)
    except ErroAPI as e:
        if e.erro in ("predefinicao_inexistente", "predefinicao_incompativel"):
            return _erro_esri(400, e.mensagem, [str(e.detalhe)] if e.detalhe else [])
        raise


__all__ = ["router"]
