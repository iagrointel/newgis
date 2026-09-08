"""Partes puras do MapServer (item L2-04-f): a aritmética da tela, a escolha do símbolo por classe,
a leitura de `layers`/`layerDefs` e a amostra de legenda. Nenhuma toca o banco — por isso rodam em
milissegundos e podem cobrir os casos de borda que um teste de API cobriria devagar."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.consulta import mapserver
from app.erros import ErroAPI

DRAWING_UNICO = {"renderer": {"type": "uniqueValue", "field1": "classe", "uniqueValueInfos": [
    {"value": "a", "label": "classe a", "symbol": {"type": "esriSFS", "color": [200, 30, 30, 255]}},
    {"value": "b", "label": "classe b", "symbol": {"type": "esriSFS", "color": [30, 100, 200, 255]}},
], "defaultSymbol": {"type": "esriSFS", "color": [204, 204, 204, 255]}, "defaultLabel": "outros"}}
DRAWING_INTERVALOS = {"renderer": {"type": "classBreaks", "field": "populacao", "classBreakInfos": [
    {"classMinValue": None, "classMaxValue": 100, "label": "- 100",
     "symbol": {"type": "esriSFS", "color": [1, 1, 1, 255]}},
    {"classMinValue": 100, "classMaxValue": 200, "label": "100 - 200",
     "symbol": {"type": "esriSFS", "color": [2, 2, 2, 255]}},
]}}
DRAWING_SIMPLES = {"renderer": {"type": "simple", "label": "tudo",
                                "symbol": {"type": "esriSFS", "color": [9, 9, 9, 255]}}}


def test_tela_projeta_canto_e_centro():
    tela = mapserver.Tela((0.0, 0.0, 10.0, 5.0), 100, 50)
    assert tela.ponto(0.0, 0.0) == (0.0, 50.0)      # canto inferior esquerdo é o pé da imagem
    assert tela.ponto(10.0, 5.0) == (100.0, 0.0)    # canto superior direito é o topo
    assert tela.ponto(5.0, 2.5) == (50.0, 25.0)


def test_tela_sem_area_nao_divide_por_zero():
    tela = mapserver.Tela((1.0, 1.0, 1.0, 1.0), 10, 10)
    x, y = tela.ponto(1.0, 1.0)
    assert x == 0.0 and y == 10.0


def test_tolerancia_e_meio_pixel_do_lado_menor():
    tela = mapserver.Tela((0.0, 0.0, 100.0, 100.0), 100, 200)
    assert tela.tolerancia == pytest.approx(0.25)


def test_classes_de_valores_unicos_incluem_o_padrao():
    cls = mapserver.classes(DRAWING_UNICO)
    assert [c["label"] for c in cls] == ["classe a", "classe b", "outros"]
    assert cls[-1]["valor"] is None


def test_classes_de_intervalos_e_de_simples():
    assert [c["label"] for c in mapserver.classes(DRAWING_INTERVALOS)] == ["- 100", "100 - 200"]
    assert len(mapserver.classes(DRAWING_SIMPLES)) == 1, "renderer simples tem UMA classe, não zero"


@pytest.mark.parametrize("valor,cor", [("a", [200, 30, 30, 255]), ("b", [30, 100, 200, 255]),
                                       ("z", [204, 204, 204, 255]), (None, [204, 204, 204, 255])])
def test_simbolo_por_valor_unico(valor, cor):
    assert mapserver.simbolo_de(DRAWING_UNICO, valor)["color"] == cor


@pytest.mark.parametrize("valor,cor", [(50, [1, 1, 1, 255]), (100, [1, 1, 1, 255]),
                                       (150, [2, 2, 2, 255]), (5000, [2, 2, 2, 255])])
def test_simbolo_por_intervalo(valor, cor):
    assert mapserver.simbolo_de(DRAWING_INTERVALOS, valor)["color"] == cor


def test_amostra_de_legenda_usa_a_cor_da_classe():
    for classe in mapserver.classes(DRAWING_UNICO):
        png = mapserver.amostra_de_legenda(classe["symbol"], "Polygon")
        imagem = Image.open(io.BytesIO(png)).convert("RGBA")
        assert imagem.size == (mapserver.LEGENDA_LADO, mapserver.LEGENDA_LADO)
        assert tuple(classe["symbol"]["color"]) in {c[1] for c in imagem.getcolors(maxcolors=4096)}


def test_amostra_de_ponto_e_de_linha_desenham_algo():
    simbolo_ponto = {"type": "esriSMS", "color": [10, 20, 30, 255], "size": 8.0}
    simbolo_linha = {"type": "esriSLS", "color": [10, 20, 30, 255], "width": 2.0}
    for simbolo, geometria in ((simbolo_ponto, "Point"), (simbolo_linha, "LineString")):
        imagem = Image.open(io.BytesIO(mapserver.amostra_de_legenda(simbolo, geometria))).convert("RGBA")
        assert imagem.getextrema()[3][1] > 0, "a amostra não pode sair inteiramente transparente"


CAMADAS = [{"id": 0, "visivel": True}, {"id": 1, "visivel": False}, {"id": 2, "visivel": True}]


@pytest.mark.parametrize("layers,esperado", [
    (None, [0, 2]),
    ("show:1", [1]),
    ("show:0,1,2", [0, 1, 2]),
    ("hide:0", [2]),
    ("include:1", [0, 1, 2]),
    ("exclude:2", [0]),
])
def test_selecao_de_camadas(layers, esperado):
    assert [c["id"] for c in mapserver.selecao_de_camadas(CAMADAS, layers)] == esperado


@pytest.mark.parametrize("layers", ["0,1", "mostrar:0", "show:a"])
def test_selecao_de_camadas_malformada_e_400(layers):
    with pytest.raises(ErroAPI):
        mapserver.selecao_de_camadas(CAMADAS, layers)


def test_layer_defs_nas_duas_formas():
    assert mapserver.defs_por_camada('{"0":"pop > 1","2":"nome = \'x\'"}') == {0: "pop > 1", 2: "nome = 'x'"}
    assert mapserver.defs_por_camada("0:pop > 1;2:nome = 'x'") == {0: "pop > 1", 2: "nome = 'x'"}
    assert mapserver.defs_por_camada(None) == {}


@pytest.mark.parametrize("bruto", ["{isso não é json", '{"a":"x"}', "0 sem dois pontos", "[1,2]"])
def test_layer_defs_malformado_e_400(bruto):
    with pytest.raises(ErroAPI):
        mapserver.defs_por_camada(bruto)


def test_where_compilado_recusa_o_que_nao_esta_na_lista_branca():
    colunas = {"populacao": '"populacao"'}
    sql, params = mapserver.where_compilado("populacao > 10", colunas)
    assert "populacao" in sql and params == [10]
    assert mapserver.where_compilado(None, colunas) == ("TRUE", [])
    with pytest.raises(ErroAPI):
        mapserver.where_compilado("senha_hash IS NOT NULL", colunas)
    with pytest.raises(ErroAPI):
        mapserver.where_compilado("1=1; DROP TABLE plat.item", colunas)


@pytest.mark.parametrize("size", ["8000,8000", "4097,10", "10,4097", "0,10", "-1,-1", "10", "a,b"])
def test_tamanho_fora_do_limite_declarado_e_400(size):
    with pytest.raises(ErroAPI):
        mapserver.tamanho_do_pedido(size)


def test_tamanho_no_limite_passa():
    assert mapserver.tamanho_do_pedido("1024,768") == (1024, 768)
    assert mapserver.tamanho_do_pedido("4096,4096") == (4096, 4096)


@pytest.mark.parametrize("bruto", ["0,0,1", "1,1,0,0", "a,b,c,d", "0,0,nan,1", "", None])
def test_bbox_malformado_e_400(bruto):
    with pytest.raises(ErroAPI):
        mapserver.bbox_do_pedido(bruto)


@pytest.mark.parametrize("dpi", ["0", "-5", "601", "x"])
def test_dpi_fora_da_faixa_e_400(dpi):
    with pytest.raises(ErroAPI):
        mapserver.dpi_do_pedido(dpi)


def test_dpi_padrao_e_96():
    assert mapserver.dpi_do_pedido(None) == 96.0
    assert mapserver.dpi_do_pedido("300") == 300.0


def test_ponto_em_pixel_cresce_com_o_dpi():
    """Símbolo em PONTOS: a 96 dpi um traço de 0,75 pt tem 1 px; a 300 dpi tem 3 px. É o que faz um
    mapa a 300 dpi sair legível em vez de com o traço fino de tela."""
    assert mapserver._px(0.75, 96.0) == 1
    assert mapserver._px(0.75, 300.0) == 3


def test_desenho_de_poligono_pinta_a_cor_do_simbolo():
    camada = {"drawing_info": DRAWING_UNICO, "opacidade": 1}
    quadrado = {"type": "Polygon", "coordinates": [[[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]]]}
    tela = mapserver.Tela((0.0, 0.0, 10.0, 10.0), 50, 50)
    imagem = mapserver.desenhar([(camada, [(quadrado, "a")])], tela, 96.0, True)
    assert imagem.getpixel((25, 25)) == (200, 30, 30, 255)
    assert imagem.getpixel((1, 1))[3] == 0, "fora do polígono a imagem transparente fica transparente"


def test_opacidade_da_camada_entra_no_alfa():
    camada = {"drawing_info": DRAWING_UNICO, "opacidade": 0.5}
    quadrado = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
    tela = mapserver.Tela((0.0, 0.0, 10.0, 10.0), 20, 20)
    imagem = mapserver.desenhar([(camada, [(quadrado, "a")])], tela, 96.0, True)
    assert imagem.getpixel((10, 10))[3] == pytest.approx(127, abs=2)


def test_camada_zero_desenha_por_cima():
    """Ordem de empilhamento do ArcGIS Server: o identificador 0 é a camada de cima."""
    cima = {"drawing_info": DRAWING_UNICO, "opacidade": 1}
    baixo = {"drawing_info": DRAWING_INTERVALOS, "opacidade": 1}
    quadrado = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
    tela = mapserver.Tela((0.0, 0.0, 10.0, 10.0), 20, 20)
    imagem = mapserver.desenhar([(cima, [(quadrado, "a")]), (baixo, [(quadrado, 50)])], tela, 96.0, False)
    assert imagem.getpixel((10, 10)) == (200, 30, 30, 255)


@pytest.mark.parametrize("formato,assinatura,tipo", [
    ("png32", b"\x89PNG", "image/png"), ("png", b"\x89PNG", "image/png"),
    ("jpg", b"\xff\xd8", "image/jpeg"), ("pdf", b"%PDF-", "application/pdf"),
])
def test_bytes_da_imagem_em_cada_formato(formato, assinatura, tipo):
    imagem = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
    dados, tipo_conteudo = mapserver.bytes_da_imagem(imagem, formato)
    assert dados.startswith(assinatura) and tipo_conteudo == tipo
