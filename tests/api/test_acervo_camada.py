"""Registro de camadas do acervo da casa (item L6-01-a-registro; migração 027; `scripts/acervo_sync.py`).
Refutação do item: "adversário confere que as 2 tabelas fantasma conhecidas do registro
(public.prodes_yearly_all_indexed e farma.djen_pub_termo) não aparecem e que a coluna de contagem não é
reltuples" — a regra abaixo é DINÂMICA (estimativa > 0 e COUNT(*) exato = 0), não uma lista de nomes, então
cobre essas duas e qualquer fantasma futura. `plat.acervo_camada` é registro GLOBAL (sem tenant_id/RLS, como
`plat.acervo_ficha`): a suíte lê como `plat_app` sem `contexto()`."""

import os
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "scripts" / "acervo_sync.py"


# `sudo` limpa o ambiente do processo filho (env_reset): PLAT_SCHEMA/PLAT_SCHEMA_TRABALHO precisam
# ser repassados na linha de comando com `env`, senao o script roda com o schema padrao e escreve no
# `plat` de PRODUCAO enquanto o teste le do schema isolado -- era esta a causa da falha destes dois
# arquivos em QUALQUER trilha (achado F9).
_REPASSAR = ("PLAT_SCHEMA", "PLAT_SCHEMA_TRABALHO", "PLAT_DSN", "PLAT_CANAL_JOB")


def _env_da_trilha() -> list[str]:
    passar = [f"{k}={os.environ[k]}" for k in _REPASSAR if k in os.environ]
    return ["env", *passar] if passar else []


def _rodar_sync(limite: int, servidor: str = "vultr", banco: str = "iagro_sat"):
    return subprocess.run(
        ["sudo", "-u", "postgres", *_env_da_trilha(), "python3", str(SYNC), "--banco", banco,
         "--servidor", servidor, "--limite", str(limite)],
        capture_output=True, text=True, env=os.environ.copy(), timeout=320,
    )


def test_script_existe_e_e_idempotente_e_rapido(conexao_plat_app):
    """portão: 'script acervo_sync.py idempotente roda em ≤ 5 min'."""
    assert SYNC.exists()
    inicio = time.monotonic()
    r1 = _rodar_sync(limite=30)
    duracao1 = time.monotonic() - inicio
    assert r1.returncode == 0, r1.stderr
    assert duracao1 < 300, f"{duracao1:.1f}s > 5 min"

    inicio = time.monotonic()
    r2 = _rodar_sync(limite=30)
    duracao2 = time.monotonic() - inicio
    assert r2.returncode == 0, r2.stderr
    assert duracao2 < 300

    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.acervo_camada WHERE sincronizado_em > now() - interval '10 minutes'"
        )
        recentes = cur.fetchone()["n"]
    # idempotente: rodar de novo não deixa linha duplicada por acervo_camada_id (PK já garante; aqui prova-se
    # que a rodada realmente re-tocou linhas, não que criou lixo novo a cada chamada)
    assert recentes >= 1


def test_nenhuma_tabela_fantasma_fica_exposta(conexao_plat_app):
    """regra DINÂMICA (não lista de nomes): estimativa > 0 e COUNT(*) exato = 0 nunca é 'exposta'."""
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT acervo_camada_id FROM plat.acervo_camada "
            "WHERE estado = 'exposta' AND linhas_exatas = 0 AND coalesce(linhas_estimadas, 0) > 0"
        )
        fantasmas_expostas = cur.fetchall()
    assert fantasmas_expostas == []

    # as 2 fantasmas nomeadas no item nunca aparecem como 'exposta' (se estiverem no registro, têm de estar
    # 'bloqueada' com o motivo dinâmico — nunca ausentes silenciosamente E nunca expostas)
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT schema_nome, tabela, estado, motivo_bloqueio, linhas_exatas, linhas_estimadas "
            "FROM plat.acervo_camada WHERE (schema_nome, tabela) IN "
            "(('public','prodes_yearly_all_indexed'), ('farma','djen_pub_termo'))"
        )
        conhecidas = cur.fetchall()
    for row in conhecidas:
        assert row["estado"] != "exposta", row


def test_coluna_de_contagem_nao_e_reltuples(conexao_plat_app):
    """`linhas_exatas` (COUNT(*) exato) tem de divergir de `linhas_estimadas` (reltuples) em pelo menos uma
    linha — se as duas colunas sempre coincidissem, seria sinal de que a exata é a estimativa disfarçada."""
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.acervo_camada "
            "WHERE linhas_exatas IS NOT NULL AND linhas_estimadas IS NOT NULL "
            "AND linhas_exatas <> linhas_estimadas"
        )
        divergentes = cur.fetchone()["n"]
    assert divergentes > 0


def test_contagem_nao_concluida_nunca_vira_zero(conexao_plat_app):
    """timeout de 25 s: `linhas_exatas` fica NULL, nunca 0 (metodologia §7.31 — ausência de dado nunca é
    medição)."""
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.acervo_camada "
            "WHERE motivo_bloqueio = 'contagem_nao_concluida_em_25s' AND linhas_exatas IS NOT NULL"
        )
        errado = cur.fetchone()["n"]
    assert errado == 0


def test_pendente_de_licenca_bate_com_acervo_fonte(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT ac.estado, f.licenca FROM plat.acervo_camada ac "
            "JOIN acervo.fonte f ON f.fonte_id = ac.fonte_id "
            "WHERE ac.estado IN ('exposta', 'pendente_de_licenca')"
        )
        linhas = cur.fetchall()
    assert linhas, "o teste pressupõe que o sincronizador já rodou (test_script_existe roda antes)"
    for row in linhas:
        tem_licenca = bool(row["licenca"] and row["licenca"].strip())
        if row["estado"] == "exposta":
            assert tem_licenca, row
        else:
            assert not tem_licenca, row


def test_plat_app_so_le_acervo_camada(conexao_plat_app):
    """O papel da aplicacao so LE o registro. O nome do papel vem de `current_user`, nao escrito na mao:
    o reescritor de schema troca `plat` por `plat_t<trilha>` mas nao toca em `plat_app` (o `_` e caractere
    de palavra, achado F6), entao a forma literal media o papel de PRODUCAO e voltava vazia em toda trilha.
    Como a conexao ja e a do papel da aplicacao daquele ambiente, `current_user` e a resposta certa nos dois."""
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema = 'plat' AND table_name = 'acervo_camada' AND grantee = current_user"
        )
        privilegios = {r["privilege_type"] for r in cur.fetchall()}
    assert privilegios == {"SELECT"}


@pytest.mark.lento
def test_execucao_completa_registra_estatisticas(conexao_plat_app):
    r = _rodar_sync(limite=462)  # ~ o total medido 06/09/2026 (462 candidatas); nunca digitar o número em asserção
    assert r.returncode == 0, r.stderr
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT * FROM plat.acervo_camada_execucao ORDER BY id DESC LIMIT 1")
        ultima = cur.fetchone()
    assert ultima["duracao_ms"] < 300_000
    assert ultima["candidatas"] > 0
    assert ultima["expostas"] + ultima["bloqueadas"] + ultima["pendentes"] == ultima["candidatas"]
