"""Árvore OGC 3D Tiles 1.1 gerada do GLB (item L2-09-c).

A cláusula do portão é "tileset 3D Tiles gerado valida no validador do 3d-tiles-tools". A conferência é
feita pelo validador OFICIAL (`3d-tiles-validator`, Apache-2.0, do CesiumGS), instalado por
`deploy/tiles3d_validador_instalar.sh` fora do repositório versionado. Sem ele o teste SALTA dizendo o
motivo — nunca passa por omissão, e nunca se conforma com um validador escrito por nós, que seria o
gerador se olhando no espelho.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.modelos3d import glb, ifc, montagem, posicionamento, tiles3d
from tests.apoio_modelos3d import ALTURA_M, IFC_ABERTO, LAT, LON, glb_caixa

RAIZ = Path(__file__).resolve().parents[2]
VALIDADOR = RAIZ / "var" / "tiles3d" / "node_modules" / ".bin" / "3d-tiles-validator"
ITEM = "L2-09-c-modelos-gltf-ifc-3dtiles"


@pytest.fixture(scope="module")
def glb_da_casa():
    modelo = ifc.carregar(IFC_ABERTO.read_bytes())
    dados, _ = montagem.montar(modelo.elementos, "casa-de-teste")
    return dados


def _escrever(tmp: Path, tileset: dict, conteudos: dict) -> Path:
    (tmp / "conteudo").mkdir(parents=True, exist_ok=True)
    (tmp / "tileset.json").write_bytes(tiles3d.escrever_json(tileset))
    for caminho, corpo in conteudos.items():
        (tmp / caminho).write_bytes(corpo)
    return tmp / "tileset.json"


def test_estrutura_minima_do_tileset(glb_da_casa):
    tileset, conteudos = tiles3d.gerar(glb_da_casa, LON, LAT, ALTURA_M, 0.0, 1.0, "casa")
    assert tileset["asset"]["version"] == "1.1"
    raiz = tileset["root"]
    assert raiz["refine"] == "ADD"
    assert len(raiz["transform"]) == 16
    assert len(raiz["boundingVolume"]["box"]) == 12
    assert raiz["children"]
    assert {f["content"]["uri"] for f in raiz["children"]} == set(conteudos)
    assert all(not c.startswith("/") and ".." not in c for c in conteudos)


def test_a_transformacao_poe_a_raiz_no_ponto_pedido(glb_da_casa):
    tileset, _ = tiles3d.gerar(glb_da_casa, LON, LAT, ALTURA_M, 0.0, 1.0, "casa")
    m = tileset["root"]["transform"]
    lon, lat, altura = posicionamento.ecef_para_geodesico(m[12], m[13], m[14])
    assert lon == pytest.approx(LON, abs=1e-7)
    assert lat == pytest.approx(LAT, abs=1e-7)
    assert altura == pytest.approx(ALTURA_M, abs=0.01)


def test_conteudo_de_cada_tile_e_um_glb_legivel(glb_da_casa):
    _, conteudos = tiles3d.gerar(glb_da_casa, LON, LAT, ALTURA_M)
    for corpo in conteudos.values():
        gltf, binario = glb.ler(corpo)
        assert gltf["scenes"][0]["nodes"]
        glb.exigir_embutido(gltf)


def test_o_guid_sobrevive_ao_recorte(glb_da_casa):
    """Recortar o modelo em tiles não pode perder o identificador: é ele que liga o clique à propriedade."""
    gltf_todo, _ = glb.ler(glb_da_casa)
    esperados = {n["extras"]["guid"] for n in gltf_todo["nodes"]}
    _, conteudos = tiles3d.gerar(glb_da_casa, LON, LAT, ALTURA_M)
    vistos = set()
    for corpo in conteudos.values():
        gltf, _ = glb.ler(corpo)
        for i in gltf["scenes"][0]["nodes"]:
            vistos.add(gltf["nodes"][i]["extras"]["guid"])
    assert vistos == esperados


def test_modelo_grande_e_dividido_em_quadrantes(glb_da_casa, monkeypatch):
    """Com o teto de nós por tile baixado, a mesma cena tem de sair em mais de um tile — e sem perder nó."""
    monkeypatch.setattr(tiles3d, "NOS_POR_TILE", 2)
    tileset, conteudos = tiles3d.gerar(glb_da_casa, LON, LAT, ALTURA_M)
    assert len(conteudos) > 1
    assert tileset["extras"]["tiles"] == len(conteudos)
    total = sum(len(glb.ler(c)[0]["scenes"][0]["nodes"]) for c in conteudos.values())
    assert total == tileset["extras"]["nos"]


def test_glb_com_recurso_externo_nao_vira_tileset():
    from tests.apoio_modelos3d import glb_com_textura_externa
    with pytest.raises(glb.GlbInvalido):
        tiles3d.gerar(glb_com_textura_externa(), LON, LAT, ALTURA_M)


def test_caixa_do_tile_esta_no_sistema_z_para_cima():
    """A caixa do 3D Tiles é Z para cima; o conteúdo é glTF, Y para cima. A altura da caixa de teste
    (8 m) tem de aparecer no TERCEIRO eixo da caixa, não no segundo."""
    tileset, _ = tiles3d.gerar(glb_caixa(), LON, LAT, ALTURA_M)
    caixa = tileset["root"]["boundingVolume"]["box"]
    from tests.apoio_modelos3d import CAIXA_ALTURA_M, LARGURA_M, PROFUNDIDADE_M
    assert caixa[3] * 2 == pytest.approx(LARGURA_M, abs=1e-3)        # meia-extensão no eixo X
    assert caixa[7] * 2 == pytest.approx(PROFUNDIDADE_M, abs=1e-3)   # eixo Y do tile = norte
    assert caixa[11] * 2 == pytest.approx(CAIXA_ALTURA_M, abs=1e-3)  # eixo Z do tile = vertical


@pytest.mark.skipif(not VALIDADOR.exists(),
                    reason="validador oficial ausente: rode bash deploy/tiles3d_validador_instalar.sh")
@pytest.mark.parametrize("nos_por_tile", [64, 2])
def test_o_validador_oficial_aprova_o_tileset(glb_da_casa, tmp_path, monkeypatch, nos_por_tile, medida):
    monkeypatch.setattr(tiles3d, "NOS_POR_TILE", nos_por_tile)
    tileset, conteudos = tiles3d.gerar(glb_da_casa, LON, LAT, ALTURA_M, 30.0, 1.0, "casa")
    alvo = _escrever(tmp_path, tileset, conteudos)
    r = subprocess.run([str(VALIDADOR), "--tilesetFile", str(alvo)], capture_output=True, text=True,
                       timeout=300, cwd=str(RAIZ / "var" / "tiles3d"))
    saida = r.stdout + r.stderr
    corpo = saida[saida.find("{"):saida.rfind("}") + 1]
    resultado = json.loads(corpo) if corpo else {}
    medida(ITEM)(
        f"validador_oficial_{nos_por_tile}_nos_por_tile",
        {"tiles": len(conteudos), "erros": resultado.get("numErrors"),
         "avisos": resultado.get("numWarnings"), "validador": "3d-tiles-validator 0.6.1"},
        "contagem",
        "bash deploy/tiles3d_validador_instalar.sh && "
        "venv/bin/pytest tests/unit/test_modelos3d_tiles3d.py -k validador_oficial",
    )
    assert resultado.get("numErrors") == 0, saida[-3000:]
    assert resultado.get("numWarnings") == 0, saida[-3000:]


@pytest.mark.skipif(shutil.which("node") is None, reason="node ausente")
def test_o_validador_reprova_um_tileset_quebrado(tmp_path):
    """Controle negativo: se o validador aprovasse qualquer coisa, o teste acima não provaria nada."""
    if not VALIDADOR.exists():
        pytest.skip("validador oficial ausente: rode bash deploy/tiles3d_validador_instalar.sh")
    tileset, conteudos = tiles3d.gerar(glb_caixa(), LON, LAT, ALTURA_M)
    tileset["root"].pop("geometricError")
    alvo = _escrever(tmp_path, tileset, conteudos)
    r = subprocess.run([str(VALIDADOR), "--tilesetFile", str(alvo)], capture_output=True, text=True,
                       timeout=300, cwd=str(RAIZ / "var" / "tiles3d"))
    saida = r.stdout + r.stderr
    corpo = saida[saida.find("{"):saida.rfind("}") + 1]
    assert json.loads(corpo).get("numErrors", 0) > 0, saida[-2000:]


def test_variavel_de_ambiente_nao_muda_o_resultado():
    """O gerador não lê ambiente: o mesmo GLB dá o mesmo tileset em qualquer máquina."""
    os.environ["PLAT_MODELO3D_INEXISTENTE"] = "1"
    try:
        a, _ = tiles3d.gerar(glb_caixa(), LON, LAT, ALTURA_M)
        b, _ = tiles3d.gerar(glb_caixa(), LON, LAT, ALTURA_M)
        assert a == b
    finally:
        os.environ.pop("PLAT_MODELO3D_INEXISTENTE", None)
