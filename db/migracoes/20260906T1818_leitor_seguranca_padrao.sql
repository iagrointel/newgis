-- 20260906T1818_leitor_seguranca_padrao: conserto dos achados F1 e F3 do laudo do adversário do item
-- L2-04-a-leitor-rls-martin (laco/handoffs/T3/L2-04-a-leitor-rls-martin-ADVERSARIO.md). Idempotente.
--
-- F1 — `plat_app` lia o segredo da prova e forjava a prova de qualquer inquilino, porque `001_fundacao.sql`
-- concede SELECT/EXECUTE amplo em `plat.*` a `plat_app` (GRANT ... ON ALL TABLES + DEFAULT PRIVILEGES) e a
-- migração do item só revogou de PUBLIC. O texto do item promete "segredo que só função SECURITY DEFINER
-- lê" — agora é verdade: revoga-se de `plat_app` explicitamente. Isto não abre uma via nova de leitura entre
-- inquilinos (plat_app já é omni-inquilino por desenho), mas fecha o caminho de uma injeção de SQL na API
-- cunhar provas de leitor de qualquer inquilino.
--
-- F3 — `plat.camada_preparar` (029) deixava toda camada nova com a política ALL citando `plat_leitor` e um
-- `GRANT SELECT` direto: sem token, sem prova, um `SET plat.tenant_id` cru bastava para o papel de leitura
-- ler a camada. Só `plat.camada_tile_garantir` (item L2-04-a) corrigia isso depois, criando a política
-- ancorada em `plat.tenant_leitor()`. Qualquer caminho que chame `camada_preparar` sem o segundo passo
-- reabre o vazamento. Conserto: `camada_preparar` deixa de conceder QUALQUER coisa a `plat_leitor` — o
-- estado seguro (leitor sem acesso nenhum) vira o padrão, e só `camada_tile_garantir` habilita a leitura,
-- sempre com a prova. Uma camada que nunca passa por `camada_tile_garantir` agora falha FECHADA (o leitor
-- não tem GRANT na tabela: `permission denied`), não aberta.

-- ---------------------------------------------------------------- F1: revogar de plat_app
REVOKE SELECT ON plat.segredo_leitor FROM plat_app;
REVOKE EXECUTE ON FUNCTION plat.prova_leitor(int) FROM plat_app;

-- ---------------------------------------------------------------- F3: camada_preparar sem plat_leitor
-- Mesma assinatura e mesmo corpo da 029, exceto a política (agora só plat_app) e a remoção do GRANT SELECT
-- final ao papel de leitura. A 029 é legado imutável; esta é a versão vigente da função.
CREATE OR REPLACE FUNCTION plat.camada_preparar(p_schema text, p_tabela text, p_srid int, p_tipo text, p_usuario int)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND 'd_' || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  nome_curto := substr(p_tabela, 3);

  EXECUTE format(
    'ALTER TABLE %1$I.%2$I '
    '  ADD COLUMN IF NOT EXISTS globalid       uuid        NOT NULL DEFAULT gen_random_uuid(), '
    '  ADD COLUMN IF NOT EXISTS versao         int         NOT NULL DEFAULT 1, '
    '  ADD COLUMN IF NOT EXISTS tenant_id      int         NOT NULL DEFAULT %3$L, '
    '  ADD COLUMN IF NOT EXISTS criado_em      timestamptz NOT NULL DEFAULT now(), '
    '  ADD COLUMN IF NOT EXISTS atualizado_em  timestamptz NOT NULL DEFAULT now(), '
    '  ADD COLUMN IF NOT EXISTS criado_por     int, '
    '  ADD COLUMN IF NOT EXISTS atualizado_por int',
    p_schema, p_tabela, t_atual
  );
  EXECUTE format('UPDATE %1$I.%2$I SET criado_por = %3$L, atualizado_por = %3$L WHERE criado_por IS NULL',
                  p_schema, p_tabela, p_usuario);
  BEGIN
    EXECUTE format('ALTER TABLE %1$I.%2$I ADD CONSTRAINT c_%3$s_globalid_u UNIQUE (globalid)',
                    p_schema, p_tabela, nome_curto);
  EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL; END;
  BEGIN
    EXECUTE format('ALTER SEQUENCE %1$I.%2$I_fid_seq MAXVALUE 2147483647 NO CYCLE', p_schema, p_tabela);
  EXCEPTION WHEN undefined_table THEN NULL; END;
  EXECUTE format('CREATE INDEX IF NOT EXISTS c_%2$s_geom_gix ON %1$I.%3$I USING gist (geom)',
                  p_schema, nome_curto, p_tabela);
  EXECUTE format('CREATE INDEX IF NOT EXISTS c_%2$s_versao_ix ON %1$I.%3$I (atualizado_em)',
                  p_schema, nome_curto, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I ENABLE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I FORCE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('DROP POLICY IF EXISTS p_c_%2$s ON %1$I.%3$I', p_schema, nome_curto, p_tabela);
  -- F3: sem plat_leitor aqui. O leitor só ganha acesso pela política que camada_tile_garantir cria,
  -- ancorada em plat.tenant_leitor() (prova por token), nunca pela GUC crua tenant_atual().
  EXECUTE format(
    'CREATE POLICY p_c_%2$s ON %1$I.%3$I FOR ALL TO plat_app '
    'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
    p_schema, nome_curto, p_tabela
  );
  EXECUTE format('DROP TRIGGER IF EXISTS tg_versao ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_versao BEFORE UPDATE ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_versao()', p_schema, p_tabela);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_tenant ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_tenant BEFORE INSERT ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_inserir()', p_schema, p_tabela);
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, p_tabela, 'plat camada (L0-04)');
  -- F3: removido o `GRANT SELECT ON ... TO plat_leitor` que a 029 fazia aqui. Quem concede é só
  -- camada_tile_garantir, junto com a política que exige a prova.
END $$;

-- ---------------------------------------------------------------- F3: retroativo
-- Tabelas já preparadas por camada_preparar (029) que NUNCA passaram por camada_tile_garantir ainda estão
-- com a política antiga (plat_app, plat_leitor) e o GRANT SELECT direto ao leitor. Varre por PADRÃO DE NOME
-- (não pelo catálogo, que só cobre camada_vetorial/hospedada — o ponto do achado é que o padrão vale para
-- qualquer chamador de camada_preparar, catalogado ou não) e conserta só as que ainda não têm a função de
-- tile (quem já tem foi corrigida por camada_tile_garantir e tem GRANT SELECT que este passo NÃO deve
-- revogar, senão quebra a leitura legítima por prova).
DO $$
DECLARE papel text := plat.papel_leitor(); r record; existe_func boolean; n int := 0;
BEGIN
  FOR r IN
    SELECT n.nspname AS esquema, c.relname AS tabela
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname ~ '^d_[a-z0-9_]{1,60}$' AND c.relname ~ '^c_[0-9a-f]{16}$' AND c.relkind = 'r'
  LOOP
    existe_func := to_regprocedure(
      format('%I.%I(integer,integer,integer,json)', r.esquema, 't_' || substr(r.tabela, 3))
    ) IS NOT NULL;
    CONTINUE WHEN existe_func;  -- já passou por camada_tile_garantir: política e GRANT já corretos
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', 'p_c_' || substr(r.tabela, 3), r.esquema, r.tabela);
    EXECUTE format(
      'CREATE POLICY %I ON %I.%I FOR ALL TO plat_app '
      'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
      'p_c_' || substr(r.tabela, 3), r.esquema, r.tabela
    );
    IF has_table_privilege(papel, format('%I.%I', r.esquema, r.tabela), 'SELECT') THEN
      EXECUTE format('REVOKE SELECT ON %I.%I FROM %I', r.esquema, r.tabela, papel);
    END IF;
    n := n + 1;
  END LOOP;
  RAISE NOTICE 'camada_preparar retroativo: % tabela(s) sem função de tile tiveram plat_leitor removido', n;
END $$;
