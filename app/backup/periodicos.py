"""Periódicos do backup — duas frentes somadas à lista PERIODICOS do L0-05 na importação (mesmo padrão de
`app/catalogo/periodicos.py`/`app/conexao/periodicos.py`): a rotina global do inquilino técnico `plataforma`
(item L0-06-a-dump-logico: dump diário 03:00, verificação semanal segunda 05:30, ensaio de restauração
mensal dia 1 às 04:30 — `backup.dump_logico`/`backup.verificar`/`backup.restore_drill`) e o backup POR
INQUILINO (item L0-06-backup-status: `backup.executar`/`backup.ensaio_restauracao`).

Os dois entram PAUSADOS por padrão de `plat.agenda_periodica_sincronizar` (`ativa = false` para agenda
nova; quem liga é o dono, à mão, como as demais periódicas da casa). Limite honesto herdado do desenho
`backup.executar`/`backup.ensaio_restauracao`: `sincronizar_periodicos` faz o upsert sempre no inquilino
TÉCNICO `plataforma` — rodando dali, esses dois fariam backup só do schema `d_plataforma`, não de cada
inquilino de cliente (backup automático por inquilino de verdade precisa de agenda por tenant, que o
sistema de periódicos de hoje não tem; cada admin de inquilino já pode disparar
`POST /api/jobs {tipo: backup.executar}` a qualquer momento pela tela /admin/backup)."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    # L0-06-a-dump-logico (global, inquilino técnico `plataforma`)
    ("backup lógico diário (dump_logico)", "0 3 * * *", "backup.dump_logico", {"origem": "periodico"}),
    ("verificação de backups", "30 5 * * 1", "backup.verificar", {}),
    ("ensaio de restauração (restore_drill)", "30 4 1 * *", "backup.restore_drill", {"origem": "periodico"}),
    # L0-06-backup-status (por inquilino)
    ("backup lógico diário", "0 3 * * *", "backup.executar", {"origem": "periodico"}),
    ("ensaio de restauração semanal", "30 4 * * 0", "backup.ensaio_restauracao", {"origem": "periodico"}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
