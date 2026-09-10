"""Periódicos das imagens (item L1-01-i), somados à lista PERIODICOS do L0-05 na importação (mesmo padrão de
app/catalogo/periodicos.py; nenhum arquivo do L0-05 é editado): coleta de lixo semanal às 05:00 de domingo
no inquilino técnico `plataforma` — o relatório fica em Tarefas; apagar órfão é decisão humana."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("lixo de imagens", "0 5 * * 0", "imagens.raster_gc", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
