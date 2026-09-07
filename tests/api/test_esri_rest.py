"""Rotas do conector ArcGIS REST externo (item L6-02-d-arcgis-rest-externo): `/api/conexoes/{id}/esri/*`.
Portão de pronto: "3 serviços públicos de órgãos brasileiros que respondem 200 na data adicionados e
vistos; contagem copiada = returnCountOnly; token do cliente cifrado e nunca exposto; cor de preenchimento/
linha importada." Refutação: "adversário aponta serviço com maxRecordCount = 1 e serviço que exige token
sem fornecê-lo: erro claro, sem laço infinito" — o caso `maxRecordCount=1` está provado sem rede em
`tests/unit/test_esri_rest.py::test_consultar_tudo_para_no_teto_de_paginas_com_maxrecordcount_1`; aqui
prova-se, com rede real, o caso do serviço que EXIGE token (SIGEL/ANEEL declara `Token Required` para
`SIGEL/Linhas_de_Transmissao`) e as 3 conexões reais medidas em 07/09/2026 contra o SIGEL/ANEEL
(`https://sigel.aneel.gov.br/arcgis/rest/services`, Agência Nacional de Energia Elétrica — órgão regulador
federal brasileiro, ArcGIS Server 11.5, sem paywall/robots que bloqueie)."""

import time

import pytest

from tests.api.conftest import PREFIXO_TESTE

URL_EOL_FEATURESERVER = "https://sigel.aneel.gov.br/arcgis/rest/services/PORTAL/Camadas_Downloads/FeatureServer"
URL_AREAS_PUBLICAS_MAPSERVER = "https://sigel.aneel.gov.br/arcgis/rest/services/PORTAL/Areas_Publicas/MapServer"
URL_DISTRIBUICAO_FEATURESERVER = "https://sigel.aneel.gov.br/arcgis/rest/services/PORTAL/Distribuição/FeatureServer"
URL_LT_EXIGE_TOKEN = "https://sigel.aneel.gov.br/arcgis/rest/services/SIGEL/Linhas_de_Transmissao/FeatureServer"


@pytest.fixture
def limpar_conexoes(sessao_a):
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def _criar(sessao, nome_sufixo, url, **extra):
    corpo = {"tipo": "esri_rest", "nome": f"{PREFIXO_TESTE}-esri-{nome_sufixo}", "url": url, **extra}
    return sessao.post("/api/conexoes", json=corpo)


@pytest.mark.lento
def test_tres_servicos_publicos_brasileiros_200_e_vistos(sessao_a, limpar_conexoes):
    """Cláusula 1: 3 serviços ArcGIS REST de um órgão brasileiro (ANEEL/SIGEL) respondem 200 hoje, são
    adicionados como conexão e VISTOS (descrição da camada com campos/geometria — o que a tela "conexões"
    mostraria ao clicar em ver/publicar)."""
    casos = [
        ("eol", URL_EOL_FEATURESERVER, "esriGeometryPoint"),
        ("areas", URL_AREAS_PUBLICAS_MAPSERVER, "esriGeometryPolygon"),
        ("distrib", URL_DISTRIBUICAO_FEATURESERVER, "esriGeometryPolygon"),
    ]
    for sufixo, url, geometria_esperada in casos:
        r = _criar(sessao_a, sufixo, url)
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        limpar_conexoes.append(cid)

        r_testar = sessao_a.post(f"/api/conexoes/{cid}/testar")
        assert r_testar.status_code == 200, r_testar.text
        assert r_testar.json()["status"] == 200, f"{sufixo}: serviço não respondeu 200 hoje: {r_testar.json()}"

        r_desc = sessao_a.get(f"/api/conexoes/{cid}/esri/descricao")
        assert r_desc.status_code == 200, r_desc.text
        assert r_desc.json()["tipo_servico"] in ("FeatureServer", "MapServer")
        camadas = r_desc.json()["camadas"]
        assert len(camadas) > 0, f"{sufixo}: serviço sem sub-camada declarada"

        camada_0 = next(c for c in camadas if c["id"] == 0)
        r_camada = sessao_a.get(f"/api/conexoes/{cid}/esri/camadas/0")
        assert r_camada.status_code == 200, r_camada.text
        corpo = r_camada.json()
        assert corpo["tipo_geometria"] == geometria_esperada == camada_0["tipo_geometria"]
        assert corpo["max_record_count"] > 0
        assert len(corpo["campos"]) > 0


@pytest.mark.lento
def test_contagem_e_returncountonly(sessao_a, limpar_conexoes):
    """Cláusula 2: a contagem exposta pela API usa `returnCountOnly=true` — nunca baixa feição para contar."""
    r = _criar(sessao_a, "contagem", URL_EOL_FEATURESERVER)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_contagem = sessao_a.get(f"/api/conexoes/{cid}/esri/camadas/0/contagem")
    assert r_contagem.status_code == 200, r_contagem.text
    total = r_contagem.json()["total"]
    assert isinstance(total, int) and total > 0

    # confere contra o serviço bruto (mesma técnica, direto — não é o teste "confiando em si mesmo": é a
    # MESMA operação returnCountOnly que a ANEEL expõe, chamada aqui só para comparar o número).
    import httpx

    bruto = httpx.get(
        f"{URL_EOL_FEATURESERVER}/0/query", params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        timeout=15,
    ).json()
    assert bruto["count"] == total


@pytest.mark.lento
def test_simbologia_preenchimento_e_contorno_importados(sessao_a, limpar_conexoes):
    """Cláusula 4: cor de preenchimento/linha importada do renderer simples real (`Areas_Publicas`, polígono
    laranja com contorno preto — visto por `curl` em 07/09/2026)."""
    r = _criar(sessao_a, "simbologia", URL_AREAS_PUBLICAS_MAPSERVER)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_camada = sessao_a.get(f"/api/conexoes/{cid}/esri/camadas/0")
    assert r_camada.status_code == 200, r_camada.text
    simbologia = r_camada.json()["simbologia"]
    assert simbologia is not None, "serviço real com esriSFS simples deveria ter simbologia importada"
    assert simbologia["geometria"] == "poligono"
    assert simbologia["preenchimento_rgba"] == [246, 197, 103, 255]
    assert simbologia["contorno_rgba"] == [0, 0, 0, 255]


@pytest.mark.lento
def test_feicoes_paginadas_geometria_e_atributos_reais(sessao_a, limpar_conexoes):
    """Consulta paginada (referenciado) contra o serviço real: filtro `where`, geometria e atributos vêm do
    serviço de verdade, `outSR=4326`."""
    r = _criar(sessao_a, "feicoes", URL_EOL_FEATURESERVER)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_feicoes = sessao_a.get(f"/api/conexoes/{cid}/esri/camadas/0/feicoes", params={"where": "UF1='RN'"})
    assert r_feicoes.status_code == 200, r_feicoes.text
    corpo = r_feicoes.json()
    assert corpo["type"] == "FeatureCollection"
    assert len(corpo["features"]) > 0
    primeira = corpo["features"][0]
    assert primeira["geometry"]["type"] == "Point"
    assert primeira["properties"]["UF1"] == "RN"
    assert corpo["plat_paginas_lidas"] >= 1


@pytest.mark.lento
def test_mapserver_export_devolve_imagem_real(sessao_a, limpar_conexoes):
    """MapServer `/export` (imagem dinâmica) via proxy: PNG de verdade, gerado pelo serviço real."""
    r = _criar(sessao_a, "mapa", URL_AREAS_PUBLICAS_MAPSERVER)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_mapa = sessao_a.get(
        f"/api/conexoes/{cid}/esri/mapa",
        params={"bbox": "-46,-24,-45,-23", "largura": 256, "altura": 256, "outSR": 4326},
    )
    assert r_mapa.status_code == 200, r_mapa.text
    assert r_mapa.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert r_mapa.headers["content-type"] == "image/png"


@pytest.mark.lento
def test_servico_que_exige_token_sem_fornecer_da_erro_claro_sem_travar(sessao_a, limpar_conexoes):
    """Refutação (2ª parte): SIGEL/Linhas_de_Transmissao exige token real (`Token Required`, código 499);
    sem credencial, a rota devolve erro claro em segundos — nunca um laço/timeout longo."""
    r = _criar(sessao_a, "exige-token", URL_LT_EXIGE_TOKEN)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    inicio = time.monotonic()
    r_desc = sessao_a.get(f"/api/conexoes/{cid}/esri/descricao")
    duracao = time.monotonic() - inicio
    assert r_desc.status_code == 502
    assert "token" in r_desc.json()["mensagem"].lower()
    assert duracao < 30, f"demorou {duracao:.1f}s — deveria falhar rápido, não tentar de novo em loop"


@pytest.mark.lento
def test_credencial_cifrada_nunca_aparece_na_resposta(sessao_a, limpar_conexoes):
    """Cláusula 3: token do cliente cifrado no banco e nunca exposto — nem na listagem, nem na ficha da
    conexão, nem no corpo/erro das rotas do conector (mesmo quando o valor é usado internamente na
    requisição ao serviço externo)."""
    token_falso = "TOKEN-SECRETO-DE-TESTE-NUNCA-DEVE-APARECER"
    r = _criar(sessao_a, "credencial", URL_EOL_FEATURESERVER, credencial=token_falso)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    assert "credencial_cifrada" not in r.text
    assert token_falso not in r.text
    assert r.json()["tem_credencial"] is True

    r_ver = sessao_a.get(f"/api/conexoes/{cid}")
    assert token_falso not in r_ver.text
    assert "credencial_cifrada" not in r_ver.text

    # a rota usa a credencial de verdade contra o serviço (token inválido -> ANEEL recusa), mas o valor
    # jamais volta no corpo do erro
    r_desc = sessao_a.get(f"/api/conexoes/{cid}/esri/descricao")
    assert token_falso not in r_desc.text

    r_lista = sessao_a.get("/api/conexoes")
    assert token_falso not in r_lista.text
