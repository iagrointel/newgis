"""Periódicos do catálogo (ADR 0004 seção 11.4), somados à lista PERIODICOS do L0-05 na importação (o worker lê a
lista de app/jobs/periodicos.py ao sincronizar; nenhum arquivo do L0-05 é editado): lixeira diária às 03:50 e
compactação de versões de hora em hora, no minuto 40, no inquilino técnico `plataforma` (era uma vez por dia:
com uma passada diária um item ficava dias acima do teto de 50 linhas — achado G2-3 do adversário)."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("lixeira diária", "50 3 * * *", "catalogo.lixeira_expurgar", {"dias": 30}),
    ("versões de hora em hora", "40 * * * *", "catalogo.versoes_compactar", {"manter": 50}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
