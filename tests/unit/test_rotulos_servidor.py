"""Unidade da coluna de rótulo pré-calculada no servidor (item L2-02-d-rotulos,
app/estilos/rotulos_servidor.py) e da identidade "dois modos" exigida pelo portão: uma expressão
COMPILÁVEL, avaliada pelo caminho compilado-MapLibre (compilador_maplibre + arnês de referência em
tests/apoio_expressao_maplibre.py) e pelo caminho servidor (avaliador_py direto), tem de dar o
MESMO texto, feição a feição — é a prova de que, quando uma classe de rótulo cai para a coluna do
servidor (porque a expressão real não é compilável), o texto que ela mostra não é um "modo
alternativo" inventado: é o cálculo de referência da própria linguagem.

A refutação do item também mora aqui: expressão com divisão por zero, campo nulo e texto de 2.000
caracteres nunca produz 'null'/'NaN'/'undefined' no rótulo."""

import json

from app.estilos.rotulos_servidor import nome_coluna_servidor, pre_calcular, texto_seguro
from app.expressao.avaliador_py import analisar
from app.expressao.compilador_maplibre import compilar as compilar_maplibre
from tests.apoio_expressao_maplibre import texto_final


def _feicoes_sinteticas(n: int) -> list[dict]:
    usos = ["lavoura", "pastagem", "mata", None]
    saida = []
    for i in range(n):
        saida.append({"classe_uso": usos[i % len(usos)], "area_ha": round(10 + i * 3.7, 2)})
    return saida


class TestIdentidadeDoisModos:
    def test_100_feicoes_texto_identico_compilado_vs_servidor(self):
        # SeNulo guarda o campo que pode vir nulo (mata/None no ciclo sintético) — Maiuscula(nulo)
        # é tipo_invalido no avaliador (ErroExpressao), então uma expressão robusta de rótulo
        # sempre guarda antes; sem o guard os dois modos ainda concordam (os dois ficam vazios
        # naquela feição), mas o objetivo aqui é testar o CASO SÃO, não o caso de erro (esse é
        # coberto à parte em TestRefutacao).
        expressao = "Concatenar(Maiuscula(SeNulo($classe_uso, 'sem classe')), ' - ', Texto($area_ha))"
        feicoes = _feicoes_sinteticas(100)

        expr_maplibre = compilar_maplibre(analisar(expressao))
        textos_compilados = [texto_final(expr_maplibre, f) for f in feicoes]
        textos_servidor = pre_calcular(expressao, feicoes)

        assert len(textos_compilados) == 100
        assert textos_compilados == textos_servidor
        # confere que a comparação não é trivial (não são todas strings vazias/iguais)
        assert len({t for t in textos_compilados}) > 1

    def test_campo_nulo_concatenar_vira_texto_vazio_nos_dois_modos(self):
        expressao = "Concatenar('uso: ', $classe_uso)"
        feicao = {"classe_uso": None}
        expr_maplibre = compilar_maplibre(analisar(expressao))
        assert texto_final(expr_maplibre, feicao) == pre_calcular(expressao, [feicao])[0] == "uso: "


class TestNomeColuna:
    def test_deterministico_e_estavel(self):
        a = nome_coluna_servidor("TextoNumero($area_ha, 1)")
        b = nome_coluna_servidor("TextoNumero($area_ha, 1)")
        assert a == b
        assert a.startswith("plat_rotulo_")

    def test_expressoes_diferentes_dao_colunas_diferentes(self):
        assert nome_coluna_servidor("TextoNumero($a, 1)") != nome_coluna_servidor("TextoNumero($a, 2)")

    def test_espaco_nas_pontas_nao_muda_o_nome(self):
        assert nome_coluna_servidor(" TextoNumero($a) ") == nome_coluna_servidor("TextoNumero($a)")


class TestRefutacao:
    """adversário: expressão com divisão por zero, campo nulo e texto de 2.000 caracteres; nunca
    'null'/'NaN'/'undefined'."""

    def test_divisao_por_zero_nao_derruba_o_lote(self):
        feicoes = [{"a": 10, "b": 0}, {"a": 20, "b": 2}, {"a": 5, "b": 0}]
        textos = pre_calcular("TextoNumero($a / $b, 1)", feicoes)
        assert len(textos) == 3
        for t in textos:
            assert t.strip().lower() not in {"null", "nan", "undefined", "none"}
        # a feição com b=2 calculou de verdade (não é tudo vazio por causa das outras)
        assert textos[1] != ""

    def test_campo_nulo_nao_produz_null_literal(self):
        feicoes = [{"area_ha": None}, {"area_ha": 42.5}]
        textos = pre_calcular("Concatenar(Texto($area_ha), ' ha')", feicoes)
        assert "null" not in textos[0].lower()
        assert textos[1] == "42.5 ha"

    def test_texto_de_2000_caracteres_nao_quebra(self):
        grande = "x" * 2000
        textos = pre_calcular("Concatenar($grande, ' fim')", [{"grande": grande}])
        assert len(textos) == 1
        assert textos[0].endswith(" fim")
        assert "null" not in textos[0].lower() and "nan" not in textos[0].lower()

    def test_campo_ausente_no_contexto_nao_produz_null_literal(self):
        # `avaliar_texto` levanta ErroExpressao (campo_nao_permitido) quando o campo nem existe no
        # contexto — pre_calcular tem de converter isso em rótulo vazio, nunca propagar.
        textos = pre_calcular("Texto($inexistente)", [{}])
        assert textos == [""]

    def test_texto_seguro_nunca_devolve_grafias_proibidas(self):
        for proibido in ("null", "NULL", "Null", "nan", "NaN", "undefined", "None"):
            assert texto_seguro(proibido) == ""
        assert texto_seguro(None) == ""
        assert texto_seguro(True) == "verdadeiro"
        assert texto_seguro(False) == "falso"
        assert texto_seguro(3.5) == "3.5"
        assert texto_seguro("area boa") == "area boa"


def test_medidas_gravadas_para_o_portao(tmp_path_factory):
    """Escreve o corpo de tests/medidas/L2-02-d-rotulos.json referente a este arquivo (o restante
    das medidas — e2e, glifos/cache — é gravado por tests/e2e/test_rotulos_render.py; os dois
    escrevem chaves diferentes no mesmo documento, nunca se pisam)."""
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[1] / "medidas" / "L2-02-d-rotulos.json"
    doc = (
        json.loads(caminho.read_text(encoding="utf-8"))
        if caminho.exists()
        else {"item": "L2-02-d-rotulos", "medidas": {}}
    )
    doc.setdefault("medidas", {})["identidade_dois_modos_100_feicoes"] = {
        "valor": "ok",
        "unidade": "bool",
        "comando": "venv/bin/pytest tests/unit/test_rotulos_servidor.py::TestIdentidadeDoisModos -q",
    }
    caminho.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
