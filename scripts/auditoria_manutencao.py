#!/usr/bin/env python3
"""Manutenção da trilha de auditoria (item L7-20). Roda como `postgres`, nunca como `plat_app`.

  sudo -u postgres python3 scripts/auditoria_manutencao.py estado      [--schema plat]
  sudo -u postgres python3 scripts/auditoria_manutencao.py agendar     [--schema plat] [--horario '17 3 * * *']
  sudo -u postgres python3 scripts/auditoria_manutencao.py desagendar  [--schema plat]
  sudo -u postgres python3 scripts/auditoria_manutencao.py expurgar    [--schema plat] [--lote 50000]

Por que existe: `plat.auditoria_expurgar` e as funções de agendamento são NEGADAS a `plat_app` de propósito
(se a aplicação pudesse chamá-las, o administrador de um inquilino apagaria a própria trilha pela API). Quem
opera precisa de um caminho nomeado, e é este — nada de SQL solto no terminal.

⚠ pg_cron é recurso GLOBAL da máquina: o nome do job sai de `current_schema()`, então `--schema` decide
qual job se mexe. Ver docs/adr/0021-trilha-auditoria.md, seção "Regra para quem usar pg_cron".
"""

import argparse
import json
import os
import subprocess
import sys


def psql(banco: str, sql: str, *, schema: str) -> str:
    # o search_path vai por PGOPTIONS, não por um `-c SET ...`: um segundo -c faria o psql imprimir também
    # o "SET" da primeira instrução e a saída deixaria de ser só o valor consultado.
    saida = subprocess.run(
        ["psql", "-d", banco, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PGOPTIONS": f"-c search_path={schema},public"},
    )
    if saida.returncode != 0:
        sys.stderr.write(saida.stderr)
        raise SystemExit(saida.returncode)
    return saida.stdout.strip()


def estado(banco: str, schema: str) -> dict:
    nome = psql(banco, "SELECT auditoria_cron_nome()", schema=schema)
    agendados = psql(banco, "SELECT auditoria_cron_contar()", schema=schema)
    linhas = psql(banco, "SELECT count(*) FROM auditoria", schema=schema)
    mais_antiga = psql(banco, "SELECT coalesce(min(em)::text, '')  FROM auditoria", schema=schema)
    por_inquilino = psql(
        banco,
        "SELECT coalesce(json_agg(json_build_object('tenant_id', t.id, 'slug', t.slug, "
        "  'retencao_dias', auditoria_retencao_dias(t.id), "
        "  'linhas', (SELECT count(*) FROM auditoria a WHERE a.tenant_id = t.id)))::text, '[]') FROM tenant t",
        schema=schema,
    )
    return {
        "schema": schema,
        "job_expurgo": nome,
        "jobs_agendados_com_esse_nome": int(agendados),
        "linhas": int(linhas),
        "mais_antiga": mais_antiga or None,
        "inquilinos": json.loads(por_inquilino),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("acao", choices=("estado", "agendar", "desagendar", "expurgar"))
    p.add_argument("--banco", default="iagro_sat")
    p.add_argument("--schema", default="plat")
    p.add_argument("--horario", default="17 3 * * *")
    p.add_argument("--lote", type=int, default=50000)
    a = p.parse_args()
    if a.acao == "estado":
        print(json.dumps(estado(a.banco, a.schema), ensure_ascii=False, indent=1))
    elif a.acao == "agendar":
        nome = psql(a.banco, f"SELECT auditoria_cron_agendar({a.horario!r})", schema=a.schema)
        print(json.dumps({"agendado": nome, "horario": a.horario}, ensure_ascii=False))
    elif a.acao == "desagendar":
        ok = psql(a.banco, "SELECT auditoria_cron_desagendar()", schema=a.schema)
        print(json.dumps({"desagendado": ok == "t"}, ensure_ascii=False))
    else:
        n = psql(a.banco, f"SELECT auditoria_expurgar({a.lote})", schema=a.schema)
        print(json.dumps({"linhas_expurgadas": int(n)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
