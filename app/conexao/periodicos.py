"""Periódico de `app/conexao/tarefas.py`, somado à lista PERIODICOS do L0-05 na importação (mesmo padrão de
`app/catalogo/periodicos.py`): a cada 15 min (o mínimo do agendador), verificando dentro da execução só as
conexões vencidas há mais de 30 min (`app/conexao/tarefas.py` decide isso, não o cron)."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("saúde das conexões", "*/15 * * * *", "conexoes.saude_verificar", {}),
    # L6-02-m: catálogo de conectores públicos, reteste semanal (segunda 04:00), decisão B12
    ("catálogo de conectores públicos", "0 4 * * 1", "endpoints_publicos.retestar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
