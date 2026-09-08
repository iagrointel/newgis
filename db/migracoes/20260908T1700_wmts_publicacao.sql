-- Item L2-04-i-wms-wmts-sld: publicação de uma camada como WMTS pré-renderizado.
-- Uma linha por camada publicada: onde está o arquivo PMTiles raster no bucket do inquilino, que faixa
-- de zoom ele cobre e quanto custou gerar. O tile servido sai deste arquivo por leitura de FAIXA
-- (Range no S3/Garage), sem tocar no banco de feições -- é o que faz z0-z14 de uma camada grande caber
-- num pedido de 20 ms. Sem linha aqui, o WMTS continua desenhando ao vivo.
CREATE TABLE IF NOT EXISTS plat.wmts_publicacao (
  item_id      uuid PRIMARY KEY,
  tenant_id    int  NOT NULL,
  chave        text NOT NULL,                      -- chave do objeto PMTiles (app/objetos.py)
  estilo       text NOT NULL DEFAULT 'padrao',
  z_min        int  NOT NULL,
  z_max        int  NOT NULL,
  tiles        bigint NOT NULL DEFAULT 0,
  bytes        bigint NOT NULL DEFAULT 0,
  feicoes      bigint,
  duracao_ms   bigint,
  gerado_em    timestamptz NOT NULL DEFAULT now(),
  gerado_por   int,
  job_id       uuid,
  CONSTRAINT ck_wmts_zoom CHECK (z_min >= 0 AND z_max >= z_min AND z_max <= 22)
);
CREATE INDEX IF NOT EXISTS ix_wmts_publicacao_tenant ON plat.wmts_publicacao (tenant_id, gerado_em DESC);
ALTER TABLE plat.wmts_publicacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.wmts_publicacao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_wmts_publicacao ON plat.wmts_publicacao;
CREATE POLICY p_wmts_publicacao ON plat.wmts_publicacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.wmts_publicacao TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/wmts_publicar', 'camada publicada como WMTS pré-renderizado (PMTiles raster no bucket, item L2-04-i)')
ON CONFLICT (nome) DO NOTHING;
