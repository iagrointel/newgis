-- 20260910T2015_agol: item L2-08-migracao-agol — publicação de camada vetorial hospedada como hosted feature
-- layer na conta ArcGIS Online do INQUILINO. A credencial cifrada NÃO tem tabela própria: vive em
-- `tenant.config->'agol'` (coluna jsonb já existente desde 003), mesmo lugar e mesmo padrão de
-- `tenant.config->'smtp'` (item L0-07-d) — `app/agol/cifra.py`/`config.py` cifram/decifram, nunca esta
-- migração. O que É novo aqui é o estado de publicação POR ITEM (`plat.agol_publicacao`), mesmo desenho de
-- `plat.raster_item` (031/20260906T1901): tabela-espelho com RLS por inquilino, upsert em ON CONFLICT — o
-- `dados` de um item `camada_vetorial` tem esquema fechado (additionalProperties:false, 029/036) e não
-- cabe o estado de uma integração aqui sem migrar aquele contrato para toda camada vetorial existente.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.agol_publicacao (
  id                    bigserial PRIMARY KEY,
  tenant_id             int NOT NULL REFERENCES plat.tenant(id),
  item_id               uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  job_id                uuid,
  estado                text NOT NULL DEFAULT 'pendente'
                          CHECK (estado IN ('pendente', 'publicando', 'publicado', 'erro')),
  portal                text,
  agol_geojson_item_id  text,
  agol_servico_item_id  text,
  servico_url           text,
  n_feicoes             int,
  mensagem              text,
  publicado_em          timestamptz,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, item_id)
);
CREATE INDEX IF NOT EXISTS ix_agol_publicacao_tenant ON plat.agol_publicacao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_agol_publicacao_job ON plat.agol_publicacao (job_id);

ALTER TABLE plat.agol_publicacao ENABLE ROW LEVEL SECURITY;

-- FOR ALL (não só SELECT, como `p_conexao_saude_historico_ler`): ao contrário do histórico de saúde de
-- conexão, que só uma função SECURITY DEFINER grava, aqui é a própria rota/job do inquilino (sob RLS normal,
-- contexto do próprio tenant) que faz o upsert — não há verificação de terceiro inquilino a proteger.
DROP POLICY IF EXISTS p_agol_publicacao ON plat.agol_publicacao;
CREATE POLICY p_agol_publicacao ON plat.agol_publicacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

REVOKE ALL ON plat.agol_publicacao FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON plat.agol_publicacao TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.agol_publicacao_id_seq TO plat_app;

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/agol_configurar', 'credencial ArcGIS Online do inquilino configurada ou atualizada (nunca a credencial em si)'),
  ('org/agol_remover', 'credencial ArcGIS Online do inquilino removida'),
  ('org/agol_testar', 'teste da credencial ArcGIS Online do inquilino (ok/erro, nunca a credencial)'),
  ('agol/publicar_iniciar', 'publicação de camada vetorial no ArcGIS Online do inquilino enfileirada')
ON CONFLICT (nome) DO NOTHING;
