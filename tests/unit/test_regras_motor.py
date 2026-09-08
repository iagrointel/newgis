"""Motor das regras de atributo (item L2-10-d-regras-de-atributo, `app/regras/motor.py`), sem banco: cálculo que
dispara e preenche o campo, encadeamento por ordem, gatilho por campo, restrição com código/mensagem, regra
desabilitada, exclusão em massa, validação sob demanda, campos virtuais, e a refutação "regra que muda o próprio
campo gatilho" (ciclo detectado na configuração, nunca na edição)."""

from __future__ import annotations

import datetime
import decimal

import pytest

from app.erros import ErroAPI
from app.regras import motor

CAMPOS = [{"nome": "a", "tipo": "double precision"}, {"nome": "b", "tipo": "double precision"},
          {"nome": "rotulo", "tipo": "text"}, {"nome": "area_ha", "tipo": "double precision"},
          {"nome": "quando", "tipo": "timestamptz"}]


def _dados(regras=None, virtuais=None):
    return {"campos": CAMPOS, "regras": regras or [], "campos_virtuais": virtuais or []}


def _erro(dados, codigo):
    with pytest.raises(ErroAPI) as e:
        motor.compilar(dados)
    assert e.value.status_code == 422 and e.value.erro == codigo, (e.value.erro, e.value.mensagem)
    return e.value


def test_calculo_dispara_e_encadeia_na_ordem_declarada():
    comp = motor.compilar(_dados([
        {"id": "rotulo", "tipo": "calculo", "campo": "rotulo", "expressao": "Concatenar('b=', Texto($b))",
         "gatilhos": ["b"], "ordem": 2},
        {"id": "dobro", "tipo": "calculo", "campo": "b", "expressao": "$a * 2", "gatilhos": ["a"], "ordem": 1},
    ]))
    assert [r.id for r in comp.regras] == ["dobro", "rotulo"]
    saida, rodaram = motor.aplicar_edicao(comp, {"a": 21}, None, "inserir")
    assert saida == {"a": 21, "b": 42, "rotulo": "b=42"} and rodaram == ["dobro", "rotulo"]
    # atualização que não toca o gatilho: nenhuma das duas roda
    saida, rodaram = motor.aplicar_edicao(comp, {"area_ha": 1}, {"a": 1, "b": 2, "rotulo": "x"}, "atualizar")
    assert saida == {"area_ha": 1} and rodaram == []
    # atualização de `a` dispara a primeira, e o `b` calculado dispara a segunda (encadeamento)
    saida, rodaram = motor.aplicar_edicao(comp, {"a": 5}, {"a": 1, "b": 2, "rotulo": "x"}, "atualizar")
    assert saida == {"a": 5, "b": 10, "rotulo": "b=10"} and rodaram == ["dobro", "rotulo"]


def test_ordem_invertida_muda_o_resultado():
    """A mesma dupla com a ordem trocada: `rotulo` roda antes de `dobro` e lê o `b` ANTIGO — a ordem é respeitada
    literalmente, não inferida."""
    comp = motor.compilar(_dados([
        {"id": "rotulo", "tipo": "calculo", "campo": "rotulo", "expressao": "Concatenar('b=', Texto($b))", "ordem": 1},
        {"id": "dobro", "tipo": "calculo", "campo": "b", "expressao": "$a * 2", "ordem": 2},
    ]))
    saida, _ = motor.aplicar_edicao(comp, {"a": 5}, {"a": 1, "b": 2, "rotulo": "x"}, "atualizar")
    assert saida == {"a": 5, "rotulo": "b=2", "b": 10}


def test_restricao_recusa_com_codigo_e_mensagem_configurados():
    comp = motor.compilar(_dados([
        {"id": "positivo", "tipo": "restricao", "expressao": "$a >= 0", "codigo": "a_negativo",
         "mensagem": "a não pode ser negativo"},
    ]))
    assert motor.aplicar_edicao(comp, {"a": 0}, None, "inserir")[0] == {"a": 0}
    with pytest.raises(ErroAPI) as e:
        motor.aplicar_edicao(comp, {"a": -1}, None, "inserir")
    assert (e.value.status_code, e.value.erro, e.value.mensagem) == (422, "a_negativo", "a não pode ser negativo")
    assert e.value.detalhe == {"regra": "positivo", "resultado": False}
    # nulo também recusa (três valores: nulo não é verdadeiro)
    with pytest.raises(ErroAPI):
        motor.aplicar_edicao(comp, {"rotulo": "x"}, {"a": None}, "atualizar")


def test_regra_desabilitada_nao_dispara_e_eventos_restringem():
    comp = motor.compilar(_dados([
        {"id": "dobro", "tipo": "calculo", "campo": "b", "expressao": "$a * 2", "habilitada": False},
        {"id": "so_insert", "tipo": "calculo", "campo": "rotulo", "expressao": "'novo'", "eventos": ["inserir"]},
    ]))
    saida, rodaram = motor.aplicar_edicao(comp, {"a": 3}, None, "inserir")
    assert saida == {"a": 3, "rotulo": "novo"} and rodaram == ["so_insert"]
    saida, rodaram = motor.aplicar_edicao(comp, {"a": 4}, {"a": 3, "rotulo": "novo"}, "atualizar")
    assert saida == {"a": 4} and rodaram == []


def test_exclusao_em_massa_pula_so_as_marcadas():
    comp = motor.compilar(_dados([
        {"id": "dobro", "tipo": "calculo", "campo": "b", "expressao": "$a * 2", "excluir_em_massa": True},
        {"id": "rotulo", "tipo": "calculo", "campo": "rotulo", "expressao": "'x'"},
    ]))
    assert motor.aplicar_edicao(comp, {"a": 1}, None, "inserir", em_massa=True)[0] == {"a": 1, "rotulo": "x"}
    assert motor.aplicar_edicao(comp, {"a": 1}, None, "inserir")[0] == {"a": 1, "b": 2, "rotulo": "x"}


def test_validacao_so_sob_demanda_e_lista_falhas():
    comp = motor.compilar(_dados([
        {"id": "area", "tipo": "validacao", "expressao": "$area_ha <= 100", "mensagem": "área acima de 100 ha"},
        {"id": "rot", "tipo": "validacao", "expressao": "!EhNulo($rotulo)", "codigo": "sem_rotulo"},
        {"id": "quebrada", "tipo": "validacao", "expressao": "$a / 0 > 1"},
    ]))
    # na edição, regra de validação nunca roda (nem recusa)
    assert motor.aplicar_edicao(comp, {"area_ha": 1000}, None, "inserir")[1] == []
    falhas = motor.avaliar_validacao(comp, {"a": 1, "area_ha": 500, "rotulo": None})
    assert [f["regra"] for f in falhas] == ["area", "rot", "quebrada"]
    assert falhas[0]["mensagem"] == "área acima de 100 ha" and falhas[0]["codigo"] == "regra_validacao"
    assert falhas[1]["codigo"] == "sem_rotulo"
    assert falhas[2]["codigo"] == "regra_erro_avaliacao"  # erro de avaliação é falha registrada, não engolida
    so_quebrada = motor.avaliar_validacao(comp, {"a": 1, "area_ha": 5, "rotulo": "ok"})
    assert [(f["regra"], f["codigo"]) for f in so_quebrada] == [("quebrada", "regra_erro_avaliacao")]


def test_campos_virtuais_na_leitura_e_no_contexto_das_regras():
    comp = motor.compilar(_dados(
        [{"id": "r", "tipo": "restricao", "expressao": "$area_m2 < 1000000", "mensagem": "grande demais"}],
        [{"nome": "area_m2", "expressao": "$area_ha * 10000"}],
    ))
    assert motor.valores_virtuais(comp, {"area_ha": 2.5}) == {"area_m2": 25000}
    assert motor.aplicar_edicao(comp, {"area_ha": 1}, None, "inserir")[0] == {"area_ha": 1}
    with pytest.raises(ErroAPI) as e:
        motor.aplicar_edicao(comp, {"area_ha": 200}, None, "inserir")
    assert e.value.erro == "regra_restricao" and e.value.mensagem == "grande demais"


def test_valores_do_banco_viram_valores_da_linguagem():
    q = datetime.datetime(2026, 9, 8, 12, 0, tzinfo=datetime.UTC)
    assert motor.valor_para_contexto(decimal.Decimal("2.50")) == 2.5
    assert motor.valor_para_contexto(decimal.Decimal("3")) == 3
    assert motor.valor_para_contexto(q) == int(q.timestamp() * 1000)
    assert motor.valor_para_contexto(datetime.date(2026, 9, 8)) == int(q.timestamp() * 1000) - 12 * 3600 * 1000
    comp = motor.compilar(
        _dados([{"id": "d", "tipo": "calculo", "campo": "rotulo", "expressao": "Texto(Ano($quando))"}])
    )
    assert motor.aplicar_edicao(comp, {"rotulo": ""}, {"quando": q}, "atualizar")[0]["rotulo"] == "2026"


# ---- refutação: ciclo, campo inexistente, expressão inválida — tudo na CONFIGURAÇÃO
def test_regra_que_muda_o_proprio_campo_gatilho_e_ciclo():
    e = _erro(
        _dados([{"id": "x", "tipo": "calculo", "campo": "a", "expressao": "$a + 1", "gatilhos": ["a"]}]), "regra_ciclo"
    )
    assert e.detalhe["ciclo"] == ["x"]


def test_ciclo_entre_regras_encadeadas_e_detectado_com_o_caminho():
    e = _erro(_dados([
        {"id": "x", "tipo": "calculo", "campo": "a", "expressao": "$b + 1"},
        {"id": "y", "tipo": "calculo", "campo": "b", "expressao": "$rotulo", "gatilhos": ["rotulo"]},
        {"id": "z", "tipo": "calculo", "campo": "rotulo", "expressao": "Texto($a)", "gatilhos": ["a"]},
    ]), "regra_ciclo")
    assert e.detalhe["ciclo"][0] == e.detalhe["ciclo"][-1] and len(e.detalhe["ciclo"]) == 4
    # cadeia sem volta é aceita
    comp = motor.compilar(_dados([
        {"id": "x", "tipo": "calculo", "campo": "b", "expressao": "$a + 1"},
        {"id": "y", "tipo": "calculo", "campo": "rotulo", "expressao": "Texto($b)", "gatilhos": ["b"]},
    ]))
    assert [r.id for r in comp.regras] == ["x", "y"]


def test_campo_inexistente_expressao_invalida_e_alvo_de_sistema():
    _erro(_dados([{"id": "x", "tipo": "restricao", "expressao": "$nao_existe > 1"}]), "regra_campo_inexistente")
    _erro(_dados([{"id": "x", "tipo": "calculo", "campo": "nao_existe", "expressao": "1"}]), "regra_campo_inexistente")
    _erro(_dados([{"id": "x", "tipo": "calculo", "campo": "fid", "expressao": "1"}]), "regra_campo_inexistente")
    _erro(_dados([{"id": "x", "tipo": "restricao", "expressao": "$a >"}]), "regra_expressao_invalida")
    repetido = [{"id": "x", "tipo": "restricao", "expressao": "$a > 1"},
                {"id": "x", "tipo": "restricao", "expressao": "1 == 1"}]
    _erro(_dados(repetido), "regra_invalida")
    _erro(_dados([{"id": "x", "tipo": "restricao", "campo": "a", "expressao": "1 == 1"}]), "regra_invalida")
    virtuais_encadeados = [{"nome": "v1", "expressao": "$v2 + 1"}, {"nome": "v2", "expressao": "1"}]
    _erro(_dados([], virtuais_encadeados), "regra_campo_inexistente")
    _erro(_dados([], [{"nome": "a", "expressao": "1"}]), "regra_invalida")
    _erro(_dados([{"id": f"r{i}", "tipo": "restricao", "expressao": "1 == 1"} for i in range(101)]), "regra_invalida")


def test_compilacao_e_cacheada_pelo_conteudo():
    d = _dados([{"id": "x", "tipo": "calculo", "campo": "b", "expressao": "$a * 2"}])
    assert motor.compilar(d) is motor.compilar({**d, "campos": list(d["campos"])})
    outro = _dados([{"id": "x", "tipo": "calculo", "campo": "b", "expressao": "$a * 3"}])
    assert motor.compilar(d) is not motor.compilar(outro)
