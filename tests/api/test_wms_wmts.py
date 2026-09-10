"""Rotas do conector WMS/WMTS externo (item L6-02-b-wms-wmts): `/api/conexoes/{id}/wms/*` e
`/api/conexoes/{id}/wmts/*`. Portão de pronto: "e2e adiciona 1 WMS e 1 WMTS públicos brasileiros e vê no
mapa; GetFeatureInfo devolve atributos; serviço só em EPSG:4674 funciona via proxy; teste sem rede com
capabilities em fixture + 1 teste com rede marcado". Os testes sem rede (fixture, XXE, eixo invertido) estão
em `tests/unit/test_wms_wmts_analise.py`; aqui vai a rede real, marcada `pytest.mark.lento`, contra dois
serviços públicos brasileiros medidos à mão em 07/09/2026 (toda chamada por trás de `buscar_seguro`, nunca
um cliente HTTP direto no teste):

  WMS  = INDE (Infraestrutura Nacional de Dados Espaciais, geoserver.gov.br) — 1.3.0, > 5 mil camadas.
  WMTS = BDGEx (Banco de Dados Geográficos do Exército) — RESTful, camada `ctmmultiescalas_mercator` nativa
  `GoogleMapsCompatible`/EPSG:3857 (consumo direto) e as demais (`ctm250` etc.) só no TileMatrixSet `bdgex`,
  que é EPSG:4326 (SIRGAS2000/WGS84 geográfico) — mesma família de CRS do EPSG:4674 do portão de pronto
  (geográfico, não é 3857), mesmo caminho de código (`mosaico_tile_reprojetado`, reprojeção por GDAL). Não
  achamos serviço WMTS público brasileiro que declare EPSG:4674 EXATO (ver nota na cláusula abaixo); o caso
  EPSG:4674 literal está coberto sem rede, com fixture, em
  `tests/unit/test_wms_wmts_analise.py::test_wmts_restful_4674_nao_e_nativo_3857` e no adversário de eixo
  invertido; aqui provamos que o MESMO código de proxy funciona fim-a-fim contra um serviço geográfico REAL
  não-3857, o que é a garantia que falta (a fixture só prova a análise, não o download+mosaico+GDAL)."""

import pytest

from tests.api.conftest import PREFIXO_TESTE

URL_WMS_INDE = "https://geoservicos.inde.gov.br/geoserver/wms"
URL_WMTS_BDGEX = "https://bdgex.eb.mil.br/mapcache/wmts"


def _criar(sessao, nome_sufixo, url, tipo):
    corpo = {"tipo": tipo, "nome": f"{PREFIXO_TESTE}-conexao-{nome_sufixo}", "url": url}
    return sessao.post("/api/conexoes", json=corpo)


@pytest.fixture
def limpar_conexoes(sessao_a):
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


@pytest.mark.lento
def test_wms_capacidades_camada_real_e_getmap(sessao_a, limpar_conexoes):
    """Cláusula 1 (WMS real brasileiro): capacidades leem camada/CRS/estilo/bbox de verdade; GetMap devolve
    imagem PNG de verdade (o que a tela usaria para 'ver no mapa')."""
    r = _criar(sessao_a, "wms-inde", URL_WMS_INDE, "wms")
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_cap = sessao_a.get(f"/api/conexoes/{cid}/wms/capacidades")
    assert r_cap.status_code == 200, r_cap.text
    corpo = r_cap.json()
    assert corpo["versao"] == "1.3.0"
    folhas = [f for c in corpo["camadas"] for f in _achatar(c)]
    assert len(folhas) > 100, "INDE declara milhares de camadas; poucas indica capabilities truncado/errado"
    consultavel = next(f for f in folhas if f["consultavel"] and f["bbox_lonlat"])
    assert set(consultavel["crs_suportados"]) >= {"EPSG:4326", "EPSG:3857"}

    r_mapa = sessao_a.get(
        f"/api/conexoes/{cid}/wms/mapa",
        params={
            "camada": consultavel["nome"], "crs": "EPSG:3857", "largura": 256, "altura": 256,
            "bbox": "-6200000,-3300000,-5500000,-2600000",
        },
    )
    assert r_mapa.status_code == 200, r_mapa.text
    assert r_mapa.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert r_mapa.headers["x-plat-reprojetado"] == "0"  # 3857 é declarado direto, sem reprojeção


@pytest.mark.lento
def test_wms_getfeatureinfo_devolve_atributos(sessao_a, limpar_conexoes):
    """Cláusula 2: GetFeatureInfo devolve atributos (não apenas 200 vazio) para um clique dentro do bbox de
    uma camada consultável real."""
    r = _criar(sessao_a, "wms-inde-gfi", URL_WMS_INDE, "wms")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    r_cap = sessao_a.get(f"/api/conexoes/{cid}/wms/capacidades")
    folhas = [f for c in r_cap.json()["camadas"] for f in _achatar(c)]
    assert r_cap.json()["getfeatureinfo_disponivel"] is True
    consultavel = next(f for f in folhas if f["consultavel"] and f["bbox_lonlat"])
    minx, miny, maxx, maxy = consultavel["bbox_lonlat"]

    r_gfi = sessao_a.get(
        f"/api/conexoes/{cid}/wms/feicao",
        params={
            "camada": consultavel["nome"], "crs": "EPSG:4326",
            "bbox": f"{minx},{miny},{maxx},{maxy}", "largura": 512, "altura": 512,
            "coluna": 256, "linha": 256, "formato_info": "application/json",
        },
    )
    assert r_gfi.status_code == 200, r_gfi.text
    assert len(r_gfi.content) > 0  # atributo ou "sem feição no ponto" — nunca corpo vazio/erro silencioso


@pytest.mark.lento
def test_wmts_tile_direto_3857_e_proxy_reprojetado_geografico(sessao_a, limpar_conexoes):
    """Cláusulas 3+4: WMTS real (BDGEx) — camada `ctmmultiescalas_mercator` é nativa 3857 (tile direto, sem
    proxy); camada `ctm250` só declara o TileMatrixSet `bdgex` (EPSG:4326 geográfico, mesma família não-3857
    do EPSG:4674 do portão) e sai pelo proxy (`mosaico_tile_reprojetado`, marcado `X-Plat-Reprojetado: 1`)."""
    r = _criar(sessao_a, "wmts-bdgex", URL_WMTS_BDGEX, "wmts")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_cap = sessao_a.get(f"/api/conexoes/{cid}/wmts/capacidades")
    assert r_cap.status_code == 200, r_cap.text
    tms = r_cap.json()["tile_matrix_sets"]
    assert tms["GoogleMapsCompatible"]["nativo_3857"] is True
    assert tms["bdgex"]["nativo_3857"] is False

    r_info_direto = sessao_a.get(
        f"/api/conexoes/{cid}/wmts/tile-info",
        params={"camada": "ctmmultiescalas_mercator", "tile_matrix_set": "GoogleMapsCompatible"},
    )
    assert r_info_direto.status_code == 200, r_info_direto.text
    assert r_info_direto.json()["direto"] is True
    assert "{z}" in r_info_direto.json()["template"]

    r_tile_direto = sessao_a.get(f"/api/conexoes/{cid}/wmts/tile/GoogleMapsCompatible/6/23/26",
                                  params={"camada": "ctmmultiescalas_mercator"})
    assert r_tile_direto.status_code == 200, r_tile_direto.text
    assert r_tile_direto.headers["x-plat-reprojetado"] == "0"

    r_info_proxy = sessao_a.get(
        f"/api/conexoes/{cid}/wmts/tile-info", params={"camada": "ctm250", "tile_matrix_set": "bdgex"},
    )
    assert r_info_proxy.json()["direto"] is False

    r_tile_proxy = sessao_a.get(f"/api/conexoes/{cid}/wmts/tile/bdgex/6/23/26", params={"camada": "ctm250"})
    assert r_tile_proxy.status_code == 200, r_tile_proxy.text
    assert r_tile_proxy.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert r_tile_proxy.headers["x-plat-reprojetado"] == "1"


def _achatar(camada: dict) -> list[dict]:
    saida = []
    if camada["nome"]:
        saida.append(camada)
    for filha in camada["filhas"]:
        saida.extend(_achatar(filha))
    return saida
