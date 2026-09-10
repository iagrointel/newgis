"""web/js/mapa/grafico_svg.js (item L2-01-i-graficos-de-camada) rodando no node, sem navegador:
  * os 5 tipos desenham elementos clicáveis com data-chave/data-de/data-ate (é o que liga o clique à seleção);
  * o SVG fica ≤ 40 kB NOS PIORES CASOS que o servidor pode devolver (500 categorias + outros, 200 faixas, 5.000
    pontos de dispersão, 10.000 faixas de data) — portão "SVG próprio ≤ 40 kB" por construção, não por sorte;
  * tabela oculta e CSV saem dos mesmos dados (linhas = série; rodapé com total/nulos; regressão no CSV);
  * ticks de eixo são 1-2-5 e cobrem o domínio; rótulos de data tratam ano 1 a.C. e infinity (refutação)."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULO = ROOT / "web" / "js" / "mapa" / "grafico_svg.js"
PAINEL = ROOT / "web" / "js" / "mapa" / "graficos.js"
TETO_SVG = 40 * 1024


def executar_js(codigo: str, dados=None):
    """`dados` entra pelo stdin (os piores casos passam de 100 kB, acima do limite de argv do kernel)."""
    prog = ("const g = await import('./web/js/mapa/grafico_svg.js');\n"
            "const dados = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));\n" + codigo)
    p = subprocess.run(["node", "--input-type=module", "-e", "import { createRequire } from 'node:module'; "
                        "const require = createRequire(import.meta.url);\n" + prog],
                       cwd=ROOT, text=True, capture_output=True, input=json.dumps(dados))
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _svg(dados: dict) -> str:
    return executar_js("console.log(JSON.stringify(g.paraTexto(g.desenhar(dados))));", dados)


def _barras(n, outros=None, estatistica="count"):
    return {"tipo": "barras", "campo": "categoria", "campo_y": None if estatistica == "count" else "valor",
            "estatistica": estatistica,
            "series": [{"chave": f"categoria {i}", "n": 600 - i, "valor": 600 - i} for i in range(n)],
            "outros": outros, "total": 5000, "nulos": 0, "truncado": outros is not None}


def test_modulos_cabem_no_teto():
    assert MODULO.stat().st_size <= TETO_SVG, MODULO.stat().st_size
    assert PAINEL.stat().st_size <= TETO_SVG, PAINEL.stat().st_size


def test_barras_com_outros_e_nulo_tem_um_rect_por_barra_com_data_chave():
    dados = _barras(6, outros={"categorias": 4994, "n": 3000, "valor": 3000})
    dados["series"].append({"chave": None, "n": 7, "valor": 7})
    svg = _svg(dados)
    assert svg.count('class="barra"') == 8  # 6 categorias + nulo + outros
    assert 'data-chave="categoria 0"' in svg and 'data-nulo="1"' in svg and 'data-outros="1"' in svg
    assert "outros (4.994)" in svg and "sem valor" in svg
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220"')


@pytest.mark.parametrize("nome, dados", [
    ("barras_500_mais_outros", _barras(500, outros={"categorias": 4500, "n": 3000, "valor": 3000}, estatistica="sum")),
    ("pizza_500", {**_barras(500), "tipo": "pizza"}),
    ("histograma_200", {"tipo": "histograma", "campo": "v", "bordas": [], "nulos": 3, "total": 100,
                        "series": [{"chave": i + 1, "de": i * 0.37, "ate": (i + 1) * 0.37, "n": i % 7, "valor": i % 7}
                                   for i in range(200)]}),
    ("dispersao_5000", {"tipo": "dispersao", "campo": "x", "campo_y": "y",
                        "series": [{"x": i / 50, "y": 3 * i / 50 + 7} for i in range(5000)],
                        "regressao": {"a": 3, "b": 7, "r2": 1, "n": 1_000_000}, "amostra": True,
                        "x_min": 0, "x_max": 100, "y_min": 7, "y_max": 307}),
    ("linha_10000", {"tipo": "linha", "campo": "q", "estatistica": "count", "granularidade": "dia", "nulos": 1,
                     "total": 10,
                     "series": [{"chave": f"{2000 + i // 366:04d}-01-01T03:00:00+00:00", "n": i % 50, "valor": i % 50}
                                for i in range(10_000)]}),
])
def test_svg_fica_abaixo_de_40_kb_no_pior_caso(nome, dados):
    svg = _svg(dados)
    assert len(svg.encode("utf-8")) <= TETO_SVG, (nome, len(svg))
    if nome == "pizza_500":
        assert svg.count('class="fatia barra') == 51  # 50 fatias + outros (corte no cliente só para o desenho)
    if nome == "barras_500_mais_outros":
        assert svg.count('class="barra"') == 101 and 'data-outros="1"' in svg and "outros (4.9" in svg
    if nome == "dispersao_5000":
        assert 'data-pontos="1250"' in svg or 'data-pontos="1500"' in svg
        assert 'class="regressao"' in svg and 'data-a="3"' in svg and "r² = 1.0000" in svg
    if nome == "linha_10000":
        assert "de 10.000 faixas desenhadas" in svg


def test_histograma_marca_a_ultima_faixa_como_fechada():
    dados = {"tipo": "histograma", "campo": "v", "bordas": [], "nulos": 0, "total": 50,
             "series": [{"chave": i + 1, "de": i * 10, "ate": (i + 1) * 10, "n": 5, "valor": 5} for i in range(10)]}
    svg = _svg(dados)
    assert svg.count('class="barra"') == 10 and svg.count('data-ultima="1"') == 1
    assert 'data-de="90" data-ate="100" data-ultima="1"' in svg


def test_linha_por_mes_com_datas_fora_de_faixa_e_nulos():
    dados = {"tipo": "linha", "campo": "quando", "estatistica": "count", "granularidade": "mes",
             "series": [{"chave": "-infinity", "n": 1, "valor": 1},
                        {"chave": "0001-12-01 03:06:28+00 BC", "n": 1, "valor": 1},
                        {"chave": "2026-07-01 03:00:00+00", "n": 3, "valor": 3},
                        {"chave": "2026-08-01 03:00:00+00", "n": 2, "valor": 2},
                        {"chave": "infinity", "n": 1, "valor": 1}, {"chave": None, "n": 4, "valor": 4}],
             "nulos": 4, "total": 12}
    svg = _svg(dados)
    assert svg.count('class="barra ponto') == 5  # a faixa nula não vira ponto
    assert "12/0001 a.C." in svg and "+∞" in svg and "−∞" in svg and "4 sem data" in svg
    tb = executar_js("console.log(JSON.stringify(g.tabela(dados)));", dados)
    assert len(tb["linhas"]) == 6 and tb["linhas"][2][0] == "07/2026" and tb["rodape"] == [["total", 12], ["nulos", 4]]


def test_tabela_e_csv_saem_dos_mesmos_dados():
    dados = _barras(3, outros={"categorias": 2, "n": 10, "valor": 12.5}, estatistica="avg")
    dados["series"][1]["valor"] = None
    saida = executar_js("console.log(JSON.stringify({t: g.tabela(dados), c: g.csv(dados)}));", dados)
    assert saida["t"]["cabecalho"] == ["categoria", "n", "avg_valor"]
    assert saida["t"]["linhas"] == [["categoria 0", 600, 600], ["categoria 1", 599, None], ["categoria 2", 598, 598],
                                    ["outros (2)", 10, 12.5]]
    linhas = saida["c"].lstrip("﻿").split("\r\n")
    assert linhas[0] == "categoria;n;avg_valor" and linhas[2] == "categoria 1;599;"
    assert linhas[4] == "outros (2);10;12,5"
    assert linhas[5] == "total;5000" and linhas[6] == "nulos;0"
    disp = {"tipo": "dispersao", "campo": "x", "campo_y": "y", "series": [{"x": 1, "y": 2.5}],
            "regressao": {"a": 1.5, "b": 1, "r2": 0.9, "n": 1}}
    c = executar_js("console.log(JSON.stringify(g.csv(dados)));", disp).lstrip("﻿").split("\r\n")
    assert c[0] == "x;y" and c[1] == "1;2,5" and c[2] == "a;1,5" and c[4] == "r2;0,9"


@pytest.mark.parametrize("minimo, maximo, esperado", [
    (0, 87, [0, 20, 40, 60, 80]), (-3, 3, [-3, -2, -1, 0, 1, 2, 3]), (0.001, 0.0093, [0.002, 0.004, 0.006, 0.008]),
    (0, 1_000_000, [0, 200000, 400000, 600000, 800000, 1000000]), (12.5, 12.5, [12.5]),
])
def test_ticks_1_2_5_cobrem_o_dominio(minimo, maximo, esperado):
    assert executar_js("console.log(JSON.stringify(g.ticks(dados[0], dados[1])));", [minimo, maximo]) == esperado


def test_vazio_desenha_mensagem_e_nao_quebra():
    casos = ({"tipo": "barras", "campo": "c", "estatistica": "count", "series": [], "outros": None, "total": 0,
              "nulos": 0},
             {"tipo": "histograma", "campo": "v", "series": [], "bordas": [], "nulos": 9, "total": 9},
             {"tipo": "dispersao", "campo": "x", "campo_y": "y", "series": [], "regressao": None},
             {"tipo": "linha", "campo": "q", "estatistica": "count", "series": [{"chave": None, "n": 3, "valor": 3}],
              "nulos": 3, "total": 3})
    for dados in casos:
        svg = _svg(dados)
        assert "sem valores para desenhar" in svg and 'class="barra' not in svg


def test_texto_hostil_em_chave_e_escapado():
    dados = _barras(1)
    dados["series"][0]["chave"] = "<script>alert(1)</script>\"'&"
    svg = _svg(dados)
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    assert 'data-chave="&lt;script&gt;alert(1)&lt;/script&gt;&quot;\'&amp;"' in svg
