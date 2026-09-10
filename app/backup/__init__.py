"""Backup lógico por inquilino e ensaio de restauração (item L0-06-backup-status; linha L0 fundação).

Porta para o PLAT o que já roda em produção no SIG de teste interno da casa
(`/home/dev/fgr/sig/pipeline/backup.sh` + `restore_test.sh`, rotas `/api/backups` e
`/api/backups/verificar`): pg_dump -Fc do schema, sha256, tabela de registro, e um ensaio que restaura o
último dump e confere COUNT(*) contra o banco vivo.

Duas diferenças por causa do multi-inquilino do PLAT (nenhum bucket nem banco globais):

1. o dump é do schema `d_<slug>` do PRÓPRIO inquilino que pediu o backup (nunca de outro) e sobe ao bucket
   do PRÓPRIO inquilino no Garage — o mesmo caminho que `app/imagens/ingestao.py` usa para o COG
   (`app/objetos.py::guardar_arquivo`, classe `backup`), não um bucket `plat-backup` à parte;
2. o ensaio de restauração não usa um banco temporário separado (o Postgres é COMPARTILHADO com sistemas
   de cliente e não pode ganhar bancos avulsos nem reiniciar): restaura num SCHEMA temporário da MESMA
   base (`plat_ensaio_<hex>`), convertendo o dump `-Fc` para SQL de texto (`pg_restore -f -`) e trocando o
   nome do schema por substituição de texto antes de rodar — `pg_restore` não tem como renomear o schema
   de destino sozinho (confirmado lendo `restore_test.sh`, que por isso usa um banco `sigcorp_verifica` à
   parte; aqui a regra do turno proíbe tocar/reiniciar o Postgres do jeito que aquele script tocaria).

`app/backup/nucleo.py` é puro (sem banco, sem subprocesso — testável em unidade); `app/backup/tarefas.py`
tem os dois tipos de job (`backup.executar`, `backup.ensaio_restauracao`); `app/backup/periodicos.py`
declara a agenda (pausada); `app/backup/rotas.py` expõe `/api/backup/backups` e `/api/backup/ensaios`.

Fase 2 (PITR físico com pgBackRest, item L0-06-b-pitr-pgbackrest) fica de fora deste turno por decisão já
registrada no ledger: exige `pgbackrest` (apt, root) e `archive_mode=on` no Postgres compartilhado — reinício
que esta trilha não pode fazer.
"""
