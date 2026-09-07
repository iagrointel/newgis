"""Agendas (ADR 0003 seção 7): cron inválida/fuso inválido/intervalo < 15 min = 422; criação com proxima_em; o
relógio (`agenda.tick` com instante injetado) dispara 3 ocorrências exatamente uma vez cada, mesmo com dois relógios
concorrentes; 5 falhas seguidas pausam; rodar-agora cria job; cota de agendas = 413; pausar/retomar; periódico
`expurgo diário` sincronizado pelo worker no inquilino técnico."""

import datetime
import threading
import time

import psycopg2
import psycopg2.extras
import pytest

from app.jobs import agenda as mod_agenda
from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)
from tests import jobs_sessao
from tests.api.jobs.conftest import esperar

# serial (07/09): estes testes injetam um instante no MESMO relógio de agendas que a unidade de jobs viva
# executa a cada 30 s (app/jobs/worker.py -> mod_agenda.tick). Quando a rodada em paralelo atrasa o teste e o
# relógio de parede cruza a fronteira da cron, a unidade dispara a mesma ocorrência e sobra um job: medido
# 'assert 2 == 0 + 1' e 'assert 3 == 1 + 1'. Correndo sozinho o teste leva segundos e não cruza a fronteira.
# Isto é redução de risco, não eliminação: a unidade de jobs continua viva ao lado.
pytestmark = pytest.mark.serial

UTC = datetime.UTC


@pytest.fixture
def nome():
    return f"teste-{time.time_ns()}"


def _criar(cliente, nome, tipo="prova.progresso", parametros=None, cron="*/15 * * * *", **extra):
    corpo = {"nome": nome, "tipo": tipo, "parametros": parametros or {"duracao_s": 0, "passos": 1}, "cron": cron,
             **extra}
    return cliente.post("/api/agendas", json=corpo)


def _apagar(cliente, agenda_id):
    assert cliente.delete(f"/api/agendas/{agenda_id}").status_code == 204


def test_validacoes_422_e_409(cliente_demo, nome):
    assert _criar(cliente_demo, nome, cron="61 * * * *").json()["erro"] == "cron_invalida"
    assert _criar(cliente_demo, nome, cron="* * * *").json()["erro"] == "cron_invalida"
    assert _criar(cliente_demo, nome, cron="*/5 * * * *").json()["erro"] == "intervalo_minimo"
    assert _criar(cliente_demo, nome, fuso="Marte/Olympus").json()["erro"] == "fuso_invalido"
    assert _criar(cliente_demo, nome, tipo="nao.existe").json()["erro"] == "tipo_desconhecido"
    r = _criar(cliente_demo, nome)
    assert r.status_code == 201, r.text
    try:
        assert _criar(cliente_demo, nome).status_code == 409
        assert r.json()["proxima_em"] > datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
        assert r.json()["fuso"] == "America/Sao_Paulo" and r.json()["ativa"] is True
    finally:
        _apagar(cliente_demo, r.json()["id"])


def test_relogio_dispara_cada_ocorrencia_uma_vez_com_dois_relogios(cliente_demo, worker_vivo, env, nome):
    r = _criar(cliente_demo, nome)
    assert r.status_code == 201, r.text
    agenda = r.json()
    proxima = datetime.datetime.fromisoformat(agenda["proxima_em"].replace("Z", "+00:00"))
    # o relógio é do worker: só a role plat_worker executa agenda_vencidas/agenda_enfileirar (006)
    cons = [psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=CursorSchemaAmbiente) for _ in range(2)]
    for c in cons:
        c.autocommit = True
    try:
        criados = []
        for k in range(3):
            agora = proxima + datetime.timedelta(minutes=15 * k, seconds=5)
            resultados: list = []

            def relogio(c, a=agora, saida=resultados):
                saida.extend(mod_agenda.tick(c, a))

            threads = [threading.Thread(target=relogio, args=(c,)) for c in cons]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            # o relógio enfileira TODA agenda vencida (inclusive as de outras sessões de teste): conta-se só a desta
            meus = [j["id"] for j in cliente_demo.get("/api/jobs", params={"agenda_id": agenda["id"], "limite": 50})
                    .json()["itens"]]
            assert len(meus) == k + 1, f"ocorrência {k}: {len(meus)} jobs desta agenda (2 relógios; ids {resultados})"
            criados = meus
        lista = cliente_demo.get("/api/jobs", params={"agenda_id": agenda["id"], "limite": 50}).json()
        assert lista["total"] == 3 and {j["id"] for j in lista["itens"]} == set(criados)
        programados = sorted(j["programado_para"] for j in lista["itens"])
        assert len(set(programados)) == 3
        for jid in criados:
            fim = esperar(cliente_demo, jid, timeout=60)
            assert fim["estado"] == "concluido" and fim["agenda_id"] == agenda["id"] and fim["usuario_id"]
        depois = cliente_demo.get(f"/api/agendas/{agenda['id']}").json()
        assert depois["ultimo_estado"] == "concluido" and depois["falhas_seguidas"] == 0
        assert depois["ultimo_job_id"] in criados
    finally:
        for c in cons:
            c.close()
        _apagar(cliente_demo, agenda["id"])


def test_cinco_falhas_seguidas_pausam_a_agenda(cliente_demo, worker_vivo, env, nome):
    r = _criar(cliente_demo, nome, tipo="prova.falha", parametros={"definitiva": True})
    assert r.status_code == 201, r.text
    agenda = r.json()
    proxima = datetime.datetime.fromisoformat(agenda["proxima_em"].replace("Z", "+00:00"))
    con = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    try:
        for k in range(5):
            mod_agenda.tick(con, proxima + datetime.timedelta(minutes=15 * k, seconds=5))
            meus = cliente_demo.get("/api/jobs", params={"agenda_id": agenda["id"], "ordenar": "criado_em:desc",
                                                         "limite": 5}).json()["itens"]
            assert len(meus) == k + 1, meus
            assert esperar(cliente_demo, meus[0]["id"], timeout=60)["estado"] == "falhou"
            a = cliente_demo.get(f"/api/agendas/{agenda['id']}").json()
            assert a["falhas_seguidas"] == k + 1
        assert a["ativa"] is False and a["proxima_em"] is None
        assert cliente_demo.post(f"/api/agendas/{agenda['id']}/pausar").json()["erro"] == "ja_pausada"
        antes = datetime.datetime.now(UTC)
        retomada = cliente_demo.post(f"/api/agendas/{agenda['id']}/retomar").json()
        assert retomada["ativa"] is True and retomada["falhas_seguidas"] == 0 and retomada["proxima_em"]
        assert retomada["proxima_em"] > antes.strftime("%Y-%m-%dT%H:%M:%S"), "retomar recomeça do relógio real"
        mod_agenda.tick(con, antes)
        depois = cliente_demo.get("/api/jobs", params={"agenda_id": agenda["id"]}).json()["total"]
        assert depois == 5, "agenda retomada não pode reenfileirar ocorrências antigas"
    finally:
        con.close()
        _apagar(cliente_demo, agenda["id"])


def test_rodar_agora_pausar_retomar_atualizar(cliente_demo, worker_vivo, nome):
    agenda = _criar(cliente_demo, nome).json()
    try:
        r = cliente_demo.post(f"/api/agendas/{agenda['id']}/rodar-agora")
        assert r.status_code == 201 and r.json()["agenda_id"] == agenda["id"]
        assert esperar(cliente_demo, r.json()["id"], timeout=60)["estado"] == "concluido"
        p = cliente_demo.post(f"/api/agendas/{agenda['id']}/pausar").json()
        assert p["ativa"] is False and p["proxima_em"] is None
        assert cliente_demo.post(f"/api/agendas/{agenda['id']}/retomar").json()["ativa"] is True
        assert cliente_demo.post(f"/api/agendas/{agenda['id']}/retomar").json()["erro"] == "ja_ativa"
        u = cliente_demo.put(f"/api/agendas/{agenda['id']}", json={"cron": "0 4 * * *", "fuso": "America/Manaus"})
        assert u.status_code == 200 and u.json()["cron"] == "0 4 * * *" and u.json()["fuso"] == "America/Manaus"
        assert u.json()["proxima_em"].endswith("08:00:00.000Z") or u.json()["proxima_em"].endswith("08:00:00Z")
        assert cliente_demo.put(f"/api/agendas/{agenda['id']}", json={"cron": "*/1 * * * *"}).status_code == 422
        lista = cliente_demo.get("/api/agendas", params={"ativa": True}).json()
        assert any(a["id"] == agenda["id"] for a in lista["itens"])
    finally:
        _apagar(cliente_demo, agenda["id"])
    assert cliente_demo.get(f"/api/agendas/{agenda['id']}").status_code == 404


def test_cota_de_agendas_413_e_rls(cliente_demo, cliente_demo2, conexao_plat_app, sessao_demo2, nome):
    existentes = cliente_demo2.get("/api/agendas", params={"limite": 200}).json()["total"]
    with conexao_plat_app.cursor() as cur:  # cota = o que B já tem + 1 (outra rodada pode ter agenda viva em B)
        jobs_sessao.contexto(cur, sessao_demo2[1], sessao_demo2[2], "admin")
        cur.execute("UPDATE plat.tenant SET config = config || jsonb_build_object('cota_agendas', %s) WHERE id = %s",
                    (existentes + 1, sessao_demo2[1]))
    conexao_plat_app.commit()
    a = None
    try:
        r = _criar(cliente_demo2, nome)
        assert r.status_code == 201, r.text
        a = r.json()
        r2 = _criar(cliente_demo2, nome + "-2")
        assert r2.status_code == 413 and r2.json()["erro"] == "cota_agendas", r2.text
        assert cliente_demo.get(f"/api/agendas/{a['id']}").status_code == 404, "agenda de demo2 visível para demo"
        assert cliente_demo.post(f"/api/agendas/{a['id']}/pausar").status_code == 404
    finally:
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, sessao_demo2[1], sessao_demo2[2], "admin")
            cur.execute("UPDATE plat.tenant SET config = config - 'cota_agendas' WHERE id = %s", (sessao_demo2[1],))
        conexao_plat_app.commit()
        if a:
            _apagar(cliente_demo2, a["id"])


def test_cota_diaria_de_jobs_413(cliente_demo2, conexao_plat_app, sessao_demo2):
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, sessao_demo2[1], sessao_demo2[2], "admin")
        cur.execute("UPDATE plat.tenant SET config = config || '{\"cota_jobs_dia\": 0}' WHERE id = %s",
                    (sessao_demo2[1],))
    conexao_plat_app.commit()
    try:
        r = cliente_demo2.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"duracao_s": 0}})
        assert r.status_code == 413 and r.json()["erro"] == "cota_jobs_dia" and r.json()["detalhe"]["cota"] == 0
    finally:
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, sessao_demo2[1], sessao_demo2[2], "admin")
            cur.execute("UPDATE plat.tenant SET config = config - 'cota_jobs_dia' WHERE id = %s", (sessao_demo2[1],))
        conexao_plat_app.commit()


def test_periodico_expurgo_sincronizado_no_inquilino_plataforma(env):
    """O worker faz o upsert na partida; a leitura aqui é pela função de vencidas (role do worker) com data futura."""
    con = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT nome, tipo, cron, fuso, tenant_id FROM plat.agenda_vencidas(now() + interval '2 days') "
                        "WHERE nome = 'expurgo diário'")
            r = cur.fetchone()
        con.rollback()
    finally:
        con.close()
    assert r is not None, "worker não sincronizou o periódico 'expurgo diário' (partida do plat-worker)"
    assert r["tipo"] == "jobs.expurgo" and r["cron"] == "30 3 * * *" and r["fuso"] == "America/Sao_Paulo"
