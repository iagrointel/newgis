-- 20260907T1243_rede_areas_sujas_e_erros: área suja por edição + validação incremental + feições de erro
-- (item L4-03-d-areas-sujas-e-validacao; ADR docs/adr/20260907T1243-areas-sujas-e-validacao.md).
--
-- Constrói sobre `plat.rede_feicao`/`rede_conexao`/`rede_associacao`/`rede_regra` do item
-- L4-03-a-regras-de-conectividade (migração 20260906T2058). Três movimentos:
--
-- 1) plat.rede ganha `versao_edicao` (contador monotônico, uma unidade por applyEdits bem-sucedido — a
--    "versão" que cada área suja carrega) e `tracado_sobre_area_suja_modo` (comporta de configuração:
--    'avisar' devolve 200 com aviso, 'bloquear' devolve 409; padrão 'avisar').
-- 2) plat.rede_area_suja: um polígono envolvente por FEIÇÃO editada (não por lote — "editar 1 trecho cria
--    1 área suja"), com a versão da edição. `limpa_em` é preenchido quando a validação processa a área
--    (soft-delete: mantém histórico, `limpa_em IS NULL` é o filtro de "visível no mapa").
-- 3) plat.rede_erro: erros de topologia como FEIÇÃO (código, mensagem, feição referida, geometria) —
--    "aparecem como camada" (GeoJSON, ver rotas_areas_sujas.py). `feicao_id` é ON DELETE CASCADE: erro
--    sobre feição apagada não faz sentido sozinho; erros de âmbito da rede (ex. tipo sem regra no pacote)
--    gravam `feicao_id NULL`.
--
-- FKs compostas (tenant_id, id), RLS/GRANT no padrão de 20260906T2058. Idempotente. Sem BEGIN/COMMIT.
-- Aplicada como postgres.

-- 1. comportas na rede -------------------------------------------------------------------------------

ALTER TABLE plat.rede ADD COLUMN IF NOT EXISTS versao_edicao bigint NOT NULL DEFAULT 0;
ALTER TABLE plat.rede ADD COLUMN IF NOT EXISTS tracado_sobre_area_suja_modo text NOT NULL DEFAULT 'avisar';
ALTER TABLE plat.rede DROP CONSTRAINT IF EXISTS rede_tracado_area_suja_modo_check;
ALTER TABLE plat.rede ADD CONSTRAINT rede_tracado_area_suja_modo_check
  CHECK (tracado_sobre_area_suja_modo IN ('avisar', 'bloquear'));

-- 2. área suja -----------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plat.rede_area_suja (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  rede_id      uuid NOT NULL,
  feicao_id    uuid,
  versao       bigint NOT NULL,
  geometria    geometry(Polygon, 4326) NOT NULL,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  limpa_em     timestamptz
);
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_area_suja' AND c.conname = 'rede_area_suja_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.rede_area_suja ADD CONSTRAINT rede_area_suja_tenant_id_id_key UNIQUE (tenant_id, id);
  END IF;
END $$;
ALTER TABLE plat.rede_area_suja DROP CONSTRAINT IF EXISTS rede_area_suja_tenant_rede_fkey;
ALTER TABLE plat.rede_area_suja ADD CONSTRAINT rede_area_suja_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_area_suja DROP CONSTRAINT IF EXISTS rede_area_suja_tenant_feicao_fkey;
ALTER TABLE plat.rede_area_suja ADD CONSTRAINT rede_area_suja_tenant_feicao_fkey
  FOREIGN KEY (tenant_id, feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_rede_area_suja_rede ON plat.rede_area_suja (rede_id) WHERE limpa_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_rede_area_suja_tenant ON plat.rede_area_suja (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_area_suja_geo ON plat.rede_area_suja USING gist (geometria);

-- 3. feição de erro ------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plat.rede_erro (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  codigo         text NOT NULL,
  mensagem       text NOT NULL,
  feicao_id      uuid,
  tipo_referencia text NOT NULL DEFAULT 'feicao' CHECK (tipo_referencia IN ('feicao', 'conexao', 'associacao', 'rede')),
  detalhe        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detalhe) = 'object'),
  geometria      geometry(Geometry, 4326),
  versao         bigint NOT NULL,
  gerado_em      timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_erro' AND c.conname = 'rede_erro_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.rede_erro ADD CONSTRAINT rede_erro_tenant_id_id_key UNIQUE (tenant_id, id);
  END IF;
END $$;
ALTER TABLE plat.rede_erro DROP CONSTRAINT IF EXISTS rede_erro_tenant_rede_fkey;
ALTER TABLE plat.rede_erro ADD CONSTRAINT rede_erro_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_erro DROP CONSTRAINT IF EXISTS rede_erro_tenant_feicao_fkey;
ALTER TABLE plat.rede_erro ADD CONSTRAINT rede_erro_tenant_feicao_fkey
  FOREIGN KEY (tenant_id, feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_rede_erro_rede ON plat.rede_erro (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_erro_tenant ON plat.rede_erro (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_erro_codigo ON plat.rede_erro (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_erro_geo ON plat.rede_erro USING gist (geometria);

-- RLS + GRANT: mesmo padrão do catálogo (migração 20260906T2058)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_area_suja', 'rede_erro'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/validar_extensao', 'validação incremental (por extensão ou tudo) restrita às áreas sujas ativas'),
  ('redes/tracar', 'traçado a partir de uma feição, com aviso/recusa se cruzar área suja'),
  ('redes/area_sujas_modo', 'troca avisar/bloquear do traçado sobre área suja (rede.administrar)')
ON CONFLICT (nome) DO NOTHING;
