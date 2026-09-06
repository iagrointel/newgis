#!/usr/bin/env python3
"""Reescreve uma migração de db/migracoes/ para o AMBIENTE DE HOMOLOGAÇÃO (item L7-31; docs/HOMOLOGACAO.md):
usado por db/migrar_homolog.sh, nunca chamado à mão em produção.

  schema  plat            -> plat_homolog          (reescrever_schema, MESMA regra do cursor da app:
  schema  plat_trabalho    -> plat_trabalho_homolog  GUC customizado como 'plat.tenant_id' fica de fora)
  papel   plat_app         -> plat_homolog_app
  papel/canal plat_worker  -> plat_homolog_worker    (mesmo token nas duas migrações: CREATE ROLE, GRANT,
                                                       pg_notify('plat_worker', ...), rolname = 'plat_worker')
  canal   plat_job         -> plat_homolog_job       (só notificação; não existe papel com esse nome)

Sem isso, aplicar as migrações originais duas vezes na mesma base criaria os MESMOS objetos (`plat.job`,
role `plat_app`) e a segunda aplicação ou colide com a primeira ou, pior, opera em cima do schema de
produção. Nada aqui é escrito em disco: lê o arquivo pedido e imprime o SQL reescrito em stdout.

Uso: reescrever_homolog.py <arquivo.sql>
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.schema_ambiente import reescrever_schema  # noqa: E402

_PAPEL_APP = re.compile(r"\bplat_app\b")
_PAPEL_WORKER = re.compile(r"\bplat_worker\b")  # papel E canal de notificação: mesmo token, mesma troca
_CANAL_JOB = re.compile(r"\bplat_job\b")

SCHEMA_HOMOLOG = "plat_homolog"
SCHEMA_TRABALHO_HOMOLOG = "plat_trabalho_homolog"
PAPEL_APP_HOMOLOG = "plat_homolog_app"
PAPEL_WORKER_HOMOLOG = "plat_homolog_worker"
CANAL_JOB_HOMOLOG = "plat_homolog_job"


def reescrever_homolog(sql: str) -> str:
    sql = reescrever_schema(sql, schema=SCHEMA_HOMOLOG, schema_trabalho=SCHEMA_TRABALHO_HOMOLOG)
    sql = _PAPEL_APP.sub(PAPEL_APP_HOMOLOG, sql)
    sql = _PAPEL_WORKER.sub(PAPEL_WORKER_HOMOLOG, sql)
    sql = _CANAL_JOB.sub(CANAL_JOB_HOMOLOG, sql)
    return sql


def main() -> None:
    if len(sys.argv) != 2:
        print("uso: reescrever_homolog.py <arquivo.sql>", file=sys.stderr)
        raise SystemExit(2)
    caminho = Path(sys.argv[1])
    sys.stdout.write(reescrever_homolog(caminho.read_text()))


if __name__ == "__main__":
    main()
