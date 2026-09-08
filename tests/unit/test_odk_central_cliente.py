"""Cliente da API do ODK Central (item L2-07-e-odk-central-ponte) contra o dublê HTTP de
`tests/odk_central_duble.py`. Prova o CONTRATO (caminhos, parâmetros, paginação, erro) e a defesa de SSRF, que
não é do dublê: `validar_url` roda de verdade em toda chamada."""

import hashlib

import pytest

from app.conexao import seguranca
from app.odk.central import Central, ErroCentral
from tests.odk_central_duble import URL_BASE, CentralDuble, instalar, png


@pytest.fixture
def duble(monkeypatch) -> CentralDuble:
    d = CentralDuble()
    instalar(monkeypatch, d)
    return d


def _central(duble: CentralDuble) -> Central:
    return Central(url_base=URL_BASE, token=duble.token)


def test_publica_o_xlsform_com_publish_true_e_o_cabecalho_de_fallback(duble):
    c = _central(duble)
    r = c.publicar_xlsform(duble.projeto, b"PK\x03\x04planilha-de-teste", "campo_odk")
    assert r["xmlFormId"] == "campo_odk" and r["publishedAt"]
    metodo, caminho = duble.chamadas[0]
    assert metodo == "POST" and caminho.startswith(f"/v1/projects/{duble.projeto}/forms?")
    assert "publish=true" in caminho
    assert duble.corpo_publicado == b"PK\x03\x04planilha-de-teste"
    assert duble.cabecalhos_publicacao["x-xlsform-formid-fallback"] == "campo_odk"
    assert duble.cabecalhos_publicacao["content-type"].endswith("spreadsheetml.sheet")
    assert c.formulario(duble.projeto, "campo_odk")["hash"]  # o formulário aparece no Central depois


def test_envios_paginam_por_top_e_skip_e_param_na_pagina_curta(duble):
    _central(duble).publicar_xlsform(duble.projeto, b"PK\x03\x04x", "campo_odk")
    duble.semear_envios(250)
    linhas = list(_central(duble).envios(duble.projeto, "campo_odk"))
    assert len(linhas) == 250
    pedidos = [c for _m, c in duble.chamadas if "Submissions" in c]
    assert len(pedidos) == 3  # 100 + 100 + 50 (a terceira volta curta e encerra)
    assert all("%24expand=%2A" in p or "$expand=*" in p for p in pedidos)


def test_teto_de_envios_por_execucao(duble):
    _central(duble).publicar_xlsform(duble.projeto, b"PK\x03\x04x", "campo_odk")
    duble.semear_envios(150)
    assert len(list(_central(duble).envios(duble.projeto, "campo_odk", teto=20))) == 20


def test_anexo_volta_com_os_bytes_e_o_sha256_do_dublê(duble):
    _central(duble).publicar_xlsform(duble.projeto, b"PK\x03\x04x", "campo_odk")
    duble.semear_envios(1)
    c = _central(duble)
    lista = c.anexos_do_envio(duble.projeto, "campo_odk", "uuid:zt-odk-000")
    assert lista == [{"name": "foto-000.png", "exists": True}]
    bruto = c.anexo(duble.projeto, "campo_odk", "uuid:zt-odk-000", "foto-000.png")
    assert bruto.startswith(b"\x89PNG")
    assert hashlib.sha256(bruto).hexdigest() == hashlib.sha256(png((0, 128, 32))).hexdigest()


def test_credencial_errada_vira_credencial_recusada(duble):
    with pytest.raises(ErroCentral) as e:
        Central(url_base=URL_BASE, token="token-errado").formulario(duble.projeto, "campo_odk")
    assert e.value.motivo == "credencial_recusada" and e.value.status == 401


def test_sem_credencial_tambem_e_recusado(duble):
    with pytest.raises(ErroCentral) as e:
        Central(url_base=URL_BASE).formulario(duble.projeto, "campo_odk")
    assert e.value.motivo == "credencial_recusada"


def test_resposta_que_nao_e_json_nao_passa_por_dado_valido(duble):
    """Refutação do item, parte "XML malformado": pelo OData o envio chega em JSON, então o caso equivalente é
    o Central (ou um proxy no meio) devolver corpo que não é JSON. Vira erro nomeado, nunca lista vazia."""
    duble.resposta_crua = b"<html><body>502 Bad Gateway</body></html>"
    with pytest.raises(ErroCentral) as e:
        _central(duble).formulario(duble.projeto, "campo_odk")
    assert e.value.motivo == "resposta_nao_e_json"


def test_odata_sem_a_chave_value(duble):
    duble.resposta_crua = b'{"@odata.context": "x"}'
    with pytest.raises(ErroCentral) as e:
        list(_central(duble).envios(duble.projeto, "campo_odk"))
    assert e.value.motivo == "odata_sem_value"


def test_status_do_central_vira_erro_com_o_status(duble):
    duble.status_forcado = 500
    with pytest.raises(ErroCentral) as e:
        _central(duble).formulario(duble.projeto, "campo_odk")
    assert e.value.status == 500 and e.value.motivo == "http_500"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8150", "http://localhost/v1", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/v1", "http://[::1]/v1", "file:///etc/passwd", "http://user:senha@8.8.8.8/v1",
])
def test_ssrf_a_conexao_apontada_para_dentro_nao_sai_da_maquina(monkeypatch, url):
    """Refutação do item: nenhuma das URLs abre conexão. O transporte é substituído por um que EXPLODE se for
    usado — se a defesa falhasse, o teste quebraria com `AssertionError`, não com um erro de rede."""
    def _explode(*a, **kw):
        raise AssertionError("a defesa de SSRF deixou passar: o transporte foi usado")

    monkeypatch.setattr(seguranca, "cliente_pinado", _explode)
    with pytest.raises(ErroCentral) as e:
        Central(url_base=url, token="x").formulario(7, "campo_odk")
    assert e.value.motivo.startswith("url_insegura:")
    assert e.value.status is None


def test_entidades_do_dataset(duble):
    duble.semear_entidades("municipios", [("ssa", "Salvador", {"estado": "ba"})])
    assert _central(duble).entidades(duble.projeto, "municipios")[0]["uuid"] == "ssa"
    with pytest.raises(ErroCentral) as e:
        _central(duble).entidades(duble.projeto, "nao-existe")
    assert e.value.status == 404
