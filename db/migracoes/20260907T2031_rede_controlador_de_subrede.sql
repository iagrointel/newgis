-- Item L4-04-a-controladores-e-tiers: controlador de subrede e a tabela de subredes.
-- depende: 20260906T2000_rede_topologia_derivada.sql
--
-- Um CONTROLADOR de subrede é o terminal de um dispositivo (feição de ponto) que dá nome e origem a uma
-- subrede dentro de um tier: o disjuntor de saída da subestação controla o alimentador (tier de média
-- tensão), o lado de baixa do transformador controla a subrede de baixa tensão. O tier já existe desde
-- 20260906T1553 (`plat.rede_tier`, com `ordem` e `tipo` hierarquico/particionado).
--
-- Por que o controlador NÃO aponta para `plat.rede_topo_no`: `topologia.habilitar()` APAGA e refaz o índice
-- derivado inteiro a cada construção, e uma chave estrangeira para o nó levaria todo controlador junto na
-- primeira reconstrução. A âncora durável é a FEIÇÃO (`plat.rede_feicao_ponto`) mais o número do terminal —
-- exatamente o par que a topologia usa para recriar o nó (`rede_topo_no.origem_id`/`terminal_num`). Quando a
-- importação não tem dispositivo nenhum para ancorar (alimentador cujo arquivo não traz o equipamento de
-- saída), a âncora é a COORDENADA do nó de cabeça, gravada aqui; o nó corrente é resolvido na leitura.

CREATE TABLE IF NOT EXISTS plat.rede_subrede (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  tier_id       uuid NOT NULL,
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  estado        text NOT NULL DEFAULT 'suja' CHECK (estado IN ('limpa','suja')),
  resumo        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(resumo) = 'object'),
  atualizado_em timestamptz,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_subrede ON plat.rede_subrede (rede_id, tier_id, nome);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_tenant ON plat.rede_subrede (tenant_id);
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_tenant_rede_fkey;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_tenant_tier_fkey;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_tenant_tier_fkey
  FOREIGN KEY (tenant_id, tier_id) REFERENCES plat.rede_tier (tenant_id, id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS plat.rede_controlador (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  subrede_id    uuid NOT NULL,
  tier_id       uuid NOT NULL,
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  origem        text NOT NULL CHECK (origem IN ('dispositivo','no_de_cabeca')),
  feicao_id     uuid,
  terminal_num  int CHECK (terminal_num IS NULL OR terminal_num BETWEEN 1 AND 8),
  tipo_id       uuid,
  papel         text NOT NULL CHECK (papel IN ('fonte','sumidouro')),
  geom          geometry(Point, 4326) NOT NULL,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  criado_por    int REFERENCES plat.usuario(id),
  UNIQUE (tenant_id, id),
  CONSTRAINT rede_controlador_ancora CHECK (
    (origem = 'dispositivo' AND feicao_id IS NOT NULL) OR
    (origem = 'no_de_cabeca' AND feicao_id IS NULL AND terminal_num IS NULL))
);
-- "A unique name for the controller in the tier must be provided" (subnetwork-controller.htm): o nome do
-- CONTROLADOR é único dentro do tier; o nome da SUBREDE é outro campo, e uma subrede pode ter vários
-- controladores. Os dois nomes coincidem no caso comum de um controlador só.
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_controlador_nome
  ON plat.rede_controlador (rede_id, tier_id, nome);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_controlador_feicao
  ON plat.rede_controlador (rede_id, feicao_id, coalesce(terminal_num, 0))
  WHERE feicao_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_controlador_cabeca
  ON plat.rede_controlador (rede_id, geom) WHERE feicao_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_rede_controlador_tenant ON plat.rede_controlador (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_controlador_subrede ON plat.rede_controlador (subrede_id);
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_tenant_rede_fkey;
ALTER TABLE plat.rede_controlador ADD CONSTRAINT rede_controlador_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_tenant_subrede_fkey;
ALTER TABLE plat.rede_controlador ADD CONSTRAINT rede_controlador_tenant_subrede_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_tenant_feicao_fkey;
ALTER TABLE plat.rede_controlador ADD CONSTRAINT rede_controlador_tenant_feicao_fkey
  FOREIGN KEY (tenant_id, feicao_id) REFERENCES plat.rede_feicao_ponto (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_tenant_tier_fkey;
ALTER TABLE plat.rede_controlador ADD CONSTRAINT rede_controlador_tenant_tier_fkey
  FOREIGN KEY (tenant_id, tier_id) REFERENCES plat.rede_tier (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_controlador DROP CONSTRAINT IF EXISTS rede_controlador_tenant_tipo_fkey;
ALTER TABLE plat.rede_controlador ADD CONSTRAINT rede_controlador_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260906T1553 e 20260906T2000.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_subrede','rede_controlador'] LOOP
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
  ('redes/controlador_definir', 'controlador de subrede definido (subrede, tier, feição, terminal)'),
  ('redes/controlador_remover', 'controlador de subrede removido (subrede, tier)'),
  ('redes/controlador_importar', 'controladores marcados a partir da importação (contagem por tier)'),
  ('redes/subrede_atualizar', 'subrede atualizada: traçado refeito a partir dos controladores')
ON CONFLICT (nome) DO NOTHING;
