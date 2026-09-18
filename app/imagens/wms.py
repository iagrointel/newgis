"""WMS 1.3.0 (OGC 06-042, esquema `capabilities_1_3_0.xsd`) por token — item L1-02-g-wms-1-3-0-raster.

Nasce do mesmo motivo que trouxe WMTS/tiles: o cliente que só sabe "Adicionar camada WMS" (muita
prefeitura, muito QGIS antigo, o Portal/AGOL aceita WMS de terceiro) não tem outra porta de entrada
para o raster desta plataforma. `GetMap` reusa a leitura de pixel de `app/imagens/tiles.py::recorte`
(a função IRMÃ de `ladrilho`, ver o comentário lá); este módulo só serializa XML.

O DEFEITO CLÁSSICO do WMS 1.3.0 — e a razão de existir `EIXO_TROCADO` abaixo — é a ordem de eixo do
`BBOX`/`BoundingBox`: no WMS 1.1.1 (e em CRS:84) a ordem é sempre longitude,latitude (x,y). No WMS
1.3.0, a especificação manda usar a ordem de eixo DECLARADA pela autoridade do CRS (Annex B.3/B.4 da
06-042), e o registro EPSG declara EPSG:4326 como (latitude, longitude) — então em EPSG:4326 o `BBOX`
vem miny,minx,maxy,maxx (sul,oeste,norte,leste), o INVERSO do que qualquer humano espera. EPSG:3857
(Web Mercator) é (easting, northing) = (x, y) normal, sem troca. Confundir os dois é o erro mais comum
de implementação de WMS 1.3.0 (o próprio OGC CITE tem caso de teste dedicado a isso) — por isso todo
bbox que atravessa a fronteira wms.py <-> tiles.py já vem/vai SEMPRE na ordem normal (oeste,sul,leste,
norte); a troca de eixo mora só nas duas pontas deste arquivo (`bbox_do_parametro` / `bbox_para_atributo`).

Cobertura desta passagem (linha viva em `docs/PARIDADE.md`):
  feito    - GetCapabilities (uma `<Layer>` por item raster do token, `EX_GeographicBoundingBox`,
             `BoundingBox` em EPSG:4326 e EPSG:3857 com o eixo correto nos dois); GetMap (LAYERS, CRS,
             BBOX, WIDTH, HEIGHT, FORMAT image/png|image/jpeg, TRANSPARENT, STYLES=vazio/default);
             `ServiceExceptionReport` para todo erro de domínio WMS (nunca 500 mudo).
             GetFeatureInfo (INFO_FORMAT application/json e text/plain; valor por banda no pixel
             pedido por I/J, lido com `rio_tiler.Reader.point`, o MESMO caminho de `identify` do
             ImageServer e de `/ponto`).
  fora     - SLD_BODY/SLD (recusado explicitamente, nunca interpretado — ver `rotas_wms.py`);
             TIME/dimensão; `UpdateSequence`; camadas com múltiplos `STYLES` nomeados."""

from __future__ import annotations

from xml.sax.saxutils import escape

from rasterio.warp import transform_bounds

NS_WMS = "http://www.opengis.net/wms"
NS_XLINK = "http://www.w3.org/1999/xlink"
NS_OGC = "http://www.opengis.net/ogc"
VERSAO = "1.3.0"
FORMATOS_MAPA = ("image/png", "image/jpeg")
FORMATOS_INFO = ("application/json", "text/plain")
# (conserto L1-02-g, 17/09) A hipótese do item lista EPSG:3857/4326/4674/31981-31985; a fachada só
# declarava dois. O motor de pixel (`app/imagens/tiles.py::recorte`) sempre aceitou qualquer EPSG via
# pyproj — a limitação era só desta lista. EPSG:4674 é o SIRGAS2000 geográfico, referência oficial do
# Brasil (IBGE); 31981-31985 são SIRGAS2000 / UTM 21S a 25S, que é o que a maioria das prefeituras usa.
CRS_SUPORTADOS = (
    "EPSG:4326", "EPSG:3857", "EPSG:4674",
    "EPSG:31981", "EPSG:31982", "EPSG:31983", "EPSG:31984", "EPSG:31985",
)

# CRS cujo BBOX/BoundingBox troca de eixo no 1.3.0 (latitude antes de longitude). Fora daqui, a ordem é
# a "normal" (x,y = leste,norte). Ver docstring do módulo. EPSG:4674, como todo CRS geográfico do
# registro EPSG, é declarado (latitude, longitude) — mesma armadilha do 4326; as UTM (31981-31985) são
# (easting, northing) e ficam de fora.
EIXO_TROCADO = {"EPSG:4326", "EPSG:4674"}


def normalizar_crs(valor: str | None) -> str | None:
    """'EPSG:4326', 'epsg:4326' ou 'urn:ogc:def:crs:EPSG::4326' -> 'EPSG:4326'; None se não reconhecido."""
    if not valor:
        return None
    v = valor.strip().upper()
    if v.startswith("URN:OGC:DEF:CRS:EPSG:") or v.startswith("URN:OGC:DEF:CRS:EPSG::"):
        v = "EPSG:" + v.rsplit(":", 1)[-1]
    if v in CRS_SUPORTADOS:
        return v
    return None


def bbox_do_parametro(crs: str, partes: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """O `BBOX=` do GetMap, na ordem que o CLIENTE mandou -> (oeste, sul, leste, norte) sempre normal.
    Em EPSG:4326 o cliente manda (miny,minx,maxy,maxx) = (sul,oeste,norte,leste); a função devolve
    (oeste,sul,leste,norte)."""
    a, b, c, d = partes
    if crs in EIXO_TROCADO:
        sul, oeste, norte, leste = a, b, c, d
        return (oeste, sul, leste, norte)
    return (a, b, c, d)


def bbox_para_atributo(
    crs: str, oeste: float, sul: float, leste: float, norte: float,
) -> tuple[float, float, float, float]:
    """O inverso de `bbox_do_parametro`: (oeste,sul,leste,norte) normal -> (minx,miny,maxx,maxy) do
    jeito que o `<BoundingBox>` do GetCapabilities tem de escrever para este CRS."""
    if crs in EIXO_TROCADO:
        return (sul, oeste, norte, leste)
    return (oeste, sul, leste, norte)


def service_exception(mensagem: str, codigo: str | None = None) -> str:
    """`ServiceExceptionReport` (OGC 06-042 Annex A / `exceptions_1_3_0.xsd`). `codigo`, quando dado, é
    um dos códigos padrão da tabela E.1 (InvalidFormat, InvalidCRS, LayerNotDefined, StyleNotDefined,
    LayerNotQueryable, InvalidPoint, MissingDimensionValue, InvalidDimensionValue,
    OperationNotSupported) — sem `code`, o elemento fica sem atributo (também válido no XSD)."""
    atributo = f' code="{escape(codigo)}"' if codigo else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ServiceExceptionReport version="{VERSAO}" xmlns="{NS_OGC}" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="{NS_OGC} http://schemas.opengis.net/wms/1.3.0/exceptions_1_3_0.xsd">\n'
        f"  <ServiceException{atributo}>{escape(mensagem)}</ServiceException>\n"
        "</ServiceExceptionReport>\n"
    )


def _finito(v: float) -> bool:
    return v == v and v not in (float("inf"), float("-inf"))


def _estilo_xml(item_id: str, nome: str, titulo: str, legend_href: str, indent: str) -> list[str]:
    """`<Style>` (OGC 06-042 §7.2.4.6.5) com `<LegendURL>` apontando para `GetLegendGraphic` — item
    L1-02-f: cada predefinição de renderização compatível com o item (fábrica cujo `min_bandas` cabe +
    predefinições custom do inquilino) vira um estilo nomeado, do jeito que um cliente WMS de verdade
    (QGIS "Estilos") já sabe listar e trocar sem inventar parâmetro nenhum."""
    return [
        f'{indent}  <Style>',
        f"{indent}    <Name>{escape(nome)}</Name>",
        f"{indent}    <Title>{escape(titulo)}</Title>",
        f'{indent}    <LegendURL width="240" height="56">',
        '      <Format>image/png</Format>',
        f'      <OnlineResource xlink:type="simple" xlink:href="{escape(legend_href)}"/>',
        f"{indent}    </LegendURL>",
        f"{indent}  </Style>",
    ]


def _camada_xml(item: dict, indent: str = "      ") -> list[str]:
    oeste, sul, leste, norte = item["bounds"]
    linhas = [
        f"{indent}<Layer queryable=\"1\" opaque=\"0\">",  # GetFeatureInfo implementado (L1-02-g)
        f"{indent}  <Name>{escape(item['item_id'])}</Name>",
        f"{indent}  <Title>{escape(item['titulo'])}</Title>",
    ]
    if item.get("resumo"):
        linhas.append(f"{indent}  <Abstract>{escape(item['resumo'])}</Abstract>")
    for crs in CRS_SUPORTADOS:
        linhas.append(f"{indent}  <CRS>{crs}</CRS>")
    linhas += [
        f"{indent}  <EX_GeographicBoundingBox>",
        f"{indent}    <westBoundLongitude>{oeste:.7f}</westBoundLongitude>",
        f"{indent}    <eastBoundLongitude>{leste:.7f}</eastBoundLongitude>",
        f"{indent}    <southBoundLatitude>{sul:.7f}</southBoundLatitude>",
        f"{indent}    <northBoundLatitude>{norte:.7f}</northBoundLatitude>",
        f"{indent}  </EX_GeographicBoundingBox>",
    ]
    for crs in CRS_SUPORTADOS:
        if crs == "EPSG:4326":
            o, sl, le, no = oeste, sul, leste, norte
        else:
            # projetada ou geográfica, a regra é a mesma: reprojetar o retângulo de 4326 para o CRS
            # declarado. `transform_bounds` de um CRS UTM fora da zona do dado devolve infinito — a
            # camada simplesmente não anuncia esse BoundingBox (o `<CRS>` continua anunciado, porque o
            # GetMap aceita; é o que o GeoServer também faz).
            try:
                o, sl, le, no = transform_bounds("EPSG:4326", crs, oeste, sul, leste, norte)
            except Exception:  # noqa: BLE001 — CRS impossível para este retângulo: pular, nunca quebrar
                continue
            if not all(_finito(v) for v in (o, sl, le, no)):
                continue
        minx, miny, maxx, maxy = bbox_para_atributo(crs, o, sl, le, no)
        linhas.append(
            f'{indent}  <BoundingBox CRS="{crs}" minx="{minx:.7f}" miny="{miny:.7f}" '
            f'maxx="{maxx:.7f}" maxy="{maxy:.7f}"/>'
        )
    # (10/09) `<Style>` vem DEPOIS de EX_GeographicBoundingBox e BoundingBox: a sequência de `<Layer>` no
    # 1.3.0 (OGC 06-042, esquema oficial) é Name, Title, Abstract, KeywordList, CRS*,
    # EX_GeographicBoundingBox, BoundingBox*, Dimension*, Attribution, AuthorityURL*, Identifier*,
    # MetadataURL*, DataURL*, FeatureListURL*, Style*, Min/MaxScaleDenominator, Layer*. Com o Style logo
    # após os CRS, o xmllint reprovava cada camada ("EX_GeographicBoundingBox: this element is not
    # expected") — GetCapabilities inválido para cliente com parser estrito.
    for estilo in item.get("estilos") or []:
        linhas += _estilo_xml(item["item_id"], estilo["nome"], estilo["titulo"], estilo["legend_href"], indent)
    linhas.append(f"{indent}</Layer>")
    return linhas


def capabilities(*, base: str, titulo: str, resumo: str, camadas: list[dict], largura_max: int,
                 altura_max: int) -> str:
    """`base` é a URL de serviço COM o token no caminho (mesma decisão C6 do WMTS), sem barra no fim.
    `camadas`: lista de {item_id, titulo, resumo, bounds=[oeste,sul,leste,norte] em EPSG:4326}."""
    onlineresource = f'<OnlineResource xlink:type="simple" xlink:href="{escape(base + "/wms?")}"/>'
    linhas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<WMS_Capabilities version="{VERSAO}" xmlns="{NS_WMS}" xmlns:xlink="{NS_XLINK}"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        f'  xsi:schemaLocation="{NS_WMS} http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd">',
        "  <Service>",
        "    <Name>WMS</Name>",
        f"    <Title>{escape(titulo)}</Title>",
        f"    <Abstract>{escape(resumo)}</Abstract>",
        f"    {onlineresource}",
        f"    <MaxWidth>{largura_max}</MaxWidth>",
        f"    <MaxHeight>{altura_max}</MaxHeight>",
        "  </Service>",
        "  <Capability>",
        "    <Request>",
        "      <GetCapabilities>",
        "        <Format>text/xml</Format>",
        "        <DCPType><HTTP><Get>",
        f"          {onlineresource}",
        "        </Get></HTTP></DCPType>",
        "      </GetCapabilities>",
        "      <GetMap>",
    ]
    for f in FORMATOS_MAPA:
        linhas.append(f"        <Format>{f}</Format>")
    linhas += [
        "        <DCPType><HTTP><Get>",
        f"          {onlineresource}",
        "        </Get></HTTP></DCPType>",
        "      </GetMap>",
        "      <GetFeatureInfo>",
    ]
    for f in FORMATOS_INFO:
        linhas.append(f"        <Format>{f}</Format>")
    linhas += [
        "        <DCPType><HTTP><Get>",
        f"          {onlineresource}",
        "        </Get></HTTP></DCPType>",
        "      </GetFeatureInfo>",
        # (10/09) `GetLegendGraphic` NÃO entra em `<Request>`: no 1.3.0 ele não existe no esquema base
        # (é do perfil SLD, `sld:GetLegendGraphic` em outro namespace), e declará-lo aqui torna o
        # GetCapabilities INVÁLIDO para cliente com parser estrito. O caminho padrão de descoberta é o
        # `<LegendURL>` dentro de `<Style>`, que é do esquema base e está em cada camada; a operação
        # continua atendida quando chamada direto.
        "    </Request>",
        "    <Exception>",
        "      <Format>text/xml</Format>",
        "    </Exception>",
        "    <Layer>",
        f"      <Title>{escape(titulo)}</Title>",
    ]
    for crs in CRS_SUPORTADOS:
        linhas.append(f"      <CRS>{crs}</CRS>")
    for item in camadas:
        linhas += _camada_xml(item)
    linhas += ["    </Layer>", "  </Capability>", "</WMS_Capabilities>", ""]
    return "\n".join(linhas)


__all__ = [
    "CRS_SUPORTADOS", "EIXO_TROCADO", "FORMATOS_INFO", "FORMATOS_MAPA", "VERSAO",
    "bbox_do_parametro", "bbox_para_atributo", "capabilities", "normalizar_crs", "service_exception",
]
