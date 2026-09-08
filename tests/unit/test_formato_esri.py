"""Negociação de `f` e `callback` do protocolo Esri (item L2-04-b, app/consulta/formato_esri.py)."""

import json

import pytest

from app.consulta.formato_esri import formato_de, resposta_esri, validar_callback
from app.erros import ErroAPI


def test_json_e_o_padrao():
    assert formato_de(None) == "json" and formato_de("") == "json" and formato_de("PJSON") == "pjson"


def test_formato_desconhecido_e_400_nao_500():
    with pytest.raises(ErroAPI) as e:
        formato_de("kmz")
    assert e.value.status_code == 400


def test_pjson_e_o_mesmo_json_indentado():
    dado = {"currentVersion": 11.4, "layers": []}
    liso = resposta_esri(dado, "json").body.decode()
    bonito = resposta_esri(dado, "pjson").body.decode()
    assert json.loads(liso) == json.loads(bonito) == dado
    assert "\n" in bonito and "\n" not in liso


def test_html_responde_pagina_e_nunca_500():
    r = resposta_esri({"a": 1}, "html")
    assert r.status_code == 200 and r.media_type.startswith("text/html")
    assert b"<pre" in r.body


def test_html_escapa_o_conteudo_vindo_do_dado():
    r = resposta_esri({"titulo": "<script>alert(1)</script>"}, "html")
    assert b"<script>" not in r.body and b"&lt;script&gt;" in r.body


def test_jsonp_embrulha_no_nome_pedido():
    r = resposta_esri({"a": 1}, "json", "cb")
    assert r.body == b'cb({"a": 1});'
    assert r.media_type.startswith("text/javascript")


@pytest.mark.parametrize("cb", ["a(1)", "</script>", "a-b", "1a", "a" * 200, "a;b"])
def test_callback_com_script_e_recusado(cb):
    with pytest.raises(ErroAPI) as e:
        validar_callback(cb)
    assert e.value.status_code == 400


def test_callback_com_caminho_de_objeto_e_aceito():
    assert validar_callback("janela.cb$1") == "janela.cb$1"
