-- 20260906T2122_intercambio: item L6-02-o-importacao-exportacao-formatos.
-- plat.intercambio_exportacao: registro de uma exportação de camada ou do inquilino inteiro (escrow
-- GeoPackage + manifesto JSON), com RLS no padrão de plat.importacao (029), estado final imutável e o
-- privilégio novo conteudo.exportar (espelho em app/auth/privilegios.py). Idempotente (IF NOT EXISTS /
-- ON CONFLICT).
--
-- Por que tabela própria e não reutilizar plat.importacao: importação é um FUNIL de 5 estados em cima de
-- um arquivo de origem; exportação é um registro de SAÍDA (formato, alvo, avisos de fidelidade, arquivo
-- gerado). Misturar os dois inflaria os dois jsonb e os dois conjuntos de estados.

CREATE TABLE IF NOT EXISTS plat.intercambio_exportacao (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int         NOT NULL REFERENCES plat.tenant(id),
  usuario_id    int,
  tipo          text        NOT NULL CHECK (tipo IN ('camada','inquilino')),
  formato       text        NOT NULL,
  item_origem   uuid        REFERENCES plat.item(id) ON DELETE SET NULL,  -- NULL no tipo 'inquilino' ou se a camada for apagada depois
  parametros    jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- srid alvo, campos escolhidos, título
  estado        text        NOT NULL DEFAULT 'fila' CHECK (estado IN ('fila','rodando','concluida','falhou','cancelada')),
  item_arquivo  uuid        REFERENCES plat.item(id) ON DELETE SET NULL,  -- item 'arquivo' com o pacote gerado
  avisos        jsonb       NOT NULL DEFAULT '[]'::jsonb,   -- perdas declaradas (truncamento DBF, tipo, quantização de tile...)
  relatorio     jsonb,                                        -- feicoes, bytes, sha256, segundos, camadas (no escrow)
  erro          text,
  job_id        uuid,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_intercambio_exp_tenant ON plat.intercambio_exportacao (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_intercambio_exp_item   ON plat.intercambio_exportacao (item_origem);

ALTER TABLE plat.intercambio_exportacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_intercambio_exportacao ON plat.intercambio_exportacao;
CREATE POLICY p_intercambio_exportacao ON plat.intercambio_exportacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

CREATE OR REPLACE FUNCTION plat.intercambio_exportacao_tenant() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS NULL THEN
    NEW.tenant_id := plat.tenant_atual();
  END IF;
  IF NEW.tenant_id IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS intercambio_exportacao_tenant ON plat.intercambio_exportacao;
CREATE TRIGGER intercambio_exportacao_tenant BEFORE INSERT ON plat.intercambio_exportacao
  FOR EACH ROW EXECUTE FUNCTION plat.intercambio_exportacao_tenant();

CREATE OR REPLACE FUNCTION plat.intercambio_exportacao_estado_final() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('concluida','falhou','cancelada') AND NEW.estado IS DISTINCT FROM OLD.estado THEN
    RAISE EXCEPTION 'exportacao_em_estado_final' USING ERRCODE = 'check_violation';
  END IF;
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS intercambio_exportacao_estado_final ON plat.intercambio_exportacao;
CREATE TRIGGER intercambio_exportacao_estado_final BEFORE UPDATE ON plat.intercambio_exportacao
  FOR EACH ROW EXECUTE FUNCTION plat.intercambio_exportacao_estado_final();

-- estado final imutável também vale para o job que atualiza: as funções de gatilho rodam como dono da
-- tabela (postgres), então basta revogar o EXECUTE do papel da aplicação, como na 033.
REVOKE EXECUTE ON FUNCTION plat.intercambio_exportacao_tenant() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.intercambio_exportacao_estado_final() FROM PUBLIC, plat_app;

-- ---------------------------------------------------------------- privilégio novo: conteudo.exportar
INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('conteudo.exportar', 'conteudo', 'exportar camada ou o inquilino inteiro para arquivo', false)
ON CONFLICT (nome) DO NOTHING;
INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES
  ('editor', 'conteudo.exportar'),
  ('admin', 'conteudo.exportar')
ON CONFLICT DO NOTHING;

-- evento_tipo (nome PK): mesmo padrão da 029 ('camadas/importar').
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('intercambio/exportar_camada', 'camada exportada para arquivo (L6-02-o)'),
  ('intercambio/exportar_inquilino', 'escrow do inquilino em GeoPackage + manifesto (L6-02-o)'),
  ('intercambio/baixar', 'arquivo de exportação baixado (L6-02-o)')
ON CONFLICT (nome) DO NOTHING;
