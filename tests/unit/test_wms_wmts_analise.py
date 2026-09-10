"""Análise de GetCapabilities WMS (1.1.1 e 1.3.0) e WMTS (KVP e RESTful), sem rede — item
L6-02-b-wms-wmts. Fixtures embutidas (documentos pequenos, escritos à mão a partir da estrutura real dos
serviços GeoServer/MapServer citados na hipótese do item), analisadas por `app.conexao.wms_wmts.analisar_wms`/
`analisar_wmts`, que nunca fazem I/O de rede (a separação existe exatamente para isto)."""

from __future__ import annotations

import pytest

from app.conexao import wms_wmts as w

# --------------------------------------------------------------------------------- fixtures WMS

WMS_111_STR = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE WMT_MS_Capabilities SYSTEM "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd">
<WMT_MS_Capabilities version="1.1.1">
  <Service>
    <Name>OGC:WMS</Name>
    <Title>SIG de teste interno - WMS 1.1.1</Title>
  </Service>
  <Capability>
    <Request>
      <GetCapabilities><Format>application/vnd.ogc.wms_xml</Format></GetCapabilities>
      <GetMap>
        <Format>image/png</Format>
        <Format>image/jpeg</Format>
        <DCPType><HTTP><Get><OnlineResource xlink:href="http://exemplo.teste/wms?"
          xmlns:xlink="http://www.w3.org/1999/xlink"/></Get></HTTP></DCPType>
      </GetMap>
      <GetFeatureInfo>
        <Format>text/plain</Format>
        <Format>application/json</Format>
        <DCPType><HTTP><Get><OnlineResource xlink:href="http://exemplo.teste/wms?"
          xmlns:xlink="http://www.w3.org/1999/xlink"/></Get></HTTP></DCPType>
      </GetFeatureInfo>
    </Request>
    <Layer>
      <SRS>EPSG:4326</SRS>
      <SRS>EPSG:3857</SRS>
      <Layer queryable="1">
        <Name>municipios</Name>
        <Title>Municípios</Title>
        <Abstract>Camada de teste interno.</Abstract>
        <LatLonBoundingBox minx="-53.11" miny="-25.60" maxx="-48.05" maxy="-22.52"/>
        <Style><Name>padrao</Name><Title>Padrão</Title></Style>
      </Layer>
    </Layer>
  </Capability>
</WMT_MS_Capabilities>"""
WMS_111 = WMS_111_STR.encode("utf-8")


# WMS 1.3.0: eixo lat/lon em EPSG:4326 (Anexo B da OGC 06-042) — a caixa abaixo está escrita
# deliberadamente como (lat, lon) no <BoundingBox> para provar que `analisar_wms` devolve lon/lat.
WMS_130_EIXO_INVERTIDO_STR = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms" xmlns:xlink="http://www.w3.org/1999/xlink">
  <Service>
    <Name>WMS</Name>
    <Title>SIG de teste interno - WMS 1.3.0</Title>
  </Service>
  <Capability>
    <Request>
      <GetCapabilities><Format>text/xml</Format></GetCapabilities>
      <GetMap>
        <Format>image/png</Format>
        <DCPType><HTTP><Get><OnlineResource xlink:href="http://exemplo.teste/wms?"/></Get></HTTP></DCPType>
      </GetMap>
      <GetFeatureInfo>
        <Format>application/json</Format>
        <DCPType><HTTP><Get><OnlineResource xlink:href="http://exemplo.teste/wms?"/></Get></HTTP></DCPType>
      </GetFeatureInfo>
    </Request>
    <Layer>
      <CRS>EPSG:4326</CRS>
      <CRS>EPSG:3857</CRS>
      <Layer queryable="1">
        <Name>rodovias</Name>
        <Title>Rodovias</Title>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-53.11</westBoundLongitude>
          <eastBoundLongitude>-48.05</eastBoundLongitude>
          <southBoundLatitude>-25.60</southBoundLatitude>
          <northBoundLatitude>-22.52</northBoundLatitude>
        </EX_GeographicBoundingBox>
        <!-- BoundingBox 1.3.0/EPSG:4326: eixo (lat,lon) -> minx/miny AQUI são (lat,lon), não (lon,lat) -->
        <BoundingBox CRS="EPSG:4326" minx="-25.60" miny="-53.11" maxx="-22.52" maxy="-48.05"/>
        <Style><Name>padrao</Name><Title>Padrão</Title></Style>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""
WMS_130_EIXO_INVERTIDO = WMS_130_EIXO_INVERTIDO_STR.encode("utf-8")


# 40 MiB simulados por uma única entidade externa (XXE) referenciando /etc/passwd — o adversário do item.
# defusedxml recusa ANTES de expandir a entidade (ExternalReferenceForbidden), então o "40 MiB" nunca chega
# a existir de fato na memória: o documento em si é pequeno, só a REFERÊNCIA é maliciosa.
WMS_XXE_STR = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE WMS_Capabilities [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<WMS_Capabilities version="1.3.0">
  <Service><Name>WMS</Name><Title>&xxe;</Title></Service>
  <Capability><Layer><Layer><Name>x</Name><Title>x</Title></Layer></Layer></Capability>
</WMS_Capabilities>"""
WMS_XXE = WMS_XXE_STR.encode("utf-8")



def test_wms_111_analisado_versao_e_camada():
    cap = w.analisar_wms(WMS_111, "http://exemplo.teste/wms")
    assert cap.versao == "1.1.1"
    assert cap.titulo == "SIG de teste interno - WMS 1.1.1"
    assert cap.url_getmap == "http://exemplo.teste/wms?"
    assert "image/png" in cap.formatos_getmap
    folha = cap.por_nome("municipios")
    assert folha.titulo == "Municípios"
    assert folha.consultavel is True
    assert set(folha.crs_suportados) >= {"EPSG:4326", "EPSG:3857"}
    assert folha.bbox_lonlat == pytest.approx((-53.11, -25.60, -48.05, -22.52))
    assert folha.estilos[0].nome == "padrao"


def test_wms_130_eixo_invertido_normalizado_para_lonlat():
    """Refutação do adversário: capabilities 1.3.0 com BoundingBox em EPSG:4326 escrito (lat,lon) —
    `analisar_wms` tem de devolver (lon,lat) do MESMO jeito que o EX_GeographicBoundingBox (que não tem
    ambiguidade de eixo) já diz, e `url_getmap`/`url_getfeatureinfo` têm de escrever o BBOX de volta em
    (lat,lon) quando o pedido for para EPSG:4326 em 1.3.0."""
    cap = w.analisar_wms(WMS_130_EIXO_INVERTIDO, "http://exemplo.teste/wms")
    assert cap.versao == "1.3.0"
    folha = cap.por_nome("rodovias")
    assert folha.bbox_lonlat == pytest.approx((-53.11, -25.60, -48.05, -22.52))

    url = w.url_getmap(
        cap, camada="rodovias", crs="EPSG:4326", bbox=folha.bbox_lonlat, largura=512, altura=512,
    )
    # a URL de saída, para 1.3.0 + EPSG:4326, tem de trazer o BBOX em (lat,lon) de novo (miny,minx,maxy,maxx)
    assert "BBOX=-25.6,-53.11,-22.52,-48.05" in url
    assert "CRS=EPSG%3A4326" in url or "CRS=EPSG:4326" in url

    url_3857 = w.url_getmap(
        cap, camada="rodovias", crs="EPSG:3857", bbox=(-5000, -3000, 5000, 3000), largura=256, altura=256,
    )
    # 3857 nunca inverte eixo, em nenhuma versão
    assert "BBOX=-5000,-3000,5000,3000" in url_3857

    info_url = w.url_getfeatureinfo(
        cap, camada="rodovias", crs="EPSG:4326", bbox=folha.bbox_lonlat, largura=512, altura=512,
        coluna=100, linha=200,
    )
    assert "I=100" in info_url and "J=200" in info_url  # 1.3.0 usa I/J, não X/Y


def test_wms_xxe_nunca_resolve_entidade_externa():
    """Refutação do adversário: capabilities com ENTITY externa apontando para arquivo do sistema. defusedxml
    tem de recusar (ou ignorar a entidade), NUNCA vazar o conteúdo de /etc/passwd no título analisado."""
    with pytest.raises(w.ErroConector) as exc:
        w.analisar_wms(WMS_XXE, "http://exemplo.teste/wms")
    # defusedxml levanta EntitiesForbidden (um ValueError) para DOCTYPE com ENTITY; capturado e traduzido
    assert exc.value.motivo == "xml_invalido"


def test_wms_capabilities_maior_que_o_teto_e_recusado_pela_busca(monkeypatch):
    """Refutação do adversário: documento de 40 MiB. A defesa não é no parser (que teria de carregar tudo
    primeiro) — é em `buscar_seguro`, que corta a leitura ao passar `CONEXAO_WMS_CAPACIDADES_MAX_BYTES`
    (20 MiB). Aqui provamos que `capacidades_wms` propaga a recusa como `ErroConector`, sem nunca montar o
    corpo de 40 MiB em memória Python."""
    from app import limites
    from app.conexao import seguranca

    def _resposta_grande(*a, **k):
        assert k.get("max_bytes") == limites.CONEXAO_WMS_CAPACIDADES_MAX_BYTES
        return seguranca.ResultadoBusca(
            ok=False, status=200, mensagem="resposta_excede_limite_de_bytes",
            url_final="http://exemplo.teste/wms", latencia_ms=1, saltos=0,
        )

    monkeypatch.setattr(seguranca, "buscar_seguro", _resposta_grande)
    with pytest.raises(w.ErroConector) as exc:
        w.capacidades_wms("http://exemplo.teste/wms")
    assert "excede_limite" in exc.value.detalhe


# --------------------------------------------------------------------------------- fixtures WMTS

WMTS_KVP_3857_STR = """<?xml version="1.0" encoding="UTF-8"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <ows:ServiceIdentification><ows:Title>SIG de teste interno - WMTS KVP</ows:Title></ows:ServiceIdentification>
  <ows:OperationsMetadata>
    <ows:Operation name="GetTile">
      <ows:DCP><ows:HTTP>
        <ows:Get xlink:href="http://exemplo.teste/wmts?" xmlns:xlink="http://www.w3.org/1999/xlink"/>
      </ows:HTTP></ows:DCP>
    </ows:Operation>
  </ows:OperationsMetadata>
  <Contents>
    <Layer>
      <ows:Identifier>base</ows:Identifier>
      <ows:Title>Camada base</ows:Title>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible</TileMatrixSet></TileMatrixSetLink>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>GoogleMapsCompatible</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::3857</ows:SupportedCRS>
      <TileMatrix>
        <ows:Identifier>0</ows:Identifier>
        <ScaleDenominator>559082264.0287178</ScaleDenominator>
        <TopLeftCorner>-20037508.342789244 20037508.342789244</TopLeftCorner>
        <TileWidth>256</TileWidth><TileHeight>256</TileHeight>
        <MatrixWidth>1</MatrixWidth><MatrixHeight>1</MatrixHeight>
      </TileMatrix>
    </TileMatrixSet>
  </Contents>
</Capabilities>"""
WMTS_KVP_3857 = WMTS_KVP_3857_STR.encode("utf-8")


WMTS_RESTFUL_4674_STR = """<?xml version="1.0" encoding="UTF-8"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <ows:ServiceIdentification><ows:Title>SIG de teste interno - WMTS RESTful 4674</ows:Title></ows:ServiceIdentification>
  <Contents>
    <Layer>
      <ows:Identifier>relevo</ows:Identifier>
      <ows:Title>Relevo</ows:Title>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <TileMatrixSetLink><TileMatrixSet>SIRGAS2000</TileMatrixSet></TileMatrixSetLink>
      <ResourceURL format="image/png" resourceType="tile"
        template="http://exemplo.teste/wmts/relevo/{Style}/SIRGAS2000/{TileMatrix}/{TileRow}/{TileCol}.png"/>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>SIRGAS2000</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::4674</ows:SupportedCRS>
      <TileMatrix>
        <ows:Identifier>0</ows:Identifier>
        <ScaleDenominator>279541132.0143589</ScaleDenominator>
        <TopLeftCorner>-180 90</TopLeftCorner>
        <TileWidth>256</TileWidth><TileHeight>256</TileHeight>
        <MatrixWidth>2</MatrixWidth><MatrixHeight>1</MatrixHeight>
      </TileMatrix>
    </TileMatrixSet>
  </Contents>
</Capabilities>"""
WMTS_RESTFUL_4674 = WMTS_RESTFUL_4674_STR.encode("utf-8")



def test_wmts_kvp_3857_e_nativo_e_gera_template_direto():
    cap = w.analisar_wmts(WMTS_KVP_3857, "http://exemplo.teste/wmts")
    assert cap.titulo == "SIG de teste interno - WMTS KVP"
    tms = cap.tile_matrix_sets["GoogleMapsCompatible"]
    assert tms.crs == "EPSG:3857"
    assert tms.nativo_3857() is True
    template = w.url_wmts_tile_direta(cap, camada="base", tile_matrix_set="GoogleMapsCompatible", formato="image/png")
    assert "{z}" in template and "{x}" in template and "{y}" in template
    assert "TILEMATRIXSET=GoogleMapsCompatible" in template


def test_wmts_restful_4674_nao_e_nativo_3857():
    cap = w.analisar_wmts(WMTS_RESTFUL_4674, "http://exemplo.teste/wmts")
    tms = cap.tile_matrix_sets["SIRGAS2000"]
    assert tms.crs == "EPSG:4674"
    assert tms.nativo_3857() is False
    camada = cap.camada("relevo")
    assert camada.template_restful is not None
    assert "{TileMatrix}" in camada.template_restful
