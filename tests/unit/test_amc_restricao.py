"""Item L3-04-restricoes: restrição como objeto próprio do motor multicritério.

Cláusulas do portão provadas aqui:
- 3 restrições encadeadas sobre grade de teste, com a contagem de unidades vetadas por CADA restrição
  batendo com uma recomputação independente por `ST_Intersects` puro (nunca reaproveitando
  `app.amc.restricao`, sempre uma consulta escrita à mão neste arquivo);
- o buffer é geográfico: uma restrição com `buffer_m` é conferida contra `ST_DWithin(geography, ...)`
  calculado de novo, fora do módulo;
- o relatório escreve a frase certa a partir só do metadado (`base`): "a norma veda" para `base=norma`,
  "vetamos por precaução" para `base=precaucao`;
- e2e: as 3 restrições avaliadas, compostas por OU (`app.amc.restricao.compor`) e passadas para
  `app.amc.combinacao.combinar` — a unidade vetada sai com favorabilidade 0 e o motivo da PRIMEIRA
  restrição da lista que a vetou.

Refutação (adversário do item, também aqui): buffer 0 é aceito (deixa de exigir distância, vira
interseção pura); buffer negativo é recusado com mensagem clara; camada sem nenhuma feição na área
nunca veta silenciosamente — `avaliar` levanta `ErroRestricao('camada_vazia', ...)`.

Sem tenant/RLS: a avaliação de restrição é cálculo puro sobre geometrias literais (nunca lê tabela do
inquilino), então a conexão usada aqui é a mesma `conexao_plat_app` de `tests/conftest.py`, sem contexto
de sessão — só para ter um cursor Postgres/PostGIS de verdade.
"""

import json

import pytest

from app.amc import combinacao
from app.amc.restricao import ErroRestricao, avaliar, compor, frase_motivo, validar_restricao

# grade de teste: 5 quadrados de 100 m de lado, num carreiro ao longo do eixo x, longe o bastante um do
# outro (300 m de centro a centro) para que os buffers usados não fundam unidades vizinhas sem querer.
_ORIGEM = (-47.900000, -15.800000)  # perto do equador em latitude não é preciso; só precisa estar no BR
_LADO = 100.0  # "graus" fictícios não seriam geodésicos — as unidades abaixo já nascem em graus reais
_PASSO_M = 300.0
# 1 grau de longitude ~ 111.320 km * cos(lat) no equador; a -15.8° cos ~ 0.9626 -> usa-se conversão real
# via ST_DWithin/ST_Area (geography) no próprio teste, nunca aproximação de grau fixo.


def _quadrado_metros(cx_m: float, cy_m: float, lado_m: float) -> dict:
    """Quadrado pequeno (metros) transformado para graus por um deslocamento aproximado, só para ESPALHAR
    as unidades de teste; a métrica que importa (distância, área) é sempre recomputada em geography, nunca
    assumida a partir deste deslocamento."""
    lon0, lat0 = _ORIGEM
    m_por_grau_lat = 111_320.0
    m_por_grau_lon = 111_320.0 * 0.96  # cos(-15.8°) aproximado só para posicionar, não para medir
    dx = lado_m / 2.0 / m_por_grau_lon
    dy = lado_m / 2.0 / m_por_grau_lat
    cx = lon0 + cx_m / m_por_grau_lon
    cy = lat0 + cy_m / m_por_grau_lat
    return {
        "type": "Polygon",
        "coordinates": [[[cx - dx, cy - dy], [cx + dx, cy - dy], [cx + dx, cy + dy],
                          [cx - dx, cy + dy], [cx - dx, cy - dy]]],
    }


def _unidades(n: int = 5) -> list[tuple[str, dict]]:
    return [(f"u{i}", _quadrado_metros(i * _PASSO_M, 0.0, _LADO)) for i in range(n)]


def _ponto_metros(x_m: float, y_m: float) -> dict:
    lon0, lat0 = _ORIGEM
    m_por_grau_lat = 111_320.0
    m_por_grau_lon = 111_320.0 * 0.96
    return {"type": "Point", "coordinates": [lon0 + x_m / m_por_grau_lon, lat0 + y_m / m_por_grau_lat]}


# ---------------------------------------------------------------- recomputação independente (fora do módulo)
def _st_intersects_independente(cur, unidades, feicoes) -> dict[str, bool]:
    saida = {}
    for uid, g in unidades:
        vetada = False
        for _fid, fg, _attr in feicoes:
            cur.execute(
                "SELECT ST_Intersects(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326), "
                "ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) AS toca",
                (json.dumps(g), json.dumps(fg)),
            )
            if cur.fetchone()["toca"]:
                vetada = True
                break
        saida[uid] = vetada
    return saida


def _st_dwithin_geography_independente(cur, unidades, feicoes, buffer_m: float) -> dict[str, bool]:
    saida = {}
    for uid, g in unidades:
        vetada = False
        for _fid, fg, _attr in feicoes:
            cur.execute(
                "SELECT ST_DWithin(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)::geography, "
                "ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)::geography, %s) AS perto",
                (json.dumps(g), json.dumps(fg), buffer_m),
            )
            if cur.fetchone()["perto"]:
                vetada = True
                break
        saida[uid] = vetada
    return saida


# ---------------------------------------------------------------- fixtures de restrição
def _restricao_norma_intersecta() -> dict:
    """Veta u0 e u1: um polígono cobrindo de -50 a 350 m no eixo x (intersecta u0 em 0 m e chega perto de
    u1 em 300 m, mas sem o cobrir inteiro — a interseção pura ainda toca a borda)."""
    return {
        "id": "r_uc", "nome": "área protegida de teste", "base": "norma",
        "base_legal": "Lei fictícia de teste 0/2026, art. 1º",
        "fonte": "camada sintética do item L3-04-restricoes",
        "camada": {"tipo": "item", "id": "camada-uc-teste"},
        "buffer_m": 0,
        "regra": {"tipo": "intersecta"},
        "motivo": "unidade sobrepõe área protegida de teste",
    }


def _restricao_precaucao_buffer() -> dict:
    """Veta por proximidade (buffer geográfico): ponto em x=700 m, buffer de 100 m. Só alcança u2 (range
    550-650 m; distância ao ponto = 50 m); u3 (range 850-950 m; distância = 150 m) fica de fora com
    folga clara acima do limiar."""
    return {
        "id": "r_ponto", "nome": "ponto de precaução", "base": "precaucao",
        "fonte": "camada sintética do item L3-04-restricoes",
        "camada": {"tipo": "item", "id": "camada-ponto-teste"},
        "buffer_m": 100.0,
        "regra": {"tipo": "intersecta"},
        "motivo": "unidade a menos de 100 m do ponto de precaução",
    }


def _restricao_fracao_area() -> dict:
    """Veta por fração de área mínima: um polígono grande cobrindo inteiramente u4 (fração 1,0 >= 0,5)."""
    return {
        "id": "r_fracao", "nome": "camada de fração de teste", "base": "norma",
        "base_legal": "Lei fictícia de teste 0/2026, art. 2º",
        "fonte": "camada sintética do item L3-04-restricoes",
        "camada": {"tipo": "item", "id": "camada-fracao-teste"},
        "buffer_m": 0,
        "regra": {"tipo": "fracao_area_minima", "fracao_minima": 0.5},
        "motivo": "unidade majoritariamente coberta pela camada de fração de teste",
    }


@pytest.fixture
def cur(conexao_plat_app):
    with conexao_plat_app.cursor() as c:
        yield c


def test_restricao_intersecta_bate_com_st_intersects_independente(cur):
    unidades = _unidades()
    # feição única: retângulo de -50 a 350 m em x, toda a faixa y — toca u0 (0 m) e u1 (300 m)
    feicoes = [("f0", {
        "type": "Polygon",
        "coordinates": [[
            [_ORIGEM[0] + (-50 / (111_320.0 * 0.96)), _ORIGEM[1] - 0.01],
            [_ORIGEM[0] + (350 / (111_320.0 * 0.96)), _ORIGEM[1] - 0.01],
            [_ORIGEM[0] + (350 / (111_320.0 * 0.96)), _ORIGEM[1] + 0.01],
            [_ORIGEM[0] + (-50 / (111_320.0 * 0.96)), _ORIGEM[1] + 0.01],
            [_ORIGEM[0] + (-50 / (111_320.0 * 0.96)), _ORIGEM[1] - 0.01],
        ]],
    }, None)]

    restricao = _restricao_norma_intersecta()
    resultado = avaliar(cur, unidades, feicoes, restricao)
    esperado = _st_intersects_independente(cur, unidades, feicoes)
    obtido = {uid: r["vetada"] for uid, r in resultado.items()}
    assert obtido == esperado
    assert obtido["u0"] is True
    assert obtido["u4"] is False


def test_buffer_geografico_bate_com_st_dwithin_independente(cur):
    unidades = _unidades()
    ponto = [("p0", _ponto_metros(700.0, 0.0), None)]
    restricao = _restricao_precaucao_buffer()
    resultado = avaliar(cur, unidades, ponto, restricao)
    esperado = _st_dwithin_geography_independente(cur, unidades, ponto, 100.0)
    obtido = {uid: r["vetada"] for uid, r in resultado.items()}
    assert obtido == esperado
    assert obtido["u2"] is True  # borda de u2 a 650 m, ponto em 700 m -> 50 m de distância (buffer 100 m)
    assert obtido["u3"] is False  # borda de u3 a 850 m, ponto em 700 m -> 150 m (folga clara acima do buffer)
    assert obtido["u0"] is False
    assert obtido["u4"] is False


def test_fracao_area_minima_veta_pela_fracao(cur):
    unidades = _unidades()
    # polígono grande o bastante para cobrir u4 (1.200 m) inteiramente
    grande = _quadrado_metros(1_200.0, 0.0, 500.0)
    feicoes = [("f0", grande, None)]
    restricao = _restricao_fracao_area()
    resultado = avaliar(cur, unidades, feicoes, restricao)
    assert resultado["u4"]["vetada"] is True
    assert resultado["u4"]["fracao_intersectada"] == pytest.approx(1.0, abs=0.02)
    assert resultado["u0"]["vetada"] is False
    assert resultado["u0"]["fracao_intersectada"] == pytest.approx(0.0, abs=1e-6)


def test_tres_restricoes_encadeadas_composicao_por_ou_e_relatorio(cur):
    unidades = _unidades()
    ids = [u[0] for u in unidades]

    feicoes_uc = [("f0", {
        "type": "Polygon",
        "coordinates": [[
            [_ORIGEM[0] + (-50 / (111_320.0 * 0.96)), _ORIGEM[1] - 0.01],
            [_ORIGEM[0] + (350 / (111_320.0 * 0.96)), _ORIGEM[1] - 0.01],
            [_ORIGEM[0] + (350 / (111_320.0 * 0.96)), _ORIGEM[1] + 0.01],
            [_ORIGEM[0] + (-50 / (111_320.0 * 0.96)), _ORIGEM[1] + 0.01],
            [_ORIGEM[0] + (-50 / (111_320.0 * 0.96)), _ORIGEM[1] - 0.01],
        ]],
    }, None)]
    feicoes_ponto = [("p0", _ponto_metros(700.0, 0.0), None)]
    feicoes_fracao = [("f1", _quadrado_metros(1_200.0, 0.0, 500.0), None)]

    r_uc = _restricao_norma_intersecta()
    r_ponto = _restricao_precaucao_buffer()
    r_fracao = _restricao_fracao_area()

    avaliacoes = [
        (r_uc, avaliar(cur, unidades, feicoes_uc, r_uc)),
        (r_ponto, avaliar(cur, unidades, feicoes_ponto, r_ponto)),
        (r_fracao, avaliar(cur, unidades, feicoes_fracao, r_fracao)),
    ]
    composto = compor(ids, avaliacoes)

    # contagem por restrição, independente da composição por OU
    contagem = {c["id"]: c["unidades_vetadas"] for c in composto["contagem_por_restricao"]}
    assert contagem["r_uc"] == 2       # u0, u1
    assert contagem["r_ponto"] == 1    # u2
    assert contagem["r_fracao"] == 1   # u4

    # OU: u0,u1,u2,u4 vetadas; u3 livre
    fracao_vetada = dict(zip(ids, composto["fracao_vetada"], strict=True))
    assert fracao_vetada["u0"] == 1.0
    assert fracao_vetada["u1"] == 1.0
    assert fracao_vetada["u2"] == 1.0
    assert fracao_vetada["u3"] == 0.0
    assert fracao_vetada["u4"] == 1.0
    assert composto["unidades_vetadas_total"] == 4

    motivo = dict(zip(ids, composto["motivo"], strict=True))
    assert motivo["u0"].startswith("a norma veda")           # r_uc é 'norma'
    assert motivo["u2"].startswith("vetamos por precaução")  # r_ponto é 'precaucao'
    assert motivo["u4"].startswith("a norma veda")           # r_fracao é 'norma'
    assert motivo["u3"] is None

    # e2e: a combinação zera a nota das unidades vetadas e carrega o motivo
    n = len(ids)
    fatores = [[80.0] for _ in range(n)]  # um fator qualquer, mesma nota para todo mundo
    res = combinacao.combinar(
        fatores, [1.0], fracao_vetada=composto["fracao_vetada"], motivo_veto=composto["motivo"],
        ids_fatores=["f_qualquer"],
    )
    for i, uid in enumerate(ids):
        if fracao_vetada[uid] >= 1.0:
            assert res.fav[i] == 0.0
            assert res.vetado[i] is True or bool(res.vetado[i]) is True
            assert res.motivo[i] == motivo[uid]
        else:
            assert res.fav[i] == 80.0
            assert not res.vetado[i]


def test_frase_motivo_norma_e_precaucao():
    assert frase_motivo(_restricao_norma_intersecta()).startswith("a norma veda: ")
    assert "Lei fictícia" in frase_motivo(_restricao_norma_intersecta())
    assert frase_motivo(_restricao_precaucao_buffer()).startswith("vetamos por precaução: ")


def test_frase_motivo_recusa_base_desconhecida():
    ruim = dict(_restricao_norma_intersecta())
    ruim["base"] = "desconhecida"
    with pytest.raises(ErroRestricao) as e:
        frase_motivo(ruim)
    assert e.value.codigo == "base_desconhecida"


# ---------------------------------------------------------------- refutação do adversário
def test_buffer_zero_e_aceito_como_interseccao_pura():
    r = dict(_restricao_norma_intersecta())
    r["buffer_m"] = 0
    validar_restricao(r)  # não levanta


def test_buffer_negativo_e_recusado():
    r = dict(_restricao_norma_intersecta())
    r["buffer_m"] = -10.0
    with pytest.raises(ErroRestricao) as e:
        validar_restricao(r)
    assert e.value.codigo == "buffer_negativo"


def test_camada_vazia_nunca_veta_em_silencio(cur):
    unidades = _unidades()
    restricao = _restricao_norma_intersecta()
    with pytest.raises(ErroRestricao) as e:
        avaliar(cur, unidades, [], restricao)
    assert e.value.codigo == "camada_vazia"
    assert "sem feições na área" in e.value.mensagem


def test_regra_desconhecida_e_recusada():
    r = dict(_restricao_norma_intersecta())
    r["regra"] = {"tipo": "voo_de_passaro"}
    with pytest.raises(ErroRestricao) as e:
        validar_restricao(r)
    assert e.value.codigo == "regra_desconhecida"


def test_valor_raster_fora_do_escopo_e_declarado():
    r = dict(_restricao_norma_intersecta())
    r["regra"] = {"tipo": "valor_raster"}
    with pytest.raises(ErroRestricao) as e:
        validar_restricao(r)
    assert e.value.codigo == "regra_nao_suportada"


# ---------------------------------------------------------------- composição por OU, sem banco (lógica pura)
def test_compor_por_ou_sem_banco_motivo_da_primeira_que_vetou():
    """`compor` é pura (não abre cursor): confere a lógica de composição isolada da avaliação SQL, com
    resultados de `avaliar` construídos à mão. As cláusulas de correção CONTRA o banco (ST_Intersects e
    ST_DWithin independentes) estão nos testes acima, que exigem `cur`."""
    ids = ["u0", "u1", "u2"]
    r1 = _restricao_norma_intersecta()
    r2 = _restricao_precaucao_buffer()
    resultado_r1 = {"u0": {"vetada": True, "fracao_intersectada": None},
                    "u1": {"vetada": False, "fracao_intersectada": None},
                    "u2": {"vetada": False, "fracao_intersectada": None}}
    resultado_r2 = {"u0": {"vetada": True, "fracao_intersectada": None},
                    "u1": {"vetada": True, "fracao_intersectada": None},
                    "u2": {"vetada": False, "fracao_intersectada": None}}
    composto = compor(ids, [(r1, resultado_r1), (r2, resultado_r2)])
    assert composto["fracao_vetada"] == [1.0, 1.0, 0.0]
    # u0 é vetada por r1 E r2, mas o motivo é o da PRIMEIRA na ordem declarada (r1, 'norma')
    assert composto["motivo"][0].startswith("a norma veda")
    # u1 só é vetada por r2 ('precaucao')
    assert composto["motivo"][1].startswith("vetamos por precaução")
    assert composto["motivo"][2] is None
    contagem = {c["id"]: c["unidades_vetadas"] for c in composto["contagem_por_restricao"]}
    assert contagem["r_uc"] == 1
    assert contagem["r_ponto"] == 2
    assert composto["unidades_vetadas_total"] == 2
