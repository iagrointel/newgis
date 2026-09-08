-- 20260907T1035_feicao_anexo: item L2-03-edicao (portão: "anexos com limite de tamanho e de tipo"). O bloco
-- vive no objeto (Garage) via app/objetos.py::guardar (bucket por inquilino, cota, dedup por sha256) — esta
-- tabela só liga o objeto guardado à feição (schema/tabela/globalid), porque plat.arquivo (029/046) não
-- conhece feição, só item do catálogo e classe/referência.
CREATE TABLE IF NOT EXISTS plat.feicao_anexo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL,
  schema_dado   text NOT NULL,
  tabela_dado   text NOT NULL,
  globalid      uuid NOT NULL,
  nome          text NOT NULL,
  content_type  text NOT NULL,
  bytes         bigint NOT NULL,
  sha256        text NOT NULL,
  chave         text NOT NULL,
  criado_por    int,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  apagado_em    timestamptz
);
CREATE INDEX IF NOT EXISTS ix_feicao_anexo_busca
  ON plat.feicao_anexo (tenant_id, schema_dado, tabela_dado, globalid) WHERE apagado_em IS NULL;

ALTER TABLE plat.feicao_anexo ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.feicao_anexo FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_feicao_anexo ON plat.feicao_anexo;
CREATE POLICY p_feicao_anexo ON plat.feicao_anexo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.feicao_anexo TO plat_app;

-- eventos de domínio de anexo de feição (L2-03-edicao)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/anexo_enviar', 'anexo enviado para uma feição (L2-03-edicao)'),
  ('camadas/anexo_apagar', 'anexo removido de uma feição (L2-03-edicao)')
ON CONFLICT (nome) DO NOTHING;
