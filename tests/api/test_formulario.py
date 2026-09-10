"""Portão do item L5-03-form-builder: construtor de formulário de atributos arrasta-e-solta.

`FabricaCamada` (tests/api/test_edicao_transacional.py) cria uma camada de verdade (mesma
`plat.camada_preparar` da ingestão); aqui uma camada PRÓPRIA (`zt_l503_*`, sem `regras_campo`
pré-fabricada) prova que é o FORMULÁRIO PUBLICADO — não outro mecanismo — que passa a exigir o
campo obrigatório, o domínio, a condicional e o cálculo, nos DOIS caminhos de escrita (edição web
`POST /api/camadas/{id}/edicoes` e campo `POST /api/campo/visitas`), refutação do item: "adversário
define campo obrigatório e submete sem ele pela API"."""

from __future__ import annotations

import uuid

import pytest

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import ids_por_slug


def _ponto(lon=-46.5, lat=-23.5):
    return {"type": "Point", "coordinates": [lon, lat]}


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


@pytest.fixture
def camada(fabrica, conexao_plat_app):
    """Sem `regras_campo`: qualquer obrigatório/domínio que os testes virem tem de ter vindo do
    formulário publicado, nunca de configuração pré-existente da camada."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id,
        campos=[
            {"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
            {"nome": "ativo", "tipo": "boolean"}, {"nome": "area", "tipo": "double precision"},
            {"nome": "total", "tipo": "double precision"},
        ],
        geometria="Point",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


@pytest.fixture
def camada_b(fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo2")
    item_id, dados = fabrica.criar(
        "demo2", ids["demo2"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="Point",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo2"], "admin_id": admin_id}


def _desenho_basico():
    """grupo único: nome (obrigatório incondicional), categoria (domínio A/B/C), ativo (obrigatório SÓ
    quando categoria == 'A' — condicional), total (calculado = area * 2, cliente nunca decide)."""
    return {
        "grupos": [{
            "id": "g1", "titulo": "Dados", "campos": [
                {"id": "c_nome", "campo": "nome", "widget": "texto", "obrigatorio": True},
                {"id": "c_categoria", "campo": "categoria", "widget": "selecao",
                 "dominio": {"valores": ["A", "B", "C"]}},
                {"id": "c_ativo", "campo": "ativo", "widget": "booleano", "obrigatorio": True,
                 "obrigatorio_se": "$categoria == 'A'"},
                {"id": "c_area", "campo": "area", "widget": "numero"},
                {"id": "c_total", "campo": "total", "widget": "numero", "calculo": "$area * 2"},
            ],
        }],
    }


def _publicar(sessao, camada_id, desenho=None):
    desenho = desenho or _desenho_basico()
    r = sessao.post(f"/api/camadas/{camada_id}/formulario/versoes", json={"desenho": desenho})
    assert r.status_code == 201, r.text
    versao = r.json()["versao"]
    r = sessao.post(f"/api/camadas/{camada_id}/formulario/versoes/{versao}/publicar")
    assert r.status_code == 200, r.text
    return versao


# ---------------------------------------------------------------- desenho: validação do construtor
def test_salvar_recusa_campo_que_nao_existe_na_camada(sessao_a, camada):
    desenho = {"grupos": [{"id": "g1", "campos": [
        {"id": "c1", "campo": "nao_existe", "widget": "texto"},
    ]}]}
    r = sessao_a.post(f"/api/camadas/{camada['id']}/formulario/versoes", json={"desenho": desenho})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "formulario_campo_inexistente", r.text


def test_salvar_recusa_expressao_invalida(sessao_a, camada):
    desenho = {"grupos": [{"id": "g1", "campos": [
        {"id": "c1", "campo": "nome", "widget": "texto", "calculo": "$area +"},
    ]}]}
    r = sessao_a.post(f"/api/camadas/{camada['id']}/formulario/versoes", json={"desenho": desenho})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "formulario_expressao_invalida", r.text


def test_publicar_devolve_desenho_em_get_formulario(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    r = sessao_a.get(f"/api/camadas/{camada['id']}/formulario")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["desenho"] is not None
    nomes = {c["campo"] for g in corpo["desenho"]["grupos"] for c in g["campos"]}
    assert nomes == {"nome", "categoria", "ativo", "area", "total"}


# ---------------------------------------------------------------- RLS: outro inquilino não vê
def test_rls_outro_inquilino_nao_le_nem_edita_formulario(sessao_a, sessao_b, camada, camada_b):
    _publicar(sessao_a, camada["id"])
    r = sessao_b.get(f"/api/camadas/{camada['id']}/formulario/versoes")
    assert r.status_code == 404, r.text
    r = sessao_b.post(f"/api/camadas/{camada['id']}/formulario/versoes", json={"desenho": _desenho_basico()})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------- refutação (edição web): obrigatório
def test_edicao_sem_campo_obrigatorio_incondicional_e_422(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    corpo = {"adicionar": [{"atributos": {"categoria": "B"}, "geometria": _ponto()}], "atualizar": [], "apagar": []}
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio", r.text


def test_edicao_condicional_obrigatoria_quando_categoria_a(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "x", "categoria": "A"}, "geometria": _ponto()}],
        "atualizar": [], "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 422, r.text
    corpo_r = r.json()
    assert corpo_r["erro"] == "campo_obrigatorio"
    assert corpo_r["detalhe"]["campo"] == "ativo", corpo_r


def test_edicao_condicional_nao_obrigatoria_quando_categoria_b(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "x", "categoria": "B", "area": 5}, "geometria": _ponto()}],
        "atualizar": [], "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    item = r.json()["adicionar"][0]
    assert item["sucesso"] is True, item
    assert item["atributos"]["total"] == 10, "calculado deveria ser area*2"


def test_edicao_calculo_ignora_valor_do_cliente(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{
            "atributos": {"nome": "x", "categoria": "B", "area": 5, "total": 999999}, "geometria": _ponto(),
        }],
        "atualizar": [], "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    item = r.json()["adicionar"][0]
    assert item["sucesso"] is True, item
    assert item["atributos"]["total"] == 10, "servidor tem de recomputar, nunca aceitar o valor do cliente"


def test_edicao_dominio_fora_da_lista_e_422(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "x", "categoria": "Z"}, "geometria": _ponto()}],
        "atualizar": [], "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "fora_do_dominio", r.text


# ---------------------------------------------------------------- refutação (PWA de campo): mesmo desenho
def _visita_corpo(camada_id, dados):
    return {
        "cliente_uuid": str(uuid.uuid4()), "camada_id": camada_id, "globalid": str(uuid.uuid4()),
        "status": "visitado", "capturado_em": "2026-09-10T12:00:00Z", "dados": dados,
    }


def test_campo_sem_obrigatorio_e_422(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    r = sessao_a.post("/api/campo/visitas", json=_visita_corpo(camada["id"], {"categoria": "B"}))
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio", r.text


def test_campo_condicional_obrigatoria_quando_categoria_a(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    r = sessao_a.post("/api/campo/visitas", json=_visita_corpo(camada["id"], {"nome": "x", "categoria": "A"}))
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"]["campo"] == "ativo", r.text


def test_campo_calculo_e_condicional_ok_quando_categoria_b(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    r = sessao_a.post(
        "/api/campo/visitas",
        json=_visita_corpo(camada["id"], {"nome": "x", "categoria": "B", "area": 5, "total": 999}),
    )
    assert r.status_code == 201, r.text
    assert r.json()["dados"]["total"] == 10, "mesmo motor: cálculo do formulário vale igual no PWA de campo"


def test_campo_sem_formulario_publicado_continua_livre(sessao_a, camada):
    """Camada sem formulário publicado: comportamento de sempre, `dados` livre sem validação nenhuma —
    prova de que este item não muda nada em camada que ainda não tem formulário (compatibilidade)."""
    r = sessao_a.post("/api/campo/visitas", json=_visita_corpo(camada["id"], {"qualquer": "coisa"}))
    assert r.status_code == 201, r.text

