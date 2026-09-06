"""Rotas do acervo da casa (item L6-01-a-procedencia-acervo): `GET /api/acervo`, `GET /api/acervo/{fonte_id}`,
`POST /api/acervo/{fonte_id}/adicionar`. Regra D17: só fonte com licença ESCRITA aparece — os testes contam quantas
ficam de fora e confirmam que a ficha de uma sem licença nunca aparece. O `adicionar` cria item tipo `conexao` no
inquilino de quem chamou, provado com a mesma trava cruzada A→B do resto do catálogo (RLS por `tenant_id`)."""

import psycopg2.extras
import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug


def _admin_contexto(env, slug):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")
    return con


def _expurgar(con, item_id: str) -> None:
    with con.cursor() as cur:
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item_id,))
        cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item_id,))
    con.commit()


@pytest.fixture
def item_acervo_a(env):
    """Registra o id criado no teste para expurgo físico no fim, mesmo que a asserção falhe no meio."""
    criados = []
    yield criados
    if not criados:
        return
    con = _admin_contexto(env, "demo")
    try:
        for iid in criados:
            _expurgar(con, iid)
    finally:
        con.close()


def _conexao_direta(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)


def test_lista_so_fontes_com_licenca_e_conta_as_de_fora(sessao_a, env):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM acervo.fonte")
            total_fontes = cur.fetchone()["n"]
            cur.execute("SELECT count(*) AS n FROM acervo.fonte WHERE licenca IS NOT NULL AND btrim(licenca) <> ''")
            com_licenca = cur.fetchone()["n"]
    finally:
        con.close()
    de_fora = total_fontes - com_licenca
    assert de_fora > 0, "o teste pressupõe que existam fontes sem licença escrita (regra D17)"

    r = sessao_a.get("/api/acervo?limite=1000")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] == com_licenca == len(j["itens"])
    assert j["total"] < total_fontes
    assert all(item["licenca"] for item in j["itens"])
    # nenhum cartão da lista pode vir de uma fonte sem licença escrita
    ids_com_licenca = {item["fonte_id"] for item in j["itens"]}
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT fonte_id FROM acervo.fonte WHERE licenca IS NULL OR btrim(licenca) = ''")
            sem_licenca = {row["fonte_id"] for row in cur.fetchall()}
    finally:
        con.close()
    assert not (ids_com_licenca & sem_licenca)
    print(f"fontes de fora da lista por falta de licença escrita: {de_fora} de {total_fontes}")


def test_ficha_bate_com_acervo_fonte(sessao_a, env):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte_id, nome, dominio, licenca, frescor, tabelas, linhas_est, sha256, sha256_cmd "
                "FROM acervo.fonte WHERE licenca IS NOT NULL AND btrim(licenca) <> '' ORDER BY fonte_id LIMIT 1"
            )
            f = cur.fetchone()
    finally:
        con.close()
    assert f is not None

    r = sessao_a.get(f"/api/acervo/{f['fonte_id']}")
    assert r.status_code == 200, r.text
    ficha = r.json()
    assert ficha["fonte_id"] == f["fonte_id"]
    assert ficha["nome"] == f["nome"]
    assert ficha["dominio"] == f["dominio"]
    assert ficha["licenca"] == f["licenca"]
    assert ficha["frescor"] == f["frescor"]
    assert ficha["numero_tabelas"] == f["tabelas"]
    assert ficha["registros_estimados"] == f["linhas_est"]
    assert ficha["sha256"] == f["sha256"]
    assert ficha["comando_reexecucao"] == f["sha256_cmd"]


def test_fonte_sem_licenca_nunca_aparece(sessao_a, env):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte_id FROM acervo.fonte WHERE licenca IS NULL OR btrim(licenca) = '' "
                "ORDER BY fonte_id LIMIT 1"
            )
            f = cur.fetchone()
    finally:
        con.close()
    assert f is not None, "o teste pressupõe pelo menos uma fonte sem licença escrita"

    r = sessao_a.get(f"/api/acervo/{f['fonte_id']}")
    assert r.status_code == 404, r.text

    r = sessao_a.get(f"/api/acervo?q={f['fonte_id']}&limite=1000")
    assert r.status_code == 200
    assert f["fonte_id"] not in {item["fonte_id"] for item in r.json()["itens"]}


def test_fonte_inexistente_404(sessao_a):
    r = sessao_a.get(f"/api/acervo/{PREFIXO_TESTE}-fonte-que-nao-existe")
    assert r.status_code == 404


def test_adicionar_cria_item_conexao_no_inquilino_correto_e_rls(sessao_a, sessao_b, env, item_acervo_a):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte_id FROM acervo.fonte WHERE licenca IS NOT NULL AND btrim(licenca) <> '' "
                "ORDER BY fonte_id LIMIT 1"
            )
            fonte_id = cur.fetchone()["fonte_id"]
    finally:
        con.close()

    r = sessao_a.post(f"/api/acervo/{fonte_id}/adicionar")
    assert r.status_code == 201, r.text
    item = r.json()
    item_acervo_a.append(item["id"])
    assert item["tipo"] == "conexao"
    assert item["dados"]["protocolo"] == "acervo"
    assert item["dados"]["parametros"]["fonte_id"] == fonte_id

    con = _conexao_direta(env)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
            admin_id = cur.fetchone()["usuario_id"]
        # RLS de plat.item exige tenant_id E plat.pode_ler(id) na sessão (dono ou compartilhamento); sem o
        # usuário certo o SELECT devolve zero linhas mesmo no inquilino certo.
        contexto(con, ids["demo"], usuario_id=admin_id, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT tenant_id, tipo FROM plat.item WHERE id = %s::uuid", (item["id"],))
            row = cur.fetchone()
    finally:
        con.close()
    assert row["tenant_id"] == ids["demo"]
    assert row["tipo"] == "conexao"

    # RLS: o admin do OUTRO inquilino não lê o item recém-criado (mesma trava cruzada A→B do resto do catálogo)
    r_b = sessao_b.get(f"/api/itens/{item['id']}")
    assert r_b.status_code == 404, r_b.text

    # dono lê o próprio item recém-criado
    r_a = sessao_a.get(f"/api/itens/{item['id']}")
    assert r_a.status_code == 200
    assert r_a.json()["dados"]["parametros"]["fonte_id"] == fonte_id


def test_adicionar_fonte_sem_licenca_404(sessao_a, env):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT fonte_id FROM acervo.fonte WHERE licenca IS NULL OR btrim(licenca) = '' LIMIT 1")
            fonte_id = cur.fetchone()["fonte_id"]
    finally:
        con.close()
    r = sessao_a.post(f"/api/acervo/{fonte_id}/adicionar")
    assert r.status_code == 404, r.text
