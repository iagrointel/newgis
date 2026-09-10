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
from app.imagens import raster_item as ri
from app.imagens import wms as wms_doc
from app.imagens.rotas_tiles import CACHE_TILE, X, _asset_padrao, _autorizar, _bandas, _faixa, _fonte_do_item
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


def _camadas_visiveis(cur, auth) -> dict[str, dict[str, Any]]:
    """Item ativo do inquilino do token, restrito ao que o escopo alcança (mesma regra do `/wmts` e do
    mosaico: `tiles:ler:<item>` ou `imagens:ler`). O bbox vem do próprio STAC (`bbox` do item, sempre em
    EPSG:4326) — não abre o COG por GDAL para montar o `GetCapabilities` (custaria uma leitura remota
    por camada); só o `GetMap` de fato lê pixel."""
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
        }
    return camadas


# ---------------------------------------------------------------------------- GetCapabilities
def _get_capabilities(token: str, auth, cur) -> Response:
    camadas = list(_camadas_visiveis(cur, auth).values())
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
                formato: str, transparente: bool, expressao, bandas, faixa, colormap, asset) -> bytes:
    asset_final = _asset_padrao(expressao, asset)
    partes = []
    for nome in nomes:
        fonte, _ = _fonte_do_item(auth, nome, asset_final)
        corpo = tiles.recorte(
            fonte, bbox, crs, largura, altura, formato="png", expressao=expressao,
            bandas=_bandas(bandas), rescale=_faixa(faixa), colormap=colormap, transparente=True,
        )
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

    estilos = [s for s in (p.get("STYLES") or "").split(",") if s]
    if estilos and any(s not in ("", "default") for s in estilos):
        return _excecao(f"estilo não definido: {p.get('STYLES')} (só 'default' é servido)", "StyleNotDefined")

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
        )
    except tiles.ErroTile as e:
        return _excecao(str(e))
    except ErroAPI as e:
        return _excecao(e.mensagem, status=e.status_code)
    except Exception as e:  # leitura do armazenamento falhou: nunca 500 mudo, mas também não é do cliente
        return _excecao(f"não foi possível renderizar o mapa: {e}", status=502)

    media = "image/jpeg" if formato == "jpg" else "image/png"
    return Response(corpo, media_type=media, headers={"Cache-Control": CACHE_TILE})


# ---------------------------------------------------------------------------- despacho KVP
@router.get("/svc/{token}/wms", openapi_extra=X, summary="WMS 1.3.0 (GetCapabilities e GetMap)")
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
    return _excecao(
        f"REQUEST={p.get('REQUEST')!r} não suportado (use GetCapabilities ou GetMap; "
        "GetFeatureInfo não está implementado nesta passagem)",
        "OperationNotSupported",
    )


__all__ = ["router"]
