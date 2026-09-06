-- 023_arquivos_dedupe_parcial: remove a UNIQUE cheia que ficou em plat.arquivo (tenant_id, classe, referencia,
-- sha256) de uma aplicação anterior desta mesma tabela (uma corrida entre `db/migrar.sh` de outra sessão e a
-- edição deste arquivo fez uma versão SEM o índice parcial ser aplicada primeiro, sob o nome antigo 021_arquivos,
-- nunca commitada; a 022 chegou depois com CREATE TABLE IF NOT EXISTS, que não toca colunas/constraints de tabela
-- já existente). Sem essa remoção, reenviar o mesmo conteúdo depois de apagado (plat.arquivo.apagado_em) violaria
-- a constraint cheia, porque ela não distingue linha viva de linha apagada — só o índice parcial
-- `ix_arquivo_dedupe` (criado pela 022) faz isso. Idempotente.
ALTER TABLE plat.arquivo DROP CONSTRAINT IF EXISTS arquivo_tenant_id_classe_referencia_sha256_key;
