"""Correção T2 (2) (achado do testador): dois workers com o mesmo nome-base (o padrão é o hostname) nunca roubam job
um do outro. Antes, `job_ceifar(60, nome)` na partida do homônimo devolvia os jobs do worker vivo (reexecução do zero,
reinicios += 1). Agora a identidade é `<base>:<pid>`, registrada em plat.worker com heartbeat, e a ceifa só devolve
job cujo sinal venceu (migração 012). O teste reproduz o cenário do achado: sobe um segundo worker com o MESMO nome-base
do worker que está executando o job e prova que o job não muda de dono, não volta a zero e termina com reinicios = 0."""

import psycopg2
import psycopg2.extras

from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)
from tests.api.jobs.conftest import criar_job, esperar


def test_homonimo_nao_rouba_job_do_worker_vivo(cliente_demo, worker_vivo, iniciar_worker, env):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 24, "passos": 24})
    rodando = esperar(cliente_demo, job["id"], timeout=90,
                      condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 8)
    dono = rodando["worker"]
    base, pid = dono.rsplit(":", 1)
    assert pid.isdigit(), dono
    # o homônimo: mesmo nome-base do dono, processo novo (pid diferente), partida com ceifa
    homonimo = iniciar_worker(base, 1)
    assert homonimo.nome != dono and homonimo.nome.startswith(base + ":")
    assert homonimo.saude()["nome_base"] == base
    # 6 s depois da partida do homônimo: o job continua do mesmo dono, com progresso adiante do que estava
    depois = esperar(cliente_demo, job["id"], timeout=30,
                     condicao=lambda j: j["progresso"] >= rodando["progresso"] + 8 or j["estado"] != "rodando")
    assert depois["estado"] == "rodando" and depois["worker"] == dono, depois
    assert depois["reinicios"] == 0 and depois["progresso"] > rodando["progresso"], depois
    fim = esperar(cliente_demo, job["id"], timeout=90)
    assert fim["estado"] == "concluido" and fim["reinicios"] == 0 and fim["tentativa"] == 1 and fim["worker"] == dono
    assert fim["proveniencia"]["worker"] == dono


def test_ceifa_e_so_por_heartbeat_vencido_nunca_por_nome(env, cliente_demo, worker_vivo, iniciar_worker):
    """Com o worker dono vivo (heartbeat recente), job_ceifar não devolve nada dele; não existe assinatura por nome."""
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 12, "passos": 12})
    rodando = esperar(cliente_demo, job["id"], timeout=90, condicao=lambda j: j["estado"] == "rodando")
    w = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=CursorSchemaAmbiente)
    w.autocommit = True
    try:
        with w.cursor() as cur:
            # heartbeats (job e worker) são de 10 s: com limite 30 s nada do worker vivo vence; por nome não há como
            cur.execute("SELECT plat.job_ceifar(30, 5) AS n")
            n = cur.fetchone()["n"]
        with w.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM pg_proc WHERE proname = 'job_ceifar' "
                        "AND pronamespace = 'plat'::regnamespace AND pronargs = 3")
            assert cur.fetchone()["n"] == 0, "a assinatura job_ceifar(limite, nome, max) foi removida pela 012"
    finally:
        w.close()
    depois = cliente_demo.get(f"/api/jobs/{job['id']}").json()
    assert depois["worker"] == rodando["worker"] and depois["reinicios"] == 0, (n, depois)
    assert esperar(cliente_demo, job["id"], timeout=90)["estado"] == "concluido"
