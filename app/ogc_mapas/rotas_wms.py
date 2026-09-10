"""WMS 1.3.0 (OGC 06-042) sobre a camada hospedada — item `L2-04-i-wms-wmts-sld`. Protocolo KVP, que é
o que QGIS, ArcGIS Pro/AGOL e GDAL usam em "adicionar camada WMS".

Um serviço por ITEM (`/wms/{item_id}`), igual ao WFS do L2-04-h e ao FeatureServer do L2-04-c: o mesmo
token, o mesmo escopo (`camada:ler`), a mesma RLS. Operações: `GetCapabilities`, `GetMap`,
`GetFeatureInfo` e `GetLegendGraphic` (extensão de fato, presente em GeoServer/MapServer/QGIS Server).

Regras do 1.3.0 que este módulo implementa e que o 1.1.1 não tinha:
- parâmetro `CRS` (não `SRS`) e ORDEM DE EIXO por autoridade: em EPSG:4326 e EPSG:4674 o `BBOX` chega
  como `miny,minx,maxy,maxx` (latitude primeiro). `CRS:84` é o mesmo datum com eixo lon,lat.
- erro devolvido como `ServiceExceptionReport` XML (ou como imagem, se `EXCEPTIONS=INIMAGE|BLANK`),
  com HTTP 200 — é o que a especificação manda e o que os clientes esperam.
- `WIDTH`/`HEIGHT` até 4.096 (publicado em `MaxWidth`/`MaxHeight`).

O desenho é do `pintor` (Pillow) sobre as feições da caixa; o estilo vem do L2-02-a ou do `SLD_BODY`
do próprio pedido.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request, Response

from app import db
from app.consulta import campos as campos_mod
from app.consulta.rotas_query import _autenticar, _camada_do_item
from app.consulta.rotas_servico import _camada_e_titulo
from app.erros import ErroAPI
from app.ogc_mapas import capacidades, pintor, pool
from app.ogc_mapas import dados as dados_mod
from app.ogc_mapas import estilo as estilo_mod
from app.ogc_mapas import legenda as legenda_mod
from app.settings import settings

router = APIRouter(prefix="/wms/{item_id}", tags=["wms"])

VERSAO = "1.3.0"
_XML = "text/xml; charset=utf-8"
MIME = {"png": "image/png", "png8": "image/png", "jpeg": "image/jpeg", "gif": "image/gif"}
# quantos pixels em volta do clique entram na busca do GetFeatureInfo (o mesmo que o GeoServer usa)
RAIO_INFO_PX = 4


class ErroWms(Exception):
    """Erro de protocolo: vira `ServiceExceptionReport` com HTTP 200, não um JSON de erro da casa."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _kvp(request: Request) -> dict:
    """Parâmetros WMS são insensíveis a maiúsculas (OGC 06-042, 6.8.1); os valores, não."""
    return {k.lower(): v for k, v in request.query_params.items()}


def _exigir(p: dict, nome: str) -> str:
    v = p.get(nome)
    if v is None or v == "":
        raise ErroWms("MissingParameterValue", f"parâmetro obrigatório ausente: {nome.upper()}")
    return v


def _inteiro(p: dict, nome: str, minimo: int, maximo: int) -> int:
    bruto = _exigir(p, nome)
    try:
        v = int(bruto)
    except ValueError as e:
        raise ErroWms("InvalidParameterValue", f"{nome.upper()} precisa ser inteiro: {bruto!r}") from e
    if not (minimo <= v <= maximo):
        raise ErroWms("InvalidParameterValue", f"{nome.upper()} fora de {minimo}..{maximo}: {v}")
    return v


def _booleano(v: str | None, padrao: bool = False) -> bool:
    if v is None:
        return padrao
    return str(v).strip().lower() in ("true", "1", "yes", "sim")


def _crs(p: dict) -> str:
    bruto = (p.get("crs") or p.get("srs") or "").strip()
    if not bruto:
        raise ErroWms("MissingParameterValue", "parâmetro obrigatório ausente: CRS")
    crs = bruto.upper().replace("URN:OGC:DEF:CRS:", "").replace("::", ":")
    if crs in ("OGC:CRS84", "CRS84"):
        crs = "CRS:84"
    if crs not in capacidades.CRS_SUPORTADOS:
        raise ErroWms("InvalidCRS", f"CRS não suportado: {bruto}")
    return crs


def srid_do_crs(crs: str) -> int:
    return 4326 if crs == "CRS:84" else int(crs.split(":")[1])


def caixa_do_pedido(bruto: str, crs: str) -> tuple[float, float, float, float]:
    """`BBOX` -> (minx, miny, maxx, maxy) em coordenadas do CRS, já na ordem interna x,y.

    Em WMS 1.3.0 um CRS geográfico com eixo lat,lon (EPSG:4326, EPSG:4674) recebe o BBOX como
    `miny,minx,maxy,maxx` — trocar isto é o erro clássico entre 1.1.1 e 1.3.0, e é cláusula do portão.
    """
    partes = [x.strip() for x in (bruto or "").split(",")]
    if len(partes) != 4:
        raise ErroWms("InvalidParameterValue", "BBOX precisa de 4 números separados por vírgula")
    try:
        a, b, c, d = (float(x) for x in partes)
    except ValueError as e:
        raise ErroWms("InvalidParameterValue", f"BBOX com número inválido: {bruto!r}") from e
    caixa = (b, a, d, c) if capacidades.eixo_invertido(crs) else (a, b, c, d)
    if not (caixa[0] < caixa[2] and caixa[1] < caixa[3]):
        raise ErroWms("InvalidParameterValue", "BBOX vazio ou invertido (minx>=maxx ou miny>=maxy)")
    return caixa


def _limitar_ao_mundo(caixa, crs: str):
    """Recorta a caixa ao domínio do CRS. A refutação do item manda BBOX fora do mundo: em vez de
    devolver erro (o cliente que erra o zoom fica sem mapa), a caixa é recortada e a imagem sai com o
    que existe — a proporção pedida é mantida porque o recorte só vale para a CONSULTA, não para a
    projeção dos pixels."""
    if crs == "EPSG:3857":
        limite = (-20037508.342789244, -20037508.342789244, 20037508.342789244, 20037508.342789244)
    elif crs in ("EPSG:4326", "CRS:84", "EPSG:4674"):
        limite = (-180.0, -90.0, 180.0, 90.0)
    else:
        return caixa
    return (max(caixa[0], limite[0]), max(caixa[1], limite[1]),
            min(caixa[2], limite[2]), min(caixa[3], limite[3]))


def _formato(p: dict, permitidos=capacidades.FORMATOS_MAPA) -> str:
    bruto = (p.get("format") or "image/png").strip().lower()
    if bruto not in [f.lower() for f in permitidos] and bruto not in ("image/png; mode=8bit",):
        raise ErroWms("InvalidFormat", f"FORMAT não suportado: {bruto}")
    return pintor.FORMATOS.get(bruto, "png")


def _sld_do_pedido(p: dict) -> str | None:
    corpo = p.get("sld_body")
    if corpo:
        return corpo
    url = (p.get("sld") or "").strip()
    if not url:
        return None
    # nunca buscar URL de fora (mesma regra do L0-11): o SLD por endereço só vale para o próprio servidor
    raise ErroWms("InvalidParameterValue",
                  "SLD por URL não é aceito; mande o estilo em SLD_BODY (o servidor não busca endereço externo)")


def _camadas_pedidas(p: dict, item_id: str, nome_camada: str, chave: str = "layers") -> list[str]:
    bruto = (p.get(chave) or "").strip()
    if not bruto:
        raise ErroWms("MissingParameterValue", f"parâmetro obrigatório ausente: {chave.upper()}")
    pedidas = [x.strip() for x in bruto.split(",") if x.strip()]
    validos = {nome_camada, item_id, f"plat:{item_id.replace('-', '_')}"}
    for nome in pedidas:
        if nome not in validos:
            raise ErroWms("LayerNotDefined", f"camada desconhecida neste serviço: {nome}")
    return pedidas


def _base(request: Request, item_id: str) -> str:
    raiz = (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/")
    return f"{raiz}/wms/{item_id}"


def _resposta_excecao(e: ErroWms, p: dict, status: int = 200) -> Response:
    """`EXCEPTIONS=INIMAGE|BLANK` devolve imagem (é o que um cliente de mosaico prefere); o padrão XML."""
    modo = (p.get("exceptions") or "XML").strip().upper()
    if modo in ("INIMAGE", "BLANK"):
        largura = int(p.get("width") or 256)
        altura = int(p.get("height") or 256)
        largura = max(1, min(largura, pintor.MAX_LADO))
        altura = max(1, min(altura, pintor.MAX_LADO))
        fmt = pintor.FORMATOS.get((p.get("format") or "image/png").lower(), "png")
        corpo = pintor.imagem_vazia(largura, altura, _booleano(p.get("transparent"), True), fmt)
        return Response(content=corpo, media_type=MIME.get(fmt, "image/png"), status_code=200)
    return Response(content=capacidades.excecao_wms(e.codigo, e.mensagem), media_type=_XML, status_code=status)


@router.get("", operation_id="wms_kvp", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
@router.get("/", include_in_schema=False, operation_id="wms_kvp_barra",
            openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def wms(item_id: str, request: Request) -> Response:
    p = _kvp(request)
    try:
        servico = (p.get("service") or "WMS").upper()
        if servico != "WMS":
            raise ErroWms("InvalidParameterValue", f"SERVICE precisa ser WMS: {servico}")
        pedido = (p.get("request") or "").strip()
        if not pedido:
            raise ErroWms("MissingParameterValue", "parâmetro obrigatório ausente: REQUEST")
        auth = _autenticar(request, item_id)
        alvo = pedido.lower()
        if alvo == "getcapabilities":
            return _get_capabilities(request, item_id, auth)
        versao = (p.get("version") or VERSAO).strip()
        if versao != VERSAO:
            raise ErroWms("InvalidParameterValue",
                          f"só a versão {VERSAO} é servida (recebido {versao}); peça VERSION=1.3.0")
        if alvo == "getmap":
            return _get_map(request, item_id, auth, p)
        if alvo == "getfeatureinfo":
            return _get_feature_info(request, item_id, auth, p)
        if alvo == "getlegendgraphic":
            return _get_legend(request, item_id, auth, p)
        raise ErroWms("OperationNotSupported", f"REQUEST não suportado: {pedido}")
    except ErroWms as e:
        return _resposta_excecao(e, p)
    except ErroAPI as e:
        # 401/403/404 saem como HTTP de verdade (é o que a varredura cruzada exige: A pedindo a camada
        # de B recebe 404, não um XML de 200); só erro de PARÂMETRO vira ServiceException do protocolo
        if e.status_code in (401, 403, 404):
            raise
        return _resposta_excecao(ErroWms("InvalidParameterValue", e.mensagem), p)


def _nome_camada(item_id: str) -> str:
    return item_id


def _get_capabilities(request: Request, item_id: str, auth) -> Response:
    with db.db(auth.contexto()) as cur:
        dados, titulo = _camada_e_titulo(cur, item_id)
        schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
        ext4326 = dados_mod.extensao_nativa(cur, schema, tabela, srid, 4326)
        ext_nativa = dados_mod.extensao_nativa(cur, schema, tabela, srid, srid)
        estilos = estilo_mod.estilos_publicados(item_id, dados)
    base = _base(request, item_id)
    for e in estilos:
        e["legenda_url"] = (f"{base}?service=WMS&version=1.3.0&request=GetLegendGraphic"
                            f"&layer={item_id}&format=image/png")
        e["legenda_largura"], e["legenda_altura"] = legenda_mod.tamanho(e["classes"])
    camada = {
        "nome": _nome_camada(item_id), "titulo": titulo or item_id,
        "resumo": (dados.get("procedencia") or {}).get("fonte") or "",
        "crs_nativo": f"EPSG:{srid}", "extensao4326": ext4326, "extensao_nativa": ext_nativa,
        "estilos": estilos, "escala_min": None, "escala_max": None, "consultavel": True,
    }
    xml = capacidades.wms_capabilities(base=base, titulo_servico=titulo or "plataforma",
                                       camadas=[camada], inquilino=str(auth.tenant_id))
    return Response(content=xml, media_type=_XML)


def _preparar_desenho(cur, item_id: str, p: dict, crs: str, caixa, largura: int, altura: int):
    dados = _camada_do_item(cur, item_id)
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    est = estilo_mod.resolver(cur, item_id, dados, nome_estilo=(p.get("styles") or "").split(",")[0],
                              sld_texto=_sld_do_pedido(p))
    srid_pedido = srid_do_crs(crs)
    caixa_consulta = _limitar_ao_mundo(caixa, crs)
    if not (caixa_consulta[0] < caixa_consulta[2] and caixa_consulta[1] < caixa_consulta[3]):
        return dados, est, []          # caixa inteiramente fora do mundo: imagem vazia, sem consultar
    # tolerância = meio pixel em unidades do CRS pedido (não adianta vértice mais fino que o pixel)
    tolerancia = ((caixa[2] - caixa[0]) / max(1, largura)) * 0.5
    campos = [c["nome"] for c in campos_mod.campos_da_camada(cur, schema, tabela)
              if c["papel"] == "atributo"] if _precisa_atributos(est) else []
    feicoes = dados_mod.feicoes_da_caixa(cur, schema, tabela, srid, caixa_consulta, srid_pedido,
                                         tolerancia, campos=campos)
    return dados, est, feicoes


def _precisa_atributos(est: dict) -> bool:
    return any(c.get("teste") is not None for c in est.get("classes") or [])


def _get_map(request: Request, item_id: str, auth, p: dict) -> Response:
    crs = _crs(p)
    caixa = caixa_do_pedido(_exigir(p, "bbox"), crs)
    largura = _inteiro(p, "width", 1, pintor.MAX_LADO)
    altura = _inteiro(p, "height", 1, pintor.MAX_LADO)
    formato = _formato(p)
    transparente = _booleano(p.get("transparent"), False)
    try:
        # o orçamento é tomado ANTES de consultar o banco: pedido grande demais em rajada é recusado
        # cedo, sem ocupar conexão de banco nem memória de feição
        with pool.reservar(largura, altura):
            with db.db(auth.contexto()) as cur:
                _camadas_pedidas(p, item_id, _nome_camada(item_id))
                _dados, est, feicoes = _preparar_desenho(cur, item_id, p, crs, caixa, largura, altura)
            corpo, _n = pintor.pintar(feicoes, est, caixa, largura, altura,
                                      transparente=transparente, formato=formato)
    except pool.ServidorOcupado as e:
        return Response(content=capacidades.excecao_wms(
            "ServerBusy", f"desenho ocupado ({e.em_voo:.0f} de {pool.ORCAMENTO_MPX:.0f} Mpx em voo); repita"),
            media_type=_XML, status_code=503, headers={"Retry-After": "2"})
    cabecalhos = {"Cache-Control": "private, max-age=60", "X-Plat-Feicoes": str(len(feicoes))}
    return Response(content=corpo, media_type=MIME[formato], headers=cabecalhos)


def _get_feature_info(request: Request, item_id: str, auth, p: dict) -> Response:
    crs = _crs(p)
    caixa = caixa_do_pedido(_exigir(p, "bbox"), crs)
    largura = _inteiro(p, "width", 1, pintor.MAX_LADO)
    altura = _inteiro(p, "height", 1, pintor.MAX_LADO)
    i = _inteiro(p, "i", 0, largura - 1)
    j = _inteiro(p, "j", 0, altura - 1)
    formato = (p.get("info_format") or "application/json").strip().lower()
    if formato not in [f.lower() for f in capacidades.FORMATOS_INFO]:
        raise ErroWms("InvalidFormat", f"INFO_FORMAT não suportado: {formato}")
    try:
        maximo = max(1, min(int(p.get("feature_count") or 1), 100))
    except ValueError:
        maximo = 1
    with db.db(auth.contexto()) as cur:
        _camadas_pedidas(p, item_id, _nome_camada(item_id), chave="query_layers")
        dados = _camada_do_item(cur, item_id)
        schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
        # caixa de RAIO_INFO_PX pixels em volta do ponto clicado, em unidades do CRS do pedido
        px = (caixa[2] - caixa[0]) / largura
        py = (caixa[3] - caixa[1]) / altura
        x = caixa[0] + (i + 0.5) * px
        y = caixa[3] - (j + 0.5) * py
        alvo = (x - RAIO_INFO_PX * px, y - RAIO_INFO_PX * py, x + RAIO_INFO_PX * px, y + RAIO_INFO_PX * py)
        campos = [c["nome"] for c in campos_mod.campos_da_camada(cur, schema, tabela) if c["papel"] == "atributo"]
        feicoes = dados_mod.feicoes_da_caixa(cur, schema, tabela, srid, alvo, srid_do_crs(crs), 0.0,
                                             campos=campos, limite=maximo)
    return _resposta_info(feicoes, formato, item_id, crs)


def _resposta_info(feicoes: list[dict], formato: str, item_id: str, crs: str) -> Response:
    if formato == "application/json":
        corpo = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": f["id"], "geometry": f["geometria"], "properties": f["propriedades"]}
            for f in feicoes]}
        return Response(content=json.dumps(corpo, default=str, ensure_ascii=False),
                        media_type="application/geo+json")
    if formato == "text/html":
        if not feicoes:
            return Response(content="<html><body><p>nenhuma feição neste ponto</p></body></html>",
                            media_type="text/html; charset=utf-8")
        linhas = []
        for f in feicoes:
            celulas = "".join(f"<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>"
                              for k, v in (f["propriedades"] or {}).items())
            linhas.append(f"<table><caption>feição {escape(str(f['id']))}</caption>{celulas}</table>")
        html = ("<html><head><meta charset=\"utf-8\"><title>GetFeatureInfo</title></head><body>"
                + "".join(linhas) + "</body></html>")
        return Response(content=html, media_type="text/html; charset=utf-8")
    if formato == "text/plain":
        linhas = [f"feição {f['id']}: " + ", ".join(f"{k}={v}" for k, v in (f["propriedades"] or {}).items())
                  for f in feicoes]
        return Response(content=("\n".join(linhas) or "nenhuma feição neste ponto"),
                        media_type="text/plain; charset=utf-8")
    campos_xml = []
    for f in feicoes:
        atributos = "".join(f"<{_tag(k)}>{escape(str(v))}</{_tag(k)}>" for k, v in (f["propriedades"] or {}).items())
        campos_xml.append(f'<plat:camada fid="{escape(str(f["id"]))}">{atributos}</plat:camada>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<msGMLOutput xmlns:plat="http://plataforma.local/wms">' + "".join(campos_xml) + "</msGMLOutput>")
    return Response(content=xml, media_type="application/vnd.ogc.gml")


def _tag(nome: str) -> str:
    seguro = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in str(nome))
    return f"plat:{seguro or 'campo'}"


def _get_legend(request: Request, item_id: str, auth, p: dict) -> Response:
    formato = _formato(p, ("image/png", "image/png8", "image/jpeg"))
    with db.db(auth.contexto()) as cur:
        dados = _camada_do_item(cur, item_id)
        est = estilo_mod.resolver(cur, item_id, dados, nome_estilo=(p.get("style") or "").strip(),
                                  sld_texto=_sld_do_pedido(p))
    corpo = legenda_mod.desenhar(est, formato=formato)
    return Response(content=corpo, media_type=MIME[formato], headers={"Cache-Control": "private, max-age=300"})
