"""O alfabeto do slug do inquilino é UM só, da criação até a importação (item L0-04-c).

Achado do adversário do turno 3: `plat.tenant.slug` é criado sob CHECK '^[a-z0-9][a-z0-9-]{1,38}$' (migração
002 — hífen e dígito inicial valem), e `plat.camada_schema_garantir` da migração 029 exigia
'^[a-z][a-z0-9_]{0,60}$'. Todo inquilino com hífen no slug era aceito na criação e recusado na ingestão com
`slug_invalido`: nunca importava camada nenhuma. A suíte não pegava porque só usa demo/demo2/plataforma.

A prova não lê o texto das duas regras: EXERCITA as duas funções e compara o veredito. Quem trocar uma
sem trocar a outra reprova aqui."""

from __future__ import annotations

import psycopg2
import pytest

# slugs válidos para a criação de inquilino (migração 002); nenhum deles existe na base
SLUGS_VALIDOS = ["minha-org", "org2", "2024-prefeitura", "a-b-c-d", "demo"]  # sublinhado nao passa no CHECK da 002
SLUGS_INVALIDOS = ["Maiuscula", "com espaco", "-comeca-com-hifen", "x", "org.ponto", "org/barra"]


def _aceito_na_criacao(cur, slug: str) -> bool:
    cur.execute(
        "SELECT %s ~ substring(pg_get_constraintdef(oid) from '~ ''([^'']+)''') AS ok "
        "FROM pg_constraint WHERE conrelid = 'plat.tenant'::regclass AND contype = 'c' "
        "AND pg_get_constraintdef(oid) LIKE '%%slug%%'",
        (slug,),
    )
    linhas = cur.fetchall()
    assert linhas, "o CHECK do slug de plat.tenant sumiu"
    return all(bool(r["ok"]) for r in linhas)


def _aceito_na_ingestao(cur, slug: str) -> bool:
    """Chama a função de verdade. `slug_invalido` = alfabeto recusado; `schema_de_outro_inquilino` =
    alfabeto ACEITO (o slug simplesmente não é o do contexto). Qualquer outra exceção é erro do teste."""
    try:
        cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
    except psycopg2.errors.RaiseException as e:  # noqa: F841
        texto = str(e)
        if "slug_invalido" in texto:
            return False
        if "schema_de_outro_inquilino" in texto:
            return True
        raise
    return True  # criou o schema: o slug é o do contexto e passou no alfabeto


@pytest.mark.parametrize("slug", SLUGS_VALIDOS)
def test_slug_aceito_na_criacao_e_aceito_na_ingestao(conexao_plat_app, slug):
    with conexao_plat_app.cursor() as cur:
        criacao = _aceito_na_criacao(cur, slug)
    assert criacao, f"{slug!r} deixou de ser válido para plat.tenant; ajuste a lista do teste"
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        ingestao = _aceito_na_ingestao(cur, slug)
    conexao_plat_app.rollback()
    assert ingestao, (
        f"o slug {slug!r} é aceito na criação do inquilino e recusado pela ingestão: esse inquilino nunca "
        "consegue importar camada nenhuma"
    )


@pytest.mark.parametrize("slug", SLUGS_INVALIDOS)
def test_slug_invalido_continua_recusado_nos_dois_lados(conexao_plat_app, slug):
    """A reconciliação afrouxou a ingestão até o alfabeto da criação — não além dele."""
    with conexao_plat_app.cursor() as cur:
        assert not _aceito_na_criacao(cur, slug), f"{slug!r} passou no CHECK de plat.tenant"
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        assert not _aceito_na_ingestao(cur, slug), f"{slug!r} passou na ingestão"
    conexao_plat_app.rollback()
