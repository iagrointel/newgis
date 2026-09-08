"""Portão do item L2-03-f-edicao-em-lote-calculo-campo: `POST /api/camadas/{id}/lote`.

Camadas criadas direto no banco pela mesma `FabricaCamada` do L2-03-a (tests/api/test_edicao_transacional.py). Os
testes de job exigem um worker vivo na trilha (fixture `worker_vivo` de tests/api/jobs/conftest.py)."""

from __future__ import annotations

import math
import time

import pytest

from tests.api.jobs.conftest import esperar, worker_vivo  # noqa: F401 — fixture reexportada
from tests.api.test_edicao_transacional import (  # noqa: F401 — fixtures reexportadas
    FabricaCamada,
    _admin_usuario_id,
    _ponto,
    camada_a,
    camada_a_somente_proprias,
    camada_b,
    fabrica,
)
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-03-f-edicao-em-lote-calculo-campo"
CAMPOS_POLI = [{"nome": "nome", "tipo": "text"}, {"nome": "area_ha", "tipo": "double precision"},
               {"nome": "area_ha_sql", "tipo": "double precision"}, {"nome": "area_ha_py", "tipo": "double precision"},
               {"nome": "classe", "tipo": "text"}, {"nome": "n", "tipo": "integer"}]


def _lote(sessao, camada_id, **corpo):
    return sessao.post(f"/api/camadas/{camada_id}/lote", json=corpo)


def _quadrados(con, camada: dict, n: int, lado_graus: float = 0.001) -> None:
    """Insere `n` quadrados de ~lado_graus (≈ 110 m) em grade a partir de (-46.5, -23.5), direto no banco
    (contexto do inquilino + gatilhos da tabela: globalid/versao/rastreio/histórico como em produção)."""
    d = camada["dados"]
    contexto(con, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with con.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{d["schema"]}"."{d["tabela"]}" (nome, classe, n, geom) '
            "SELECT 'q' || i, CASE WHEN i %% 3 = 0 THEN 'A' ELSE 'B' END, i, "
            "ST_Multi(ST_SetSRID(ST_MakeEnvelope(-46.5 + (i %% 400) * %s, -23.5 + (i / 400) * %s, "
            "-46.5 + (i %% 400) * %s + %s * 0.9, -23.5 + (i / 400) * %s + %s * 0.9), 4674)) "
            "FROM generate_series(1, %s) AS i",
            (lado_graus, lado_graus, lado_graus, lado_graus, lado_graus, lado_graus, n),
        )
    con.commit()


def _linhas(fabrica, camada, colunas="*"):
    d = camada["dados"]
    contexto(fabrica.con, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with fabrica.con.cursor() as cur:
        cur.execute(f'SELECT {colunas} FROM "{d["schema"]}"."{d["tabela"]}" ORDER BY fid')
        return cur.fetchall()


def _historico_n(fabrica, camada) -> int:
    d = camada["dados"]
    contexto(fabrica.con, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with fabrica.con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.feicao_historico WHERE schema_dado = %s AND tabela_dado = %s",
                    (d["schema"], d["tabela"]))
        return cur.fetchone()["n"]


@pytest.fixture
def camada_poli(fabrica, conexao_plat_app):
    """MultiPolygon em demo com campos numéricos/texto e domínio em `classe` (A/B/C) e `n` (0-1000000)."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id, campos=CAMPOS_POLI, geometria="MultiPolygon",
        regras_campo={"classe": {"dominio_valores": ["A", "B", "C"]},
                      "n": {"dominio_min": 0, "dominio_max": 1_000_000}},
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


# ---------------------------------------------------------------- portão 1: 100 mil feições, area_ha como job ≤ 30 s
def test_calcular_area_ha_em_100_mil_feicoes_como_job(sessao_a, camada_poli, fabrica, worker_vivo, medida):
    _quadrados(fabrica.con, camada_poli, 100_000)
    hist_antes = _historico_n(fabrica, camada_poli)
    t0 = time.monotonic()
    r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha", expressao="$area_m2 / 10000",
              selecao={"todas": True})
    assert r.status_code == 202, r.text[:500]
    j = r.json()
    assert j["execucao"] == "job" and j["total"] == 100_000 and j["traducao"] == "sql", j
    fim = esperar(sessao_a, j["job_id"], timeout=120)
    dt = round(time.monotonic() - t0, 3)
    assert fim["estado"] == "concluido", fim
    assert fim["resultado"]["alteradas"] == 100_000, fim["resultado"]
    gravar = medida(ITEM)
    gravar("calcular_area_ha_100mil_s", dt, "s",
           "POST /api/camadas/{id}/lote calcular area_ha = $area_m2 / 10000 em 100.000 MultiPolygon (job camadas.lote, "
           "do pedido até estado=concluido; tests/api/test_edicao_lote.py)")
    gravar("calcular_area_ha_100mil_job_ms", fim["resultado"]["duracao_ms"], "ms",
           "duração medida dentro do job (só a transação do lote)")
    assert dt <= 30.0, f"calcular_area_ha_100mil_s = {dt} s (teto 30 s)"
    # amostra de 1.000: igual a ST_Area(geography)/10000 com tolerância 1e-6
    d = camada_poli["dados"]
    contexto(fabrica.con, camada_poli["tenant_id"], usuario_id=camada_poli["admin_id"], login="admin")
    with fabrica.con.cursor() as cur:
        cur.execute(f'SELECT area_ha, ST_Area(geom::geography) / 10000 AS esperado, versao '
                    f'FROM "{d["schema"]}"."{d["tabela"]}" WHERE fid % 100 = 7 ORDER BY fid LIMIT 1000')
        amostra = cur.fetchall()
    assert len(amostra) == 1000
    pior = max(abs(a["area_ha"] - a["esperado"]) for a in amostra)
    gravar("amostra_1000_desvio_max_ha", pior, "ha", "max |area_ha - ST_Area(geom::geography)/10000| em 1.000 feições")
    assert pior <= 1e-6, pior
    assert all(a["versao"] == 2 for a in amostra), "cada feição ganhou uma versão (gatilho tg_versao)"
    # refutação: histórico gerado para TODAS as linhas (gatilho tg_historico, também no job)
    assert _historico_n(fabrica, camada_poli) - hist_antes == 100_000


# ---------------------------------------------------------------- portão 2: linha a linha == sql
def test_linha_a_linha_da_o_mesmo_resultado_da_traducao_sql(sessao_a, camada_poli, fabrica):
    _quadrados(fabrica.con, camada_poli, 2_000)
    expressao = "Arredondar($area_m2 / 10000, 4) + Se($n % 2 == 0, 0.5, 0) - Minimo(Absoluto($n - 3), 1)"
    r1 = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha_sql", expressao=expressao,
               selecao={"todas": True}, avaliacao="sql")
    assert r1.status_code == 200 and r1.json()["traducao"] == "sql", r1.text[:400]
    r2 = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha_py", expressao=expressao,
               selecao={"todas": True}, avaliacao="linha_a_linha")
    assert r2.status_code == 200 and r2.json()["traducao"] == "linha_a_linha", r2.text[:400]
    assert r1.json()["alteradas"] == r2.json()["alteradas"] == 2_000
    linhas = _linhas(fabrica, camada_poli, "area_ha_sql, area_ha_py")
    diferentes = [ln for ln in linhas
                  if not math.isclose(ln["area_ha_sql"], ln["area_ha_py"], rel_tol=0, abs_tol=1e-9)]
    assert diferentes == [], diferentes[:5]
    # função sem tradução (Texto) cai automaticamente para linha a linha, com o motivo nomeado
    r3 = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="nome",
               expressao="Concatenar('q-', Texto($n), '-', Maiuscula($classe))", selecao={"onde": "$n <= 3"})
    assert r3.status_code == 200, r3.text[:400]
    assert r3.json()["traducao"] == "linha_a_linha" and "Texto" in r3.json()["traducao_motivo"], r3.json()
    assert r3.json()["alteradas"] == 3
    nomes = [ln["nome"] for ln in _linhas(fabrica, camada_poli, "nome")[:4]]
    assert nomes == ["q-1-B", "q-2-B", "q-3-A", "q4"], nomes


# ---------------------------------------------------------------- portão 3: 1 fora do domínio = nada muda
def test_uma_feicao_fora_do_dominio_nao_altera_nenhuma(sessao_a, camada_poli, fabrica):
    _quadrados(fabrica.con, camada_poli, 50)
    hist = _historico_n(fabrica, camada_poli)
    for avaliacao in ("sql", "linha_a_linha"):
        r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="classe",
                  expressao="Se($n == 7, 'Z', 'C')", selecao={"todas": True}, avaliacao=avaliacao)
        assert r.status_code == 422, (avaliacao, r.text[:400])
        assert r.json()["erro"] == "fora_do_dominio" and r.json()["detalhe"]["campo"] == "classe", r.json()
        assert "422" not in r.json()["mensagem"]
    assert {ln["classe"] for ln in _linhas(fabrica, camada_poli, "classe")} == {"A", "B"}
    assert all(ln["versao"] == 1 for ln in _linhas(fabrica, camada_poli, "versao"))
    assert _historico_n(fabrica, camada_poli) == hist, "rollback também apaga o histórico do UPDATE desfeito"
    # atribuir valor fixo fora do domínio: recusado antes de tocar qualquer linha
    r = _lote(sessao_a, camada_poli["id"], operacao="atribuir", campo="n", valor=-5, selecao={"todas": True})
    assert r.status_code == 422 and r.json()["erro"] == "fora_do_dominio", r.text
    # modo parcial: a linha errada vira falha nomeada, as outras gravam
    r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="classe", expressao="Se($n == 7, 'Z', 'C')",
              selecao={"todas": True}, modo="parcial")
    assert r.status_code == 200, r.text[:400]
    j = r.json()
    assert j["alteradas"] == 49 and j["falhas_total"] == 1 and j["falhas"][0]["erro"] == "fora_do_dominio", j
    assert j["traducao"] == "linha_a_linha"
    classes = [ln["classe"] for ln in _linhas(fabrica, camada_poli, "classe, n")]
    assert classes.count("C") == 49 and classes[6] == "B"  # n=7 (índice 6) ficou como estava


# ---------------------------------------------------------------- portão 4: pré-visualização correta, nada gravado
def test_previa_mostra_antes_e_depois_sem_gravar(sessao_a, camada_poli, fabrica):
    _quadrados(fabrica.con, camada_poli, 30)
    r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha", expressao="$area_m2 / 10000",
              selecao={"todas": True}, previa=True)
    assert r.status_code == 200, r.text[:400]
    j = r.json()
    assert j["execucao"] == "previa" and j["total"] == 30 and len(j["previa"]) == 10, j
    linhas = _linhas(fabrica, camada_poli, "globalid, area_ha, ST_Area(geom::geography) / 10000 AS esperado, versao")
    for p, ln in zip(j["previa"], linhas[:10], strict=True):
        assert p["id"] == str(ln["globalid"]) and p["antes"] is None
        assert math.isclose(p["depois"], ln["esperado"], abs_tol=1e-9), (p, ln["esperado"])
    assert all(ln["area_ha"] is None and ln["versao"] == 1 for ln in linhas), "prévia nunca grava"
    # prévia linha a linha com erro numa feição: a linha vem com o erro nomeado, as outras com o valor
    r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha",
              expressao="Numero(Texto($n)) / ($n - 2)", selecao={"todas": True}, previa=True)
    assert r.status_code == 200, r.text[:400]
    p = r.json()["previa"]
    assert p[1]["erro"] == "divisao_por_zero" and p[0]["depois"] == -1.0 and p[2]["depois"] == 3.0, p[:3]
    # prévia de apagar e de atribuir
    r = _lote(sessao_a, camada_poli["id"], operacao="apagar", selecao={"onde": "$n > 28"}, previa=True)
    assert r.status_code == 200 and r.json()["total"] == 2 and r.json()["previa"][0]["antes"]["n"] == 29, r.text[:300]
    r = _lote(sessao_a, camada_poli["id"], operacao="atribuir", campo="classe", valor="C", selecao={"todas": True},
              previa=True)
    assert r.status_code == 200 and r.json()["previa"][0]["depois"] == "C", r.text[:300]
    assert len(_linhas(fabrica, camada_poli, "fid")) == 30


# ---------------------------------------------------------------- portão 5: cancelar no meio = estado anterior
def test_cancelamento_no_meio_deixa_a_camada_no_estado_anterior(sessao_a, camada_poli, fabrica, worker_vivo):
    _quadrados(fabrica.con, camada_poli, 40_000)
    hist = _historico_n(fabrica, camada_poli)
    # linha a linha de propósito (mais lento: dá tempo de cancelar entre sub-lotes de 1.000)
    r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha",
              expressao="Arredondar($area_m2 / 10000, 6)", selecao={"todas": True}, avaliacao="linha_a_linha")
    assert r.status_code == 202, r.text[:400]
    jid = r.json()["job_id"]
    esperar(sessao_a, jid, timeout=60, condicao=lambda j: j["estado"] == "rodando" and (j["progresso"] or 0) >= 5)
    rc = sessao_a.post(f"/api/jobs/{jid}/cancelar")
    assert rc.status_code == 202, rc.text
    fim = esperar(sessao_a, jid, timeout=60)
    assert fim["estado"] == "cancelado", fim
    assert 0 < fim["progresso"] < 100, fim["progresso"]
    linhas = _linhas(fabrica, camada_poli, "area_ha, versao")
    assert all(ln["area_ha"] is None and ln["versao"] == 1 for ln in linhas), "o cancelamento desfez tudo"
    assert _historico_n(fabrica, camada_poli) == hist


# ---------------------------------------------------------------- limiar síncrono/job, apagar, copiar/mover, corrigir
def test_ate_5000_e_sincrono_acima_vira_job(sessao_a, camada_poli, fabrica, worker_vivo):
    _quadrados(fabrica.con, camada_poli, 5_001)
    r = _lote(sessao_a, camada_poli["id"], operacao="atribuir", campo="classe", valor="C",
              selecao={"onde": "$n <= 5000"})
    assert r.status_code == 200 and r.json()["execucao"] == "sincrono" and r.json()["alteradas"] == 5_000, r.text[:300]
    r = _lote(sessao_a, camada_poli["id"], operacao="atribuir", campo="classe", valor="B", selecao={"todas": True})
    assert r.status_code == 202 and r.json()["execucao"] == "job", r.text[:300]
    fim = esperar(sessao_a, r.json()["job_id"], timeout=60)
    assert fim["estado"] == "concluido" and fim["resultado"]["alteradas"] == 5_001, fim
    assert {ln["classe"] for ln in _linhas(fabrica, camada_poli, "classe")} == {"B"}
    eventos = sessao_a.get("/api/eventos?limite=50").json()["itens"]
    meus = [e for e in eventos if e["tipo"] == "camadas/lote" and e["alvo_id"] == camada_poli["id"]]
    assert len(meus) >= 3 and {e["propriedades"]["execucao"] for e in meus} >= {"sincrono", "job"}, meus[:3]


def test_apagar_copiar_mover_e_corrigir_geometria(sessao_a, camada_poli, camada_a, fabrica, conexao_plat_app):
    _quadrados(fabrica.con, camada_poli, 20)
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    destino_id, destino_dados = fabrica.criar(
        "demo", ids["demo"], admin_id, geometria="MultiPolygon",
        campos=[{"nome": "titulo", "tipo": "text"}, {"nome": "ordem", "tipo": "integer"}],
        regras_campo={"titulo": {"obrigatorio": True}},
    )
    destino = {"id": destino_id, "dados": destino_dados, "tenant_id": ids["demo"], "admin_id": admin_id}
    # copiar 5 com mapeamento, prévia primeiro
    corpo = {"operacao": "copiar", "selecao": {"onde": "$n <= 5"},
             "destino": {"camada": destino_id, "mapeamento": {"titulo": "nome", "ordem": "n"}}}
    r = _lote(sessao_a, camada_poli["id"], **corpo, previa=True)
    assert r.status_code == 200 and r.json()["previa"][0]["depois"] == {"titulo": "q1", "ordem": 1}, r.text[:300]
    r = _lote(sessao_a, camada_poli["id"], **corpo)
    assert r.status_code == 200 and r.json()["criadas"] == 5, r.text[:300]
    copiadas = _linhas(fabrica, destino, "titulo, ordem, ST_GeometryType(geom) AS t, criado_por")
    assert [c["titulo"] for c in copiadas] == ["q1", "q2", "q3", "q4", "q5"] and copiadas[0]["t"] == "ST_MultiPolygon"
    assert copiadas[0]["criado_por"] == admin_id
    assert len(_linhas(fabrica, camada_poli, "fid")) == 20
    # mover 3 (origem perde, destino ganha); obrigatório do destino vale: sem `titulo` no mapeamento é 422 e nada muda
    r = _lote(sessao_a, camada_poli["id"], operacao="mover", selecao={"onde": "$n > 17"},
              destino={"camada": destino_id, "mapeamento": {"ordem": "n"}})
    assert r.status_code == 422 and r.json()["erro"] == "campo_obrigatorio", r.text[:300]
    assert len(_linhas(fabrica, camada_poli, "fid")) == 20 and len(_linhas(fabrica, destino, "fid")) == 5
    r = _lote(sessao_a, camada_poli["id"], operacao="mover", selecao={"onde": "$n > 17"},
              destino={"camada": destino_id, "mapeamento": {"titulo": "nome", "ordem": "n"}})
    assert r.status_code == 200 and r.json()["criadas"] == 3 and r.json()["apagadas"] == 3, r.text[:300]
    assert len(_linhas(fabrica, camada_poli, "fid")) == 17 and len(_linhas(fabrica, destino, "fid")) == 8
    # destino de outra família de geometria (Point) é recusado antes de gravar
    r = _lote(sessao_a, camada_poli["id"], operacao="copiar", selecao={"todas": True},
              destino={"camada": camada_a["id"], "mapeamento": {"nome": "nome"}})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_geometria_invalido", r.text[:300]
    # apagar em lote por ids
    gids = [str(ln["globalid"]) for ln in _linhas(fabrica, camada_poli, "globalid")[:4]]
    r = _lote(sessao_a, camada_poli["id"], operacao="apagar", selecao={"ids": gids})
    assert r.status_code == 200 and r.json()["apagadas"] == 4, r.text[:300]
    assert len(_linhas(fabrica, camada_poli, "fid")) == 13
    # corrigir geometria: uma gravata-borboleta inválida
    d = camada_poli["dados"]
    contexto(fabrica.con, camada_poli["tenant_id"], usuario_id=admin_id, login="admin")
    with fabrica.con.cursor() as cur:
        cur.execute(f'INSERT INTO "{d["schema"]}"."{d["tabela"]}" (nome, classe, n, geom) VALUES '
                    "('borboleta', 'A', 999, ST_Multi(ST_GeomFromText("
                    "'POLYGON((-46.4 -23.4, -46.3 -23.3, -46.4 -23.3, -46.3 -23.4, -46.4 -23.4))', 4674)))")
    fabrica.con.commit()
    r = _lote(sessao_a, camada_poli["id"], operacao="corrigir_geometria", selecao={"onde": "$n >= 998"}, previa=True)
    assert r.status_code == 200, r.text[:300]
    invalidas = [p for p in r.json()["previa"] if not p["antes"]["valida"]]
    assert len(invalidas) == 1 and "Self-intersection" in invalidas[0]["antes"]["motivo"], r.json()["previa"][-1]
    assert invalidas[0]["depois"]["valida"] is True
    r = _lote(sessao_a, camada_poli["id"], operacao="corrigir_geometria", selecao={"todas": True})
    assert r.status_code == 200 and r.json()["corrigidas"] == 1, r.text[:300]
    with fabrica.con.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{d["schema"]}"."{d["tabela"]}" WHERE NOT ST_IsValid(geom)')
        assert cur.fetchone()["n"] == 0


# ---------------------------------------------------------------- refutação do adversário
def test_refutacao_outra_camada_laco_divisao_por_zero_e_isolamento(sessao_a, sessao_b, camada_poli, camada_b,
                                                                   fabrica):
    _quadrados(fabrica.con, camada_poli, 20)
    hist = _historico_n(fabrica, camada_poli)
    # expressão que tenta ler outra camada/inquilino: a linguagem não tem acesso a nada fora da lista branca
    for expressao, erro in (("$outra_camada_x", "campo_nao_permitido"), ("$tenant_id", "campo_nao_permitido"),
                            ("$criado_por", "campo_nao_permitido"), ("Buscar('camada', 1)", "funcao_desconhecida")):
        r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="n", expressao=expressao,
                  selecao={"todas": True})
        assert r.status_code == 422 and r.json()["erro"] == erro, (expressao, r.text[:300])
    # "laço infinito": a gramática não tem laço nem recursão; aninhamento acima do limite é erro nomeado, não pilha
    r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="n", expressao="(" * 200 + "1" + ")" * 200,
              selecao={"todas": True})
    assert r.status_code == 422 and r.json()["erro"] == "profundidade_excedida", r.text[:300]
    # divisão por zero em UMA feição: nada muda, nos dois caminhos
    for avaliacao in ("sql", "linha_a_linha"):
        r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="area_ha", expressao="$area_m2 / ($n - 5)",
                  selecao={"todas": True}, avaliacao=avaliacao)
        assert r.status_code == 422 and r.json()["erro"] == "divisao_por_zero", (avaliacao, r.text[:300])
    assert all(ln["area_ha"] is None and ln["versao"] == 1 for ln in _linhas(fabrica, camada_poli, "area_ha, versao"))
    assert _historico_n(fabrica, camada_poli) == hist
    # timeout: o tipo de job declara o teto (o worker mata em timeout_s, L0-05) e cada linha tem orçamento próprio
    from app import limites
    from app.jobs.tipos import REGISTRO

    assert REGISTRO["camadas.lote"].timeout_s == limites.LOTE_JOB_TIMEOUT_S and REGISTRO["camadas.lote"].tentativas == 1
    # isolamento: B nunca vê a camada de A (404, não 403), e A não alcança a camada de B
    r = _lote(sessao_b, camada_poli["id"], operacao="atribuir", campo="classe", valor="A", selecao={"todas": True})
    assert r.status_code == 404, r.text
    r = _lote(sessao_a, camada_b["id"], operacao="copiar", selecao={"todas": True},
              destino={"camada": camada_poli["id"], "mapeamento": {}})
    assert r.status_code == 404, r.text
    r = _lote(sessao_a, camada_poli["id"], operacao="copiar", selecao={"todas": True},
              destino={"camada": camada_b["id"], "mapeamento": {}})
    assert r.status_code == 404, r.text
    # campo de rastreio e campo inexistente como alvo
    r = _lote(sessao_a, camada_poli["id"], operacao="atribuir", campo="versao", valor=9, selecao={"todas": True})
    assert r.status_code == 422 and r.json()["erro"] == "campo_de_rastreio", r.text
    r = _lote(sessao_a, camada_poli["id"], operacao="atribuir", campo="nada", valor=9, selecao={"todas": True})
    assert r.status_code == 422 and r.json()["erro"] == "campo_inexistente", r.text
    # inteiro exige inteiro exato nos dois caminhos (o banco arredondaria em silêncio)
    for avaliacao in ("sql", "linha_a_linha"):
        r = _lote(sessao_a, camada_poli["id"], operacao="calcular", campo="n", expressao="$n / 2",
                  selecao={"todas": True}, avaliacao=avaliacao)
        assert r.status_code == 422 and r.json()["erro"] == "tipo_invalido", (avaliacao, r.text[:300])


def test_somente_proprias_restringe_a_selecao(sessao_a, camada_a_somente_proprias, fabrica, usuarios_a):
    """Camada com `somente_proprias`: um editor sem `feicoes.editar_total` só toca as feições que criou; as outras
    ficam fora do lote com aviso (mesma regra do L2-03-a, por seleção em vez de por feição)."""
    cam = camada_a_somente_proprias
    r = sessao_a.post(f"/api/camadas/{cam['id']}/edicoes", json={"adicionar": [
        {"atributos": {"nome": "do admin"}, "geometria": _ponto()}]})
    assert r.status_code == 200, r.text
    editor, _u, _senha = usuarios_a.sessao("editor")
    r = editor.post(f"/api/camadas/{cam['id']}/edicoes", json={"adicionar": [
        {"atributos": {"nome": "do editor"}, "geometria": _ponto(-46.4)}]})
    assert r.status_code == 200, r.text
    r = editor.post(f"/api/camadas/{cam['id']}/lote", json={"operacao": "atribuir", "campo": "nome", "valor": "x",
                                                          "selecao": {"todas": True}})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["alteradas"] == 1 and any("de outros usuários" in a for a in r.json()["avisos"]), r.json()
    nomes = sorted(ln["nome"] for ln in _linhas(fabrica, cam, "nome"))
    assert nomes == ["do admin", "x"]
