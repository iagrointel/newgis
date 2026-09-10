"""Conversor OpenDSS: as partes que não precisam de banco (item L4-05-a-exportar-opendss).

O que é provado aqui:
  * o dicionário de códigos de tensão da BDGD cobre o domínio inteiro (0 a 109, sem buraco) e resolve o
    código 63, que faltava no conversor da casa;
  * todo código de tensão que aparece nas tabelas do acervo da casa é resolvido pelo dicionário (o teste
    pula, com a razão, na máquina que não tem o acervo);
  * a curva de 864 pontos tem a forma que o item declara (12 meses x 3 tipos de dia x 24 horas) e CONSERVA
    energia; o calendário de dias úteis, sábados e domingos-e-feriados fecha o ano;
  * o escritor de arquivos .dss produz o texto esperado e nunca engole falta de dado."""

import os

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from app.rede_utilidades import opendss
from tests.dados import carga_bdgd

ANO = 2024


def test_dicionario_de_tensao_cobre_o_dominio_inteiro():
    codigos = {int(c) for c in opendss.TENSAO_KV}
    assert codigos == set(range(0, 110)), sorted(set(range(0, 110)) - codigos)
    assert opendss.TENSAO_KV["63"] == 23.1, "o código 63 era o que faltava no conversor da casa"
    # os treze códigos do conversor da casa continuam valendo exatamente o mesmo
    da_casa = {"3": 0.12, "6": 0.127, "10": 0.22, "13": 0.24, "14": 0.254, "15": 0.38, "37": 6.6,
               "39": 7.96, "41": 11.4, "46": 13.2, "49": 13.8, "58": 19.919, "72": 34.5}
    assert {k: opendss.TENSAO_KV[k] for k in da_casa} == da_casa


def test_codigo_de_tensao_ausente_ou_fora_do_dominio_para_a_conversao():
    assert opendss.kv_do_codigo("63", "TEN_NOM") == 23.1
    assert opendss.kv_do_codigo("49.0", "TEN_NOM") == 13.8
    for ruim in (None, "", "999", "abc"):
        with pytest.raises(opendss.ErroConversao) as e:
            opendss.kv_do_codigo(ruim, "TEN_NOM")
        assert e.value.codigo in ("tensao_ausente", "tensao_codigo_desconhecido")


def test_todo_codigo_de_tensao_do_acervo_da_casa_e_resolvido():
    """Cláusula do portão: o dicionário está completo PARA OS PACOTES DA CASA. Aqui isso é medido contra o
    acervo que a máquina tem (schema lido de PLAT_REDE_REFERENCIA_ESQUEMA, só leitura), não afirmado."""
    esquema = carga_bdgd.esquema()
    if not esquema:
        pytest.skip("sem PLAT_REDE_REFERENCIA_ESQUEMA: o acervo BDGD da casa não está nesta máquina")
    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        pytest.skip("sem PLAT_DSN")
    achados = set()
    with psycopg2.connect(dsn, cursor_factory=RealDictCursor) as con, con.cursor() as cur:
        cur.execute(f"SELECT DISTINCT ten_nom AS v FROM {esquema}.ctmt WHERE ten_nom IS NOT NULL")
        achados |= {str(r["v"]).strip() for r in cur.fetchall()}
        cur.execute(f"SELECT DISTINCT ten_pri AS v FROM {esquema}.eqtrmt WHERE ten_pri IS NOT NULL "
                    f"UNION SELECT DISTINCT ten_sec FROM {esquema}.eqtrmt WHERE ten_sec IS NOT NULL")
        achados |= {str(r["v"]).strip() for r in cur.fetchall()}
    assert achados, "o acervo devolveu zero código de tensão: a medida não vale"
    faltando = sorted(c for c in achados if c not in opendss.TENSAO_KV)
    assert faltando == [], faltando
    assert "63" in achados, "o código 63 tem de estar no acervo — é o caso que motivou a cláusula"


def test_calendario_fecha_o_ano_e_trata_feriado_como_domingo():
    calendario = opendss.dias_por_tipo(ANO)
    assert len(calendario) == 12
    assert sum(sum(m) for m in calendario) == 366, "2024 é bissexto"
    # 1 de janeiro de 2024 caiu numa segunda: como feriado, entra em domingos-e-feriados, não em dias úteis
    assert calendario[0] == (22, 4, 5)


def test_curva_de_864_pontos_conserva_energia():
    energia = [100.0] * 11 + [500.0]
    curva = opendss.curva_864(energia, ANO)
    horas = opendss.horas_dos_pontos(ANO)
    assert len(curva) == opendss.PONTOS_DA_CURVA == 864
    assert len(horas) == 864
    media_kw = sum(energia) / sum(horas)
    assert abs(sum(p * h for p, h in zip(curva, horas, strict=True)) * media_kw - sum(energia)) < 1e-6
    # dezembro tem 5 vezes a energia dos outros meses: a potência de dezembro tem de ser a maior
    assert max(curva[11 * 72:]) == pytest.approx(max(curva))
    assert min(curva) > 0


def test_curva_respeita_a_forma_do_dia_quando_ela_existe():
    forma = {"DU": [0.5] * 12 + [1.5] * 12, "SA": [1.0] * 24, "DO": [1.0] * 24}
    curva = opendss.curva_864([100.0] * 12, ANO, forma)
    janeiro_du = curva[:24]
    assert janeiro_du[13] == pytest.approx(3 * janeiro_du[0])
    horas = opendss.horas_dos_pontos(ANO)
    media_kw = sum([100.0] * 12) / sum(horas)
    assert abs(sum(p * h for p, h in zip(curva, horas, strict=True)) * media_kw - 1200.0) < 1e-6


def test_curva_recusa_entrada_de_tamanho_errado():
    for erro, argumentos in (("curva_meses", ([1.0] * 11, ANO, None)),
                             ("curva_horas", ([1.0] * 12, ANO, {"DU": [1.0] * 23}))):
        with pytest.raises(opendss.ErroConversao) as e:
            opendss.curva_864(*argumentos)
        assert e.value.codigo == erro


def test_escritor_produz_os_arquivos_da_pasta():
    modelo = {
        "nome": "ZT-1", "ano": ANO, "barra_fonte": "bA", "kv_fonte": 23.1, "pu_fonte": 1.0,
        "barras": {"bA": 23.1, "bB": 23.1, "bC": 0.38},
        "linhas": [{"nome": "t0", "barra1": "bA", "barra2": "bB", "fases": [1, 2, 3],
                    "comprimento_km": 0.15, "condutor": "2-CA"}],
        "trafos": [{"nome": "x0", "barra_at": "bB", "barra_bt": "bC", "kva": 75.0, "kv_at": 23.1,
                    "kv_bt": 0.38, "fases": 3, "nos_at": ".1.2.3", "nos_bt": ".1.2.3.0",
                    "ligacao_at": "delta", "ligacao_bt": "wye", "perda_ferro_pc": 0.2,
                    "resistencia_pc": 1.6}],
        "cargas": [{"nome": "u0", "barra": "bC", "fases_nos": [1], "fases": 1, "ligacao": "wye",
                    "kv": 0.2194, "kw": 1.25, "fator_de_potencia": 0.92, "modelo": 1, "vminpu": 0.92,
                    "vmaxpu": 1.25, "curva": "c1"}],
        "curvas": {"c1": [1.0] * 864}, "chaves": [],
    }
    arquivos = opendss.linhas_do_circuito(modelo)
    assert set(arquivos) == {"Master.dss", "Curvas.dss", "Linhas.dss", "Transformadores.dss",
                             "Cargas.dss", "NAO_FAZ.md"}
    assert "New Circuit.ZT_1 bus1=bA basekv=23.10000" in arquivos["Master.dss"]
    assert "New Line.t0 bus1=bA.1.2.3 bus2=bB.1.2.3 phases=3 length=0.150000 units=km" in arquivos["Linhas.dss"]
    assert "! condutor=2-CA" in arquivos["Linhas.dss"]
    assert "%noloadloss=0.2000" in arquivos["Transformadores.dss"]
    assert "%r=0.8000" in arquivos["Transformadores.dss"], "a resistência é repartida entre os dois enrolamentos"
    assert "New Load.u0 bus1=bC.1 phases=1" in arquivos["Cargas.dss"]
    assert "npts=864" in arquivos["Curvas.dss"]
    assert "Chave" in arquivos["NAO_FAZ.md"] and "Impedância de condutor" in arquivos["NAO_FAZ.md"]
