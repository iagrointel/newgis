"""Item L6-01-f-lgpd, cláusula que faltava: varredura por CONTEÚDO nas views expostas do acervo.

O portão do item pede um teste que "percorre todas as views expostas e falha se existir coluna cujo nome
case com a lista negra OU cujo conteúdo case com regex de CPF/CNPJ em amostra de 1.000 linhas". Até
17/09/2026 só existia a metade do NOME (`scripts/acervo_sync.py`) mais a curadoria manual por fonte
(`plat.acervo_lgpd`) — o adversário da linha L6 registrou isso, e o próprio docstring do sincronizador
confessava a dívida. O motor está em `app/acervo/varredura_pii.py`.

Três camadas de prova, nesta ordem:
  1. DETECTOR, offline: o par ataque × legítimo do reconhecedor de CPF/CNPJ.
  2. VARREDURA com material plantado: uma view de mentira no schema de publicação desta bancada, com um CPF
     válido numa coluna de nome inocente (`identificacao`) — a rede por NOME não pegaria, a fina pega. Ao
     lado, uma view só com dado geográfico, que tem de sair limpa (sem par positivo, "achou tudo" seria
     indistinguível de "acusa tudo").
  3. VARREDURA de verdade: todas as views que o schema de publicação realmente tem hoje. Zero achado é o
     contrato; se um dia houver achado, este teste é que precisa falhar.
"""

from __future__ import annotations

import subprocess

import psycopg2
import pytest

from app.acervo import varredura_pii
from app.schema_ambiente import CursorSchemaAmbiente

# CPFs/CNPJs de teste, com dígito verificador válido e sem dono: são as sequências de exemplo usadas em
# documentação (não pertencem a pessoa nenhuma — 123.456.789-09 é o exemplo canônico de CPF de teste).
CPF_TESTE = "123.456.789-09"
CNPJ_TESTE = "12.345.678/0001-95"


def _psql(env, sql: str) -> None:
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr


# ------------------------------------------------------------------------------ 1. detector, offline
@pytest.mark.parametrize("valor", [
    CPF_TESTE, CNPJ_TESTE, "12345678909", "12345678000195",
    "titular: 123.456.789-09 (conferido)", "  12345678909  ",
    # segundo CPF válido, de outra família de dígitos: prova que o validador não passa só no exemplo acima
    "529.982.247-25", "52998224725",
])
def test_detector_acha_documento_de_pessoa(valor):
    achado = varredura_pii.achar_documento(valor)
    assert achado is not None, valor
    assert achado[1].endswith(("09", "95", "25")) and achado[1].startswith("*"), achado


@pytest.mark.parametrize("valor", [
    None, "", "Município de São Paulo", "3550308", "2026-09-18", "-23.5505",
    "00000000000", "11111111111", "99999999999",          # enchimento, nunca documento
    "12345678901", "35503080001", "52998224726", "12345678902",   # 11 dígitos com verificador errado
    "SP-3550308-0001", "CAR: SP-3550308-A1B2C3D4",
])
def test_detector_nao_acusa_o_que_nao_e_documento(valor):
    assert varredura_pii.achar_documento(valor) is None, valor


def test_mascara_nunca_devolve_o_documento_inteiro():
    """Regra da casa: nem o relatório da varredura publica dado identificado."""
    m = varredura_pii.mascarar(CPF_TESTE)
    assert m == "*********09"
    assert "123" not in m and "456" not in m


# ------------------------------------------------------------- 2 e 3. varredura no schema de publicação
@pytest.fixture
def views_plantadas(env):
    """Duas views no schema de publicação desta bancada: uma suja (CPF numa coluna de nome inocente) e uma
    limpa (só dado geográfico). Criadas e destruídas como `postgres`; a varredura lê como a role da
    aplicação, que é quem enxerga as views de verdade."""
    schema = f"{env['PLAT_SCHEMA']}_acervo"
    app_role = psycopg2.connect(env["PLAT_DSN"]).get_dsn_parameters()["user"]
    _psql(env, f"""
        CREATE SCHEMA IF NOT EXISTS {schema};
        DROP VIEW IF EXISTS {schema}.zt_pii_suja;
        DROP VIEW IF EXISTS {schema}.zt_pii_limpa;
        DROP TABLE IF EXISTS {schema}.zt_pii_origem;
        CREATE TABLE {schema}.zt_pii_origem(
            id int, municipio text, codigo_ibge text, identificacao text, area_ha numeric);
        INSERT INTO {schema}.zt_pii_origem VALUES
            (1, 'São Paulo', '3550308', '{CPF_TESTE}', 12.5),
            (2, 'Campinas', '3509502', '3509502', 8.1),
            (3, 'Santos', '3548500', 'SP-3548500-A1', 3.3);
        CREATE VIEW {schema}.zt_pii_suja AS
            SELECT id, municipio, codigo_ibge, identificacao, area_ha FROM {schema}.zt_pii_origem;
        CREATE VIEW {schema}.zt_pii_limpa AS
            SELECT id, municipio, codigo_ibge, area_ha FROM {schema}.zt_pii_origem;
        GRANT USAGE ON SCHEMA {schema} TO {app_role};
        GRANT SELECT ON {schema}.zt_pii_suja, {schema}.zt_pii_limpa TO {app_role};
    """)
    yield schema
    _psql(env, f"DROP VIEW IF EXISTS {schema}.zt_pii_suja; DROP VIEW IF EXISTS {schema}.zt_pii_limpa; "
               f"DROP TABLE IF EXISTS {schema}.zt_pii_origem;")


def _cursor(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    return con, con.cursor()


def test_varredura_acha_cpf_em_coluna_de_nome_inocente(env, views_plantadas):
    """O ataque: a coluna se chama `identificacao` — a rede GROSSA por nome deixa passar (e tem de deixar:
    'identificação' é palavra de cadastro, não de pessoa). Quem pega é a rede fina, pelo conteúdo."""
    schema = views_plantadas
    assert not varredura_pii._e_pii_por_nome("identificacao"), "o teste pressupõe nome que a rede grossa libera"
    con, cur = _cursor(env)
    try:
        achados = varredura_pii.varrer_view(cur, schema, "zt_pii_suja")
    finally:
        con.close()
    assert [a for a in achados if a["coluna"] == "identificacao"], varredura_pii.relatorio(achados)
    achado = next(a for a in achados if a["coluna"] == "identificacao")
    assert achado["regra"].startswith("conteudo:"), achado
    assert achado["exemplo_mascarado"] == "*********09", achado
    assert CPF_TESTE not in varredura_pii.relatorio(achados), "o relatório nunca imprime o documento"


def test_varredura_nao_acusa_view_so_com_dado_geografico(env, views_plantadas):
    """Par positivo: sem ele, uma varredura que acusasse tudo passaria no teste de cima."""
    schema = views_plantadas
    con, cur = _cursor(env)
    try:
        achados = varredura_pii.varrer_view(cur, schema, "zt_pii_limpa")
    finally:
        con.close()
    assert achados == [], varredura_pii.relatorio(achados)


def test_todas_as_views_expostas_hoje_estao_limpas(env):
    """A cláusula do portão, sobre o que a bancada realmente publica. Zero achado é o contrato; view do
    acervo com CPF no conteúdo tem de derrubar esta suíte."""
    schema = f"{env['PLAT_SCHEMA']}_acervo"
    con, cur = _cursor(env)
    try:
        views = varredura_pii.views_expostas(cur, schema)
        achados = [a for a in varredura_pii.varrer_schema(cur, schema) if not a["view"].startswith("zt_")]
    finally:
        con.close()
    print(f"varredura de conteúdo: {len(views)} view(s) em {schema}, {len(achados)} achado(s)")
    assert achados == [], varredura_pii.relatorio(achados)
