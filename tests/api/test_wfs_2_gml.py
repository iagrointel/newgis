"""Portão do item L2-04-h-wfs-2-gml: WFS 2.0.0 (e 1.1.0 por compatibilidade) por token, com
GetCapabilities validado contra o XSD OFICIAL do OGC em cache local, DescribeFeatureType em XSD
gerado das colunas, GetFeature com paginação/filtro FES/GML 3.2, GetPropertyValue, consulta
armazenada GetFeatureById e Transaction pela porta de escrita única da casa.

Reusa a `FabricaCamada` do item L2-03-a (tabela real, mesma `plat.camada_preparar`) e o mesmo
padrão de retentativa do item L2-04-g contra a corrida de DDL do schema de dado compartilhado."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import psycopg2.errors
import pytest
from lxml import etree

from app.consulta import gml as gml_mod
from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import contexto, ids_por_slug

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "docs" / "xsd" / "cache" / "schemas.opengis.net"
XSD_WFS20 = CACHE / "wfs" / "2.0" / "wfs.xsd"
XSD_WFS11 = CACHE / "wfs" / "1.1.0" / "wfs.xsd"
XSD_GML32 = CACHE / "gml" / "3.2.1" / "gml.xsd"
SRID = 4674
NS = {"wfs": gml_mod.NS_WFS, "gml": gml_mod.NS_GML, "ows": gml_mod.NS_OWS,
      "plat": gml_mod.NS_PLAT}


# --------------------------------------------------------------------------------- preparação
@pytest.fixture(scope="module")
def esquema_wfs20():
    if not XSD_WFS20.exists():
        pytest.fail("cache de XSD ausente: rode docs/xsd/baixar_iso19139.py --perfil wfs20")
    return etree.XMLSchema(etree.parse(str(XSD_WFS20)))


@pytest.fixture(scope="module")
def esquema_wfs11():
    if not XSD_WFS11.exists():
        pytest.fail("cache de XSD ausente: rode docs/xsd/baixar_iso19139.py --perfil wfs20")
    return etree.XMLSchema(etree.parse(str(XSD_WFS11)))


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


def _criar_com_retentativa(fabrica, con, *args, **kwargs):
    """Mesma mitigação do item L2-04-g: `plat.camada_schema_garantir` grava no schema de dado
    COMPARTILHADO entre trilhas, e o trinco de aconselhamento só serializa quem já o carrega."""
    ultimo = None
    for tentativa in range(6):
        try:
            return fabrica.criar(*args, **kwargs)
        except psycopg2.errors.InternalError_ as e:
            if "concurrently updated" not in str(e):
                raise
            ultimo = e
            con.rollback()
            time.sleep(0.2 * (tentativa + 1))
    raise ultimo


@pytest.fixture
def camada(fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = _criar_com_retentativa(
        fabrica, conexao_plat_app, "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "area", "tipo": "double precision"},
                {"nome": "quando", "tipo": "timestamp without time zone"}],
        geometria="Point", edicao={"habilitada": True})
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


def _semear(sessao_a, camada_id, quantos=5):
    ids = []
    for i in range(quantos):
        r = sessao_a.post(f"/api/camadas/{camada_id}/edicoes", json={
            "adicionar": [{"atributos": {"nome": f"p{i}", "area": float(i),
                                          "quando": f"2026-01-{i + 1:02d}T12:00:00"},
                            "geometria": {"type": "Point", "coordinates": [-49.0 - i / 10, -27.0 - i / 10]}}],
            "crs": {"srid": 4326}})
        assert r.status_code == 200, r.text
        ids.append(r.json()["adicionar"][0]["fid"])
    return ids


def _wfs(sessao, camada_id, **p):
    p.setdefault("SERVICE", "WFS")
    p.setdefault("VERSION", "2.0.0")
    return sessao.get(f"/wfs/{camada_id}", params=p)


def _arvore(resposta) -> etree._Element:
    return etree.fromstring(resposta.content)


# --------------------------------------------------------------------------------- GetCapabilities
def test_capabilities_2_0_valida_contra_o_xsd_do_ogc(sessao_a, camada, esquema_wfs20):
    r = _wfs(sessao_a, camada["id"], REQUEST="GetCapabilities")
    assert r.status_code == 200, r.text
    doc = _arvore(r)
    esquema_wfs20.assertValid(doc)
    assert doc.get("version") == "2.0.0"
    nomes = [e.text for e in doc.iterfind(".//wfs:FeatureTypeList/wfs:FeatureType/wfs:Name", NS)]
    assert nomes == [gml_mod.tipo_qualificado(camada["id"])]
    crs = doc.findtext(".//wfs:FeatureTypeList/wfs:FeatureType/wfs:DefaultCRS", namespaces=NS)
    assert crs == "urn:ogc:def:crs:EPSG::4326"
    paginacao = [c for c in doc.iterfind(".//ows:Constraint", NS)
                 if c.get("name") == "ImplementsResultPaging"]
    assert paginacao and paginacao[0].findtext("ows:DefaultValue", namespaces=NS) == "TRUE"


def test_capabilities_1_1_0_valida_contra_o_xsd_do_ogc(sessao_a, camada, esquema_wfs11):
    r = _wfs(sessao_a, camada["id"], REQUEST="GetCapabilities", VERSION="1.1.0")
    assert r.status_code == 200, r.text
    esquema_wfs11.assertValid(_arvore(r))


def test_owslib_le_o_capabilities(sessao_a, camada):
    """Prova de cliente: a mesma biblioteca que QGIS/GDAL usam para descobrir o serviço."""
    from owslib.wfs import WebFeatureService

    r = _wfs(sessao_a, camada["id"], REQUEST="GetCapabilities")
    servico = WebFeatureService(url=f"http://testserver/wfs/{camada['id']}", version="2.0.0",
                                xml=r.content)
    tipo = gml_mod.tipo_qualificado(camada["id"])
    assert tipo in servico.contents
    operacoes = [o.name for o in servico.operations]
    for esperada in ("GetCapabilities", "DescribeFeatureType", "GetFeature"):
        assert esperada in operacoes


def test_versao_desconhecida_e_recusada(sessao_a, camada):
    r = _wfs(sessao_a, camada["id"], REQUEST="GetCapabilities", VERSION="3.9.9")
    assert r.status_code == 400
    r = _wfs(sessao_a, camada["id"], REQUEST="GetCapabilities", ACCEPTVERSIONS="9.9.9,2.0.0")
    assert r.status_code == 200


# --------------------------------------------------------------------------------- DescribeFeatureType
@pytest.fixture
def esquema_da_camada(sessao_a, camada):
    r = _wfs(sessao_a, camada["id"], REQUEST="DescribeFeatureType")
    assert r.status_code == 200, r.text
    texto = r.text.replace("http://schemas.opengis.net/gml/3.2.1/gml.xsd", XSD_GML32.as_uri())
    return etree.XMLSchema(etree.fromstring(texto.encode("utf-8")))


def test_describefeaturetype_gera_xsd_das_colunas(sessao_a, camada, esquema_da_camada):
    r = _wfs(sessao_a, camada["id"], REQUEST="DescribeFeatureType")
    doc = _arvore(r)
    elementos = {e.get("name"): e.get("type") for e in doc.iter("{http://www.w3.org/2001/XMLSchema}element")}
    assert elementos["nome"] == "xsd:string"
    assert elementos["area"] == "xsd:double"
    assert elementos["quando"] == "xsd:dateTime"
    assert elementos["geometria"] == "gml:PointPropertyType"


def test_getfeature_gml_valida_contra_o_xsd_publicado(sessao_a, camada, esquema_da_camada):
    _semear(sessao_a, camada["id"], 3)
    r = _wfs(sessao_a, camada["id"], REQUEST="GetFeature", TYPENAMES=gml_mod.tipo_qualificado(camada["id"]))
    assert r.status_code == 200, r.text
    doc = _arvore(r)
    membros = doc.findall("wfs:member/*", NS)
    assert len(membros) == 3
    for m in membros:
        esquema_da_camada.assertValid(m)


# --------------------------------------------------------------------------------- GetFeature
def test_paginacao_count_e_startindex(sessao_a, camada):
    _semear(sessao_a, camada["id"], 5)
    pagina1 = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", COUNT=2))
    pagina2 = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", COUNT=2, STARTINDEX=2))
    assert pagina1.get("numberMatched") == "5"
    assert pagina1.get("numberReturned") == "2"
    ids1 = [f.get(f"{{{gml_mod.NS_GML}}}id") for f in pagina1.findall("wfs:member/*", NS)]
    ids2 = [f.get(f"{{{gml_mod.NS_GML}}}id") for f in pagina2.findall("wfs:member/*", NS)]
    assert len(ids1) == len(ids2) == 2
    assert not set(ids1) & set(ids2)


def test_resulttype_hits_nao_traz_feicao(sessao_a, camada):
    _semear(sessao_a, camada["id"], 4)
    doc = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", RESULTTYPE="hits"))
    assert doc.get("numberMatched") == "4"
    assert doc.get("numberReturned") == "0"
    assert doc.findall("wfs:member", NS) == []


def test_bbox_srsname_e_propertyname(sessao_a, camada):
    _semear(sessao_a, camada["id"], 5)
    # BBOX na forma curta (longitude, latitude) e na forma de autoridade (latitude, longitude)
    curto = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature",
                          BBOX="-49.25,-27.25,-48.95,-26.95,EPSG:4326"))
    urn = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature",
                        BBOX="-27.25,-49.25,-26.95,-48.95,urn:ogc:def:crs:EPSG::4326"))
    assert curto.get("numberMatched") == urn.get("numberMatched") == "3"
    saida = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", PROPERTYNAME="nome", COUNT=1))
    feicao = saida.find("wfs:member/*", NS)
    marcas = [etree.QName(f).localname for f in feicao]
    assert "nome" in marcas
    assert "area" not in marcas and "geometria" not in marcas


def test_sortby_ordena(sessao_a, camada):
    _semear(sessao_a, camada["id"], 4)
    doc = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", SORTBY="area DESC"))
    areas = [float(e.text) for e in doc.iterfind(f".//{{{gml_mod.NS_PLAT}}}area")]
    assert areas == sorted(areas, reverse=True)


def test_saida_em_geojson(sessao_a, camada):
    _semear(sessao_a, camada["id"], 2)
    r = _wfs(sessao_a, camada["id"], REQUEST="GetFeature", OUTPUTFORMAT="application/json")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection"
    assert corpo["numberMatched"] == 2


def test_ordem_dos_eixos_na_saida_gml(sessao_a, camada):
    """`urn:ogc:def:crs:EPSG::4326` (padrão do WFS 2.0) sai latitude longitude; CRS84 sai ao
    contrário. O mesmo ponto, duas escritas."""
    _semear(sessao_a, camada["id"], 1)
    padrao = _wfs(sessao_a, camada["id"], REQUEST="GetFeature").text
    crs84 = _wfs(sessao_a, camada["id"], REQUEST="GetFeature",
                 SRSNAME="http://www.opengis.net/def/crs/OGC/1.3/CRS84").text
    assert "<gml:pos>-27.0 -49.0</gml:pos>" in padrao
    assert "<gml:pos>-49.0 -27.0</gml:pos>" in crs84


# --------------------------------------------------------------------------------- filtro FES x CQL2
def _filtro(miolo: str) -> str:
    return ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2">' + miolo + "</fes:Filter>")


def test_fes_comparacao_conta_o_mesmo_que_o_cql2(sessao_a, camada):
    _semear(sessao_a, camada["id"], 5)
    wfs = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", RESULTTYPE="hits",
                        FILTER=_filtro("<fes:PropertyIsGreaterThan>"
                                       "<fes:ValueReference>area</fes:ValueReference>"
                                       "<fes:Literal>1.5</fes:Literal></fes:PropertyIsGreaterThan>")))
    ogc = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                       params={"filter": "area > 1.5", "filter-lang": "cql2-text"})
    assert ogc.status_code == 200, ogc.text
    assert int(wfs.get("numberMatched")) == ogc.json()["numberMatched"] == 3


def test_fes_intersects_conta_o_mesmo_que_o_cql2(sessao_a, camada):
    _semear(sessao_a, camada["id"], 5)
    poligono = ("<gml:Polygon srsName=\"http://www.opengis.net/def/crs/OGC/1.3/CRS84\">"
                "<gml:exterior><gml:LinearRing><gml:posList>"
                "-49.25 -27.25 -48.95 -27.25 -48.95 -26.95 -49.25 -26.95 -49.25 -27.25"
                "</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>")
    wfs = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", RESULTTYPE="hits",
                        FILTER=_filtro("<fes:Intersects><fes:ValueReference>geometria</fes:ValueReference>"
                                       + poligono + "</fes:Intersects>")))
    # CQL2-text desta casa recebe geometria como GeoJSON entre aspas simples (ver app/consulta/cql2.py)
    cql = ("S_INTERSECTS(geometria, '{\"type\": \"Polygon\", \"coordinates\": "
           "[[[-49.25, -27.25], [-48.95, -27.25], [-48.95, -26.95], [-49.25, -26.95], "
           "[-49.25, -27.25]]]}')")
    ogc = sessao_a.get(f"/ogc/features/{camada['id']}/collections/0/items",
                       params={"filter": cql, "filter-lang": "cql2-text"})
    assert ogc.status_code == 200, ogc.text
    assert int(wfs.get("numberMatched")) == ogc.json()["numberMatched"] == 3


def test_fes_por_post_xml(sessao_a, camada):
    _semear(sessao_a, camada["id"], 5)
    corpo = f"""<wfs:GetFeature xmlns:wfs="{gml_mod.NS_WFS}" xmlns:fes="{gml_mod.NS_FES}"
        service="WFS" version="2.0.0" resultType="hits">
      <wfs:Query typeNames="{gml_mod.tipo_qualificado(camada['id'])}">
        <fes:Filter><fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>
          <fes:Literal>p2</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>
      </wfs:Query>
    </wfs:GetFeature>"""
    r = sessao_a.post(f"/wfs/{camada['id']}", content=corpo.encode("utf-8"),
                      headers={"content-type": "text/xml"})
    assert r.status_code == 200, r.text
    assert _arvore(r).get("numberMatched") == "1"


# --------------------------------------------------------------------------------- GetPropertyValue e stored query
def test_getpropertyvalue_devolve_valuecollection(sessao_a, camada):
    _semear(sessao_a, camada["id"], 3)
    r = _wfs(sessao_a, camada["id"], REQUEST="GetPropertyValue", VALUEREFERENCE="nome")
    assert r.status_code == 200, r.text
    doc = _arvore(r)
    assert etree.QName(doc).localname == "ValueCollection"
    valores = [e.text for e in doc.iterfind(f".//{{{gml_mod.NS_PLAT}}}nome")]
    assert sorted(valores) == ["p0", "p1", "p2"]


def test_stored_query_getfeaturebyid(sessao_a, camada):
    fids = _semear(sessao_a, camada["id"], 3)
    nome = gml_mod.nome_tipo(camada["id"])
    r = _wfs(sessao_a, camada["id"], REQUEST="GetFeature",
             STOREDQUERY_ID="urn:ogc:def:query:OGC-WFS::GetFeatureById", ID=f"{nome}.{fids[1]}")
    assert r.status_code == 200, r.text
    doc = _arvore(r)
    assert doc.get("numberMatched") == "1"
    assert doc.find("wfs:member/*", NS).get(f"{{{gml_mod.NS_GML}}}id") == f"{nome}.{fids[1]}"


def test_lista_e_descreve_consultas_armazenadas(sessao_a, camada):
    lista = _arvore(_wfs(sessao_a, camada["id"], REQUEST="ListStoredQueries"))
    ids = [e.get("id") for e in lista.iterfind(f"{{{gml_mod.NS_WFS}}}StoredQuery")]
    assert "urn:ogc:def:query:OGC-WFS::GetFeatureById" in ids
    descreve = _arvore(_wfs(sessao_a, camada["id"], REQUEST="DescribeStoredQueries"))
    assert descreve.find(f"{{{gml_mod.NS_WFS}}}StoredQueryDescription") is not None


# --------------------------------------------------------------------------------- Transaction
def test_transaction_insert_passa_pela_porta_unica_e_marca_origem_wfs(
        sessao_a, camada, conexao_plat_app):
    nome_tipo = gml_mod.nome_tipo(camada["id"])
    corpo = f"""<wfs:Transaction xmlns:wfs="{gml_mod.NS_WFS}" xmlns:gml="{gml_mod.NS_GML}"
        xmlns:plat="{gml_mod.NS_PLAT}" service="WFS" version="2.0.0">
      <wfs:Insert>
        <plat:{nome_tipo}>
          <plat:nome>inserida por wfs</plat:nome>
          <plat:area>42.5</plat:area>
          <plat:geometria><gml:Point srsName="http://www.opengis.net/def/crs/OGC/1.3/CRS84">
            <gml:pos>-49.3 -27.3</gml:pos></gml:Point></plat:geometria>
        </plat:{nome_tipo}>
      </wfs:Insert>
    </wfs:Transaction>"""
    r = sessao_a.post(f"/wfs/{camada['id']}", content=corpo.encode("utf-8"),
                      headers={"content-type": "text/xml"})
    assert r.status_code == 200, r.text
    doc = _arvore(r)
    assert doc.findtext(f".//{{{gml_mod.NS_WFS}}}totalInserted") == "1"
    rid = doc.find(f".//{{{gml_mod.NS_FES}}}ResourceId").get("rid")
    assert rid.startswith(f"{nome_tipo}.")

    lido = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature", RESOURCEID=rid))
    assert lido.get("numberMatched") == "1"
    assert lido.findtext(f".//{{{gml_mod.NS_PLAT}}}nome") == "inserida por wfs"

    conexao_plat_app.rollback()
    contexto(conexao_plat_app, camada["tenant_id"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT propriedades FROM plat.evento WHERE tipo = 'camadas/editar' "
                    "AND alvo_id = %s ORDER BY id DESC LIMIT 1", (camada["id"],))
        linha = cur.fetchone()
    conexao_plat_app.rollback()
    assert linha is not None, "a transação WFS não registrou evento de edição"
    props = linha["propriedades"]
    props = json.loads(props) if isinstance(props, str) else props
    assert props["origem"] == "wfs"
    assert props["adicionados"] == 1


def test_transaction_update_e_delete(sessao_a, camada):
    fids = _semear(sessao_a, camada["id"], 2)
    nome_tipo = gml_mod.nome_tipo(camada["id"])
    corpo = f"""<wfs:Transaction xmlns:wfs="{gml_mod.NS_WFS}" xmlns:fes="{gml_mod.NS_FES}"
        xmlns:plat="{gml_mod.NS_PLAT}" service="WFS" version="2.0.0">
      <wfs:Update typeName="plat:{nome_tipo}">
        <wfs:Property><wfs:ValueReference>nome</wfs:ValueReference><wfs:Value>trocado</wfs:Value></wfs:Property>
        <fes:Filter><fes:ResourceId rid="{nome_tipo}.{fids[0]}"/></fes:Filter>
      </wfs:Update>
      <wfs:Delete typeName="plat:{nome_tipo}">
        <fes:Filter><fes:ResourceId rid="{nome_tipo}.{fids[1]}"/></fes:Filter>
      </wfs:Delete>
    </wfs:Transaction>"""
    r = sessao_a.post(f"/wfs/{camada['id']}", content=corpo.encode("utf-8"),
                      headers={"content-type": "text/xml"})
    assert r.status_code == 200, r.text
    doc = _arvore(r)
    assert doc.findtext(f".//{{{gml_mod.NS_WFS}}}totalUpdated") == "1"
    assert doc.findtext(f".//{{{gml_mod.NS_WFS}}}totalDeleted") == "1"
    restante = _arvore(_wfs(sessao_a, camada["id"], REQUEST="GetFeature"))
    assert restante.get("numberMatched") == "1"
    assert restante.findtext(f".//{{{gml_mod.NS_PLAT}}}nome") == "trocado"


# --------------------------------------------------------------------------------- ataques do adversário
def test_count_absurdo_e_limitado_em_vez_de_derrubar(sessao_a, camada):
    _semear(sessao_a, camada["id"], 2)
    r = _wfs(sessao_a, camada["id"], REQUEST="GetFeature", COUNT=10**9)
    assert r.status_code == 200
    assert _arvore(r).get("numberReturned") == "2"


def test_xxe_no_filter_e_recusado_com_erro_nomeado(sessao_a, camada):
    ataque = ('<?xml version="1.0"?><!DOCTYPE fes:Filter [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
              '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
              "<fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>"
              "<fes:Literal>&xxe;</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>")
    r = _wfs(sessao_a, camada["id"], REQUEST="GetFeature", FILTER=ataque)
    assert r.status_code == 400
    assert r.json()["erro"] in ("xml_dtd_proibida", "xml_entidade_proibida")
    r2 = sessao_a.post(f"/wfs/{camada['id']}", content=ataque.encode("utf-8"),
                       headers={"content-type": "text/xml"})
    assert r2.status_code == 400


def test_sem_token_nao_le_nada(camada):
    from tests.api.conftest import novo_cliente

    cliente = novo_cliente()
    r = cliente.get(f"/wfs/{camada['id']}", params={"SERVICE": "WFS", "REQUEST": "GetCapabilities"})
    assert r.status_code in (401, 403)


def test_item_de_outro_inquilino_nao_aparece(sessao_b, camada):
    r = sessao_b.get(f"/wfs/{camada['id']}", params={"SERVICE": "WFS", "REQUEST": "GetCapabilities"})
    assert r.status_code in (403, 404)


# --------------------------------------------------------------------------------- GDAL relê o GML
def test_gdal_rele_o_gml_com_geometria_valida(sessao_a, camada, conexao_plat_app, tmp_path, medida):
    """Mil feições saem em GML 3.2, o GDAL reabre o arquivo, conta o mesmo que o banco e todas as
    geometrias voltam válidas e no lugar certo (a ordem dos eixos do URN 4326 inclusa)."""
    dados = camada["dados"]
    contexto(conexao_plat_app, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (nome, area, geom) '
            "SELECT 'f' || i, i::double precision, "
            f"ST_SetSRID(ST_MakePoint(-49.0 - i * 0.001, -27.0 - i * 0.001), {SRID}) "
            "FROM generate_series(1, 1000) i")
        conexao_plat_app.commit()
    contexto(conexao_plat_app, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{dados["schema"]}"."{dados["tabela"]}"')
        no_banco = cur.fetchone()["n"]
    conexao_plat_app.rollback()

    r = _wfs(sessao_a, camada["id"], REQUEST="GetFeature", COUNT=1000)
    assert r.status_code == 200, r.text[:400]
    arquivo = tmp_path / "wfs.gml"
    arquivo.write_bytes(r.content)

    saida = subprocess.run(  # noqa: S603 - binário fixo do sistema, sem entrada do cliente
        ["/usr/bin/ogrinfo", "-al", "-so", "--config", "GML_DOWNLOAD_SCHEMA", "NO", str(arquivo)],
        capture_output=True, text=True, timeout=180, check=False)
    assert saida.returncode == 0, saida.stderr[-2000:]

    from osgeo import gdal, ogr

    gdal.SetConfigOption("GML_DOWNLOAD_SCHEMA", "NO")
    fonte = ogr.Open(str(arquivo))
    assert fonte is not None, "GDAL não abriu o GML gerado"
    camada_ogr = fonte.GetLayer(0)
    lidas = validas = 0
    for feicao in camada_ogr:
        g = feicao.GetGeometryRef()
        assert g is not None
        assert g.IsValid()
        x, y = g.GetX(), g.GetY()
        assert -50.5 < x < -48.5, f"longitude fora da faixa: {x}"
        assert -28.5 < y < -26.5, f"latitude fora da faixa: {y}"
        validas += 1
        lidas += 1
    fonte = None
    assert lidas == no_banco == 1000
    medida("L2-04-h-wfs-2-gml")("gml_feicoes_relidas_gdal", lidas, "feições",
                                "ogr.Open sobre a saída GML 3.2 do GetFeature (COUNT=1000)")
    medida("L2-04-h-wfs-2-gml")("gml_geometrias_validas", validas, "feições",
                                "OGRGeometry.IsValid() em cada feição relida")
