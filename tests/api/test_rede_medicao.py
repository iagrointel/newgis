"""Telemetria da rede de utilidades (item L4-13-integracao-telemetria; ADR — ver docs/adr/ desta trilha).

Cláusulas do portão provadas aqui:
  - idempotência por (ativo, grandeza, ts): publicar o mesmo trio duas vezes não duplica
    (test_lote_idempotente_nao_duplica).
  - refutação do item: "envia timestamp futuro e unidade errada e confere recusa com mensagem"
    (test_ts_futuro_recusado, test_unidade_incompativel_recusada, test_grandeza_desconhecida_recusada).
  - refutação do item: isolamento entre inquilinos — publicar sob o MESMO `ativo` uuid em dois inquilinos
    nunca mistura leitura (test_inquilino_b_nunca_ve_leitura_de_a) — CLÁUSULA INEGOCIÁVEL.
  - alarme declarado "carregamento > 100% por 30 min" dispara evento só na transição, e resolve quando volta
    a <= 100% (test_alarme_dispara_e_resolve).
  - ficha do ativo: última leitura de cada grandeza + série (test_ultima_e_serie).
  - agregação a jusante pela topologia, com uma rede mínima de verdade (test_agregado_jusante_soma_trafos).
"""

import datetime
import uuid

import pytest

from tests.api.test_rede_topologia import _criar_rede, _habilitar, _importar_eletrica, _linha, _ponto

UTC = datetime.UTC


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _publicar(sessao, leituras):
    r = sessao.post("/api/rede/medicao/leituras", json={"leituras": leituras})
    assert r.status_code == 201, r.text
    return r.json()


def _leitura(ativo, ts, grandeza="corrente_a", valor=10.0, unidade="A", fonte="teste"):
    return {"ativo": ativo, "ts": _iso(ts), "fonte": fonte, "grandeza": grandeza, "valor": valor,
            "unidade": unidade}


# ---------------------------------------------------------------------- idempotência
def test_lote_idempotente_nao_duplica(sessao_a):
    ativo = str(uuid.uuid4())
    agora = datetime.datetime.now(UTC)
    r1 = _publicar(sessao_a, [_leitura(ativo, agora)])
    assert r1["aceitas"] == 1 and r1["duplicadas"] == 0

    r2 = _publicar(sessao_a, [_leitura(ativo, agora)])
    assert r2["aceitas"] == 0 and r2["duplicadas"] == 1

    # o MESMO lote, duas vezes dentro da mesma chamada, também não duplica
    ativo2 = str(uuid.uuid4())
    r3 = _publicar(sessao_a, [_leitura(ativo2, agora), _leitura(ativo2, agora)])
    assert r3["aceitas"] == 1 and r3["duplicadas"] == 1

    r = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/serie", params={"grandeza": "corrente_a", "dias": 1})
    assert r.status_code == 200, r.text
    assert r.json()["n"] == 1


# ---------------------------------------------------------------------- refutação: recusa honesta
def test_ts_futuro_recusado_com_mensagem(sessao_a):
    ativo = str(uuid.uuid4())
    futuro = datetime.datetime.now(UTC) + datetime.timedelta(hours=6)
    r = _publicar(sessao_a, [_leitura(ativo, futuro)])
    assert r["aceitas"] == 0
    assert len(r["rejeitadas"]) == 1
    rej = r["rejeitadas"][0]
    assert rej["erro"] == "ts_futuro" and rej["mensagem"]


def test_grandeza_desconhecida_recusada_com_mensagem(sessao_a):
    ativo = str(uuid.uuid4())
    r = _publicar(sessao_a, [_leitura(ativo, datetime.datetime.now(UTC), grandeza="vazao_gas", unidade="m3")])
    assert r["aceitas"] == 0
    rej = r["rejeitadas"][0]
    assert rej["erro"] == "grandeza_desconhecida" and rej["mensagem"]


def test_unidade_incompativel_recusada_com_mensagem(sessao_a):
    ativo = str(uuid.uuid4())
    r = _publicar(sessao_a, [_leitura(ativo, datetime.datetime.now(UTC), grandeza="corrente_a", unidade="V")])
    assert r["aceitas"] == 0
    rej = r["rejeitadas"][0]
    assert rej["erro"] == "unidade_incompativel" and "corrente_a" in rej["mensagem"]


def test_carregamento_pct_nao_pode_ser_publicado_de_fora(sessao_a):
    """carregamento_pct é DERIVADA — só o motor de alarme escreve; publicar de fora é grandeza desconhecida
    (tipo != 'bruto'), não um erro de servidor."""
    ativo = str(uuid.uuid4())
    r = _publicar(sessao_a, [_leitura(ativo, datetime.datetime.now(UTC), grandeza="carregamento_pct",
                                      unidade="%", valor=120)])
    assert r["aceitas"] == 0 and r["rejeitadas"][0]["erro"] == "grandeza_desconhecida"


def test_lote_vazio_ou_mal_formado_rejeitado_pelo_pydantic(sessao_a):
    r = sessao_a.post("/api/rede/medicao/leituras", json={"leituras": []})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- isolamento entre inquilinos
def test_inquilino_b_nunca_ve_leitura_de_a(sessao_a, sessao_b):
    ativo = str(uuid.uuid4())  # MESMO uuid nos dois inquilinos, de propósito — é o pior caso
    agora = datetime.datetime.now(UTC)
    _publicar(sessao_a, [_leitura(ativo, agora, valor=111.0)])
    _publicar(sessao_b, [_leitura(ativo, agora, valor=222.0)])

    ra = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/ultimas")
    rb = sessao_b.get(f"/api/rede/medicao/ativos/{ativo}/ultimas")
    assert ra.status_code == 200 and rb.status_code == 200

    leituras_a = {leit["grandeza"]: leit for leit in ra.json()["leituras"]}
    leituras_b = {leit["grandeza"]: leit for leit in rb.json()["leituras"]}
    assert leituras_a["corrente_a"]["valor"] == 111.0
    assert leituras_b["corrente_a"]["valor"] == 222.0

    # série: A não enxerga o ponto de B nem vice-versa
    sa = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/serie", params={"grandeza": "corrente_a", "dias": 1})
    sb = sessao_b.get(f"/api/rede/medicao/ativos/{ativo}/serie", params={"grandeza": "corrente_a", "dias": 1})
    assert sa.json()["n"] == 1 and sa.json()["pontos"][0]["valor"] == 111.0
    assert sb.json()["n"] == 1 and sb.json()["pontos"][0]["valor"] == 222.0

    # placa: B cadastra a placa do MESMO ativo, A continua sem ver placa nenhuma
    r = sessao_b.put(f"/api/rede/medicao/ativos/{ativo}", json={"kva_nominal": 30, "tensao_nominal_v": 380})
    assert r.status_code == 200, r.text
    assert sessao_a.get(f"/api/rede/medicao/ativos/{ativo}").json()["placa_cadastrada"] is False
    assert sessao_b.get(f"/api/rede/medicao/ativos/{ativo}").json()["placa_cadastrada"] is True


# ---------------------------------------------------------------------- ficha do ativo
def test_ultima_e_serie(sessao_a):
    ativo = str(uuid.uuid4())
    agora = datetime.datetime.now(UTC)
    velha = agora - datetime.timedelta(days=2)
    _publicar(sessao_a, [
        _leitura(ativo, velha, grandeza="corrente_a", valor=10.0),
        _leitura(ativo, agora, grandeza="corrente_a", valor=20.0),
        _leitura(ativo, agora, grandeza="temperatura", valor=35.5, unidade="C"),
    ])
    r = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/ultimas")
    leituras = {leit["grandeza"]: leit for leit in r.json()["leituras"]}
    assert leituras["corrente_a"]["valor"] == 20.0  # a mais recente, não a mais velha
    assert leituras["temperatura"]["valor"] == 35.5

    r = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/serie", params={"grandeza": "corrente_a", "dias": 7})
    assert r.json()["n"] == 2
    r = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/serie", params={"grandeza": "corrente_a", "dias": 1})
    assert r.json()["n"] == 1  # a leitura de 2 dias atrás sai da janela de 1 dia


# ---------------------------------------------------------------------- alarme declarado
def _publicar_corrente_3fases(sessao, ativo, ts, i_por_fase):
    _publicar(sessao, [_leitura(ativo, ts, grandeza=f"corrente_{f}", valor=i_por_fase) for f in "abc"])


def test_alarme_dispara_e_resolve(sessao_a):
    ativo = str(uuid.uuid4())
    r = sessao_a.put(f"/api/rede/medicao/ativos/{ativo}", json={"kva_nominal": 15, "tensao_nominal_v": 380})
    assert r.status_code == 200, r.text
    # 15 kVA / (√3 x 380V) ≈ 22,8 A é a corrente nominal; 40 A por fase é bem acima de 100%
    agora = datetime.datetime.now(UTC)
    inicio = agora - datetime.timedelta(minutes=35)
    t = inicio
    while t <= agora:
        _publicar_corrente_3fases(sessao_a, ativo, t, 40.0)
        t += datetime.timedelta(minutes=5)
    # a última publicação já respondeu com o alarme (rota publica -> avalia na mesma chamada)
    r = sessao_a.get("/api/eventos", params={"tipo": "rede_medicao/alarme_disparado"})
    assert r.status_code == 200, r.text
    disparos = [e for e in r.json()["itens"] if e["alvo_id"] == ativo]
    assert len(disparos) == 1, "o alarme dispara UMA vez na transição, não uma vez por leitura"

    r = sessao_a.get(f"/api/rede/medicao/ativos/{ativo}/ultimas")
    carregamento = next(leit for leit in r.json()["leituras"] if leit["grandeza"] == "carregamento_pct")
    assert carregamento["valor"] > 100

    # volta ao normal: publica uma corrente baixa e o alarme resolve
    _publicar_corrente_3fases(sessao_a, ativo, agora + datetime.timedelta(minutes=1), 5.0)
    r = sessao_a.get("/api/eventos", params={"tipo": "rede_medicao/alarme_resolvido"})
    resolvidos = [e for e in r.json()["itens"] if e["alvo_id"] == ativo]
    assert len(resolvidos) == 1


def test_alarme_nao_dispara_antes_de_30_min_continuos(sessao_a):
    ativo = str(uuid.uuid4())
    sessao_a.put(f"/api/rede/medicao/ativos/{ativo}", json={"kva_nominal": 15, "tensao_nominal_v": 380})
    agora = datetime.datetime.now(UTC)
    inicio = agora - datetime.timedelta(minutes=15)  # só 15 min de surto, < 30
    t = inicio
    while t <= agora:
        _publicar_corrente_3fases(sessao_a, ativo, t, 40.0)
        t += datetime.timedelta(minutes=5)
    r = sessao_a.get("/api/eventos", params={"tipo": "rede_medicao/alarme_disparado"})
    disparos = [e for e in r.json()["itens"] if e["alvo_id"] == ativo]
    assert disparos == []


# ---------------------------------------------------------------------- agregação a jusante
@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def test_agregado_jusante_soma_trafos(sessao_a, limpar_redes):
    """Rede mínima: um dispositivo na RAIZ (o ponto de partida do traçado — `_resolver_ponto` só resolve
    feicao_id de DISPOSITIVO, nunca de trecho solto) com um trecho MT descendo até um segundo trafo. Jusante
    da raiz soma a leitura mais recente de `grandeza` dos trafos alcançados, SEM contar a própria raiz."""
    rid = _criar_rede(sessao_a, "medicao-jusante", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    trafo_raiz = _ponto(sessao_a, rid, -47.0, -22.0, "transformador_de_distribuicao", 1)
    _linha(sessao_a, rid, [[-47.0, -22.0], [-47.0, -22.01]])
    _linha(sessao_a, rid, [[-47.0, -22.01], [-47.0, -22.02]])
    trafo_jusante = _ponto(sessao_a, rid, -47.0, -22.02, "transformador_de_distribuicao", 1)
    _habilitar(sessao_a, rid)

    for trafo, valor in ((trafo_raiz, 30.0), (trafo_jusante, 50.0)):
        r = sessao_a.put(f"/api/rede/medicao/ativos/{trafo['id']}",
                         json={"kva_nominal": 45, "tensao_nominal_v": 380})
        assert r.status_code == 200, r.text
        _publicar(sessao_a, [_leitura(trafo["id"], datetime.datetime.now(UTC), valor=valor)])

    # trafo tem 2 terminais na MESMA coordenada (alta=1, baixa=2); a topologia liga o trecho ao terminal 1
    # (medido: `rede_topo_aresta.no_origem_id` é sempre o nó do terminal_num=1 quando os dois terminais
    # colidem no mesmo ponto) — terminal 2 fica órfão, então o ponto de partida do traçado é o 1
    r = sessao_a.get("/api/rede/medicao/jusante", params={
        "rede_id": rid, "ativo": trafo_raiz["id"], "grandeza": "corrente_a", "terminal": 1,
    })
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["trafos_a_jusante"] == 1
    assert corpo["ids"] == [trafo_jusante["id"]]
    assert corpo["trafos_com_leitura"] == 1
    assert corpo["soma"] == 50.0
    assert corpo["unidade"] == "A"
