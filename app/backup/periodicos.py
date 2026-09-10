"""Periódicos do backup (item L0-06-backup-status), somados à lista do L0-05 na importação (mesmo padrão de
`app/catalogo/periodicos.py`/`app/conexao/periodicos.py`): backup diário e ensaio de restauração semanal.

Nascem PAUSADOS de propósito (pedido explícito do turno: "sem ligar cron nenhum: só a agenda no banco,
pausada, para o dono decidir") — `sincronizar_periodicos` (`app/jobs/agenda.py`) faz o upsert da LINHA em
`plat.agenda` a cada partida do worker (nome, cron, tipo, parâmetros), mas quem liga/desliga a EXECUÇÃO é o
campo `ativa`, que esta lista não toca: a linha nasce com o padrão de `plat.agenda_periodica_sincronizar`,
que é `ativa = false` para agenda nova (as demais periódicas da casa — expurgo, sessões, ANALYZE — foram
ligadas à mão pelo dono depois de existirem; aqui é a mesma etapa, só que ainda não andada).

Limite honesto que fica registrado aqui: `sincronizar_periodicos` faz o upsert sempre no inquilino TÉCNICO
`plataforma` (é assim que os periódicos de app/jobs/periodicos.py já funcionam — não é um desenho novo
desta trilha). Rodando dali, `backup.executar`/`backup.ensaio_restauracao` fariam backup do schema
`d_plataforma` do próprio inquilino técnico, não de cada inquilino de cliente — backup automático POR
INQUILINO de verdade precisa de uma agenda por tenant, que o sistema de periódicos de hoje não tem (é maior
que este item: cada admin de inquilino já pode disparar `POST /api/jobs {tipo: backup.executar}` a qualquer
momento pela tela /admin/backup, e é isso que fica pronto e testado neste turno)."""

from app.jobs import periodicos as base

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("backup lógico diário", "0 3 * * *", "backup.executar", {"origem": "periodico"}),
    ("ensaio de restauração semanal", "30 4 * * 0", "backup.ensaio_restauracao", {"origem": "periodico"}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
