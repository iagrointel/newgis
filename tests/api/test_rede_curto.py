"""Curto-circuito por barra e coordenação de proteção pela API (item L4-27-curto-circuito-e-protecao).

Cláusulas do portão provadas aqui:

* curto calculado sobre UM alimentador, com `Ik` por barra, e o número de barras conferido por consulta
  INDEPENDENTE às tabelas de topologia — `test_curto_do_alimentador_tem_ik_por_barra`;
* dispositivo SEM faixa de interrupção cadastrada sai `sem_dado`; com faixa cadastrada, o mesmo
  alimentador passa a `interrompe` — `test_dispositivo_sem_faixa_sai_sem_dado_e_com_faixa_interrompe`;
* o resultado sai como TABELA (colunas descritas + linhas) e como CAMADA (pontos com a coordenada lida
  da topologia) — `test_tabela_e_camada_do_mesmo_calculo`.

Refutação (papel adversário), provada aqui:

* `test_fonte_sem_potencia_de_curto_e_recusada`: premissa ausente e potência zero (impedância de fonte
  nula) dão 422 nomeado, nunca corrente infinita;
* `test_ler_antes_de_calcular_da_404`: leitura sem cálculo é 404, não uma tabela vazia que pareceria zero;
* `test_subrede_inexistente_da_404`.

A cláusula "curto em 1 alimentador da COOPERATIVA DE TESTE" (rede real da casa) é medida à parte, em
`tests/api/test_rede_curto_medida.py`, marcada `lento`.
"""

import math

import pytest

from tests.api.test_rede_opendss import (
    CTMT,
    DISJUNTOR,
    SUB,
    TEN_NOM,
    _alimentador,
    _atualizar_tudo,
    _criar_rede,
)

PREMISSAS = {"potencia_de_curto_mva": 250.0, "relacao_x_r_fonte": 10.0, "fator_tensao_c": 1.05}


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _alimentador_pronto(sessao, env, limpar, sufixo):
    rid = _criar_rede(sessao, sufixo, limpar)
    feicoes = _alimentador(sessao, rid)
    _atualizar_tudo(sessao, env, rid)
    return rid, feicoes


def _nos_da_topologia(env, sessao, rid) -> int:
    """Quantos nós a topologia tem, contados DIRETO na tabela — caminho independente do que o cálculo
    monta. Serve de teto: barras = nós menos as fusões por chave fechada."""
    import psycopg2

    from app import db as banco
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    con.close()
    with banco.db(banco.Contexto(tenant_id, int(eu["id"]), "teste-l427")) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.rede_topo_no WHERE rede_id = %s::uuid", (rid,))
        return cur.fetchone()["n"]


def test_curto_do_alimentador_tem_ik_por_barra(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "curto")
    r = sessao_a.post(f"/api/rede/{rid}/subrede/{CTMT}/curto", json=PREMISSAS)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert saida["subrede"] == CTMT
    assert saida["barras"] >= 3, saida
    assert saida["barras"] <= _nos_da_topologia(env, sessao_a, rid), "barra não pode passar de nó"
    # as premissas voltam inteiras: o número não se lê sem a hipótese que o produziu
    assert saida["premissas"]["potencia_de_curto_mva"] == 250.0
    assert saida["premissas"]["fator_tensao_c"] == 1.05
    assert saida["premissas"]["impedancia_da_fonte_pu"] == pytest.approx(100.0 / 250.0)
    resumo = saida["resumo"]
    assert resumo["barras_alcancadas"] >= 3
    assert resumo["ik3_maxima_a"] > resumo["ik3_minima_a"] > 0

    # a maior corrente é a da barra da fonte, e ela bate com a conta fechada c·Un/(√3·|Z_fonte|)
    corpo = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/curto").json()
    por_barra = {linha["barra"]: linha for linha in corpo["linhas"]}
    fonte = por_barra[resumo["barra_fonte"]]
    kv = fonte["kv"]
    z_fonte = kv * kv / 250.0
    esperado = 1.05 * kv * 1000.0 / (math.sqrt(3.0) * z_fonte)
    assert fonte["ik3_a"] == pytest.approx(esperado, rel=1e-6)
    assert fonte["ik3_a"] == resumo["ik3_maxima_a"], "a fonte é a barra de maior corrente numa radial"


def test_tabela_e_camada_do_mesmo_calculo(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "curto-camada")
    assert sessao_a.post(f"/api/rede/{rid}/subrede/{CTMT}/curto", json=PREMISSAS).status_code == 200

    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/curto")
    assert r.status_code == 200, r.text
    tabela = r.json()
    assert [c["codigo"] for c in tabela["colunas"]][:4] == ["barra", "kv", "ik3_a", "ik1_a"]
    correntes = [linha["ik3_a"] for linha in tabela["linhas"] if linha["ik3_a"] is not None]
    assert correntes == sorted(correntes, reverse=True), "a tabela sai da maior corrente para a menor"
    assert all(linha["veredito"] in (
        "interrompe", "abaixo_da_faixa", "acima_da_capacidade", "sem_dado",
        "sem_dispositivo_a_montante") for linha in tabela["linhas"])

    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/curto/camada")
    assert r.status_code == 200, r.text
    camada = r.json()
    assert camada["type"] == "FeatureCollection" and camada["features"]
    assert len(camada["features"]) + camada["barras_sem_coordenada"] == len(tabela["linhas"])
    for f in camada["features"]:
        lon, lat = f["geometry"]["coordinates"]
        assert (lon, lat) != (0.0, 0.0), "barra sem coordenada não vira ponto na Ilha Nula"
        assert -180 <= lon <= 180 and -90 <= lat <= 90
        assert "ik3_a" in f["properties"] and "veredito" in f["properties"]
    # a camada é o MESMO cálculo, não outro: corrente por barra tem de bater linha a linha
    da_tabela = {linha["barra"]: linha["ik3_a"] for linha in tabela["linhas"]}
    for f in camada["features"]:
        assert f["properties"]["ik3_a"] == da_tabela[f["properties"]["barra"]]


def test_dispositivo_sem_faixa_sai_sem_dado_e_com_faixa_interrompe(sessao_a, env, limpar_redes):
    rid, feicoes = _alimentador_pronto(sessao_a, env, limpar_redes, "curto-faixa")
    assert sessao_a.post(f"/api/rede/{rid}/subrede/{CTMT}/curto", json=PREMISSAS).status_code == 200
    linhas = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/curto").json()["linhas"]
    vereditos = {linha["veredito"] for linha in linhas}
    # a BDGD não tem campo de faixa de interrupção: sem alguém cadastrar, o veredito honesto é "sem dado"
    assert "sem_dado" in vereditos, linhas
    assert vereditos <= {"sem_dado", "sem_dispositivo_a_montante"}, linhas
    assert all(linha["faixa_min_a"] is None and linha["faixa_max_a"] is None for linha in linhas)

    # agora a faixa é cadastrada na feição do disjuntor, pelo applyEdits da própria camada de rede
    atributos = {"ctmt": CTMT, "sub": SUB, "unsemt_fas_con": "ABC", "unsemt_p_n_ope": "F",
                 "ten_nom": TEN_NOM, "unsemt_cod_id": "CH-1", "tipo_codigo": DISJUNTOR,
                 "corrente_interrupcao_min_a": 1.0, "corrente_interrupcao_max_a": 1e9}
    r = sessao_a.post(f"/api/rede/{rid}/feicoes/pontos/applyEdits",
                      json={"updates": [{"attributes": {"id": feicoes["disjuntor"]["id"],
                                                        "atributos": atributos}}]})
    assert r.status_code == 200 and r.json()["updateResults"][0]["success"] is True, r.text

    assert sessao_a.post(f"/api/rede/{rid}/subrede/{CTMT}/curto", json=PREMISSAS).status_code == 200
    linhas = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/curto").json()["linhas"]
    com_dispositivo = [linha for linha in linhas if linha["dispositivo_codigo"] == "CH-1"]
    assert com_dispositivo, linhas
    assert {linha["veredito"] for linha in com_dispositivo} == {"interrompe"}
    assert all(linha["faixa_max_a"] == 1e9 for linha in com_dispositivo)


@pytest.mark.parametrize("corpo,codigo", [
    ({}, "impedancia_de_fonte_ausente"),
    ({"potencia_de_curto_mva": 0}, "impedancia_de_fonte_nula"),
    ({"potencia_de_curto_mva": -10}, "impedancia_de_fonte_nula"),
    ({"potencia_de_curto_mva": 100, "impedancia_de_fonte": 0}, "premissa_desconhecida"),
])
def test_fonte_sem_potencia_de_curto_e_recusada(sessao_a, env, limpar_redes, corpo, codigo):
    """Refutação exigida: fonte de impedância nula não devolve corrente infinita — é recusada."""
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "curto-recusa")
    r = sessao_a.post(f"/api/rede/{rid}/subrede/{CTMT}/curto", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == codigo, r.text


def test_ler_antes_de_calcular_da_404(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "curto-sem-calculo")
    for caminho in (f"/api/rede/{rid}/subrede/{CTMT}/curto",
                    f"/api/rede/{rid}/subrede/{CTMT}/curto/camada"):
        r = sessao_a.get(caminho)
        assert r.status_code == 404, r.text
        assert r.json()["erro"] == "curto_nao_calculado"


def test_subrede_inexistente_da_404(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "curto-404")
    r = sessao_a.post(f"/api/rede/{rid}/subrede/ZT-NAO-EXISTE/curto", json=PREMISSAS)
    assert r.status_code == 404, r.text
