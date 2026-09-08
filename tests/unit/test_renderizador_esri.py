"""Conversão estilo MapLibre -> drawingInfo do FeatureServer (item L2-04-b, app/consulta/renderizador.py).

Sem banco e sem rede: a conversão é função pura, e é onde mora o risco de o mapa do cliente sair com
a classificação errada."""

import pytest

from app.consulta.renderizador import cor_para_esri, para_drawing_info


@pytest.mark.parametrize(("entrada", "esperado"), [
    ("#ff0000", [255, 0, 0, 255]),
    ("#f00", [255, 0, 0, 255]),
    ("#ff000080", [255, 0, 0, 128]),
    ("rgb(1, 2, 3)", [1, 2, 3, 255]),
    ("rgba(1,2,3,0.5)", [1, 2, 3, 128]),
    ([9, 8, 7], [9, 8, 7, 255]),
])
def test_cor_reconhecida(entrada, esperado):
    assert cor_para_esri(entrada) == esperado


@pytest.mark.parametrize("entrada", ["verde", "#ff00", None, 3, "rgb(1,2)"])
def test_cor_nao_reconhecida_devolve_none(entrada):
    assert cor_para_esri(entrada) is None


def test_opacidade_do_paint_entra_no_canal_alfa():
    d = para_drawing_info({"type": "fill", "paint": {"fill-color": "#ff0000", "fill-opacity": 0.5}})
    assert d["renderer"]["type"] == "simple"
    assert d["renderer"]["symbol"]["color"] == [255, 0, 0, 128]
    assert d["renderer"]["symbol"]["type"] == "esriSFS"
    assert d["transparency"] == 50


def test_linha_e_ponto_usam_a_familia_de_simbolo_certa():
    linha = para_drawing_info({"type": "line", "paint": {"line-color": "#123456", "line-width": 2.5}})
    assert linha["renderer"]["symbol"]["type"] == "esriSLS"
    assert linha["renderer"]["symbol"]["width"] == 2.5
    ponto = para_drawing_info({"type": "circle", "paint": {"circle-color": "#123456", "circle-radius": 4}})
    assert ponto["renderer"]["symbol"]["type"] == "esriSMS"
    assert ponto["renderer"]["symbol"]["size"] == 8.0


def test_match_vira_unique_value_com_valores_e_padrao():
    d = para_drawing_info({"type": "fill", "paint": {
        "fill-color": ["match", ["get", "classe"], "mata", "#0a0", "pasto", "#cc0", "#cccccc"]}})
    r = d["renderer"]
    assert r["type"] == "uniqueValue" and r["field1"] == "classe"
    assert [i["value"] for i in r["uniqueValueInfos"]] == ["mata", "pasto"]
    assert r["uniqueValueInfos"][0]["symbol"]["color"] == [0, 170, 0, 255]
    assert r["defaultSymbol"]["color"] == [204, 204, 204, 255]


def test_step_vira_class_breaks_com_faixas_encadeadas():
    d = para_drawing_info({"type": "fill", "paint": {
        "fill-color": ["step", ["get", "pop"], "#eeeeee", 100, "#ff0000", 1000, "#990000"]}})
    r = d["renderer"]
    assert r["type"] == "classBreaks" and r["field"] == "pop"
    faixas = [(i["classMinValue"], i["classMaxValue"]) for i in r["classBreakInfos"]]
    assert faixas == [(None, 100), (100, 1000), (1000, None)]


def test_expressao_nao_convertivel_cai_em_simple_e_diz_por_que():
    d = para_drawing_info({"type": "fill", "paint": {
        "fill-color": ["interpolate", ["linear"], ["get", "x"], 0, "#fff", 1, "#000"]}})
    assert d["renderer"]["type"] == "simple"
    assert d["_conversao"] == "expressao nao convertida"
    assert d["renderer"]["symbol"]["color"] == [128, 128, 128, 255]


def test_match_com_cor_invalida_nao_inventa_classificacao():
    d = para_drawing_info({"type": "fill", "paint": {
        "fill-color": ["match", ["get", "c"], "a", "azulado", "#ccc"]}})
    assert d["renderer"]["type"] == "simple" and d["_conversao"] == "expressao nao convertida"


def test_rotulo_do_layout_vira_labeling_info():
    d = para_drawing_info({"type": "fill", "paint": {"fill-color": "#fff"},
                           "layout": {"text-field": ["get", "nome"], "text-size": 13}})
    assert d["labelingInfo"][0]["labelExpressionInfo"]["expression"] == "$feature.nome"
    assert d["labelingInfo"][0]["symbol"]["font"]["size"] == 13.0


def test_estilo_ausente_devolve_renderer_valido():
    d = para_drawing_info(None)
    assert d["renderer"]["type"] == "simple" and d["_conversao"] == "sem cor no estilo"
