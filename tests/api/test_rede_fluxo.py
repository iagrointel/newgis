"""Fluxo de potência do alimentador pela API (item L4-07-fluxo-de-potencia).

Cláusulas do portão provadas aqui:

* o alimentador inteiro (média tensão, transformador, baixa tensão, ramal, consumidor e geração
  distribuída) é analisado e o resultado sai POR ELEMENTO, com o número de barras conferido contra a
  topologia por consulta INDEPENDENTE — `test_fluxo_do_alimentador_tem_resultado_por_elemento`;
* CONVERGÊNCIA sempre ao lado do resultado, nas três leituras (POST, tabela e camada) —
  `test_convergencia_acompanha_toda_leitura`;
* PARÂMETROS e VERSÃO DA TOPOLOGIA na ficha do resultado — `test_ficha_traz_parametros_e_topologia`;
* as três CAMADAS (tensão, corrente, carregamento) saem com geometria de verdade e o mesmo número da
  tabela — `test_tres_camadas_do_mesmo_calculo`;
* o job `redes.analisar_alimentador` roda o lote e agrega — `test_job_analisa_o_lote_e_agrega`.

Refutação (papel adversário), provada aqui:

* `test_trafo_sem_potencia_falha_alto_no_fluxo`: transformador sem POT_NOM faz a análise PARAR com 422,
  em vez de resolver um circuito com 0 kVA;
* `test_o_mesmo_alimentador_duas_vezes_da_o_mesmo_resultado`: determinismo ponta a ponta, pela API;
* `test_parametro_desconhecido_e_recusado_pela_api`;
* `test_ler_antes_de_analisar_da_404` e `test_grandeza_desconhecida_e_recusada`.

A cláusula "a cooperativa de teste inteira (16 alimentadores com cliente)" é medida à parte, em
`tests/api/test_rede_fluxo_medida.py`, marcada `lento`.
"""

import os

import pytest

from tests.api.test_rede_opendss import (
    CTMT,
    _alimentador,
    _atualizar_tudo,
    _criar_rede,
)

pytest.importorskip("opendssdirect",
                    reason="opendssdirect não está nesta máquina: o motor de fluxo não foi medido")

# modo `hora` no teste rápido: a varredura anual dos 864 pontos é medida em test_rede_fluxo_medida.py
UMA_HORA = {"modo": "hora", "ponto": 0, "ano": 2026}
ANO_INTEIRO = {"modo": "anual", "ano": 2026}


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _alimentador_pronto(sessao, env, limpar, sufixo, **kwargs):
    # sufixo único por processo: uma rodada anterior interrompida (o motor OpenDSS já derrubou o
    # interpretador uma vez, antes do conserto do diretório de trabalho) deixa a rede de teste no banco da
    # trilha, e o nome repetido faria a rodada seguinte falhar com 409 em vez de medir o produto.
    rid = _criar_rede(sessao, f"{sufixo}-{os.getpid()}", limpar)
    feicoes = _alimentador(sessao, rid, **kwargs)
    _atualizar_tudo(sessao, env, rid)
    return rid, feicoes


def _contexto(env, sessao):
    import psycopg2

    from app import db as banco
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    con.close()
    return tenant_id, banco.Contexto(tenant_id, int(eu["id"]), "teste-l407")


def _nos_e_trechos(env, sessao, rid) -> tuple[int, int]:
    """Nós e trechos da topologia contados DIRETO na tabela — caminho independente do que o cálculo monta."""
    from app import db as banco

    _, contexto = _contexto(env, sessao)
    with banco.db(contexto) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.rede_topo_no WHERE rede_id = %s::uuid", (rid,))
        nos = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid "
                    "AND no_origem_id IS NOT NULL AND no_destino_id IS NOT NULL", (rid,))
        return nos, cur.fetchone()["n"]


def _analisar(sessao, rid, corpo=None, **query):
    q = "&".join(f"{k}={v}" for k, v in {"jusante": "true", **query}.items())
    return sessao.post(f"/api/rede/{rid}/subrede/{CTMT}/fluxo?{q}", json=corpo or UMA_HORA)


# --- cláusula: resultado por elemento ------------------------------------------------------------------

def test_fluxo_do_alimentador_tem_resultado_por_elemento(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo")
    r = _analisar(sessao_a, rid)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert saida["subrede"] == CTMT and saida["convergiu"] is True, saida["avisos"]
    nos, trechos = _nos_e_trechos(env, sessao_a, rid)
    assert 0 < saida["resumo"]["barras"] <= nos, (saida["resumo"], nos)
    assert saida["resumo"]["trechos"] == trechos, (saida["resumo"], trechos)
    assert saida["resumo"]["transformadores"] == 1, saida["resumo"]

    tabela = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").json()
    tipos = {}
    for linha in tabela["linhas"]:
        tipos.setdefault(linha["tipo"], []).append(linha)
    assert set(tipos) == {"barra", "trecho", "trafo"}, sorted(tipos)

    # tensão por barra E FASE, em por unidade e dentro de faixa plausível
    fases = {linha["fase"] for linha in tipos["barra"]}
    assert fases <= {1, 2, 3} and fases, fases
    for linha in tipos["barra"]:
        assert 0.5 < linha["tensao_pu"] < 1.5, linha
    # corrente, carregamento e perda por trecho
    assert len(tipos["trecho"]) == trechos
    for linha in tipos["trecho"]:
        assert linha["corrente_a"] >= 0 and linha["carregamento_pc"] >= 0 and linha["perda_kw"] >= 0, linha
    # carregamento e perda de ferro por transformador
    trafo = tipos["trafo"][0]
    assert trafo["codigo"] == "TR-1"
    assert trafo["carregamento_pc"] >= 0 and trafo["perda_ferro_kw"] > 0, trafo
    assert trafo["potencia_kva"] >= 0, trafo
    # a tabela sai da menor tensão para a maior: o que dói primeiro
    tensoes = [linha["tensao_pu"] for linha in tabela["linhas"] if linha["tensao_pu"] is not None]
    assert tensoes == sorted(tensoes), tensoes[:5]
    assert tabela["total"] == len(tabela["linhas"])

    # e o filtro por tipo devolve o mesmo subconjunto
    so_trechos = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo?tipo=trecho").json()
    assert {linha["tipo"] for linha in so_trechos["linhas"]} == {"trecho"}
    assert len(so_trechos["linhas"]) == trechos


# --- cláusula: convergência ao lado de toda leitura ----------------------------------------------------

def test_convergencia_acompanha_toda_leitura(sessao_a, env, limpar_redes):
    """Regra dura do item: nenhuma leitura devolve número sem o estado de convergência ao lado."""
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-conv")
    assert _analisar(sessao_a, rid).status_code == 200

    def conferir(doc):
        assert doc["convergiu"] is True, doc
        c = doc["convergencia"]
        assert c["convergiu"] is True and c["pontos"] == 1 and c["pontos_sem_convergencia"] == 0, c

    conferir(_analisar(sessao_a, rid).json())
    conferir(sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").json())
    for grandeza in ("tensao", "corrente", "carregamento"):
        conferir(sessao_a.get(
            f"/api/rede/{rid}/subrede/{CTMT}/fluxo/camada?grandeza={grandeza}").json())


def test_ficha_traz_parametros_e_topologia(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-ficha")
    corpo = {**UMA_HORA, "fator_de_carga": 1.3, "corrente_nominal_a": 120.0,
             "modelo_de_carga": "corrente_constante", "tensao_da_fonte_pu": 1.01}
    assert _analisar(sessao_a, rid, corpo).status_code == 200
    ficha = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").json()
    assert ficha["parametros"]["fator_de_carga"] == 1.3
    assert ficha["parametros"]["corrente_nominal_a"] == 120.0
    assert ficha["parametros"]["modelo_de_carga"] == "corrente_constante"
    assert ficha["parametros"]["tensao_da_fonte_pu"] == 1.01
    assert ficha["parametros"]["modo"] == "hora" and ficha["parametros"]["ponto"] == 0
    assert ficha["topologia_versao"], "a versão da topologia usada tem de vir na ficha"
    assert ficha["resumo"]["corrente_nominal_de_referencia_a"] == 120.0
    assert "triagem" in ficha["resumo"]["impedancia"]
    assert ficha["ponto_critico"]["indice"] == 0
    assert ficha["pico_ram_mb"] > 0 and ficha["onde_rodou"] == "local"


def test_energia_do_ano_e_perda_de_ferro_saem_na_varredura_anual(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-anual")
    r = _analisar(sessao_a, rid, ANO_INTEIRO)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert saida["convergencia"]["pontos"] == 864
    energia = saida["energia"]
    assert energia["horas_do_ano"] == 8760.0
    assert energia["transformadores_com_per_fer"] == 1
    assert energia["perda_de_ferro_declarada_kwh"] > 0
    # o transformador do alimentador de teste tem PER_FER = 150 W: 150 W x 8760 h = 1.314 kWh
    assert energia["perda_de_ferro_declarada_kwh"] == pytest.approx(1314.0, rel=1e-9)
    razao = energia["razao_perda_de_ferro"]
    assert abs(razao - 1.0) <= 0.02, razao
    assert energia["energia_perdida_kwh"] > 0


# --- cláusula: as três camadas ------------------------------------------------------------------------

def test_tres_camadas_do_mesmo_calculo(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-camada")
    assert _analisar(sessao_a, rid).status_code == 200
    tabela = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").json()
    por_tipo = {}
    for linha in tabela["linhas"]:
        por_tipo.setdefault(linha["tipo"], []).append(linha)

    camadas = {}
    for grandeza in ("tensao", "corrente", "carregamento"):
        r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo/camada?grandeza={grandeza}")
        assert r.status_code == 200, r.text
        camadas[grandeza] = r.json()
        doc = camadas[grandeza]
        assert doc["type"] == "FeatureCollection" and doc["features"], doc["elementos_do_tipo"]
        assert doc["grandeza"] == grandeza
        assert len(doc["features"]) + doc["elementos_sem_geometria"] == doc["elementos_do_tipo"]
        for f in doc["features"]:
            assert f["properties"]["valor"] is not None
            assert f["properties"]["unidade"] in ("pu", "A", "%")

    # tensão é ponto por barra e fase; corrente e carregamento são a linha do trecho
    assert {f["geometry"]["type"] for f in camadas["tensao"]["features"]} == {"Point"}
    assert camadas["tensao"]["elementos_do_tipo"] == len(por_tipo["barra"])
    for grandeza in ("corrente", "carregamento"):
        assert {f["geometry"]["type"] for f in camadas[grandeza]["features"]} == {"LineString"}
        assert camadas[grandeza]["elementos_do_tipo"] == len(por_tipo["trecho"])
    for f in camadas["tensao"]["features"]:
        lon, lat = f["geometry"]["coordinates"]
        assert (lon, lat) != (0.0, 0.0), "barra sem coordenada não vira ponto na Ilha Nula"
        assert -180 <= lon <= 180 and -90 <= lat <= 90

    # a camada é o MESMO cálculo, não outro: valor por elemento bate com a tabela
    da_tabela = {linha["elemento"]: linha for linha in por_tipo["trecho"]}
    for f in camadas["corrente"]["features"]:
        assert f["properties"]["valor"] == da_tabela[f["properties"]["elemento"]]["corrente_a"]
    for f in camadas["carregamento"]["features"]:
        assert f["properties"]["valor"] == da_tabela[f["properties"]["elemento"]]["carregamento_pc"]


# --- cláusula: o job roda o lote e agrega --------------------------------------------------------------

def test_job_analisa_o_lote_e_agrega(sessao_a, env, limpar_redes):
    """O caminho pesado é job. Aqui ele roda pelo MESMO motor, chamado direto (o worker é outro item),
    sobre a rede de teste: um alimentador de média tensão e o de baixa que pende do transformador."""
    from app.rede_utilidades import tarefas

    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-job")
    tenant_id, contexto = _contexto(env, sessao_a)

    class _Ctx:
        def __init__(self):
            self.tenant_id = tenant_id
            self.passos = []

        def db(self):
            from app import db as banco

            return banco.db(contexto)

        def progresso(self, pct, mensagem=""):
            self.passos.append((pct, mensagem))

    ctx = _Ctx()
    saida = tarefas.redes_analisar_alimentador(
        ctx, rede_id=rid, tier="media_tensao", jusante=True, parametros=UMA_HORA)
    assert saida["alimentadores_pedidos"] >= 1, saida
    assert saida["recusados"] == [], saida["recusados"]
    assert [a["subrede"] for a in saida["analisados"]] == [CTMT]
    assert saida["analisados"][0]["convergiu"] is True
    agregado = saida["agregado"]
    assert agregado["alimentadores_agregados"] == agregado["alimentadores"] == 1
    assert agregado["alimentadores_fora_por_nao_convergencia"] == []
    assert agregado["energia_da_carga_kwh"] >= 0
    assert saida["pico_ram_mb"] > 0
    assert ctx.passos, "o job informa progresso alimentador a alimentador"


# --- refutação ----------------------------------------------------------------------------------------

def test_trafo_sem_potencia_falha_alto_no_fluxo(sessao_a, env, limpar_redes):
    """Refutação exigida: transformador sem POT_NOM PARA a análise, em vez de resolver um circuito de
    0 kVA que compila e mente."""
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-sem-pot", pot_nom=None)
    r = _analisar(sessao_a, rid)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "trafo_sem_potencia", r.text
    # e nada ficou gravado: leitura depois da recusa é 404, nunca uma tabela pela metade
    assert sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").status_code == 404


def test_o_mesmo_alimentador_duas_vezes_da_o_mesmo_resultado(sessao_a, env, limpar_redes):
    """Refutação exigida: o adversário roda duas vezes e compara. Só relógio e memória podem mudar."""
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-determinismo")
    assert _analisar(sessao_a, rid, ANO_INTEIRO).status_code == 200
    primeira = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").json()
    assert _analisar(sessao_a, rid, ANO_INTEIRO).status_code == 200
    segunda = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo").json()

    def comparavel(doc):
        return {k: v for k, v in doc.items()
                if k not in ("execucao_id", "calculado_em", "duracao_ms", "pico_ram_mb")}

    assert comparavel(primeira) == comparavel(segunda)
    # e a análise nova SUBSTITUI a anterior: uma execução viva por alimentador
    assert primeira["execucao_id"] != segunda["execucao_id"]


@pytest.mark.parametrize("corpo,codigo", [
    ({"fator_carga": 2.0}, "parametro_desconhecido"),
    ({"modo": "semanal"}, "modo_invalido"),
    ({"modo": "hora"}, "ponto_ausente"),
    ({"modo": "hora", "ponto": 864}, "ponto_fora_da_curva"),
    ({"fator_de_carga": 0}, "fator_de_carga_invalido"),
    ({"modelo_de_carga": "zip"}, "zipv_ausente"),
])
def test_parametro_desconhecido_e_recusado_pela_api(sessao_a, env, limpar_redes, corpo, codigo):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, f"fluxo-recusa-{codigo[:8]}")
    r = _analisar(sessao_a, rid, corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == codigo, r.text


def test_ler_antes_de_analisar_da_404(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-sem-calculo")
    for caminho in (f"/api/rede/{rid}/subrede/{CTMT}/fluxo",
                    f"/api/rede/{rid}/subrede/{CTMT}/fluxo/camada?grandeza=tensao"):
        r = sessao_a.get(caminho)
        assert r.status_code == 404, r.text
        assert r.json()["erro"] == "fluxo_nao_calculado"


def test_grandeza_desconhecida_e_recusada(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-grandeza")
    assert _analisar(sessao_a, rid).status_code == 200
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/fluxo/camada?grandeza=potencia")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "grandeza_invalida"


def test_subrede_inexistente_da_404(sessao_a, env, limpar_redes):
    rid, _ = _alimentador_pronto(sessao_a, env, limpar_redes, "fluxo-404")
    r = sessao_a.post(f"/api/rede/{rid}/subrede/ZT-NAO-EXISTE/fluxo", json=UMA_HORA)
    assert r.status_code == 404, r.text
