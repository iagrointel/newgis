"""Portão do item L2-03-edicao: dividir/unir feição (`app/edicao/combinar.py`). Reusa a mesma fábrica de
camada de `tests/api/test_edicao_transacional.py`, agora com uma camada de LINHA para os testes de divisão."""

from __future__ import annotations

import uuid

import pytest

from tests.api.test_edicao_transacional import _admin_usuario_id, camada_b, fabrica  # noqa: F401
from tests.api.test_rls import ids_por_slug


def _linha(coords):
    return {"type": "LineString", "coordinates": coords}


@pytest.fixture
def camada_linha(fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="LineString",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


@pytest.fixture
def camada_poligono(fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="MultiPolygon",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


def _adicionar(sessao, camada_id, geometria, nome="x"):
    r = sessao.post(
        f"/api/camadas/{camada_id}/edicoes",
        json={"adicionar": [{"atributos": {"nome": nome}, "geometria": geometria}], "atualizar": [], "apagar": []},
    )
    assert r.status_code == 200, r.text
    return r.json()["adicionar"][0]


# ---------------------------------------------------------------- unir
def test_unir_duas_linhas_conectadas_vira_uma(sessao_a, camada_linha):
    a = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.60, -23.50], [-46.55, -23.50]]), nome="trecho-a")
    b = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.55, -23.50], [-46.50, -23.50]]), nome="trecho-b")
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/unir",
        json={"ids": [a["id"], b["id"]], "versoes": {a["id"]: a["versao"], b["id"]: b["versao"]}},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["sucesso"] is True
    assert set(corpo["ids_apagados"]) == {a["id"], b["id"]}

    r2 = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/edicoes",
        json={"adicionar": [], "atualizar": [], "apagar": [{"id": a["id"]}]},
    )
    assert r2.status_code == 404  # já não existe: a união apagou (modo transação propaga o erro)

    hist = sessao_a.get(f"/api/camadas/{camada_linha['id']}/feicoes/{corpo['id']}/historico").json()
    assert hist[0]["operacao"] == "inserir"


def test_unir_poligonos_adjacentes(sessao_a, camada_poligono):
    quad1 = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    quad2 = {"type": "Polygon", "coordinates": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]}
    a = _adicionar(sessao_a, camada_poligono["id"], quad1)
    b = _adicionar(sessao_a, camada_poligono["id"], quad2)
    r = sessao_a.post(
        f"/api/camadas/{camada_poligono['id']}/feicoes/unir",
        json={"ids": [a["id"], b["id"]], "versoes": {a["id"]: a["versao"], b["id"]: b["versao"]}},
    )
    assert r.status_code == 200, r.text


def test_unir_menos_de_duas_e_recusado(sessao_a, camada_linha):
    # o próprio contrato de entrada (min_length=2) já recusa antes de chegar na regra de negócio
    a = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.6, -23.5], [-46.5, -23.5]]))
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/unir",
        json={"ids": [a["id"]], "versoes": {a["id"]: a["versao"]}},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "validacao"


def test_unir_com_versao_desatualizada_e_conflito(sessao_a, camada_linha):
    a = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.6, -23.5], [-46.55, -23.5]]))
    b = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.55, -23.5], [-46.5, -23.5]]))
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/unir",
        json={"ids": [a["id"], b["id"]], "versoes": {a["id"]: 999, b["id"]: b["versao"]}},
    )
    assert r.status_code == 409
    assert r.json()["erro"] == "conflito_versao"


def test_unir_sem_declarar_versao_de_uma_das_feicoes_e_422(sessao_a, camada_linha):
    """Achado do adversário (07/09): `versoes` incompleto (ou `{}`) não pode deixar a checagem de
    concorrência rodar só para os ids presentes — a origem sem versão declarada tem de ser recusada
    (422), nunca unida silenciosamente por cima de uma edição concorrente que o cliente nunca viu."""
    a = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.6, -23.5], [-46.55, -23.5]]))
    b = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.55, -23.5], [-46.5, -23.5]]))
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/edicoes",
        json={"atualizar": [{"id": a["id"], "versao": 1, "atributos": {}}]},
    )
    assert r.status_code == 200, r.text  # sobe a versão de `a` para 2 por baixo do tapete

    r2 = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/unir",
        json={"ids": [a["id"], b["id"]], "versoes": {b["id"]: b["versao"]}},  # falta a versão de `a`
    )
    assert r2.status_code == 422
    assert r2.json()["erro"] == "versao_ausente"
    assert r2.json()["detalhe"]["id"] == a["id"]


def test_unir_feicao_inexistente_e_404(sessao_a, camada_linha):
    a = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.6, -23.5], [-46.5, -23.5]]))
    outro = str(uuid.uuid4())
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/unir",
        json={"ids": [a["id"], outro], "versoes": {}},
    )
    assert r.status_code == 404


def test_unir_de_outro_inquilino_e_404(sessao_a, sessao_b, camada_linha, camada_b):
    a = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.6, -23.5], [-46.5, -23.5]]))
    b = _adicionar(sessao_b, camada_b["id"], {"type": "Point", "coordinates": [-46.5, -23.5]})
    r = sessao_b.post(
        f"/api/camadas/{camada_b['id']}/feicoes/unir",
        json={"ids": [a["id"], b["id"]], "versoes": {}},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- dividir
def test_dividir_linha_no_meio(sessao_a, camada_linha):
    f = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.60, -23.50], [-46.50, -23.50]]), nome="rota")
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/dividir",
        json={"id": f["id"], "versao": f["versao"], "ponto": [-46.55, -23.50]},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["id_apagado"] == f["id"]
    assert len(corpo["novas"]) == 2

    r2 = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/edicoes",
        json={"adicionar": [], "atualizar": [], "apagar": [{"id": f["id"]}]},
    )
    assert r2.status_code == 404  # a origem foi apagada pela divisão

    for nova in corpo["novas"]:
        hist = sessao_a.get(f"/api/camadas/{camada_linha['id']}/feicoes/{nova['id']}/historico").json()
        assert hist[0]["operacao"] == "inserir"
        assert hist[0]["atributos_depois"]["nome"] == "rota"  # atributo herdado da origem


def test_dividir_no_extremo_e_recusado(sessao_a, camada_linha):
    f = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.60, -23.50], [-46.50, -23.50]]))
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/dividir",
        json={"id": f["id"], "versao": f["versao"], "ponto": [-46.60, -23.50]},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "ponto_de_divisao_invalido"


def test_dividir_poligono_e_recusado(sessao_a, camada_poligono):
    quad = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    f = _adicionar(sessao_a, camada_poligono["id"], quad)
    r = sessao_a.post(
        f"/api/camadas/{camada_poligono['id']}/feicoes/dividir",
        json={"id": f["id"], "versao": f["versao"], "ponto": [0.5, 0.5]},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "divisao_nao_suportada"


def test_dividir_com_versao_desatualizada_e_conflito(sessao_a, camada_linha):
    f = _adicionar(sessao_a, camada_linha["id"], _linha([[-46.60, -23.50], [-46.50, -23.50]]))
    r = sessao_a.post(
        f"/api/camadas/{camada_linha['id']}/feicoes/dividir",
        json={"id": f["id"], "versao": 999, "ponto": [-46.55, -23.50]},
    )
    assert r.status_code == 409
    assert r.json()["erro"] == "conflito_versao"
