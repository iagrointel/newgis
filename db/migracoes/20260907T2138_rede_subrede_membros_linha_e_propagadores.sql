-- Item L4-04-b-atualizar-e-exportar-subrede: o que a ATUALIZAÇÃO da subrede grava.
-- depende: 20260907T2031_rede_controlador_de_subrede.sql
--
-- Três coisas que faltavam ao item irmão L4-04-a (que criou controlador, tier e o registro da subrede):
--
--  1. ONDE FICA O NOME DA SUBREDE EM CADA ELEMENTO. No ArcGIS Utility Network `Update Subnetwork` escreve o
--     nome da subrede no campo `subnetworkname` da PRÓPRIA feição. Aqui o nome vai para uma tabela derivada
--     (`plat.rede_subrede_elemento`), nunca para `plat.rede_feicao_*.atributos`: aquele jsonb é o dado COMO
--     VEIO DO ARQUIVO (BDGD Módulo 10), e misturar dado derivado com dado de origem apaga a diferença entre
--     "o arquivo diz" e "a plataforma calculou" — que é justamente o que a cláusula de conferência do portão
--     precisa comparar (nome calculado x CTMT do arquivo). A tabela é o atributo de rede; a origem fica limpa.
--
--  2. A LINHA AGREGADA DA SUBREDE (`SubnetLine` da Esri): uma feição de linha por subrede, refeita a cada
--     atualização, para desenhar e medir a subrede sem varrer os elementos. Como é 1 para 1 com a subrede,
--     são duas colunas em `plat.rede_subrede`, não uma tabela nova.
--
--  3. OS PROPAGADORES. No modelo da Esri o propagador é configurado no TIER (atributo de rede propagado do
--     controlador para baixo). Aqui é a lista de códigos de atributo em `plat.rede_tier.propagadores`; o
--     valor propagado de cada elemento fica em `plat.rede_subrede_elemento.propagados`.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.rede_tier ADD COLUMN IF NOT EXISTS propagadores jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE plat.rede_tier DROP CONSTRAINT IF EXISTS rede_tier_propagadores_lista;
ALTER TABLE plat.rede_tier ADD CONSTRAINT rede_tier_propagadores_lista
  CHECK (jsonb_typeof(propagadores) = 'array' AND jsonb_array_length(propagadores) <= 20);

ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS linha geometry(MultiLineString, 4326);
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS comprimento_m double precision;

CREATE TABLE IF NOT EXISTS plat.rede_subrede_elemento (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  subrede_id    uuid NOT NULL,
  tier_id       uuid NOT NULL,
  subrede_nome  text NOT NULL CHECK (btrim(subrede_nome) <> '' AND length(subrede_nome) <= 200),
  feicao_id     uuid NOT NULL,
  terminal_num  int CHECK (terminal_num IS NULL OR terminal_num BETWEEN 1 AND 8),
  geometria     text NOT NULL CHECK (geometria IN ('ponto', 'linha')),
  tipo_id       uuid,
  propagados    jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(propagados) = 'object'),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_subrede_elemento
  ON plat.rede_subrede_elemento (subrede_id, feicao_id, coalesce(terminal_num, 0));
CREATE INDEX IF NOT EXISTS ix_rede_subrede_elemento_rede
  ON plat.rede_subrede_elemento (rede_id, feicao_id);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_elemento_tenant ON plat.rede_subrede_elemento (tenant_id);
ALTER TABLE plat.rede_subrede_elemento DROP CONSTRAINT IF EXISTS rede_subrede_elemento_tenant_rede_fkey;
ALTER TABLE plat.rede_subrede_elemento ADD CONSTRAINT rede_subrede_elemento_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_subrede_elemento DROP CONSTRAINT IF EXISTS rede_subrede_elemento_tenant_subrede_fkey;
ALTER TABLE plat.rede_subrede_elemento ADD CONSTRAINT rede_subrede_elemento_tenant_subrede_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_subrede_elemento DROP CONSTRAINT IF EXISTS rede_subrede_elemento_tenant_tier_fkey;
ALTER TABLE plat.rede_subrede_elemento ADD CONSTRAINT rede_subrede_elemento_tenant_tier_fkey
  FOREIGN KEY (tenant_id, tier_id) REFERENCES plat.rede_tier (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260907T2031.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_subrede_elemento'] LOOP
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
  ('redes/subredes_atualizar', 'atualização em lote das subredes sujas da rede (job)'),
  ('redes/tier_propagadores', 'propagadores do tier redefinidos (atributos propagados do controlador)')
ON CONFLICT (nome) DO NOTHING;
