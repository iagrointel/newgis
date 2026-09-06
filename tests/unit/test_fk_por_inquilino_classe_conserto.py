"""Prova do item FK-CLASSE-CONSERTO (turno 3, 06/09/2026): a migração
`20260906T1847_fk_por_inquilino_classe.sql` trocou 44 FKs simples do schema `plat` (fora de
`plat.rede_*`, já provada em `test_rede_pacote_conserto_a1_a4.py` de outro item) por FK composta
`(tenant_id, id)`. A prova aqui é cruzada, direto pela role `plat_app` (sem passar pela API — em
vários casos a rota já filtra por RLS antes de gravar; o ponto do conserto é que a garantia agora
mora no BANCO, não só espalhada pelo código de cada rota): o inquilino B tenta pendurar uma linha
SUA apontando para o `id` de uma linha do inquilino A -- um caso por TABELA ALVO das 10 que a
migração tocou (usuario, item, pasta, grupo, categoria, papel_personalizado, compartilhamento_link,
conexao, job, token_servico), incluindo auto-referência uuid (`pasta.pai_id`, `categoria.pai_id`),
auto-referência inteira (`token_servico.renovado_por`) e cadeia de duas tabelas
(`compartilhamento_link_item`, provada nos dois sentidos: por `item_id` e por `link_id`). A FK tem
de recusar SEMPRE — com o id de A (existe, não é seu) e com um id inventado (não existe) — e a
MENSAGEM de recusa do Postgres tem de ser a mesma nos dois casos, matando o oráculo de existência."""

import uuid

import psycopg2
import pytest

from tests.api.test_rls import contexto, ids_por_slug


@pytest.fixture
def tenants(conexao_plat_app):
    return ids_por_slug(conexao_plat_app)


def _z(prefixo: str) -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:10]}"


def _contexto_admin(con, tenant_id):
    """Define o contexto RLS como o admin do inquilino (usuario_atual() precisa bater com dono_id/
    usuario_id nas políticas WITH CHECK das tabelas de conteúdo — não basta o tenant_id)."""
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND login = 'admin' LIMIT 1", (tenant_id,))
        admin_id = cur.fetchone()["id"]
    contexto(con, tenant_id, admin_id, "admin")
    return admin_id


def _admin(cur, tenant_id):
    cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND login = 'admin' LIMIT 1", (tenant_id,))
    return cur.fetchone()["id"]


def _item(cur, tenant_id):
    dono = _admin(cur, tenant_id)
    cur.execute(
        "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id) VALUES (%s, 'arquivo', %s, %s) RETURNING id",
        (tenant_id, _z("item"), dono),
    )
    return cur.fetchone()["id"]


def _pasta(cur, tenant_id):
    dono = _admin(cur, tenant_id)
    cur.execute(
        "INSERT INTO plat.pasta(tenant_id, nome, dono_id) VALUES (%s, %s, %s) RETURNING id",
        (tenant_id, _z("pasta"), dono),
    )
    return cur.fetchone()["id"]


def _usuario_alvo(cur, tenant_id):
    """Não cria linha nova -- o admin semeado já serve de alvo `usuario` (id estável, sempre existe)."""
    return _admin(cur, tenant_id)


def _grupo(cur, tenant_id):
    dono = _admin(cur, tenant_id)
    cur.execute(
        "INSERT INTO plat.grupo(tenant_id, nome, dono_id) VALUES (%s, %s, %s) RETURNING id",
        (tenant_id, _z("grupo"), dono),
    )
    return cur.fetchone()["id"]


def _categoria(cur, tenant_id):
    cur.execute("INSERT INTO plat.categoria(tenant_id, nome) VALUES (%s, %s) RETURNING id", (tenant_id, _z("categoria")))
    return cur.fetchone()["id"]


def _papel(cur, tenant_id):
    cur.execute(
        "INSERT INTO plat.papel_personalizado(tenant_id, nome, perfil_minimo) VALUES (%s, %s, 'visualizador') RETURNING id",
        (tenant_id, _z("papel")),
    )
    return cur.fetchone()["id"]


def _conexao(cur, tenant_id):
    dono = _admin(cur, tenant_id)
    cur.execute(
        "INSERT INTO plat.conexao(tenant_id, nome, tipo, dono_id, url) VALUES (%s, %s, 'wms', %s, %s) RETURNING id",
        (tenant_id, _z("conexao"), dono, "https://exemplo.invalido/wms"),
    )
    return cur.fetchone()["id"]


def _job(cur, tenant_id):
    usuario = _admin(cur, tenant_id)
    cur.execute(
        "INSERT INTO plat.job(tenant_id, tipo, usuario_id, pesado, memoria_mb, timeout_s) "
        "VALUES (%s, %s, %s, false, 256, 60) RETURNING id",
        (tenant_id, _z("job"), usuario),
    )
    return cur.fetchone()["id"]


def _token(cur, tenant_id):
    usuario = _admin(cur, tenant_id)
    nome = _z("token")
    cur.execute(
        "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo) "
        "VALUES (%s, %s, %s, %s, 'zfk') RETURNING id",
        (tenant_id, usuario, nome, f"hash-{nome}"),
    )
    return cur.fetchone()["id"]


def _preparar_alvo_em_a(con, tenant_id, criar_alvo):
    _contexto_admin(con, tenant_id)
    with con.cursor() as cur:
        alvo = criar_alvo(cur, tenant_id)
    con.commit()
    return alvo


def _inserir_item_pasta_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, pasta_id) VALUES (%s, 'arquivo', %s, %s, %s::uuid)",
        (b, _z("item"), _admin(cur, b), valor),
    )


def _inserir_pasta_pai_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.pasta(tenant_id, nome, dono_id, pai_id) VALUES (%s, %s, %s, %s::uuid)",
        (b, _z("pasta-filha"), _admin(cur, b), valor),
    )


def _inserir_favorito_item_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.favorito(tenant_id, usuario_id, item_id) VALUES (%s, %s, %s::uuid)",
        (b, _admin(cur, b), valor),
    )


def _inserir_link_item_id(cur, b, valor):
    item_dono_do_link = _item(cur, b)
    cur.execute(
        "INSERT INTO plat.compartilhamento_link(tenant_id, item_id, token_hash, prefixo) "
        "VALUES (%s, %s::uuid, %s, 'zfk') RETURNING id",
        (b, item_dono_do_link, _z("hash")),
    )
    link_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO plat.compartilhamento_link_item(tenant_id, link_id, item_id) VALUES (%s, %s::uuid, %s::uuid)",
        (b, link_id, valor),
    )


def _inserir_token_renovado_por(cur, b, valor):
    nome = _z("token-b")
    cur.execute(
        "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, renovado_por) "
        "VALUES (%s, %s, %s, %s, 'zfk', %s)",
        (b, _admin(cur, b), nome, f"hash-{nome}", valor),
    )


def _inserir_item_dono_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id) VALUES (%s, 'arquivo', %s, %s)",
        (b, _z("item-dono"), valor),
    )


def _inserir_item_grupo_grupo_id(cur, b, valor):
    item_de_b = _item(cur, b)
    cur.execute(
        "INSERT INTO plat.item_grupo(tenant_id, item_id, grupo_id) VALUES (%s, %s::uuid, %s::uuid)",
        (b, item_de_b, valor),
    )


def _inserir_categoria_pai_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.categoria(tenant_id, nome, pai_id) VALUES (%s, %s, %s::uuid)",
        (b, _z("categoria-filha"), valor),
    )


def _inserir_convite_papel_id(cur, b, valor):
    nome = _z("convite")
    cur.execute(
        "INSERT INTO plat.convite(tenant_id, email, perfil, criado_por, token_hash, expira_em, papel_id) "
        "VALUES (%s, %s, 'editor', %s, %s, now() + interval '7 days', %s)",
        (b, f"{nome}@exemplo.invalido", _admin(cur, b), f"hash-{nome}", valor),
    )


def _inserir_conexao_saude_conexao_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.conexao_saude_historico(tenant_id, conexao_id, ok) VALUES (%s, %s::uuid, true)",
        (b, valor),
    )


def _inserir_job_log_job_id(cur, b, valor):
    cur.execute(
        "INSERT INTO plat.job_log(tenant_id, job_id, nivel, mensagem) VALUES (%s, %s::uuid, 'INFO', 'zt-fkclasse')",
        (b, valor),
    )


def _link(cur, tenant_id):
    item_id = _item(cur, tenant_id)
    nome = _z("link-alvo")
    cur.execute(
        "INSERT INTO plat.compartilhamento_link(tenant_id, item_id, token_hash, prefixo) "
        "VALUES (%s, %s::uuid, %s, 'zfk') RETURNING id",
        (tenant_id, item_id, f"hash-{nome}"),
    )
    return cur.fetchone()["id"]


def _inserir_link_item_link_id(cur, b, valor):
    item_de_b = _item(cur, b)
    cur.execute(
        "INSERT INTO plat.compartilhamento_link_item(tenant_id, link_id, item_id) VALUES (%s, %s::uuid, %s::uuid)",
        (b, valor, item_de_b),
    )


CASOS = {
    "item_pasta_id": (_pasta, _inserir_item_pasta_id, lambda: str(uuid.uuid4())),
    "pasta_pai_id_auto_referencia": (_pasta, _inserir_pasta_pai_id, lambda: str(uuid.uuid4())),
    "favorito_item_id": (_item, _inserir_favorito_item_id, lambda: str(uuid.uuid4())),
    "compartilhamento_link_item_id": (_item, _inserir_link_item_id, lambda: str(uuid.uuid4())),
    "token_servico_renovado_por_auto_referencia": (_token, _inserir_token_renovado_por, lambda: 2_000_000_000),
    "item_dono_id_alvo_usuario": (_usuario_alvo, _inserir_item_dono_id, lambda: 2_000_000_000),
    "item_grupo_grupo_id": (_grupo, _inserir_item_grupo_grupo_id, lambda: str(uuid.uuid4())),
    "categoria_pai_id_auto_referencia": (_categoria, _inserir_categoria_pai_id, lambda: str(uuid.uuid4())),
    "convite_papel_id": (_papel, _inserir_convite_papel_id, lambda: 2_000_000_000),
    "conexao_saude_historico_conexao_id": (_conexao, _inserir_conexao_saude_conexao_id, lambda: str(uuid.uuid4())),
    "job_log_job_id": (_job, _inserir_job_log_job_id, lambda: str(uuid.uuid4())),
    "compartilhamento_link_item_link_id_alvo_link": (_link, _inserir_link_item_link_id, lambda: str(uuid.uuid4())),
}


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_fk_de_b_nao_alcanca_linha_de_a_como_plat_app(conexao_plat_app, tenants, caso):
    con = conexao_plat_app
    a, b = tenants["demo"], tenants["demo2"]
    criar_alvo, inserir_na_filha_de_b, id_inventado = CASOS[caso]

    alvo_de_a = _preparar_alvo_em_a(con, a, criar_alvo)

    _contexto_admin(con, b)
    with con.cursor() as cur:
        with pytest.raises((psycopg2.errors.ForeignKeyViolation, psycopg2.errors.RaiseException, psycopg2.errors.InsufficientPrivilege)) as erro_inventado:
            inserir_na_filha_de_b(cur, b, id_inventado())
    con.rollback()

    _contexto_admin(con, b)
    with con.cursor() as cur:
        with pytest.raises((psycopg2.errors.ForeignKeyViolation, psycopg2.errors.RaiseException, psycopg2.errors.InsufficientPrivilege)) as erro_de_a:
            inserir_na_filha_de_b(cur, b, alvo_de_a)
    con.rollback()

    # a mensagem de recusa é IDÊNTICA nos dois casos — mata o oráculo de existência: quem recebe o
    # erro não consegue distinguir "não existe" de "existe, mas é de outro inquilino". Em item.pasta_id
    # e pasta.pai_id, quem recusa primeiro é o gatilho de coerência de inquilino (já existia antes desta
    # migração, mesma mensagem única nos dois casos); nas demais, é a FK composta nova.
    assert type(erro_inventado.value) is type(erro_de_a.value), (erro_inventado.value, erro_de_a.value)
    msg_inventado = str(erro_inventado.value).split("\n")[0]
    msg_de_a = str(erro_de_a.value).split("\n")[0]
    assert msg_inventado == msg_de_a, (msg_inventado, msg_de_a)
