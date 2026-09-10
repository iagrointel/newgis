-- 20260908T1659_amc_preset: presets do motor multicritério (item L3-01-h-presets, linha L3).
--
-- Hipótese do item: preset = conjunto nomeado de pesos e vetos de um modelo, salvo por usuário
-- (escopo 'usuario', visível só ao dono) ou compartilhado no inquilino (escopo 'inquilino'), com
-- autor, data e descrição. O preset é autocontido: carrega a ordem declarada dos fatores do modelo
-- (a tabela de modelo do item L3-01-a está REFUTADA e não existe no master), por isso o preset é o
-- próprio contexto de validação na importação e na aplicação.
--
-- Decisões (ADR 20260908T1659-presets-amc):
--  * os presets INTEGRADOS ('pesos iguais' e os quatro exemplos do motor logístico da casa:
--    galpão, última milha, indústria e custo mínimo) NÃO são linhas desta tabela: vivem em código
--    (app/amc/presets.py), valem para todo inquilino, são somente leitura e nunca recebem nome de
--    cliente — dado aberto. Esta tabela guarda só o que o usuário criou (CRUD por API e tela).
--  * veto é fração constante [0,1] por fator (a fração vetada da nota de cada unidade quando o
--    fator está no modelo), o mesmo contrato de fracao_vetada de app/amc/combinacao.py; unidade
--    sem dado continua sem nota (o veto marca, não inventa número).
--  * unicidade por (inquilino, escopo, nome em caixa baixa): presets de usuário e de inquilino
--    podem ter o mesmo nome; dentro do mesmo escopo, não.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres. Padrão de RLS copiado de
-- 20260906T1640_multiescala.sql.

CREATE TABLE IF NOT EXISTS plat.amc_preset (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  descricao     text NOT NULL DEFAULT '' CHECK (length(descricao) <= 2000),
  escopo        text NOT NULL DEFAULT 'usuario' CHECK (escopo IN ('usuario', 'inquilino')),
  conteudo      jsonb NOT NULL,
  dono_id       int NOT NULL REFERENCES plat.usuario(id),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_amc_preset_nome ON plat.amc_preset (tenant_id, escopo, lower(nome));
CREATE INDEX IF NOT EXISTS ix_amc_preset_dono ON plat.amc_preset (tenant_id, dono_id);

-- ------------------------------------------------------------------ RLS por inquilino
DO $$
BEGIN
  EXECUTE format('ALTER TABLE plat.amc_preset ENABLE ROW LEVEL SECURITY');
  EXECUTE format('DROP POLICY IF EXISTS p_amc_preset_ler ON plat.amc_preset');
  EXECUTE format('CREATE POLICY p_amc_preset_ler ON plat.amc_preset FOR SELECT TO plat_app '
                 'USING (tenant_id = plat.tenant_atual())');
  EXECUTE format('DROP POLICY IF EXISTS p_amc_preset_inserir ON plat.amc_preset');
  EXECUTE format('CREATE POLICY p_amc_preset_inserir ON plat.amc_preset FOR INSERT TO plat_app '
                 'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())');
  EXECUTE format('DROP POLICY IF EXISTS p_amc_preset_alterar ON plat.amc_preset');
  EXECUTE format('CREATE POLICY p_amc_preset_alterar ON plat.amc_preset FOR UPDATE TO plat_app '
                 'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())');
  EXECUTE format('DROP POLICY IF EXISTS p_amc_preset_apagar ON plat.amc_preset');
  EXECUTE format('CREATE POLICY p_amc_preset_apagar ON plat.amc_preset FOR DELETE TO plat_app '
                 'USING (tenant_id = plat.tenant_atual())');
  EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.amc_preset TO plat_app');
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('amc/preset', 'preset do motor multicritério criado (nome, escopo, fatores e pesos)'),
  ('amc/preset_atualizar', 'preset do motor multicritério editado (nome, escopo, conteúdo)'),
  ('amc/preset_apagar', 'preset do motor multicritério apagado (nome)'),
  ('amc/preset_importar', 'preset importado de JSON (nome, escopo, fatores)'),
  ('amc/preset_aplicar', 'preset aplicado sobre matriz de fatores: recálculo síncrono, sem job '
                         '(fatores, unidades, faltando)')
ON CONFLICT (nome) DO NOTHING;
