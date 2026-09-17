"""Item L3-04-restricoes — teste do COMBINADOR `app.amc.restricao.compor` (remediação de 17/09/2026:
o combinador já existia; o que faltava era o teste do portão).

Caso calculado à mão (números escritos aqui, nunca derivados do código sob teste):

- grade de 5 unidades: u0, u1, u2, u3, u4
- r_norma (base 'norma') veta u0 e u1
- r_precaucao (base 'precaucao') veta u1 e u2   <- u1 vetada por DUAS restrições (sobreposição)
- r_fracao (base 'norma') veta u4

Composição por OU:
- unidades vetadas no total: u0, u1, u2, u4 -> 4 unidades (u1 conta UMA vez, nunca duas)
- fração vetada do total: 4/5 = 0,8
- contagem POR restrição: r_norma=2, r_precaucao=2, r_fracao=1 (soma 5 > 4: cada restrição conta
  separado, o total após o OU não)
- motivo de u1: o da PRIMEIRA restrição da lista que a vetou (r_norma -> 'a norma veda')

Veto na combinação: unidade vetada sai com favorabilidade 0 e o motivo legível vindo do metadado
('a norma veda' para base=norma, 'vetamos por precaução' para base=precaucao).

Camada vazia (refutação do adversário): restringir zero unidades em silêncio é reprovação —
`avaliar` com camada sem feições levanta ErroRestricao('camada_vazia') avisando
'camada sem feições na área'.
"""

import pytest

from app.amc import combinacao
from app.amc.restricao import ErroRestricao, avaliar, compor

IDS = ["u0", "u1", "u2", "u3", "u4"]

R_NORMA = {
    "id": "r_norma", "nome": "área protegida", "base": "norma",
    "base_legal": "Lei fictícia de teste 0/2026, art. 1º",
    "fonte": "caso calculado à mão deste teste",
    "regra": {"tipo": "intersecta"},
    "motivo": "unidade sobrepõe área protegida",
}
R_PRECAUCAO = {
    "id": "r_precaucao", "nome": "entorno de nascente", "base": "precaucao",
    "fonte": "caso calculado à mão deste teste",
    "regra": {"tipo": "intersecta"},
    "motivo": "unidade dentro da faixa de precaução",
}
R_FRACAO = {
    "id": "r_fracao", "nome": "solo inapto", "base": "norma",
    "base_legal": "Lei fictícia de teste 0/2026, art. 2º",
    "fonte": "caso calculado à mão deste teste",
    "regra": {"tipo": "fracao_area_minima", "fracao_minima": 0.5},
    "motivo": "unidade majoritariamente sobre solo inapto",
}

# resultados de `avaliar` construídos à mão, conforme o caso acima (compor é lógica pura, sem banco)
RES_NORMA = {uid: {"vetada": uid in ("u0", "u1"), "fracao_intersectada": None} for uid in IDS}
RES_PRECAUCAO = {uid: {"vetada": uid in ("u1", "u2"), "fracao_intersectada": None} for uid in IDS}
RES_FRACAO = {uid: {"vetada": uid == "u4", "fracao_intersectada": 1.0 if uid == "u4" else 0.0}
              for uid in IDS}


def _composto():
    return compor(IDS, [(R_NORMA, RES_NORMA), (R_PRECAUCAO, RES_PRECAUCAO), (R_FRACAO, RES_FRACAO)])


def test_sobreposicao_ou_nao_conta_duas_vezes_mas_contagem_por_restricao_soma_separado():
    c = _composto()
    # total após o OU: u1 vetada por duas restrições conta UMA vez
    assert c["fracao_vetada"] == [1.0, 1.0, 1.0, 0.0, 1.0]
    assert c["unidades_vetadas_total"] == 4
    # contagem por restrição: cada uma soma a sua, independente da sobreposição
    contagem = {e["id"]: e["unidades_vetadas"] for e in c["contagem_por_restricao"]}
    assert contagem == {"r_norma": 2, "r_precaucao": 2, "r_fracao": 1}
    for e in c["contagem_por_restricao"]:
        assert e["total_unidades"] == 5
    # a soma das contagens por restrição (5) é MAIOR que o total vetado (4): é a assinatura do OU
    assert sum(contagem.values()) == 5 > c["unidades_vetadas_total"]


def test_veto_zera_favorabilidade_e_motivo_vem_do_metadado():
    c = _composto()
    motivo = dict(zip(IDS, c["motivo"], strict=True))
    assert motivo["u0"].startswith("a norma veda: ")
    assert "Lei fictícia" in motivo["u0"]
    assert motivo["u1"].startswith("a norma veda: ")  # primeira da lista que vetou u1 é r_norma
    assert motivo["u2"].startswith("vetamos por precaução: ")
    assert motivo["u4"].startswith("a norma veda: ")
    assert motivo["u3"] is None

    res = combinacao.combinar(
        [[80.0]] * 5, [1.0],
        fracao_vetada=c["fracao_vetada"], motivo_veto=c["motivo"], ids_fatores=["f"],
    )
    for i, uid in enumerate(IDS):
        if uid == "u3":
            assert res.fav[i] == 80.0
            assert not res.vetado[i]
        else:
            assert res.fav[i] == 0.0
            assert bool(res.vetado[i]) is True
            assert res.motivo[i] == motivo[uid]


def test_fracao_vetada_contra_caso_calculado_a_mao():
    c = _composto()
    fracao_total = c["unidades_vetadas_total"] / len(IDS)
    assert fracao_total == pytest.approx(0.8)  # 4 de 5 unidades vetadas, número escrito à mão


def test_camada_vazia_avisa_em_vez_de_vetar_zero_em_silencio(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(ErroRestricao) as e:
            avaliar(cur, [("u0", {"type": "Point", "coordinates": [-47.9, -15.8]})], [], R_NORMA)
    assert e.value.codigo == "camada_vazia"
    assert "camada sem feições na área" in e.value.mensagem
