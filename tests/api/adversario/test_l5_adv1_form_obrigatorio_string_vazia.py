"""Adversário de linha L5 builder (parte 1) — item L5-03-form-builder.

Achado: a checagem de "campo obrigatório" (`app/edicao/servico.py::validar_atributos` e
`app/formulario/motor.py::validar_dados_livre`, os DOIS caminhos que o próprio item promete cobrir —
edição web e PWA de campo) só olha `campo not in limpos or limpos[campo] is None`. Uma string vazia (`""`)
enviada explicitamente NÃO é `None` e passa incólume — o adversário "submete sem o campo obrigatório"
mandando `""` em vez de omitir a chave, e os dois caminhos aceitam.

Prova de que é a MESMA causa raiz nos dois lugares (não dois bugs independentes): os dois trechos usam a
identidade textual `nome not in limpos or limpos[nome] is None` / `campo not in limpos or limpos[campo] is
None` — nenhum dos dois trata string vazia como ausência de valor.

Os testes oficiais do item (`tests/api/test_formulario.py::test_edicao_sem_campo_obrigatorio_incondicional_e_422`
e `::test_campo_sem_obrigatorio_e_422`) só testam a chave OMITIDA — nunca a string vazia."""

import pytest

from tests.api.test_formulario import _ponto, _publicar, _visita_corpo

ITEM = "L5-03-form-builder"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-03: app/edicao/servico.py::validar_atributos só recusa campo obrigatório ausente/None; "
        "string vazia '' passa (nome not in limpos or limpos[nome] is None não cobre '' ) na edição web "
        "POST /api/camadas/{id}/edicoes"
    ),
)
def test_edicao_web_recusa_campo_obrigatorio_com_string_vazia(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "", "categoria": "B"}, "geometria": _ponto()}],
        "atualizar": [],
        "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio", r.text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-03: app/formulario/motor.py::validar_dados_livre (mesmo texto de checagem) tem a MESMA lacuna "
        "na rota de campo POST /api/campo/visitas — string vazia '' para um campo obrigatório é aceita"
    ),
)
def test_pwa_campo_recusa_campo_obrigatorio_com_string_vazia(sessao_a, camada):
    _publicar(sessao_a, camada["id"])
    r = sessao_a.post("/api/campo/visitas", json=_visita_corpo(camada["id"], {"nome": "", "categoria": "B"}))
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio", r.text
