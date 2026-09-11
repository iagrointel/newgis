"""Descoberta de camada (item L6-02-conectores-vivos, `app/conexao/descoberta.py`): parsing de WMS 1.1.1/
1.3.0, WMTS 1.0.0, WFS 2.0 (fixtures em `tests/dados/conexao/`, sem rede) e OGC API - Features/ArcGIS REST
(JSON inline). `app.conexao.seguranca.buscar_seguro` é trocado por um dublê que devolve os bytes da fixture —
o que se prova aqui é o PARSER, não a disponibilidade real de um serviço (isso é `tests/api/test_wms_publico.py`
e a prova manual contra o GeoSampa do "barra mínima" do item).

A recusa de SSRF (`test_url_insegura_recusada_antes_de_qualquer_rede`) NÃO é dublada: chama
`descobrir_camadas` de verdade contra `http://127.0.0.1:1/...`, provando que o módulo nunca contorna
`app.conexao.seguranca.validar_url` — nenhuma outra rota de rede existe neste arquivo além de
`seguranca.buscar_seguro`."""

from pathlib import Path

import pytest

from app.conexao import descoberta

FIXTURAS = Path(__file__).resolve().parents[1] / "dados" / "conexao"


class _RespostaFalsa:
    def __init__(self, corpo: bytes, content_type: str, ok: bool = True, status: int = 200, mensagem: str = "http_200"):
        self.ok = ok
        self.status = status
        self.mensagem = mensagem
        self.url_final = "http://fixture.local/capabilities"
        self.latencia_ms = 1
        self.saltos = 0
        self.corpo = corpo
        self.content_type = content_type


@pytest.fixture
def buscar_dublado(monkeypatch):
    """Substitui `descoberta.seguranca.buscar_seguro` por um dublê configurável por teste
    (`buscar_dublado.definir(bytes, content_type)`); nenhuma requisição sai desta máquina."""
    estado = {}

    def _falso(url, **kw):
        estado["url"] = url
        return estado["resposta"]

    def definir(corpo: bytes, content_type: str = "text/xml"):
        estado["resposta"] = _RespostaFalsa(corpo, content_type)

    monkeypatch.setattr(descoberta.seguranca, "buscar_seguro", _falso)
    definir.url_chamada = lambda: estado.get("url")
    return definir


def _ler(nome: str) -> bytes:
    return (FIXTURAS / nome).read_bytes()


# ---------------------------------------------------------------------------- WMS
def test_wms_1_3_0_lista_camadas_com_crs_e_extensao(buscar_dublado):
    buscar_dublado(_ler("wms_1_3_0.xml"), "text/xml")
    r = descoberta.descobrir_camadas({"tipo": "wms", "url": "https://raster.geosampa.example/geoserver/wms"})
    assert r.ok, r.mensagem
    nomes = {c.nome for c in r.camadas}
    assert nomes == {"geoportal:MOSAICO_ORTO_RGB_10CM_20CM", "geoportal:LOGRADOURO_SISTEMA_VIARIO"}
    ortofoto = next(c for c in r.camadas if c.nome == "geoportal:MOSAICO_ORTO_RGB_10CM_20CM")
    assert ortofoto.titulo == "Mosaico Ortofoto 10-20cm"
    # CRS herdado do Layer pai (EPSG:4326) + o declarado na própria camada (EPSG:3857) — as duas contam
    assert set(ortofoto.crs) == {"EPSG:4326", "EPSG:3857"}
    assert ortofoto.extensao == {
        "minx": -46.83, "miny": -24.02, "maxx": -46.36, "maxy": -23.35, "crs": "EPSG:4326",
    }


def test_wms_1_1_1_eixo_sem_namespace(buscar_dublado):
    """1.1.1 não tem namespace e usa `<SRS>`/`<LatLonBoundingBox minx=.../>` em vez de `<CRS>`/
    `<EX_GeographicBoundingBox>` — o mesmo parser (`_local` remove namespace) tem de casar os dois."""
    buscar_dublado(_ler("wms_1_1_1.xml"), "text/xml")
    r = descoberta.descobrir_camadas({"tipo": "wms", "url": "https://geoservicos.ibge.example/wms"})
    assert r.ok, r.mensagem
    assert len(r.camadas) == 1
    c = r.camadas[0]
    assert c.nome == "BDIA:geol_area"
    assert "EPSG:4674" in c.crs and "EPSG:4326" in c.crs
    assert c.extensao == {"minx": -73.99, "miny": -33.75, "maxx": -28.84, "maxy": 5.27, "crs": "EPSG:4326"}


def test_wms_url_de_capacidades_ja_com_getcapabilities_nao_duplica(buscar_dublado):
    buscar_dublado(_ler("wms_1_3_0.xml"), "text/xml")
    descoberta.descobrir_camadas({
        "tipo": "wms", "url": "https://x.example/wms?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0",
    })
    assert buscar_dublado.url_chamada() == "https://x.example/wms?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0"


# ---------------------------------------------------------------------------- WMTS
def test_wmts_resolve_crs_do_tilematrixset(buscar_dublado):
    buscar_dublado(_ler("wmts.xml"), "text/xml")
    r = descoberta.descobrir_camadas({"tipo": "wmts", "url": "https://bdgex.example/wmts"})
    assert r.ok, r.mensagem
    assert len(r.camadas) == 1
    c = r.camadas[0]
    assert c.nome == "bdgex:carta"
    assert c.titulo == "Carta Topográfica"
    # o Identifier do TileMatrixSetLink é só o NOME ("GoogleMapsCompatible"); o parser resolve para o
    # ows:SupportedCRS de verdade lido do TileMatrixSet definido em Contents (achado do T3: sem isso a
    # coluna crs mostraria o nome do conjunto de matrizes, não um código de CRS)
    assert c.crs == ["urn:ogc:def:crs:EPSG::3857"]
    assert c.extensao == {"minx": -74.0, "miny": -34.0, "maxx": -28.8, "maxy": 5.3, "crs": "EPSG:4326"}


# ---------------------------------------------------------------------------- WFS
def test_wfs_2_0_lista_feature_types(buscar_dublado):
    buscar_dublado(_ler("wfs_2_0.xml"), "text/xml")
    r = descoberta.descobrir_camadas({"tipo": "wfs", "url": "https://ana.example/wfs"})
    assert r.ok, r.mensagem
    assert len(r.camadas) == 1
    c = r.camadas[0]
    assert c.nome == "ana:bacia_hidrografica"
    assert c.titulo == "Bacia hidrográfica"
    assert set(c.crs) == {"urn:ogc:def:crs:EPSG::4674", "urn:ogc:def:crs:EPSG::4326"}
    assert c.extensao == {"minx": -73.99, "miny": -33.75, "maxx": -28.84, "maxy": 5.27, "crs": "EPSG:4326"}


# ---------------------------------------------------------------------------- OGC API - Features
def test_ogc_api_features_colecoes(buscar_dublado):
    doc = {
        "collections": [
            {
                "id": "poco_outorga", "title": "Poços de outorga",
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84", "http://www.opengis.net/def/crs/EPSG/0/4674"],
                "extent": {"spatial": {"bbox": [[-73.99, -33.75, -28.84, 5.27]], "crs": "CRS84"}},
            },
            {"id": "sem_titulo"},
        ],
    }
    buscar_dublado(__import__("json").dumps(doc).encode("utf-8"), "application/json")
    r = descoberta.descobrir_camadas({"tipo": "ogc_api", "url": "https://ana.example/ogc"})
    assert r.ok, r.mensagem
    assert {c.nome for c in r.camadas} == {"poco_outorga", "sem_titulo"}
    poco = next(c for c in r.camadas if c.nome == "poco_outorga")
    assert poco.titulo == "Poços de outorga"
    assert poco.extensao == {"minx": -73.99, "miny": -33.75, "maxx": -28.84, "maxy": 5.27, "crs": "CRS84"}
    sem_titulo = next(c for c in r.camadas if c.nome == "sem_titulo")
    assert sem_titulo.titulo == "sem_titulo"  # sem `title`: cai no próprio id, nunca um palpite
    assert sem_titulo.extensao is None


def test_ogc_api_url_ja_com_collections_nao_duplica(buscar_dublado):
    buscar_dublado(b'{"collections": []}', "application/json")
    descoberta.descobrir_camadas({"tipo": "ogc_api", "url": "https://x.example/ogc/collections"})
    assert buscar_dublado.url_chamada() == "https://x.example/ogc/collections"


# ---------------------------------------------------------------------------- ArcGIS REST
def test_esri_rest_layers_do_servico(buscar_dublado):
    doc = {
        "name": "Cadastro",
        "spatialReference": {"wkid": 4674, "latestWkid": 4674},
        "fullExtent": {"xmin": -73.99, "ymin": -33.75, "xmax": -28.84, "ymax": 5.27, "spatialReference": {"wkid": 4674}},
        "layers": [{"id": 0, "name": "imoveis"}, {"id": 1, "name": "sedes"}],
    }
    buscar_dublado(__import__("json").dumps(doc).encode("utf-8"), "application/json")
    r = descoberta.descobrir_camadas({"tipo": "esri_rest", "url": "https://mapas.example/arcgis/rest/services/Cadastro/MapServer"})
    assert r.ok, r.mensagem
    assert {c.nome for c in r.camadas} == {"0", "1"}
    imoveis = next(c for c in r.camadas if c.nome == "0")
    assert imoveis.titulo == "imoveis"
    assert imoveis.crs == ["EPSG:4674"]
    assert imoveis.extensao == {"minx": -73.99, "miny": -33.75, "maxx": -28.84, "maxy": 5.27, "crs": "EPSG:4674"}


def test_esri_rest_sem_layers_vira_1_camada_do_servico(buscar_dublado):
    """ImageServer não tem `layers`: o serviço inteiro é a única camada descobrível."""
    doc = {"name": "Ortofoto", "description": "Mosaico anual", "spatialReference": {"wkid": 3857}}
    buscar_dublado(__import__("json").dumps(doc).encode("utf-8"), "application/json")
    r = descoberta.descobrir_camadas({"tipo": "esri_rest", "url": "https://mapas.example/arcgis/rest/services/Orto/ImageServer"})
    assert r.ok, r.mensagem
    assert len(r.camadas) == 1
    assert r.camadas[0].nome == "Ortofoto"
    assert r.camadas[0].titulo == "Mosaico anual"


# ---------------------------------------------------------------------------- fronteira honesta
def test_protocolo_sem_descoberta_automatica_nunca_tenta_rede(monkeypatch):
    chamou = {"sim": False}
    monkeypatch.setattr(descoberta.seguranca, "buscar_seguro", lambda *a, **kw: chamou.update(sim=True))
    r = descoberta.descobrir_camadas({"tipo": "s3", "url": "https://bucket.example/dado.parquet"})
    assert r.ok is False
    assert "não tem descoberta automática" in r.mensagem
    assert chamou["sim"] is False


def test_documento_sem_camada_e_falha_nomeada(buscar_dublado):
    buscar_dublado(b"<WMS_Capabilities><Capability/></WMS_Capabilities>", "text/xml")
    r = descoberta.descobrir_camadas({"tipo": "wms", "url": "https://x.example/wms"})
    assert r.ok is False
    assert r.mensagem == "nenhuma_camada_encontrada_no_documento"


def test_documento_ilegivel_nao_levanta(buscar_dublado):
    buscar_dublado(b"isto nao e xml valido <<<", "text/xml")
    r = descoberta.descobrir_camadas({"tipo": "wms", "url": "https://x.example/wms"})
    assert r.ok is False
    assert r.mensagem.startswith("erro_ao_interpretar:")


# ---------------------------------------------------------------------------- SSRF (sem dublê: rede real bloqueada na validação)
def test_url_insegura_recusada_antes_de_qualquer_rede():
    """`descobrir_camadas` nunca contorna `app.conexao.seguranca.validar_url`: uma URL que resolve para
    loopback é recusada por `buscar_seguro` DENTRO da própria função de segurança, sem que este módulo
    precise saber disso — a prova é que a recusa chega até aqui com o motivo de `seguranca.py`."""
    r = descoberta.descobrir_camadas({"tipo": "wms", "url": "http://127.0.0.1:1/geoserver/wms"})
    assert r.ok is False
    assert r.mensagem.startswith("url_insegura:")
    assert "loopback" in r.mensagem


def test_url_cloud_metadata_recusada():
    r = descoberta.descobrir_camadas({"tipo": "esri_rest", "url": "http://169.254.169.254/latest/meta-data/"})
    assert r.ok is False
    assert r.mensagem.startswith("url_insegura:")
    assert "link_local" in r.mensagem
