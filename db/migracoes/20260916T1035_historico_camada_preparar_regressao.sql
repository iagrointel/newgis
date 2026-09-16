-- depende: 20260907T1025_historico_feicao.sql
-- depende: 20260907T2030_isolamento_schema_de_dado_com_trinco.sql
--
-- Achado no L2-03-f (edição em lote, item L2-03-f-edicao-em-lote-calculo-campo, 16/09): nenhuma linha
-- nova em plat.feicao_historico depois de um INSERT/UPDATE numa camada criada hoje, apesar de tg_versao
-- e tg_tenant funcionarem normalmente (versão bate, tenant_id bate). Reproduzido fora da suíte:
--
--   SELECT tgname FROM pg_trigger WHERE tgrelid = '<schema>.<tabela>'::regclass AND NOT tgisinternal;
--   -- tg_tenant, tg_versao — tg_historico ausente
--
-- Causa raiz: `20260907T1025_historico_feicao.sql` (10:25) acrescentou a criação de tg_historico dentro
-- de `plat.camada_preparar`, mas `20260907T2030_isolamento_schema_de_dado_com_trinco.sql` (20:30, MESMO
-- dia) redefine a MESMA função inteira (CREATE OR REPLACE) para juntar dois ramos concorrentes (trinco
-- do ADR 0025 + isolamento de schema do ADR 0018) e copiou o corpo de ANTES das 10:25 — sem essas duas
-- linhas o tg_historico nunca mais foi criado. Nenhuma migração posterior toca camada_preparar (conferido
-- em `grep -rl camada_preparar db/migracoes/*.sql`), então toda camada publicada entre 07/09 20:30 e agora
-- está sem histórico por gatilho, em qualquer trilha. A retroativa da 1025 não ajuda: rodou uma vez, antes
-- da regressão, e só cobria o que já existia naquele momento.
--
-- Conserto: redefine `plat.camada_preparar` com o MESMO corpo de 20260907T2030 (trinco + isolamento de
-- schema, intocados) e as duas linhas de tg_historico de volta, na mesma posição relativa (depois de
-- tg_tenant). Retroativa própria (idempotente, condicionada a "trigger ainda ausente") religa quem ficou
-- sem, sem duplicar quem já tem.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE OR REPLACE FUNCTION plat.camada_preparar(p_schema text, p_tabela text, p_srid int, p_tipo text, p_usuario int)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9][a-z0-9_-]{0,80}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual
                   AND plat.camada_schema_prefixo() || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  nome_curto := substr(p_tabela, 3);  -- os 16 hex, sem o prefixo c_ (nome de índice/política/trigger não colide)
  -- trinco pela TABELA: duas tentativas do mesmo carregamento (reexecução do job, retomada) fazem
  -- ALTER/CREATE INDEX/CREATE POLICY na mesma tabela e atualizam as mesmas linhas de catálogo.
  PERFORM pg_advisory_xact_lock(hashtext('camada_preparar:' || p_schema || '.' || p_tabela));

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
  EXECUTE format(
    'CREATE POLICY p_c_%2$s ON %1$I.%3$I FOR ALL TO plat_app, plat_leitor '
    'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
    p_schema, nome_curto, p_tabela
  );
  EXECUTE format('DROP TRIGGER IF EXISTS tg_versao ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_versao BEFORE UPDATE ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_versao()', p_schema, p_tabela);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_tenant ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_tenant BEFORE INSERT ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_inserir()', p_schema, p_tabela);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_historico ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_historico AFTER INSERT OR UPDATE OR DELETE ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_historico_registrar()', p_schema, p_tabela);
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, p_tabela, 'plat camada (L0-04)');
  EXECUTE format('GRANT SELECT ON %1$I.%2$I TO plat_leitor', p_schema, p_tabela);
END $$;
REVOKE EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) TO plat_app;

-- retroativa: só quem ficou sem tg_historico entre 07/09 20:30 e agora (a varredura da 1025 já cobriu o
-- que veio antes; CONTINUE WHEN evita recriar quem já tem, então rodar de novo no futuro não duplica nada).
DO $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT i.dados->>'schema' AS esquema, i.dados->>'tabela' AS tabela
           FROM plat.item i
           WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
             AND coalesce(i.dados->>'fonte', 'hospedada') = 'hospedada'
             AND i.dados->>'schema' ~ '^d_[a-z0-9_-]{1,80}$' AND i.dados->>'tabela' ~ '^c_[0-9a-f]{16}$' LOOP
    CONTINUE WHEN to_regclass(format('%I.%I', r.esquema, r.tabela)) IS NULL;
    CONTINUE WHEN EXISTS (
      SELECT 1 FROM pg_trigger
      WHERE tgrelid = format('%I.%I', r.esquema, r.tabela)::regclass
        AND tgname = 'tg_historico' AND NOT tgisinternal
    );
    EXECUTE format('CREATE TRIGGER tg_historico AFTER INSERT OR UPDATE OR DELETE ON %I.%I '
                   'FOR EACH ROW EXECUTE FUNCTION plat.feicao_historico_registrar()', r.esquema, r.tabela);
    n := n + 1;
  END LOOP;
  RAISE NOTICE 'gatilho de histórico religado em % camada(s) que tinham ficado sem (regressão 07/09 20:30)', n;
END $$;
