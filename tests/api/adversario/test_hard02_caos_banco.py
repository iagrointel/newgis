"""HARD-02 (caos) — matar a conexão do Postgres no meio e provar que a API se recupera. Um dos 3 cenários de caos
do portão: `pg_terminate_backend` derruba TODOS os backends da role da aplicação da trilha; a próxima requisição
tem de responder 200 (o pool de app/db.py descarta a conexão morta e repete a preparação), nunca uma cascata de
500. Cenário seguro em produção: age só sobre a role da trilha (plat_t<nome>_app), nunca sobre `plat_app`. Marcado
`lento`; só roda em trilha (conftest do pacote)."""

from __future__ import annotations

import os
import subprocess

import pytest


def _role_da_trilha() -> str:
    # a role da aplicação da trilha é derivada do schema (plat_t<nome> -> plat_t<nome>_app); não usa uma conexão
    # compartilhada, que este próprio teste vai derrubar.
    schema = os.environ.get("PLAT_SCHEMA", "plat")
    return "plat_app" if schema == "plat" else f"{schema}_app"


def _matar_backends(role: str) -> int:
    """Encerra todos os backends da role via superusuário local; devolve quantos foram encerrados."""
    sql = (f"SELECT count(pg_terminate_backend(pid)) AS n FROM pg_stat_activity "
           f"WHERE usename = '{role}' AND pid <> pg_backend_pid()")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-tAc", sql],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return int((r.stdout.strip() or "0"))


@pytest.mark.lento
def test_conexao_do_banco_morta_no_meio_a_api_se_recupera(sessao_a):
    role = _role_da_trilha()
    assert role.startswith("plat_t") and role.endswith("_app") and role != "plat_app", role  # nunca produção
    # controle positivo: antes do caos, a API responde
    assert sessao_a.get("/api/eu").status_code == 200
    # aquece o pool com algumas requisições (para haver backends vivos a derrubar)
    for _ in range(3):
        sessao_a.get("/api/itens?limite=1")
    mortos = _matar_backends(role)
    assert mortos >= 1, "nenhum backend da role da trilha foi encerrado (pool vazio?)"
    # a PRÓXIMA requisição não pode virar 500: o pool descarta a conexão morta e repete a preparação.
    # (o servidor real pode ter mais de uma conexão morta na fila; algumas requisições seguidas cobrem isso.)
    codigos = [sessao_a.get("/api/eu").status_code for _ in range(5)]
    assert 200 in codigos, codigos
    assert all(c != 500 for c in codigos), codigos
    # e o estado firme depois: duas requisições seguidas 200
    assert sessao_a.get("/api/eu").status_code == 200
    assert sessao_a.get("/api/itens?limite=1").status_code == 200
