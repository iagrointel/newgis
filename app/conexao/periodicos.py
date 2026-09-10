"""Periódicos de `app/conexao/tarefas.py` e `app/conexao/tarefas_agendamento.py`, somados à lista PERIODICOS
do L0-05 na importação (mesmo padrão de `app/catalogo/periodicos.py`): "saúde das conexões" a cada 15 min (o
mínimo do agendador), verificando dentro da execução só as conexões vencidas há mais de 30 min; "avisos de
agenda" também a cada 15 min (item L6-02-k), drenando `plat.agenda_aviso` (agenda pausada por 5 falhas
seguidas) — o teto de 1 e-mail a cada 6h por agenda já é decidido na ENTRADA da fila, não aqui."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("saúde das conexões", "*/15 * * * *", "conexoes.saude_verificar", {}),
    ("avisos de agenda", "*/15 * * * *", "agenda.avisos_enviar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
