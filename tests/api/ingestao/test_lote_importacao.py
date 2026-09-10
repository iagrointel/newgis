"""Importação em LOTE (item L6-02-o): agrupa N chamadas de `POST /api/importacoes` + `PUT .../confirmar`
numa só, sem reescrever a inspeção/carga do L0-04 — `app.intercambio.lote_importar` só faz o loop em cima de
`app.ingestao.rotas.preparar_importacao`/`preparar_confirmacao`. Reusa o harness inteiro de
`tests/api/ingestao/conftest.py` (Ingestor, dados gerados) e o worker de `tests/api/exportacao/conftest.py`
(nenhum worker novo é escrito para este item)."""

from __future__ import annotations

from tests.api.exportacao.conftest import worker_exportacao  # noqa: F401 -- reusa o worker já testado
from tests.api.ingestao.conftest import GERADOS, esperar_job


def _preencher_confirmacao(proposta: dict, importacao_id: str) -> dict:
    perguntas = (proposta or {}).get("perguntas") or []
    entrada = {"importacao_id": importacao_id}
    if "crs" in perguntas:
        entrada["crs"] = {"srid": (proposta.get("crs") or {}).get("sugestao") or 4674}
    if "codificacao" in perguntas:
        entrada["codificacao"] = {"valor": "UTF-8"}
    return entrada


def test_lote_de_3_arquivos_cria_3_importacoes_e_publica_3_camadas(
    ingestor_a, worker_exportacao, sessao_a  # noqa: F811 -- fixture reusada por nome (import acima)
):
    arquivos = [("cobertura.gpkg", "gpkg"), ("cobertura.geojson", "geojson"), ("lugares_pv.csv", "csv")]
    itens_pedido = []
    for nome, formato in arquivos:
        obj = ingestor_a.enviar_arquivo(GERADOS / nome)
        item_id = ingestor_a.item_arquivo(obj, nome)
        itens_pedido.append({"arquivo_id": item_id, "formato": formato})

    r = sessao_a.post("/api/intercambio/importacoes-lote", json={"itens": itens_pedido})
    assert r.status_code == 202, r.text
    lote_id = r.json()["lote_id"]
    itens_criados = r.json()["itens"]
    assert len(itens_criados) == 3, itens_criados

    for item in itens_criados:
        job = esperar_job(sessao_a, item["job_id"], timeout=60)
        assert job["estado"] == "concluido", job

    r2 = sessao_a.get(f"/api/intercambio/importacoes-lote/{lote_id}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["total"] == 3
    itens_propostos = r2.json()["itens"]
    assert {i["estado"] for i in itens_propostos} == {"proposta"}, itens_propostos

    corpo_confirmar = {"itens": [_preencher_confirmacao(i["proposta"], i["id"]) for i in itens_propostos]}
    r3 = sessao_a.put(f"/api/intercambio/importacoes-lote/{lote_id}/confirmar", json=corpo_confirmar)
    assert r3.status_code == 202, r3.text
    assert len(r3.json()["itens"]) == 3

    for item in r3.json()["itens"]:
        job = esperar_job(sessao_a, item["job_id"], timeout=90)
        assert job["estado"] == "concluido", job

    r4 = sessao_a.get("/api/importacoes", params={"lote_id": lote_id})
    assert r4.status_code == 200, r4.text
    finais = r4.json()["itens"]
    assert len(finais) == 3
    for f in finais:
        assert f["estado"] == "concluida", f
        assert f["lote_id"] == lote_id
        ingestor_a.camadas.append(f["item_id"])  # teardown do fixture apaga a camada de verdade


def test_lote_com_formato_invalido_e_atomico_nao_cria_nenhuma_importacao(ingestor_a, sessao_a):
    """O lote é UMA transação: se o item 2 de 2 tem formato inexistente, o item 1 (válido) também não vira
    linha em `plat.importacao` (rollback) — a mesma garantia que a importação avulsa já dava para 1 arquivo."""
    obj = ingestor_a.enviar_arquivo(GERADOS / "cobertura.gpkg")
    item_id = ingestor_a.item_arquivo(obj, "cobertura.gpkg")

    antes = sessao_a.get("/api/importacoes", params={"limite": 1}).json()["total"]
    r = sessao_a.post("/api/intercambio/importacoes-lote", json={"itens": [
        {"arquivo_id": item_id, "formato": "gpkg"},
        {"arquivo_id": item_id, "formato": "formato-que-nao-existe"},
    ]})
    assert r.status_code == 422, r.text
    depois = sessao_a.get("/api/importacoes", params={"limite": 1}).json()["total"]
    assert depois == antes, "o lote deveria ser atômico: nenhuma importação deveria ter sido criada"
