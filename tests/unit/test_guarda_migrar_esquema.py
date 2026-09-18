"""Trava: db/migrar.sh recusa quando o ambiente aponta para outro esquema (18/09/2026).

O aplicador fala com `plat.versao_migracao` LITERALMENTE — nao conhece PLAT_SCHEMA. Com o .env de
uma trilha carregado, ele lia e gravava o registro de PRODUCAO, dizia "iguais N / pendentes 0" e nao
migrava a trilha. Efeito medido: a trilha ficava sem a migracao, a instancia dela devolvia 503 em
/saude, e todo teste que sobe aplicacao viva se auto-PULAVA ("uvicorn nao subiu em 10 s"). A clausula
central de L2-04-e (RSS do worker) sumiu assim e o item foi recusado por falta de prova que existia.

Par positivo: prova que RECUSA com esquema de trilha E que ACEITA sem a variavel. So a primeira
metade seria satisfeita por um script que recusa sempre."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MIGRAR = RAIZ / "db" / "migrar.sh"


def _roda(env_extra: dict[str, str], tirar: tuple[str, ...] = ()):
    env = dict(os.environ, **env_extra)
    for k in tirar:
        env.pop(k, None)
    # PLAT_MIGRACOES aponta para pasta vazia: o alvo aqui e a GUARDA, nao aplicar nada.
    env["PLAT_MIGRACOES"] = str(RAIZ / "tests" / "dados" / "migracoes_vazio")
    return subprocess.run(["bash", str(MIGRAR)], cwd=RAIZ, env=env,
                          capture_output=True, text=True, timeout=180)


def test_recusa_quando_o_ambiente_aponta_para_esquema_de_trilha():
    r = _roda({"PLAT_SCHEMA": "plat_tqualquer"})
    assert r.returncode != 0, (r.returncode, r.stdout[-1500:], r.stderr[-1500:])
    assert "RECUSADO" in r.stderr, r.stderr[-1500:]
    assert "migrar_trilha.sh" in r.stderr, r.stderr[-1500:]


def test_nao_recusa_quando_o_esquema_e_o_de_producao():
    """Par positivo: sem PLAT_SCHEMA (ou com plat) a guarda tem de ficar calada.

    Nao exige rc=0: com a pasta de migracoes vazia o script sai com 2 ('nenhuma migração'), o que ja
    prova que passou da guarda."""
    for env_extra, tirar in (({}, ("PLAT_SCHEMA",)), ({"PLAT_SCHEMA": "plat"}, ())):
        r = _roda(env_extra, tirar)
        assert "RECUSADO" not in r.stderr, (env_extra, r.stderr[-1500:])
