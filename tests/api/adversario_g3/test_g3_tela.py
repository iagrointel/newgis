"""Ataque adversarial G3 ao item L0-05-c-tela-tarefas — refutação literal: "adversário abre a tela com
100 mil jobs (paginação obrigatória)". A tela lê GET /api/jobs; este teste mede a API com 100 mil linhas de
plat.job no inquilino, que é o que a primeira pintura espera. Marcado `lento`: insere e APAGA as 100 mil."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

MEDIDAS = Path("tests/medidas/adv-g3-tela.json")


def _psql(sql: str) -> str:
    esquema = os.environ.get("PLAT_SCHEMA", "plat")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t",
                        "-v", "ON_ERROR_STOP=1", "-c", f"SET search_path = {esquema}, public; {sql}"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.lento
def test_primeira_pintura_da_tela_com_100_mil_jobs(sessao_a):
    marcador = "zadv3.cem_mil"
    try:
        # o gatilho da migração 006 obriga o job a nascer pendente e só o worker o conclui; para não
        # disputar a fila, nascem agendados para daqui a um ano (a tela lista igual)
        _psql(f"""INSERT INTO job(tenant_id, tipo, pesado, memoria_mb, timeout_s, agendado_para)
                  SELECT t.id, '{marcador}', false, 128, 60, now() + interval '365 days'
                  FROM tenant t, generate_series(1, 100000) WHERE t.slug = 'demo';""")
        total = int(_psql("SELECT count(*) FROM job;").splitlines()[-1])
        t0 = time.monotonic()
        r = sessao_a.get("/api/jobs?limite=50")
        dt_lista = time.monotonic() - t0
        assert r.status_code == 200, r.text
        corpo = r.json()
        t1 = time.monotonic()
        r2 = sessao_a.get("/api/jobs/resumo")
        dt_resumo = time.monotonic() - t1
        medida = {"jobs_na_base": total, "primeira_pagina_s": round(dt_lista, 3),
                  "resumo_s": round(dt_resumo, 3), "itens_na_pagina": len(corpo["itens"]),
                  "total_declarado": corpo["total"], "resumo_status": r2.status_code}
        MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
        MEDIDAS.write_text(json.dumps(medida, ensure_ascii=False, indent=2), encoding="utf-8")
        assert len(corpo["itens"]) <= 200, "a API devolveu mais que o LIMITE_MAX"
        assert dt_lista <= 1.0, (f"a primeira página da tela levou {dt_lista:.3f} s com {total} jobs "
                                 f"(o portão pede ≤ 1 s com 1.000): {json.dumps(medida)}")
    finally:
        _psql(f"DELETE FROM job WHERE tipo = '{marcador}';")
