-- depende: 20260906T1540_migracao_inventario_portal.sql
-- Clonagem de camadas hospedadas e tabelas de um Portal/AGOL (item L2-08-b-clonar-camadas-hospedadas): um
-- registro por execução com retomada por camada, relatório por camada (contagem origem × destino, domínios,
-- relacionamentos, anexos, escritas, hash de amostra) e o lastEditDate lido para a re-execução incremental.
-- As camadas criadas são itens `camada_vetorial` comuns do catálogo (app/catalogo/camada_nova.py).
CREATE TABLE IF NOT EXISTS plat.migracao_clone (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  conexao_id      uuid NOT NULL REFERENCES plat.conexao(id) ON DELETE CASCADE,
  url_servico     text NOT NULL CHECK (length(url_servico) <= 2048),
  camadas_pedidas int[],                      -- NULL = todas as camadas e tabelas do serviço
  job_id          uuid,
  estado          text NOT NULL DEFAULT 'pendente'
                  CHECK (estado IN ('pendente','rodando','concluido','falhou','cancelado')),
  retomada        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {camada_origem: {fase, deslocamento, item_id, edit_date}}
  camadas         jsonb NOT NULL DEFAULT '[]'::jsonb,   -- relatório por camada
  relatorio       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- totais e avisos
  mensagem        text,
  criado_por      int NOT NULL REFERENCES plat.usuario(id),
  iniciado_em     timestamptz,
  terminado_em    timestamptz,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_migracao_clone_tenant ON plat.migracao_clone (tenant_id, criado_em DESC);

ALTER TABLE plat.migracao_clone ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_migracao_clone_ler ON plat.migracao_clone;
CREATE POLICY p_migracao_clone_ler ON plat.migracao_clone FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_migracao_clone_inserir ON plat.migracao_clone;
CREATE POLICY p_migracao_clone_inserir ON plat.migracao_clone FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino());
DROP POLICY IF EXISTS p_migracao_clone_alterar ON plat.migracao_clone;
CREATE POLICY p_migracao_clone_alterar ON plat.migracao_clone FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_migracao_clone_apagar ON plat.migracao_clone;
CREATE POLICY p_migracao_clone_apagar ON plat.migracao_clone FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual()
         AND (criado_por = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')));
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.migracao_clone TO plat_app;

DROP TRIGGER IF EXISTS migracao_clone_atualizado_em ON plat.migracao_clone;
CREATE TRIGGER migracao_clone_atualizado_em BEFORE UPDATE ON plat.migracao_clone
  FOR EACH ROW EXECUTE FUNCTION plat.tg_migracao_atualizado_em();

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('migracao/clonar', 'clonagem de camadas hospedadas pedida (L2-08-b)'),
  ('migracao/clone_apagar', 'registro de clonagem removido (L2-08-b)')
ON CONFLICT (nome) DO NOTHING;
