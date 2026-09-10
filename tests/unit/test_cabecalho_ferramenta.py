"""Cabeçalho declarativo da ferramenta-script (item L2-16-c-script-vira-ferramenta) em unidade:
parse do manifesto YAML da docstring, validação de valores (a cerca que vira 422 antes de
qualquer job) e o formulário gerado. O exemplo `examples/ferramentas/buffer_por_campo.py` é a
referência: é o MESMO arquivo que a suíte de API publica e executa no contêiner."""

from pathlib import Path

import pytest

from app.ferramentas import cabecalho

EXEMPLO = Path(__file__).resolve().parents[2] / "examples" / "ferramentas" / "buffer_por_campo.py"


def _codigo() -> str:
    return EXEMPLO.read_text(encoding="utf-8")


# ------------------------------------------------------------------ parse
def test_parse_do_exemplo():
    cab = cabecalho.parse(_codigo())
    assert cab["nome"] == "buffer_por_campo"
    assert cab["titulo"] == "Buffer por campo"
    assert [p["nome"] for p in cab["parametros"]] == ["entrada", "distancia_m", "srid"]
    assert [p["tipo"] for p in cab["parametros"]] == ["item", "numero", "inteiro"]
    # vocabulário GP da família (paridade Esri, mesma língua do L2-05-a)
    assert [p["tipo_gp"] for p in cab["parametros"]] == [
        "GPFeatureRecordSetLayer", "GPDouble", "GPLong"]
    assert [s["nome"] for s in cab["saidas"]] == ["buffer", "resumo"]


def test_parse_aceita_ferramenta_sem_parametro():
    codigo = ('"""\nnome: sem_parametro\ntitulo: Sem parâmetro\nparametros: []\n'
              'saidas:\n  - nome: fora\n    tipo: texto\n"""\n')
    cab = cabecalho.parse(codigo)
    assert cab["parametros"] == []
    assert cabecalho.validar_valores(cab, {}) == {}


def test_padrao_torna_parametro_opcional():
    cab = cabecalho.parse(_codigo())
    entrada, distancia, srid = cab["parametros"]
    assert entrada["obrigatorio"] is True
    assert distancia["obrigatorio"] is False and distancia["padrao"] == 100
    assert srid["obrigatorio"] is False and srid["padrao"] == 31983


@pytest.mark.parametrize("codigo,trecho", [
    ('"""\nnome: A MAIUSCULA\ntitulo: t\nparametros:\n  - nome: campo\n    tipo: texto\n'
     'saidas:\n  - nome: fora\n    tipo: texto\n"""\n', "nome"),
    ('"""\nnome: ok_nome\nparametros:\n  - nome: campo\n    tipo: texto\n'
     'saidas:\n  - nome: fora\n    tipo: texto\n"""\n', "titulo"),
    ('"""\nnome: ok_nome\ntitulo: t\nparametros: 3\nsaidas:\n  - nome: fora\n    tipo: texto\n"""\n',
     "parametros"),
    ('"""\nnome: ok_nome\ntitulo: t\nparametros:\n  - nome: campo\n    tipo: tabuleiro\n'
     'saidas:\n  - nome: fora\n    tipo: texto\n"""\n', "vocabulário"),
    ('"""\nnome: ok_nome\ntitulo: t\nparametros:\n  - nome: campo\n    tipo: texto\n"""\n', "saidas"),
    ('"""\nnome: ok_nome\ntitulo: t\nparametros:\n  - nome: campo\n    tipo: texto\n'
     'saidas:\n  - nome: fora\n    tipo: texto\n"""\nprint(x\n', "não compila"),
    ('"""\n[1, 2, 3]\n"""\n', "mapeamento"),
    ("x = 1\n", "docstring"),
])
def test_parse_recusa_com_a_mensagem_nomeada(codigo, trecho):
    with pytest.raises(cabecalho.ErroCabecalho) as e:
        cabecalho.parse(codigo)
    assert trecho in str(e.value)


def test_minimo_maximo_somente_para_numero():
    codigo = ('"""\nnome: ok_nome\ntitulo: t\nparametros:\n  - nome: campo\n    tipo: texto\n'
              '    minimo: 0\nsaidas:\n  - nome: fora\n    tipo: texto\n"""\n')
    with pytest.raises(cabecalho.ErroCabecalho) as e:
        cabecalho.parse(codigo)
    assert "minimo/maximo" in str(e.value)


def test_parametro_repetido():
    codigo = ('"""\nnome: ok_nome\ntitulo: t\nparametros:\n  - nome: campo\n    tipo: texto\n'
              '  - nome: campo\n    tipo: inteiro\nsaidas:\n  - nome: fora\n    tipo: texto\n"""\n')
    with pytest.raises(cabecalho.ErroCabecalho) as e:
        cabecalho.parse(codigo)
    assert "repetidos" in str(e.value)


# ------------------------------------------------------------------ validar_valores
UID = "11111111-1111-1111-1111-111111111111"


def test_valores_do_exemplo_com_padroes():
    cab = cabecalho.parse(_codigo())
    valores = cabecalho.validar_valores(cab, {"entrada": UID})
    assert valores == {"entrada": UID, "distancia_m": 100.0, "srid": 31983}


def test_valores_converte_e_aceita_dentro_da_faixa():
    cab = cabecalho.parse(_codigo())
    valores = cabecalho.validar_valores(cab, {"entrada": UID, "distancia_m": 250, "srid": 31984})
    assert valores["distancia_m"] == 250.0 and valores["srid"] == 31984


def test_valores_fora_do_tipo_e_da_faixa():
    cab = cabecalho.parse(_codigo())
    for parametros, trecho in [
        ({"entrada": UID, "distancia_m": "muito"}, "número"),
        ({"entrada": UID, "distancia_m": True}, "número"),
        ({"entrada": UID, "distancia_m": -1}, "mínimo"),
        ({"entrada": UID, "distancia_m": 100001}, "máximo"),
        ({"entrada": UID, "srid": 31983.5}, "inteiro"),
        ({"entrada": UID, "nao_declarado": 1}, "não declarado"),
        ({"entrada": "nao-e-uuid"}, "uuid"),
    ]:
        with pytest.raises(cabecalho.ErroValor) as e:
            cabecalho.validar_valores(cab, parametros)
        assert e.value.campo in parametros, (parametros, str(e.value))
        assert trecho in str(e.value)


def test_entrada_obrigatoria_ausente():
    with pytest.raises(cabecalho.ErroValor) as e:
        cabecalho.validar_valores(cabecalho.parse(_codigo()), {"distancia_m": 10})
    assert e.value.campo == "entrada"


# ------------------------------------------------------------------ formulario
def test_formulario_vem_so_do_cabecalho():
    ficha = cabecalho.formulario(cabecalho.parse(_codigo()))
    assert ficha["nome"] == "buffer_por_campo"
    por_nome = {p["nome"]: p for p in ficha["parametros"]}
    assert por_nome["entrada"]["esquema"]["format"] == "uuid"
    assert por_nome["distancia_m"]["esquema"]["type"] == "number"
    assert por_nome["distancia_m"]["esquema"]["minimum"] == 0
    assert por_nome["distancia_m"]["esquema"]["maximum"] == 100000
    assert por_nome["srid"]["esquema"]["type"] == "integer"
    assert por_nome["entrada"]["obrigatorio"] is True
    assert [s["nome"] for s in ficha["saidas"]] == ["buffer", "resumo"]
    # o corpo do script não vaza no formulário
    assert "shapely" not in str(ficha) and "PARAMETROS" not in str(ficha)
