"""Unitários do item L2-01-l: SLD 1.0.0 gerado da mesma lista de classes da legenda, política de CRS por
formato, teto de linhas e perdas declaradas. Nada aqui toca o banco."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.exportacao import motor
from app.exportacao.formatos import FORMATOS, obter
from app.exportacao.rotas import _perdas_declaradas
from app.mapa import sld
from app.mapa.simbologia import legenda

SLD_NS = {"sld": sld.SLD, "ogc": sld.OGC}


def arvore(texto: str) -> ET.Element:
    return ET.fromstring(texto)


def test_sld_tem_uma_regra_por_classe_e_as_cores_da_legenda():
    """A cláusula "estilo da camada como JSON MapLibre e como SLD 1.0" só vale se os dois desenharem o
    mesmo mapa: as cores do SLD saem da MESMA `classes()` que alimenta a legenda."""
    simb = {"tipo": "valores_unicos", "campo": "categoria", "valores": ["mata", "pasto", "urbano"]}
    texto = sld.gerar(simb, "Polygon", nome="c1", titulo="Camada")
    raiz = arvore(texto)
    regras = raiz.findall(".//sld:Rule", SLD_NS)
    entradas = legenda(simb, "Polygon")
    assert len(regras) == len(entradas) == 4  # 3 valores + "outros"
    cores_sld = [r.find(".//sld:Fill/sld:CssParameter[@name='fill']", SLD_NS).text for r in regras]
    assert cores_sld == [e["cor"] for e in entradas]
    assert [r.find("sld:Title", SLD_NS).text for r in regras] == [e["rotulo"] for e in entradas]


def test_a_classe_do_resto_usa_ElseFilter_e_nao_uma_regra_sem_filtro():
    """Uma regra sem filtro casa com TUDO: se o "outros" saísse assim, o SLD pintaria o mapa inteiro da
    cor do resto. No SLD 1.0 a classe do resto é `ElseFilter`."""
    simb = {"tipo": "valores_unicos", "campo": "categoria", "valores": ["mata"]}
    raiz = arvore(sld.gerar(simb, "Point", nome="c1"))
    regras = raiz.findall(".//sld:Rule", SLD_NS)
    assert regras[0].find("ogc:Filter", SLD_NS) is not None
    assert regras[-1].find("sld:ElseFilter", SLD_NS) is not None
    assert regras[-1].find("ogc:Filter", SLD_NS) is None


def test_sld_de_intervalos_vira_PropertyIsLessThan_no_campo_certo():
    simb = {"tipo": "intervalos", "campo": "area_ha", "cortes": [10, 50]}
    raiz = arvore(sld.gerar(simb, "LineString", nome="c1"))
    comparacoes = raiz.findall(".//ogc:PropertyIsLessThan", SLD_NS)
    assert [c.find("ogc:PropertyName", SLD_NS).text for c in comparacoes] == ["area_ha", "area_ha"]
    assert [c.find("ogc:Literal", SLD_NS).text for c in comparacoes] == ["10.0", "50.0"]


def test_rotulo_com_caractere_de_xml_sai_escapado_e_o_documento_continua_valido():
    """Rótulo de classe é dado do usuário (valor de um campo). `&`, `<` e aspas têm de sair escapados —
    a mesma razão pela qual nenhum literal de filtro entra em texto de SQL neste repositório."""
    simb = {"tipo": "valores_unicos", "campo": "categoria", "valores": ['mata & "cia" <b>']}
    texto = sld.gerar(simb, "Polygon", nome="c1")
    assert "&amp;" in texto and "&lt;" in texto
    raiz = arvore(texto)  # não levanta: o documento continua bem formado
    assert raiz.findall(".//ogc:Literal", SLD_NS)[0].text == 'mata & "cia" <b>'


def test_simbologia_simples_gera_uma_regra_sem_filtro():
    raiz = arvore(sld.gerar({"tipo": "simples", "cor": "#123456"}, "Point", nome="c1"))
    regras = raiz.findall(".//sld:Rule", SLD_NS)
    assert len(regras) == 1
    assert regras[0].find("ogc:Filter", SLD_NS) is None and regras[0].find("sld:ElseFilter", SLD_NS) is None
    assert regras[0].find(".//sld:Mark/sld:Fill/sld:CssParameter", SLD_NS).text == "#123456"


# ---------------------------------------------------------------- política de CRS por formato
@pytest.mark.parametrize(("nome", "pedido", "esperado"), [
    ("gpkg", 31983, 31983),      # livre: sai o que se pediu
    ("gpkg", None, None),        # livre sem pedido: o CRS da própria tabela
    ("geojson", None, 4326),     # preso: 4326 MESMO sem pedido (senão o rótulo mentiria)
    ("geojsonseq", None, 4326),
    ("kml", None, 4326),
    ("mvt", None, 3857),
    ("csv", 31983, 31983),       # sem CRS no arquivo, mas a reprojeção dos números vale
    ("csv", None, None),
])
def test_crs_de_saida_obedece_a_politica_do_formato(nome, pedido, esperado):
    assert motor.crs_de_saida(obter(nome), pedido) == esperado


def test_doze_formatos_reabrem_com_ogrinfo_e_nenhum_deles_e_tilado():
    """A cláusula 1 do portão fala em 12 formatos: é este conjunto, e o teste de API é quem os gera."""
    doze = [n for n, f in FORMATOS.items() if f.reabre_com_ogrinfo and not f.tilado and n != "pacote"]
    assert len(doze) == 12, sorted(doze)
    assert {"gpkg", "geojson", "geojsonseq", "shapefile", "csv", "xlsx", "kml", "kmz", "fgb", "gml",
            "dxf", "filegdb"} == set(doze)


def test_so_o_xlsx_tem_teto_de_linhas_e_ele_e_o_do_proprio_excel():
    tetos = {n: f.linhas_max for n, f in FORMATOS.items() if f.linhas_max}
    assert tetos == {"xlsx": 1_048_576}


def test_perdas_declaradas_dizem_o_que_o_formato_nao_leva():
    assert any("não guarda atributo" in p for p in _perdas_declaradas(obter("dxf"), ["nome"]))
    assert any("não guarda geometria" in p for p in _perdas_declaradas(obter("csv"), ["nome"]))
    assert any("EPSG:4326" in p for p in _perdas_declaradas(obter("geojson"), ["nome"]))
    assert any("tile" in p for p in _perdas_declaradas(obter("mvt"), ["nome"]))
    assert any("10 caracteres" in p for p in _perdas_declaradas(obter("shapefile"), ["nome"]))
    assert _perdas_declaradas(obter("gpkg"), ["nome"]) == []
