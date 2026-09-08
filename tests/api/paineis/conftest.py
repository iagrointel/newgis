"""Semeadura do painel de exemplo (item L2-06-a-modelo-painel-fontes, `plat.painel_exemplo_semear`,
migração `20260906T2145_documento_painel.sql`) para os testes de dados do painel: mesma disciplina de
`tests/e2e/test_tarefas.py::test_primeira_pintura_com_mil_jobs` (SECURITY DEFINER de demonstração, pulado
se `plat.ambiente.semear_demo = false`)."""

import pytest

# ids fixos da semente (declarados na própria função SQL) — os dois usados nos testes desta pasta
FONTE_OCORRENCIAS = "01JPA1NEKEXEMPK0F0NTE0000A"
FONTE_AGUA = "01JPA1NEKEXEMPK0F0NTE0000B"


def _liberar_schema_de_dado_recem_criado(slug: str) -> None:
    """`d_<slug>` (schema de dado da camada física) é compartilhado entre produção e trilhas (achado
    07/09 do trilha_ambiente.sh, seção 'c2'): a trilha ganha GRANT nas tabelas que já EXISTIAM quando o
    ambiente foi montado, mas `plat.painel_exemplo_semear` cria uma tabela NOVA depois disso — sem este
    passo o SELECT da própria API falha com `permission denied for table c_...`, um erro de PRIVILÉGIO
    disfarçado de bug de produto. Só roda quando o teste está numa trilha isolada (`PLAT_SCHEMA` != `plat`);
    em produção este bloco nunca executa (o app não chama sudo)."""
    import os
    import subprocess

    schema = os.environ.get("PLAT_SCHEMA", "plat")
    if schema == "plat":
        return
    app_role, worker_role = f"{schema}_app", f"{schema}_worker"
    subprocess.run(
        [
            "sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-v", "ON_ERROR_STOP=0", "-q", "-c",
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "d_{slug}" TO {app_role}, {worker_role}',
        ],
        capture_output=True, text=True, check=False,
    )


def _semear(con, slug: str) -> dict:
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT plat.semente_demo_habilitada() AS ligada")
        if not cur.fetchone()["ligada"]:
            pytest.skip("plat.ambiente.semear_demo = false nesta instalação")
        cur.execute("SELECT camada_id, painel_id FROM plat.painel_exemplo_semear(%s)", (slug,))
        r = cur.fetchone()
    con.commit()
    _liberar_schema_de_dado_recem_criado(slug)
    return {"camada_id": str(r["camada_id"]), "painel_id": str(r["painel_id"])}


@pytest.fixture(scope="session")
def painel_exemplo_demo(conexao_plat_app_sessao):
    return _semear(conexao_plat_app_sessao, "demo")


@pytest.fixture(scope="session")
def painel_exemplo_demo2(conexao_plat_app_sessao):
    return _semear(conexao_plat_app_sessao, "demo2")


@pytest.fixture(scope="session")
def conexao_plat_app_sessao(env):
    """Mesma coisa que `conexao_plat_app` (tests/conftest.py) mas de ESCOPO DE SESSÃO — a semeadura só
    precisa rodar uma vez por rodada da suíte, e a fixture padrão fecha a conexão a cada teste."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    yield con
    con.close()
