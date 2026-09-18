"""Periódicos do backup — duas frentes somadas à lista PERIODICOS do L0-05 na importação (mesmo padrão de
`app/catalogo/periodicos.py`/`app/conexao/periodicos.py`): a rotina global do inquilino técnico `plataforma`
(item L0-06-a-dump-logico: dump diário 03:00, verificação semanal segunda 05:30, ensaio de restauração
mensal dia 1 às 04:30 — `backup.dump_logico`/`backup.verificar`/`backup.restore_drill`) e o backup POR
INQUILINO (item L0-06-backup-status: `backup.executar`/`backup.ensaio_restauracao`).

Os dois do backup por inquilino entram PAUSADOS (quem liga é o dono, à mão, como as demais periódicas da
casa; a decisão está na migração 20260910T2210).

18/09/2026: o limite que este cabeçalho declarava — "o upsert é sempre no inquilino TÉCNICO, então backup
automático por inquilino não existe" — foi RESOLVIDO, não só documentado. Os dois passaram para
`PERIODICOS_POR_INQUILINO`, que `app/jobs/agenda.py::sincronizar_periodicos` aplica a CADA inquilino ativo
(`plat.agenda_periodica_por_inquilino_sincronizar`, migração 20260918T0242). Ligar a agenda passa a ter
efeito sobre dado de cliente; antes, ligá-la faria backup de `d_plataforma` e de mais nada, com sucesso e
sem aviso. O disparo manual por `POST /api/jobs {tipo: backup.executar}` (tela /admin/backup) continua.

⛔ O que segue sendo decisão do dono, e NÃO foi mudado aqui: os dois nascem `ativa = false`. Enquanto
ninguém ligar, "backup diário" continua não sendo o comportamento padrão de nenhum inquilino — o que existe
agora é o interruptor ligado ao lugar certo."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    # L0-06-a-dump-logico (global, inquilino técnico `plataforma`)
    ("backup lógico diário (dump_logico)", "0 3 * * *", "backup.dump_logico", {"origem": "periodico"}),
    ("verificação de backups", "30 5 * * 1", "backup.verificar", {}),
    ("ensaio de restauração (restore_drill)", "30 4 1 * *", "backup.restore_drill", {"origem": "periodico"}),
]

# L0-06-backup-status: estes valem PARA CADA INQUILINO (o 5º campo é `ativa_na_criacao`). Até 18/09/2026
# estavam na lista global e, por isso, só existiam no inquilino técnico `plataforma` — achado do adversário
# do T9, medido em plat.agenda: um inquilino de cliente tinha ZERO linha desses tipos, nem pausada.
# `ativa_na_criacao=False` mantém a decisão de quem os criou (migração 20260910T2210: "agenda no banco,
# pausada, para o dono decidir"); o que muda é que, quando o dono ligar, existe o que ligar em cada
# inquilino, e não uma linha só apontando para `d_plataforma`.
PERIODICOS_POR_INQUILINO: list[tuple[str, str, str, dict, bool]] = [
    ("backup lógico diário", "0 3 * * *", "backup.executar", {"origem": "periodico"}, False),
    ("ensaio de restauração semanal", "30 4 * * 0", "backup.ensaio_restauracao", {"origem": "periodico"}, False),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
for _p in PERIODICOS_POR_INQUILINO:
    if _p not in base.PERIODICOS_POR_INQUILINO:
        base.PERIODICOS_POR_INQUILINO.append(_p)
