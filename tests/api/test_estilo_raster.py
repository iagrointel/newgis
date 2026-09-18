"""Portão do item L2-02-f-estilo-raster medido por PIXEL DE REFERÊNCIA, sobre o que está no tronco hoje.

O que este arquivo prova, sem navegador: os parâmetros de estilo raster que o item define (bandas,
faixa/rescale, rampa de cor, expressão de índice) chegam de fato ao renderizador e MUDAM o pixel do
jeito previsto — não basta o ladrilho voltar 200 com um PNG qualquer. Método:

  * o ladrilho em tons de cinza (banda única + faixa) é a referência; o mesmo ladrilho com
    `colormap=viridis` tem de dar, PIXEL A PIXEL, exatamente a cor que a tabela de cores do
    `rio_tiler` associa ao valor cinza daquele pixel (a mesma tabela que o servidor usa);
  * estreitar a faixa tem de SATURAR o pixel (nunca escurecê-lo) e mudar a imagem — um servidor que
    ignorasse o parâmetro devolveria os dois ladrilhos idênticos, e isso é o que o par positivo/negativo
    pega;
  * a expressão de índice (NDVI) segue a MESMA regra de cor, o que prova que a rampa se aplica ao
    resultado da expressão e não à banda crua;
  * recusa com par positivo: expressão fora do vocabulário é recusada, a NDVI legítima passa.

LACUNA MEDIDA (por isso o item não fica PROVADO inteiro): a ponte "estilo salvo -> parâmetros de
ladrilho -> legenda" do portão NÃO existe em master — `app/estilos/compilador.py` compila o bloco
`raster` para a camada do MapLibre, mas não tem `parametros_tile()` nem `legenda_raster()`, e
`web/js/mapa/estilo.js` não tem editor de raster. Os dois `xfail(strict=True)` no fim deste arquivo
registram isso e viram falha no dia em que a ponte for construída (é assim que a lacuna não se perde).
Por isso `tests/api/imagens/test_estilo_raster_e2e.py`, que chama essas duas funções, não roda hoje.
"""

from __future__ import annotations

import io
import urllib.parse

import pytest
from PIL import Image
from rio_tiler.colormap import cmap as colormaps

from app.estilos import compilador
from tests.api.imagens.apoio_raster import semear_raster
from tests.api.imagens.conftest import _tenant_id

Z, X, Y = 12, 1503, 2230  # ladrilho sobre a cena sintética de apoio_raster (Brasília)
AMOSTRAS = [(32, 32), (64, 200), (128, 128), (200, 64), (240, 240)]


@pytest.fixture(scope="module")
def tenant_a(env):
    """O `tenant_id_a` da suíte de imagens vive em tests/api/imagens/conftest.py e não alcança este
    diretório; a MESMA função é reusada aqui em vez de uma consulta nova."""
    return _tenant_id(env, "demo")


@pytest.fixture(scope="module")
def raster_pixel(tenant_a):
    """`semear_raster` só cria a coleção quando o pgstac ainda não a tem; numa base onde o pgstac já tem
    "N-imagens" mas o espelho `plat.raster_colecao` está vazio (as duas guardas são herança de dois
    ramos, ver `app/imagens/pgstac.py::colecao_espelhar`), a semeadura morre em
    `raster_item_colecao_fkey`. O espelho é garantido aqui antes, com a MESMA função do app."""
    from app import db
    from app.imagens import pgstac as ps

    colecao = ps.nome_colecao(tenant_a, "imagens")
    with db.db(db.Contexto(tenant_id=tenant_a, usuario_id=0, login="teste")) as cur:
        ps.colecao_espelhar(cur, tenant_a, "imagens", colecao, "Imagens do inquilino")
    return semear_raster(tenant_a, "estilo-raster-pixel")


@pytest.fixture(scope="module")
def token_pixel(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-estilo-raster-pixel", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados["token"]
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def _pedir(cliente, token, item, **params):
    consulta = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return cliente.get(f"/svc/{token}/raster/{item}/{Z}/{X}/{Y}.png?{consulta}")


def _imagem(resposta) -> Image.Image:
    assert resposta.status_code == 200, resposta.text[:300]
    assert resposta.content[:4] == b"\x89PNG", resposta.content[:16]
    return Image.open(io.BytesIO(resposta.content)).convert("RGBA")


def _faixa_da_banda(cliente, token, item, banda: int) -> tuple[float, float]:
    r = cliente.get(f"/svc/{token}/raster/{item}/estatisticas.json?bandas={banda}")
    assert r.status_code == 200, r.text[:300]
    est = r.json()[f"b{banda}"]
    return float(est["min"]), float(est["max"])


# ---------------------------------------------------------------- rampa de cor: pixel de referência
def test_rampa_de_cor_bate_pixel_a_pixel_com_a_tabela_de_cores(cliente, token_pixel, raster_pixel):
    item = raster_pixel["item_id"]
    mn, mx = _faixa_da_banda(cliente, token_pixel, item, 4)
    cinza = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}"))
    colorido = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}",
                              colormap="viridis"))
    assert cinza.size == colorido.size == (256, 256)

    tabela = colormaps.get("viridis")
    conferidos = 0
    for px in AMOSTRAS:
        r_cinza = cinza.getpixel(px)
        if r_cinza[3] == 0:
            continue  # pixel sem dado: nada a comparar
        valor = r_cinza[0]
        assert r_cinza[0] == r_cinza[1] == r_cinza[2], f"sem colormap o pixel {px} deveria ser cinza: {r_cinza}"
        esperado = tuple(tabela[valor])[:3]
        obtido = colorido.getpixel(px)[:3]
        assert all(abs(a - b) <= 1 for a, b in zip(esperado, obtido, strict=True)), (
            f"pixel {px}: valor {valor} deveria virar {esperado} pela rampa viridis, veio {obtido}"
        )
        conferidos += 1
    assert conferidos >= 3, f"amostra insuficiente de pixels com dado: {conferidos}"


def test_esticamento_muda_o_pixel_pelo_valor_previsto(cliente, token_pixel, raster_pixel):
    """Cláusula do esticamento medida por pixel: com a faixa [mn,mx] o cinza de um pixel é
    255*(v-mn)/(mx-mn); trocando a faixa para [mn, mx2], o MESMO pixel tem de cair para o valor que essa
    conta prevê a partir do v deduzido da primeira leitura. Par: as duas imagens também têm de diferir —
    um servidor que ignorasse `faixa` devolveria bytes iguais.

    (Por que não "estreitar até saturar": a cena sintética de apoio_raster tem a banda 4 praticamente
    binária, 1200 ou 3800; estreitar por cima leva as duas classes ao mesmo lugar e não prova nada.
    Medido 17/09.)"""
    item = raster_pixel["item_id"]
    mn, mx = _faixa_da_banda(cliente, token_pixel, item, 4)
    mx2 = mn + (mx - mn) * 2.5  # faixa mais LARGA: todo pixel tem de escurecer de forma previsível
    a = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}"))
    b = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx2}"))
    assert list(a.getdata()) != list(b.getdata()), "a faixa pedida não mudou um pixel sequer"

    conferidos = 0
    for px in AMOSTRAS:
        pa, pb = a.getpixel(px), b.getpixel(px)
        if pa[3] == 0:
            continue
        valor = mn + (pa[0] / 255.0) * (mx - mn)          # valor do pixel deduzido da 1a leitura
        previsto = round(255 * (valor - mn) / (mx2 - mn))  # o que a 2a faixa tem de dar
        assert abs(pb[0] - previsto) <= 3, (
            f"pixel {px}: com faixa [{mn},{mx2}] esperava ~{previsto}, veio {pb[0]} (na faixa cheia era {pa[0]})"
        )
        conferidos += 1
    assert conferidos >= 3, f"amostra insuficiente de pixels com dado: {conferidos}"


def test_ndvi_por_expressao_usa_a_mesma_rampa_no_resultado_da_expressao(cliente, token_pixel, raster_pixel):
    item = raster_pixel["item_id"]
    cinza = _imagem(_pedir(cliente, token_pixel, item, expressao="(b4-b3)/(b4+b3)", faixa="-1,1"))
    colorido = _imagem(_pedir(cliente, token_pixel, item, expressao="(b4-b3)/(b4+b3)", faixa="-1,1",
                              colormap="rdylgn"))
    tabela = colormaps.get("rdylgn")
    conferidos = 0
    for px in AMOSTRAS:
        r_cinza = cinza.getpixel(px)
        if r_cinza[3] == 0:
            continue
        esperado = tuple(tabela[r_cinza[0]])[:3]
        obtido = colorido.getpixel(px)[:3]
        assert all(abs(a - b) <= 1 for a, b in zip(esperado, obtido, strict=True)), (
            f"pixel {px} da NDVI: esperado {esperado}, veio {obtido}"
        )
        conferidos += 1
    assert conferidos >= 3

    # e a NDVI não é a banda crua: a imagem do índice difere da imagem da banda 4 sozinha
    mn, mx = _faixa_da_banda(cliente, token_pixel, item, 4)
    banda_crua = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}"))
    assert list(banda_crua.getdata()) != list(cinza.getdata())


# ---------------------------------------------------------------- recusas, com o par legítimo junto
def test_expressao_fora_do_vocabulario_e_recusada(cliente, token_pixel, raster_pixel):
    """Refutação do item: a expressão não pode virar porta de execução. O par positivo (NDVI legítima)
    está em `test_ndvi_por_expressao_usa_a_mesma_rampa_no_resultado_da_expressao`."""
    r = _pedir(cliente, token_pixel, raster_pixel["item_id"],
               expressao="__import__('os').system('id')", faixa="-1,1")
    assert r.status_code in (400, 422), (r.status_code, r.text[:300])


def test_banda_inexistente_nao_devolve_imagem(cliente, token_pixel, raster_pixel):
    """Refutação do item ("banda inexistente"): o pedido é recusado — nunca volta um PNG. O CÓDIGO real
    medido em 17/09 é 502 `leitura_falhou` ("não foi possível ler a imagem: banda..."), e não um 4xx:
    pedido malformado do cliente sai como falha de servidor. Registrado no xfail abaixo."""
    r = _pedir(cliente, token_pixel, raster_pixel["item_id"], expressao="b99-b1", faixa="-1,1")
    assert r.status_code != 200, r.status_code
    assert r.headers["content-type"].startswith("application/"), r.headers["content-type"]


@pytest.mark.xfail(
    strict=True,
    reason="banda inexistente é erro DO CLIENTE e deveria sair 4xx; o tronco responde 502 "
           "leitura_falhou (medido 17/09). Defeito registrado, não consertado neste turno de medição.",
)
def test_banda_inexistente_deveria_ser_erro_do_cliente(cliente, token_pixel, raster_pixel):
    r = _pedir(cliente, token_pixel, raster_pixel["item_id"], expressao="b99-b1", faixa="-1,1")
    assert 400 <= r.status_code < 500, (r.status_code, r.text[:200])


def test_divisao_por_zero_na_expressao_nao_derruba_o_ladrilho(cliente, token_pixel, raster_pixel):
    """Refutação do item ("expressão com divisão por zero"): MEDIDO em 17/09 o servidor NÃO recusa —
    devolve PNG 200 (o resultado indefinido vira pixel sem dado no render). O que este teste garante é
    que não há 500 nem imagem corrompida; a decisão de recusar ou renderizar é do item, e está registrada
    aqui como comportamento atual, não como acerto."""
    r = _pedir(cliente, token_pixel, raster_pixel["item_id"], expressao="(b4-b3)/(b4-b4)", faixa="-1,1")
    assert r.status_code == 200, (r.status_code, r.text[:200])
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size == (256, 256)


def test_colormap_desconhecido_e_recusado_e_o_conhecido_passa(cliente, token_pixel, raster_pixel):
    item = raster_pixel["item_id"]
    mn, mx = _faixa_da_banda(cliente, token_pixel, item, 4)
    ruim = _pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}", colormap="rampa-inventada")
    assert ruim.status_code in (400, 422), (ruim.status_code, ruim.text[:200])
    bom = _pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}", colormap="viridis")
    assert bom.status_code == 200, bom.text[:200]


# ---------------------------------------------------------------- lacunas do portão que o tronco não tem
@pytest.mark.xfail(
    strict=True,
    reason="cláusula do portão 'parâmetros gerados abrem tile válido no TiTiler' pressupõe a ponte "
           "estilo->parâmetros: app/estilos/compilador.py não tem parametros_tile() em master "
           "(tests/api/imagens/test_estilo_raster_e2e.py chama essa função e por isso não roda hoje)",
)
def test_compilador_traduz_estilo_salvo_em_parametros_de_tile():
    pc = {"tipo": "raster", "geometria": "raster", "versao": 1,
          "parametros_raster": {"bandas": [4], "colormap_name": "viridis", "rescale": [0, 3800]}}
    consulta = compilador.parametros_tile(pc)  # noqa: B018 — ausente em master; xfail registra a lacuna
    assert consulta["bandas"] == "4"


@pytest.mark.xfail(
    strict=True,
    reason="cláusula 'legenda mostra mín/máx reais da cena' pressupõe legenda_raster() no compilador; "
           "ausente em master",
)
def test_compilador_devolve_legenda_raster_com_min_e_max():
    pc = {"tipo": "raster", "geometria": "raster", "versao": 1,
          "parametros_raster": {"bandas": [4], "colormap_name": "viridis", "rescale": [10, 20]}}
    assert compilador.legenda_raster(pc) == {"colormap_name": "viridis", "min": 10, "max": 20}


# ---------------------------------------------------------------- medida do item (tests/medidas/)
def test_medida_do_item_estilo_raster(cliente, token_pixel, raster_pixel, medida):
    """Grava tests/medidas/L2-02-f-estilo-raster.json com o que ESTE arquivo mede hoje: a maior
    diferença de cor entre o pixel renderizado e a tabela de cores (quanto menor, mais a rampa do
    servidor é a mesma do `rio_tiler`) e o estado REAL da ponte estilo -> parâmetros de ladrilho.

    A medida de 07/09 neste mesmo arquivo dizia `e2e_isolado_passou` e `unit_compilador_raster_passou`;
    medido de novo em 18/09, `app/estilos/compilador.py` não tem `parametros_tile` e
    `tests/api/imagens/test_estilo_raster_e2e.py` falha nos 4 testes com AttributeError. A medida nova
    não apaga a antiga: fica ao lado dela, com data, para a contradição aparecer."""
    item = raster_pixel["item_id"]
    mn, mx = _faixa_da_banda(cliente, token_pixel, item, 4)
    cinza = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}"))
    colorido = _imagem(_pedir(cliente, token_pixel, item, bandas="4", faixa=f"{mn},{mx}", colormap="viridis"))
    tabela = colormaps.get("viridis")
    pior, amostrados = 0, 0
    for px in AMOSTRAS:
        r_cinza = cinza.getpixel(px)
        if r_cinza[3] == 0:
            continue
        esperado = tuple(tabela[r_cinza[0]])[:3]
        obtido = colorido.getpixel(px)[:3]
        pior = max(pior, max(abs(a - b) for a, b in zip(esperado, obtido, strict=True)))
        amostrados += 1

    tem_ponte = hasattr(compilador, "parametros_tile")
    tem_legenda = hasattr(compilador, "legenda_raster")
    gravar = medida("L2-02-f-estilo-raster")
    cmd = "pytest tests/api/test_estilo_raster.py::test_medida_do_item_estilo_raster"
    gravar("pixels_conferidos_contra_a_tabela_de_cores", amostrados, "pixels com dado na amostra", cmd)
    gravar("maior_diferenca_de_cor_rampa_viridis", pior, "níveis de 0-255 (0 = idêntico)", cmd)
    gravar("ponte_estilo_para_parametros_de_tile_18_09", tem_ponte,
           "compilador.parametros_tile existe?", "hasattr(app.estilos.compilador, 'parametros_tile')")
    gravar("legenda_raster_no_compilador_18_09", tem_legenda,
           "compilador.legenda_raster existe?", "hasattr(app.estilos.compilador, 'legenda_raster')")
    gravar("e2e_isolado_18_09", "4 failed (AttributeError: module 'app.estilos.compilador' has no "
                                "attribute 'parametros_tile')", "resultado real",
           "pytest tests/api/imagens/test_estilo_raster_e2e.py")

    assert amostrados >= 3
    assert pior <= 1, f"a rampa do servidor divergiu {pior} níveis da tabela do rio_tiler"
    assert not tem_ponte and not tem_legenda, (
        "a ponte estilo->parâmetros apareceu: tire os dois xfail deste arquivo e volte a medir o portão inteiro"
    )
