-- 20260906T1540_migracao_inventario_portal: inventário só-leitura de um Portal/AGOL de terceiro
-- (item L2-08-a-leitor-portal-inventario, linha L2-08 migração AGOL). Guarda o RESULTADO da leitura do
-- portal do cliente para que a migração propriamente dita (L2-08-b clonar camadas, L2-08-c web map,
-- L2-08-d relatório e exportação reversa) trabalhe sobre um retrato gravado, e não sobre chamadas ao vivo.
--
-- Dado do INQUILINO (tenant_id + RLS), igual a `plat.conexao` (030): o portal inventariado é o do cliente
-- daquele inquilino. A credencial NÃO mora aqui — mora em `plat.conexao.credencial_cifrada` (AES-GCM,
-- app/conexao/credencial.py); este inventário só aponta para a conexão (`conexao_id`).
--
-- LGPD (regra da casa "nunca publicar dado pessoal identificado"): `plat.migracao_usuario` NÃO TEM coluna de
-- e-mail, nome completo, telefone nem qualquer outro campo pessoal — só o NOME DE LOGIN, que é o
-- identificador que a migração precisa para remapear dono de item e membro de grupo. A ausência é
-- estrutural (não existe onde gravar), não uma regra de aplicação que alguém possa esquecer de aplicar;
-- é assim que a refutação do item ("adversário confere que nenhum e-mail de usuário foi gravado") fica
-- provada pelo esquema e não pela boa vontade do código.
--
-- Nome com carimbo de tempo UTC (ADR 0014), nunca número sequencial. Idempotente. Sem BEGIN/COMMIT.

-- ---------------------------------------------------------------- execução do inventário
CREATE TABLE IF NOT EXISTS plat.migracao_inventario (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  conexao_id        uuid NOT NULL REFERENCES plat.conexao(id) ON DELETE CASCADE,
  job_id            uuid,
  estado            text NOT NULL DEFAULT 'pendente'
                      CHECK (estado IN ('pendente', 'rodando', 'concluido', 'falhou', 'cancelado')),
  portal_url        text NOT NULL CHECK (btrim(portal_url) <> '' AND length(portal_url) <= 2048),
  portal_nome       text,
  portal_id         text,
  portal_versao     text,
  -- ponto de retomada: {"fase": "...", "start": N, "itens_lidos": N}. O job grava a cada página/item, e a
  -- tentativa seguinte continua daqui em vez de recomeçar (portão "job retoma após falha de rede no meio").
  retomada          jsonb NOT NULL DEFAULT '{}'::jsonb,
  totais            jsonb NOT NULL DEFAULT '{}'::jsonb,
  mensagem          text,
  criado_por        int NOT NULL REFERENCES plat.usuario(id),
  iniciado_em       timestamptz,
  terminado_em      timestamptz,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  atualizado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_migracao_inventario_tenant ON plat.migracao_inventario (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_migracao_inventario_conexao ON plat.migracao_inventario (conexao_id);

CREATE OR REPLACE FUNCTION plat.tg_migracao_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS migracao_inventario_atualizado_em ON plat.migracao_inventario;
CREATE TRIGGER migracao_inventario_atualizado_em BEFORE UPDATE ON plat.migracao_inventario
  FOR EACH ROW EXECUTE FUNCTION plat.tg_migracao_atualizado_em();

-- ---------------------------------------------------------------- item do portal
CREATE TABLE IF NOT EXISTS plat.migracao_item (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inventario_id      uuid NOT NULL REFERENCES plat.migracao_inventario(id) ON DELETE CASCADE,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  item_esri_id       text NOT NULL CHECK (btrim(item_esri_id) <> '' AND length(item_esri_id) <= 100),
  tipo               text NOT NULL,
  titulo             text,
  dono_login         text,                  -- login do dono, nunca e-mail (LGPD; ver cabeçalho)
  url                text,
  tamanho_bytes      bigint,
  criado_esri_em     timestamptz,
  modificado_esri_em timestamptz,
  ultimo_acesso_em   timestamptz,
  num_visualizacoes  bigint,
  -- classificação prévia do item (tabela de app/migracao/classificacao.py, base do relatório do L2-08-d)
  classificacao      text NOT NULL DEFAULT 'desconhecido'
                       CHECK (classificacao IN ('migra', 'migra_parcial', 'nao_migra', 'desconhecido')),
  classificacao_motivo text,
  contagem_total     bigint,                -- soma das feições das camadas do serviço (NULL = não medida)
  camadas            jsonb NOT NULL DEFAULT '[]'::jsonb,       -- [{id, nome, tipo, contagem}]
  dependencias       jsonb NOT NULL DEFAULT '[]'::jsonb,       -- [{tipo, alvo}] web map -> camada, app -> web map
  recursos           jsonb NOT NULL DEFAULT '[]'::jsonb,       -- nomes de item/resources
  relacionados       jsonb NOT NULL DEFAULT '[]'::jsonb,       -- ids de relatedItems por tipo de relação
  lido_em            timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_migracao_item ON plat.migracao_item (inventario_id, item_esri_id);
CREATE INDEX IF NOT EXISTS ix_migracao_item_tenant ON plat.migracao_item (tenant_id);
CREATE INDEX IF NOT EXISTS ix_migracao_item_tipo ON plat.migracao_item (inventario_id, tipo);

-- ---------------------------------------------------------------- grupo do portal
CREATE TABLE IF NOT EXISTS plat.migracao_grupo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inventario_id  uuid NOT NULL REFERENCES plat.migracao_inventario(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  grupo_esri_id  text NOT NULL,
  titulo         text,
  acesso         text,
  dono_login     text,
  membros        jsonb NOT NULL DEFAULT '[]'::jsonb,   -- só logins (LGPD)
  num_membros    int NOT NULL DEFAULT 0,
  lido_em        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_migracao_grupo ON plat.migracao_grupo (inventario_id, grupo_esri_id);
CREATE INDEX IF NOT EXISTS ix_migracao_grupo_tenant ON plat.migracao_grupo (tenant_id);

-- ---------------------------------------------------------------- usuário do portal (SEM e-mail, por esquema)
CREATE TABLE IF NOT EXISTS plat.migracao_usuario (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inventario_id  uuid NOT NULL REFERENCES plat.migracao_inventario(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  login          text NOT NULL CHECK (btrim(login) <> '' AND length(login) <= 200),
  papel          text,        -- role do portal: org_admin | org_publisher | org_user | ...
  nivel          text,        -- userLicenseTypeId/level, quando o portal declara
  desativado     boolean,
  lido_em        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_migracao_usuario ON plat.migracao_usuario (inventario_id, lower(login));
CREATE INDEX IF NOT EXISTS ix_migracao_usuario_tenant ON plat.migracao_usuario (tenant_id);

-- ---------------------------------------------------------------- RLS (mesmo padrão de plat.conexao, 030)
ALTER TABLE plat.migracao_inventario ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.migracao_item       ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.migracao_grupo      ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.migracao_usuario    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_migracao_inventario_ler ON plat.migracao_inventario;
CREATE POLICY p_migracao_inventario_ler ON plat.migracao_inventario FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_migracao_inventario_inserir ON plat.migracao_inventario;
CREATE POLICY p_migracao_inventario_inserir ON plat.migracao_inventario FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino());
DROP POLICY IF EXISTS p_migracao_inventario_alterar ON plat.migracao_inventario;
CREATE POLICY p_migracao_inventario_alterar ON plat.migracao_inventario FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_migracao_inventario_apagar ON plat.migracao_inventario;
CREATE POLICY p_migracao_inventario_apagar ON plat.migracao_inventario FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual()
         AND (criado_por = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['migracao_item', 'migracao_grupo', 'migracao_usuario'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_ler ON plat.%1$s', t);
    EXECUTE format('CREATE POLICY p_%1$s_ler ON plat.%1$s FOR SELECT TO plat_app '
                   'USING (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_escrever ON plat.%1$s', t);
    EXECUTE format('CREATE POLICY p_%1$s_escrever ON plat.%1$s FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_alterar ON plat.%1$s', t);
    EXECUTE format('CREATE POLICY p_%1$s_alterar ON plat.%1$s FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_apagar ON plat.%1$s', t);
    EXECUTE format('CREATE POLICY p_%1$s_apagar ON plat.%1$s FOR DELETE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual())', t);
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.migracao_inventario, plat.migracao_item,
  plat.migracao_grupo, plat.migracao_usuario TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('migracao/inventariar', 'inventário de Portal/AGOL enfileirado (conexão, portal)'),
  ('migracao/inventario_apagar', 'inventário de Portal/AGOL apagado')
ON CONFLICT (nome) DO NOTHING;
