"""L0-02-z-apagar-inquilino-apaga-schema: DELETE /api/plataforma/inquilinos/{id} tem de apagar também o
schema de dado do inquilino (d_<slug>, onde vivem camadas/tabelas publicadas por ele), na MESMA transação
da função plat.tenant_apagar_interno — não só as linhas plat.* com tenant_id. Medido ao vivo em 10/09 antes
da migração 20260910T2307_inquilino_apagar_schema.sql: DELETE devolvia 204 e o schema continuava em
pg_namespace, com a tabela do inquilino dentro (achado do lote L0_1)."""

from __future__ import annotations

import secrets

from tests.api.conftest import PREFIXO_TESTE


def _existe_schema(conexao_plat_app, nome: str) -> bool:
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (nome,))
        return cur.fetchone() is not None


def _garantir_schema_do_inquilino(conexao_plat_app, tenant_id: int, slug: str) -> str:
    """Chama a função de produção plat.camada_schema_garantir (mesmo caminho que a ingestão real usa
    para nascer d_<slug>, migração 20260907T0240) no contexto GUC do próprio inquilino — não dá para
    fazer CREATE SCHEMA direto como plat_app (sem privilégio; só a função SECURITY DEFINER tem)."""
    nome_schema = f"d_{slug}"
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', '0', false), "
            "set_config('plat.login', 'teste-apagar-schema', false)",
            (str(tenant_id),),
        )
        cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
        cur.execute(f'CREATE TABLE "{nome_schema}".teste_apagar(id int)')
    conexao_plat_app.commit()
    return nome_schema


def _criar_inquilino_com_schema(sessao_plat, conexao_plat_app):
    """Cria um inquilino zt-* pelo superadmin e faz existir um schema/tabela de dado dele (d_<slug>) —
    sem depender de publicar camada de verdade pela API, que puxaria upload/inspeção/confirmação inteiros."""
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    r = sessao_plat.post(
        "/api/plataforma/inquilinos",
        json={"slug": slug, "nome": f"Teste apagar schema {slug}", "admin_login": "admin", "admin_nome": "Admin"},
    )
    assert r.status_code == 201, r.text
    tenant_id = r.json()["id"]
    nome_schema = _garantir_schema_do_inquilino(conexao_plat_app, tenant_id, slug)
    assert _existe_schema(conexao_plat_app, nome_schema)
    return tenant_id, nome_schema


def test_apagar_inquilino_apaga_schema_de_dado(sessao_plat, conexao_plat_app):
    tenant_id, nome_schema = _criar_inquilino_com_schema(sessao_plat, conexao_plat_app)

    r = sessao_plat.delete(f"/api/plataforma/inquilinos/{tenant_id}")
    assert r.status_code == 204, r.text

    # conexao_plat_app é outra conexão da mesma role; o DELETE já commitou do lado da API antes de
    # devolver 204 (não há transação aberta entre requisição e resposta), então a leitura aqui já vê o
    # resultado final — não precisa de nova transação além de garantir que a nossa não ficou pendurada
    # numa transação antiga que esconderia o commit alheio (READ COMMITTED, mas por segurança confirmamos).
    conexao_plat_app.rollback()
    assert not _existe_schema(conexao_plat_app, nome_schema), (
        f"schema {nome_schema} continua em pg_namespace depois do DELETE — bug original do item"
    )


def test_apagar_inquilino_sem_schema_de_dado_nao_falha(sessao_plat):
    """Inquilino que nunca publicou nada (sem d_<slug>) tem de apagar normalmente — DROP SCHEMA IF EXISTS."""
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    r = sessao_plat.post(
        "/api/plataforma/inquilinos",
        json={"slug": slug, "nome": f"Teste sem schema {slug}", "admin_login": "admin", "admin_nome": "Admin"},
    )
    assert r.status_code == 201, r.text
    tenant_id = r.json()["id"]
    r = sessao_plat.delete(f"/api/plataforma/inquilinos/{tenant_id}")
    assert r.status_code == 204, r.text


def test_inquilino_temporario_usado_duas_vezes_nao_deixa_schema_extra(sessao_plat, conexao_plat_app):
    """fixture InquilinoTemporario (tests/api/conftest.py) usada duas vezes seguidas: zero schema d_zt*
    a mais em pg_namespace ao final — a limpeza da segunda cobre o que a primeira deixou."""
    from tests.api.conftest import InquilinoTemporario

    def _schemas_zt() -> set[str]:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE %s", (f"d_{PREFIXO_TESTE}-inq-%",))
            return {row["nspname"] for row in cur.fetchall()}

    conexao_plat_app.rollback()
    antes = _schemas_zt()

    inq1 = InquilinoTemporario(sessao_plat)
    _garantir_schema_do_inquilino(conexao_plat_app, inq1.id, inq1.slug)
    inq1.apagar()

    inq2 = InquilinoTemporario(sessao_plat)
    _garantir_schema_do_inquilino(conexao_plat_app, inq2.id, inq2.slug)
    inq2.apagar()

    conexao_plat_app.rollback()
    depois = _schemas_zt()
    assert depois == antes, f"schema(s) órfão(s) depois de usar InquilinoTemporario duas vezes: {depois - antes}"
