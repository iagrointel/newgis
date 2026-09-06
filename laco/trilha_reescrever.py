#!/usr/bin/env python3
"""Reescreve uma migração de db/migracoes/ para o schema de UMA TRILHA (worktree), para que várias
trilhas rodem a suíte ao mesmo tempo sem disputar o schema `plat` de produção nem o flock global.

Mesma ideia do db/reescrever_homolog.py do produto (item L7-31), só que o alvo vem da variável
TRILHA em vez de ser fixo em "homolog". Nada é escrito em disco: imprime o SQL reescrito em stdout.

  schema plat            -> plat_t<trilha>
  schema plat_trabalho   -> plat_trabalho_t<trilha>
  papel  plat_app        -> plat_t<trilha>_app
  papel/canal plat_worker-> plat_t<trilha>_worker
  canal  plat_job        -> plat_t<trilha>_job

Uso: TRILHA=amc trilha_reescrever.py <arquivo.sql>
"""

import os
import re
import sys
from pathlib import Path

REPO = Path("/home/dev/plataforma/enterprise")
sys.path.insert(0, str(REPO))
from app.schema_ambiente import reescrever_schema  # noqa: E402

_PAPEL_APP = re.compile(r"\bplat_app\b")
_PAPEL_WORKER = re.compile(r"\bplat_worker\b")
_CANAL_JOB = re.compile(r"\bplat_job\b")


def nomes(trilha: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-z][a-z0-9]{0,10}", trilha):
        raise SystemExit("TRILHA precisa ser minúscula, começar por letra, até 11 caracteres")
    p = f"plat_t{trilha}"
    return {"schema": p, "schema_trabalho": f"plat_trabalho_t{trilha}",
            "app": f"{p}_app", "worker": f"{p}_worker", "job": f"{p}_job"}


def reescrever(sql: str, trilha: str) -> str:
    n = nomes(trilha)
    sql = reescrever_schema(sql, schema=n["schema"], schema_trabalho=n["schema_trabalho"])
    sql = _PAPEL_APP.sub(n["app"], sql)
    sql = _PAPEL_WORKER.sub(n["worker"], sql)
    sql = _CANAL_JOB.sub(n["job"], sql)
    return sql


if __name__ == "__main__":
    trilha = os.environ.get("TRILHA", "")
    if len(sys.argv) != 2:
        raise SystemExit("uso: TRILHA=<nome> trilha_reescrever.py <arquivo.sql>")
    sys.stdout.write(reescrever(Path(sys.argv[1]).read_text(encoding="utf-8"), trilha))
