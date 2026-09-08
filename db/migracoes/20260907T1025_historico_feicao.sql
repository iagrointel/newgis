-- 20260907T1025_historico_feicao: item L2-03-edicao (portão: "histórico consultável e restauração funciona",
-- conceito C5/C12 do L2 — "histórico por gatilho em toda camada, vale para SQL direto, réplica, lote,
-- importação", não só para quem passa pela API). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- plat.feicao_historico: uma linha por INSERT/UPDATE/DELETE em qualquer d_<slug>.c_<uuid16>, escrita por
-- gatilho AFTER (nunca perde a operação mesmo se a transação decidir outra coisa depois — a própria semântica
-- de "quem, quando, o quê" pede o fato consumado, e o portão pede histórico de TODA escrita, inclusive a que
-- não passa pela API de edição). Guardamos schema/tabela (não o item_id do catálogo) porque o gatilho genérico
-- não tem como resolver o catálogo por linha sem uma subconsulta cara — a rota de leitura já conhece
-- schema/tabela do item (mesmo padrão de app/edicao/servico.py::_schema_tabela) e filtra por eles.
--
-- Geometria: capturada via to_jsonb(OLD/NEW)->>'geom', que é a saída de texto do TIPO geometry (EWKB hex) —
-- funciona para QUALQUER tabela de camada, com ou sem coluna geom, sem precisar checar information_schema por
-- linha. Reconvertida para GeoJSON só na hora de gravar (ST_AsGeoJSON), nunca guardada como GeoJSON cru (evita
-- decidir aqui uma precisão/CRS de exibição que não é da conta do gatilho).
CREATE TABLE IF NOT EXISTS plat.feicao_historico (
  id               bigserial PRIMARY KEY,
  tenant_id        int NOT NULL,
  schema_dado      text NOT NULL,
  tabela_dado      text NOT NULL,
  fid              bigint,
  globalid         uuid NOT NULL,
  operacao         text NOT NULL CHECK (operacao IN ('inserir', 'atualizar', 'apagar', 'restaurar')),
  versao           int,
  atributos_antes  jsonb,
  atributos_depois jsonb,
  geom_antes       text,   -- GeoJSON (texto), NULL quando a camada não tem geometria ou a operação não a toca
  geom_depois      text,
  usuario_id       int,
  momento          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_feicao_historico_busca
  ON plat.feicao_historico (tenant_id, schema_dado, tabela_dado, globalid, momento DESC);

ALTER TABLE plat.feicao_historico ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.feicao_historico FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_feicao_historico ON plat.feicao_historico;
CREATE POLICY p_feicao_historico ON plat.feicao_historico FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT ON plat.feicao_historico TO plat_app;
GRANT USAGE ON SEQUENCE plat.feicao_historico_id_seq TO plat_app;

-- ---------------------------------------------------------------- gatilho genérico (aplicado a toda c_* por
-- plat.camada_preparar, abaixo, e retroativamente a toda camada já publicada)
CREATE OR REPLACE FUNCTION plat.feicao_historico_registrar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  antes jsonb; depois jsonb; ga text; gd text;
BEGIN
  -- to_jsonb(record) converte a coluna geometry pelo CAST explícito geometry->json que o PostGIS registra
  -- (GeoJSON com bloco "crs"; removido aqui para bater com o formato puro que o resto da API usa via
  -- ST_AsGeoJSON). Funciona para QUALQUER tabela de camada, com ou sem coluna geom.
  IF TG_OP = 'DELETE' THEN
    antes := to_jsonb(OLD);
    IF antes ? 'geom' AND antes -> 'geom' IS NOT NULL THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, geom_antes,
       usuario_id)
    VALUES (OLD.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.fid, OLD.globalid, 'apagar', OLD.versao,
            antes - 'geom', ga, plat.usuario_atual());
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    antes := to_jsonb(OLD); depois := to_jsonb(NEW);
    IF antes ? 'geom' AND antes -> 'geom' IS NOT NULL THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    IF depois ? 'geom' AND depois -> 'geom' IS NOT NULL THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, atributos_depois,
       geom_antes, geom_depois, usuario_id)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'atualizar', NEW.versao,
            antes - 'geom', depois - 'geom', ga, gd, plat.usuario_atual());
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    depois := to_jsonb(NEW);
    IF depois ? 'geom' AND depois -> 'geom' IS NOT NULL THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_depois, geom_depois,
       usuario_id)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'inserir', NEW.versao,
            depois - 'geom', gd, plat.usuario_atual());
    RETURN NEW;
  END IF;
  RETURN NULL;
END $$;

-- plat.camada_preparar ganha o gatilho de histórico (CREATE OR REPLACE da função inteira: mesma assinatura e
-- corpo da 029_ingestao_vetor.sql, só com as duas linhas novas do tg_historico ao final).
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

-- retroativo: liga tg_historico em toda camada já publicada (mesmo padrão da 20260906T1955)
DO $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT i.dados->>'schema' AS esquema, i.dados->>'tabela' AS tabela
           FROM plat.item i
           WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
             AND coalesce(i.dados->>'fonte', 'hospedada') = 'hospedada'
             AND i.dados->>'schema' ~ '^d_[a-z0-9_]{1,60}$' AND i.dados->>'tabela' ~ '^c_[0-9a-f]{16}$' LOOP
    CONTINUE WHEN to_regclass(format('%I.%I', r.esquema, r.tabela)) IS NULL;
    EXECUTE format('DROP TRIGGER IF EXISTS tg_historico ON %I.%I', r.esquema, r.tabela);
    EXECUTE format('CREATE TRIGGER tg_historico AFTER INSERT OR UPDATE OR DELETE ON %I.%I '
                   'FOR EACH ROW EXECUTE FUNCTION plat.feicao_historico_registrar()', r.esquema, r.tabela);
    n := n + 1;
  END LOOP;
  RAISE NOTICE 'gatilho de histórico ligado em % camada(s) do catálogo', n;
END $$;

-- evento de domínio da restauração (uma linha por chamada de restaurar; L2-03-edicao)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/restaurar', 'feição restaurada a partir de uma entrada do histórico (L2-03-edicao)')
ON CONFLICT (nome) DO NOTHING;
