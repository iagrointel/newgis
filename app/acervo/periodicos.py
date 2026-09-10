"""Periódico do frescor do acervo (item L6-01-h-frescor-verificacao), somado à lista PERIODICOS do L0-05 na
importação — mesmo padrão de `app/catalogo/periodicos.py`, `app/conexao/periodicos.py` e
`app/uploads/periodicos.py`, e pela mesma razão: nenhum arquivo do L0-05 é editado por esta trilha.

Semanal, domingo 05:20 (America/Sao_Paulo): depois do `manutencao_analyze` de domingo 04:00 (as estimativas do
planejador já estão em dia quando as contagens exatas rodam) e antes do horário comercial. A janela de
recontagem dentro do job é de 6 dias, não de 7: uma rodada que atrase alguns minutos não pula a semana."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("frescor do acervo", "20 5 * * 0", "acervo.frescor_verificar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
