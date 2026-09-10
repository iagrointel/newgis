"""Corrente de curto-circuito por barra e coordenação simples, sem banco (item L4-27).

Cláusulas do portão provadas aqui:

* alimentador sintético com RESPOSTA ANALÍTICA: a corrente que o módulo devolve é, barra a barra, a
  mesma que a conta fechada `Ik = c·Un/(√3·|Z|)` sobre a impedância somada à mão em ohm —
  `test_ik_bate_com_a_conta_analitica_em_tres_barras` (as três barras que o adversário confere) e
  `test_ik_de_uma_barra_so_e_v_sobre_z`;
* dispositivo SEM faixa de interrupção cadastrada sai `sem_dado`, nunca com faixa suposta —
  `test_dispositivo_sem_faixa_sai_sem_dado`; com faixa, o veredito separa os três casos —
  `test_veredito_por_faixa`.

Refutação (papel adversário), provada aqui:

* `test_fonte_sem_potencia_de_curto_e_recusada` e `test_fonte_com_impedancia_nula_e_recusada`: fonte de
  impedância zero (ou premissa ausente) é RECUSADA, em vez de devolver corrente infinita;
* `test_barra_sem_caminho_ate_a_fonte_sai_sem_corrente`: ausência de caminho vira corrente NULA com
  aviso, nunca zero (zero seria uma medida);
* `test_laco_sai_com_aviso`: onde há malha o resultado avisa que a corrente sai subestimada;
* `test_premissa_desconhecida_e_recusada`: premissa que o cálculo não conhece não é ignorada em silêncio.
"""

import math

import pytest

from app.rede_utilidades import curto_circuito as cc
from app.rede_utilidades import pandapower_rede

KV = 13.8
R_KM = pandapower_rede.IMPEDANCIA_REFERENCIA["r_ohm_per_km"]
X_KM = pandapower_rede.IMPEDANCIA_REFERENCIA["x_ohm_per_km"]
SCC_MVA = 100.0
C = 1.05
XR = 10.0


def _modelo(linhas, barras, chaves=(), trafos=()):
    return {"nome": "ZT-CURTO", "ano": 2026, "subredes": ["s"], "barra_fonte": "b1", "kv_fonte": KV,
            "pu_fonte": 1.0, "codigo_tensao_nominal": "49", "barras": dict(barras),
            "linhas": list(linhas), "trafos": list(trafos), "cargas": [], "curvas": {},
            "chaves": list(chaves),
            "conferencia": {"barras_esperadas": len(barras), "linhas_esperadas": len(linhas),
                            "transformadores": len(trafos), "cargas": 0, "geracao_distribuida": 0,
                            "nos_da_subrede": len(barras), "fusoes_por_chave_fechada": 0,
                            "trechos_da_subrede": len(linhas), "trechos_sem_no_na_topologia": 0}}


def _trecho(nome, a, b, km):
    return {"nome": nome, "barra1": a, "barra2": b, "fases": [1, 2, 3], "comprimento_km": km,
            "condutor": None, "feicao_id": f"f-{nome}"}


def _alimentador_analitico():
    """Três trechos em série a partir da fonte: 1 km, 2 km e 4 km. Radial puro, uma tensão só — é a
    forma em que a resposta fechada existe e a soma de impedância é feita à mão sem ambiguidade."""
    linhas = [_trecho("t1", "b1", "b2", 1.0), _trecho("t2", "b2", "b3", 2.0),
              _trecho("t3", "b3", "b4", 4.0)]
    barras = {f"b{i}": KV for i in range(1, 5)}
    return _modelo(linhas, barras)


def _ik_analitico(km_ate_a_barra: float) -> tuple[float, float]:
    """A conta fechada, em ohm, sem passar por nada do módulo:

      Z_fonte = (Un²/Skc") repartido pela relação X/R;  Z_trecho = (r + jx)·km;
      Ik3 = c·Un/(√3·|Z1|);   Ik1 = √3·c·Un/|2·Z1 + Z0|, com Z0 = k0·Z1 no trecho e k0_fonte·Z na fonte.
    """
    modulo_fonte = KV * KV / SCC_MVA
    r_fonte = modulo_fonte / math.sqrt(1.0 + XR * XR)
    z_fonte = complex(r_fonte, XR * r_fonte)
    z_linha = complex(R_KM, X_KM) * km_ate_a_barra
    z1 = z_fonte + z_linha
    z0 = z_fonte * cc.PREMISSAS_PADRAO["fator_sequencia_zero_fonte"] \
        + z_linha * cc.PREMISSAS_PADRAO["fator_sequencia_zero_linha"]
    un = KV * 1000.0
    ik3 = C * un / (math.sqrt(3.0) * abs(z1))
    ik1 = math.sqrt(3.0) * C * un / abs(2.0 * z1 + z0)
    return ik3, ik1


def _calcular(modelo, **premissas):
    p = cc.validar_premissas({"potencia_de_curto_mva": SCC_MVA, **premissas})
    return cc.calcular(modelo, p)


# --- cláusula: resposta analítica --------------------------------------------------------------------

def test_ik_de_uma_barra_so_e_v_sobre_z():
    """A barra da própria fonte: Z é só a da fonte, e Ik3 = c·Un/(√3·|Z_fonte|)."""
    saida = _calcular(_modelo([], {"b1": KV}))
    esperado, _ = _ik_analitico(0.0)
    # o módulo arredonda a corrente ao miliampere; a tolerância é essa, não a do float
    assert saida["barras"][0]["ik3_a"] == pytest.approx(esperado, abs=1e-3)


@pytest.mark.parametrize("barra,km", [("b2", 1.0), ("b3", 3.0), ("b4", 7.0)])
def test_ik_bate_com_a_conta_analitica_em_tres_barras(barra, km):
    """As TRÊS barras que a refutação do item manda conferir contra cálculo manual."""
    saida = _calcular(_alimentador_analitico())
    linha = next(b for b in saida["barras"] if b["barra"] == barra)
    ik3, ik1 = _ik_analitico(km)
    assert linha["ik3_a"] == pytest.approx(ik3, rel=1e-6)
    assert linha["ik1_a"] == pytest.approx(ik1, rel=1e-6)
    # a corrente cai à medida que a barra se afasta da fonte: sanidade física, não só aritmética
    assert linha["ik3_a"] < saida["barras"][0]["ik3_a"] or barra == "b1"


def test_ik1_iguala_ik3_quando_a_sequencia_zero_iguala_a_positiva():
    """Identidade da própria formulação: com Z0 = Z1 em toda parte, `3c/|2Z1+Z0|` = `c/|Z1|`."""
    saida = _calcular(_alimentador_analitico(), fator_sequencia_zero_linha=1.0,
                      fator_sequencia_zero_fonte=1.0)
    for b in saida["barras"]:
        assert b["ik1_a"] == pytest.approx(b["ik3_a"], rel=1e-9)


def test_fator_de_tensao_multiplica_a_corrente():
    """`c` é fator de proporcionalidade direto: dobrar `c` dobra toda corrente."""
    um = _calcular(_alimentador_analitico(), fator_tensao_c=1.0)
    dois = _calcular(_alimentador_analitico(), fator_tensao_c=2.0)
    for a, b in zip(um["barras"], dois["barras"], strict=True):
        assert b["ik3_a"] == pytest.approx(2.0 * a["ik3_a"], abs=2e-3)


def test_transformador_muda_a_tensao_de_base_e_a_corrente_de_baixa_e_maior():
    """Descer para a baixa tensão aumenta a corrente na mesma potência: a base de corrente sobe na razão
    inversa da tensão. O que se checa é a direção, e que a barra de baixa não fica sem número."""
    modelo = _modelo([_trecho("t1", "b1", "b2", 1.0)], {"b1": KV, "b2": KV, "b3": 0.38},
                     trafos=[{"nome": "x0", "codigo": "TR-1", "barra_at": "b2", "barra_bt": "b3",
                              "kva": 75.0, "kv_at": KV, "kv_bt": 0.38, "fases": 3,
                              "perda_ferro_pc": 0.2, "resistencia_pc": 1.2}])
    saida = _calcular(modelo)
    bt = next(b for b in saida["barras"] if b["barra"] == "b3")
    assert bt["alcancada"] and bt["ik3_a"] > 0
    # o delta do primário bloqueia a sequência zero da média: em b3 o Z0 acumulado é só o do trafo
    assert bt["z0_pu_r"] == pytest.approx(bt["z1_pu_r"] - next(
        b["z1_pu_r"] for b in saida["barras"] if b["barra"] == "b2"), rel=1e-9)


# --- cláusula: dispositivo sem faixa cadastrada sai "sem dado" ----------------------------------------

def _com_chave(atributos, barras=("b2",)):
    modelo = _alimentador_analitico()
    modelo["chaves"] = [{"feicao_id": "11111111-1111-1111-1111-111111111111", "tipo": "religador",
                         "estado": "fechada", "nos": ["n1"], "codigo": "CH-1",
                         "atributos": atributos, "barras": list(barras)}]
    return modelo


def test_dispositivo_sem_faixa_sai_sem_dado():
    saida = _calcular(_com_chave({"unsemt_cod_id": "CH-1"}))
    por_barra = {d["barra"]: d for d in saida["dispositivos"]}
    # b3 e b4 estão a jusante da chave que fica em b2: o dispositivo a montante existe, a faixa não
    assert por_barra["b3"]["codigo"] == "CH-1"
    assert por_barra["b3"]["veredito"] == "sem_dado"
    assert por_barra["b3"]["faixa_min_a"] is None and por_barra["b3"]["faixa_max_a"] is None
    # a barra da fonte não tem dispositivo entre ela e a fonte
    assert por_barra["b1"]["veredito"] == "sem_dispositivo_a_montante"
    # a própria barra do dispositivo não conta o dispositivo que está nela (a falta está nos terminais)
    assert por_barra["b2"]["veredito"] == "sem_dispositivo_a_montante"


@pytest.mark.parametrize("minimo,maximo,esperado", [
    (0.0, 1e9, "interrompe"),
    (1e9, 2e9, "abaixo_da_faixa"),
    (0.0, 1.0, "acima_da_capacidade"),
    (None, None, "sem_dado"),
])
def test_veredito_por_faixa(minimo, maximo, esperado):
    atributos = {"unsemt_cod_id": "CH-1"}
    if minimo is not None:
        atributos["corrente_interrupcao_min_a"] = minimo
    if maximo is not None:
        atributos["corrente_interrupcao_max_a"] = maximo
    saida = _calcular(_com_chave(atributos))
    por_barra = {d["barra"]: d for d in saida["dispositivos"]}
    assert por_barra["b4"]["veredito"] == esperado


def test_faixa_invertida_no_cadastro_vira_sem_dado():
    """Mínimo maior que máximo não é faixa: é erro de cadastro. Vira `sem_dado`, e nunca se conserta
    o dado do inquilino em silêncio trocando os dois."""
    saida = _calcular(_com_chave({"corrente_interrupcao_min_a": 500.0,
                                  "corrente_interrupcao_max_a": 100.0}))
    por_barra = {d["barra"]: d for d in saida["dispositivos"]}
    assert por_barra["b4"]["veredito"] == "sem_dado"


def test_contagem_por_veredito_fecha_com_a_lista():
    saida = _calcular(_com_chave({"corrente_interrupcao_min_a": 0.0,
                                  "corrente_interrupcao_max_a": 1e9}))
    contagem = saida["resumo"]["dispositivos_por_veredito"]
    assert sum(contagem.values()) == len(saida["dispositivos"]) == len(saida["barras"])
    assert set(contagem) <= set(cc.VEREDITOS)


# --- refutação: a fonte de impedância nula ------------------------------------------------------------

def test_fonte_sem_potencia_de_curto_e_recusada():
    with pytest.raises(cc.ErroCurto) as e:
        cc.validar_premissas({})
    assert e.value.codigo == "impedancia_de_fonte_ausente"
    with pytest.raises(cc.ErroCurto):
        cc.validar_premissas(None)


@pytest.mark.parametrize("valor", [0, 0.0, -1.0, "0"])
def test_fonte_com_impedancia_nula_e_recusada(valor):
    with pytest.raises(cc.ErroCurto) as e:
        cc.validar_premissas({"potencia_de_curto_mva": valor})
    assert e.value.codigo == "impedancia_de_fonte_nula"


def test_potencia_de_curto_nao_numerica_e_recusada():
    with pytest.raises(cc.ErroCurto) as e:
        cc.validar_premissas({"potencia_de_curto_mva": "muita"})
    assert e.value.codigo == "impedancia_de_fonte_nula"


def test_premissa_desconhecida_e_recusada():
    with pytest.raises(cc.ErroCurto) as e:
        cc.validar_premissas({"potencia_de_curto_mva": 100.0, "impedancia_da_fonte": 0.0})
    assert e.value.codigo == "premissa_desconhecida"


def test_fator_de_tensao_absurdo_e_recusado():
    with pytest.raises(cc.ErroCurto) as e:
        cc.validar_premissas({"potencia_de_curto_mva": 100.0, "fator_tensao_c": 50.0})
    assert e.value.codigo == "premissa_invalida"


def test_premissas_saem_gravadas_no_resultado():
    """O número não se lê sem a hipótese: toda premissa volta no resultado."""
    saida = _calcular(_alimentador_analitico())
    assert set(cc.PREMISSAS_PADRAO) <= set(saida["premissas"])
    assert saida["premissas"]["potencia_de_curto_mva"] == SCC_MVA
    assert saida["resumo"]["impedancia_de_referencia"] == pandapower_rede.IMPEDANCIA_REFERENCIA


# --- refutação: ausência não vira zero ----------------------------------------------------------------

def test_barra_sem_caminho_ate_a_fonte_sai_sem_corrente():
    modelo = _alimentador_analitico()
    modelo["barras"]["b9"] = KV               # barra solta, sem trecho nenhum
    saida = _calcular(modelo)
    solta = next(b for b in saida["barras"] if b["barra"] == "b9")
    assert solta["alcancada"] is False
    assert solta["ik3_a"] is None and solta["ik1_a"] is None
    assert any(a["codigo"] == "barra_sem_caminho_ate_a_fonte" for a in saida["avisos"])
    assert saida["resumo"]["barras_alcancadas"] == 4


def test_laco_sai_com_aviso():
    modelo = _alimentador_analitico()
    modelo["linhas"].append(_trecho("t4", "b4", "b2", 3.0))   # fecha a malha
    saida = _calcular(modelo)
    aviso = next(a for a in saida["avisos"] if a["codigo"] == "rede_com_laco")
    assert aviso["quantidade"] == 1
    assert saida["resumo"]["arestas_fora_da_arvore"] == 1


def test_sem_laco_nao_avisa():
    saida = _calcular(_alimentador_analitico())
    assert saida["avisos"] == []
    assert saida["resumo"]["arestas_fora_da_arvore"] == 0


def test_nome_da_barra_volta_ao_no_da_topologia():
    """A camada lê a coordenada de `plat.rede_topo_no` pelo identificador escondido no nome da barra."""
    assert cc._no_id("b" + "0123456789abcdef" * 2) == "01234567-89ab-cdef-0123-456789abcdef"
    assert cc._no_id("b1") is None and cc._no_id("") is None
    assert cc._no_id("b" + "z" * 32) is None
