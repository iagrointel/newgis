-- Item L4-02-e-configuracoes-de-tracado: a configuração de traçado nomeada e compartilhável.
-- depende: 20260907T2031_rede_controlador_de_subrede.sql
--
-- Uma CONFIGURAÇÃO DE TRAÇADO é um documento salvo que preenche o pedido de POST /api/rede/{id}/tracar:
-- o tipo do traçado, as barreiras de condição e de filtro, o filtro de saída, as funções sobre atributo e
-- o tipo de resultado. Não é um segundo motor de traçado — o motor continua sendo `tracado.py`/`direcao.py`,
-- e a configuração só decide COM QUE PEDIDO ele é chamado e COMO o resultado é resumido.
--
-- `codigo` é o nome curto pelo qual a tela e a API a citam (único dentro da rede). `origem='pacote'` marca as
-- configurações que vêm prontas com o pacote de ativos (elétrica-BR); `origem='usuario'`, as que alguém criou.
-- `compartilhada` diz se a configuração vale para todo o inquilino ou só para quem a criou — o compartilhamento
-- NUNCA atravessa inquilino: a política de RLS abaixo é por `tenant_id`, como em toda tabela de rede.

CREATE TABLE IF NOT EXISTS plat.rede_config_tracado (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  codigo        text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  descricao     text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  tipo          text NOT NULL CHECK (tipo IN ('conectado','subrede','montante','jusante')),
  config        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(config) = 'object'),
  origem        text NOT NULL DEFAULT 'usuario' CHECK (origem IN ('pacote','usuario')),
  compartilhada boolean NOT NULL DEFAULT true,
  dono_id       int REFERENCES plat.usuario(id),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_config_tracado ON plat.rede_config_tracado (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_config_tracado_tenant ON plat.rede_config_tracado (tenant_id);
ALTER TABLE plat.rede_config_tracado DROP CONSTRAINT IF EXISTS rede_config_tracado_tenant_rede_fkey;
ALTER TABLE plat.rede_config_tracado ADD CONSTRAINT rede_config_tracado_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260907T2031.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_config_tracado'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/config_tracado_criar', 'configuração de traçado criada (código, tipo)'),
  ('redes/config_tracado_alterar', 'configuração de traçado alterada (código, tipo)'),
  ('redes/config_tracado_apagar', 'configuração de traçado apagada (código)')
ON CONFLICT (nome) DO NOTHING;
