"""Backup lógico da plataforma — DUAS frentes no mesmo pacote (nasceram em ramos diferentes, cobrem
alcances diferentes do mesmo item L0-06 e continuam as duas em uso; nenhuma substitui a outra):

## L0-06-a-dump-logico (ADR 20260906T2124) — rotina GLOBAL, inquilino técnico `plataforma`

- job `backup.dump_logico` (periódico diário 03:00): pg_dump -Fc do schema plat e de cada d_<slug> de
  inquilino ativo, UM arquivo por inquilino (restaurável por inquilino), sha256/bytes/tabelas/tempo em
  `plat.backup`, cópia para o bucket '<prefixo>backup' do Garage e para o destino externo S3 quando
  configurado, manifesto dos objetos por inquilino gravado junto no bucket.
- retenção de 14 diários + 8 semanais por schema (o dump de domingo é o semanal).
- espaço conferido ANTES de escrever: livre < mínimo (padrão 10 GB) vira job 'falhou' com mensagem e
  notificação ao superadmin (evento + e-mail quando houver SMTP) — nunca silêncio.
- job `backup.verificar`: recalcula o sha256 dos arquivos registrados, acusa divergência (falha), lista
  arquivos órfãos (sem linha) e linhas sem arquivo, e confere os objetos do bucket contra o registrado.
- job `backup.restore_drill` (item L0-06-c-restore-drill): restaura o último dump de cada esquema num
  banco temporário e compara COUNT(*) contra a produção.

O pg_dump roda como o superusuário local via `sudo -n -u postgres` (mesmo padrão do backup do SIG de teste
interno da casa, pipeline/backup.sh): só assim o dump atravessa a RLS FORCE das tabelas de camada sem papel
novo com BYPASSRLS e senha para guardar. O `-n` falha na hora se o sudoers não cobrir — vira FalhaDefinitiva
com mensagem, e a falha segue o caminho de notificação.

## L0-06-backup-status — backup POR INQUILINO e ensaio de restauração

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
   Jobs: `backup.executar`, `backup.ensaio_restauracao`.

`app/backup/nucleo.py` é puro (sem banco, sem subprocesso — testável em unidade, as duas frentes juntas);
`app/backup/tarefas.py` tem os quatro tipos de job das duas frentes; `app/backup/periodicos.py` declara as
duas agendas (pausadas); `app/backup/rotas.py` expõe `/api/backup/backups` e `/api/backup/ensaios`
(leitura, por inquilino); `app/backup/destino.py` é o destino Garage/S3 global da frente L0-06-a.

Fase 2 (PITR físico com pgBackRest, item L0-06-b-pitr-pgbackrest) fica de fora por decisão já registrada no
ledger: exige `pgbackrest` (apt, root) e `archive_mode=on` no Postgres compartilhado — reinício que nenhuma
das duas frentes pode fazer.
"""
