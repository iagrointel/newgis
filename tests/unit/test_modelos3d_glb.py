"""Recipiente glTF binário: ida e volta, recusa de recurso externo e caixa envolvente (item L2-09-c)."""

import struct

import pytest

from app.modelos3d import glb
from tests.apoio_modelos3d import (
    CAIXA_ALTURA_M,
    LARGURA_M,
    PROFUNDIDADE_M,
    glb_caixa,
    glb_com_textura_externa,
)


def test_ida_e_volta_preserva_json_e_binario():
    dados = glb_caixa()
    gltf, binario = glb.ler(dados)
    assert gltf["asset"]["version"] == "2.0"
    assert len(binario) >= gltf["buffers"][0]["byteLength"]
    de_novo = glb.escrever(gltf, binario)
    gltf2, binario2 = glb.ler(de_novo)
    assert gltf2 == gltf
    assert binario2[:gltf["buffers"][0]["byteLength"]] == binario[:gltf["buffers"][0]["byteLength"]]


@pytest.mark.parametrize("estrago, pedaco", [
    (lambda d: b"XXXX" + d[4:], "assinatura"),
    (lambda d: d[:4] + struct.pack("<I", 3) + d[8:], "versão"),
    (lambda d: d[:8] + struct.pack("<I", len(d) + 10) + d[12:], "tamanho"),
    (lambda d: d[:20], "menor"),
])
def test_arquivo_estragado_e_recusado(estrago, pedaco):
    with pytest.raises(glb.GlbInvalido):
        glb.ler(estrago(glb_caixa()))


def test_arquivo_que_nao_e_glb():
    with pytest.raises(glb.GlbInvalido):
        glb.ler(b"ISO-10303-21;\nHEADER;\n")


def test_recurso_externo_e_listado_e_recusado():
    """Refutação do item: glTF com textura de fora não entra — o navegador buscaria em servidor de terceiro."""
    gltf, _ = glb.ler(glb_com_textura_externa())
    assert glb.recursos_externos(gltf) == ["https://exemplo.invalido/textura.png"]
    with pytest.raises(glb.GlbInvalido) as e:
        glb.exigir_embutido(gltf)
    assert "recurso externo" in str(e.value)


def test_recurso_embutido_em_data_uri_passa():
    gltf, _ = glb.ler(glb_caixa())
    gltf["images"] = [{"uri": "data:image/png;base64,iVBORw0KGgo="}]
    assert glb.recursos_externos(gltf) == []
    glb.exigir_embutido(gltf)  # não levanta


def test_caixa_bate_com_as_dimensoes_declaradas():
    gltf, binario = glb.ler(glb_caixa())
    minimo, maximo = glb.caixa(gltf, binario)
    assert maximo[0] - minimo[0] == pytest.approx(LARGURA_M, abs=1e-4)
    assert maximo[1] - minimo[1] == pytest.approx(CAIXA_ALTURA_M, abs=1e-4)
    assert maximo[2] - minimo[2] == pytest.approx(PROFUNDIDADE_M, abs=1e-4)


def test_caixa_aplica_a_matriz_do_no():
    gltf, binario = glb.ler(glb_caixa())
    gltf["nodes"][0]["translation"] = [100.0, 5.0, -3.0]
    minimo, maximo = glb.caixa(gltf, binario)
    assert minimo[0] == pytest.approx(100.0, abs=1e-4)
    assert maximo[0] == pytest.approx(100.0 + LARGURA_M, abs=1e-4)
    assert minimo[1] == pytest.approx(5.0, abs=1e-4)


def test_caixa_aplica_escala_do_no():
    gltf, binario = glb.ler(glb_caixa())
    gltf["nodes"][0]["scale"] = [2.0, 2.0, 2.0]
    minimo, maximo = glb.caixa(gltf, binario)
    assert maximo[0] - minimo[0] == pytest.approx(2 * LARGURA_M, abs=1e-4)


def test_modelo_sem_malha_levanta():
    gltf, binario = glb.ler(glb_caixa())
    gltf["nodes"] = [{"name": "vazio"}]
    gltf["scenes"] = [{"nodes": [0]}]
    with pytest.raises(glb.GlbInvalido):
        glb.caixa(gltf, binario)


def test_ler_acessor_devolve_os_vertices():
    gltf, binario = glb.ler(glb_caixa())
    pontos = glb.ler_acessor(gltf, binario, 0)
    assert len(pontos) == 8
    assert all(len(p) == 3 for p in pontos)
    assert max(p[0] for p in pontos) == pytest.approx(LARGURA_M, abs=1e-4)
