"""Item L0-09-metadado-catalogo, cláusula 2 (D42): exportação de metadado ISO 19115-3 (`mdb:MD_Metadata`,
`GET /api/itens/{id}/metadado.xml?formato=19115-3`), ao lado do gerador ISO 19139/GMD padrão (mesma rota, sem
`formato=`) — mesmo mecanismo de validação offline contra o XSD oficial cacheado (`docs/xsd/cache/`, baixado
por `docs/xsd/baixar_iso19139.py --perfil iso19115-3`; sem rede em tempo de teste nem de requisição), mesma
autenticação (`catalogo:ler`) e mesmo isolamento por inquilino que `tests/api/catalogo/test_metadado_ogc.py`
já prova para o formato legado. Cobre um item vetorial (`camada_vetorial`, com todos os campos opcionais) e
um raster (`raster`, só os obrigatórios) — os dois tipos que a Vale/Esri chamariam de "vector" e "raster
dataset" no Portal for ArcGIS (docs/PARIDADE.md)."""

import json
from pathlib import Path

from lxml import etree

from app.catalogo import csw as mod_csw
from app.catalogo import metadado
from tests.api.conftest import novo_cliente

_RAIZ_XSD = Path(__file__).resolve().parents[3] / "docs" / "xsd" / "cache"
NS = {"mdb": metadado.MDB, "mri": metadado.MRI, "gco": metadado.GCO3, "gex": metadado.GEX,
      "mrl": metadado.MRL, "cit": metadado.CIT}


def _token_catalogo_ler(sessao):
    r = sessao.post("/api/tokens", json={"nome": "zt-l0-09-19115-3", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_metadado_19115_3_item_vetorial_completo_valida_contra_xsd_oficial(sessao_a, itens_a):
    it = itens_a.criar(
        "camada_vetorial",
        resumo="Resumo do item vetorial de teste",
        descricao="Descrição mais longa, com **markdown**",
        tags=["agro", "teste-zt-19115-3"],
        creditos="iAgroSat",
        termos_de_uso="Uso interno",
        extent=[-50.0, -20.0, -40.0, -10.0],
    )
    r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml", params={"formato": "19115-3"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    doc = etree.fromstring(r.content)
    assert doc.tag == f"{{{metadado.MDB}}}MD_Metadata"
    # a mesma rotina de validação que a rota usa: aqui é prova, não confiança na rota
    metadado.validar_19115_3(r.content)
    assert doc.find(".//mri:MD_DataIdentification", NS) is not None
    assert doc.find(".//gex:EX_GeographicBoundingBox", NS) is not None
    keywords = {e.text for e in doc.findall(".//mri:keyword/gco:CharacterString", NS)}
    assert "teste-zt-19115-3" in keywords
    # o formato padrão (sem ?formato=) continua sendo ISO 19139/GMD — os dois convivem
    r_padrao = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml")
    assert etree.fromstring(r_padrao.content).tag == "{http://www.isotc211.org/2005/gmd}MD_Metadata"


def test_metadado_19115_3_item_raster_minimo_tambem_valida(sessao_a, itens_a):
    """Item sem resumo, sem tags, sem extent, sem termos de uso: só os campos obrigatórios do tipo (o
    esquema JSON de `raster` — `plat.tipo_item.esquema` — exige `colecao`/`stac_id`/`perfil`/`origem`/
    `srid_nativo`; nenhum deles entra no metadado ISO, então valores sintéticos bastam aqui)."""
    it = itens_a.criar(
        "raster",
        dados={
            "colecao": "zt-teste-19115-3",
            "stac_id": "zt-teste-19115-3-item",
            "perfil": "visual",
            "origem": "referenciado",
            "srid_nativo": 4326,
        },
    )
    r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml", params={"formato": "19115-3"})
    assert r.status_code == 200
    metadado.validar_19115_3(r.content)
    doc = etree.fromstring(r.content)
    # sem xmin/extent no item: nenhum gex:EX_Extent deve aparecer (nunca inventar geometria)
    assert doc.find(".//mri:extent", NS) is None


def test_metadado_19115_3_404_item_inexistente_e_de_outro_inquilino(sessao_a, sessao_b, itens_b):
    import uuid

    assert sessao_a.get(
        f"/api/itens/{uuid.uuid4()}/metadado.xml", params={"formato": "19115-3"}
    ).status_code == 404
    de_b = itens_b.criar("mapa")
    r = sessao_a.get(f"/api/itens/{de_b['id']}/metadado.xml", params={"formato": "19115-3"})
    assert r.status_code == 404
    assert sessao_b.get(f"/api/itens/{de_b['id']}/metadado.xml", params={"formato": "19115-3"}).status_code == 200


def test_metadado_19115_3_por_token_de_servico_catalogo_ler(sessao_a, sessao_b, itens_a, itens_b):
    it = itens_a.criar("mapa")
    de_b = itens_b.criar("mapa")
    tok = _token_catalogo_ler(sessao_a)
    c = novo_cliente()
    h = {"Authorization": f"Bearer {tok}"}
    r = c.get(f"/api/itens/{it['id']}/metadado.xml", params={"formato": "19115-3"}, headers=h)
    assert r.status_code == 200
    metadado.validar_19115_3(r.content)
    # o token é do inquilino A: item de B nunca aparece, mesmo sabendo o uuid certo
    assert c.get(
        f"/api/itens/{de_b['id']}/metadado.xml", params={"formato": "19115-3"}, headers=h
    ).status_code == 404


def test_metadado_19115_3_formato_invalido_e_422(sessao_a, itens_a):
    """`formato=` só aceita `19115-3` (pattern da rota); qualquer outro valor é erro do pedido, não silêncio
    nem fallback pro padrão — testado autenticado, senão a falta de credencial (401) mascara a validação."""
    it = itens_a.criar("mapa")
    r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml", params={"formato": "19139"})
    assert r.status_code == 422


def test_csw_get_records_outputschema_19115_3_reaproveita_o_gerador_e_valida(sessao_a, itens_a):
    import secrets

    marca = "ztcsw19115" + secrets.token_hex(6)
    itens_a.criar("mapa", resumo="resumo csw 19115-3", tags=[marca], extent=[-50.0, -20.0, -40.0, -10.0])
    r = sessao_a.get(
        "/csw",
        params={"REQUEST": "GetRecords", "OUTPUTSCHEMA": mod_csw.MDB, "CONSTRAINT": f"AnyText LIKE '%{marca}%'"},
    )
    assert r.status_code == 200, r.text
    doc = etree.fromstring(r.content)
    registros = doc.findall(f".//{{{mod_csw.MDB}}}MD_Metadata")
    assert len(registros) == 1
    metadado.validar_19115_3(etree.tostring(registros[0]))


def test_csw_get_record_by_id_outputschema_alias_iso19115_3(sessao_a, itens_a):
    it = itens_a.criar("mapa", resumo="r", extent=[-50.0, -20.0, -40.0, -10.0])
    r = sessao_a.get("/csw", params={"REQUEST": "GetRecordById", "ID": it["id"], "OUTPUTSCHEMA": "iso19115-3"})
    assert r.status_code == 200, r.text
    doc = etree.fromstring(r.content)
    md = doc.find(f".//{{{mod_csw.MDB}}}MD_Metadata")
    assert md is not None
    metadado.validar_19115_3(etree.tostring(md))


def test_medidas_l0_09_19115_3(sessao_a, itens_a, medida):
    import statistics
    import time

    it = itens_a.criar(
        "camada_vetorial", resumo="r", tags=["a", "b"], creditos="c", termos_de_uso="t",
        extent=[-50, -20, -40, -10],
    )
    tempos = []
    for _ in range(5):
        ini = time.perf_counter()
        r = sessao_a.get(f"/api/itens/{it['id']}/metadado.xml", params={"formato": "19115-3"})
        tempos.append((time.perf_counter() - ini) * 1000)
        assert r.status_code == 200
    grava = medida("L0-09-metadado-catalogo")
    grava(
        "mediana_5_metadado_19115_3_xml_ms",
        round(statistics.median(tempos), 1),
        "ms",
        "mediana de 5x GET /api/itens/{id}/metadado.xml?formato=19115-3 (gera + valida contra o XSD mdb)",
    )
    manifesto = json.loads((_RAIZ_XSD / "MANIFESTO.json").read_text(encoding="utf-8"))
    grava(
        "xsd_cache_arquivos_iso19115_3",
        len(manifesto["perfis"]["iso19115-3"]["entradas"]),
        "sementes",
        "sementes do perfil iso19115-3 em docs/xsd/cache/MANIFESTO.json['perfis']",
    )
