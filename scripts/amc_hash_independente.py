#!/usr/bin/env python3
"""Recomputa, POR FORA da aplicação, o hash de versão de um modelo multicritério e confere com o gravado.

Este script não importa `app.amc.esquema` de propósito: a regra do hash está escrita aqui de novo, a partir do texto
do ADR 0016 e do `docs/esquemas/amc_modelo.v1.json`, para que uma mudança silenciosa no módulo da aplicação apareça
como divergência. É o que o adversário roda (item L3-01-a, cláusula "hash recomputado por script independente").

Regra do hash: sha256 sobre `json.dumps(definicao, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
codificado em UTF-8, com a normalização numérica do ADR 0016 aplicada antes: número de ponto flutuante com parte
fracionária zero e magnitude < 2^53 vira inteiro (em JSON `3` e `3.0` são o mesmo número). A regra está reescrita
aqui, não importada.

Uso:
  python3 scripts/amc_hash_independente.py --arquivo modelo.json
      imprime o hash do documento no arquivo (um objeto JSON).
  python3 scripts/amc_hash_independente.py --tenant 3
      conecta com PLAT_DSN (role plat_app, RLS), põe o contexto do inquilino e confere TODA versão gravada em
      <PLAT_SCHEMA>.amc_modelo_versao, além de conferir que a cabeça de cada modelo aponta para uma versão existente.

Saída: uma linha por versão conferida e um resumo. Código 0 = tudo bate; 1 = divergência (com a lista); 2 = uso.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def normalizar(valor):
    """Normalização numérica do ADR 0016, reescrita aqui de propósito (não importa app.amc.esquema). Sem recursão:
    o documento pode ter milhares de níveis de aninhamento em `extrator.parametros`."""
    def escalar(v):
        if isinstance(v, bool):
            return v
        return int(v) if isinstance(v, float) and v.is_integer() and abs(v) < 2.0 ** 53 else v

    if not isinstance(valor, (dict, list)):
        return escalar(valor)
    raiz = {} if isinstance(valor, dict) else []
    pendentes = [(valor, raiz)]
    while pendentes:
        origem, destino = pendentes.pop()
        if isinstance(destino, list):
            destino.extend([None] * len(origem))
        for chave, v in (origem.items() if isinstance(origem, dict) else enumerate(origem)):
            if isinstance(v, (dict, list)):
                copia = {} if isinstance(v, dict) else []
                pendentes.append((v, copia))
            else:
                copia = escalar(v)
            destino[chave] = copia
    return raiz


def hash_canonico(definicao) -> str:
    canonico = json.dumps(normalizar(definicao), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def dsn_do_env() -> str:
    if os.environ.get("PLAT_DSN"):
        return os.environ["PLAT_DSN"]
    caminho = RAIZ / ".env"
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if linha.startswith("PLAT_DSN="):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")
    print("sem PLAT_DSN no ambiente nem em .env", file=sys.stderr)
    sys.exit(2)


def schema_do_env() -> str:
    """O ambiente (homologação, base por trilha) troca o schema por PLAT_SCHEMA; sem isso a auditoria só alcançava
    a produção — apontado pelo adversário do item L3-01-a."""
    if os.environ.get("PLAT_SCHEMA"):
        return os.environ["PLAT_SCHEMA"]
    caminho = RAIZ / ".env"
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if linha.startswith("PLAT_SCHEMA="):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")
    return "plat"


def conferir_banco(tenant_id: int, dsn: str, schema: str) -> int:
    import psycopg2
    import psycopg2.extras

    if not schema.replace("_", "").isalnum():
        print(f"nome de schema inválido: {schema!r}", file=sys.stderr)
        return 2
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = con.cursor()
        cur.execute(f"SET search_path = {schema}, public")
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', '0', true), "
                    "set_config('plat.login', 'amc_hash_independente', true)", (str(tenant_id),))
        cur.execute(f"SELECT modelo_id, versao_hash, numero, definicao FROM {schema}.amc_modelo_versao "
                    "ORDER BY modelo_id, numero")
        versoes = cur.fetchall()
        cur.execute(f"SELECT id, versao_hash FROM {schema}.amc_modelo")
        cabecas = cur.fetchall()
    finally:
        con.rollback()
        con.close()

    divergentes = []
    for v in versoes:
        recomputado = hash_canonico(v["definicao"])
        ok = recomputado == v["versao_hash"]
        if not ok:
            divergentes.append((str(v["modelo_id"]), v["numero"], v["versao_hash"], recomputado))
        print(f"{'ok  ' if ok else 'ERRO'} modelo {v['modelo_id']} versão {v['numero']}: gravado {v['versao_hash']} "
              f"· recomputado {recomputado}")

    conhecidas = {(str(v["modelo_id"]), v["versao_hash"]) for v in versoes}
    orfas = [str(c["id"]) for c in cabecas if (str(c["id"]), c["versao_hash"]) not in conhecidas]
    for mid in orfas:
        print(f"ERRO modelo {mid}: a cabeça aponta para uma versão que não existe")

    print(f"\nversões conferidas: {len(versoes)} · divergentes: {len(divergentes)} · cabeças órfãs: {len(orfas)}")
    return 1 if (divergentes or orfas) else 0


def main() -> int:
    p = argparse.ArgumentParser(description="recomputa o hash de versão de modelo AMC por fora da aplicação")
    p.add_argument("--arquivo", help="JSON com a definição do modelo; imprime o hash e sai")
    p.add_argument("--tenant", type=int, help="id do inquilino: confere toda versão gravada")
    p.add_argument("--dsn", help="DSN do PostgreSQL (padrão: PLAT_DSN do ambiente ou do .env)")
    p.add_argument("--schema", help="schema a auditar (padrão: PLAT_SCHEMA do ambiente ou do .env, senão plat)")
    a = p.parse_args()
    if a.arquivo:
        print(hash_canonico(json.loads(Path(a.arquivo).read_text(encoding="utf-8"))))
        return 0
    if a.tenant is None:
        p.print_help()
        return 2
    return conferir_banco(a.tenant, a.dsn or dsn_do_env(), a.schema or schema_do_env())


if __name__ == "__main__":
    sys.exit(main())
