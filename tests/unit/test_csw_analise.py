"""Leitura de CSW 2.0.2 / ISO 19139 sem rede (item L6-06-descoberta-csw), sobre respostas GRAVADAS do CSW da INDE
em 07/09/2026 (`tests/dados/csw/`; nomes de pessoa, e-mail e telefone de contato retirados da gravação). Cobre:
montagem do pedido KVP, GetRecords (total/paginação/registros), GetRecordById com WMS+WFS (endereço base,
camada), a ficha de procedência, o registro SEM serviço ligado (refutação do item), XML inseguro e resposta que
não é CSW."""

from pathlib import Path

import pytest

from app import limites
from app.conexao import csw, proveniencia

DADOS = Path(__file__).resolve().parents[1] / "dados" / "csw"
URL_INDE = "https://metadados.inde.gov.br/geonetwork/srv/eng/csw"
ID_WMS_WFS = "fbdd4fe6-956f-4d20-bbf9-068365edabb8"
ID_SEM_ENDERECO = "f8126f1f-1883-4ddb-90ed-1d9a519f8913"


def _ler(nome: str) -> bytes:
    return (DADOS / nome).read_bytes()


# --------------------------------------------------------------------------- pedidos


def test_url_getrecords_kvp_com_texto_e_bbox():
    u = csw.url_getrecords(URL_INDE, "rodovia d'água", [-48, -25, -46, -23], inicio=11, maximo=5)
    assert u.startswith(URL_INDE + "?")
    assert "request=GetRecords" in u and "outputSchema=http%3A%2F%2Fwww.isotc211.org%2F2005%2Fgmd" in u
    assert "constraintLanguage=CQL_TEXT" in u and "maxRecords=5" in u and "startPosition=11" in u
    # aspa simples do CQL dobrada; BBOX na ordem oeste,sul,leste,norte
    assert "AnyText+like+%27%25rodovia+d%27%27%C3%A1gua%25%27+AND+" in u
    assert "BBOX%28ows%3ABoundingBox%2C-48%2C-25%2C-46%2C-23%29" in u


def test_url_getrecords_respeita_teto_e_mantem_parametros_do_usuario():
    u = csw.url_getrecords("https://x.example/csw?lang=por&service=csw", "a", None, maximo=999)
    assert f"maxRecords={limites.CSW_MAX_REGISTROS}" in u
    assert "lang=por" in u and u.count("service=") == 1  # o service= colado pelo usuário não duplica o nosso


def test_url_getrecordbyid():
    u = csw.url_getrecordbyid(URL_INDE, ID_WMS_WFS)
    assert "request=GetRecordById" in u and f"id={ID_WMS_WFS}" in u and "elementSetName=full" in u


# --------------------------------------------------------------------------- GetRecords


def test_getrecords_inde_devolve_registros_total_e_pagina():
    res = csw.analisar_getrecords(_ler("inde_getrecords_tuberculose.xml"))
    assert res.total == 52 and res.devolvidos == 2 and res.proximo == 3
    assert len(res.registros) == 2
    r = res.registros[0]
    assert r.identificador and r.titulo and "tuberculose" in r.titulo.lower()
    assert r.organizacao and "IBGE" in r.organizacao.upper() or "Geografia" in (r.organizacao or "")
    assert r.bbox and len(r.bbox) == 4 and r.bbox[0] < r.bbox[2] and r.bbox[1] < r.bbox[3]
    assert {s.tipo for s in r.servicos} == {"wms", "wfs"}


# --------------------------------------------------------------------------- GetRecordById


def test_getrecordbyid_wms_e_wfs_com_endereco_base_e_camada():
    r = csw.analisar_getrecordbyid(_ler("inde_getrecordbyid_wms_wfs.xml"))
    assert r is not None and r.identificador == ID_WMS_WFS
    por_tipo = {s.tipo: s for s in r.servicos}
    assert set(por_tipo) == {"wms", "wfs"}
    # endereço BASE (sem querystring) é o que vira plat.conexao.url; a URL declarada fica guardada
    assert por_tipo["wms"].url == "https://geoservicos.ibge.gov.br/geoserver/ODS/ows"
    assert "?" not in por_tipo["wms"].url and "request=GetCapabilities" in por_tipo["wms"].url_declarada
    assert por_tipo["wms"].camada == "ods_3_3_2_2014_uf_1"
    assert por_tipo["wfs"].camada == "ODS:ods_3_3_2_2014_uf_1"
    assert por_tipo["wms"].protocolo == "OGC:WMS" and por_tipo["wfs"].protocolo == "OGC:WFS"
    assert r.data_metadado == "2025-08-28T17:05:21"
    assert "Objetivos de Desenvolvimento Sustentável" in r.palavras_chave
    assert r.sem_servico is False


def test_registro_com_protocolo_wms_mas_sem_endereco_e_sem_servico():
    """Caso REAL da INDE (cartas topográficas do IBGE): `OGC:WMS-1.1.1-http-get-map` com linkage vazio. Não é
    serviço; vira aviso — e nunca conexão (refutação do item)."""
    r = csw.analisar_getrecordbyid(_ler("inde_getrecordbyid_wms_sem_endereco.xml"))
    assert r is not None and r.identificador == ID_SEM_ENDERECO
    assert r.servicos == [] and r.sem_servico is True
    assert any("sem serviço ligado" in a for a in r.avisos)
    assert any("sem endereço" in a for a in r.avisos)
    assert r.bbox == [-43.5, -22.5, -43.25, -22.25]
    assert r.linhagem and "digitalização" in r.linhagem


def test_registro_sem_nenhum_onlineresource():
    """o adversário fornece ISO sem OnlineResource algum: sem serviço, sem exceção."""
    import re

    bruto = _ler("inde_getrecordbyid_wms_wfs.xml").decode("utf-8")
    sem = re.sub(r"<gmd:onLine>.*?</gmd:onLine>", "", bruto, flags=re.S)
    assert "CI_OnlineResource" not in sem
    r = csw.analisar_getrecordbyid(sem.encode("utf-8"))
    assert r is not None and r.sem_servico and r.titulo


def test_servico_sem_protocolo_so_conta_quando_a_url_diz_service():
    corpo = b"""<?xml version="1.0"?><csw:GetRecordByIdResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
      xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
      <gmd:MD_Metadata><gmd:fileIdentifier><gco:CharacterString>x</gco:CharacterString></gmd:fileIdentifier>
      <gmd:distributionInfo><gmd:MD_Distribution><gmd:transferOptions><gmd:MD_DigitalTransferOptions>
        <gmd:onLine><gmd:CI_OnlineResource><gmd:linkage><gmd:URL>https://a.example/geoserver/ows?service=WFS&amp;typeName=ns:t</gmd:URL></gmd:linkage></gmd:CI_OnlineResource></gmd:onLine>
        <gmd:onLine><gmd:CI_OnlineResource><gmd:linkage><gmd:URL>https://a.example/pagina.html</gmd:URL></gmd:linkage></gmd:CI_OnlineResource></gmd:onLine>
        <gmd:onLine><gmd:CI_OnlineResource><gmd:linkage><gmd:URL>ftp://a.example/x</gmd:URL></gmd:linkage>
          <gmd:protocol><gco:CharacterString>OGC:WMS</gco:CharacterString></gmd:protocol></gmd:CI_OnlineResource></gmd:onLine>
      </gmd:MD_DigitalTransferOptions></gmd:transferOptions></gmd:MD_Distribution></gmd:distributionInfo>
      </gmd:MD_Metadata></csw:GetRecordByIdResponse>"""
    r = csw.analisar_getrecordbyid(corpo)
    assert [(s.tipo, s.url, s.camada) for s in r.servicos] == [("wfs", "https://a.example/geoserver/ows", "ns:t")]
    assert any("ftp://a.example/x" in a for a in r.avisos)  # WMS declarado com endereço ftp: aviso, não serviço


# --------------------------------------------------------------------------- ficha


def test_ficha_preenchida_do_iso_e_campos_nao_declarados_ficam_none():
    bruto = _ler("inde_getrecordbyid_wms_wfs.xml")
    r = csw.analisar_getrecordbyid(bruto)
    wms = next(s for s in r.servicos if s.tipo == "wms")
    f = csw.ficha(r, wms, URL_INDE, bruto, "2026-09-07")
    assert f["fonte"] == r.organizacao and f["responsavel"] == r.organizacao
    assert f["url"] == wms.url and f["url_declarada"] == wms.url_declarada
    assert f["licenca"] is None  # o registro real não declara licença em texto: fica None, nunca um palpite
    assert f["data_de_acesso"] == "2026-09-07"
    assert f["sha256"] and len(f["sha256"]) == 64
    assert f["comando_reexecucao"].startswith("GET " + URL_INDE + "?") and ID_WMS_WFS in f["comando_reexecucao"]
    assert f["catalogo"] == {"url": URL_INDE, "identificador": ID_WMS_WFS, "data_metadado": "2025-08-28T17:05:21"}
    assert f["frescor"] and "2025-08-28" in f["frescor"]
    assert any("não declara licença" in a for a in f["limites"])
    assert f["confianca"] == "declarado"  # organização declarada
    for chave in ("fonte", "url", "licenca", "data_do_dado", "data_de_acesso", "metodo", "confianca", "frescor",
                  "sha256", "comando_reexecucao"):
        assert chave in f


def test_publicar_completa_ficha_do_servico_com_o_registro_iso(monkeypatch):
    """`proveniencia.descobrir` sobre uma conexão criada por CSW: o que o serviço vivo declara vence (fonte =
    Title do GetCapabilities), o que ele não declara vem do ISO (licença, data do dado, responsável), e o
    método diz de onde veio cada parte."""
    bruto = _ler("inde_getrecordbyid_wms_wfs.xml")
    r = csw.analisar_getrecordbyid(bruto)
    r.licenca = "CC BY 4.0 (declarada no registro)"
    wms = next(s for s in r.servicos if s.tipo == "wms")
    iso = csw.ficha(r, wms, URL_INDE, bruto, "2026-09-07")

    class _Resp:
        ok = True
        corpo = b"<WMS_Capabilities><Service><Title>Servico vivo</Title></Service></WMS_Capabilities>"

    monkeypatch.setattr(proveniencia.seguranca, "buscar_seguro", lambda *a, **k: _Resp())
    d = proveniencia.descobrir({
        "tipo": "wms", "url": wms.url, "saude": "ok", "saude_verificada_em": None,
        "config": {"camada": wms.camada, "procedencia": iso},
    })
    p = d.procedencia
    assert p["fonte"] == "Servico vivo"                      # o serviço vivo vence
    assert p["licenca"] == "CC BY 4.0 (declarada no registro)"  # o serviço não declarou: veio do ISO
    assert p["responsavel"] == r.organizacao and p["data_do_dado"] == r.data_do_dado
    assert "preenchidos do registro ISO 19139" in p["metodo"] and URL_INDE in p["metodo"]
    assert p["url"] == wms.url and p["sha256"]  # o sha256 é o do GetCapabilities (sondagem viva), não do ISO
    assert d.atribuicao == "Servico vivo"


# --------------------------------------------------------------------------- respostas ruins


def test_xml_com_entidade_externa_e_recusado():
    corpo = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
             b'<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2">&e;</csw:GetRecordsResponse>')
    with pytest.raises(csw.ErroCSW) as e:
        csw.analisar_getrecords(corpo)
    assert e.value.motivo == "xml_inseguro"


def test_exception_report_e_html_viram_erro_nomeado():
    exc = (b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows">'
           b'<ows:Exception exceptionCode="InvalidParameterValue">'
           b'<ows:ExceptionText>constraint invalido</ows:ExceptionText></ows:Exception></ows:ExceptionReport>')
    with pytest.raises(csw.ErroCSW) as e:
        csw.analisar_getrecords(exc)
    assert e.value.motivo == "excecao_do_catalogo" and "InvalidParameterValue" in (e.value.detalhe or "")
    with pytest.raises(csw.ErroCSW) as e2:
        csw.analisar_getrecords(b"<html><body>manutencao</body></html>")
    assert e2.value.motivo == "resposta_nao_e_csw"
    with pytest.raises(csw.ErroCSW) as e3:
        csw.analisar_getrecordbyid(b"isto nao e xml <<<")
    assert e3.value.motivo == "xml_invalido"
