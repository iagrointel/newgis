#!/usr/bin/env python3
"""Recomputa o `versao_hash` de um modelo AMC POR FORA da aplicação (item L3-01-a-modelo-dado, cláusula do
portão "hash recomputado por script independente"). Não importa `app.amc.esquema` nem `app.catalogo.documento`
de propósito — reimplementa a fórmula (json.dumps com sort_keys e separadores fixos, sha256 do utf-8) do zero,
para que um bug nessas funções não escape à prova.

    python3 scripts/amc_hash_independente.py --arquivo definicao.json
    python3 scripts/amc_hash_independente.py --tenant 3                 # confere cada modelo do inquilino
    python3 scripts/amc_hash_independente.py --tenant 3 --modelo <uuid> # só um

O modo `--tenant`/`--modelo` conecta com `PLAT_DSN` do ambiente (o mesmo `.env`/trilha que a API usa) e honra
`PLAT_SCHEMA` (padrão `plat`) via `SET search_path` — nunca um `FROM plat.amc_modelo` escrito na mão, que
ignoraria o schema de uma trilha ou de `plat_homolog` (achado do laudo do rascunho anterior deste item,
`laco/handoffs/T3/L3-01-ADVERSARIO.md` §"⚠ O modo --tenant do script está preso ao schema plat")."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def hash_canonico(definicao: dict) -> str:
    canonico = json.dumps(definicao, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _modo_arquivo(caminho: str) -> int:
    definicao = json.loads(Path(caminho).read_text(encoding="utf-8"))
    print(hash_canonico(definicao))
    return 0


def _modo_tenant(tenant_id: int, modelo_id: str | None) -> int:
    import psycopg2
    import psycopg2.extras

    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        print("PLAT_DSN não está no ambiente (source o .env ou o laco/var/trilha/<trilha>.env)", file=sys.stderr)
        return 2
    schema = os.environ.get("PLAT_SCHEMA", "plat")
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with con.cursor() as cur:
            cur.execute(f"SET search_path = {psycopg2.extensions.quote_ident(schema, con)}, public")
            # RLS de plat.amc_modelo exige o contexto de inquilino (plat.tenant_atual(), lido de
            # current_setting('plat.tenant_id')) — sem isto toda consulta devolve 0 linhas, igual a
            # "sem contexto" em tests/api/test_rls.py; usuario_id/login são só para o log de acesso.
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', '0', true), "
                "set_config('plat.login', 'amc_hash_independente', true)",
                (str(tenant_id),),
            )
            sql = "SELECT id, nome, definicao, versao_hash, executado FROM amc_modelo WHERE tenant_id = %s"
            params: list = [tenant_id]
            if modelo_id:
                sql += " AND id = %s"
                params.append(modelo_id)
            cur.execute(sql + " ORDER BY criado_em", params)
            linhas = cur.fetchall()
        con.rollback()
    finally:
        con.close()

    if not linhas:
        print(f"nenhum modelo encontrado (tenant={tenant_id}, schema={schema})", file=sys.stderr)
        return 1

    divergentes = 0
    for r in linhas:
        recomputado = hash_canonico(r["definicao"])
        ok = recomputado == r["versao_hash"]
        if not ok:
            divergentes += 1
        print(f"{r['id']}  gravado={r['versao_hash']}  recomputado={recomputado}  {'OK' if ok else 'DIVERGENTE'}"
              f"  executado={r['executado']}  nome={r['nome']!r}")
    print(f"\nschema={schema}  modelos={len(linhas)}  divergentes: {divergentes}")
    return 1 if divergentes else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", help="caminho de um JSON com a definição do modelo")
    ap.add_argument("--tenant", type=int, help="id do inquilino (plat.tenant.id); confere no banco")
    ap.add_argument("--modelo", help="uuid de um modelo específico (com --tenant); sem isto, confere todos")
    args = ap.parse_args()

    if args.arquivo and args.tenant:
        ap.error("--arquivo e --tenant são exclusivos")
    if args.arquivo:
        return _modo_arquivo(args.arquivo)
    if args.tenant:
        return _modo_tenant(args.tenant, args.modelo)
    ap.error("informe --arquivo <caminho> ou --tenant <id>")
    return 2


if __name__ == "__main__":
    sys.exit(main())
