-- depende: 20260907T0240_ddl_concorrente_trinco.sql
-- depende: 20260907T0245_isolamento_schema_de_dado.sql
--
-- Junção de dois consertos que redefinem as MESMAS funções SECURITY DEFINER:
--
--   * 20260907T0240 (ramo wt/conc, ADR 0025) pôs `pg_advisory_xact_lock` antes de todo DDL que
--     atualiza linha de catálogo (CREATE SCHEMA, GRANT), porque duas sessões do mesmo inquilino
--     publicando camada ao mesmo tempo terminavam em `tuple concurrently updated`.
--   * 20260907T0245 (este ramo, ADR 0018) fez o schema de dado carregar a INSTALAÇÃO
--     (`plat.camada_schema_prefixo()`), porque `d_<slug>` não contém a palavra `plat` e por isso
--     escapava do tradutor de app/schema_ambiente.py: produção, homologação e trilhas gravavam
--     todas no mesmo `d_demo`.
--
-- Como a 0245 tem carimbo POSTERIOR, aplicar as duas na ordem deixaria as versões sem trinco de pé e
-- `tests/api/test_camada_schema_corrida.py::test_toda_funcao_com_ddl_tem_trinco` reprovaria — que é
-- exatamente o aviso escrito no cabeçalho da 0240. Este arquivo redefine as três funções UMA vez, com
-- as duas propriedades juntas. Nada é apagado nem renomeado.
--
-- CHAVE DO TRINCO: o objeto que o DDL toca. Com o isolamento, o objeto não é mais `d_<slug>` e sim
-- `plat.camada_schema_prefixo() || slug`, que é diferente em cada instalação. Por isso a chave passa a
-- ser o NOME DO SCHEMA, e não o slug: duas instalações com o mesmo apelido de inquilino tocam schemas
-- diferentes e não têm por que esperar uma pela outra. Dentro de uma instalação nada muda — mesmo
-- inquilino, mesma chave, e `camada_schema_garantir` e `tenant_criar` continuam dividindo a chave
-- porque criam o mesmo schema. `camada_preparar` mantém a chave da 0240 (schema + tabela), que já
-- carregava o prefixo da instalação dentro de `p_schema`. Colisão de `hashtext` entre chaves distintas
-- só causaria espera desnecessária, nunca erro.
--
-- ALFABETO: união dos dois ramos. A 0240 preservou de propósito o alfabeto de
-- `20260906T1607_slug_ingestao_reconciliado.sql` (ramo wt/g3fix, ainda não juntado), que aceita `-`; a
-- 0245 precisou aceitar `_` e nomes mais longos, porque o schema de uma trilha é
-- `d_plat_t<nome>_<slug>`. A união aceita os dois e continua recusando qualquer outra coisa.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE esq text;
BEGIN
  IF p_slug !~ '^[a-z0-9][a-z0-9_-]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  esq := plat.camada_schema_prefixo() || p_slug;
  PERFORM pg_advisory_xact_lock(hashtext('camada_schema_garantir:' || esq));
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', esq);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', esq);
END $$;
REVOKE EXECUTE ON FUNCTION plat.camada_schema_garantir(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;

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
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, p_tabela, 'plat camada (L0-04)');
  EXECUTE format('GRANT SELECT ON %1$I.%2$I TO plat_leitor', p_schema, p_tabela);
END $$;
REVOKE EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) TO plat_app;

-- tenant_criar cria o MESMO schema que camada_schema_garantir: divide a chave, senão criar inquilino
-- ao mesmo tempo que outra sessão publica camada nele volta a colidir.
CREATE OR REPLACE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb,
  p_admin_login text, p_admin_nome text, p_senha_hash text)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; uid int; esq text;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_slug IN ('plataforma','plat','public','admin','api','static','svc','ogc','tiles','saude','entrar','conta') THEN
    RAISE EXCEPTION 'slug_reservado';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config) VALUES (p_slug, p_nome, coalesce(p_config, '{}'::jsonb)) RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, trocar_senha)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin', true) RETURNING id INTO uid;
  esq := plat.camada_schema_prefixo() || p_slug;
  PERFORM pg_advisory_xact_lock(hashtext('camada_schema_garantir:' || esq));
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', esq);  -- item L0-04
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', esq);
  RETURN QUERY SELECT tid, uid;
END $$;
