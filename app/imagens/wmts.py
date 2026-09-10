"""WMTS 1.0.0 (OGC 07-057r7) por item e por mosaico (item L1-02-tiles-token).

O documento é gerado a partir da MESMA grade que serve o ladrilho (morecantile `WebMercatorQuad`,
decisão C4 do conceito L1): quem lê o GetCapabilities e quem pede o ladrilho enxergam a mesma grade,
sem tabela paralela escrita à mão.

Duas formas de pedir o ladrilho, as duas declaradas no documento:
- KVP (`?SERVICE=WMTS&REQUEST=GetTile&...`), que é o que o QGIS usa por padrão; e
- REST (`ResourceURL` com o gabarito `{TileMatrix}/{TileCol}/{TileRow}`), que é a MESMA URL XYZ do
  serviço — de propósito: um só endereço para decorar, um só caminho de cache no nginx.

O XML é validado contra o esquema oficial pelo teste (`tests/api/imagens/test_tiles_wmts.py`), com os
XSD do OGC guardados em `tests/dados/ogc_xsd/` para a validação não depender de rede."""

from __future__ import annotations

from xml.sax.saxutils import escape

from app.imagens.tiles import TMS

NS = {
    "wmts": "http://www.opengis.net/wmts/1.0",
    "ows": "http://www.opengis.net/ows/1.1",
    "xlink": "http://www.w3.org/1999/xlink",
}
CRS_URN = "urn:ogc:def:crs:EPSG::3857"
WKSS = "urn:ogc:def:wkss:OGC:1.0:GoogleMapsCompatible"
TMS_ID = "WebMercatorQuad"


def _tile_matrix_set(zoom_min: int, zoom_max: int) -> list[str]:
    linhas = [
        "    <TileMatrixSet>",
        f"      <ows:Identifier>{TMS_ID}</ows:Identifier>",
        f"      <ows:SupportedCRS>{CRS_URN}</ows:SupportedCRS>",
        f"      <WellKnownScaleSet>{WKSS}</WellKnownScaleSet>",
    ]
    for z in range(zoom_min, zoom_max + 1):
        m = TMS.matrix(z)
        x0, y0 = m.pointOfOrigin
        linhas += [
            "      <TileMatrix>",
            f"        <ows:Identifier>{m.id}</ows:Identifier>",
            f"        <ScaleDenominator>{m.scaleDenominator:.10f}</ScaleDenominator>",
            f"        <TopLeftCorner>{x0:.10f} {y0:.10f}</TopLeftCorner>",
            f"        <TileWidth>{m.tileWidth}</TileWidth>",
            f"        <TileHeight>{m.tileHeight}</TileHeight>",
            f"        <MatrixWidth>{m.matrixWidth}</MatrixWidth>",
            f"        <MatrixHeight>{m.matrixHeight}</MatrixHeight>",
            "      </TileMatrix>",
        ]
    linhas.append("    </TileMatrixSet>")
    return linhas


def capabilities(
    *,
    base: str,
    identificador: str,
    titulo: str,
    bounds: list[float],
    zoom_min: int,
    zoom_max: int,
    formatos: list[str],
    consulta: str = "",
    resumo: str = "",
) -> str:
    """`base` é a URL do serviço COM o token no caminho (decisão C6), sem barra no fim.
    `consulta` é a parte de renderização (expressão, bandas, faixa, colormap) que o cliente escolheu:
    entra no gabarito REST e no KVP para que o mapa aberto no QGIS já traga a mesma pintura."""
    oeste, sul, leste, norte = bounds
    extra = f"?{consulta}" if consulta else ""
    kvp = f"{base}/wmts?"
    linhas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Capabilities xmlns="http://www.opengis.net/wmts/1.0"',
        '  xmlns:ows="http://www.opengis.net/ows/1.1"',
        '  xmlns:xlink="http://www.w3.org/1999/xlink"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '  xsi:schemaLocation="http://www.opengis.net/wmts/1.0'
        ' http://schemas.opengis.net/wmts/1.0/wmtsGetCapabilities_response.xsd"',
        '  version="1.0.0">',
        "  <ows:ServiceIdentification>",
        f"    <ows:Title>{escape(titulo)}</ows:Title>",
        "    <ows:ServiceType>OGC WMTS</ows:ServiceType>",
        "    <ows:ServiceTypeVersion>1.0.0</ows:ServiceTypeVersion>",
        "  </ows:ServiceIdentification>",
        "  <ows:OperationsMetadata>",
    ]
    for operacao in ("GetCapabilities", "GetTile"):
        linhas += [
            f'    <ows:Operation name="{operacao}">',
            "      <ows:DCP>",
            "        <ows:HTTP>",
            f'          <ows:Get xlink:href="{escape(kvp)}">',
            '            <ows:Constraint name="GetEncoding">',
            "              <ows:AllowedValues><ows:Value>KVP</ows:Value></ows:AllowedValues>",
            "            </ows:Constraint>",
            "          </ows:Get>",
            "        </ows:HTTP>",
            "      </ows:DCP>",
            "    </ows:Operation>",
        ]
    linhas += [
        "  </ows:OperationsMetadata>",
        "  <Contents>",
        "    <Layer>",
        f"      <ows:Title>{escape(titulo)}</ows:Title>",
    ]
    if resumo:
        linhas.append(f"      <ows:Abstract>{escape(resumo)}</ows:Abstract>")
    linhas += [
        "      <ows:WGS84BoundingBox>",
        f"        <ows:LowerCorner>{oeste:.7f} {sul:.7f}</ows:LowerCorner>",
        f"        <ows:UpperCorner>{leste:.7f} {norte:.7f}</ows:UpperCorner>",
        "      </ows:WGS84BoundingBox>",
        f"      <ows:Identifier>{escape(identificador)}</ows:Identifier>",
        '      <Style isDefault="true">',
        "        <ows:Identifier>default</ows:Identifier>",
        "      </Style>",
    ]
    for f in formatos:
        linhas.append(f"      <Format>{f}</Format>")
    linhas += [
        "      <TileMatrixSetLink>",
        f"        <TileMatrixSet>{TMS_ID}</TileMatrixSet>",
        "      </TileMatrixSetLink>",
    ]
    for f in formatos:
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[f]
        gabarito = f"{base}/{{TileMatrix}}/{{TileCol}}/{{TileRow}}.{ext}{extra}"
        linhas.append(f'      <ResourceURL format="{f}" resourceType="tile" template="{escape(gabarito)}"/>')
    linhas += ["    </Layer>"]
    linhas += _tile_matrix_set(zoom_min, zoom_max)
    linhas += ["  </Contents>", "</Capabilities>", ""]
    return "\n".join(linhas)


__all__ = ["CRS_URN", "TMS_ID", "capabilities"]
