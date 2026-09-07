"""Manifesto de ferramenta validado na importação (item L2-05-a; `make check` roda isto): parâmetro sem tipo,
tipo fora do vocabulário GP, saída ausente, assinatura errada = ErroRegistro; normalização dos valores no
vocabulário GP (unidade linear em metros, booleano em texto, referência a item por uuid/url) e descritores."""

import pytest

from app.ferramentas import buffer as _buffer  # noqa: F401 — registra a ferramenta de exemplo
from app.ferramentas import registro
from app.ferramentas.registro import ErroParametro, ErroRegistro, Parametro, ferramenta

SAIDA = Parametro("saida", "GPFeatureRecordSetLayer", "saída", direcao="saida")


def _f(ctx, entradas, parametros, destino):
    return {}


def test_buffer_registrado_com_manifesto_valido():
    f = registro.obter("buffer")
    assert f is not None and f.categoria == "proximidade" and f.versao == 2
    assert [p.nome for p in f.entradas] == ["camada", "distancia", "campo_distancia", "distancia_interna",
                                            "metodo", "dissolver"]
    assert [p.nome for p in f.saidas] == ["saida"]
    assert all(p.tipo in registro.TIPOS_GP for p in f.parametros)


@pytest.mark.parametrize("parametros, trecho", [
    ((Parametro("campo", "", "x"), SAIDA), "sem tipo"),
    ((Parametro("campo", "GPCoisa", "x"), SAIDA), "fora do vocabulário"),
    ((Parametro("campo", "GPString", "x"),), "sem saída"),
    ((Parametro("campo", "GPString", "x"), Parametro("campo", "GPLong", "x"), SAIDA), "repetido"),
    ((Parametro("campo", "GPMultiValue", "x"), SAIDA), "subtipo"),
    ((Parametro("campo", "GPLong", "x", opcoes=("a",)), SAIDA), "opcoes"),
    ((Parametro("campo", "GPLong", "x", padrao="dez"), SAIDA), "padrão fora do tipo"),
])
def test_manifesto_invalido_e_recusado_na_importacao(parametros, trecho):
    with pytest.raises(ErroRegistro, match=trecho):
        ferramenta(nome="zt_invalida", titulo="t", categoria="resumo", parametros=parametros,
                   custo=lambda e, p: 0)(_f)
    assert registro.obter("zt_invalida") is None


def test_categoria_nome_e_assinatura_errados():
    with pytest.raises(ErroRegistro, match="categoria"):
        ferramenta(nome="zt_a", titulo="t", categoria="magia", parametros=(SAIDA,), custo=lambda e, p: 0)(_f)
    with pytest.raises(ErroRegistro, match="nome de ferramenta"):
        ferramenta(nome="Zt-A", titulo="t", categoria="resumo", parametros=(SAIDA,), custo=lambda e, p: 0)(_f)
    with pytest.raises(ErroRegistro, match="recebe"):
        ferramenta(nome="zt_b", titulo="t", categoria="resumo", parametros=(SAIDA,),
                   custo=lambda e, p: 0)(lambda ctx: 0)
    with pytest.raises(ErroRegistro, match="repetida"):
        ferramenta(nome="buffer", titulo="t", categoria="resumo", parametros=(SAIDA,), custo=lambda e, p: 0)(_f)


def test_normalizacao_no_vocabulario_gp():
    f = registro.obter("buffer")
    uid = "0f8fad5b-d9cb-469f-a165-70867728950e"
    v = registro.validar_parametros(f, {"camada": {"url": f"https://x.invalido/rest/services/{uid}/FeatureServer/0"},
                                        "distancia": {"distance": 2, "units": "esriKilometers"}, "dissolver": "true"})
    assert v == {"camada": uid, "distancia": {"distance": 2.0, "units": "esriKilometers", "metros": 2000.0},
                 "campo_distancia": None, "distancia_interna": None, "metodo": "geodesico", "dissolver": True}
    v = registro.validar_parametros(f, {"camada": uid})
    assert v["distancia"]["metros"] == 100.0 and v["dissolver"] is False
    for dados, campo in [({"camada": uid, "distancia": "x"}, "distancia"), ({"camada": "abc"}, "camada"),
                         ({"camada": uid, "outro": 1}, "outro"), ({}, "camada"),
                         ({"camada": uid, "distancia": {"distance": 1, "units": "esriLeguas"}}, "distancia"),
                         ({"camada": uid, "distancia": {"distance": 200000}}, "distancia")]:
        with pytest.raises(ErroParametro) as e:
            registro.validar_parametros(f, dados)
        assert e.value.campo == campo


def test_parametros_de_formulario_gp_decodifica_json_e_ignora_extras():
    f = registro.obter("buffer")
    crus = {"f": "json", "token": "abc", "env:outSR": "4326", "camada": "x", "distancia": '{"distance": 3}',
            "dissolver": "false"}
    assert registro.parametros_de_formulario_gp(f, crus) == {"camada": "x", "distancia": {"distance": 3},
                                                             "dissolver": "false"}
    with pytest.raises(ErroParametro):
        registro.parametros_de_formulario_gp(f, {"raio": "1"})


def test_descritores_api_e_gpserver():
    f = registro.obter("buffer")
    d = registro.descrever(f)
    assert d["esquema"]["properties"]["camada"]["format"] == "uuid" and d["esquema"]["required"] == ["camada"]
    assert d["esquema"]["properties"]["distancia"]["properties"]["units"]["enum"] == sorted(registro.UNIDADES_LINEARES)
    gp = registro.descrever_gp(f)
    tipos = {p["name"]: p["dataType"] for p in gp["parameters"]}
    assert tipos == {"camada": "GPFeatureRecordSetLayer", "distancia": "GPLinearUnit", "dissolver": "GPBoolean",
                     "campo_distancia": "GPString", "distancia_interna": "GPLinearUnit", "metodo": "GPString",
                     "saida": "GPFeatureRecordSetLayer"}
    obrig = {p["name"]: p["parameterType"] for p in gp["parameters"]}
    assert obrig["camada"] == "esriGPParameterTypeRequired" and obrig["distancia"] == "esriGPParameterTypeOptional"
