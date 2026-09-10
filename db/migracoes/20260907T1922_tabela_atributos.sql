-- Tabela de atributos por camada (item L2-01-g-tabela-atributos): a VISTA da tabela, por usuário e por camada.
--
-- O que NÃO entra aqui: a linha de dado. As feições continuam onde a ingestão as pôs (`d_<slug>.c_<16 hex>`,
-- migração 029), com a RLS por inquilino que `plat.camada_preparar()` já instala. Esta migração guarda só a
-- PREFERÊNCIA DE APRESENTAÇÃO: quais colunas aparecem, com que rótulo, em que ordem, com que largura, e qual
-- é o domínio (código -> descrição) de cada coluna. É o equivalente do "field visibility/alias/order" que o
-- Map Viewer guarda no item do mapa; aqui fica em tabela própria porque a preferência é DE QUEM OLHA, não do
-- item: dois usuários do mesmo inquilino veem a mesma camada com larguras diferentes sem disputar a mesma linha.
--
-- Por que `usuario_id` NOT NULL e não uma vista "da organização" com usuario_id NULL: `UNIQUE (item_id,
-- usuario_id)` não deduplica NULL no Postgres (dois NULL são distintos), então a vista de organização exigiria
-- índice parcial e um segundo caminho de leitura. O portão deste item pede coluna oculta e largura persistida
-- POR USUÁRIO; a vista de organização, se um dia for pedida, entra como item próprio.
--
-- Idempotente; sem BEGIN/COMMIT; aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.tabela_vista (
  id            bigserial PRIMARY KEY,
  tenant_id     int  NOT NULL REFERENCES plat.tenant(id),
  item_id       uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  usuario_id    int  NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  colunas       jsonb NOT NULL DEFAULT '[]'::jsonb,
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tabela_vista_item_usuario_u UNIQUE (item_id, usuario_id),
  CONSTRAINT ck_tabela_vista_colunas CHECK (jsonb_typeof(colunas) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_tabela_vista_tenant ON plat.tabela_vista (tenant_id);

CREATE OR REPLACE FUNCTION plat.tg_tabela_vista_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tabela_vista_atualizado_em ON plat.tabela_vista;
CREATE TRIGGER tabela_vista_atualizado_em BEFORE UPDATE ON plat.tabela_vista
  FOR EACH ROW EXECUTE FUNCTION plat.tg_tabela_vista_atualizado_em();

ALTER TABLE plat.tabela_vista ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_tabela_vista_ler ON plat.tabela_vista;
CREATE POLICY p_tabela_vista_ler ON plat.tabela_vista FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual());

DROP POLICY IF EXISTS p_tabela_vista_inserir ON plat.tabela_vista;
CREATE POLICY p_tabela_vista_inserir ON plat.tabela_vista FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual() AND plat.usuario_do_inquilino());

DROP POLICY IF EXISTS p_tabela_vista_alterar ON plat.tabela_vista;
CREATE POLICY p_tabela_vista_alterar ON plat.tabela_vista FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual())
  WITH CHECK (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual());

DROP POLICY IF EXISTS p_tabela_vista_apagar ON plat.tabela_vista;
CREATE POLICY p_tabela_vista_apagar ON plat.tabela_vista FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual());

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/vista_tabela', 'vista da tabela de atributos gravada (colunas visíveis, alias, largura, domínio)')
ON CONFLICT (nome) DO NOTHING;
