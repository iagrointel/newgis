"""Correção T2 (achado do testador): a role plat_app, mesmo com contexto de inquilino, não leva um job a rodando/
concluido/falhou nem forja resultado. Camadas provadas: REVOKE UPDATE em plat.job; gatilho job_transicao (INSERT nasce
pendente e limpo; transições só com plat.via_worker ligado pelas funções do worker); EXECUTE das funções que mudam
estado só para a role plat_worker; plat_worker sem SELECT direto em plat.job; job_cancelar e job_progresso são o que
sobra para API e filho. Também: jobs_expurgar apaga marcadores e passos órfãos e só roda no inquilino plataforma."""

import uuid

import psycopg2
import psycopg2.extras
import pytest

from tests import jobs_sessao
from tests.api.jobs.conftest import criar_job, esperar

JOB_INSERT = ("INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s, "
              "agendado_para{cols}) VALUES (%s, %s, 'prova.progresso', '{{\"duracao_s\": 0, \"passos\": 1}}', "
              "false, 256, 60, '2099-01-01'{vals}) RETURNING id")


def _ctx(con, sessao):
    cur = con.cursor()
    jobs_sessao.contexto(cur, sessao[1], sessao[2], "admin")
    return cur


def test_update_forjado_pendente_para_rodando_e_recusado(conexao_plat_app, sessao_demo):
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute(JOB_INSERT.format(cols="", vals=""), (sessao_demo[1], sessao_demo[2]))
    jid = cur.fetchone()["id"]
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
        cur.execute("UPDATE plat.job SET estado = 'rodando', worker = 'forjado' WHERE id = %s", (jid,))
    conexao_plat_app.rollback()
    cur = _ctx(conexao_plat_app, sessao_demo)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
        cur.execute("UPDATE plat.job SET estado = 'concluido', resultado = '{\"forjado\": true}' WHERE id = %s", (jid,))
    conexao_plat_app.rollback()


def test_insert_forjado_ja_concluido_e_recusado_pelo_gatilho(conexao_plat_app, sessao_demo):
    cur = _ctx(conexao_plat_app, sessao_demo)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="nasce pendente"):
        cur.execute(JOB_INSERT.format(cols=", estado, resultado, terminado_em",
                                      vals=", 'concluido', '{\"forjado\": true}', now()"),
                    (sessao_demo[1], sessao_demo[2]))
    conexao_plat_app.rollback()
    cur = _ctx(conexao_plat_app, sessao_demo)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="nasce pendente"):
        cur.execute(JOB_INSERT.format(cols=", tentativa, worker", vals=", 1, 'forjado'"),
                    (sessao_demo[1], sessao_demo[2]))
    conexao_plat_app.rollback()


def test_plat_app_nao_executa_as_funcoes_do_worker(conexao_plat_app, sessao_demo):
    chamadas = [
        "SELECT * FROM plat.job_pegar('forjado', true)",
        "SELECT plat.job_terminar(%s, 'forjado', 'concluido', '{}', NULL, NULL)",
        "SELECT plat.job_devolver(%s, 'forjado', 'x', false, 0, 5, NULL)",
        "SELECT plat.job_ceifar(60, 5)",
        "SELECT plat.worker_registrar('forjado', 1, 'x', 'x', 1)",
        "SELECT * FROM plat.agenda_vencidas(now())",
        "SELECT plat.via_worker_ligar()",
    ]
    for sql in chamadas:
        cur = _ctx(conexao_plat_app, sessao_demo)
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
            cur.execute(sql, (str(uuid.uuid4()),) if "%s" in sql else None)
        conexao_plat_app.rollback()


def test_worker_nao_le_plat_job_direto_mas_pega_pela_funcao(env, cliente_demo, worker_vivo):
    assert env.get("PLAT_DSN_WORKER"), (
        "PLAT_DSN_WORKER ausente (item L7-19: mora em /etc/plat/segredos/PLAT_DSN_WORKER, injetado pelo Makefile)"
    )
    w = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=psycopg2.extras.RealDictCursor)
    w.autocommit = True
    try:
        with w.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("SELECT count(*) FROM plat.job")
        with w.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("SELECT count(*) FROM plat.usuario")
        with w.cursor() as cur:  # o que o worker pode: as funções da fila (aqui a de cota do relógio)
            cur.execute("SELECT plat.jobs_no_dia(1) AS n")
            assert cur.fetchone()["n"] >= 0
    finally:
        w.close()


def test_progresso_so_do_proprio_job_e_worker(conexao_plat_app, sessao_demo, cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 30, "passos": 30})
    rodando = esperar(cliente_demo, job["id"], timeout=60,
                      condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 1)
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("SELECT plat.job_progresso(%s, 'forjado', 99, 'x') AS r", (job["id"],))
    assert cur.fetchone()["r"] is None, "job_progresso aceitou outro nome de worker"
    conexao_plat_app.rollback()
    depois = cliente_demo.get(f"/api/jobs/{job['id']}").json()
    assert depois["progresso"] < 99 and depois["worker"] == rodando["worker"]
    assert cliente_demo.post(f"/api/jobs/{job['id']}/cancelar").status_code == 202
    assert esperar(cliente_demo, job["id"], timeout=30)["estado"] == "cancelado"


def test_progresso_acima_de_100_e_grampeado_em_100(conexao_plat_app, sessao_demo, cliente_demo, worker_vivo):
    """Refutação do portão L0-05-b ('envia progresso 150%', achado do testador T3: nunca tinha teste). O worker
    certo (nome real do job em execução) chamando com 150 tem de gravar 100, nunca 150 nem erro: `plat.
    job_progresso` grampeia com `greatest(0, least(100, p_progresso))` (migração 006) e a coluna tem `CHECK
    (progresso BETWEEN 0 AND 100)` como segunda trava (migração 004)."""
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 30, "passos": 30})
    rodando = esperar(cliente_demo, job["id"], timeout=60,
                      condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 1)
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("SELECT plat.job_progresso(%s, %s, 150, 'acima do limite') AS r", (job["id"], rodando["worker"]))
    assert cur.fetchone()["r"] is not None, "job_progresso recusou o worker certo do próprio job"
    cur.execute("SELECT progresso FROM plat.job WHERE id = %s", (job["id"],))
    assert cur.fetchone()["progresso"] == 100, "progresso de 150 não foi grampeado em 100"
    conexao_plat_app.rollback()  # não commita por cima do worker de verdade que segue rodando o mesmo job
    assert cliente_demo.post(f"/api/jobs/{job['id']}/cancelar").status_code == 202
    assert esperar(cliente_demo, job["id"], timeout=30)["estado"] == "cancelado"


def test_cancelar_pela_api_continua_funcionando_e_estado_final_nao_volta(cliente_demo, worker_vivo, conexao_plat_app,
                                                                        sessao_demo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})
    fim = esperar(cliente_demo, job["id"], timeout=60)
    assert fim["estado"] == "concluido"
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("SELECT plat.job_cancelar(%s, %s) AS r", (job["id"], sessao_demo[2]))
    assert cur.fetchone()["r"] == "concluido"
    conexao_plat_app.rollback()
    assert cliente_demo.post(f"/api/jobs/{job['id']}/cancelar").json()["erro"] == "estado_final"


def test_expurgo_apaga_marcadores_e_passos_orfaos_so_no_inquilino_plataforma(conexao_plat_app, sessao_demo, env):
    orfao = str(uuid.uuid4())
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("INSERT INTO plat_trabalho.marcadores(job_id, marcador) VALUES (%s, %s)", (orfao, str(uuid.uuid4())))
    cur.execute("INSERT INTO plat_trabalho.passos(job_id, passo) VALUES (%s, 1)", (orfao,))
    conexao_plat_app.commit()
    cur = _ctx(conexao_plat_app, sessao_demo)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="plataforma"):
        cur.execute("SELECT * FROM plat.jobs_expurgar(3650, 3650)")
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login('plataforma', 'admin')")
        plataforma = cur.fetchone()
    assert plataforma is not None, "admin do inquilino plataforma não semeado (install.sh)"
    cur = _ctx(conexao_plat_app, (None, plataforma["tenant_id"], plataforma["usuario_id"]))
    cur.execute("SELECT * FROM plat.jobs_expurgar(3650, 3650)")
    r = cur.fetchone()
    conexao_plat_app.commit()
    assert r["jobs_apagados"] == 0 and r["marcadores_apagados"] >= 1 and r["passos_apagados"] >= 1
    with conexao_plat_app.cursor() as cur:  # plat_trabalho não tem RLS: o órfão sumiu
        cur.execute("SELECT count(*) AS n FROM plat_trabalho.marcadores WHERE job_id = %s", (orfao,))
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat_trabalho.passos WHERE job_id = %s", (orfao,))
        assert cur.fetchone()["n"] == 0
    conexao_plat_app.rollback()
    # segunda chamada: nada sobrou (a conferência entre inquilinos é da própria função, sob SECURITY DEFINER)
    cur = _ctx(conexao_plat_app, (None, plataforma["tenant_id"], plataforma["usuario_id"]))
    cur.execute("SELECT * FROM plat.jobs_expurgar(3650, 3650)")
    r2 = cur.fetchone()
    conexao_plat_app.commit()
    assert r2["marcadores_apagados"] == 0 and r2["passos_apagados"] == 0, r2
