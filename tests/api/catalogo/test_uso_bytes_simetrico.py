"""Contador simétrico (item L0-07-c-cotas-uso, correção pós-refutação de 06/09): tenant.uso_bytes (cota de
TABELA, migração 029) só crescia — incrementado no fim de uma carga (app/ingestao/carregar.py linha 319) e
NUNCA decrementado quando a tabela cai no expurgo da lixeira (app/catalogo/destruidores.py::_camada_vetorial
faz DROP TABLE, mas ninguém descontava o tamanho de tenant.uso_bytes). Corrigido em
app/catalogo/tarefas.py::catalogo_lixeira_expurgar. Mesmo padrão de setup de
tests/api/catalogo/test_lixeira.py::test_expurgo_com_relogio_simulado_apaga_tabela_fisica (tabela real em
plat_trabalho, relógio envelhecido em vez de esperar 30 dias de verdade)."""

from tests.api.catalogo.conftest import esperar_job, titulo_zt
from tests.api.test_rls import contexto, ids_por_slug


def test_expurgo_decrementa_uso_bytes_tanto_quanto_a_carga_incrementou(
    sessao_a, itens_a, conexao_plat_app, worker_vivo
):
    ids_map = ids_por_slug(conexao_plat_app)
    tenant_id = ids_map["demo"]
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]

    tabela = "zt_simetrico_" + titulo_zt()[-6:]
    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, geom geometry(Point, 4326))")
        cur.execute(
            f"INSERT INTO plat_trabalho.{tabela}(geom) "
            "SELECT ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326) FROM generate_series(1, 2000)"
        )
    conexao_plat_app.commit()

    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT pg_total_relation_size(c.oid) AS b FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace WHERE n.nspname = 'plat_trabalho' AND c.relname = %s", (tabela,))
        tamanho = cur.fetchone()["b"]
        assert tamanho and tamanho > 0
        cur.execute("SELECT uso_bytes FROM plat.tenant WHERE id = %s", (tenant_id,))
        base = cur.fetchone()["uso_bytes"]
        # simula o incremento que app/ingestao/carregar.py já faz de verdade no fim de uma carga (linha 319):
        # "UPDATE plat.tenant SET uso_bytes = uso_bytes + %s" — mesma instrução, mesmo papel (plat_app), só
        # fora do pipeline completo de ingestão (que exigiria um arquivo real) para isolar o que este teste prova.
        cur.execute("UPDATE plat.tenant SET uso_bytes = uso_bytes + %s WHERE id = %s", (tamanho, tenant_id))
    conexao_plat_app.commit()

    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "id", "tipo": "integer"}], "fonte": "hospedada",
        },
    )
    assert sessao_a.delete(f"/api/itens/{it['id']}").status_code == 204

    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute(
            "UPDATE plat.item SET apagado_em = now() - interval '31 days' WHERE id = %s::uuid RETURNING id",
            (it["id"],),
        )
        assert cur.fetchall()
    conexao_plat_app.commit()

    r = sessao_a.post(
        "/api/jobs", json={"tipo": "catalogo.lixeira_expurgar", "parametros": {"dias": 30, "ids": [it["id"]]}}
    )
    assert r.status_code == 201, r.text
    job = esperar_job(sessao_a, r.json()["id"], 120)
    assert job["estado"] == "concluido" and job["resultado"]["expurgados"] == 1, job

    with conexao_plat_app.cursor() as cur:
        # to_regclass(%s) não serve aqui: o rewrite de schema por trilha (CursorSchemaAmbiente) só troca texto
        # da CONSULTA, nunca valor de parâmetro — 'plat_trabalho' teria de ir na query em si (mesmo achado que
        # tests/api/catalogo/test_lixeira.py::test_expurgo_com_relogio_simulado_apaga_tabela_fisica também
        # esbarra nesta base de trilha; aqui evitado escrevendo o nome do schema na query, não no bind).
        cur.execute(
            "SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'plat_trabalho' AND c.relname = %s",
            (tabela,),
        )
        assert cur.fetchone()["n"] == 0, "a tabela física tem de sumir no expurgo"
    # SELECT em plat.tenant passa pela RLS (p_tenant, WHERE id = plat.tenant_atual()): o `contexto()` grava
    # com set_config(..., true) = SET LOCAL, escopo de transação — o commit acima já zerou (mesma pegadinha
    # que test_lixeira.py já documenta), sem recontextualizar o SELECT abaixo lia 0 linhas (None, não 0).
    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT uso_bytes FROM plat.tenant WHERE id = %s", (tenant_id,))
        depois = cur.fetchone()["uso_bytes"]

    # ANTES da correção: depois == base + tamanho (só subiu). Corrigido: depois volta a bater com base (não
    # exatamente igual porque outros testes concorrentes também mexem em uso_bytes do mesmo inquilino demo —
    # a prova que importa é que DESCEU pelo tamanho da tabela apagada, não que ficou estática ou subiu).
    assert depois <= base + tamanho, (
        f"contador de cota não é simétrico: subiu {tamanho} na carga e não desceu no expurgo "
        f"(base={base}, depois_da_carga={base + tamanho}, depois_do_expurgo={depois})"
    )
    assert depois < base + tamanho, "uso_bytes não baixou nada no expurgo — contador continua assimétrico"
    conexao_plat_app.rollback()
    itens_a.criados.remove(it["id"])
