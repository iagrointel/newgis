"""Cláusulas de DESEMPENHO do portão de L4-13-integracao-telemetria — as duas que o adversário da rodada 2
apontou como nunca medidas (tests/unit/test_l4_adv2_telemetria_medida_ausente.py):

1. "simulador de 20 sensores de trafo (corrente por fase 5 min, temperatura, tensão 10 min) publica e a
   ficha do trafo mostra a última leitura em ≤ 5 s" — UM POST com o ciclo atual dos 20 sensores (5 grandezas
   × 20 = 100 leituras) seguido da ficha (GET /ultimas) de cada um dos 20 trafos; o relógio abre no POST e
   fecha na ÚLTIMA ficha. Portão: ≤ 5 s no total. Medido SOB a carga da cláusula 2 (1 mês × 20 sensores já
   gravado), não numa base vazia. Antes do ciclo medido roda um ciclo de AQUECIMENTO com ts já semeado
   (tudo duplicado — prova a idempotência sob 777 mil linhas e paga a derivação retroativa do motor de
   alarme sobre o lookback); o ciclo medido é o regime permanente do simulador: cada publicação tem só o
   ponto novo para derivar. O tempo do aquecimento também é gravado (latencia_catchup_motor_ms), sem
   esconder custo.
2. "consulta de 1 mês de 20 sensores em tempo medido" — 30 dias de corrente_a (a cadência de 5 min do
   simulador, 8.640 pontos por sensor) de CADA um dos 20 sensores via GET /serie (dias=30): 172.800 pontos
   no total; o tempo de parede das 20 consultas é o número gravado. O portão pede o tempo MEDIDO (não dá
   teto); a única cláusula com teto é a da ficha (≤ 5 s).

O histórico de 30 dias é SEMEADO por SQL direto (INSERT em lote via execute_values como plat_app, pelo MESMO
caminho de RLS/contexto da aplicação — db.db(Contexto); COPY não passa em tabela com RLS, medido nesta trilha):
publicar 777.600 leituras pela API HTTP só para encher a base levaria a tarde e não é o que as cláusulas medem
— elas medem a consulta sobre o mês cheio e a latência da ficha em regime, não a velocidade de backfill. A
ingestão pela API (idempotência, recusa de ts futuro/unidade errada, isolamento entre inquilinos) já está
provada em tests/api/test_rede_medicao.py.

Marcado `lento` (mesma convenção de tests/api/test_fluxo_vazao.py): fora do driver, roda com `-m lento`.
Grava tests/medidas/L4-13-integracao-telemetria.json só com PLAT_GRAVAR_MEDIDAS=1 (ADR 0001 seção 10), com
as chaves na RAIZ no formato que o teste do adversário confere + o detalhe aninhado da casa.
"""

import datetime
import json
import math
import os
import time
import uuid
from pathlib import Path

import psycopg2.extras as psycopg2_extras
import pytest

from app import db
from app.versao import git_sha_curto
from tests.api.test_fluxo_vazao import _carga_da_maquina

RAIZ = Path(__file__).resolve().parents[2]
ITEM = "L4-13-integracao-telemetria"
MEDIDAS = RAIZ / "tests" / "medidas" / f"{ITEM}.json"
COMANDO = "PLAT_GRAVAR_MEDIDAS=1 roda_teste.sh tests/api/test_rede_medicao_desempenho.py -q -m lento"

SENSORES = 20
DIAS = 30
PASSO_S = 5 * 60
KVA_NOMINAL = 112.5       # trafo típico de distribuição; I_nominal ≈ 171 A a 380 V
TENSAO_NOMINAL_V = 380.0
UTC = datetime.UTC

# grade do simulador: corrente por fase + temperatura a cada 5 min; tensão a cada 10 min (portão literal)
PONTOS_5MIN = DIAS * 24 * 12          # 8.640 por grandeza de 5 min
LINHAS_POR_SENSOR = PONTOS_5MIN * 4 + PONTOS_5MIN // 2   # 38.880
LINHAS_TOTAIS = LINHAS_POR_SENSOR * SENSORES             # 777.600


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _leitura(ativo, cod_id, ts, grandeza, valor, unidade):
    return {"ativo": ativo, "cod_id": cod_id, "ts": _iso(ts), "fonte": "simulador", "grandeza": grandeza,
            "valor": valor, "unidade": unidade}


def _corrente(i_sensor: int, k: int, fase: int) -> float:
    """~50-60 % da nominal (nunca dispara o alarme), variação determinística — nada de aleatório em prova."""
    return round(80.0 + 12.0 * math.sin(k / 48.0 + fase * 2.1 + i_sensor * 0.7), 2)


def _ciclo(ativos, ts: datetime.datetime) -> list[dict]:
    """Um ciclo de publicação do simulador: as 5 grandezas dos 20 sensores no mesmo ts."""
    leituras = []
    for i, (ativo, cod_id) in enumerate(ativos):
        for fase, grandeza in enumerate(("corrente_a", "corrente_b", "corrente_c")):
            leituras.append(_leitura(ativo, cod_id, ts, grandeza, _corrente(i, 0, fase), "A"))
        leituras.append(_leitura(ativo, cod_id, ts, "temperatura", round(55.0 + i * 0.5, 2), "C"))
        leituras.append(_leitura(ativo, cod_id, ts, "tensao_a", round(220.0 + i * 0.3, 2), "V"))
    return leituras


@pytest.fixture
def simulador(sessao_a, conexao_plat_app):
    """20 trafos com placa cadastrada e 30 dias de leituras semeadas (777.600 linhas) na cadência do
    portão. Devolve os ativos, a grade de tempo e o custo da semeadura (gravado como contexto da medida)."""
    with conexao_plat_app.cursor() as cur:
        # ids pela função SECURITY DEFINER (mesma via de test_rls.ids_por_slug): /api/eu não expõe tenant_id
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('demo', 'admin')")
        dono = cur.fetchone()
    ctx = db.Contexto(tenant_id=dono["tenant_id"], usuario_id=dono["usuario_id"], login="admin")

    ativos = [(str(uuid.uuid4()), f"ztmed-{i:02d}") for i in range(SENSORES)]
    for ativo, cod_id in ativos:
        r = sessao_a.put(f"/api/rede/medicao/ativos/{ativo}",
                         json={"cod_id": cod_id, "kva_nominal": KVA_NOMINAL,
                               "tensao_nominal_v": TENSAO_NOMINAL_V})
        assert r.status_code == 200, r.text

    agora = datetime.datetime.now(UTC)
    fim = agora.replace(second=0, microsecond=0)
    fim = fim - datetime.timedelta(minutes=fim.minute % 5)  # grade de 5 min, <= agora
    inicio = fim - datetime.timedelta(days=DIAS)

    t0 = time.monotonic()
    with db.db(ctx) as cur:
        mes = inicio.date().replace(day=1)
        while mes <= fim.date():
            cur.execute("SELECT plat.rede_medicao_particao_garantir(%s)", (mes,))
            mes = (mes + datetime.timedelta(days=32)).replace(day=1)
        for i, (ativo, cod_id) in enumerate(ativos):
            linhas = []
            for k in range(PONTOS_5MIN):
                ts = inicio + datetime.timedelta(seconds=k * PASSO_S)
                for fase, grandeza in enumerate(("corrente_a", "corrente_b", "corrente_c")):
                    linhas.append((ctx.tenant_id, ativo, cod_id, ts, "simulador", grandeza,
                                   _corrente(i, k, fase), "A", "{}"))
                linhas.append((ctx.tenant_id, ativo, cod_id, ts, "simulador", "temperatura",
                               round(50.0 + 8.0 * math.sin(k / 96.0 + i), 2), "C", "{}"))
                if k % 2 == 0:  # tensão: grade de 10 min
                    linhas.append((ctx.tenant_id, ativo, cod_id, ts, "simulador", "tensao_a",
                                   round(220.0 + 3.0 * math.sin(k / 144.0 + i), 2), "V", "{}"))
            assert len(linhas) == LINHAS_POR_SENSOR
            psycopg2_extras.execute_values(
                cur,
                "INSERT INTO plat.rede_medicao(tenant_id, ativo, cod_id, ts, fonte, grandeza, valor, "
                "unidade, leitura) VALUES %s",
                linhas, page_size=8192)
    semeadura_s = round(time.monotonic() - t0, 1)
    return {"sessao": sessao_a, "ativos": ativos, "inicio": inicio, "fim": fim,
            "semeadura_s": semeadura_s}


@pytest.mark.lento
def test_portao_desempenho_20_sensores_ficha_e_consulta_1_mes(simulador):
    sessao = simulador["sessao"]
    ativos = simulador["ativos"]
    fim = simulador["fim"]

    # 0) aquecimento: ciclo com ts JÁ semeado — tudo duplicado (idempotência sob 777 mil linhas) e o motor
    #    de alarme deriva o lookback retroativo de uma vez (é o custo que um sensor real que ficou offline
    #    paga ao reconectar; gravado à parte, fora do teto de 5 s do regime permanente)
    ts_aquece = fim - datetime.timedelta(minutes=10)  # na grade de 5 E de 10 min -> as 5 grandezas existem
    t0 = time.monotonic()
    r = sessao.post("/api/rede/medicao/leituras", json={"leituras": _ciclo(ativos, ts_aquece)})
    assert r.status_code == 201, r.text
    corpo = r.json()
    catchup_ms = round((time.monotonic() - t0) * 1000, 1)
    assert corpo["aceitas"] == 0 and corpo["duplicadas"] == SENSORES * 5, corpo

    # 1) consulta de 1 mês de 20 sensores, tempo medido (cláusula 2): corrente_a de cada sensor, 30 dias
    t0 = time.monotonic()
    total_pontos = 0
    for ativo, _cod_id in ativos:
        r = sessao.get(f"/api/rede/medicao/ativos/{ativo}/serie",
                       params={"grandeza": "corrente_a", "dias": DIAS})
        assert r.status_code == 200, r.text
        serie = r.json()
        # a janela é [agora-30d, agora] no instante da consulta: a grade semeada cobre [fim-30d, fim-5min],
        # logo no MÁXIMO o primeiro ponto da grade já envelheceu para fora da janela — nunca mais que um
        assert PONTOS_5MIN - 1 <= serie["n"] <= PONTOS_5MIN, serie["n"]
        assert serie["pontos"][-1]["ts"] == _iso(fim - datetime.timedelta(minutes=5))
        total_pontos += serie["n"]
    consulta_ms = round((time.monotonic() - t0) * 1000, 1)

    # 2) o ciclo medido do portão (cláusula 1): 20 sensores publicam o ts novo e a ficha de cada trafo
    #    mostra essa leitura; relógio do POST à ÚLTIMA ficha — teto de 5 s para o conjunto inteiro
    t0 = time.monotonic()
    r = sessao.post("/api/rede/medicao/leituras", json={"leituras": _ciclo(ativos, fim)})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["aceitas"] == SENSORES * 5 and corpo["rejeitadas"] == [], corpo
    for ativo, _cod_id in ativos:
        r = sessao.get(f"/api/rede/medicao/ativos/{ativo}/ultimas")
        assert r.status_code == 200, r.text
        por_grandeza = {leit["grandeza"]: leit for leit in r.json()["leituras"]}
        assert por_grandeza["corrente_a"]["ts"] == _iso(fim), por_grandeza.get("corrente_a")
        assert por_grandeza["temperatura"]["ts"] == _iso(fim)
        assert por_grandeza["tensao_a"]["ts"] == _iso(fim)
    latencia_ms = round((time.monotonic() - t0) * 1000, 1)
    assert latencia_ms <= 5000, (
        f"portão estourado: 20 sensores publicaram e a última ficha fechou em {latencia_ms} ms (> 5000)")

    maquina = _carga_da_maquina()
    if os.environ.get("PLAT_GRAVAR_MEDIDAS") == "1":
        plano = {
            "latencia_ultima_leitura_ms": latencia_ms,
            "consulta_1_mes_20_sensores_ms": consulta_ms,
            "carga_1min": maquina["carga_1min"],
            "ram_livre_gb": maquina["ram_livre_gb"],
        }
        detalhe = [  # (nome, valor, unidade) — contexto da medida, mesma forma aninhada da casa
            ("sensores", SENSORES, "sensores"),
            ("linhas_semeadas", LINHAS_TOTAIS, "linhas"),
            ("pontos_por_serie", PONTOS_5MIN, "pontos"),
            ("pontos_consultados_total", total_pontos, "pontos"),
            ("latencia_catchup_motor_ms", catchup_ms, "ms"),
            ("semeadura_insert_s", simulador["semeadura_s"], "s"),
            ("teto_ficha_ms", 5000, "ms"),
            ("nucleos", maquina["nucleos"], "núcleos"),
        ]
        aninhado = {nome: {"valor": valor, "unidade": unidade, "comando": COMANDO}
                    for nome, valor, unidade in detalhe}
        for nome, unidade in (("latencia_ultima_leitura_ms", "ms"), ("consulta_1_mes_20_sensores_ms", "ms"),
                              ("carga_1min", "carga"), ("ram_livre_gb", "GB")):
            aninhado[nome] = {"valor": plano[nome], "unidade": unidade, "comando": COMANDO}
        dados = {"item": ITEM,
                 **plano,
                 "medidas": aninhado,
                 "maquina": f"frota remota (Hetzner), Postgres local da trilha; {maquina['nucleos']} núcleos",
                 "gerado_em": datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "git_sha": git_sha_curto()}
        MEDIDAS.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n[medida {ITEM}] ficha 20 sensores: {latencia_ms} ms (teto 5000) | "
          f"consulta 1 mês x 20 sensores ({total_pontos} pontos): {consulta_ms} ms | "
          f"catchup do motor: {catchup_ms} ms | carga {maquina['carga_1min']} | "
          f"RAM livre {maquina['ram_livre_gb']} GB", flush=True)
