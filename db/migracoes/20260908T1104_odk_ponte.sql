-- 20260908T1104_odk_ponte: ponte opcional com o ODK Central (item L2-07-e-odk-central-ponte).
--
-- Duas tabelas, ambas do INQUILINO (tenant_id + RLS), sobre o modelo de conexão externa de 030/036:
--   plat.odk_ponte  liga um formulário de coleta (plat.item tipo 'formulario', item L2-07-b) a um formulário
--                   publicado num projeto do ODK Central alcançado por uma plat.conexao do tipo 'odk_central'.
--   plat.odk_envio  memória de idempotência: um envio do Central (instanceID, que o OData devolve em `__id`)
--                   vira NO MÁXIMO uma feição. Job repetido reencontra a linha e não grava de novo.
--
-- A credencial continua só em plat.conexao (AES-GCM, app/conexao/credencial.py): esta migração não guarda
-- segredo nenhum. O tipo novo de conexão entra no CHECK de 030 (a lista tem de continuar igual à de
-- app/limites.py CONEXAO_TIPOS — as duas mudam juntas).
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- depende: 20260907T2010_formulario_coleta.sql

ALTER TABLE plat.conexao DROP CONSTRAINT IF EXISTS conexao_tipo_check;
ALTER TABLE plat.conexao ADD CONSTRAINT conexao_tipo_check CHECK (tipo IN (
  'wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles',
  'postgres_fdw', 's3', 'http', 'odk_central'
));

CREATE TABLE IF NOT EXISTS plat.odk_ponte (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  conexao_id     uuid NOT NULL REFERENCES plat.conexao(id) ON DELETE CASCADE,
  formulario_id  uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  projeto        int NOT NULL CHECK (projeto > 0),
  xml_form_id    text NOT NULL CHECK (btrim(xml_form_id) <> '' AND length(xml_form_id) <= 255),
  versao         text,
  hash_central   text,           -- `hash` que o Central devolve ao publicar (md5 do XForm, do lado dele)
  publicado_em   timestamptz,
  sincronizado_em timestamptz,   -- fim da última sincronização que terminou sem erro
  dono_id        int NOT NULL REFERENCES plat.usuario(id),
  criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_odk_ponte_tenant ON plat.odk_ponte (tenant_id);
-- um formulário nosso publicado uma vez por conexão; e um xmlFormId do Central usado por uma ponte só
CREATE UNIQUE INDEX IF NOT EXISTS ux_odk_ponte_formulario ON plat.odk_ponte (conexao_id, formulario_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_odk_ponte_central ON plat.odk_ponte (conexao_id, projeto, lower(xml_form_id));

CREATE TABLE IF NOT EXISTS plat.odk_envio (
  ponte_id     uuid NOT NULL REFERENCES plat.odk_ponte(id) ON DELETE CASCADE,
  instance_id  text NOT NULL CHECK (btrim(instance_id) <> '' AND length(instance_id) <= 255),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  feicao_id    uuid,             -- globalid da feição gravada; NULL só quando o envio foi recusado
  anexos       int NOT NULL DEFAULT 0,
  motivo       text,             -- por que foi recusado (nunca some em silêncio; NULL = aplicado)
  recebido_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ponte_id, instance_id)
);
CREATE INDEX IF NOT EXISTS ix_odk_envio_tenant ON plat.odk_envio (tenant_id);

ALTER TABLE plat.odk_ponte ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.odk_envio ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_odk_ponte_ler ON plat.odk_ponte;
CREATE POLICY p_odk_ponte_ler ON plat.odk_ponte FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_odk_ponte_inserir ON plat.odk_ponte;
CREATE POLICY p_odk_ponte_inserir ON plat.odk_ponte FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND dono_id = plat.usuario_atual() AND plat.usuario_do_inquilino());

DROP POLICY IF EXISTS p_odk_ponte_alterar ON plat.odk_ponte;
CREATE POLICY p_odk_ponte_alterar ON plat.odk_ponte FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')))
  WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_odk_ponte_apagar ON plat.odk_ponte;
CREATE POLICY p_odk_ponte_apagar ON plat.odk_ponte FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')));

DROP POLICY IF EXISTS p_odk_envio_ler ON plat.odk_envio;
CREATE POLICY p_odk_envio_ler ON plat.odk_envio FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_odk_envio_inserir ON plat.odk_envio;
CREATE POLICY p_odk_envio_inserir ON plat.odk_envio FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_odk_envio_alterar ON plat.odk_envio;
CREATE POLICY p_odk_envio_alterar ON plat.odk_envio FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_odk_envio_apagar ON plat.odk_envio;
CREATE POLICY p_odk_envio_apagar ON plat.odk_envio FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual());

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.odk_ponte TO plat_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.odk_envio TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('odk/publicar', 'formulário de coleta publicado num projeto do ODK Central (projeto, xmlFormId, versão)'),
  ('odk/sincronizar', 'envios do ODK Central puxados por OData (lidos, aplicados, repetidos, recusados)')
ON CONFLICT (nome) DO NOTHING;
