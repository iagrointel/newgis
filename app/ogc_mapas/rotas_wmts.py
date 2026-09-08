"""WMTS 1.0.0 (OGC 07-057r7) sobre a mesma camada hospedada — item `L2-04-i-wms-wmts-sld`.

Dois encodings, porque os clientes se dividem: KVP (`?SERVICE=WMTS&REQUEST=GetTile&...`, o que o QGIS
manda quando você cola a URL de capacidades) e RESTful (`/rest/{camada}/{estilo}/{matriz}/{z}/{y}/{x}.png`,
o que ArcGIS Pro/AGOL preferem e o que entra no `ResourceURL` das capacidades).

O tile é desenhado pelo mesmo `pintor` do WMS na grade `GoogleMapsCompatible` (EPSG:3857, 256 px) — o
mesmo recorte do XYZ do visualizador, então um tile do WMTS e um tile do mapa da casa cobrem a mesma
caixa. Quando a camada tem tiles PRÉ-RENDERIZADOS (job `wmts_prerender`, arquivo PMTiles raster no
bucket do inquilino), o tile sai do arquivo por leitura de faixa (`Range`) e não passa pelo banco.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app import db
from app.consulta.rotas_query import _autenticar, _camada_do_item
from app.consulta.rotas_servico import _camada_e_titulo
from app.erros import ErroAPI
from app.ogc_mapas import capacidades, matrizes, pintor, prerenderizado
from app.ogc_mapas import dados as dados_mod
from app.ogc_mapas import estilo as estilo_mod
from app.ogc_mapas.rotas_wms import ErroWms, _kvp
from app.settings import settings

router = APIRouter(prefix="/wmts/{item_id}", tags=["wmts"])

VERSAO = "1.0.0"
_XML = "text/xml; charset=utf-8"
MIME_TILE = {"png": "image/png", "jpeg": "image/jpeg"}
Z_MAX_VIVO = 22


def _base(request: Request, item_id: str) -> str:
    raiz = (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/")
    return f"{raiz}/wmts/{item_id}"


def _resposta_excecao(e: ErroWms, status: int = 400) -> Response:
    return Response(content=capacidades.excecao_ows(e.codigo, e.mensagem), media_type=_XML, status_code=status)


def _capabilities(request: Request, item_id: str, auth) -> Response:
    with db.db(auth.contexto()) as cur:
        dados, titulo = _camada_e_titulo(cur, item_id)
        ext4326 = dados_mod.extensao_nativa(cur, schema=dados["schema"], tabela=dados["tabela"],
                                            srid_nativo=int(dados["srid"]), srid_saida=4326)
        estilos = estilo_mod.estilos_publicados(item_id, dados)
        pre = prerenderizado.descricao(cur, item_id)
    base = _base(request, item_id)
    camada = {"nome": item_id, "titulo": titulo or item_id,
              "resumo": (dados.get("procedencia") or {}).get("fonte") or "",
              "extensao4326": ext4326,
              "estilos": [{"nome": e["nome"], "titulo": e["titulo"], "padrao": True} for e in estilos]}
    z_max = pre["z_max"] if pre else 18
    xml = capacidades.wmts_capabilities(base=base, base_rest=f"{base}/rest",
                                        titulo_servico=titulo or "plataforma", camadas=[camada],
                                        z_min=0, z_max=z_max)
    return Response(content=xml, media_type=_XML)


def _tile(request: Request, item_id: str, auth, *, z: int, x: int, y: int, formato: str,
          nome_estilo: str | None) -> Response:
    if not matrizes.valido(z, x, y, 0, Z_MAX_VIVO):
        raise ErroWms("TileOutOfRange", f"tile fora da matriz: z={z} x={x} y={y}")
    caixa = matrizes.caixa_do_tile(z, x, y)
    with db.db(auth.contexto()) as cur:
        guardado = prerenderizado.ler_tile(cur, item_id, z, x, y)
        if guardado is not None:
            return Response(content=guardado, media_type="image/png",
                            headers={"Cache-Control": "private, max-age=3600", "X-Plat-Origem": "prerenderizado"})
        dados = _camada_do_item(cur, item_id)
        schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
        est = estilo_mod.resolver(cur, item_id, dados, nome_estilo=nome_estilo)
        tolerancia = matrizes.pixel_span(z) * 0.5
        campos = _campos_para_estilo(cur, schema, tabela, est)
        feicoes = dados_mod.feicoes_da_caixa(cur, schema, tabela, srid, caixa, 3857, tolerancia, campos=campos)
    corpo, _n = pintor.pintar(feicoes, est, caixa, matrizes.TAMANHO_TILE, matrizes.TAMANHO_TILE,
                              transparente=(formato != "jpeg"), formato=formato)
    return Response(content=corpo, media_type=MIME_TILE[formato],
                    headers={"Cache-Control": "private, max-age=600", "X-Plat-Feicoes": str(len(feicoes)),
                             "X-Plat-Origem": "vivo"})


def _campos_para_estilo(cur, schema: str, tabela: str, est: dict) -> list[str]:
    from app.consulta import campos as campos_mod

    if not any(c.get("teste") is not None for c in est.get("classes") or []):
        return []
    return [c["nome"] for c in campos_mod.campos_da_camada(cur, schema, tabela) if c["papel"] == "atributo"]


def _formato_tile(bruto: str | None) -> str:
    v = (bruto or "image/png").strip().lower()
    if v in ("image/png", "png"):
        return "png"
    if v in ("image/jpeg", "image/jpg", "jpeg", "jpg"):
        return "jpeg"
    raise ErroWms("InvalidParameterValue", f"FORMAT não suportado no WMTS: {bruto}")


@router.get("", operation_id="wmts_kvp", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
@router.get("/", include_in_schema=False, operation_id="wmts_kvp_barra",
            openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def wmts(item_id: str, request: Request) -> Response:
    p = _kvp(request)
    try:
        servico = (p.get("service") or "WMTS").upper()
        if servico != "WMTS":
            raise ErroWms("InvalidParameterValue", f"SERVICE precisa ser WMTS: {servico}")
        pedido = (p.get("request") or "").strip().lower()
        if not pedido:
            raise ErroWms("MissingParameterValue", "parâmetro obrigatório ausente: REQUEST")
        auth = _autenticar(request, item_id)
        if pedido == "getcapabilities":
            return _capabilities(request, item_id, auth)
        versao = (p.get("version") or VERSAO).strip()
        if versao != VERSAO:
            raise ErroWms("InvalidParameterValue", f"só a versão {VERSAO} é servida (recebido {versao})")
        if pedido == "gettile":
            camada = (p.get("layer") or "").strip()
            if camada and camada != item_id:
                raise ErroWms("InvalidParameterValue", f"LAYER desconhecida neste serviço: {camada}")
            tms = (p.get("tilematrixset") or matrizes.IDENTIFICADOR).strip()
            if tms != matrizes.IDENTIFICADOR:
                raise ErroWms("InvalidParameterValue",
                              f"TILEMATRIXSET não suportado: {tms} (só {matrizes.IDENTIFICADOR})")
            try:
                z = int(str(p.get("tilematrix", "")).split(":")[-1])
                y = int(p["tilerow"])
                x = int(p["tilecol"])
            except (KeyError, ValueError) as e:
                raise ErroWms("MissingParameterValue",
                              "TILEMATRIX, TILEROW e TILECOL são obrigatórios e inteiros") from e
            return _tile(request, item_id, auth, z=z, x=x, y=y, formato=_formato_tile(p.get("format")),
                         nome_estilo=(p.get("style") or "").strip())
        raise ErroWms("OperationNotSupported", f"REQUEST não suportado no WMTS: {pedido}")
    except ErroWms as e:
        return _resposta_excecao(e)
    except ErroAPI as e:
        # 401/403/404 saem como HTTP de verdade (é o que a varredura cruzada exige: A pedindo a camada
        # de B recebe 404, não um XML de 200); só erro de PARÂMETRO vira ServiceException do protocolo
        if e.status_code in (401, 403, 404):
            raise
        return _resposta_excecao(ErroWms("InvalidParameterValue", e.mensagem))


@router.get("/rest/WMTSCapabilities.xml", operation_id="wmts_rest_capabilities",
            openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def wmts_rest_capabilities(item_id: str, request: Request) -> Response:
    auth = _autenticar(request, item_id)
    return _capabilities(request, item_id, auth)


@router.get("/rest/{camada}/{estilo}/{tms}/{z}/{y}/{x}.png", operation_id="wmts_rest_tile",
            openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def wmts_rest_tile(item_id: str, camada: str, estilo: str, tms: str, z: int, y: int, x: int,
                   request: Request) -> Response:
    try:
        auth = _autenticar(request, item_id)
        if camada != item_id:
            raise ErroWms("InvalidParameterValue", f"camada desconhecida neste serviço: {camada}")
        if tms != matrizes.IDENTIFICADOR:
            raise ErroWms("InvalidParameterValue", f"TileMatrixSet não suportado: {tms}")
        return _tile(request, item_id, auth, z=z, x=x, y=y, formato="png",
                     nome_estilo=("" if estilo in ("padrao", "default", "") else estilo))
    except ErroWms as e:
        return _resposta_excecao(e)
