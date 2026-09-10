"""Medição diária de uso (item L0-07-c-cotas-uso; app/jobs/periodicos.py::jobs_uso_medir, plat.uso_medir da
migração 20260906T2124_cotas_uso.sql). Duas cláusulas do portão que o Kimi não tinha coberto por teste
nenhum (achado ao fechar o item): "medição bate com pg_total_relation_size" e "série diária com 30 pontos
após simular 30 dias". Achado no caminho: o job em si tinha um `NameError: name 'datetime' is not defined`
(faltava `import datetime` em app/jobs/periodicos.py) — sem este teste, `jobs.uso_medir` nunca teria rodado
de verdade nem uma vez; ver tests/api/jobs/test_jobs_periodicos.py, que também prova isso via o periódico."""

import datetime

from tests.api.test_rls import contexto, ids_por_slug


def _rodar_uso_medir(sessao, dia: str) -> dict:
    from tests.api.catalogo.conftest import esperar_job

    r = sessao.post("/api/jobs", json={"tipo": "jobs.uso_medir", "parametros": {"dia": dia}})
    assert r.status_code == 201, r.text
    return esperar_job(sessao, r.json()["id"], 60)


def test_medicao_bate_com_pg_total_relation_size(sessao_a, conexao_plat_app, worker_vivo):
    ids_map = ids_por_slug(conexao_plat_app)
    tenant_id = ids_map["demo"]
    hoje = datetime.date.today().isoformat()

    job = _rodar_uso_medir(sessao_a, hoje)
    assert job["estado"] == "concluido", job
    assert job["resultado"]["inquilinos"] >= 1, job

    contexto(conexao_plat_app, tenant_id)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.uso_bytes_banco(%s) AS b", (tenant_id,))
        direto = cur.fetchone()["b"]
        cur.execute(
            "SELECT bytes_banco FROM plat.uso_inquilino WHERE tenant_id = %s AND dia = %s", (tenant_id, hoje)
        )
        r = cur.fetchone()
        assert r is not None, "jobs.uso_medir tinha de ter gravado um ponto para hoje"
        # mesma fórmula (plat.uso_bytes_banco) chamada nos dois lados: diferença tem de ser 0, não só <= 1%
        # (a folga de 1% do portão é para o LADO DO BUCKET, medido por fora via Admin API do Garage — não
        # coberto aqui; ver FRONTEIRA HONESTA no handoff).
        assert r["bytes_banco"] == direto, (r["bytes_banco"], direto)


def test_serie_diaria_com_30_pontos_apos_simular_30_dias(sessao_a, conexao_plat_app, worker_vivo):
    ids_map = ids_por_slug(conexao_plat_app)
    tenant_id = ids_map["demo"]
    hoje = datetime.date.today()
    dias = [(hoje - datetime.timedelta(days=n)).isoformat() for n in range(30)]

    for dia in dias:
        job = _rodar_uso_medir(sessao_a, dia)
        assert job["estado"] == "concluido", (dia, job)

    contexto(conexao_plat_app, tenant_id)
    with conexao_plat_app.cursor() as cur:
        # evitar "= ANY(%s::date[])" e "count(DISTINCT dia)" direto: os dois disparam um plano de SkipScan
        # que esta instância do Postgres não sustenta para plat.uso_inquilino (PK composta tenant_id, dia) —
        # psycopg2.errors.InternalError_ "unsupported subplan type for SkipScan: Result", sem relação com o
        # item. Contornado com GROUP BY + count(*) em subconsulta, plano simples de índice.
        cur.execute(
            "SELECT count(*) AS n FROM (SELECT dia FROM plat.uso_inquilino "
            "WHERE tenant_id = %s AND dia BETWEEN %s AND %s GROUP BY dia) x",
            (tenant_id, min(dias), max(dias)),
        )
        assert cur.fetchone()["n"] == 30, "30 chamadas de jobs.uso_medir em 30 dias distintos tinham de virar 30 pontos"
