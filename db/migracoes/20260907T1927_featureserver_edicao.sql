-- 20260907T1927_featureserver_edicao: item L2-04-d (escrita Esri-compatível: applyEdits, anexos, uploads).
-- depende: 20260907T1025_historico_feicao.sql
-- depende: 20260907T1035_feicao_anexo.sql
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Três coisas, todas pequenas, nenhuma tabela de feição nova:
--   1. `origem` no histórico de feição: o portão do item pede que a edição que entra pelo FeatureServer seja
--      distinguível da que entra pelo navegador. A origem é declarada pela aplicação como parâmetro de sessão
--      (`plat.origem`, LOCAL à transação, mesmo mecanismo de `plat.tenant_id`/`plat.usuario_id` do ADR 0001),
--      e o gatilho a copia. Assim vale para QUALQUER escrita, inclusive a que não passa pela API — o padrão
--      é 'api', nunca NULL, para que a leitura não tenha de tratar ausência.
--   2. `numero` em `plat.feicao_anexo`: o protocolo Esri identifica anexo por INTEIRO (`attachmentInfos[].id`,
--      `/attachments/{id}`, `deleteAttachments?attachmentIds=1,2`). O identificador da casa é uuid e continua
--      sendo a chave; `numero` é só o rosto Esri, estável por linha.
--   3. `plat.esri_upload`: `/uploads/upload` do protocolo Esri guarda o arquivo ANTES de existir feição-pai
--      (o cliente manda o anexo grande primeiro e depois cita o `uploadId` no applyEdits). O bloco vive no
--      Garage por `app/objetos.py::guardar`, como todo o resto; esta tabela só guarda o bilhete.
ALTER TABLE plat.feicao_historico ADD COLUMN IF NOT EXISTS origem text NOT NULL DEFAULT 'api';

CREATE OR REPLACE FUNCTION plat.origem_atual() RETURNS text LANGUAGE sql STABLE AS
  $$ SELECT coalesce(NULLIF(current_setting('plat.origem', true), ''), 'api') $$;

-- mesmo corpo de 20260907T1025_historico_feicao.sql, com `origem` acrescentada nas três operações
CREATE OR REPLACE FUNCTION plat.feicao_historico_registrar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  antes jsonb; depois jsonb; ga text; gd text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    antes := to_jsonb(OLD);
    IF antes ? 'geom' AND antes -> 'geom' IS NOT NULL THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, geom_antes,
       usuario_id, origem)
    VALUES (OLD.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.fid, OLD.globalid, 'apagar', OLD.versao,
            antes - 'geom', ga, plat.usuario_atual(), plat.origem_atual());
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    antes := to_jsonb(OLD); depois := to_jsonb(NEW);
    IF antes ? 'geom' AND antes -> 'geom' IS NOT NULL THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    IF depois ? 'geom' AND depois -> 'geom' IS NOT NULL THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, atributos_depois,
       geom_antes, geom_depois, usuario_id, origem)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'atualizar', NEW.versao,
            antes - 'geom', depois - 'geom', ga, gd, plat.usuario_atual(), plat.origem_atual());
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    depois := to_jsonb(NEW);
    IF depois ? 'geom' AND depois -> 'geom' IS NOT NULL THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_depois, geom_depois,
       usuario_id, origem)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'inserir', NEW.versao,
            depois - 'geom', gd, plat.usuario_atual(), plat.origem_atual());
    RETURN NEW;
  END IF;
  RETURN NULL;
END $$;

ALTER TABLE plat.feicao_anexo ADD COLUMN IF NOT EXISTS numero bigserial;
CREATE UNIQUE INDEX IF NOT EXISTS ux_feicao_anexo_numero ON plat.feicao_anexo (numero);
GRANT USAGE, SELECT ON SEQUENCE plat.feicao_anexo_numero_seq TO plat_app;

CREATE TABLE IF NOT EXISTS plat.esri_upload (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL,
  nome         text NOT NULL,
  content_type text NOT NULL,
  bytes        bigint NOT NULL,
  sha256       text NOT NULL,
  chave        text NOT NULL,
  criado_por   int,
  criado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_esri_upload_tenant ON plat.esri_upload (tenant_id, criado_em DESC);
ALTER TABLE plat.esri_upload ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.esri_upload FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_esri_upload ON plat.esri_upload;
CREATE POLICY p_esri_upload ON plat.esri_upload FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.esri_upload TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/upload_esri', 'arquivo recebido em /uploads/upload do FeatureServer (L2-04-d)')
ON CONFLICT (nome) DO NOTHING;
