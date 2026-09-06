-- 029_ingestao_vetor: núcleo da ingestão vetorial (item L0-04-ingest-vetor; ADR 0005), reduzido a 4 formatos
-- (shapefile.zip, gpkg, geojson, csv) nesta passagem. Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- plat.importacao (upload -> inspeção -> proposta -> confirmação -> carga -> camada_vetorial no catálogo);
-- role plat_leitor (leitor só-SELECT das tabelas de camada, para Martin/tiles do L2, ainda sem LOGIN);
-- plat.tenant ganha uso_bytes/uso_reservado_bytes (cota de armazenamento de tabela, independente da cota do
-- bucket Garage que L0-11/ADR 0006 já controla); plat.camada_schema_garantir/plat.camada_preparar (SECURITY
-- DEFINER: só elas criam schema/alteram tabela de camada fora do privilégio comum de plat_app);
-- plat.feicao_inserir/plat.feicao_versao (gatilhos genéricos de toda tabela d_<slug>.c_<uuid16>);
-- tenant_criar (versão da 003, com sessão) passa a criar o schema d_<slug> do inquilino novo; os 3 inquilinos
-- já existentes (demo, demo2, plataforma) recebem o schema agora; tipo_item camada_vetorial ganha esquema v2
-- (estatisticas/importacao); evento_tipo ganha camadas/importar e importacoes/*.

-- ---------------------------------------------------------------- plat_leitor (role só-leitura, sem LOGIN ainda)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_leitor') THEN
    CREATE ROLE plat_leitor NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA plat TO plat_leitor;

-- ---------------------------------------------------------------- plat.tenant: cota de armazenamento de tabela
ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS uso_bytes bigint NOT NULL DEFAULT 0;
ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS uso_reservado_bytes bigint NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------- plat.importacao
CREATE TABLE IF NOT EXISTS plat.importacao (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  usuario_id    int REFERENCES plat.usuario(id),
  arquivo_id    uuid NOT NULL REFERENCES plat.item(id),
  item_id       uuid NOT NULL,                                     -- pré-alocado; vira plat.item.id na carga
  formato       text NOT NULL,
  estado        text NOT NULL DEFAULT 'inspecionando'
                CHECK (estado IN ('inspecionando','proposta','confirmada','carregando','concluida','falhou',
                                  'cancelada','expirada')),
  proposta      jsonb,
  confirmacao   jsonb,
  relatorio     jsonb,
  job_inspecao  uuid,
  job_carga     uuid,
  erro          text,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  expira_em     timestamptz
);
CREATE INDEX IF NOT EXISTS ix_importacao_tenant  ON plat.importacao (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_importacao_arquivo ON plat.importacao (arquivo_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_importacao_item ON plat.importacao (item_id);

ALTER TABLE plat.importacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_importacao ON plat.importacao;
CREATE POLICY p_importacao ON plat.importacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- estado final é imutável (mesmo padrão de plat.job_estado_final_imutavel, ADR 0003 seção 4/ 004_jobs.sql)
CREATE OR REPLACE FUNCTION plat.importacao_estado_final_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('concluida','falhou','cancelada','expirada') AND NEW.estado IS DISTINCT FROM OLD.estado THEN
    RAISE EXCEPTION 'importacao_em_estado_final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS importacao_estado_final_imutavel ON plat.importacao;
CREATE TRIGGER importacao_estado_final_imutavel BEFORE UPDATE ON plat.importacao
  FOR EACH ROW EXECUTE FUNCTION plat.importacao_estado_final_imutavel();

-- ---------------------------------------------------------------- gatilhos genéricos das tabelas de camada
-- (aplicados pelo plat.camada_preparar a cada d_<slug>.c_<uuid16>; ADR 0005 seção 7.1)
CREATE OR REPLACE FUNCTION plat.feicao_inserir() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS NULL THEN
    NEW.tenant_id := plat.tenant_atual();
  END IF;
  IF NEW.tenant_id IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  NEW.criado_por := coalesce(NEW.criado_por, plat.usuario_atual());
  NEW.atualizado_por := coalesce(NEW.atualizado_por, plat.usuario_atual());
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION plat.feicao_versao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.versao := OLD.versao + 1;
  NEW.atualizado_em := now();
  NEW.atualizado_por := plat.usuario_atual();
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------- schema por inquilino (SECURITY DEFINER: só
-- ela cria schema — plat_app não tem CREATE no banco, de propósito, ver ADR 0001)
CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
END $$;

-- ---------------------------------------------------------------- plat.camada_preparar (DDL pós-ogr2ogr; seção 7.1)
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
  nome_curto := substr(p_tabela, 3);  -- os 16 hex, sem o prefixo c_ (nome de índice/política/trigger não colide)

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

-- ---------------------------------------------------------------- backfill: schema d_<slug> dos inquilinos já
-- existentes (novos inquilinos ganham o schema no próprio tenant_criar, alterado abaixo)
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT slug FROM plat.tenant LOOP
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || r.slug);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || r.slug);
  END LOOP;
END $$;

-- tenant_criar (assinatura da 003, com p_sessao_hash): mesma função, com a criação do schema acrescentada
CREATE OR REPLACE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb,
  p_admin_login text, p_admin_nome text, p_senha_hash text)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; uid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_slug IN ('plataforma','plat','public','admin','api','static','svc','ogc','tiles','saude','entrar','conta') THEN
    RAISE EXCEPTION 'slug_reservado';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config) VALUES (p_slug, p_nome, coalesce(p_config, '{}'::jsonb)) RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, trocar_senha)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin', true) RETURNING id INTO uid;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);  -- item L0-04
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
  RETURN QUERY SELECT tid, uid;
END $$;

-- ---------------------------------------------------------------- tipo_item camada_vetorial: esquema v2
-- (acrescenta estatisticas/importacao; procedencia já era additionalProperties:true desde a 011)
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('camada_vetorial', 'camada', 'Camada vetorial', 'camada vetorial hospedada ou referenciada (tabela PostGIS)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["schema","tabela","geometria","srid","campos","fonte"],
     "properties":{
       "schema":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "tabela":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "geometria":{"type":"string","enum":["Point","MultiPoint","LineString","MultiLineString","Polygon","MultiPolygon","Geometry","nenhuma"]},
       "srid":{"type":"integer","minimum":1,"maximum":999999},
       "campos":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":false,"required":["nome","tipo"],
                 "properties":{"nome":{"type":"string","maxLength":63},"tipo":{"type":"string","maxLength":64},"alias":{"type":"string","maxLength":200}}}},
       "fonte":{"type":"string","enum":["hospedada","referenciada"]},
       "edicao":{"type":"object","additionalProperties":false,"properties":{"habilitada":{"type":"boolean"}}},
       "procedencia":{"type":"object","additionalProperties":true},
       "estatisticas":{"type":"object","additionalProperties":true},
       "importacao":{"type":"object","additionalProperties":true}}}'::jsonb,
   2, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/importar', 'camada vetorial publicada por ingestão (L0-04)'),
  ('importacoes/criar', 'nova importação (inspeção) criada a partir de um arquivo'),
  ('importacoes/confirmar', 'proposta de importação confirmada pelo usuário')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- privilégios de tabela/função novas (mesmo
-- padrão do 001_fundacao: ALTER DEFAULT PRIVILEGES já cobre tabela/função criada por postgres em schema plat)
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) TO plat_app;
