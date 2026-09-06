"""Periódico de `app/conexao/tarefas.py`, somado à lista PERIODICOS do L0-05 na importação (mesmo padrão de
`app/catalogo/periodicos.py`): a cada 15 min (o mínimo do agendador), verificando dentro da execução só as
conexões vencidas há mais de 30 min (`app/conexao/tarefas.py` decide isso, não o cron)."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("saúde das conexões", "*/15 * * * *", "conexoes.saude_verificar", {}),
    # item L6-02-h: o relógio bate a cada 15 min, mas quem decide se JÁ VENCEU é o `proximo_em` de cada linha
    # de plat.conexao_arquivo (intervalo escolhido pelo inquilino, mínimo 15 min, padrão 1 dia).
    ("arquivos por URL vencidos", "*/15 * * * *", "conexoes.arquivo_sincronizar_vencidas", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
