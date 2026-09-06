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


# ---------------------------------------------------------------------------------------------- L6-01-d-ficha-fonte
# A ficha já tinha os 10 campos de procedência (migração 021, item anterior) — conferido por leitura antes de somar
# código (docs/adr/0012). O que faltava: endpoints confirmados e vivos (acervo.endpoint) e completude "x/10" por
# extenso. Os testes abaixo conferem os DOIS: campo por campo contra acervo.fonte/acervo.endpoint, para 20 fontes
# (o portão do item pede exatamente isso), nunca contra um número digitado.


def test_ficha_confere_20_fontes_campo_a_campo_incluindo_endpoints_e_completude(sessao_a, env):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte_id, nome, orgao, dominio, licenca, frescor, data_dado, data_acesso, script_gerador, "
                "sha256, sha256_cmd, metodo, confianca, limites, proxima_verificacao, tabelas, linhas_est, bytes "
                "FROM acervo.fonte WHERE licenca IS NOT NULL AND btrim(licenca) <> '' ORDER BY fonte_id LIMIT 20"
            )
            fontes = cur.fetchall()
            assert len(fontes) == 20, "a base precisa de pelo menos 20 fontes licenciadas para este teste"
            cur.execute(
                "SELECT fonte_id, count(*) AS total, count(*) FILTER (WHERE confirmado AND http = '200') AS vivos "
                "FROM acervo.endpoint WHERE fonte_id = ANY(%s) GROUP BY fonte_id",
                ([f["fonte_id"] for f in fontes],),
            )
            endpoints_por_fonte = {r["fonte_id"]: r for r in cur.fetchall()}
    finally:
        con.close()

    algum_com_endpoint = False
    for f in fontes:
        r = sessao_a.get(f"/api/acervo/{f['fonte_id']}")
        assert r.status_code == 200, r.text
        ficha = r.json()
        # os 10 campos de procedência da hipótese do item, um a um contra acervo.fonte (url já coberto por
        # test_ficha_bate_com_acervo_fonte)
        assert ficha["licenca"] == f["licenca"]
        assert ficha["frescor"] == f["frescor"]
        assert ficha["data_dado"] == f["data_dado"]
        assert ficha["script_gerador"] == f["script_gerador"]
        assert ficha["sha256"] == f["sha256"]
        assert ficha["comando_reexecucao"] == f["sha256_cmd"]
        assert ficha["metodo"] == f["metodo"]
        assert ficha["confianca"] == f["confianca"]
        assert ficha["limites"] == f["limites"]  # "o que este dado não sustenta", em conteúdo real
        assert ficha["numero_tabelas"] == f["tabelas"]
        assert ficha["registros_estimados"] == f["linhas_est"]

        # endpoints confirmados e vivos (item L6-01-d) contra acervo.endpoint
        e = endpoints_por_fonte.get(f["fonte_id"])
        total_esperado = e["total"] if e else 0
        vivos_esperado = e["vivos"] if e else 0
        assert ficha["endpoints_total"] == total_esperado, f["fonte_id"]
        assert ficha["endpoints_confirmados_vivos"] == vivos_esperado, f["fonte_id"]
        assert len(ficha["endpoints"]) == min(total_esperado, 200)
        assert all(ep["vivo"] == (bool(ep["confirmado"]) and ep["http"] == "200") for ep in ficha["endpoints"])
        if total_esperado:
            algum_com_endpoint = True

        # completude "x/10" por extenso, nunca fabricada quando a view não tem base de cálculo
        if ficha["procedencia_pontuacao"] is None:
            assert ficha["completude_texto"] is None
        else:
            esperado = f"{ficha['procedencia_pontuacao']:.1f}".replace(".", ",") + "/10"
            assert ficha["completude_texto"] == esperado

    assert algum_com_endpoint, "o teste pressupõe que ao menos uma das 20 fontes tenha endpoint testado"


def test_campo_ausente_na_ficha_nunca_e_fabricado(sessao_a, env):
    """sha256 ausente em acervo.fonte tem de continuar ausente (None) na API — nunca virar '' nem um valor
    qualquer. 'não registrado' (a hipótese do item) é problema de quem EXIBE, não da API mentir um dado."""
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte_id FROM acervo.fonte WHERE licenca IS NOT NULL AND btrim(licenca) <> '' "
                "AND sha256 IS NULL ORDER BY fonte_id LIMIT 1"
            )
            fonte_id = cur.fetchone()["fonte_id"]
    finally:
        con.close()
    r = sessao_a.get(f"/api/acervo/{fonte_id}")
    assert r.status_code == 200, r.text
    assert r.json()["sha256"] is None


# ---------------------------------------------------------------------------------------------------- L6-01-f-lgpd
# `acervo.fonte` não tem nenhum campo de classificação de risco de dado pessoal (conferido por \d antes de escrever
# qualquer coisa) — a classificação vive em `plat.acervo_lgpd`, curada à mão (migração 041; nunca escrita pela API,
# nunca calculada). Das 68 fontes licenciadas revisadas, só `onr` (matrículas: a tabela ingerida não guarda nome do
# titular, mas `url_mat` aponta para o documento de matrícula real no cartório, que guarda) ficou marcada.


def _fonte_risco_pii(env) -> str:
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT fonte_id FROM plat.acervo_lgpd WHERE risco_pii ORDER BY fonte_id LIMIT 1")
            row = cur.fetchone()
    finally:
        con.close()
    assert row is not None, "o teste pressupõe pelo menos uma fonte curada como risco_pii em plat.acervo_lgpd"
    return row["fonte_id"]


def test_ficha_de_fonte_marcada_mostra_risco_pii_e_motivo(sessao_a, env):
    fonte_id = _fonte_risco_pii(env)
    r = sessao_a.get(f"/api/acervo/{fonte_id}")
    assert r.status_code == 200, r.text
    ficha = r.json()
    assert ficha["risco_pii"] is True
    assert ficha["risco_pii_motivo"]  # nunca marcado sem motivo escrito (CHECK no banco já garante; API espelha)


def test_fonte_sem_curadoria_lgpd_nao_e_marcada_por_padrao(sessao_a, env):
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte_id FROM acervo.fonte f WHERE f.licenca IS NOT NULL AND btrim(f.licenca) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM plat.acervo_lgpd l WHERE l.fonte_id = f.fonte_id) "
                "ORDER BY fonte_id LIMIT 1"
            )
            fonte_id = cur.fetchone()["fonte_id"]
    finally:
        con.close()
    r = sessao_a.get(f"/api/acervo/{fonte_id}")
    assert r.status_code == 200, r.text
    assert r.json()["risco_pii"] is False
    assert r.json()["risco_pii_motivo"] is None


def test_adicionar_fonte_marcada_risco_pii_sem_confirmacao_recusa(sessao_a, env):
    fonte_id = _fonte_risco_pii(env)
    r = sessao_a.post(f"/api/acervo/{fonte_id}/adicionar")
    assert r.status_code == 409, r.text
    j = r.json()
    assert j["erro"] == "confirmacao_pii_exigida"
    assert j["detalhe"]["risco_pii_motivo"]

    # a recusa fica registrada (auditoria: quem tentou, quando, sem confirmar)
    r_ev = sessao_a.get("/api/eventos?limite=50")
    tipos = [e["tipo"] for e in r_ev.json()["itens"]]
    assert "acervo/adicionar_recusado_pii" in tipos


def test_adicionar_fonte_marcada_risco_pii_com_confirmacao_explicita_confirmacao_falsa_ainda_recusa(sessao_a, env):
    fonte_id = _fonte_risco_pii(env)
    r = sessao_a.post(f"/api/acervo/{fonte_id}/adicionar", json={"confirma_risco_pii": False})
    assert r.status_code == 409, r.text


def test_adicionar_fonte_marcada_risco_pii_com_confirmacao_cria_item(sessao_a, env, item_acervo_a):
    fonte_id = _fonte_risco_pii(env)
    r = sessao_a.post(f"/api/acervo/{fonte_id}/adicionar", json={"confirma_risco_pii": True})
    assert r.status_code == 201, r.text
    item = r.json()
    item_acervo_a.append(item["id"])
    assert item["dados"]["parametros"]["fonte_id"] == fonte_id
    assert item["dados"]["parametros"]["confirma_risco_pii"] is True


def test_adicionar_fonte_sem_risco_pii_nao_exige_confirmacao(sessao_a, env, item_acervo_a):
    """Regressão: a imensa maioria das fontes (67 de 68) não tem curadoria de risco; POST sem corpo continua
    funcionando exatamente como antes do item L6-01-f (nenhum corpo, nenhuma confirmação)."""
    con = _conexao_direta(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT f.fonte_id FROM acervo.fonte f WHERE f.licenca IS NOT NULL AND btrim(f.licenca) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM plat.acervo_lgpd l WHERE l.fonte_id = f.fonte_id AND l.risco_pii) "
                "ORDER BY fonte_id LIMIT 1"
            )
            fonte_id = cur.fetchone()["fonte_id"]
    finally:
        con.close()
    r = sessao_a.post(f"/api/acervo/{fonte_id}/adicionar")
    assert r.status_code == 201, r.text
    item = r.json()
    item_acervo_a.append(item["id"])
    assert "confirma_risco_pii" not in item["dados"]["parametros"]
