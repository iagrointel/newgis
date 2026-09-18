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

# As FIXTURES `fabrica`/`camada` vivem em tests/api/test_formulario.py e não viajam com o `import` dos
# ajudantes: sem trazê-las para o espaço de nomes deste módulo, os dois testes abaixo morriam em
# "fixture 'camada' not found" — um erro de PREPARO que o `xfail(strict=True)` mascarava de refutação
# viva. Medido em 18/09/2026: com a fixture no lugar, os dois passam.
from tests.api.test_formulario import _ponto, _publicar, _visita_corpo, camada, fabrica  # noqa: F401

ITEM = "L5-03-form-builder"


def test_edicao_web_recusa_campo_obrigatorio_com_string_vazia(sessao_a, camada):  # noqa: F811 — fixture do pytest, importada de proposito
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "", "categoria": "B"}, "geometria": _ponto()}],
        "atualizar": [],
        "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio", r.text


def test_pwa_campo_recusa_campo_obrigatorio_com_string_vazia(sessao_a, camada):  # noqa: F811 — fixture do pytest, importada de proposito
    _publicar(sessao_a, camada["id"])
    r = sessao_a.post("/api/campo/visitas", json=_visita_corpo(camada["id"], {"nome": "", "categoria": "B"}))
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio", r.text


def test_edicao_web_com_campo_obrigatorio_preenchido_continua_passando(sessao_a, camada):  # noqa: F811 — fixture do pytest, importada de proposito
    """Par positivo 1: recusar a string vazia não pode ter fechado a escrita legítima — a mesma feição
    com o campo obrigatório preenchido continua entrando."""
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "posto 1", "categoria": "B"}, "geometria": _ponto()}],
        "atualizar": [],
        "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 200, r.text


def test_zero_e_falso_nao_contam_como_campo_vazio(sessao_a, camada):  # noqa: F811 — fixture do pytest, importada de proposito
    """Par positivo 2: `0`, `0.0` e `False` são VALORES preenchidos, não ausência. A camada exige `ativo`
    quando `categoria == 'A'` (condicional do desenho); mandar `ativo=False` e `area=0` tem de passar."""
    _publicar(sessao_a, camada["id"])
    corpo = {
        "adicionar": [{"atributos": {"nome": "posto 2", "categoria": "A", "ativo": False, "area": 0},
                       "geometria": _ponto()}],
        "atualizar": [],
        "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
