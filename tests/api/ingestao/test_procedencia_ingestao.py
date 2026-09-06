"""Procedência de camada importada (item L0-09-a-procedencia), medida no fluxo real de ingestão.

Cláusula do portão: "toda camada importada nasce com >= 4 campos preenchidos (sha256, data_acesso, gerador,
metodo) medidos no teste". Refutação do adversário: o mesmo arquivo importado duas vezes tem o mesmo sha256;
um arquivo com um byte diferente tem sha256 diferente.
"""

import pytest

from app.catalogo import procedencia
from tests.api.conftest import PREFIXO_TESTE
from tests.api.ingestao.conftest import GERADOS, esperar_job

ITEM = "L0-09-a-procedencia"
pytestmark = pytest.mark.skipif(not GERADOS.exists(), reason="rode `venv/bin/python tests/dados/gerar.py` antes")


def _importar_bytes(ingestor, sessao, tmp_path, nome: str, conteudo: bytes, formato: str) -> dict:
    """Sobe um conteúdo qualquer como arquivo e roda a importação até o fim; devolve a importação final."""
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo)
    obj = ingestor.enviar_arquivo(caminho)
    item_id = ingestor.item_arquivo(obj, nome)
    r = sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": formato})
    assert r.status_code == 202, r.text
    esperar_job(sessao, r.json()["job_id"], timeout=60)
    return ingestor.confirmar(r.json()["importacao_id"])


def _procedencia_do_item(sessao, item_id: str) -> dict:
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_camada_importada_nasce_com_os_quatro_campos_medidos(ingestor_a, sessao_a, medida):
    importacao_id, insp = ingestor_a.importar("cobertura.gpkg", "gpkg")
    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final

    j = _procedencia_do_item(sessao_a, final["item_id"])
    bloco = j["dados"]["procedencia"]
    preenchidos = [c for c in procedencia.CAMPOS_AUTOMATICOS if bloco.get(c)]
    assert preenchidos == list(procedencia.CAMPOS_AUTOMATICOS), bloco
    assert len(bloco["sha256"]) == 64
    assert bloco["gerador"].startswith("plat ingestao.carregar ")
    assert bloco["metodo"] == "ogr2ogr + ST_MakeValid"
    assert bloco["data_de_acesso"]  # data em que o arquivo entrou, não a data de hoje inventada
    # origem campo a campo: o que a máquina mediu está marcado como medido
    assert bloco["origem"]["sha256"] == "medido"
    assert bloco["origem"]["gerador"] == "medido"
    assert bloco["origem"]["metodo"] == "medido"
    assert bloco["origem"]["data_de_acesso"] == "medido"
    assert bloco["origem"]["fonte"] == "declarado"  # o nome do arquivo foi o usuário quem deu
    # o que só o usuário pode declarar continua NULL: inferir licença/url do nome do arquivo é o erro que a
    # regra da casa proíbe
    assert bloco["licenca"] is None and bloco["url"] is None
    assert j["procedencia"]["pontuacao"] is not None and j["procedencia"]["pontuacao"] > 0
    medida(ITEM)(
        "campos_medidos_em_camada_importada", len(preenchidos), "de 4",
        "pytest tests/api/ingestao/test_procedencia_ingestao.py::"
        "test_camada_importada_nasce_com_os_quatro_campos_medidos",
    )


def test_mesmo_arquivo_duas_vezes_tem_o_mesmo_sha256(ingestor_a, sessao_a, medida):
    """Refutação do adversário, parte 1."""
    conteudo = (GERADOS / "cobertura.geojson").read_bytes()
    a = ingestor_a.importar("cobertura.geojson", "geojson")
    fim_a = ingestor_a.confirmar(a[0])
    b = ingestor_a.importar("cobertura.geojson", "geojson")
    fim_b = ingestor_a.confirmar(b[0])
    assert fim_a["estado"] == fim_b["estado"] == "concluida"
    sha_a = _procedencia_do_item(sessao_a, fim_a["item_id"])["dados"]["procedencia"]["sha256"]
    sha_b = _procedencia_do_item(sessao_a, fim_b["item_id"])["dados"]["procedencia"]["sha256"]
    assert sha_a == sha_b, "o mesmo arquivo gerou dois hashes diferentes"
    assert fim_a["item_id"] != fim_b["item_id"], "duas importações do mesmo arquivo são dois itens"
    import hashlib

    assert sha_a == hashlib.sha256(conteudo).hexdigest(), "o hash gravado não é o do arquivo de origem"
    medida(ITEM)(
        "sha256_estavel_no_reimporte", 1, "booleano",
        "pytest tests/api/ingestao/test_procedencia_ingestao.py::test_mesmo_arquivo_duas_vezes_tem_o_mesmo_sha256",
    )


def test_um_byte_diferente_muda_o_sha256(ingestor_a, sessao_a, tmp_path):
    """Refutação do adversário, parte 2: um byte a mais (uma quebra de linha no fim, que o GeoJSON aceita e
    o GDAL lê igual) já muda o hash — o hash é do CONTEÚDO, não do nome nem do tamanho declarado."""
    original = (GERADOS / "cobertura.geojson").read_bytes()
    alterado = original + b"\n"
    assert len(alterado) == len(original) + 1

    fim_1 = _importar_bytes(ingestor_a, sessao_a, tmp_path, f"{PREFIXO_TESTE}_igual.geojson", original, "geojson")
    fim_2 = _importar_bytes(ingestor_a, sessao_a, tmp_path, f"{PREFIXO_TESTE}_1byte.geojson", alterado, "geojson")
    assert fim_1["estado"] == fim_2["estado"] == "concluida", (fim_1, fim_2)
    sha_1 = _procedencia_do_item(sessao_a, fim_1["item_id"])["dados"]["procedencia"]["sha256"]
    sha_2 = _procedencia_do_item(sessao_a, fim_2["item_id"])["dados"]["procedencia"]["sha256"]
    assert sha_1 != sha_2, "um byte diferente devolveu o mesmo hash"
