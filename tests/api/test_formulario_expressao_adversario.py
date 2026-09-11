"""Achados da auditoria de 10/09/2026 sobre o item L5-03-form-builder.

Dois defeitos foram MEDIDOS na instância viva, e não em leitura de código:

1. Um desenho cuja expressão referencia um campo inexistente PUBLICAVA com HTTP 200, e a camada
   ficava sem edição: toda gravação seguinte devolvia 409 `campo não permitido`, porque a expressão
   só era avaliada na hora de escrever. Quem paga é o editor, não quem desenhou.
2. Dois campos calculados que se referenciam (`nome = $agente`, `agente = $nome`) publicavam e, ao
   gravar, saíam os DOIS NULOS com HTTP 200 — o valor digitado pelo usuário era descartado em
   silêncio. Perda silenciosa de dado é pior que recusar o desenho.

Ambos passam a morrer na validação do desenho, que roda ao salvar rascunho e de novo ao publicar.
"""
import pytest

from app.erros import ErroAPI
from app.formulario.motor import validar_desenho

CAMPOS = {n: {"nome": n} for n in ("nome", "agente", "kv_max")}


def _desenho(campos):
    return {"grupos": [{"id": "g", "titulo": "x", "campos": campos}]}


def _codigo(exc: ErroAPI) -> str:
    return getattr(exc, "codigo", None) or exc.args[1]


def test_expressao_com_campo_inexistente_e_recusada():
    d = _desenho([{"id": "c", "campo": "nome", "widget": "texto", "calculo": "$fantasma * 2"}])
    with pytest.raises(ErroAPI) as e:
        validar_desenho(d, CAMPOS)
    assert _codigo(e.value) == "formulario_expressao_invalida"
    assert "fantasma" in e.value.args[2]


def test_condicional_com_campo_inexistente_e_recusada():
    d = _desenho([{"id": "c", "campo": "nome", "widget": "texto", "obrigatorio_se": "$xpto == 1"}])
    with pytest.raises(ErroAPI) as e:
        validar_desenho(d, CAMPOS)
    assert _codigo(e.value) == "formulario_expressao_invalida"


def test_laco_entre_dois_calculados_e_recusado():
    d = _desenho([
        {"id": "c1", "campo": "nome", "widget": "texto", "calculo": "$agente"},
        {"id": "c2", "campo": "agente", "widget": "texto", "calculo": "$nome"},
    ])
    with pytest.raises(ErroAPI) as e:
        validar_desenho(d, CAMPOS)
    assert _codigo(e.value) == "formulario_calculo_circular"


def test_campo_que_se_calcula_a_si_mesmo_e_recusado():
    d = _desenho([{"id": "c", "campo": "nome", "widget": "texto", "calculo": "$nome + 1"}])
    with pytest.raises(ErroAPI) as e:
        validar_desenho(d, CAMPOS)
    assert _codigo(e.value) == "formulario_calculo_circular"


def test_cadeia_de_calculos_sem_laco_continua_valendo():
    """A trava de laço não pode recusar dependência legítima em cadeia (kv_max -> nome -> agente)."""
    d = _desenho([
        {"id": "c1", "campo": "nome", "widget": "texto", "calculo": "$kv_max"},
        {"id": "c2", "campo": "agente", "widget": "texto", "calculo": "$nome"},
    ])
    validar_desenho(d, CAMPOS)


def test_campo_nao_persistido_pode_ser_referenciado():
    """Campo declarado no desenho mas não gravado na tabela continua servindo de variável."""
    d = _desenho([
        {"id": "c1", "campo": "rascunho", "widget": "numero", "persistido": False},
        {"id": "c2", "campo": "nome", "widget": "texto", "calculo": "$rascunho * 2"},
    ])
    validar_desenho(d, CAMPOS)
