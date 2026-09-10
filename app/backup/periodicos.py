"""Periódicos do backup (item L0-06-a), somados à lista PERIODICOS do L0-05 na importação (mesmo padrão de
app/catalogo/periodicos.py): dump diário às 03:00 e verificação semanal às segundas 05:30, no inquilino
técnico `plataforma`."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("backup lógico diário", "0 3 * * *", "backup.dump_logico", {"origem": "periodico"}),
    ("verificação de backups", "30 5 * * 1", "backup.verificar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
