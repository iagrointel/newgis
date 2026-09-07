"""Item L3-17-similaridade (linha L3 motor AMC) — "localização semelhante" / "Find Similar Locations":
dadas 1-N unidades de referência, ranqueia as demais por parecença sobre fatores padronizados (z-score),
com índice de similaridade e escolha de campos. Portão de pronto, cláusula por cláusula:

1. reproduz exemplo numérico de referência (recomputação INDEPENDENTE, sem chamar `app.amc.similaridade`
   para gerar o esperado — só `statistics`/aritmética pura do teste, igual ao padrão de L3-01-c);
2. escolha de campos (o mesmo par de unidades muda de ranking conforme os campos escolhidos);
3. export (CSV e GeoJSON, formato e conteúdo conferidos);
4. teste (esta suíte + a refutação exigida: referência = candidato dá índice 1 e 1º lugar).

Grava `tests/medidas/L3-17-similaridade.json` só com `PLAT_GRAVAR_MEDIDAS=1` (fixture `medida` do conftest
raiz), como todo item da casa."""

import csv
import io
import math
import statistics

import pytest

from app.amc import similaridade as sim

ITEM = "L3-17-similaridade"


def _clausula(medida, nome, valor, unidade, comando):
    """Grava a medida (quando PLAT_GRAVAR_MEDIDAS=1) e devolve o valor, para poder também usá-lo em assert."""
    medida(ITEM)(nome, valor, unidade, comando)
    return valor


# ================================================================ dados do exemplo de referência
# 4 unidades (município fictício), 2 fatores: chuva média anual (mm) e temperatura média (°C). Números
# redondos de propósito, para a recomputação manual no teste não escorregar em ponto flutuante.
UNIDADES = {
    "A": {"chuva": 1200.0, "temp": 22.0},
    "B": {"chuva": 1300.0, "temp": 23.0},
    "C": {"chuva": 800.0, "temp": 30.0},
    "D": {"chuva": 1250.0, "temp": 21.0},
}


def _zscore_independente(unidades: dict, campo: str) -> dict:
    """Z-score populacional (ddof=0) recomputado só com `statistics`, sem tocar `app.amc.similaridade`."""
    valores = [v[campo] for v in unidades.values()]
    media = statistics.fmean(valores)
    desvio = statistics.pstdev(valores)  # população, não amostra — mesma convenção do módulo sob teste
    return {uid: (v[campo] - media) / desvio for uid, v in unidades.items()}


def _cosseno_independente(v1: list[float], v2: list[float]) -> float:
    produto = sum(a * b for a, b in zip(v1, v2, strict=True))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return produto / (n1 * n2)


# ================================================================ cláusula 1 — exemplo numérico de referência
def test_1_reproduz_exemplo_numerico_de_referencia(medida):
    """Padroniza as 4 unidades nos 2 campos, calcula o cosseno de B, C e D contra A (referência única — o
    centroide de uma referência só é o próprio vetor dela) inteiramente por fora do módulo, e confere que
    `app.amc.similaridade.calcular` chega ao mesmo índice, dentro de 1e-9."""
    z_chuva = _zscore_independente(UNIDADES, "chuva")
    z_temp = _zscore_independente(UNIDADES, "temp")
    vetores = {uid: [z_chuva[uid], z_temp[uid]] for uid in UNIDADES}

    esperado_indice = {}
    for uid in UNIDADES:
        cos = _cosseno_independente(vetores[uid], vetores["A"])
        esperado_indice[uid] = (cos + 1.0) / 2.0
    assert esperado_indice["A"] == pytest.approx(1.0, abs=1e-12)  # referência contra si mesma

    resultado = sim.calcular(UNIDADES, referencias=["A"], campos=["chuva", "temp"], metrica="cosseno")
    obtido = {linha["unidade_id"]: linha["indice_similaridade"] for linha in resultado.ranking}
    for uid in UNIDADES:
        assert obtido[uid] == pytest.approx(esperado_indice[uid], abs=1e-9), uid

    # a ordem esperada (calculada fora): quem tem chuva/temp mais parecidos com A vem primeiro
    ordem_esperada = sorted(UNIDADES, key=lambda u: -esperado_indice[u])
    ordem_obtida = [linha["unidade_id"] for linha in resultado.ranking]
    assert ordem_obtida == ordem_esperada

    _clausula(medida, "exemplo_referencia_indice_A", obtido["A"], "índice (0-1)",
              "test_1_reproduz_exemplo_numerico_de_referencia")
    _clausula(medida, "exemplo_referencia_ordem", ",".join(ordem_obtida), "sequência de unidade_id",
              "test_1_reproduz_exemplo_numerico_de_referencia")


def test_1b_estatisticas_devolvidas_batem_com_media_e_desvio_independentes():
    resultado = sim.calcular(UNIDADES, referencias=["A"], campos=["chuva", "temp"])
    assert resultado.estatisticas["chuva"]["media"] == pytest.approx(statistics.fmean(
        [v["chuva"] for v in UNIDADES.values()]))
    assert resultado.estatisticas["chuva"]["desvio"] == pytest.approx(statistics.pstdev(
        [v["chuva"] for v in UNIDADES.values()]))


def test_1c_metrica_euclidiana_tambem_bate_com_recomputacao_independente(medida):
    z_chuva = _zscore_independente(UNIDADES, "chuva")
    z_temp = _zscore_independente(UNIDADES, "temp")
    vetores = {uid: [z_chuva[uid], z_temp[uid]] for uid in UNIDADES}
    ref = vetores["A"]
    esperado = {uid: 1.0 / (1.0 + math.sqrt(sum((a - b) ** 2 for a, b in zip(v, ref, strict=True))))
                for uid, v in vetores.items()}

    resultado = sim.calcular(UNIDADES, referencias=["A"], campos=["chuva", "temp"], metrica="euclidiana")
    obtido = {linha["unidade_id"]: linha["indice_similaridade"] for linha in resultado.ranking}
    for uid in UNIDADES:
        assert obtido[uid] == pytest.approx(esperado[uid], abs=1e-9), uid
    assert obtido["A"] == pytest.approx(1.0, abs=1e-12)
    _clausula(medida, "exemplo_referencia_euclidiana_indice_A", obtido["A"], "índice (0-1)",
              "test_1c_metrica_euclidiana_tambem_bate_com_recomputacao_independente")


def test_1d_centroide_de_duas_referencias_e_a_media_dos_vetores_padronizados(medida):
    """1-N referências: com A e B como referência, o alvo é o centroide (média) dos dois vetores padronizados
    — recomputado aqui à parte."""
    z_chuva = _zscore_independente(UNIDADES, "chuva")
    z_temp = _zscore_independente(UNIDADES, "temp")
    vetores = {uid: [z_chuva[uid], z_temp[uid]] for uid in UNIDADES}
    centroide = [(vetores["A"][i] + vetores["B"][i]) / 2 for i in range(2)]
    esperado_c = _cosseno_independente(vetores["C"], centroide)
    esperado_indice_c = (esperado_c + 1.0) / 2.0

    resultado = sim.calcular(UNIDADES, referencias=["A", "B"], campos=["chuva", "temp"])
    obtido_c = next(linha["indice_similaridade"] for linha in resultado.ranking if linha["unidade_id"] == "C")
    assert obtido_c == pytest.approx(esperado_indice_c, abs=1e-9)
    _clausula(medida, "centroide_duas_referencias_indice_C", obtido_c, "índice (0-1)",
              "test_1d_centroide_de_duas_referencias_e_a_media_dos_vetores_padronizados")


# ================================================================ cláusula 2 — escolha de campos
def test_2_escolha_de_campos_muda_o_ranking(medida):
    """Um par de unidades muda de posição relativa dependendo de que fator entra na comparação — prova de que
    'campos' realmente filtra (não é um parâmetro decorativo). X é muito parecida com A em 'chuva' e muito
    diferente em 'temp'; Y é o oposto — escolhido de propósito para inverter a ordem entre os dois cálculos.
    Métrica euclidiana aqui (com 1 único campo o cosseno degenera para só o sinal, ver docstring do módulo —
    a cláusula de escolha de campos é sobre o FILTRO, não sobre essa particularidade do cosseno)."""
    unidades = {
        "A": {"chuva": 1000.0, "temp": 20.0},
        "X": {"chuva": 1010.0, "temp": 40.0},   # quase igual a A em chuva, longe em temp
        "Y": {"chuva": 1600.0, "temp": 21.0},   # longe de A em chuva, quase igual em temp
    }
    so_chuva = sim.calcular(unidades, referencias=["A"], campos=["chuva"], metrica="euclidiana")
    so_temp = sim.calcular(unidades, referencias=["A"], campos=["temp"], metrica="euclidiana")
    pos_chuva = {linha["unidade_id"]: linha["posicao"] for linha in so_chuva.ranking}
    pos_temp = {linha["unidade_id"]: linha["posicao"] for linha in so_temp.ranking}
    assert so_chuva.campos == ["chuva"] and so_temp.campos == ["temp"]
    assert pos_chuva["X"] < pos_chuva["Y"], "só chuva: X (quase igual a A) tinha de vir antes de Y"
    assert pos_temp["Y"] < pos_temp["X"], "só temp: Y (quase igual a A) tinha de vir antes de X"
    assert pos_chuva != pos_temp, "selecionar campos diferentes tinha de mudar o ranking, e não mudou"

    ambos = sim.calcular(unidades, referencias=["A"], campos=["chuva", "temp"])
    assert sorted(ambos.campos) == ["chuva", "temp"]
    _clausula(medida, "campos_escolhidos_mudam_ranking", pos_chuva != pos_temp, "booleano",
              "test_2_escolha_de_campos_muda_o_ranking")


def test_2b_campo_omitido_usa_todos_os_vistos_na_matriz():
    resultado = sim.calcular(UNIDADES, referencias=["A"])
    assert resultado.campos == ["chuva", "temp"]  # ordem alfabética, determinística


def test_2c_campo_inexistente_em_toda_unidade_e_erro_422():
    with pytest.raises(sim.ErroSimilaridade) as exc:
        sim.calcular(UNIDADES, referencias=["A"], campos=["altitude"])
    assert exc.value.codigo == "fator_sem_dado"


def test_2d_unidade_sem_valor_no_campo_escolhido_sai_do_ranking_e_entra_em_excluidas():
    unidades = dict(UNIDADES, E={"chuva": 1000.0, "temp": None})
    resultado = sim.calcular(unidades, referencias=["A"], campos=["chuva", "temp"])
    ids_ranking = {linha["unidade_id"] for linha in resultado.ranking}
    assert "E" not in ids_ranking
    assert resultado.excluidas == [{"unidade_id": "E", "motivo": "dado_incompleto"}]


def test_2e_desvio_zero_num_campo_nao_quebra_e_zera_o_eixo():
    """Todas as unidades com o mesmo valor de 'chuva': o desvio é zero; a convenção é z=0 nesse eixo, sem
    ZeroDivisionError, e o ranking passa a depender só do outro campo."""
    unidades = {"A": {"chuva": 1000.0, "temp": 20.0}, "B": {"chuva": 1000.0, "temp": 25.0},
                "C": {"chuva": 1000.0, "temp": 30.0}}
    resultado = sim.calcular(unidades, referencias=["A"], campos=["chuva", "temp"])
    assert resultado.estatisticas["chuva"]["desvio"] == 0.0
    # A contra si mesma continua 1,0; B e C só se distinguem pelo campo 'temp'
    por_id = {linha["unidade_id"]: linha["indice_similaridade"] for linha in resultado.ranking}
    assert por_id["A"] == pytest.approx(1.0)


# ================================================================ cláusula 3 — export
def test_3_export_csv_tem_cabecalho_fixo_e_uma_linha_por_unidade_do_ranking(medida):
    resultado = sim.calcular(UNIDADES, referencias=["A"], campos=["chuva", "temp"])
    texto = sim.exportar_csv(resultado)
    linhas = list(csv.reader(io.StringIO(texto)))
    assert linhas[0] == ["posicao", "unidade_id", "indice_similaridade"]
    assert len(linhas) == 1 + len(UNIDADES)  # cabeçalho + 4 unidades (nenhuma excluída neste exemplo)
    primeira = linhas[1]
    assert primeira[0] == "1" and primeira[1] == "A"  # referência = candidato: 1ª linha do CSV
    assert float(primeira[2]) == pytest.approx(1.0, abs=1e-9)
    # excluídas nunca aparecem no CSV (não têm posição nem índice)
    unidades_com_excluida = dict(UNIDADES, E={"chuva": 1000.0, "temp": None})
    resultado2 = sim.calcular(unidades_com_excluida, referencias=["A"], campos=["chuva", "temp"])
    texto2 = sim.exportar_csv(resultado2)
    assert "E" not in texto2
    _clausula(medida, "export_csv_linhas", len(linhas), "linhas (cabeçalho + unidades)",
              "test_3_export_csv_tem_cabecalho_fixo_e_uma_linha_por_unidade_do_ranking")


def test_3b_export_geojson_e_featurecollection_com_uma_feicao_por_unidade_do_ranking(medida):
    resultado = sim.calcular(UNIDADES, referencias=["A"], campos=["chuva", "temp"])
    doc = sim.exportar_geojson(resultado)
    assert doc["type"] == "FeatureCollection"
    assert len(doc["features"]) == len(UNIDADES)
    por_id = {f["properties"]["unidade_id"]: f for f in doc["features"]}
    assert por_id["A"]["properties"]["referencia"] is True
    assert por_id["A"]["properties"]["posicao"] == 1
    assert por_id["A"]["geometry"] is None  # sem geometria informada: null, nunca inventada
    assert por_id["B"]["properties"]["referencia"] is False

    geom_a = {"type": "Point", "coordinates": [-46.5, -23.5]}
    doc2 = sim.exportar_geojson(resultado, geometrias={"A": geom_a})
    por_id2 = {f["properties"]["unidade_id"]: f for f in doc2["features"]}
    assert por_id2["A"]["geometry"] == geom_a
    assert por_id2["B"]["geometry"] is None
    _clausula(medida, "export_geojson_feicoes", len(doc["features"]), "feições",
              "test_3b_export_geojson_e_featurecollection_com_uma_feicao_por_unidade_do_ranking")


# ================================================================ cláusula 4 — teste (validações de entrada)
def test_4_sem_unidades_e_erro():
    with pytest.raises(sim.ErroSimilaridade) as exc:
        sim.calcular({}, referencias=["A"])
    assert exc.value.codigo == "sem_unidades"


def test_4b_sem_referencia_e_erro():
    with pytest.raises(sim.ErroSimilaridade) as exc:
        sim.calcular(UNIDADES, referencias=[])
    assert exc.value.codigo == "sem_referencia"


def test_4c_referencia_fora_da_matriz_e_erro():
    with pytest.raises(sim.ErroSimilaridade) as exc:
        sim.calcular(UNIDADES, referencias=["Z"])
    assert exc.value.codigo == "referencia_desconhecida"


def test_4d_referencia_com_dado_incompleto_e_erro():
    unidades = dict(UNIDADES, A={"chuva": 1200.0, "temp": None})
    with pytest.raises(sim.ErroSimilaridade) as exc:
        sim.calcular(unidades, referencias=["A"], campos=["chuva", "temp"])
    assert exc.value.codigo == "referencia_incompleta"


def test_4e_metrica_invalida_e_erro():
    with pytest.raises(sim.ErroSimilaridade) as exc:
        sim.calcular(UNIDADES, referencias=["A"], metrica="manhattan")
    assert exc.value.codigo == "metrica_invalida"


def test_4f_ranking_desempata_por_unidade_id_para_ser_deterministico():
    unidades = {"A": {"x": 0.0}, "B": {"x": 0.0}, "C": {"x": 0.0}}
    resultado = sim.calcular(unidades, referencias=["A"], campos=["x"])
    assert [linha["unidade_id"] for linha in resultado.ranking] == ["A", "B", "C"]


def test_2f_cosseno_com_1_campo_degenera_para_o_sinal_e_o_desempate_por_distancia_resolve():
    """Achado do próprio autor ao escrever a refutação (documentado no módulo): com 1 único campo, cosseno só
    enxerga sinal — A e D (mesmo lado de B) empatam com B em índice 1,0 quando a referência é B. O desempate
    por distância padronizada garante que B (distância 0 a si mesma) continua em 1º lugar mesmo nesse caso."""
    resultado = sim.calcular(UNIDADES, referencias=["B"], campos=["chuva"], metrica="cosseno")
    por_id = {linha["unidade_id"]: linha for linha in resultado.ranking}
    assert por_id["A"]["indice_similaridade"] == pytest.approx(1.0, abs=1e-9)  # mesmo lado da média que B
    assert por_id["D"]["indice_similaridade"] == pytest.approx(1.0, abs=1e-9)  # idem
    assert por_id["C"]["indice_similaridade"] == pytest.approx(0.0, abs=1e-9)  # lado oposto
    assert por_id["B"]["posicao"] == 1, "a própria referência não pode perder o 1º lugar num empate"


# ================================================================ refutação exigida (adversário)
def test_refutacao_referencia_igual_a_candidato_da_indice_1_e_1o_lugar(medida):
    """Cláusula de refutação do item: quando um candidato É a referência, o índice de similaridade tem de sair
    exatamente 1 e a posição tem de ser 1 — nos dois métodos, com 1 e com 2 campos."""
    for metrica in ("cosseno", "euclidiana"):
        for campos in (["chuva"], ["chuva", "temp"]):
            resultado = sim.calcular(UNIDADES, referencias=["B"], campos=campos, metrica=metrica)
            linha_b = next(linha for linha in resultado.ranking if linha["unidade_id"] == "B")
            assert linha_b["indice_similaridade"] == pytest.approx(1.0, abs=1e-12), (metrica, campos)
            assert linha_b["posicao"] == 1, (metrica, campos)
    _clausula(medida, "refutacao_referencia_igual_candidato", True, "booleano",
              "test_refutacao_referencia_igual_a_candidato_da_indice_1_e_1o_lugar")
