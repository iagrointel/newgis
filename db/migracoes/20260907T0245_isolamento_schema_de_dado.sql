-- Isolamento do schema de dado por instalação (achado F8 do adversário de 07/09/2026,
-- laco/handoffs/T4/ADVERSARIO-reescritor-schema.md).
--
-- Defeito: o dado de camada mora em `d_<slug>`, derivado só do APELIDO do inquilino. O nome não contém
-- a palavra `plat`, então o tradutor de schema (app/schema_ambiente.py) nunca o alcança: produção,
-- homologação e as dezenas de trilhas gravam no MESMO `d_demo`. Medido em 07/09/2026: 79 tabelas em
-- `d_demo`, 65 delas de sete trilhas diferentes e 14 do produto.
--
-- Conserto: o prefixo do schema de dado passa a incluir a INSTALAÇÃO. Em produção o prefixo continua
-- `d_` (nenhum schema é renomeado, nenhuma camada existente muda de lugar); em qualquer ambiente
-- derivado (homologação, trilha) vira `d_<schema do ambiente>_`, ex. `d_plat_homolog_demo`.
--
-- Nada é renomeado nem apagado aqui de propósito: a limpeza das tabelas de trilha que já estão em
-- `d_demo`/`d_demo2` é decisão do dono (a lista está no laudo do item).

-- ---------------------------------------------------------------- prefixo por instalação
-- `'p' || 'lat'` NÃO é reescrito pelo tradutor (a regex casa a PALAVRA inteira `plat`), enquanto o
-- literal `'plat'` do lado esquerdo é. Em produção os dois lados são iguais e o prefixo fica `d_`;
-- numa instalação derivada o lado esquerdo virou o nome do schema do ambiente e o prefixo o carrega.
CREATE OR REPLACE FUNCTION plat.camada_schema_prefixo() RETURNS text
LANGUAGE sql IMMUTABLE AS $f$
  SELECT CASE WHEN 'plat' = 'p' || 'lat' THEN 'd_' ELSE 'd_' || 'plat' || '_' END
$f$;
REVOKE EXECUTE ON FUNCTION plat.camada_schema_prefixo() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_schema_prefixo() TO plat_app, plat_leitor, plat_worker;

-- ---------------------------------------------------------------- schema por inquilino (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE esq text;
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  esq := plat.camada_schema_prefixo() || p_slug;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', esq);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', esq);
END $$;
REVOKE EXECUTE ON FUNCTION plat.camada_schema_garantir(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;

-- ---------------------------------------------------------------- camada_preparar: mesma função da 029,
-- com a checagem de dono do schema pelo prefixo da instalação (o resto do corpo é idêntico).
CREATE OR REPLACE FUNCTION plat.camada_preparar(p_schema text, p_tabela text, p_srid int, p_tipo text, p_usuario int)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,80}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
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

-- ---------------------------------------------------------------- tenant_criar (assinatura da 029)
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
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', esq);  -- item L0-04
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', esq);
  RETURN QUERY SELECT tid, uid;
END $$;

-- ---------------------------------------------------------------- backfill: schema prefixado dos inquilinos
-- já existentes (em produção o prefixo é `d_` e o CREATE IF NOT EXISTS não faz nada).
DO $$
DECLARE r record; esq text;
BEGIN
  FOR r IN SELECT slug FROM plat.tenant LOOP
    esq := plat.camada_schema_prefixo() || r.slug;
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', esq);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', esq);
  END LOOP;
END $$;
