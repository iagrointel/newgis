"""Critérios sobre a própria feição (item L3-06-criterios-de-feicao), cláusula por cláusula do portão.

O dado é ABERTO e está no repositório: `tests/dados/l3_06_feicoes.geojson` (1.000 pontos, centróide de
edificação do OpenStreetMap no recorte de Guarulhos, ODbL 1.0, com o atributo numérico `area_m2` medido em
EPSG:31983) e `tests/dados/l3_06_camada_pontos.geojson` (212 lugares do mesmo recorte). Gerador e proveniência
em `tests/dados/gerar_l3_06.py` e `web/dados/basemap/PROVENIENCIA.md`.

A conferência da contagem em raio contra `ST_DWithin` está em `tests/api/test_amc_criterios_feicao_api.py`,
que é onde há banco.
"""

import csv
import io
import json
import math
from pathlib import Path

import numpy as np
import pytest

from app import limites
from app.amc import criterios_feicao as cf

DADOS = Path(__file__).resolve().parents[1] / "dados"
SRID = 31983  # SIRGAS 2000 / UTM 23S — zona do recorte


def _carregar(nome: str) -> list[dict]:
    return json.loads((DADOS / nome).read_text(encoding="utf-8"))["features"]


@pytest.fixture(scope="module")
def feicoes() -> list[dict]:
    f = _carregar("l3_06_feicoes.geojson")
    assert len(f) == 1_000, "o portão fala em 1.000 pontos de dado aberto"
    return f


@pytest.fixture(scope="module")
def pontos() -> list[dict]:
    return _carregar("l3_06_camada_pontos.geojson")


def criterios_quatro() -> list[dict]:
    """Os quatro critérios do portão: atributo da própria feição, contagem em raio, distância ao mais
    próximo e um 'ideal' sobre o mesmo atributo."""
    return [
        {"id": "area", "tipo": "atributo", "campo": "area_m2", "influencia": "positiva", "peso": 3,
         "minimo": 0, "maximo": 1000},
        {"id": "lugares_1km", "tipo": "contagem_raio", "camada": "lugares", "raio_m": 1000,
         "influencia": "positiva", "peso": 2},
        {"id": "dist_lugar", "tipo": "distancia_mais_proxima", "camada": "lugares", "influencia": "inversa",
         "peso": 2},
        {"id": "area_ideal", "tipo": "atributo", "campo": "area_m2", "influencia": "ideal", "alvo": 200,
         "alcance": 200, "peso": 1},
    ]


@pytest.fixture(scope="module")
def avaliacao(feicoes, pontos):
    return cf.avaliar(feicoes, criterios_quatro(), SRID, {"lugares": pontos})


# ------------------------------------------------------- cláusula 1: 1.000 pontos, 4 critérios, ranqueia
def test_mil_pontos_quatro_criterios_roda_e_ranqueia(avaliacao):
    d = avaliacao.como_dicionario()
    assert d["n_feicoes"] == 1_000
    assert len(d["criterios"]) == 4
    posicoes = sorted(l["posicao"] for l in d["linhas"] if l["posicao"] is not None)
    assert posicoes == list(range(1, len(posicoes) + 1)), "o ranque tem de ser 1..N, sem buraco e sem repetição"
    assert len(posicoes) == d["n_incluidas"]
    notas = [l["nota"] for l in sorted(d["linhas"], key=lambda x: x["posicao"] or 10**9)[:len(posicoes)]]
    assert notas == sorted(notas, reverse=True), "a posição 1 é a maior nota"
    assert all(0.0 <= n <= 100.0 for n in notas)


def test_nota_confere_com_a_soma_ponderada_recalculada_a_mao(avaliacao):
    """Recomputação independente: Σ w·f / Σ w sobre os critérios COM dado, feita aqui do zero."""
    pesos = [c["peso"] for c in avaliacao.fichas]
    for i in range(0, 1_000, 37):
        fav = avaliacao.favorabilidades[i]
        tem = np.isfinite(fav)
        esperado = float((fav[tem] * np.array(pesos)[tem]).sum() / np.array(pesos)[tem].sum())
        assert avaliacao.notas[i] == pytest.approx(esperado, abs=1e-9)


# ------------------------------------------------------- cláusula 3: 'ideal' dá 100 no alvo e 0 nos extremos
def test_ideal_da_cem_no_alvo_e_zero_nos_extremos():
    ficha = cf.validar_criterio({"id": "x", "tipo": "atributo", "campo": "v", "influencia": "ideal",
                                 "alvo": 200.0, "minimo": 0.0, "maximo": 400.0})
    escala = cf.transformacao_da_influencia(ficha, [0.0, 200.0, 400.0])
    from app.amc import transformacoes as tr
    notas = tr.transformar([0.0, 100.0, 200.0, 300.0, 400.0], escala["transformacao"])
    assert notas[2] == pytest.approx(100.0)
    assert notas[0] == pytest.approx(0.0)
    assert notas[4] == pytest.approx(0.0)
    assert notas[1] == pytest.approx(50.0), "a queda é linear e simétrica"
    assert notas[1] == pytest.approx(notas[3]), "simétrica: mesma distância do alvo, mesma nota"


def test_ideal_fora_do_dominio_nao_volta_a_subir():
    ficha = cf.validar_criterio({"id": "x", "tipo": "atributo", "campo": "v", "influencia": "ideal",
                                 "alvo": 200.0, "alcance": 200.0})
    escala = cf.transformacao_da_influencia(ficha, [0.0])
    from app.amc import transformacoes as tr
    assert list(tr.transformar([-10_000.0, 10_000.0], escala["transformacao"])) == [0.0, 0.0]


def test_ideal_com_alvo_fora_do_meio_declara_o_alcance_adotado():
    """Alvo em 100 num domínio 0-400: o alcance é o do lado mais longo (300). O extremo mais distante zera; o
    mais próximo não zera, e a ficha diz que o alcance foi derivado."""
    ficha = cf.validar_criterio({"id": "x", "tipo": "atributo", "campo": "v", "influencia": "ideal",
                                 "alvo": 100.0, "minimo": 0.0, "maximo": 400.0})
    escala = cf.transformacao_da_influencia(ficha, [0.0, 400.0])
    assert "alcance" in escala["limites_derivados"]
    from app.amc import transformacoes as tr
    n0, n400 = tr.transformar([0.0, 400.0], escala["transformacao"])
    assert n400 == pytest.approx(0.0)
    assert n0 > 0.0


def test_influencia_positiva_e_inversa_sao_espelho():
    from app.amc import transformacoes as tr
    base = {"tipo": "atributo", "campo": "v", "minimo": 0.0, "maximo": 10.0}
    p = cf.transformacao_da_influencia(cf.validar_criterio({**base, "id": "p", "influencia": "positiva"}), [0, 10])
    n = cf.transformacao_da_influencia(cf.validar_criterio({**base, "id": "n", "influencia": "inversa"}), [0, 10])
    vp = tr.transformar([0.0, 2.5, 5.0, 10.0], p["transformacao"])
    vn = tr.transformar([0.0, 2.5, 5.0, 10.0], n["transformacao"])
    assert list(vp) == pytest.approx([0.0, 25.0, 50.0, 100.0])
    assert list(vn) == pytest.approx([100.0, 75.0, 50.0, 0.0])


# ------------------------------------------------------- cláusula 4: histograma e matriz de correlação
def test_histograma_por_criterio_conta_tudo(avaliacao):
    d = avaliacao.como_dicionario()
    assert [h["criterio"] for h in d["histogramas"]] == ["area", "lugares_1km", "dist_lugar", "area_ideal"]
    for h in d["histogramas"]:
        assert h["n"] + h["n_sem_dado"] == 1_000
        if h["n"]:
            assert sum(h["contagens"]) == h["n"], "toda feição com dado cai em alguma barra"
            assert len(h["bordas"]) == len(h["contagens"]) + 1


def test_matriz_de_correlacao_entre_criterios(avaliacao):
    c = avaliacao.como_dicionario()["correlacao"]
    assert c["criterios"] == ["area", "lugares_1km", "dist_lugar", "area_ideal"]
    assert len(c["matriz"]) == 4 and all(len(linha) == 4 for linha in c["matriz"])
    for i in range(4):
        assert c["matriz"][i][i] == pytest.approx(1.0), "a diagonal é 1"
        for j in range(4):
            assert c["matriz"][i][j] == c["matriz"][j][i], "a matriz é simétrica"
            assert -1.0 <= c["matriz"][i][j] <= 1.0


def test_correlacao_confere_com_numpy_par_a_par(avaliacao):
    """Recomputação independente do par (area, dist_lugar) com np.corrcoef sobre as linhas completas."""
    c = avaliacao.como_dicionario()["correlacao"]
    a = avaliacao.favorabilidades[:, 0]
    b = avaliacao.favorabilidades[:, 2]
    comum = np.isfinite(a) & np.isfinite(b)
    esperado = float(np.corrcoef(a[comum], b[comum])[0, 1])
    assert c["matriz"][0][2] == pytest.approx(esperado, abs=1e-6)


def test_correlacao_sem_variacao_devolve_nulo_e_nao_zero():
    feicoes = [{"id": f"f{i}", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]},
                "properties": {"a": float(i), "b": 7.0}} for i in range(10)]
    a = cf.avaliar(feicoes, [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"},
                             {"id": "b", "tipo": "atributo", "campo": "b", "influencia": "positiva"}], SRID)
    c = a.como_dicionario()["correlacao"]
    assert c["matriz"][0][1] is None, "critério constante não tem correlação; devolver 0 seria inventar"


# ------------------------------------------------------- cláusula 5: export CSV
def test_csv_tem_uma_linha_por_feicao_na_ordem_do_ranque(avaliacao):
    linhas = list(csv.reader(io.StringIO(avaliacao.csv())))
    assert len(linhas) == 1_001
    cabecalho = linhas[0]
    assert cabecalho[:5] == ["id", "estado", "motivo_filtro", "posicao", "nota"]
    for c in ("area", "lugares_1km", "dist_lugar", "area_ideal"):
        assert f"{c}_valor" in cabecalho and f"{c}_favorabilidade" in cabecalho
    primeiras = [l[3] for l in linhas[1:6]]
    assert primeiras == ["1", "2", "3", "4", "5"]


def test_csv_traz_a_feicao_filtrada_no_fim_com_o_motivo(feicoes, pontos):
    criterios = criterios_quatro()
    criterios[0]["faixa_inclusao"] = {"minimo": 100.0}
    a = cf.avaliar(feicoes, criterios, SRID, {"lugares": pontos})
    # o motivo do filtro tem vírgula: a leitura é com o módulo csv, que é a prova de que a citação está certa
    linhas = list(csv.reader(io.StringIO(a.csv())))[1:]
    estados = [l[1] for l in linhas]
    assert estados.count("filtrada") > 0
    assert estados[-1] == "filtrada", "quem não tem posição sai no fim"
    assert linhas[-1][3] == "" and "fora da faixa de inclusão" in linhas[-1][2]


# ------------------------------------------------------- filtro de inclusão não é veto
def test_filtro_de_inclusao_tira_do_ranque_sem_zerar_a_nota_de_ninguem(feicoes, pontos):
    criterios = criterios_quatro()
    criterios[0]["faixa_inclusao"] = {"minimo": 50.0, "maximo": 500.0}
    a = cf.avaliar(feicoes, criterios, SRID, {"lugares": pontos})
    d = a.como_dicionario()
    assert d["n_filtradas"] > 0 and d["n_incluidas"] + d["n_filtradas"] == 1_000
    for l in d["linhas"]:
        if l["estado"] == cf.ESTADO_FILTRADA:
            assert l["posicao"] is None and l["nota"] is None
            assert l["motivo_filtro"] and "fora da faixa" in l["motivo_filtro"]
            assert not (50.0 <= l["valores"]["area"] <= 500.0)
        else:
            assert 50.0 <= l["valores"]["area"] <= 500.0
            assert l["posicao"] is not None


def test_valor_ausente_nao_e_filtrado_por_faixa():
    feicoes = [{"id": "com", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {"a": 1.0}},
               {"id": "sem", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {}}]
    a = cf.avaliar(feicoes, [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva",
                              "minimo": 10.0, "maximo": 20.0, "faixa_inclusao": {"minimo": 10.0}}], SRID)
    d = a.como_dicionario()
    por_id = {l["id"]: l for l in d["linhas"]}
    assert por_id["com"]["estado"] == cf.ESTADO_FILTRADA, "1 está fora da faixa [10, +inf]"
    assert por_id["sem"]["estado"] == cf.ESTADO_INCLUIDA, "falta de dado não é 'fora da faixa'"
    assert por_id["sem"]["nota"] is None, "sem dado em nenhum critério, a feição fica sem nota (nunca 0)"


# ------------------------------------------------------- refutação exigida pelo item
def test_raio_zero_e_recusado():
    with pytest.raises(cf.ErroCriterio) as e:
        cf.validar_criterio({"id": "x", "tipo": "contagem_raio", "camada": "c", "raio_m": 0,
                             "influencia": "positiva"})
    assert e.value.codigo == "raio_invalido"


def test_raio_de_mil_quilometros_e_recusado():
    with pytest.raises(cf.ErroCriterio) as e:
        cf.validar_criterio({"id": "x", "tipo": "contagem_raio", "camada": "c", "raio_m": 1_000_000,
                             "influencia": "positiva"})
    assert e.value.codigo == "raio_acima_do_teto"
    assert e.value.detalhe["teto_m"] == limites.AMC_CRITERIO_RAIO_M_MAX


def test_feicao_sem_geometria_para_a_extracao_com_o_id_na_mensagem(pontos):
    feicoes = [{"id": "boa", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {}},
               {"id": "torta", "geometry": None, "properties": {}}]
    with pytest.raises(cf.ErroCriterio) as e:
        cf.avaliar(feicoes, [{"id": "d", "tipo": "distancia_mais_proxima", "camada": "lugares",
                              "influencia": "inversa"}], SRID, {"lugares": pontos})
    assert e.value.codigo == "feicao_sem_geometria"
    assert "torta" in e.value.mensagem


def test_atributo_de_texto_nao_vira_numero_em_silencio():
    feicoes = [{"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]},
                "properties": {"a": "muito grande"}}]
    with pytest.raises(cf.ErroCriterio) as e:
        cf.avaliar(feicoes, [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}], SRID)
    assert e.value.codigo == "atributo_nao_numerico"
    assert e.value.detalhe["campo"] == "a"


def test_atributo_booleano_tambem_e_recusado():
    feicoes = [{"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]},
                "properties": {"a": True}}]
    with pytest.raises(cf.ErroCriterio) as e:
        cf.avaliar(feicoes, [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}], SRID)
    assert e.value.codigo == "atributo_nao_numerico"


def test_camada_pedida_e_nao_fornecida_e_erro_nomeado():
    feicoes = [{"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {}}]
    with pytest.raises(cf.ErroCriterio) as e:
        cf.avaliar(feicoes, [{"id": "d", "tipo": "contagem_raio", "camada": "sumida", "raio_m": 10,
                              "influencia": "positiva"}], SRID, {})
    assert e.value.codigo == "camada_nao_fornecida"


def test_teto_de_feicoes_recusa_em_vez_de_cortar():
    feicoes = [{"id": f"f{i}", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {"a": 1.0}}
               for i in range(limites.AMC_CRITERIOS_FEICAO_MAX + 1)]
    with pytest.raises(cf.ErroCriterio) as e:
        cf.avaliar(feicoes, [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}], SRID)
    assert e.value.codigo == "feicoes_demais"


def test_id_de_criterio_repetido_e_recusado():
    with pytest.raises(cf.ErroCriterio) as e:
        cf.validar_criterios([{"id": "a", "tipo": "atributo", "campo": "x", "influencia": "positiva"},
                              {"id": "a", "tipo": "atributo", "campo": "y", "influencia": "positiva"}])
    assert e.value.codigo == "id_repetido"


def test_sem_dado_em_nenhuma_feicao_nao_inventa_escala():
    feicoes = [{"id": "f1", "geometry": {"type": "Point", "coordinates": [-46.5, -23.4]}, "properties": {}}]
    with pytest.raises(cf.ErroCriterio) as e:
        cf.avaliar(feicoes, [{"id": "a", "tipo": "atributo", "campo": "a", "influencia": "positiva"}], SRID)
    assert e.value.codigo == "sem_dado_para_derivar"


def test_nan_nunca_vira_zero(avaliacao):
    assert not np.any(np.isnan(avaliacao.notas) & np.array([e == cf.ESTADO_INCLUIDA
                                                            for e in avaliacao.estado]) & (avaliacao.notas == 0.0))
    for linha in avaliacao.como_dicionario()["linhas"]:
        for valor in linha["favorabilidades"].values():
            assert valor is None or math.isfinite(valor)
