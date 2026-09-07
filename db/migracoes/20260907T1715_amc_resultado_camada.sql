-- Item L3-13-resultado-como-camada: cada execução do motor AMC concluída pode publicar o resultado como
-- ITEM DO CATÁLOGO — uma camada vetorial (unidades + favorabilidade + fatores + veto), e, quando o conjunto
-- de unidades é uma grade, também um raster COG da favorabilidade com um item STAC (multihash). As duas
-- tabelas abaixo são o REGISTRO de que a publicação aconteceu (idempotência: 1 camada e 1 raster por
-- execução) e a FICHA DE PROVENIÊNCIA da publicação em si (schema/tabela ou chave do objeto, sha256,
-- versões). O conteúdo da camada nasce em `plat.item`/`d_<slug>.<tabela>` pela MESMA função de criação do
-- L5-31 (`app.catalogo.camada_esquema.criar_camada_de_campos`, que chama `plat.camada_schema_garantir` e
-- `plat.camada_preparar` — nenhum DDL novo é escrito aqui).

CREATE TABLE IF NOT EXISTS plat.amc_resultado_camada (
  execucao_id    uuid PRIMARY KEY REFERENCES plat.amc_execucao(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  item_id        uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  schema_nome    text NOT NULL,
  tabela_nome    text NOT NULL,
  n_feicoes      int NOT NULL CHECK (n_feicoes >= 0),
  sha256         text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  campos         jsonb NOT NULL,                 -- [{nome, tipo, alias, fator_id?}] publicados na tabela
  criado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_amc_resultado_camada_tenant ON plat.amc_resultado_camada (tenant_id, criado_em DESC);

CREATE TABLE IF NOT EXISTS plat.amc_resultado_raster (
  execucao_id    uuid PRIMARY KEY REFERENCES plat.amc_execucao(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  item_id        uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  chave_objeto   text NOT NULL,                  -- chave do COG no Garage (app.objetos)
  sha256         text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  multihash      text NOT NULL,                  -- '1220' + sha256 hex (sha2-256, 32 bytes)
  largura_px     int NOT NULL CHECK (largura_px > 0),
  altura_px      int NOT NULL CHECK (altura_px > 0),
  pixel_x_deg    double precision NOT NULL CHECK (pixel_x_deg > 0),
  pixel_y_deg    double precision NOT NULL CHECK (pixel_y_deg > 0),
  bbox           double precision[4] NOT NULL,   -- [minx, miny, maxx, maxy] em 4326
  bandas         jsonb NOT NULL DEFAULT '[{"nome": "favorabilidade"}]'::jsonb,
  criado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_amc_resultado_raster_tenant ON plat.amc_resultado_raster (tenant_id, criado_em DESC);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['amc_resultado_camada', 'amc_resultado_raster'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR ALL TO plat_app USING (tenant_id = plat.tenant_atual()) '
                   'WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
  END LOOP;
END $$;

-- Imutável como o resto do motor AMC (mesmo princípio de plat.amc_materializado_guarda: resultado publicado
-- não se edita — reexecutar o modelo é como se corrige, não um UPDATE na publicação).
CREATE OR REPLACE FUNCTION plat.amc_resultado_publicado_guarda() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN COALESCE(NEW, OLD); END IF;
  RAISE EXCEPTION 'amc_resultado_camada_imutavel'
    USING HINT = 'publicação de resultado não se edita nem se apaga direto; apague a execução (cascata)';
END $$;

DROP TRIGGER IF EXISTS amc_resultado_camada_guarda ON plat.amc_resultado_camada;
CREATE TRIGGER amc_resultado_camada_guarda BEFORE UPDATE OR DELETE ON plat.amc_resultado_camada
  FOR EACH ROW EXECUTE FUNCTION plat.amc_resultado_publicado_guarda();

DROP TRIGGER IF EXISTS amc_resultado_raster_guarda ON plat.amc_resultado_raster;
CREATE TRIGGER amc_resultado_raster_guarda BEFORE UPDATE OR DELETE ON plat.amc_resultado_raster
  FOR EACH ROW EXECUTE FUNCTION plat.amc_resultado_publicado_guarda();
