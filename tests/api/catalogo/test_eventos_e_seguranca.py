"""Eventos e segurança do catálogo (ADR 0004 seções 6.3, 12 e 16): toda rota de escrita deste item tem entrada em
eventos_esperados.py e todo tipo citado existe em plat.evento_tipo (o teste geral em test_eventos.py cobre; aqui a
sequência real do item e o conteúdo das propriedades); funções SECURITY DEFINER do catálogo sem EXECUTE para PUBLIC;
plat_app sem EXECUTE nas funções do worker (regressão da 011 apontada pelo cronista); plat_app sem INSERT/UPDATE/
DELETE em item_versao, tipo_item, relacao_tipo; DELETE físico em item proibido; limites do código = CHECKs do banco."""

import re
import uuid

import psycopg2
import pytest

from app import limites
from tests.api.eventos_esperados import EVENTOS_POR_ROTA
from tests.api.test_rls import contexto, ids_por_slug

VOCABULARIO_CATALOGO = {
    "itens/adicionar",
    "itens/atualizar",
    "itens/apagar",
    "itens/restaurar",
    "itens/mover",
    "itens/transferir",
    "itens/status",
    "itens/proteger",
    "itens/desproteger",
    "itens/miniatura",
    "itens/versao_restaurar",
    "itens/versao_publicar",
    "itens/dados_migrar",
    "itens/relacoes",
    "compartilhamento/alterar",
    "compartilhamento/link_criar",
    "compartilhamento/link_revogar",
    "compartilhamento/link_acesso",
    "pastas/criar",
    "pastas/renomear",
    "pastas/mover",
    "pastas/apagar",
    "categorias/alterar",
    "categorias/importar",
    "favoritos/adicionar",
    "favoritos/remover",
    "lixeira/expurgar",
    "lixeira/esvaziar",
    # L5-14-publicacao-links-embed: as rotas de publicação ficam sob /api/itens/{id}, então entram em
    # ROTAS_CATALOGO abaixo e o vocabulário delas (migração 20260907T1410_publicacao_documento.sql) pertence a
    # esta lista.
    "publicacao/publicar",
    "publicacao/despublicar",
}
ROTAS_CATALOGO = [
    r
    for r in EVENTOS_POR_ROTA
    if any(k in r[1] for k in ("/itens", "/pastas", "/categorias", "/favoritos", "/lixeira"))
]


def test_vocabulario_no_banco_e_rotas_declaradas(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT nome FROM plat.evento_tipo")
        tipos = {r["nome"] for r in cur.fetchall()}
    assert VOCABULARIO_CATALOGO <= tipos, VOCABULARIO_CATALOGO - tipos
    assert len(ROTAS_CATALOGO) >= 25
    citados = {t for r in ROTAS_CATALOGO for t in EVENTOS_POR_ROTA[r]}
    assert citados <= VOCABULARIO_CATALOGO


def test_sequencia_real_e_propriedades_sem_segredo(sessao_a, itens_a):
    it = itens_a.criar("mapa", descricao="descrição longa que nunca vai para o evento " * 3)
    iid = it["id"]
    sessao_a.put(
        f"/api/itens/{iid}", json={"titulo": it["titulo"] + " x", "dados": {"esquema_versao": 1, "corpo": {"a": 1}}}
    )
    r = sessao_a.post(f"/api/itens/{iid}/links", json={})
    tok, lid = r.json()["token"], r.json()["id"]
    sessao_a.delete(f"/api/itens/{iid}/links/{lid}")
    sessao_a.put(f"/api/favoritos/{iid}")
    sessao_a.delete(f"/api/favoritos/{iid}")
    sessao_a.delete(f"/api/itens/{iid}")
    sessao_a.post(f"/api/lixeira/{iid}/restaurar")
    itens = sessao_a.get("/api/eventos?limite=50").json()["itens"]
    meus = [e for e in itens if e["alvo_id"] in (iid, lid)]
    tipos = [e["tipo"] for e in reversed(meus)]
    assert tipos == [
        "itens/adicionar",
        "itens/atualizar",
        "compartilhamento/link_criar",
        "compartilhamento/link_revogar",
        "favoritos/adicionar",
        "favoritos/remover",
        "itens/apagar",
        "itens/restaurar",
    ], tipos
    texto = str(meus)
    assert tok not in texto and "descrição longa" not in texto and '"corpo"' not in texto
    atualizar = next(e for e in meus if e["tipo"] == "itens/atualizar")
    assert atualizar["propriedades"] == {"campos": ["dados", "titulo"], "versao": 2}
    assert all(e["req_id"] and e["ator"]["login"] for e in meus)


def test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app(conexao_plat_app, sessao_a):
    with conexao_plat_app.cursor() as cur:
        cur.execute("""
            SELECT proname FROM pg_proc WHERE pronamespace = 'plat'::regnamespace
              AND (proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(proacl) a WHERE a::text LIKE '=%'))""")
        assert [r["proname"] for r in cur.fetchall()] == []
        cur.execute("""
            SELECT proname, has_function_privilege('plat_app', oid, 'EXECUTE') AS app,
                   has_function_privilege('plat_worker', oid, 'EXECUTE') AS worker
            FROM pg_proc WHERE pronamespace = 'plat'::regnamespace
              AND proname IN ('job_pegar', 'job_terminar', 'job_devolver', 'job_ceifar', 'worker_registrar',
                              'agenda_vencidas', 'via_worker_ligar', 'job_transicao')""")
        linhas = cur.fetchall()
    assert len(linhas) >= 7
    for r in linhas:
        assert r["app"] is False, f"plat_app com EXECUTE em {r['proname']} (regressão da 011)"
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0)
    for sql in ("SELECT * FROM plat.job_pegar('forjado', true)", "SELECT plat.via_worker_ligar()"):
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(sql)
        conexao_plat_app.rollback()


def test_delete_fisico_proibido_e_expurgo_so_do_inquilino(conexao_plat_app, sessao_a, sessao_b, itens_a, itens_b):
    it = itens_a.criar("mapa")
    de_b = itens_b.criar("mapa")
    sessao_b.delete(f"/api/itens/{de_b['id']}")
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (it["id"],))
        assert cur.rowcount == 0  # política FOR DELETE USING (false)
        cur.execute("SELECT plat.item_expurgar(%s::uuid) AS ok", (de_b["id"],))
        assert cur.fetchone()["ok"] is False  # item de B na lixeira: o contexto de A não expurga
        cur.execute("SELECT count(*) AS n FROM plat.lixeira_expurgar(0, now() + interval '1 day', NULL)")
        cur.execute(
            "SELECT count(*) AS n FROM plat.lixeira_expurgar(0, now() + interval '1 day', %s::uuid[])", ([de_b["id"]],)
        )
        assert cur.fetchone()["n"] == 0
    conexao_plat_app.rollback()
    assert sessao_b.post(f"/api/lixeira/{de_b['id']}/restaurar").status_code == 200


def test_pode_ler_sem_contexto_e_link_itens_forjado(conexao_plat_app, itens_a, sessao_a):
    it = itens_a.criar("mapa")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.pode_ler(%s::uuid) AS l, plat.pode_editar(%s::uuid) AS e", (it["id"], it["id"]))
        r = cur.fetchone()
        assert r["l"] is False and r["e"] is False
    ids = ids_por_slug(conexao_plat_app)
    # anônimo forjando plat.link_itens no contexto do inquilino: só vê o que está na lista,
    # e a lista só vem de link_resolver
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', '', true), "
            "set_config('plat.link_itens', %s, true)",
            (str(ids["demo"]), str(uuid.uuid4())),
        )
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE id = %s::uuid", (it["id"],))
        assert cur.fetchone()["n"] == 0
    conexao_plat_app.rollback()


def test_limites_do_codigo_batem_com_os_checks(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("""
            SELECT c.conname, pg_get_constraintdef(c.oid) AS def FROM pg_constraint c
            WHERE c.conrelid IN ('plat.item'::regclass, 'plat.pasta'::regclass, 'plat.categoria'::regclass,
                                 'plat.compartilhamento_link'::regclass) AND c.contype = 'c'""")
        defs = " ".join(r["def"] for r in cur.fetchall())
        cur.execute("SELECT plat.categorias_max(1) AS m, plat.cota_itens(1) AS c")
        r = cur.fetchone()
    esperados = {
        f"length(titulo) >= 1) AND (length(titulo) <= {limites.ITEM_TITULO_MAX}": True,
        f"length(resumo) <= {limites.ITEM_RESUMO_MAX}": True,
        f"length(descricao) <= {limites.ITEM_DESCRICAO_MAX}": True,
        f"length(creditos) <= {limites.ITEM_CREDITOS_MAX}": True,
        f"cardinality(tags) <= {limites.ITEM_TAGS_MAX}": True,
        f"cardinality(categorias) <= {limites.ITEM_CATEGORIAS_MAX}": True,
        f"length(nome) <= {limites.PASTA_NOME_MAX}": True,
        f"profundidade <= {limites.PASTA_PROFUNDIDADE_MAX - 1}": True,
        f"length(nome) <= {limites.CATEGORIA_NOME_MAX}": True,
        f"nivel <= {limites.CATEGORIA_NIVEIS}": True,
        f"'{limites.LINK_VALIDADE_MAX_DIAS} days'": True,
    }
    for trecho in esperados:
        assert re.sub(r"\s+", " ", trecho) in re.sub(r"\s+", " ", defs), trecho
    assert r["m"] == limites.CATEGORIAS_POR_INQUILINO[0] and r["c"] == limites.COTA_ITENS
    assert limites.LINK_TOKEN_BYTES * 2 == 64 and limites.MINIATURA_PIXELS_MAX == 25_000_000
