-- 20260906T1815_rede_fk_por_inquilino: chave estrangeira COMPOSTA (tenant_id, id) na rede de utilidades
-- (item L4-01-a-pacote-de-ativos, achado A1 do adversário do turno 3).
--
-- A migração 20260906T1553 criou as FKs internas de `plat.rede_*` só por `id` (uuid). Isso não é filtrado
-- pela RLS: `plat_app`, autenticado como o inquilino B, consegue inserir uma linha SUA (tenant_id = B) cujo
-- `tipo_id`/`categoria_id`/`dominio_id`/... aponta para uma linha de OUTRO inquilino (A) — a FK só confere que
-- o id existe em algum lugar da tabela, não que é do mesmo tenant_id da linha que está sendo gravada. Medido:
-- um uuid de A é ACEITO como `tipo_id` em `rede_tipo_categoria` de B (oráculo de existência) e a exportação de
-- B passa a dar 500 (`deposito.exportar` indexa por id assumindo que está tudo na mesma rede/inquilino).
--
-- Conserto: toda tabela alvo de uma dessas FKs ganha `UNIQUE (tenant_id, id)` (trivial — `id` já é único
-- sozinho; a restrição composta é só a "porta" para a FK também composta) e toda FK interna passa a ser
-- `(tenant_id, xxx_id) REFERENCES alvo (tenant_id, id)`. Com MATCH SIMPLE (o padrão), uma FK composta com um
-- membro NULL (`terminal_id`, `tipo_id` em `rede_atributo`) não é conferida — mantém a mesma nulidade opcional
-- de antes. `ON DELETE` preserva o comportamento da migração original (CASCADE em tudo, SET NULL em
-- `rede_tipo.terminal_id`). Idempotente: os `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT` rodam de novo sem
-- erro; o `DO $$ ... $$` de UNIQUE confere `pg_constraint` antes de criar.
--
-- A TRAVA fica em `tests/unit/test_fk_composta_por_inquilino.py`: varre `pg_constraint` do schema inteiro e
-- reprova qualquer FK simples (não composta por tenant_id) entre duas tabelas que tenham as duas coluna
-- `tenant_id` — não só as 10 desta rede, qualquer tabela futura do produto.

DO $$
DECLARE alvo text;
BEGIN
  FOREACH alvo IN ARRAY ARRAY['rede', 'rede_dominio', 'rede_tier', 'rede_categoria',
                              'rede_terminal_config', 'rede_grupo', 'rede_tipo'] LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
      WHERE n.nspname = 'plat' AND t.relname = alvo AND c.conname = alvo || '_tenant_id_id_key'
    ) THEN
      EXECUTE format('ALTER TABLE plat.%I ADD CONSTRAINT %I UNIQUE (tenant_id, id)', alvo, alvo || '_tenant_id_id_key');
    END IF;
  END LOOP;
END $$;

-- rede_dominio.rede_id -> rede
ALTER TABLE plat.rede_dominio DROP CONSTRAINT IF EXISTS rede_dominio_rede_id_fkey;
ALTER TABLE plat.rede_dominio DROP CONSTRAINT IF EXISTS rede_dominio_tenant_rede_fkey;
ALTER TABLE plat.rede_dominio ADD CONSTRAINT rede_dominio_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- rede_tier.rede_id -> rede ; rede_tier.dominio_id -> rede_dominio
ALTER TABLE plat.rede_tier DROP CONSTRAINT IF EXISTS rede_tier_rede_id_fkey;
ALTER TABLE plat.rede_tier DROP CONSTRAINT IF EXISTS rede_tier_tenant_rede_fkey;
ALTER TABLE plat.rede_tier ADD CONSTRAINT rede_tier_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tier DROP CONSTRAINT IF EXISTS rede_tier_dominio_id_fkey;
ALTER TABLE plat.rede_tier DROP CONSTRAINT IF EXISTS rede_tier_tenant_dominio_fkey;
ALTER TABLE plat.rede_tier ADD CONSTRAINT rede_tier_tenant_dominio_fkey
  FOREIGN KEY (tenant_id, dominio_id) REFERENCES plat.rede_dominio (tenant_id, id) ON DELETE CASCADE;

-- rede_categoria.rede_id -> rede
ALTER TABLE plat.rede_categoria DROP CONSTRAINT IF EXISTS rede_categoria_rede_id_fkey;
ALTER TABLE plat.rede_categoria DROP CONSTRAINT IF EXISTS rede_categoria_tenant_rede_fkey;
ALTER TABLE plat.rede_categoria ADD CONSTRAINT rede_categoria_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- rede_terminal_config.rede_id -> rede
ALTER TABLE plat.rede_terminal_config DROP CONSTRAINT IF EXISTS rede_terminal_config_rede_id_fkey;
ALTER TABLE plat.rede_terminal_config DROP CONSTRAINT IF EXISTS rede_terminal_config_tenant_rede_fkey;
ALTER TABLE plat.rede_terminal_config ADD CONSTRAINT rede_terminal_config_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- rede_grupo.rede_id -> rede ; rede_grupo.dominio_id -> rede_dominio
ALTER TABLE plat.rede_grupo DROP CONSTRAINT IF EXISTS rede_grupo_rede_id_fkey;
ALTER TABLE plat.rede_grupo DROP CONSTRAINT IF EXISTS rede_grupo_tenant_rede_fkey;
ALTER TABLE plat.rede_grupo ADD CONSTRAINT rede_grupo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_grupo DROP CONSTRAINT IF EXISTS rede_grupo_dominio_id_fkey;
ALTER TABLE plat.rede_grupo DROP CONSTRAINT IF EXISTS rede_grupo_tenant_dominio_fkey;
ALTER TABLE plat.rede_grupo ADD CONSTRAINT rede_grupo_tenant_dominio_fkey
  FOREIGN KEY (tenant_id, dominio_id) REFERENCES plat.rede_dominio (tenant_id, id) ON DELETE CASCADE;

-- rede_tipo.rede_id -> rede ; grupo_id -> rede_grupo ; tier_id -> rede_tier ; terminal_id -> rede_terminal_config
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_rede_id_fkey;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_tenant_rede_fkey;
ALTER TABLE plat.rede_tipo ADD CONSTRAINT rede_tipo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_grupo_id_fkey;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_tenant_grupo_fkey;
ALTER TABLE plat.rede_tipo ADD CONSTRAINT rede_tipo_tenant_grupo_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.rede_grupo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_tier_id_fkey;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_tenant_tier_fkey;
ALTER TABLE plat.rede_tipo ADD CONSTRAINT rede_tipo_tenant_tier_fkey
  FOREIGN KEY (tenant_id, tier_id) REFERENCES plat.rede_tier (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_terminal_id_fkey;
ALTER TABLE plat.rede_tipo DROP CONSTRAINT IF EXISTS rede_tipo_tenant_terminal_fkey;
ALTER TABLE plat.rede_tipo ADD CONSTRAINT rede_tipo_tenant_terminal_fkey
  FOREIGN KEY (tenant_id, terminal_id) REFERENCES plat.rede_terminal_config (tenant_id, id) ON DELETE SET NULL;

-- rede_tipo_categoria.rede_id -> rede ; tipo_id -> rede_tipo ; categoria_id -> rede_categoria
ALTER TABLE plat.rede_tipo_categoria DROP CONSTRAINT IF EXISTS rede_tipo_categoria_rede_id_fkey;
ALTER TABLE plat.rede_tipo_categoria DROP CONSTRAINT IF EXISTS rede_tipo_categoria_tenant_rede_fkey;
ALTER TABLE plat.rede_tipo_categoria ADD CONSTRAINT rede_tipo_categoria_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tipo_categoria DROP CONSTRAINT IF EXISTS rede_tipo_categoria_tipo_id_fkey;
ALTER TABLE plat.rede_tipo_categoria DROP CONSTRAINT IF EXISTS rede_tipo_categoria_tenant_tipo_fkey;
ALTER TABLE plat.rede_tipo_categoria ADD CONSTRAINT rede_tipo_categoria_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_tipo_categoria DROP CONSTRAINT IF EXISTS rede_tipo_categoria_categoria_id_fkey;
ALTER TABLE plat.rede_tipo_categoria DROP CONSTRAINT IF EXISTS rede_tipo_categoria_tenant_categoria_fkey;
ALTER TABLE plat.rede_tipo_categoria ADD CONSTRAINT rede_tipo_categoria_tenant_categoria_fkey
  FOREIGN KEY (tenant_id, categoria_id) REFERENCES plat.rede_categoria (tenant_id, id) ON DELETE CASCADE;

-- rede_atributo.rede_id -> rede ; grupo_id -> rede_grupo ; tipo_id -> rede_tipo (nullable)
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_rede_id_fkey;
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_tenant_rede_fkey;
ALTER TABLE plat.rede_atributo ADD CONSTRAINT rede_atributo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_grupo_id_fkey;
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_tenant_grupo_fkey;
ALTER TABLE plat.rede_atributo ADD CONSTRAINT rede_atributo_tenant_grupo_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.rede_grupo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_tipo_id_fkey;
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_tenant_tipo_fkey;
ALTER TABLE plat.rede_atributo ADD CONSTRAINT rede_atributo_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- rede_regra.rede_id -> rede ; de_tipo_id / para_tipo_id -> rede_tipo
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_rede_id_fkey;
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_tenant_rede_fkey;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_de_tipo_id_fkey;
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_tenant_de_tipo_fkey;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_de_tipo_fkey
  FOREIGN KEY (tenant_id, de_tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_para_tipo_id_fkey;
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_tenant_para_tipo_fkey;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_para_tipo_fkey
  FOREIGN KEY (tenant_id, para_tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
