"""Motor de avaliação de regras de conectividade (item L4-03-a-regras-de-conectividade), sem banco: só as
funções puras de `app/rede_utilidades/regras.py` contra listas de `Regra` montadas à mão, e a contagem do
pacote elétrico instalado (cláusula do portão: "pacote elétrica-BR traz ≥ 40 regras")."""

import json
from pathlib import Path

from app.rede_utilidades.regras import (
    Regra,
    Violacao,
    avaliar_associacao,
    avaliar_eje,
    avaliar_je,
    avaliar_jj,
    regra_json,
    texto_regra,
)

RAIZ = Path(__file__).resolve().parents[2]
PACOTE_ELETRICO = RAIZ / "app" / "rede_utilidades" / "pacotes" / "eletrica-br.json"


# ------------------------------------------------------------------------------------------- contagem do pacote

def test_pacote_eletrica_br_tem_pelo_menos_40_regras():
    doc = json.loads(PACOTE_ELETRICO.read_text(encoding="utf-8"))
    regras = doc["regras"]
    assert len(regras) >= 40, f"portão pede ≥ 40 regras; o pacote tem {len(regras)}"
    tipos = {r["tipo"] for r in regras}
    assert tipos == {"juncao_juncao", "juncao_aresta", "aresta_juncao_aresta", "contencao", "estrutura"}, tipos


def test_pacote_eletrica_br_tem_a_regra_do_exemplo_do_portao():
    """"trecho MT só liga a trafo pelo terminal AT" — o exemplo textual do próprio portão do item."""
    doc = json.loads(PACOTE_ELETRICO.read_text(encoding="utf-8"))
    achada = [
        r for r in doc["regras"]
        if r["tipo"] == "juncao_aresta" and r["de"]["grupo"] == "transformador_de_distribuicao"
        and r["de"].get("terminal") == "alta" and r["para"]["grupo"] == "trecho_de_media_tensao"
    ]
    assert achada, "falta a regra de terminal alta do transformador para o trecho de MT"
    assert not any(
        r["tipo"] == "juncao_aresta" and r["de"]["grupo"] == "transformador_de_distribuicao"
        and r["de"].get("terminal") == "baixa" and r["para"]["grupo"] == "trecho_de_media_tensao"
        for r in doc["regras"]
    ), "o terminal baixa do transformador não pode ligar ao trecho de MT (é o de BT)"


# ------------------------------------------------------------------------------------------------- avaliar_je

TRAFO = ("transformador_de_distribuicao", 1)
MT = ("trecho_de_media_tensao", 1)
BT = ("trecho_de_baixa_tensao", 1)
UC_BT = ("unidade_consumidora", 1)


def _regras_basicas() -> list[Regra]:
    return [
        Regra(id="r1", tipo="juncao_aresta", de=TRAFO, para=MT, de_terminal="alta"),
        Regra(id="r2", tipo="juncao_aresta", de=TRAFO, para=BT, de_terminal="baixa"),
    ]


def test_avaliar_je_aceita_terminal_certo():
    r, v = avaliar_je(_regras_basicas(), TRAFO, MT, "alta", ["f1", "f2"])
    assert v is None and r.id == "r1"


def test_avaliar_je_recusa_terminal_errado_e_cita_a_regra_candidata():
    r, v = avaliar_je(_regras_basicas(), TRAFO, MT, "baixa", ["f1", "f2"])
    assert r is None
    assert v.codigo == "terminal_errado"
    assert "alta" in v.mensagem  # a mensagem cita o terminal exigido pela regra
    assert v.candidatas and v.candidatas[0]["id"] == "r1"


def test_avaliar_je_recusa_sem_terminal_declarado():
    r, v = avaliar_je(_regras_basicas(), TRAFO, MT, None, ["f1"])
    assert r is None and v.codigo == "terminal_errado"


def test_avaliar_je_sem_regra_para_o_par_cita_sem_regra_e_nao_tem_candidata():
    """O exemplo do portão: trecho de MT ligado direto a UC de BT (sem ramal) não tem regra nenhuma."""
    r, v = avaliar_je(_regras_basicas(), UC_BT, MT, "conexao", ["fA", "fB"])
    assert r is None
    assert v.codigo == "sem_regra"
    assert "sem regra = proibido" in v.mensagem
    assert v.candidatas == []
    assert v.json()["feicoes"] == ["fA", "fB"]
    assert "regras_candidatas" not in v.json()


def test_texto_regra_juncao_aresta_com_e_sem_terminal():
    com = Regra(id="x", tipo="juncao_aresta", de=TRAFO, para=MT, de_terminal="alta")
    sem = Regra(id="y", tipo="juncao_aresta", de=TRAFO, para=MT)
    assert "pelo terminal 'alta'" in texto_regra(com)
    assert "sem terminal" in texto_regra(sem)


def test_regra_json_leva_terminal_so_quando_declarado():
    com = Regra(id="x", tipo="juncao_aresta", de=TRAFO, para=MT, de_terminal="alta", descricao="d")
    j = regra_json(com)
    assert j["de"]["terminal"] == "alta" and "terminal" not in j["para"]
    assert j["descricao"] == "d"


# ------------------------------------------------------------------------------------------------- avaliar_jj

POSTE = ("ponto_notavel", 1)
CHAVE = ("chave_de_media_tensao", 1)


def test_avaliar_jj_par_nao_ordenado():
    regras = [Regra(id="j1", tipo="juncao_juncao", de=POSTE, para=CHAVE)]
    r1, v1 = avaliar_jj(regras, POSTE, CHAVE, ["a", "b"])
    r2, v2 = avaliar_jj(regras, CHAVE, POSTE, ["a", "b"])
    assert r1 is not None and r2 is not None and r1.id == r2.id == "j1"
    assert v1 is None and v2 is None


def test_avaliar_jj_sem_regra():
    r, v = avaliar_jj([], POSTE, CHAVE, ["a", "b"])
    assert r is None and v.codigo == "sem_regra" and "juncao_juncao" in v.mensagem


# ---------------------------------------------------------------------------------------------- avaliar_eje

RAMAL = ("ramal_de_ligacao", 1)


def test_avaliar_eje_via_e_o_meio_pontas_nao_ordenadas():
    regras = [Regra(id="e1", tipo="aresta_juncao_aresta", de=MT, para=BT, via=POSTE)]
    r1, v1 = avaliar_eje(regras, MT, POSTE, BT, ["a"])
    r2, v2 = avaliar_eje(regras, BT, POSTE, MT, ["a"])
    assert r1 is not None and r2 is not None and r1.id == r2.id
    assert v1 is None and v2 is None


def test_avaliar_eje_sem_regra_cita_a_juncao_do_meio():
    r, v = avaliar_eje([], MT, POSTE, RAMAL, ["a"])
    assert r is None
    assert v.codigo == "sem_regra"
    assert "ponto_notavel/1" in v.mensagem


# ---------------------------------------------------------------------------------------- avaliar_associacao

def test_avaliar_associacao_e_direcional():
    regras = [Regra(id="c1", tipo="contencao", de=POSTE, para=TRAFO)]
    r_ok, v_ok = avaliar_associacao(regras, "contencao", POSTE, TRAFO, ["p", "t"])
    r_inv, v_inv = avaliar_associacao(regras, "contencao", TRAFO, POSTE, ["p", "t"])
    assert r_ok is not None and v_ok is None
    assert r_inv is None and v_inv.codigo == "sem_regra"
    assert "contenção" in v_inv.mensagem


def test_avaliar_associacao_estrutura_rotulo_diferente_de_contencao():
    r, v = avaliar_associacao([], "estrutura", POSTE, TRAFO, ["p", "t"])
    assert v.codigo == "sem_regra" and "fixação estrutural" in v.mensagem


def test_violacao_json_agrupa_candidatas_so_quando_existem():
    v_sem = Violacao("sem_regra", "m", ["a"])
    v_com = Violacao("terminal_errado", "m", ["a"], [{"id": "r1"}])
    assert "regras_candidatas" not in v_sem.json()
    assert v_com.json()["regras_candidatas"] == [{"id": "r1"}]
