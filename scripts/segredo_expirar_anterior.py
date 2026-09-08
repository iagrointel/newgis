#!/usr/bin/env python3
"""Expira o PLAT_SECRET_ANTERIOR 24 h depois de uma rotação (item L7-19-segredos-e-certificados).

`plat segredo rotacionar PLAT_SECRET` grava o valor antigo em /etc/plat/segredos/PLAT_SECRET_ANTERIOR
(dupla-chave: o que foi cifrado/assinado com a chave velha continua legível) e o carimbo em
PLAT_SECRET_ANTERIOR_EM. A hipótese do item diz "por 24 h" — sem este expirador o valor antigo valia
até ação humana (achado do adversário do T7). Este script roda pelo timer plat-segredo-expira.timer
(de hora em hora, como root): passadas 24 h do carimbo, esvazia o ANTERIOR e reinicia plat-api e
plat-worker — o arquivo é lido na subida do processo, então a retirada só vale de verdade com o
restart (try-restart: não sobe quem está parado de propósito). Janela efetiva: 24 h a 24 h 59 min
(granularidade do timer), documentada no runbook.

Sem carimbo, carimbo malformado ou ANTERIOR já vazio: sai sem fazer nada (idempotente).
"""

from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path

CRED_DIR = Path("/etc/plat/segredos")
JANELA_H = 24


def main() -> int:
    carimbo_path = CRED_DIR / "PLAT_SECRET_ANTERIOR_EM"
    anterior_path = CRED_DIR / "PLAT_SECRET_ANTERIOR"
    if not carimbo_path.exists():
        return 0
    try:
        quando = datetime.datetime.strptime(
            carimbo_path.read_text(encoding="utf-8").strip(), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=datetime.timezone.utc)
    except (ValueError, OSError) as e:
        print(f"carimbo de PLAT_SECRET_ANTERIOR_EM ilegível ({e}) — nada expirado", file=sys.stderr)
        return 1
    idade = datetime.datetime.now(datetime.timezone.utc) - quando
    if idade < datetime.timedelta(hours=JANELA_H):
        return 0
    if not anterior_path.exists() or anterior_path.stat().st_size == 0:
        carimbo_path.unlink(missing_ok=True)
        return 0
    anterior_path.write_text("", encoding="utf-8")
    carimbo_path.unlink(missing_ok=True)
    print(
        f"PLAT_SECRET_ANTERIOR expirado após {idade} (janela de {JANELA_H} h): arquivo esvaziado; "
        "reiniciando plat-api e plat-worker para a retirada valer nos processos vivos"
    )
    subprocess.run(["systemctl", "try-restart", "plat-api", "plat-worker"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
