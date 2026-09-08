"""Fluxo de potência do alimentador, sem banco (item L4-07-fluxo-de-potencia).

Cláusulas do portão provadas aqui:

* ALIMENTADOR SINTÉTICO DE RESPOSTA ANALÍTICA CONHECIDA: cinco barras em série, uma carga só na ponta.
  Com carga só no fim, a MESMA corrente atravessa os cinco trechos, e a queda de tensão em cada um é
  exatamente `I x Z` (fasorial). `test_queda_de_tensao_em_linha_unica_e_i_vezes_z` confere a barra a barra,
  contra a impedância que o próprio motor declara para o trecho (R1, X1 e comprimento), sem passar por
  nada do módulo — é a conta fechada que o adversário do item repete;
* CONVERGÊNCIA registrada e mostrada: `test_convergencia_vem_com_o_resultado` e
  `test_alimentador_que_nao_converge_fica_marcado_e_fora_da_agregacao`;
* PARÂMETROS declarados na ficha: `test_parametros_saem_na_ficha_do_resultado` e
  `test_fator_de_carga_e_modelo_de_carga_mudam_o_resultado`;
* PERDA DE FERRO simulada contra PER_FER x horas do ano: `test_perda_de_ferro_simulada_bate_com_a_declarada`.

Refutação (papel adversário), provada aqui:

* `test_o_mesmo_alimentador_duas_vezes_da_o_mesmo_resultado` — determinismo;
* `test_alimentador_que_nao_converge_fica_marcado_e_fora_da_agregacao` — quem não convergiu sai da
  agregação e é NOMEADO na lista dos excluídos;
* `test_parametro_desconhecido_e_recusado`, `test_zip_sem_coeficientes_e_recusado` e
  `test_modo_hora_sem_ponto_e_recusado` — parâmetro que não fecha é recusado, nunca ignorado em silêncio.

(O transformador sem POT_NOM, a outra refutação exigida, falha ANTES deste módulo, na montagem do modelo:
está em `tests/api/test_rede_opendss.py::test_trafo_sem_potencia_falha_alto` e é conferido de novo pela
API em `tests/api/test_rede_fluxo.py`.)
"""

import cmath
import math

import pytest

from app.rede_utilidades import fluxo_potencia as fp
from app.rede_utilidades import opendss

pytest.importorskip("opendssdirect",
                    reason="opendssdirect não está nesta máquina: o motor de fluxo não foi medido")

KV = 13.8
ANO = 2026  # ano não bissexto: as horas do ano são exatamente 8760
KM = [1.0, 2.0, 1.5, 3.0, 0.5]


def _trecho(nome, a, b, km):
    return {"nome": nome, "barra1": a, "barra2": b, "fases": [1, 2, 3], "comprimento_km": km,
            "condutor": None, "feicao_id": None}


def _modelo(linhas, barras, cargas=(), trafos=(), curvas=None):
    return {"nome": "ZT-FLUXO", "ano": ANO, "subredes": ["s"], "barra_fonte": "b1", "kv_fonte": KV,
            "pu_fonte": 1.0, "codigo_tensao_nominal": "49", "barras": dict(barras),
            "linhas": list(linhas), "trafos": list(trafos), "cargas": list(cargas),
            "curvas": dict(curvas or {}), "chaves": [], "avisos": {}, "ignorados": {},
            "conferencia": {}}


def _curva_plana(nome="cplana"):
    """Curva de 864 pontos com a mesma potência em todo ponto: assim a resposta analítica não depende de
    qual ponto o motor escolheu como crítico."""
    return {nome: [1.0] * opendss.PONTOS_DA_CURVA}


def _alimentador_em_serie(kw=200.0, vminpu=0.92):
    """Cinco trechos em série a partir da fonte, com UMA carga trifásica na ponta. É a forma em que a
    resposta fechada existe: com carga só no fim, a corrente é a mesma nos cinco trechos."""
    barras = {f"b{i}": KV for i in range(1, 7)}
    linhas = [_trecho(f"t{i}", f"b{i}", f"b{i + 1}", KM[i - 1]) for i in range(1, 6)]
    cargas = [{"nome": "u0", "barra": "b6", "fases_nos": [1, 2, 3], "fases": 3, "ligacao": "wye",
               "kv": KV, "kw": kw, "fator_de_potencia": 0.92, "modelo": 1,
               "vminpu": vminpu, "vmaxpu": 1.25, "curva": "cplana", "energia_mensal_medida": True}]
    return _modelo(linhas, barras, cargas, curvas=_curva_plana())


def _resolver(modelo, **parametros):
    return fp.resolver(modelo, fp.validar_parametros({"modo": "hora", "ponto": 0, "ano": ANO,
                                                      **parametros}))


# --- cláusula: alimentador sintético de resposta analítica (queda de tensão = I x Z) --------------------

def test_queda_de_tensao_em_linha_unica_e_i_vezes_z():
    """A conta fechada, feita fora do módulo: para cada trecho, `V_a - V_b = Z x I`, com Z lido do motor
    (R1 + jX1, ohm por quilômetro, vezes o comprimento) e I a corrente fasorial que atravessa o trecho.

    Cinco barras conferidas — as mesmas cinco que a refutação do item pede."""
    import opendssdirect as dss

    modelo = _alimentador_em_serie()
    saida = _resolver(modelo)
    assert saida["convergencia"]["convergiu"] is True, saida["avisos"]

    # o motor ficou no ponto resolvido: lê dele a tensão e a corrente COMPLEXAS, e a impedância declarada
    tensoes = {}
    for barra in [f"b{i}" for i in range(1, 7)]:
        dss.Circuit.SetActiveBus(barra)
        crus = dss.Bus.Voltages()
        tensoes[barra] = [complex(crus[2 * f], crus[2 * f + 1]) for f in range(3)]

    conferidas = 0
    for i in range(1, 6):
        nome = f"t{i}"
        dss.Lines.Name(nome)
        assert dss.Lines.Units() == 3, "o comprimento do trecho é declarado em quilômetro"
        z = complex(dss.Lines.R1(), dss.Lines.X1()) * dss.Lines.Length()
        dss.Circuit.SetActiveElement(f"Line.{nome}")
        crus = dss.CktElement.Currents()
        correntes = [complex(crus[2 * f], crus[2 * f + 1]) for f in range(3)]
        for fase in range(3):
            esperada = tensoes[f"b{i}"][fase] - z * correntes[fase]
            medida = tensoes[f"b{i + 1}"][fase]
            assert cmath.isclose(medida, esperada, rel_tol=1e-6, abs_tol=1e-3), (nome, fase, medida, esperada)
            conferidas += 1
    assert conferidas == 15, "cinco trechos x três fases"

    # e a tensão que o módulo GRAVA por barra e fase é a mesma, em por unidade de tensão de fase
    base_fase = KV * 1000.0 / math.sqrt(3.0)
    por_barra_fase = {(x["elemento"], x["fase"]): x["tensao_pu"]
                      for x in saida["elementos"] if x["tipo"] == "barra"}
    for barra, fasores in tensoes.items():
        for fase, valor in enumerate(fasores, start=1):
            assert por_barra_fase[(barra, fase)] == pytest.approx(abs(valor) / base_fase, rel=1e-4)

    # a tensão cai monotonicamente da fonte para a ponta: é a assinatura de um radial com carga no fim
    caminho = [por_barra_fase[(f"b{i}", 1)] for i in range(1, 7)]
    assert caminho == sorted(caminho, reverse=True), caminho
    assert caminho[0] > caminho[-1], caminho


def test_carregamento_do_trecho_e_a_corrente_sobre_a_nominal_declarada():
    """O carregamento não vem do cadastro (a BDGD não traz ampacidade): é a corrente sobre a corrente
    nominal DECLARADA no parâmetro, e o parâmetro sai gravado ao lado do número."""
    saida = _resolver(_alimentador_em_serie(), corrente_nominal_a=25.0)
    trechos = [x for x in saida["elementos"] if x["tipo"] == "trecho"]
    assert len(trechos) == 5
    for x in trechos:
        # os dois números saem arredondados a 4 casas; a tolerância é a do arredondamento, não folga
        assert x["carregamento_pc"] == pytest.approx(100.0 * x["corrente_a"] / 25.0, abs=1e-3)
    assert saida["resumo"]["corrente_nominal_de_referencia_a"] == 25.0
    assert saida["parametros"]["corrente_nominal_a"] == 25.0


def test_perda_do_trecho_e_positiva_e_soma_com_a_do_circuito():
    saida = _resolver(_alimentador_em_serie())
    trechos = [x for x in saida["elementos"] if x["tipo"] == "trecho"]
    assert all(x["perda_kw"] > 0 for x in trechos), trechos
    # o trecho mais comprido perde mais que o mais curto, com a mesma corrente atravessando os dois
    por_nome = {x["elemento"]: x["perda_kw"] for x in trechos}
    assert por_nome["t4"] > por_nome["t5"], por_nome  # 3,0 km contra 0,5 km


# --- cláusula: convergência sempre ao lado do resultado ------------------------------------------------

def test_convergencia_vem_com_o_resultado():
    saida = _resolver(_alimentador_em_serie())
    c = saida["convergencia"]
    assert set(c) == {"convergiu", "pontos", "pontos_sem_convergencia", "pontos_nao_convergidos"}
    assert c["convergiu"] is True and c["pontos"] == 1 and c["pontos_sem_convergencia"] == 0


def test_varredura_anual_percorre_os_864_pontos():
    saida = fp.resolver(_alimentador_em_serie(),
                        fp.validar_parametros({"modo": "anual", "ano": ANO}))
    assert saida["convergencia"]["pontos"] == opendss.PONTOS_DA_CURVA == 864
    assert saida["convergencia"]["pontos_sem_convergencia"] == 0
    ponto = saida["ponto_critico"]
    assert 1 <= ponto["mes"] <= 12 and ponto["tipo_de_dia"] in opendss.TIPOS_DE_DIA
    assert 0 <= ponto["hora"] <= 23 and ponto["carga_kw"] > 0
    # energia da carga: com curva plana, é a potência do ponto vezes as horas do ano
    energia = saida["energia"]
    assert energia["horas_do_ano"] == 8760.0
    assert energia["energia_da_carga_kwh"] == pytest.approx(ponto["carga_kw"] * 8760.0, rel=1e-3)
    assert energia["energia_perdida_kwh"] > 0


def test_alimentador_que_nao_converge_fica_marcado_e_fora_da_agregacao():
    """Carga além do joelho da curva de máxima transferência de potência: o fluxo NÃO fecha, e essa é a
    situação física em que ele não fecha mesmo. `vminpu` baixo é o que impede o OpenDSS de salvar a
    iteração trocando a carga por impedância constante quando a tensão desaba — com o `vminpu` padrão o
    solver converge para um ponto que não é o pedido. O resultado sai MARCADO, sem estado por elemento, e
    a agregação de vários alimentadores o exclui NOMEANDO-O."""
    saida = _resolver(_alimentador_em_serie(kw=1.0e5, vminpu=0.001))
    assert saida["convergencia"]["convergiu"] is False
    assert saida["convergencia"]["pontos_sem_convergencia"] == saida["convergencia"]["pontos"]
    assert saida["elementos"] == [], "sem convergência não se lê estado de elemento"
    codigos = {a["codigo"] for a in saida["avisos"]}
    assert "alimentador_nao_convergiu" in codigos and "pontos_sem_convergencia" in codigos

    bom = {"subrede": "ZT-A", "convergiu": True,
           "energia": {"energia_da_carga_kwh": 10.0, "energia_perdida_kwh": 1.0,
                       "perda_de_ferro_simulada_kwh": 0.5, "perda_de_ferro_declarada_kwh": 0.5},
           "resumo": {"tensao_pu_minima": 0.97}}
    ruim = {"subrede": "ZT-B", "convergiu": False,
            "energia": {"energia_da_carga_kwh": 999.0, "energia_perdida_kwh": 999.0,
                        "perda_de_ferro_simulada_kwh": 999.0, "perda_de_ferro_declarada_kwh": 999.0},
            "resumo": {"tensao_pu_minima": 0.01}}
    agregado = fp.agregar([bom, ruim])
    assert agregado["alimentadores"] == 2 and agregado["alimentadores_agregados"] == 1
    assert agregado["alimentadores_fora_por_nao_convergencia"] == ["ZT-B"]
    assert agregado["energia_perdida_kwh"] == 1.0 and agregado["tensao_pu_minima"] == 0.97


# --- cláusula: perda de ferro simulada x PER_FER x horas do ano ----------------------------------------

def _com_transformador(kva=75.0, per_fer_w=150.0, kw=20.0, km=0.05):
    """Alimentador com um transformador de distribuição: média tensão até o trafo, baixa tensão depois.
    `perda_ferro_pc` é o que o conversor escreve como `%noloadloss` a partir do PER_FER do arquivo."""
    barras = {"b1": KV, "b2": KV, "b3": 0.38}
    linhas = [_trecho("t1", "b1", "b2", km)]
    trafos = [{"nome": "x0", "codigo": "TR-ZT", "barra_at": "b2", "barra_bt": "b3", "kva": kva,
               "kv_bt": 0.38, "kv_at": KV, "fases": 3, "nos_at": ".1.2.3", "nos_bt": ".1.2.3.0",
               "ligacao_at": "delta", "ligacao_bt": "wye",
               "perda_ferro_pc": 100.0 * per_fer_w / (1000.0 * kva),
               "resistencia_pc": 1.0}]
    cargas = [{"nome": "u0", "barra": "b3", "fases_nos": [1, 2, 3], "fases": 3, "ligacao": "wye",
               "kv": 0.38, "kw": kw, "fator_de_potencia": 0.92, "modelo": 1, "vminpu": 0.92,
               "vmaxpu": 1.25, "curva": "cplana", "energia_mensal_medida": True}]
    return _modelo(linhas, barras, cargas, trafos, curvas=_curva_plana())


def test_perda_de_ferro_simulada_bate_com_a_declarada():
    """A cláusula: perda de ferro simulada no ano contra PER_FER x 8760 do arquivo, dentro de +-2 %.

    A diferença que sobra tem causa conhecida e MEDIDA no teste seguinte, não é ruído: a perda a vazio do
    OpenDSS varia com o quadrado da tensão da barra, e a barra do transformador só fica em 1 por unidade
    quando não há queda antes dela. Por isso este alimentador de conferência é curto (50 m de média
    tensão): aqui se mede a fidelidade do motor ao PER_FER do arquivo, não a queda de tensão de um
    circuito de exemplo."""
    saida = fp.resolver(_com_transformador(kw=5.0), fp.validar_parametros({"modo": "anual", "ano": ANO}))
    energia = saida["energia"]
    assert energia["transformadores_com_per_fer"] == 1
    assert energia["transformadores_sem_per_fer"] == 0
    assert energia["perda_de_ferro_declarada_w"] == pytest.approx(150.0, rel=1e-9)
    assert energia["perda_de_ferro_declarada_kwh"] == pytest.approx(150.0 / 1000.0 * 8760.0, rel=1e-9)
    razao = energia["razao_perda_de_ferro"]
    assert razao is not None
    assert abs(razao - 1.0) <= 0.02, razao
    # e a perda de ferro aparece TAMBÉM por transformador, no resultado por elemento
    trafos = [x for x in saida["elementos"] if x["tipo"] == "trafo"]
    assert len(trafos) == 1 and trafos[0]["codigo"] == "TR-ZT"
    assert trafos[0]["perda_ferro_kw"] == pytest.approx(0.15, rel=0.02)
    assert trafos[0]["carregamento_pc"] > 0


def test_a_razao_da_perda_de_ferro_cai_quando_o_transformador_carrega():
    """A causa da diferença que sobra, nomeada e MEDIDA em vez de escondida.

    A perda a vazio do OpenDSS é uma admitância fixa ligada atrás da impedância do enrolamento. Com o
    transformador vazio o núcleo vê a tensão nominal e a perda simulada é o PER_FER do arquivo; com o
    transformador carregado o núcleo vê menos, e a perda cai com o quadrado dessa tensão. Medido aqui: a
    razão desce monotonicamente com o carregamento, e a +-2 % da cláusula vale até cerca de 20 % de carga
    da placa — acima disso o desvio passa de 2 % por esse motivo, não por erro de conversão.

    Isto é o que quem lê o número precisa saber, e é por isso que a análise grava o carregamento do
    transformador ao lado da perda de ferro dele."""
    razoes = []
    for kw in (0.5, 5.0, 12.0, 20.0):
        saida = fp.resolver(_com_transformador(kw=kw), fp.validar_parametros({"modo": "anual", "ano": ANO}))
        trafo = [x for x in saida["elementos"] if x["tipo"] == "trafo"][0]
        razoes.append((trafo["carregamento_pc"], saida["energia"]["razao_perda_de_ferro"]))
    carregamentos = [c for c, _ in razoes]
    valores = [r for _, r in razoes]
    assert carregamentos == sorted(carregamentos), razoes
    assert valores == sorted(valores, reverse=True), razoes
    assert valores[0] == pytest.approx(1.0, abs=0.005), razoes  # praticamente vazio: bate com o arquivo
    assert abs(valores[1] - 1.0) <= 0.02, razoes                # carregamento médio anual: dentro da faixa
    assert abs(valores[-1] - 1.0) > 0.02, razoes                # 30 % da placa: já sai da faixa, e por quê


def test_transformador_sem_per_fer_e_contado_e_nao_supoe_perda():
    modelo = _com_transformador()
    modelo["trafos"][0]["perda_ferro_pc"] = None
    saida = fp.resolver(modelo, fp.validar_parametros({"modo": "anual", "ano": ANO}))
    energia = saida["energia"]
    assert energia["transformadores_sem_per_fer"] == 1
    assert energia["perda_de_ferro_declarada_kwh"] == 0.0
    assert energia["razao_perda_de_ferro"] is None, "sem PER_FER não existe razão a comparar"
    assert "transformador_sem_perda_de_ferro_no_arquivo" in {a["codigo"] for a in saida["avisos"]}


# --- cláusula: parâmetros declarados na ficha ----------------------------------------------------------

def test_parametros_saem_na_ficha_do_resultado():
    saida = _resolver(_alimentador_em_serie(), fator_de_carga=1.5, tensao_da_fonte_pu=1.02)
    assert saida["parametros"] == {
        "modo": "hora", "ponto": 0, "ano": ANO, "fator_de_carga": 1.5,
        "modelo_de_carga": "potencia_constante", "zipv": None, "tensao_da_fonte_pu": 1.02,
        "corrente_nominal_a": 400.0, "com_geracao_distribuida": True}
    assert saida["pico_ram_mb"] > 0
    assert "triagem" in saida["resumo"]["impedancia"]


def test_fator_de_carga_e_modelo_de_carga_mudam_o_resultado():
    base = _resolver(_alimentador_em_serie())
    dobro = _resolver(_alimentador_em_serie(), fator_de_carga=2.0)
    corrente = lambda s: max(x["corrente_a"] for x in s["elementos"] if x["tipo"] == "trecho")  # noqa: E731
    assert corrente(dobro) > 1.9 * corrente(base), (corrente(base), corrente(dobro))

    # com carga de impedância constante a corrente cai (a tensão cai e a potência cai com ela)
    impedancia = _resolver(_alimentador_em_serie(), modelo_de_carga="impedancia_constante")
    assert impedancia["parametros"]["modelo_de_carga"] == "impedancia_constante"
    assert corrente(impedancia) != pytest.approx(corrente(base), rel=1e-9)


def test_tensao_da_fonte_desloca_todas_as_barras():
    alta = _resolver(_alimentador_em_serie(), tensao_da_fonte_pu=1.05)
    pu = {x["elemento"]: x["tensao_pu"] for x in alta["elementos"]
          if x["tipo"] == "barra" and x["fase"] == 1}
    assert pu["b1"] == pytest.approx(1.05, rel=1e-3)


# --- refutação: determinismo ---------------------------------------------------------------------------

def test_o_mesmo_alimentador_duas_vezes_da_o_mesmo_resultado():
    """O adversário roda duas vezes e compara. Tudo o que não é relógio nem memória tem de bater bit a bit."""
    def sem_relogio(s):
        return {k: v for k, v in s.items() if k not in ("duracao_ms", "pico_ram_mb")}

    primeira = fp.resolver(_alimentador_em_serie(), fp.validar_parametros({"modo": "anual", "ano": ANO}))
    segunda = fp.resolver(_alimentador_em_serie(), fp.validar_parametros({"modo": "anual", "ano": ANO}))
    assert sem_relogio(primeira) == sem_relogio(segunda)


# --- refutação: parâmetro que não fecha é recusado -----------------------------------------------------

def test_o_diretorio_de_trabalho_do_processo_sobrevive_ao_calculo():
    """Refutação achada ao construir: o `Compile` do OpenDSS troca o diretório de trabalho DO PROCESSO para
    a pasta do circuito. Com a pasta temporária apagada no fim, o processo ficava sem diretório válido e a
    chamada seguinte ao motor morria com falha de segmentação — o worker cairia no segundo alimentador.
    Aqui se confere que o diretório volta ao que era, e que dois cálculos seguidos passam."""
    import os

    antes = os.getcwd()
    fp.resolver(_alimentador_em_serie(), fp.validar_parametros({"modo": "hora", "ponto": 0, "ano": ANO}))
    assert os.getcwd() == antes
    fp.resolver(_com_transformador(), fp.validar_parametros({"modo": "hora", "ponto": 0, "ano": ANO}))
    assert os.getcwd() == antes


def test_parametro_desconhecido_e_recusado():
    with pytest.raises(fp.ErroFluxo) as e:
        fp.validar_parametros({"fator_carga": 2.0})
    assert e.value.codigo == "parametro_desconhecido" and "fator_carga" in e.value.mensagem


def test_modo_hora_sem_ponto_e_recusado():
    with pytest.raises(fp.ErroFluxo) as e:
        fp.validar_parametros({"modo": "hora"})
    assert e.value.codigo == "ponto_ausente"
    for ruim in (-1, 864, "meia-noite"):
        with pytest.raises(fp.ErroFluxo):
            fp.validar_parametros({"modo": "hora", "ponto": ruim})


def test_zip_sem_coeficientes_e_recusado():
    with pytest.raises(fp.ErroFluxo) as e:
        fp.validar_parametros({"modelo_de_carga": "zip"})
    assert e.value.codigo == "zipv_ausente"
    with pytest.raises(fp.ErroFluxo) as e:
        fp.validar_parametros({"modelo_de_carga": "zip", "zipv": [0.5, 0.5, 0.5, 0, 0, 1, 0.8]})
    assert e.value.codigo == "zipv_nao_soma_um"
    with pytest.raises(fp.ErroFluxo) as e:
        fp.validar_parametros({"zipv": [0, 0, 1, 0, 0, 1, 0.8]})
    assert e.value.codigo == "zipv_sem_modelo_zip"
    aceito = fp.validar_parametros({"modelo_de_carga": "zip", "zipv": [0, 0, 1, 0, 0, 1, 0.8]})
    assert aceito["zipv"] == [0, 0, 1, 0, 0, 1, 0.8]


def test_numero_invalido_em_parametro_e_recusado():
    for chave, valor, codigo in (("fator_de_carga", 0, "fator_de_carga_invalido"),
                                 ("fator_de_carga", "x", "fator_de_carga_invalido"),
                                 ("corrente_nominal_a", -5, "corrente_nominal_invalida"),
                                 ("tensao_da_fonte_pu", 0, "tensao_da_fonte_invalida"),
                                 ("modo", "semanal", "modo_invalido"),
                                 ("modelo_de_carga", "exponencial", "modelo_de_carga_invalido"),
                                 ("ano", "ontem", "ano_invalido")):
        with pytest.raises(fp.ErroFluxo) as e:
            fp.validar_parametros({chave: valor})
        assert e.value.codigo == codigo, (chave, valor, e.value.codigo)


def test_ponto_da_curva_traduzido_para_mes_tipo_de_dia_e_hora():
    assert fp.descrever_ponto(0) == {"indice": 0, "mes": 1, "tipo_de_dia": "DU", "hora": 0}
    assert fp.descrever_ponto(23) == {"indice": 23, "mes": 1, "tipo_de_dia": "DU", "hora": 23}
    assert fp.descrever_ponto(24) == {"indice": 24, "mes": 1, "tipo_de_dia": "SA", "hora": 0}
    assert fp.descrever_ponto(72) == {"indice": 72, "mes": 2, "tipo_de_dia": "DU", "hora": 0}
    assert fp.descrever_ponto(863) == {"indice": 863, "mes": 12, "tipo_de_dia": "DO", "hora": 23}


def test_geracao_distribuida_pode_ser_desligada_e_muda_a_corrente():
    modelo = _alimentador_em_serie()
    modelo["cargas"].append({"nome": "g1", "barra": "b6", "fases_nos": [1, 2, 3], "fases": 3,
                             "ligacao": "wye", "kv": KV, "kw": -100.0, "fator_de_potencia": 1.0,
                             "modelo": 5, "vminpu": 0.5, "vmaxpu": 1.5, "curva": "cplana",
                             "energia_mensal_medida": True})
    corrente = lambda s: max(x["corrente_a"] for x in s["elementos"] if x["tipo"] == "trecho")  # noqa: E731
    com = _resolver(modelo)
    sem = _resolver(modelo, com_geracao_distribuida=False)
    assert corrente(sem) > corrente(com), (corrente(com), corrente(sem))
    assert sem["parametros"]["com_geracao_distribuida"] is False
