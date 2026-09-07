"""Testes sem rede do conector ArcGIS REST externo (item L6-02-d-arcgis-rest-externo). Os testes com rede
real contra serviços públicos brasileiros ficam em `tests/api/test_esri_rest.py` (marcados `lento`)."""

from __future__ import annotations

import pytest

from app.conexao import esri_rest, rotas_esri_rest

# ------------------------------------------------------------------ simbologia_simples


def test_simbologia_poligono_preenchimento_e_contorno():
    drawing_info = {
        "renderer": {
            "type": "simple",
            "symbol": {
                "type": "esriSFS", "color": [246, 197, 103, 255],
                "outline": {"type": "esriSLS", "color": [0, 0, 0, 255], "width": 0.4},
            },
        },
    }
    s = esri_rest.simbologia_simples(drawing_info)
    assert s.geometria == "poligono"
    assert s.preenchimento_rgba == (246, 197, 103, 255)
    assert s.contorno_rgba == (0, 0, 0, 255)
    assert s.contorno_largura == 0.4


def test_simbologia_linha_so_contorno():
    drawing_info = {
        "renderer": {"type": "simple", "symbol": {"type": "esriSLS", "color": [178, 178, 178, 255], "width": 1}},
    }
    s = esri_rest.simbologia_simples(drawing_info)
    assert s.geometria == "linha"
    assert s.preenchimento_rgba is None
    assert s.contorno_rgba == (178, 178, 178, 255)


def test_simbologia_marcador_de_imagem_nao_tem_cor():
    """esriPMS (marcador de imagem) não declara preenchimento/contorno no sentido do portão — `None`, nunca
    uma cor inventada."""
    drawing_info = {"renderer": {"type": "simple", "symbol": {"type": "esriPMS", "imageData": "..."}}}
    assert esri_rest.simbologia_simples(drawing_info) is None


def test_simbologia_class_breaks_fora_do_escopo():
    """Renderer que não é `simple` (classBreaks/uniqueValue) fica fora da hipótese "simbologia simples"."""
    drawing_info = {"renderer": {"type": "classBreaks", "classBreakInfos": []}}
    assert esri_rest.simbologia_simples(drawing_info) is None


def test_simbologia_sem_drawing_info():
    assert esri_rest.simbologia_simples(None) is None
    assert esri_rest.simbologia_simples({}) is None


# ------------------------------------------------------------------ consultar_tudo — refutação: maxRecordCount hostil


def test_consultar_tudo_para_no_teto_de_paginas_com_maxrecordcount_1(monkeypatch):
    """Refutação do item: serviço com `maxRecordCount=1` (ou qualquer serviço que nunca sinalize o fim da
    paginação) NUNCA entra em laço infinito — o motor para no teto `ESRI_REST_PAGINAS_MAX`, marca
    `truncado=True` com o aviso, e devolve o que já leu."""
    chamadas = {"n": 0}

    def _pagina_hostil(url_camada, *, offset, tamanho, where, out_fields, out_sr, token):
        chamadas["n"] += 1
        # devolve sempre 1 feição, NUNCA sinaliza exceededTransferLimit=False com página incompleta
        # (um servidor real e bem comportado pararia; este finge que sempre há mais uma página)
        feicao = {
            "type": "Feature", "properties": {"id": offset}, "geometry": {"type": "Point", "coordinates": [0, 0]},
        }
        doc = {"type": "FeatureCollection", "features": [feicao], "exceededTransferLimit": True}
        return doc, None

    monkeypatch.setattr(esri_rest, "consultar_pagina", _pagina_hostil)
    from app import limites

    resultado = esri_rest.consultar_tudo(
        "https://exemplo.invalido/FeatureServer/0", max_record_count_servico=1,
    )
    assert resultado.ok is True
    assert resultado.truncado is True
    assert resultado.paginas_lidas == limites.ESRI_REST_PAGINAS_MAX
    assert chamadas["n"] == limites.ESRI_REST_PAGINAS_MAX
    assert len(resultado.feicoes) == limites.ESRI_REST_PAGINAS_MAX  # 1 por página, maxRecordCount=1
    assert any("teto de segurança" in a for a in resultado.avisos)


def test_consultar_tudo_tamanho_de_pagina_respeita_maxrecordcount_do_servidor(monkeypatch):
    """Nunca pede mais do que o `maxRecordCount` declarado, mesmo quando o padrão da casa é maior."""
    pedidos = []

    def _pagina(url_camada, *, offset, tamanho, where, out_fields, out_sr, token):
        pedidos.append(tamanho)
        return {"type": "FeatureCollection", "features": []}, None

    monkeypatch.setattr(esri_rest, "consultar_pagina", _pagina)
    esri_rest.consultar_tudo("https://exemplo.invalido/FeatureServer/0", max_record_count_servico=50)
    assert pedidos[0] == 50


def test_consultar_tudo_erro_na_primeira_pagina_nao_e_sucesso(monkeypatch):
    def _pagina(url_camada, *, offset, tamanho, where, out_fields, out_sr, token):
        return None, "erro_de_conexao:algumacoisa"

    monkeypatch.setattr(esri_rest, "consultar_pagina", _pagina)
    resultado = esri_rest.consultar_tudo("https://exemplo.invalido/FeatureServer/0")
    assert resultado.ok is False
    assert "erro_de_conexao" in resultado.mensagem


def test_consultar_tudo_pagina_maior_que_pedida_vira_aviso_nao_crash(monkeypatch):
    def _pagina(url_camada, *, offset, tamanho, where, out_fields, out_sr, token):
        if offset == 0:
            feats = [{"type": "Feature", "properties": {}, "geometry": None}] * (tamanho + 5)
            return {"type": "FeatureCollection", "features": feats}, None
        return {"type": "FeatureCollection", "features": []}, None

    monkeypatch.setattr(esri_rest, "consultar_pagina", _pagina)
    resultado = esri_rest.consultar_tudo("https://exemplo.invalido/FeatureServer/0", max_record_count_servico=10)
    assert resultado.ok is True
    assert any("mais do que" in a for a in resultado.avisos)


# ------------------------------------------------------------------ detecção do tipo de serviço pela URL


@pytest.mark.parametrize(
    "url,esperado",
    [
        ("https://exemplo.gov.br/arcgis/rest/services/x/FeatureServer", "FeatureServer"),
        ("https://exemplo.gov.br/arcgis/rest/services/x/FeatureServer/", "FeatureServer"),
        ("https://exemplo.gov.br/arcgis/rest/services/x/mapserver", "MapServer"),
        ("https://exemplo.gov.br/arcgis/rest/services/x/ImageServer", "ImageServer"),
        ("https://exemplo.gov.br/arcgis/rest/services/x/GPServer", None),
        ("https://exemplo.gov.br/arcgis/rest/services/x/FeatureServer/0", None),  # sub-camada, não a raiz
    ],
)
def test_tipo_servico_detectado_da_url(url, esperado):
    assert rotas_esri_rest._tipo_servico(url) == esperado


# ------------------------------------------------------------------ contagem — resposta sem campo `count`


def test_buscar_json_erro_token_vira_mensagem_clara():
    """`_buscar_json` reconhece o formato de erro `{"error":{"code":499,...}}` do ArcGIS Server e traduz para
    uma mensagem que nomeia o problema (token), nunca deixa a exceção genérica de JSON estourar."""
    import json as _json

    from app.conexao import seguranca

    class _Resultado:
        ok = True
        corpo = _json.dumps({"error": {"code": 499, "message": "Token Required"}}).encode()

    def _buscar_seguro_falso(*a, **k):
        return _Resultado()

    import app.conexao.esri_rest as mod

    original = seguranca.buscar_seguro
    try:
        mod.seguranca.buscar_seguro = _buscar_seguro_falso
        with pytest.raises(esri_rest.ErroConector) as ei:
            esri_rest.descrever_servico("https://exemplo.invalido/FeatureServer")
        assert "token" in str(ei.value).lower()
    finally:
        mod.seguranca.buscar_seguro = original
