-- 20260907T1308_rede_conserta_fk_regra_set_null: corrige a FK composta de `regra_id` em
-- `plat.rede_conexao`/`plat.rede_associacao` (migração 20260906T2058), achado ao exercitar
-- `checar_regra_inexistente` do item L4-03-d-areas-sujas-e-validacao.
--
-- O bug: `FOREIGN KEY (tenant_id, regra_id) REFERENCES plat.rede_regra (tenant_id, id) ON DELETE
-- SET NULL` é uma FK de DUAS colunas — e o Postgres zera TODAS as colunas do lado referenciador
-- num `ON DELETE SET NULL` composto, não só a que mudou de sentido. Apagar (ou reimportar por CSV,
-- que apaga e reinsere) uma regra ainda usada por uma conexão/associação tenta gravar
-- `tenant_id = NULL` na linha — e como `tenant_id` é `NOT NULL`, o `DELETE` inteiro do conjunto de
-- regras falha com `NotNullViolation`. Every reimportação de CSV que remove uma regra em uso
-- quebra a rota inteira; nunca foi pego porque nenhum teste anterior tinha conexão derivada E
-- reimportava CSV na mesma rede.
--
-- O conserto: FK de UMA coluna só (`regra_id` -> `rede_regra.id`, sem `tenant_id`). Correção
-- segura porque `regra_id` só é gravado por `rotas_regras.py`/`regras_csv.py`, sempre com uma
-- regra JÁ carregada da mesma rede (logo do mesmo tenant) — não abre brecha de cruzar inquilino,
-- só deixa de duplicar a garantia com uma segunda coluna que o `ON DELETE SET NULL` não sabe tratar
-- parcialmente. Idempotente.

ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_tenant_regra_fkey;
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_regra_fkey;
ALTER TABLE plat.rede_conexao ADD CONSTRAINT rede_conexao_regra_fkey
  FOREIGN KEY (regra_id) REFERENCES plat.rede_regra (id) ON DELETE SET NULL;

ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tenant_regra_fkey;
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_regra_fkey;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_regra_fkey
  FOREIGN KEY (regra_id) REFERENCES plat.rede_regra (id) ON DELETE SET NULL;
