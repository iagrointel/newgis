"""Os dois documentos `GetCapabilities` (item L2-04-i): WMS 1.3.0 (OGC 06-042) e WMTS 1.0.0
(OGC 07-057r7). Modelo de f-string com `saxutils.escape`, igual ao WFS do L2-04-h — a diferença é que
aqui o portão exige validação contra a XSD OFICIAL, então a ordem dos elementos segue a sequência do
esquema, não o gosto do autor, e o teste valida cada documento gerado contra `docs/xsd/cache`.

Duas armadilhas do WMS 1.3.0 que o 1.1.1 não tinha e que os clientes cobram:
1. `CRS` (não `SRS`), e a ORDEM DOS EIXOS de um CRS geográfico é a do banco de autoridade — em
   EPSG:4326 é latitude,longitude. O `BoundingBox` publicado aqui e o `BBOX` recebido no GetMap
   seguem essa regra (ver `rotas_wms._caixa_do_pedido`).
2. `EX_GeographicBoundingBox` é sempre longitude/latitude em graus, independente do CRS da camada.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from app.ogc_mapas import matrizes

CRS_SUPORTADOS = ("EPSG:3857", "EPSG:4326", "CRS:84", "EPSG:4674",
                  "EPSG:31981", "EPSG:31982", "EPSG:31983", "EPSG:31984", "EPSG:31985")
# CRS geográficos cujo eixo, na autoridade EPSG, é latitude,longitude (WMS 1.3.0 respeita; CRS:84 não)
CRS_LAT_LON = {"EPSG:4326", "EPSG:4674"}
FORMATOS_MAPA = ("image/png", "image/png8", "image/jpeg", "image/gif")
FORMATOS_INFO = ("application/json", "text/html", "text/plain", "application/vnd.ogc.gml")
FORMATOS_TILE = ("image/png", "image/jpeg")
MAX_LADO = 4096


def eixo_invertido(crs: str) -> bool:
    return crs.upper() in CRS_LAT_LON


def _online(href: str) -> str:
    return (f'<OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" '
            f'xlink:href={quoteattr(href)}/>')


def _operacao(nome: str, formatos, href: str) -> str:
    fs = "".join(f"<Format>{escape(f)}</Format>" for f in formatos)
    return (f"<{nome}>{fs}<DCPType><HTTP><Get>{_online(href + '?')}</Get></HTTP></DCPType></{nome}>")


def wms_capabilities(*, base: str, titulo_servico: str, camadas: list[dict], inquilino: str) -> str:
    """`camadas` = [{nome, titulo, resumo, crs_nativo, extensao4326, extensao_nativa, estilos:[{nome,titulo}],
    escala_min, escala_max, consultavel}]."""
    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd">',
        "<Service><Name>WMS</Name>",
        f"<Title>{escape(titulo_servico)}</Title>",
        f"<Abstract>Serviço WMS 1.3.0 do inquilino {escape(inquilino)} na plataforma.</Abstract>",
        _online(base),
        "<Fees>none</Fees><AccessConstraints>none</AccessConstraints>",
        f"<MaxWidth>{MAX_LADO}</MaxWidth><MaxHeight>{MAX_LADO}</MaxHeight>",
        "</Service><Capability><Request>",
        _operacao("GetCapabilities", ("text/xml",), base),
        _operacao("GetMap", FORMATOS_MAPA, base),
        _operacao("GetFeatureInfo", FORMATOS_INFO, base),
        "</Request>",
        "<Exception><Format>XML</Format><Format>INIMAGE</Format><Format>BLANK</Format></Exception>",
        f"<Layer><Title>{escape(titulo_servico)}</Title>",
        "".join(f"<CRS>{c}</CRS>" for c in CRS_SUPORTADOS),
    ]
    if camadas:
        partes.append(_caixa_geografica_uniao(camadas))
    for c in camadas:
        partes.append(_camada_wms(c))
    partes.append("</Layer></Capability></WMS_Capabilities>")
    return "".join(partes)


def _caixa_geografica_uniao(camadas: list[dict]) -> str:
    caixas = [c["extensao4326"] for c in camadas if c.get("extensao4326")]
    if not caixas:
        return _caixa_geografica((-180.0, -90.0, 180.0, 90.0))
    minx = min(b[0] for b in caixas)
    miny = min(b[1] for b in caixas)
    maxx = max(b[2] for b in caixas)
    maxy = max(b[3] for b in caixas)
    return _caixa_geografica((minx, miny, maxx, maxy))


def _caixa_geografica(b) -> str:
    """`EX_GeographicBoundingBox` é SEMPRE longitude/latitude em grau decimal (WMS 1.3.0, 7.2.4.6.6)."""
    return ("<EX_GeographicBoundingBox>"
            f"<westBoundLongitude>{b[0]:.6f}</westBoundLongitude>"
            f"<eastBoundLongitude>{b[2]:.6f}</eastBoundLongitude>"
            f"<southBoundLatitude>{b[1]:.6f}</southBoundLatitude>"
            f"<northBoundLatitude>{b[3]:.6f}</northBoundLatitude>"
            "</EX_GeographicBoundingBox>")


def _caixa(crs: str, b) -> str:
    """`BoundingBox` na ordem de eixo do CRS: em EPSG:4326/4674 é (lat, lon), nos projetados é (x, y)."""
    if eixo_invertido(crs):
        return f'<BoundingBox CRS="{crs}" minx="{b[1]:.6f}" miny="{b[0]:.6f}" maxx="{b[3]:.6f}" maxy="{b[2]:.6f}"/>'
    return f'<BoundingBox CRS="{crs}" minx="{b[0]:.6f}" miny="{b[1]:.6f}" maxx="{b[2]:.6f}" maxy="{b[3]:.6f}"/>'


def _camada_wms(c: dict) -> str:
    p = [f'<Layer queryable="{1 if c.get("consultavel", True) else 0}" opaque="0">',
         f"<Name>{escape(c['nome'])}</Name><Title>{escape(c['titulo'])}</Title>"]
    if c.get("resumo"):
        p.append(f"<Abstract>{escape(c['resumo'])}</Abstract>")
    p.append("".join(f"<CRS>{x}</CRS>" for x in CRS_SUPORTADOS))
    if c.get("extensao4326"):
        p.append(_caixa_geografica(c["extensao4326"]))
        p.append(_caixa("EPSG:4326", c["extensao4326"]))
        p.append(_caixa("CRS:84", c["extensao4326"]))
    if c.get("extensao_nativa") and c.get("crs_nativo") and c["crs_nativo"] not in ("EPSG:4326", "CRS:84"):
        p.append(_caixa(c["crs_nativo"], c["extensao_nativa"]))
    for e in c.get("estilos") or []:
        legenda = ""
        if e.get("legenda_url"):
            legenda = (f'<LegendURL width="{e.get("legenda_largura", 20)}" height="{e.get("legenda_altura", 20)}">'
                       f"<Format>image/png</Format>{_online(e['legenda_url'])}</LegendURL>")
        p.append(f"<Style><Name>{escape(e['nome'])}</Name><Title>{escape(e['titulo'])}</Title>{legenda}</Style>")
    if c.get("escala_min") is not None:
        p.append(f"<MinScaleDenominator>{c['escala_min']}</MinScaleDenominator>")
    if c.get("escala_max") is not None:
        p.append(f"<MaxScaleDenominator>{c['escala_max']}</MaxScaleDenominator>")
    p.append("</Layer>")
    return "".join(p)


def wmts_capabilities(*, base: str, base_rest: str, titulo_servico: str, camadas: list[dict],
                      z_min: int = 0, z_max: int = matrizes.ZOOM_MAX) -> str:
    """`camadas` = [{nome, titulo, resumo, extensao4326, estilos:[{nome, titulo, padrao}], z_min, z_max}]."""
    ns = ('xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1" '
          'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
          'xsi:schemaLocation="http://www.opengis.net/wmts/1.0 '
          'http://schemas.opengis.net/wmts/1.0/wmtsGetCapabilities_response.xsd"')
    p = ['<?xml version="1.0" encoding="UTF-8"?>', f'<Capabilities version="1.0.0" {ns}>',
         "<ows:ServiceIdentification>", f"<ows:Title>{escape(titulo_servico)}</ows:Title>",
         "<ows:ServiceType>OGC WMTS</ows:ServiceType><ows:ServiceTypeVersion>1.0.0</ows:ServiceTypeVersion>",
         "<ows:Fees>none</ows:Fees><ows:AccessConstraints>none</ows:AccessConstraints>",
         "</ows:ServiceIdentification>",
         "<ows:OperationsMetadata>",
         _operacao_ows("GetCapabilities", base), _operacao_ows("GetTile", base),
         _operacao_ows("GetFeatureInfo", base),
         "</ows:OperationsMetadata><Contents>"]
    for c in camadas:
        p.append(_camada_wmts(c, base_rest))
    p.append(_matriz_set(z_min, z_max))
    p.append("</Contents>")
    p.append(f'<ServiceMetadataURL xlink:href={quoteattr(base_rest + "/WMTSCapabilities.xml")}/>')
    p.append("</Capabilities>")
    return "".join(p)


def _operacao_ows(nome: str, base: str) -> str:
    return (f'<ows:Operation name="{nome}"><ows:DCP><ows:HTTP>'
            f'<ows:Get xlink:href={quoteattr(base + "?")}>'
            '<ows:Constraint name="GetEncoding"><ows:AllowedValues><ows:Value>KVP</ows:Value>'
            "</ows:AllowedValues></ows:Constraint></ows:Get></ows:HTTP></ows:DCP></ows:Operation>")


def _camada_wmts(c: dict, base_rest: str) -> str:
    b = c.get("extensao4326") or (-180.0, -90.0, 180.0, 90.0)
    p = ["<Layer>", f"<ows:Title>{escape(c['titulo'])}</ows:Title>"]
    if c.get("resumo"):
        p.append(f"<ows:Abstract>{escape(c['resumo'])}</ows:Abstract>")
    p.append("<ows:WGS84BoundingBox>"
             f"<ows:LowerCorner>{b[0]:.6f} {b[1]:.6f}</ows:LowerCorner>"
             f"<ows:UpperCorner>{b[2]:.6f} {b[3]:.6f}</ows:UpperCorner></ows:WGS84BoundingBox>")
    p.append(f"<ows:Identifier>{escape(c['nome'])}</ows:Identifier>")
    for e in c.get("estilos") or [{"nome": "padrao", "titulo": "padrão", "padrao": True}]:
        padrao = ' isDefault="true"' if e.get("padrao") else ""
        p.append(f"<Style{padrao}><ows:Title>{escape(e['titulo'])}</ows:Title>"
                 f"<ows:Identifier>{escape(e['nome'])}</ows:Identifier></Style>")
    p.extend(f"<Format>{f}</Format>" for f in FORMATOS_TILE)
    p.append(f"<TileMatrixSetLink><TileMatrixSet>{matrizes.IDENTIFICADOR}</TileMatrixSet></TileMatrixSetLink>")
    modelo = (f"{base_rest}/{escape(c['nome'])}/{{Style}}/{{TileMatrixSet}}/{{TileMatrix}}/{{TileRow}}/"
              "{TileCol}.png")
    p.append(f'<ResourceURL format="image/png" resourceType="tile" template={quoteattr(modelo)}/>')
    p.append("</Layer>")
    return "".join(p)


def _matriz_set(z_min: int, z_max: int) -> str:
    p = [f"<TileMatrixSet><ows:Identifier>{matrizes.IDENTIFICADOR}</ows:Identifier>",
         "<ows:SupportedCRS>urn:ogc:def:crs:EPSG::3857</ows:SupportedCRS>",
         "<WellKnownScaleSet>urn:ogc:def:wkss:OGC:1.0:GoogleMapsCompatible</WellKnownScaleSet>"]
    for m in matrizes.matrizes(z_min, z_max):
        canto = m["canto_superior_esquerdo"]
        p.append("<TileMatrix>"
                 f"<ows:Identifier>{m['identificador']}</ows:Identifier>"
                 f"<ScaleDenominator>{m['denominador_escala']:.10f}</ScaleDenominator>"
                 f"<TopLeftCorner>{canto[0]:.10f} {canto[1]:.10f}</TopLeftCorner>"
                 f"<TileWidth>{m['largura_tile']}</TileWidth><TileHeight>{m['altura_tile']}</TileHeight>"
                 f"<MatrixWidth>{m['colunas']}</MatrixWidth><MatrixHeight>{m['linhas']}</MatrixHeight>"
                 "</TileMatrix>")
    p.append("</TileMatrixSet>")
    return "".join(p)


def excecao_wms(codigo: str, mensagem: str) -> str:
    """`ServiceExceptionReport` 1.3.0 — o corpo de erro que todo cliente WMS sabe ler."""
    cod = f' code="{escape(codigo)}"' if codigo else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://www.opengis.net/ogc http://schemas.opengis.net/wms/1.3.0/exceptions_1_3_0.xsd">'
            f"<ServiceException{cod}>{escape(mensagem)}</ServiceException></ServiceExceptionReport>")


def excecao_ows(codigo: str, mensagem: str, localizador: str | None = None) -> str:
    """`ows:ExceptionReport` 1.1.0 — o corpo de erro do WMTS."""
    loc = f' locator="{escape(localizador)}"' if localizador else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<ExceptionReport xmlns="http://www.opengis.net/ows/1.1" version="1.1.0" xml:lang="pt" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsAll.xsd">'
            f'<Exception exceptionCode="{escape(codigo)}"{loc}>'
            f"<ExceptionText>{escape(mensagem)}</ExceptionText></Exception></ExceptionReport>")
