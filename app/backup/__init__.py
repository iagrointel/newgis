"""Rotina de backup lógico da plataforma (item L0-06-a-dump-logico; ADR 20260906T2124).

Desenho (fase 1, sem reiniciar o Postgres — archive_mode=off medido e ligar archive num banco
compartilhado com outros serviços da casa é decisão do gerente/dono, fase 2 = L0-06-b-pitr-pgbackrest):

- job `backup.dump_logico` (periódico diário 03:00 no inquilino técnico `plataforma`): pg_dump -Fc do
  schema plat e de cada d_<slug> de inquilino ativo, UM arquivo por inquilino (restaurável por inquilino),
  sha256/bytes/tabelas/tempo em `plat.backup`, cópia para o bucket '<prefixo>backup' do Garage e para o
  destino externo S3 quando configurado, manifesto dos objetos por inquilino gravado junto no bucket.
- retenção de 14 diários + 8 semanais por schema (o dump de domingo é o semanal).
- espaço conferido ANTES de escrever: livre < mínimo (padrão 10 GB) vira job 'falhou' com mensagem e
  notificação ao superadmin (evento + e-mail quando houver SMTP) — nunca silêncio.
- job `backup.verificar`: recalcula o sha256 dos arquivos registrados, acusa divergência (falha), lista
  arquivos órfãos (sem linha) e linhas sem arquivo, e confere os objetos do bucket contra o registrado.

O pg_dump roda como o superusuário local via `sudo -n -u postgres` (mesmo padrão do backup do SIG de teste
interno da casa, pipeline/backup.sh): só assim o dump atravessa a RLS FORCE das tabelas de camada sem papel
novo com BYPASSRLS e senha para guardar. O `-n` falha na hora se o sudoers não cobrir — vira FalhaDefinitiva
com mensagem, e a falha segue o caminho de notificação.
"""
