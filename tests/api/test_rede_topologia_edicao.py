"""Refutação do item L4-01-b-topologia-derivada: applyEdits, área suja e traçado.

Prova o roteiro exigido ao adversário, passo a passo:
1. desloca um vértice em 0,10 m via applyEdits → a topologia MARCA área suja (motivo 'edicao', polígono no
   lugar certo) e, depois do `habilitar` seguinte, o traçado a partir de um lado NÃO atravessa para o outro
   (0,10 m > tolerância padrão de 0,05 m — o trecho editado ficou desconectado de verdade);
2. enquanto a área suja está aberta, o traçado avisa que atravessa índice possivelmente velho
   (`atravessa_area_suja`) — nunca devolve resultado fingindo confiança;
3. criação e remoção de feição sobre topologia construída também marcam área suja ('criacao'/'remocao');
4. applyEdits com item inválido no lote: a falha fica no item (success: false) e o lote continua.

Os cenários de cruzamento sem nó (não conecta) e de contagem de grau 1 na escala real estão em
`test_rede_topologia.py` e `test_rede_topologia_medida.py`, respectivamente.
"""

import pytest

from tests.api.test_rede_topologia import (
    _criar_rede,
    _habilitar,
    _importar_eletrica,
    _linha,
    _ponto,
    _projetar,
)


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def _apply_linhas(sessao, rid, corpo):
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _alcance(sessao, rid, no_id):
    r = sessao.get(f"/api/rede/{rid}/topologia/alcance", params={"no": no_id})
    assert r.status_code == 200, r.text
    return r.json()


def _no_em(sessao, rid, lon, lat, delta=1e-6):
    """O nó da topologia MAIS PRÓXIMO de (lon, lat) — achado por coordenada, nunca por ordem de criação.
    Mais próximo, não "primeiro dentro do delta": dois nós podem cair no mesmo delta (é o caso do vértice
    deslocado 0,10 m, a ~9e-7 grau do nó antigo) e o teste precisa do nó certo, não de um dos dois."""
    nos = sessao.get(f"/api/rede/{rid}/topologia/nos", params={"limite": 2000}).json()["itens"]
    candidatos = [n for n in nos if abs(n["lon"] - lon) < delta and abs(n["lat"] - lat) < delta]
    assert candidatos, f"nenhum nó em ({lon}, {lat}); nós: {[(n['lon'], n['lat']) for n in nos]}"
    return min(candidatos, key=lambda n: (n["lon"] - lon) ** 2 + (n["lat"] - lat) ** 2)


def _montar_cadeia(sessao, rid, limpar):
    """Três trechos de MT em cadeia A—B—C—D (4 nós, 3 arestas). Devolve os ids das 3 linhas e os 4 pontos."""
    a, b, c, d = (-47.50, -16.00), (-47.49, -16.00), (-47.48, -16.00), (-47.47, -16.00)
    l1 = _linha(sessao, rid, [a, b])
    l2 = _linha(sessao, rid, [b, c])
    l3 = _linha(sessao, rid, [c, d])
    resumo = _habilitar(sessao, rid)
    assert resumo["nos"] == 4 and resumo["arestas"] == 3, resumo
    return [l1, l2, l3], (a, b, c, d)


def test_applyedits_desloca_010m_marca_area_suja_e_tracado_nao_atravessa(sessao_a, limpar_redes, env):
    rid = _criar_rede(sessao_a, "adv-010m", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    (l1, l2, l3), (a, b, c, d) = _montar_cadeia(sessao_a, rid, limpar_redes)

    no_a = _no_em(sessao_a, rid, *a)
    antes = _alcance(sessao_a, rid, no_a["id"])
    assert antes["nos_alcancados"] == 4 and antes["arestas_alcancadas"] == 3
    assert antes["areas_sujas_abertas"] == 0 and antes["atravessa_area_suja"] is False

    # o adversário desloca o vértice B do trecho do meio em 0,10 m para o norte — via applyEdits
    b2 = _projetar(env, b[0], b[1], 0.10, 0)
    res = _apply_linhas(sessao_a, rid, {
        "updates": [{"attributes": {"id": l2["id"]}, "geometry": {"paths": [[list(b2), list(c)]]}}],
    })
    assert res["updateResults"] == [{"id": l2["id"], "success": True}]

    # 1) a topologia marca área suja: uma área, motivo 'edicao', apontando a feição editada, cobrindo o
    # vértice velho E o novo (o envelope velho U novo expandido pela tolerância)
    sujas = sessao_a.get(f"/api/rede/{rid}/topologia/areas-sujas").json()
    assert sujas["total"] == 1, sujas
    area = sujas["itens"][0]
    assert area["motivo"] == "edicao" and area["feicao_id"] == l2["id"]
    lons = [p[0] for anel in area["geometria"]["coordinates"] for p in anel]
    lats = [p[1] for anel in area["geometria"]["coordinates"] for p in anel]
    assert min(lons) <= b[0] <= max(lons) and min(lats) <= b[1] and b2[1] <= max(lats)

    # 2) com a área suja aberta, o traçado AVISA que atravessa índice possivelmente velho
    sujo = _alcance(sessao_a, rid, no_a["id"])
    assert sujo["areas_sujas_abertas"] == 1
    assert sujo["atravessa_area_suja"] is True

    # 3) `habilitar` reconstrói: a área suja morre e o traçado NÃO atravessa — 0,10 m > tolerância 0,05 m,
    # o trecho do meio desconectou de verdade do primeiro: sobram 5 nós (A, B, B', C, D) e a ilha A—B de um
    # lado, B'—C—D do outro
    resumo2 = _habilitar(sessao_a, rid)
    assert resumo2["nos"] == 5 and resumo2["arestas"] == 3, resumo2
    assert sessao_a.get(f"/api/rede/{rid}/topologia/areas-sujas").json()["total"] == 0

    no_a_depois = _no_em(sessao_a, rid, *a)
    depois = _alcance(sessao_a, rid, no_a_depois["id"])
    assert depois["nos_alcancados"] == 2 and depois["arestas_alcancadas"] == 1, (
        f"o traçado a partir de A tinha de parar no vértice deslocado; veio {depois}")
    assert depois["atravessa_area_suja"] is False
    # e do outro lado da falha: o nó vizinho do vértice deslocado alcança C e D, mas NUNCA A
    no_b2 = _no_em(sessao_a, rid, *b2)
    outro_lado = _alcance(sessao_a, rid, no_b2["id"])
    assert outro_lado["nos_alcancados"] == 3 and outro_lado["arestas_alcancadas"] == 2


def test_applyedits_desloca_004m_continua_conectado(sessao_a, limpar_redes, env):
    """O mesmo applyEdits com 0,04 m (< tolerância): marca área suja do mesmo jeito, mas depois do
    `habilitar` a cadeia INTEIRA continua conectada — a régua é sempre a tolerância da rede."""
    rid = _criar_rede(sessao_a, "adv-004m", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    (l1, l2, l3), (a, b, c, d) = _montar_cadeia(sessao_a, rid, limpar_redes)

    b2 = _projetar(env, b[0], b[1], 0.04, 0)
    res = _apply_linhas(sessao_a, rid, {
        "updates": [{"attributes": {"id": l2["id"]}, "geometry": {"paths": [[list(b2), list(c)]]}}],
    })
    assert res["updateResults"][0]["success"] is True
    assert sessao_a.get(f"/api/rede/{rid}/topologia/areas-sujas").json()["total"] == 1

    _habilitar(sessao_a, rid)
    no_a = _no_em(sessao_a, rid, *a)
    depois = _alcance(sessao_a, rid, no_a["id"])
    assert depois["nos_alcancados"] == 4 and depois["arestas_alcancadas"] == 3


def test_criar_e_remover_feicao_sobre_topologia_construida_marca_area_suja(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "adv-motivos", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    (l1, l2, l3), _pontos = _montar_cadeia(sessao_a, rid, limpar_redes)

    novo = _ponto(sessao_a, rid, -47.40, -16.00, "transformador_de_distribuicao", 1)
    sujas = sessao_a.get(f"/api/rede/{rid}/topologia/areas-sujas").json()
    assert sujas["total"] == 1 and sujas["itens"][0]["motivo"] == "criacao"
    assert sujas["itens"][0]["feicao_id"] == novo["id"]

    res = _apply_linhas(sessao_a, rid, {"deletes": [l3["id"]]})
    assert res["deleteResults"] == [{"id": l3["id"], "success": True}]
    sujas = sessao_a.get(f"/api/rede/{rid}/topologia/areas-sujas").json()
    motivos = sorted(i["motivo"] for i in sujas["itens"])
    assert sujas["total"] == 2 and motivos == ["criacao", "remocao"]


def test_applyedits_item_invalido_fica_no_item_e_o_lote_continua(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "adv-lote", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    res = _apply_linhas(sessao_a, rid, {
        "adds": [
            {"attributes": {"grupo": "grupo_que_nao_existe", "tipo_codigo": 1},
             "geometry": {"paths": [[[-47.50, -16.0], [-47.49, -16.0]]]}},
            {"attributes": {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1},
             "geometry": {"paths": [[[-47.50, -16.0], [-47.49, -16.0]]]}},
        ],
        "updates": [{"attributes": {"id": "00000000-0000-0000-0000-000000000000"},
                     "geometry": {"paths": [[[-47.5, -16.0], [-47.49, -16.0]]]}}],
    })
    assert res["addResults"][0]["success"] is False
    assert res["addResults"][0]["error"]["code"] == 404
    assert res["addResults"][1]["success"] is True, "o segundo item do lote tinha de gravar normalmente"
    assert res["updateResults"][0]["success"] is False
    assert res["updateResults"][0]["error"]["code"] == 404
