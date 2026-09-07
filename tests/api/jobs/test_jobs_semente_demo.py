"""Semeadura de demonstração (migração 014, correção T2 (3) do L0-05). O e2e dos 1.000 jobs semeava por SQL direto e
a 006 passou a barrar isso: a 006 continua como está e a semeadura passou a ser uma função de nome explícito,
plat.jobs_semear_demo, com quatro guardas. Este arquivo prova as quatro e prova que nada da 006 foi afrouxado:
plat_app não liga o interruptor, não forja INSERT concluído e não muda estado nem com o GUC plat.via_worker ligado
por conta própria."""

import psycopg2
import pytest

from tests import jobs_sessao

# serial (07/09): liga e desliga o interruptor da semente de demonstração, que vale para o inquilino inteiro.
pytestmark = pytest.mark.serial

SEMEAR = "SELECT plat.jobs_semear_demo(%s, %s, %s::jsonb, %s) AS n"


def _ctx(con, sessao):
    cur = con.cursor()
    jobs_sessao.contexto(cur, sessao[1], sessao[2], "admin")
    return cur


def _ligada(cur) -> bool:
    cur.execute("SELECT plat.semente_demo_habilitada() AS ligada")
    return bool(cur.fetchone()["ligada"])


def test_interruptor_e_so_leitura_para_a_api(conexao_plat_app, sessao_demo):
    """plat.ambiente é a guarda 1: a role da API lê e não escreve (a 001 dá UPDATE por privilégio padrão em toda
    tabela nova do schema, por isso a 014 revoga explicitamente)."""
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("SELECT nome, semear_demo FROM plat.ambiente")
    linha = cur.fetchone()
    assert linha["nome"] in ("dev", "producao")
    for sql in ("UPDATE plat.ambiente SET semear_demo = true",
                "DELETE FROM plat.ambiente",
                "INSERT INTO plat.ambiente (unico, nome, semear_demo) VALUES (false, 'dev', true)"):
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
            cur.execute(sql)
        conexao_plat_app.rollback()
        cur = _ctx(conexao_plat_app, sessao_demo)


def test_semeadura_cria_jobs_terminais_marcados(conexao_plat_app, sessao_demo):
    cur = _ctx(conexao_plat_app, sessao_demo)
    if not _ligada(cur):
        pytest.skip("plat.ambiente.semear_demo = false nesta instalação")
    cur.execute(SEMEAR, (7, "prova.progresso", '{"duracao_s": 0, "passos": 1}', "concluido"))
    assert cur.fetchone()["n"] == 7
    cur.execute("SELECT estado, progresso, worker, resultado, parametros FROM plat.job "
                "WHERE parametros->>'semente_demo' = 'true' ORDER BY criado_em DESC LIMIT 7")
    linhas = cur.fetchall()
    assert len(linhas) == 7
    for j in linhas:
        assert j["estado"] == "concluido" and j["progresso"] == 100 and j["worker"] == "semente_demo"
        assert j["resultado"] == {"semente_demo": True} and j["parametros"]["semente_demo"] is True
    conexao_plat_app.rollback()  # nada fica no banco: a semeadura é uma transação como outra qualquer


def test_guardas_estado_teto_e_tipo(conexao_plat_app, sessao_demo):
    cur = _ctx(conexao_plat_app, sessao_demo)
    if not _ligada(cur):
        pytest.skip("plat.ambiente.semear_demo = false nesta instalação")
    casos = [
        ((1, "prova.progresso", "{}", "rodando"), psycopg2.errors.InsufficientPrivilege, "estado final"),
        ((1, "prova.progresso", "{}", "pendente"), psycopg2.errors.InsufficientPrivilege, "estado final"),
        ((5001, "prova.progresso", "{}", "concluido"), psycopg2.errors.CheckViolation, "1 a 5000"),
        ((0, "prova.progresso", "{}", "concluido"), psycopg2.errors.CheckViolation, "1 a 5000"),
        ((1, "", "{}", "concluido"), psycopg2.errors.CheckViolation, "nome do tipo"),
    ]
    for args, erro, texto in casos:
        with pytest.raises(erro, match=texto):
            cur.execute(SEMEAR, args)
        conexao_plat_app.rollback()
        cur = _ctx(conexao_plat_app, sessao_demo)


def test_inquilino_que_nao_e_de_demonstracao_e_recusado(conexao_plat_app, sessao_demo):
    """Guarda 2: mesmo com o interruptor ligado, só demo, demo2 e zt-% são semeados. O inquilino técnico
    'plataforma' serve de contraprova (existe em toda instalação)."""
    cur = _ctx(conexao_plat_app, sessao_demo)
    if not _ligada(cur):
        pytest.skip("plat.ambiente.semear_demo = false nesta instalação")
    cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('plataforma', 'admin')")
    linha = cur.fetchone()
    if linha is None:
        pytest.skip("inquilino técnico 'plataforma' sem admin semeado (rode install.sh)")
    conexao_plat_app.rollback()
    cur = conexao_plat_app.cursor()
    jobs_sessao.contexto(cur, linha["tenant_id"], linha["usuario_id"], "admin")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="inquilino de demonstração"):
        cur.execute(SEMEAR, (1, "prova.progresso", "{}", "concluido"))
    conexao_plat_app.rollback()


def test_006_continua_inteira_com_a_014_aplicada(conexao_plat_app, sessao_demo):
    """A 014 não afrouxa a 006: o GUC plat.via_worker é definível por qualquer role (placeholder do Postgres), mas
    plat_app não tem UPDATE em plat.job nem EXECUTE nas funções do worker, e o INSERT já concluído continua barrado
    pelo gatilho — com o GUC ligado por conta própria."""
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("SELECT set_config('plat.via_worker', 'sim', true)")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="nasce pendente"):
        cur.execute(
            "INSERT INTO plat.job (tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s, estado, "
            "resultado) VALUES (plat.tenant_atual(), plat.usuario_atual(), 'prova.progresso', '{}', false, 256, 60, "
            "'concluido', '{\"forjado\": true}')"
        )
    conexao_plat_app.rollback()
    cur = _ctx(conexao_plat_app, sessao_demo)
    cur.execute("SELECT set_config('plat.via_worker', 'sim', true)")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
        cur.execute("UPDATE plat.job SET estado = 'rodando' WHERE tenant_id = plat.tenant_atual()")
    conexao_plat_app.rollback()
    cur = _ctx(conexao_plat_app, sessao_demo)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
        cur.execute("SELECT plat.via_worker_ligar()")
    conexao_plat_app.rollback()
