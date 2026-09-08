"""Item L5-01-c-widgets-dado, sem navegador: a tradução CQL2-JSON -> `where` do FeatureServer feita no navegador
(web/js/app/consulta.js) produz SÓ cláusulas que o analisador seguro do servidor (app/consulta/where_ast.py)
aceita — inclusive com aspas e ponto-e-vírgula no valor (vira literal, nunca SQL); predicado espacial vira o
parâmetro `geometry` e é recusado fora de AND; nome de campo inválido é recusado nos dois lados. Agregação,
histograma, CSV (RFC 4180) e modelo de texto em memória; a API assíncrona da vista (página/total/exportar/ids)
em fonte de memória — a mesma que a tabela e o gráfico usam contra a camada no servidor."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.consulta import where_ast

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "app" / "executar_js.mjs"


def _node(comando: str, stdin: dict | None = None) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node ausente")
    r = subprocess.run(["node", str(RUNNER), comando], input=json.dumps(stdin) if stdin else None,
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout)


COLUNAS = {"fid": "fid", "uf": '"uf"', "nome": '"nome"', "n": '"n"', "d": '"d"', "valor": '"valor"'}


def test_where_gerado_no_navegador_e_aceito_pelo_analisador_do_servidor():
    filtros = [
        {"op": "=", "args": [{"property": "uf"}, "SP"]},
        "nome like '%a%' and n between 1 and 3",
        {"op": "in", "args": [{"property": "__id"}, [1, 2, 3]]},
        {"op": "=", "args": [{"property": "nome"}, "O'Reilly; DROP TABLE x --"]},
        {"op": "isNull", "args": [{"property": "d"}]},
        {"op": "not", "args": [{"op": "like", "args": [{"property": "uf"}, "S%"]}]},
        {"op": "or", "args": [{"op": ">=", "args": [{"property": "n"}, 2]}, {"op": "<>", "args": [{"property": "uf"},
            "RJ"]}]},
        {"op": "and", "args": [{"op": ">", "args": [{"property": "valor"}, 2.5]},
                               {"op": "s_intersects", "args": [{"property": "geometria"}, {"type": "Polygon",
                                   "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}]}]},
    ]
    saida = _node("where", {"filtros": filtros})
    assert [s["erro"] for s in saida] == [None] * len(filtros), saida
    assert saida[2]["where"] == "fid IN (1, 2, 3)"                      # __id vira o campo de id do servidor
    assert saida[3]["where"] == "nome = 'O''Reilly; DROP TABLE x --'"    # aspas dobradas: literal, não SQL
    assert saida[7]["where"] == "valor > 2.5" and saida[7]["geometria"] == "s_intersects"
    for s in saida:
        c = where_ast.compilar_where(s["where"], COLUNAS)   # o servidor aceita cada cláusula gerada
        assert c.sql
        # o texto perigoso chega ao SQL só como PARÂMETRO ligado, nunca embutido
        if "DROP" in s["where"]:
            assert "DROP" not in c.sql and any("DROP" in str(p) for p in c.params)


def test_where_recusa_espacial_fora_de_and_e_campo_invalido():
    saida = _node("where", {"filtros": [
        {"op": "or", "args": [{"op": "=", "args": [{"property": "a"}, 1]}, {"op": "s_intersects",
            "args": [{"property": "geometria"}, {"type": "Point", "coordinates": [0, 0]}]}]},
        {"op": "=", "args": [{"property": "x; drop"}, 1]},
        {"op": "=", "args": [{"property": "a"}, {"property": "b"}]},
    ]})
    assert [s["erro"] for s in saida] == ["espacial_fora_de_and", "campo_invalido", "valor_invalido"]
    with pytest.raises(where_ast.ErroWhere):
        where_ast.compilar_where("x; drop = 1", COLUNAS)


FEICOES = [
    {"type": "Feature", "id": 1, "properties": {"n": 1, "uf": "SP", "v": 10.5}},
    {"type": "Feature", "id": 2, "properties": {"n": 2, "uf": "RJ", "v": 2}},
    {"type": "Feature", "id": 3, "properties": {"n": 3, "uf": "SP", "v": 'x, "y"'}},
    {"type": "Feature", "id": 4, "properties": {"n": 4, "uf": "MG", "v": 4}},
]


def test_agregacao_histograma_csv_e_modelo_em_memoria():
    r = _node("agregar", {"feicoes": FEICOES, "opcoes": {"campo": "uf", "agregacao": "soma", "campo_valor": "v",
        "faixas": 2,
                                                        "modelo": "{uf} {n} {= n * 2 } {nada}|"}})
    grupos = {g["valor"]: g for g in r["grupos"]}
    assert grupos["SP"]["n"] == 2 and grupos["SP"]["soma"] == 10.5 and grupos["SP"]["ids"] == [1, 3]  # texto não soma
    assert [g["valor"] for g in r["grupos"]] == ["SP", "MG", "RJ"]  # ordenado pela medida (soma) desc
    assert [h["n"] for h in r["histograma"]] == [2,
        1] and r["histograma"][0]["de"] == 2 and r["histograma"][-1]["ate"] == 10.5
    linhas = r["csv"].lstrip("﻿").split("\r\n")
    assert linhas[0] == "n,uf,v" and linhas[3] == '3,SP,"x, ""y"""' and r["csv"].startswith("﻿")
    assert r["modelo"] == "SP 1  |"   # {= expressão } só com avaliador (aqui sem); campo inexistente vira vazio


def test_vista_em_memoria_pagina_total_exporta_e_ids_do_filtro():
    r = _node("vista_memoria", {"feicoes": FEICOES, "filtro": {"op": "<>", "args": [{"property": "uf"}, "MG"]},
                                "ordenacao": [{"campo": "n", "direcao": "desc"}], "limite": 2})
    assert r["total"] == 3 and r["p1"] == [3, 2] and r["p2"] == [1]
    assert r["linhasCsv"] == 3 and r["feicoesGeoJson"] == 3          # exportação respeita o filtro ativo
    assert r["distintos"] == ["MG", "RJ", "SP"]                       # valores únicos ignoram o filtro dinâmico
    assert r["ids"] == [3]                                            # n > 2 dentro do filtro (uf <> MG)
