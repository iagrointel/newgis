"""Adversário de linha L0 (turno 9) — item `L0-04-i-fonte-registrada`.

ACHADO: a senha do Postgres externo registrado por `postgres_fdw` fica de pé, em texto claro, em
`pg_user_mappings` — legível por QUALQUER inquilino desta instalação, para sempre (não só "durante a
chamada", como o próprio ADR avalia).

`plat.conexao_fdw_publicar` (SECURITY DEFINER, `docs/adr/20260907T0148-fonte-registrada-postgres-fdw.md`,
dona `postgres`) grava a credencial com
    CREATE USER MAPPING FOR session_user SERVER <servidor> OPTIONS (user %L, password %L)
A seção 2 do ADR chama isso de "risco aceito e documentado" e conclui: "o texto claro existe só durante os
milissegundos da chamada da função". Isso está errado: `CREATE USER MAPPING ... OPTIONS (...)` NÃO é uma
variável de sessão nem um parâmetro de chamada — é DDL que grava a opção PERMANENTEMENTE em
`pg_user_mapping.umoptions`, um catálogo do sistema. O Postgres só devolve `NULL` em
`pg_user_mappings.umoptions` para quem NÃO é o dono do mapeamento (`umuser`) nem superusuário; aqui o dono é
sempre `session_user` (decisão 3 do próprio ADR, precisamente para funcionar em toda trilha) — e
`session_user` é o MESMO papel de login compartilhado por TODOS OS INQUILINOS desta instalação (ADR 0001:
isolamento por RLS/GUC, nunca por papel de banco; `plat_app` em produção, `plat_t<trilha>_app` em cada
trilha). Logo qualquer sessão autenticada de QUALQUER inquilino, a qualquer momento no futuro, lê em claro
`SELECT umoptions FROM pg_user_mappings` e enxerga a senha do Postgres externo de QUALQUER outro inquilino
que já tenha publicado uma fonte `postgres_fdw` — isto falsifica a cláusula literal do portão "credencial
nunca em claro no banco".

Prova ao vivo, sem precisar de banco externo real nem de senha real: `CREATE SERVER`/`CREATE USER MAPPING`
são só DDL de catálogo — o Postgres nunca tenta autenticar contra o alvo até uma consulta tocar a tabela
estrangeira — então o teste chama `plat.conexao_fdw_publicar` (a MESMA função que
`POST /api/conexoes/{id}/publicar-em-massa` chama) com um alvo TEST-NET-1 (192.0.2.0/24, RFC 5737, nunca
roteável) e uma senha fictícia, e confere se a MESMA sessão volta a ler essa senha depois pela via do
catálogo. Medido fora do teste (mesmo Postgres compartilhado da casa, sem tocar em nada): `pg_user_mappings`
já tem dezenas de linhas `fdw_*` cujo `umuser` é um único papel por trilha (`plat_til004ifonte_app`,
`plat_tcx5l602j_app`) — exatamente o padrão "um papel, muitos inquilinos" que torna o achado explorável de
verdade, não só teórico.

Não conserta nada aqui (regra da casa); o teste só documenta o achado como xfail(strict=True). O que a
correção provavelmente exige (fora do escopo deste laudo): nunca guardar a senha do lado do Postgres em
`pg_user_mapping` acessível ao papel compartilhado — por exemplo REVOKE do papel de aplicação sobre
`pg_user_mappings` e uma view/função própria que devolva só os metadados não sensíveis, ou um papel de login
por inquilino (contradiz a decisão 3 do ADR e o desenho RLS/GUC inteiro da casa)."""

import uuid

import pytest

from tests.api.test_rls import contexto, ids_por_slug

SENHA_FICTICIA = "adversario-l0-04-i-nao-e-credencial-real-8f2c91a4"  # nunca uma senha real; só prova visibilidade


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO (turno 9, adversário de linha L0, item L0-04-i-fonte-registrada): plat.conexao_fdw_publicar "
    "grava a senha do Postgres externo com CREATE USER MAPPING FOR session_user, e session_user é o MESMO "
    "papel de login para TODOS os inquilinos desta instalação (ADR 0001, RLS/GUC). "
    "pg_user_mappings.umoptions só é ocultado pelo Postgres de quem não é o dono do mapeamento nem "
    "superusuário -- aqui o dono é sempre esse papel compartilhado, então qualquer sessão autenticada de "
    "qualquer inquilino lê a senha em claro de qualquer conexão postgres_fdw já publicada por QUALQUER "
    "outro inquilino, para sempre. docs/adr/20260907T0148 seção 2 avalia isto como risco 'de milissegundos "
    "da chamada da função' -- CREATE USER MAPPING é DDL persistente, não uma variável de sessão; a avaliação "
    "de risco do próprio ADR está errada, não só a mitigação.",
)
def test_senha_do_fdw_nao_fica_legivel_em_pg_user_mappings_depois_de_publicar(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    conexao_id = str(uuid.uuid4())
    servidor = "fdw_" + conexao_id.replace("-", "")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.conexao(id, tenant_id, tipo, modo, nome, url, credencial_cifrada, dono_id) "
            "VALUES (%s::uuid, %s, 'postgres_fdw', 'referenciada', %s, "
            "'postgres://192.0.2.1:5432/basedeteste', NULL, "
            "(SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1))",
            (conexao_id, ids["demo"], f"zt adversario fdw leak {conexao_id[:8]}", ids["demo"]),
        )
    conexao_plat_app.commit()
    try:
        contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "SELECT * FROM plat.conexao_fdw_publicar(%s::uuid, 'demo', '192.0.2.1', 5432, 'basedeteste', "
                "'usuario_teste', %s, 'public', 'zt_tabela_teste', "
                "'[{\"nome\": \"id\", \"tipo_pg\": \"integer\"}]'::jsonb, %s)",
                (conexao_id, SENHA_FICTICIA, ids["demo"]),
            )
        conexao_plat_app.commit()

        # QUALQUER sessão com o MESMO papel de login lê a senha por aqui (em produção seria a sessão de
        # OUTRO inquilino qualquer -- o papel de login é o mesmo para todos; esta é só a prova mínima de
        # que a opção fica gravada em claro e visível, sem precisar de um segundo inquilino no teste).
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT umoptions FROM pg_user_mappings WHERE srvname = %s", (servidor,))
            linha = cur.fetchone()
        assert linha is not None, "user mapping não encontrado (a função não gravou o esperado?)"
        opcoes = " ".join(linha["umoptions"] or [])
        assert SENHA_FICTICIA not in opcoes, (
            f"a senha do Postgres externo aparece em claro e legível em pg_user_mappings.umoptions: {opcoes!r}"
        )
    finally:
        with conexao_plat_app.cursor() as cur:
            cur.execute(f'DROP SERVER IF EXISTS "{servidor}" CASCADE')
            cur.execute("DELETE FROM plat.conexao WHERE id = %s::uuid", (conexao_id,))
        conexao_plat_app.commit()
