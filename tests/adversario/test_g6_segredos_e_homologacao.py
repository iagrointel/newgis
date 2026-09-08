"""Ataque adversarial aos itens L7-19-segredos-e-certificados e L7-31-ambiente-homologacao (turno 3, G6).

L7-19, refutação literal: "adversário lê /proc/<pid>/environ, o journal, o .env, o garage.toml e o
histórico do git à procura de qualquer segredo; qualquer um em claro fora de /run/credentials = refutado".
L7-31, refutação literal: "adversário procura qualquer caminho pelo qual homologação alcança dado de
produção (DSN, bucket, token)". Os dois caminhos foram achados e medidos."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.adversario.apoio_g6 import RAIZ, ler_env

ITEM_SEGREDOS = "L7-19-segredos-e-certificados"
ITEM_HOMOLOG = "L7-31-ambiente-homologacao"

# O `.env` e o ambiente de homologação vivem na árvore INSTALADA do produto, não num worktree.
RAIZ_INSTALADA = Path("/home/dev/plataforma/enterprise")


def _instalado(relativo: str) -> Path:
    proprio = RAIZ / relativo
    return proprio if proprio.exists() else RAIZ_INSTALADA / relativo


ENV_PRODUCAO = _instalado(".env")
ENV_HOMOLOG = _instalado("var/homolog/homolog.env")
GARAGE_TOML = Path("/home/dev/plataforma/pipeline/garage/garage.toml")
NOMES_DE_SEGREDO = re.compile(r"SECRET|TOKEN|SENHA|PASS|KEY|DSN")


# CORRIGIDO (conferido em 08/09/2026): o ataque não reproduz mais — os segredos saíram do
# .env de produção. A marca xfail estrita saiu; o teste fica valendo como regressão.
@pytest.mark.skipif(not ENV_PRODUCAO.exists(), reason="sem .env nesta máquina")
def test_env_de_producao_nao_pode_ter_segredo_em_claro():
    sobraram = sorted(c for c in ler_env(ENV_PRODUCAO) if NOMES_DE_SEGREDO.search(c))
    assert sobraram == [], f"segredos em claro no .env: {sobraram}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-19 (a própria hipótese do item diz 'token admin do Garage da prova está em claro em "
    "garage.toml — corrigir'): não foi corrigido. admin_token e rpc_secret seguem em claro num arquivo "
    "0600 do usuário dev, legível por qualquer processo do produto (todos rodam como dev).",
)
@pytest.mark.skipif(not GARAGE_TOML.exists(), reason="sem garage.toml nesta máquina")
def test_garage_toml_nao_pode_ter_token_em_claro():
    texto = GARAGE_TOML.read_text(encoding="utf-8", errors="replace")
    achados = [c for c in ("admin_token", "rpc_secret", "metrics_token") if re.search(rf"^{c}\s*=", texto, re.M)]
    assert achados == [], f"segredo em claro em {GARAGE_TOML}: {achados}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-19 (portão: 'plat segredo rotacionar <nome> para cada um dos 5 segredos'). Existe "
    "scripts/rotacionar_segredo.sh com 2 nomes admitidos (PLAT_SECRET, PLAT_DSN_WORKER); não existe comando "
    "`plat segredo rotacionar`, não há PLAT_SECRET_ANTERIOR (dupla chave), não há rotação de chave S3 nem "
    "do token admin do Garage, e não há medida de 0 erro 5xx durante a rotação (nenhum k6 no repositório).",
)
def test_rotacao_cobre_os_cinco_segredos_do_portao():
    script = (RAIZ / "scripts" / "rotacionar_segredo.sh").read_text(encoding="utf-8")
    esperados = ["PLAT_SECRET", "PLAT_DSN_WORKER", "PLAT_DSN", "PLAT_GARAGE_ADMIN_TOKEN", "PLAT_GARAGE_S3"]
    faltando = [n for n in esperados if n not in script]
    assert faltando == [], f"segredos sem rotação: {faltando}"


# CORRIGIDO (conferido em 08/09/2026): o ataque não reproduz mais — os segredos saíram do
# .env de produção. A marca xfail estrita saiu; o teste fica valendo como regressão.
@pytest.mark.skipif(
    not (ENV_PRODUCAO.exists() and ENV_HOMOLOG.exists()), reason="ambiente de homologação não instalado"
)
def test_producao_e_homologacao_nao_compartilham_segredo():
    prod, homolog = ler_env(ENV_PRODUCAO), ler_env(ENV_HOMOLOG)
    iguais = sorted(
        c for c in prod if c in homolog and prod[c] == homolog[c] and NOMES_DE_SEGREDO.search(c)
    )
    assert iguais == [], f"segredo idêntico nos dois ambientes: {iguais}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-31 (portão): 'install.sh --ambiente homolog cria tudo idempotente' e 'docs/AMBIENTES.md'. "
    "install.sh não tem nenhuma ocorrência de --ambiente e docs/AMBIENTES.md não existe. Também não há "
    "unidade systemd plat-homolog, logo o MemoryPeak que o portão manda medir não pode ser medido.",
)
def test_artefatos_do_portao_de_homologacao_existem():
    faltando = []
    if "--ambiente" not in (RAIZ / "install.sh").read_text(encoding="utf-8"):
        faltando.append("install.sh --ambiente")
    if not (RAIZ / "docs" / "AMBIENTES.md").exists():
        faltando.append("docs/AMBIENTES.md")
    if not (RAIZ / "deploy" / "plat-homolog.service").exists():
        faltando.append("deploy/plat-homolog.service (sem unidade não há MemoryPeak)")
    assert faltando == [], f"cláusulas do portão sem artefato: {faltando}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-31 (refutação: caminho de homologação para dado de produção). Os schemas de DADO por "
    "inquilino chamam-se d_<slug> e são criados por format() em tempo de execução, dentro de função "
    "PL/pgSQL — texto que o reescritor de schema NUNCA vê. Homologação semeia os mesmos slugs "
    "(plataforma/demo/demo2) que produção, então aponta para os MESMOS schemas físicos. Medido nesta "
    "máquina: d_demo/d_demo2/d_plataforma existem uma única vez, e schemas criados por ambientes de "
    "teste (donos plat_tamc_app, plat_tgadv_app) já convivem no mesmo espaço de nomes.",
)
def test_schema_de_dado_por_inquilino_e_separado_por_ambiente():
    saida = subprocess.run(
        [
            "sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-Atc",
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'd\\_%' ORDER BY 1",
        ],
        capture_output=True, text=True, timeout=120,
    ).stdout.split()
    compartilhados = [n for n in saida if n in ("d_demo", "d_demo2", "d_plataforma")]
    homolog = [n for n in saida if n.startswith("d_homolog") or "_homolog_" in n]
    assert not compartilhados or homolog, (
        f"schemas de dado sem separação por ambiente: {compartilhados} existem uma vez só e servem aos dois"
    )


@pytest.mark.xfail(
    strict=True,
    reason="L7-31: CursorSchemaAmbiente só reescreve quando a consulta é `str` e só no método execute(). "
    "cursor.executemany() é C do psycopg2 e NÃO passa pelo execute() da subclasse; consulta em bytes "
    "(o que execute_values monta) também escapa. As duas chamadas de executemany em "
    "app/auth/rotas_usuarios.py (INSERT em plat.papel_privilegio) vão para o schema plat mesmo com "
    "PLAT_SCHEMA=plat_homolog. Hoje falha fechado só porque o papel não tem USAGE em plat — a isolação "
    "vem do GRANT, não do mecanismo que o item afirma ter.",
)
@pytest.mark.skipif(not os.environ.get("PLAT_DSN"), reason="sem PLAT_DSN no ambiente (rodar sob trilha)")
def test_executemany_respeita_o_schema_do_ambiente():
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from app.settings import settings

    if settings.PLAT_SCHEMA == "plat":
        pytest.skip("só faz sentido fora do schema de produção")
    conexao = psycopg2.connect(settings.PLAT_DSN, cursor_factory=CursorSchemaAmbiente)
    try:
        cur = conexao.cursor()
        cur.execute(f"CREATE TABLE IF NOT EXISTS {settings.PLAT_SCHEMA}.zzz_adv6_executemany(v text)")
        conexao.commit()
        cur.executemany("INSERT INTO plat.zzz_adv6_executemany(v) VALUES (%s)", [("x",)])
        conexao.commit()
    finally:
        conexao.rollback()
        with conexao.cursor() as c:
            c.execute(f"DROP TABLE IF EXISTS {settings.PLAT_SCHEMA}.zzz_adv6_executemany")
        conexao.commit()
        conexao.close()
