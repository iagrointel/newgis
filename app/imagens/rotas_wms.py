"""Serviço WMS 1.3.0 por token — item L1-02-g-wms-1-3-0-raster.

    GET /svc/<token>/wms?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0
    GET /svc/<token>/wms?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=...&CRS=...&BBOX=...&
        WIDTH=...&HEIGHT=...&FORMAT=image/png&TRANSPARENT=TRUE

Mesma porta de entrada do WMTS/XYZ (`app/imagens/rotas_tiles.py::_autorizar`, token no CAMINHO — nunca
em parâmetro — mesmo cache de 5 s, mesmo código de recusa 403). O que muda aqui é o FORMATO do erro de
domínio: onde `rotas_tiles.py` devolve o contrato JSON da casa, um cliente WMS (QGIS "Adicionar camada
WMS", Esri "Add WMS Layer") espera um `ServiceExceptionReport` — por isso todo erro que NÃO é de
autenticação/autorização (essas continuam JSON, mesma convenção do WMTS) sai daqui em XML
(`app/imagens/wms.py::service_exception`).

`LAYERS` referenciando um item de OUTRO inquilino (ou inexistente) nunca chega a `_fonte_do_item`: a
lista de camadas visíveis é calculada UMA vez (`_camadas_visiveis`, filtrada por tenant_id + escopo do
token) e usada tanto no `GetCapabilities` quanto na validação do `GetMap` — uma camada fora dela vira
`LayerNotDefined`, a MESMA mensagem para "não existe" e "não é sua" (regra da casa: nunca confirmar
existência alheia).

`SLD`/`SLD_BODY` (o vetor de XXE que a refutação do item pede) NUNCA é passado a um parser de XML —
o valor do parâmetro é só CONSULTADO (`"SLD_BODY" in p`) e a requisição é recusada antes de qualquer
outro processamento; não existe caminho de código que desserialize esse texto."""

from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app import db, limites
from app.auth import escopos as esc
from app.erros import ErroAPI
from app.imagens import leitura, tiles
from app.imagens import pgstac as ps
from app.imagens import predefinicoes as pred
from app.imagens import raster_item as ri
from app.imagens import wms as wms_doc
from app.imagens.rotas_tiles import (
    CACHE_TILE,
    X,
    _asset_padrao,
    _autorizar,
    _bandas,
    _faixa,
    _fonte_do_item,
    _predef_publicada,
)
from app.settings import settings

router = APIRouter(tags=["wms"])

_XML_WMS = "text/xml"
FORMATOS_SAIDA = {"image/png": "png", "image/jpeg": "jpg", "png": "png", "jpg": "jpg", "jpeg": "jpg"}


def _base(token: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA.rstrip('/')}/svc/{token}"


def _kvp(request: Request) -> dict[str, str]:
    """Parâmetros em maiúscula (a casa já resolve WFS do mesmo jeito, `rotas_wfs.py`) — o WMS exige
    nomes de parâmetro insensíveis a maiúscula/minúscula (OGC 06-042 §6.3.3)."""
    return {k.upper(): v for k, v in request.query_params.items()}


def _excecao(mensagem: str, codigo: str | None = None, status: int = 400) -> Response:
    return Response(wms_doc.service_exception(mensagem, codigo), media_type=_XML_WMS, status_code=status,
                    headers={"Cache-Control": "no-store, must-revalidate"})


def _estilos_do_item(cur, auth, item_id: str, stac: dict, token: str) -> list[dict]:
    """`<Style>` do item (item L1-02-f): predefinições de fábrica cujo `min_bandas` cabe no asset
    científico do item + predefinições custom do inquilino para este item. `legend_href` já sai pronto
    para `GetLegendGraphic` (mesmo `LAYER`/`STYLE` que o dispatch de `_get_legend_graphic` espera)."""
    n = pred.n_bandas(stac, "cientifico")
    base = f"{_base(token)}/wms"
    def _href(nome_estilo: str) -> str:
        return (f"{base}?SERVICE=WMS&REQUEST=GetLegendGraphic&FORMAT=image/png&"
               f"LAYER={item_id}&STYLE={nome_estilo}")

    saida = [
        {"nome": e["nome"], "titulo": e["titulo"], "legend_href": _href(e["nome"])}
        for e in pred.listar_fabrica() if e["min_bandas"] <= n
    ]
    # `plat.render_predefinicao.item_id` é uuid (item do catálogo, `plat.item`); um `raster_item` de
    # fixture de teste antiga pode ter item_id texto livre ("item-espelho-1") — nunca do catálogo, então
    # nunca tem predefinição custom. Testar antes do cast evita 500 (achado ao ligar este item na demo).
    if pred._e_uuid(item_id):  # noqa: SLF001 — mesmo teste do resto do item L1-02-f, sem duplicar
        cur.execute(
            "SELECT nome, titulo FROM plat.render_predefinicao WHERE tenant_id = %s AND item_id = %s::uuid "
            "AND apagado_em IS NULL ORDER BY nome",
            (auth.tenant_id, item_id),
        )
        for r in cur.fetchall():
            saida.append({"nome": r["nome"], "titulo": r["titulo"], "legend_href": _href(r["nome"])})
    return saida


def _camadas_visiveis(cur, auth, token: str | None = None) -> dict[str, dict[str, Any]]:
    """Item ativo do inquilino do token, restrito ao que o escopo alcança (mesma regra do `/wmts` e do
    mosaico: `tiles:ler:<item>` ou `imagens:ler`). O bbox vem do próprio STAC (`bbox` do item, sempre em
    EPSG:4326) — não abre o COG por GDAL para montar o `GetCapabilities` (custaria uma leitura remota
    por camada); só o `GetMap` de fato lê pixel. `token` só é passado quando quem chama precisa dos
    `<Style>`/`LegendURL` (GetCapabilities) — o GetMap não usa `estilos`, então não paga essa consulta."""
    linhas = [r for r in ri.listar(cur, auth.tenant_id) if r["estado"] == "ativo"]
    linhas = [
        r for r in linhas
        if esc.cobre(auth.escopos, "tiles:ler", r["item_id"]) or esc.cobre(auth.escopos, "imagens:ler")
    ]
    linhas = linhas[: limites.WMS_CAMADAS_MAX]
    camadas: dict[str, dict[str, Any]] = {}
    for r in linhas:
        stac = ps.item_obter(cur, auth.tenant_id, r["colecao"], r["item_id"])
        bbox = (stac or {}).get("bbox")
        if not stac or not bbox:
            continue
        oeste, sul, leste, norte = (bbox[0], bbox[1], bbox[3], bbox[4]) if len(bbox) == 6 else tuple(bbox)
        titulo = (stac.get("properties") or {}).get("title") or r["item_id"]
        camadas[r["item_id"]] = {
            "item_id": r["item_id"], "titulo": titulo, "resumo": "",
            "bounds": [oeste, sul, leste, norte],
            "estilos": _estilos_do_item(cur, auth, r["item_id"], stac, token) if token else [],
        }
    return camadas


# ---------------------------------------------------------------------------- GetCapabilities
def _get_capabilities(token: str, auth, cur) -> Response:
    camadas = list(_camadas_visiveis(cur, auth, token).values())
    xml = wms_doc.capabilities(
        base=_base(token), titulo="plat WMS — análise/beta privado",
        resumo="Camadas raster do inquilino acessíveis por este token; triagem, não prova.",
        camadas=camadas, largura_max=limites.WMS_LARGURA_MAX, altura_max=limites.WMS_ALTURA_MAX,
    )
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- GetMap
def _parse_bbox(txt: str | None) -> tuple[float, float, float, float] | None:
    if not txt:
        return None
    partes = txt.split(",")
    if len(partes) != 4:
        return None
    try:
        return tuple(float(p) for p in partes)  # type: ignore[return-value]
    except ValueError:
        return None


def _parse_dim(txt: str | None) -> int | None:
    if txt is None:
        return None
    try:
        v = int(txt)
    except ValueError:
        return None
    return v if v > 0 else None


def _formato_saida(txt: str | None) -> str | None:
    if not txt:
        return "png"  # sem FORMAT: PNG é o que todo cliente WMS entende (folga deliberada sobre a spec)
    return FORMATOS_SAIDA.get(txt.strip().lower())


def _renderizar(auth, camadas: dict, nomes: list[str], bbox: tuple, crs: str, largura: int, altura: int,
                formato: str, transparente: bool, expressao, bandas, faixa, colormap, asset,
                estilos_por_camada: dict[str, str | None] | None = None) -> bytes:
    estilos_por_camada = estilos_por_camada or {}
    partes = []
    for nome in nomes:
        predef = estilos_por_camada.get(nome)
        resolvido = None
        asset_camada = asset
        if predef:
            asset_camada = asset or "cientifico"
            _, stac = _fonte_do_item(auth, nome, asset_camada)
            with db.db(auth.contexto_leitura()) as cur:
                resolvido = pred.resolver(cur, auth.tenant_id, nome, predef, stac, asset_camada)
        expressao_camada = expressao or (resolvido.expressao if resolvido else None)
        bandas_camada = bandas or (
            ",".join(str(b) for b in resolvido.bandas) if resolvido and resolvido.bandas else None)
        colormap_camada = colormap or (resolvido.colormap if resolvido else None)
        asset_final = _asset_padrao(expressao_camada, asset_camada)
        fonte, _ = _fonte_do_item(auth, nome, asset_final)
        if resolvido and resolvido.hillshade:
            corpo = pred.renderizar_hillshade(
                fonte, banda=(resolvido.bandas or [1])[0], formato="png",
                resampling=resolvido.resampling,
                nodata_transparente=resolvido.nodata_transparente if not faixa else True,
                parte=(bbox, tiles.CRS.from_user_input(crs), largura, altura),
            )
        else:
            faixa_final = _faixa(faixa) if faixa else (resolvido.rescale if resolvido else None)
            corpo = tiles.recorte(
                fonte, bbox, crs, largura, altura, formato="png", expressao=expressao_camada,
                bandas=_bandas(bandas_camada), rescale=faixa_final, colormap=colormap_camada,
                transparente=True, resampling=(resolvido.resampling if resolvido else "nearest"),
            )
            if resolvido and resolvido.opacidade < 1.0:
                corpo = pred.aplicar_opacidade(corpo, "png", resolvido.opacidade)
        leitura.contar(auth.tenant_id, auth.token_id, nome, len(corpo))
        partes.append(corpo)
    if len(partes) == 1 and formato == "png" and transparente:
        return partes[0]
    from PIL import Image

    base_img = Image.open(io.BytesIO(partes[0])).convert("RGBA")
    for extra in partes[1:]:
        base_img = Image.alpha_composite(base_img, Image.open(io.BytesIO(extra)).convert("RGBA"))
    if formato != "png" or not transparente:
        fundo = Image.new("RGB", base_img.size, (255, 255, 255))
        fundo.paste(base_img, mask=base_img.split()[3])
        base_img = fundo
    buf = io.BytesIO()
    base_img.save(buf, format="JPEG" if formato == "jpg" else "PNG")
    return buf.getvalue()


def _get_map(auth, cur, p: dict[str, str]) -> Response:
    # SLD nunca é interpretado (nem sequer entra num parser de XML) — a recusa acontece ANTES de
    # qualquer outra leitura do pedido (ver docstring do módulo).
    if p.get("SLD_BODY") or p.get("SLD"):
        return _excecao("SLD/SLD_BODY não é suportado nesta implementação (parâmetro ignorado por "
                        "design, nunca interpretado como XML)")

    camadas = _camadas_visiveis(cur, auth)
    nomes = [n for n in (p.get("LAYERS") or "").split(",") if n]
    if not nomes:
        return _excecao("LAYERS é obrigatório")
    faltando = [n for n in nomes if n not in camadas]
    if faltando:
        return _excecao(f"camada não definida neste serviço: {', '.join(faltando)}", "LayerNotDefined")

    # STYLES (item L1-02-f): vazio ou "default" por camada = comportamento de hoje, sem predefinição
    # nenhuma (portão: "não mude o comportamento atual sem parâmetro"); um nome não-vazio tem de ser uma
    # predefinição de fábrica ou custom (checado agora, contra o STAC de CADA camada — não só a forma).
    estilos_brutos = (p.get("STYLES") or "").split(",") if p.get("STYLES") else []
    if estilos_brutos and len(estilos_brutos) not in (1, len(nomes)):
        return _excecao(f"STYLES tem de ter 1 valor (aplicado a todas as camadas) ou {len(nomes)} "
                        f"(um por LAYERS); recebeu {len(estilos_brutos)}", "StyleNotDefined")
    if len(estilos_brutos) == 1 and len(nomes) > 1:
        estilos_brutos = estilos_brutos * len(nomes)
    estilos_por_camada: dict[str, str | None] = {}
    for i, nome in enumerate(nomes):
        s = (estilos_brutos[i] if i < len(estilos_brutos) else "").strip()
        if not s or s == "default":
            estilos_por_camada[nome] = None
            continue
        try:
            _, stac_camada = _fonte_do_item(auth, nome, "cientifico")
            if s not in pred.NOMES_FABRICA:
                cur.execute(
                    "SELECT 1 FROM plat.render_predefinicao WHERE tenant_id = %s AND item_id = %s::uuid "
                    "AND nome = %s AND apagado_em IS NULL",
                    (auth.tenant_id, nome, s),
                )
                if cur.fetchone() is None:
                    raise ErroAPI(404, "predefinicao_inexistente", "predefinição inexistente", {})
            elif pred.n_bandas(stac_camada, "cientifico") < pred.FABRICA[s]["min_bandas"]:
                raise ErroAPI(422, "predefinicao_incompativel", "bandas insuficientes", {})
        except ErroAPI:
            return _excecao(f"estilo não definido para a camada {nome!r}: {s!r}", "StyleNotDefined")
        estilos_por_camada[nome] = s

    crs_bruto = p.get("CRS") or p.get("SRS")
    crs = wms_doc.normalizar_crs(crs_bruto)
    if crs is None:
        return _excecao(f"CRS não suportado: {crs_bruto!r} (aceitos: {', '.join(wms_doc.CRS_SUPORTADOS)})",
                        "InvalidCRS")

    bbox_bruto = _parse_bbox(p.get("BBOX"))
    if bbox_bruto is None:
        return _excecao("BBOX é obrigatório: quatro números separados por vírgula")
    oeste, sul, leste, norte = wms_doc.bbox_do_parametro(crs, bbox_bruto)
    if oeste >= leste or sul >= norte:
        return _excecao(f"BBOX inválido (mínimo >= máximo depois de aplicar a ordem de eixo de {crs}): "
                        f"{p.get('BBOX')!r}")

    largura, altura = _parse_dim(p.get("WIDTH")), _parse_dim(p.get("HEIGHT"))
    if largura is None or altura is None:
        return _excecao("WIDTH e HEIGHT são obrigatórios e têm de ser inteiros positivos")
    if largura > limites.WMS_LARGURA_MAX or altura > limites.WMS_ALTURA_MAX or \
       largura * altura > limites.WMS_PIXELS_MAX:
        return _excecao(
            f"WIDTH×HEIGHT acima do teto ({largura}×{altura} = {largura * altura} px; "
            f"teto {limites.WMS_LARGURA_MAX}×{limites.WMS_ALTURA_MAX} = {limites.WMS_PIXELS_MAX} px)")

    formato = _formato_saida(p.get("FORMAT"))
    if formato is None:
        return _excecao(f"FORMAT não suportado: {p.get('FORMAT')!r} (aceitos: image/png, image/jpeg)",
                        "InvalidFormat")
    transparente = (p.get("TRANSPARENT") or "FALSE").strip().upper() == "TRUE"

    try:
        corpo = _renderizar(
            auth, camadas, nomes, (oeste, sul, leste, norte), crs, largura, altura, formato, transparente,
            p.get("EXPRESSAO"), p.get("BANDAS"), p.get("FAIXA"), p.get("COLORMAP"), p.get("ASSET"),
            estilos_por_camada,
        )
    except tiles.ErroTile as e:
        return _excecao(str(e))
    except ErroAPI as e:
        return _excecao(e.mensagem, status=e.status_code)
    except Exception as e:  # leitura do armazenamento falhou: nunca 500 mudo, mas também não é do cliente
        return _excecao(f"não foi possível renderizar o mapa: {e}", status=502)

    media = "image/jpeg" if formato == "jpg" else "image/png"
    return Response(corpo, media_type=media, headers={"Cache-Control": CACHE_TILE})


# ---------------------------------------------------------------------------- GetFeatureInfo (L1-02-g)
FORMATOS_INFO_SAIDA = {
    "application/json": "json", "application/geo+json": "json", "json": "json",
    "text/plain": "texto", "text/plain; charset=utf-8": "texto",
}


def _valor_no_ponto(auth, item: str, x: float, y: float, crs: str, asset: str | None) -> list[float] | None:
    """Valor por banda no ponto (x,y) do CRS dado. MESMO caminho de leitura do `identify` do ImageServer
    (`rio_tiler.Reader.point`) e do `/ponto` — não existe um segundo motor de pixel aqui. `None` quando o
    ponto cai fora do raster (o WMS responde com uma feição sem valor, nunca com erro)."""
    import rasterio
    from rio_tiler.errors import PointOutsideBounds
    from rio_tiler.io import Reader

    fonte, _ = _fonte_do_item(auth, item, _asset_padrao(None, asset or "cientifico"))
    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=tiles.TMS) as src:
            try:
                pt = src.point(x, y, coord_crs=tiles.CRS.from_user_input(crs))
            except PointOutsideBounds:
                return None
            return [float(v) for v in pt.array.tolist()]


def _get_feature_info(auth, cur, p: dict[str, str]) -> Response:
    """OGC 06-042 §7.4. O pedido repete o GetMap (CRS/BBOX/WIDTH/HEIGHT) e acrescenta QUERY_LAYERS e o
    pixel I,J contado a partir do canto SUPERIOR ESQUERDO da imagem (§7.4.3.7/7.4.3.8) — a conversão de
    I,J para coordenada é feita aqui, nunca no motor de pixel."""
    camadas = _camadas_visiveis(cur, auth)
    nomes = [n for n in (p.get("QUERY_LAYERS") or "").split(",") if n]
    if not nomes:
        return _excecao("QUERY_LAYERS é obrigatório no GetFeatureInfo", "LayerNotQueryable")
    faltando = [n for n in nomes if n not in camadas]
    if faltando:
        return _excecao(f"camada não definida neste serviço: {', '.join(faltando)}", "LayerNotDefined")
    if len(nomes) > limites.WMS_CAMADAS_MAX:
        return _excecao(f"QUERY_LAYERS acima do teto de {limites.WMS_CAMADAS_MAX} camadas")

    crs_bruto = p.get("CRS") or p.get("SRS")
    crs = wms_doc.normalizar_crs(crs_bruto)
    if crs is None:
        return _excecao(f"CRS não suportado: {crs_bruto!r} (aceitos: {', '.join(wms_doc.CRS_SUPORTADOS)})",
                        "InvalidCRS")
    bbox_bruto = _parse_bbox(p.get("BBOX"))
    if bbox_bruto is None:
        return _excecao("BBOX é obrigatório: quatro números separados por vírgula")
    oeste, sul, leste, norte = wms_doc.bbox_do_parametro(crs, bbox_bruto)
    if oeste >= leste or sul >= norte:
        return _excecao(f"BBOX inválido (mínimo >= máximo depois de aplicar a ordem de eixo de {crs}): "
                        f"{p.get('BBOX')!r}")
    largura, altura = _parse_dim(p.get("WIDTH")), _parse_dim(p.get("HEIGHT"))
    if largura is None or altura is None:
        return _excecao("WIDTH e HEIGHT são obrigatórios e têm de ser inteiros positivos")
    if largura > limites.WMS_LARGURA_MAX or altura > limites.WMS_ALTURA_MAX:
        return _excecao(f"WIDTH×HEIGHT acima do teto ({largura}×{altura})")

    try:
        i, j = int(str(p.get("I")).strip()), int(str(p.get("J")).strip())
    except (TypeError, ValueError):
        return _excecao("I e J são obrigatórios e têm de ser inteiros (pixel na imagem do GetMap)",
                        "InvalidPoint")
    if not (0 <= i < largura and 0 <= j < altura):
        return _excecao(f"I,J fora da imagem pedida ({i},{j} em {largura}x{altura})", "InvalidPoint")

    formato = FORMATOS_INFO_SAIDA.get((p.get("INFO_FORMAT") or "application/json").strip().lower())
    if formato is None:
        return _excecao(f"INFO_FORMAT não suportado: {p.get('INFO_FORMAT')!r} "
                        f"(aceitos: {', '.join(wms_doc.FORMATOS_INFO)})", "InvalidFormat")

    # centro do pixel (I,J), com J crescendo para BAIXO: o topo da imagem é `norte`
    x = oeste + (i + 0.5) * (leste - oeste) / largura
    y = norte - (j + 0.5) * (norte - sul) / altura

    feicoes = []
    for nome in nomes:
        try:
            valores = _valor_no_ponto(auth, nome, x, y, crs, p.get("ASSET"))
        except ErroAPI as e:
            return _excecao(e.mensagem, status=e.status_code)
        except Exception as e:  # noqa: BLE001 — leitura remota falhou: 502 nomeado, nunca 500 mudo
            return _excecao(f"não foi possível ler o valor do pixel: {e}", status=502)
        feicoes.append({
            "type": "Feature", "id": f"{nome}.{i}.{j}",
            "geometry": {"type": "Point", "coordinates": [x, y]},
            "properties": (
                {"camada": nome, "valor": "NoData", "bandas": None} if valores is None
                else {"camada": nome, "valor": ",".join(str(v) for v in valores),
                      "bandas": {f"banda_{n}": v for n, v in enumerate(valores, start=1)}}
            ),
        })

    if formato == "texto":
        linhas = []
        for f in feicoes:
            props = f["properties"]
            linhas.append(f"{props['camada']}: {props['valor']}")
        corpo_txt = "\n".join(linhas) + "\n"
        return Response(corpo_txt, media_type="text/plain; charset=utf-8",
                        headers={"Cache-Control": "no-store, must-revalidate"})
    import json as _json

    corpo = {"type": "FeatureCollection", "features": feicoes,
             "crs": {"type": "name", "properties": {"name": crs}}}
    return Response(_json.dumps(corpo, ensure_ascii=False), media_type="application/json",
                    headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- GetLegendGraphic (L1-02-f)
def _get_legend_graphic(auth, cur, p: dict[str, str]) -> Response:
    camada = p.get("LAYER")
    if not camada:
        return _excecao("LAYER é obrigatório", "MissingDimensionValue")
    camadas = _camadas_visiveis(cur, auth)
    if camada not in camadas:
        return _excecao(f"camada não definida neste serviço: {camada}", "LayerNotDefined")
    estilo = (p.get("STYLE") or "").strip()
    nome = estilo if estilo and estilo != "default" else None
    if nome is None:
        nome = _predef_publicada(auth, camada, None)
        if nome is None:
            return _excecao(
                f"a camada {camada!r} não tem predefinição padrão nem STYLE explícito — nada para "
                "desenhar na legenda (RGB sem rampa não tem GetLegendGraphic)", "StyleNotDefined")
    try:
        _, stac = _fonte_do_item(auth, camada, "cientifico")
        resolvido = pred.resolver(cur, auth.tenant_id, camada, nome, stac, "cientifico")
    except ErroAPI:
        return _excecao(f"estilo não definido para a camada {camada!r}: {nome!r}", "StyleNotDefined")
    corpo = pred.legenda_png(resolvido)
    return Response(corpo, media_type="image/png", headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- despacho KVP
@router.get("/svc/{token}/wms", openapi_extra=X, summary="WMS 1.3.0 (GetCapabilities, GetMap, GetFeatureInfo e GetLegendGraphic)")
def wms_kvp(request: Request, token: str):
    auth = _autorizar(request, token)
    p = _kvp(request)
    if (p.get("SERVICE") or "WMS").upper() != "WMS":
        return _excecao(f"SERVICE tem de ser WMS, recebido {p.get('SERVICE')!r}")
    operacao = (p.get("REQUEST") or "").lower()
    with db.db(auth.contexto_leitura()) as cur:
        if operacao == "getcapabilities":
            return _get_capabilities(token, auth, cur)
        if operacao == "getmap":
            return _get_map(auth, cur, p)
        if operacao == "getfeatureinfo":
            return _get_feature_info(auth, cur, p)
        if operacao == "getlegendgraphic":
            return _get_legend_graphic(auth, cur, p)
    return _excecao(
        f"REQUEST={p.get('REQUEST')!r} não suportado (use GetCapabilities, GetMap, GetFeatureInfo ou "
        "GetLegendGraphic)",
        "OperationNotSupported",
    )


__all__ = ["router"]
