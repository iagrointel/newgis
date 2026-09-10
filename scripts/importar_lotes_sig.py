#!/usr/bin/env python3
"""Importa os lotes derivados do SIG de teste interno (dado aberto, schema `sigcorp` — SÓ
LEITURA) como parcelas do tipo 'lote' com registro sintético (item
L4-parcelas-01-modelo-de-parcelas; cláusula do portão).

    set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
    python3 scripts/importar_lotes_sig.py [--tenant demo] [--empreendimento N] [--limite N]

Dois caminhos de privilégio, de propósito:
  - LEITURA da origem: `sudo -u postgres psql -c COPY (...) TO STDOUT` — o papel da trilha não
    enxerga `sigcorp`, e assim ele nunca vai enxergar; a origem inteira é lida como fluxo CSV
    (sem matrícula, sem nome: só empreendimento_id, código do lote e geometria).
  - ESCRITA na malha: a conexão comum da trilha (`PLAT_DSN`, papel `plat_*_app`, RLS valendo) —
    o import grava no inquilino escolhido e respeita os tetos de `app/limites.py`.

O import NÃO é idempotente de propósito: rodar duas vezes cria dois registros (um segundo
registro é um segundo documento na malha, não a mesma carga). Imprime a contagem da rodada
que `tests/medidas/L4-parcelas-01-modelo-de-parcelas.json` registra.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Contexto, db  # noqa: E402
from app.parcelas.importar import importar_lotes  # noqa: E402

ORIGEM_SQL = (
    "COPY (SELECT l.empreendimento_id, l.codigo, ST_AsText(l.geom) "
    "FROM sigcorp.lote l {onde} ORDER BY l.id) TO STDOUT WITH (FORMAT csv)"
)


def ler_origem(empreendimento: int | None) -> list[dict]:
    onde = "WHERE l.empreendimento_id = %d" % empreendimento if empreendimento else ""
    cmd = ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-q", "-v", "ON_ERROR_STOP=1",
           "-c", ORIGEM_SQL.format(onde=onde)]
    fluxo = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [
        {"empreendimento_id": int(r[0]), "codigo": r[1], "wkt": r[2]}
        for r in csv.reader(io.StringIO(fluxo))
        if r and r[0]
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", default="demo", help="nome (ou id) do inquilino de destino")
    ap.add_argument("--empreendimento", type=int, default=None, help="só este empreendimento de origem")
    ap.add_argument("--limite", type=int, default=None, help="importa só os N primeiros (prova)")
    a = ap.parse_args()
    lotes = ler_origem(a.empreendimento)
    if a.limite:
        lotes = lotes[: a.limite]
    with db() as cur:
        cur.execute("SELECT id FROM plat.tenant WHERE nome = %s OR id::text = %s",
                    (a.tenant, a.tenant))
        t = cur.fetchone()
        if t is None:
            print(f"inquilino {a.tenant} não existe nesta base", file=sys.stderr)
            return 2
        tenant_id = int(t["id"])
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        u = cur.fetchone()
        ctx = Contexto(tenant_id=tenant_id, usuario_id=int(u["id"]) if u else 0, login="importar-lotes-sig")
    with db(ctx) as cur:
        resumo = importar_lotes(cur, tenant_id, lotes)
    print(json.dumps(resumo, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
