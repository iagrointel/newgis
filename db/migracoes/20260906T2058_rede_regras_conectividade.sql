-- 20260906T2058_rede_regras_conectividade: regras de conectividade avaliáveis + feições da rede
-- (item L4-03-a-regras-de-conectividade; ADR docs/adr/20260906T2058-regras-de-conectividade.md).
--
-- Três movimentos:
-- 1) plat.rede_regra ganha o vocabulário novo de tipo (juncao_juncao, juncao_aresta, aresta_juncao_aresta,
--    contencao, estrutura), os TERMINAIS de cada lado e o lado VIA (a junção do meio na regra
--    aresta-junção-aresta). Linhas do vocabulário antigo (migração 20260906T1553) são traduzidas:
--    conectividade_no_trecho -> juncao_aresta, conectividade_entre_nos -> juncao_juncao,
--    fixacao_estrutural -> estrutura, contencao -> contencao. A unicidade passa a enxergar via+terminais.
-- 2) plat.rede ganha regras_ativas (padrão true = 'sem regra = proibido'; desligar é ato de ADMIN da rede,
--    conferido na aplicação — é a comporta de carga em massa, documentada no ADR).
-- 3) Nascem as tabelas de FEIÇÃO (rede_feicao), de CONEXÃO derivada da geometria (rede_conexao) e de
--    ASSOCIAÇÃO explícita (rede_associacao) — o chão onde as regras são avaliadas no applyEdits e na
--    validação em lote. Conexão é sempre DERIVADA de coincidência geométrica (junção-junção ou
--    junção-ponta de aresta, tolerância em metros); associação (contenção/estrutura) é sempre explícita.
--
-- FKs compostas (tenant_id, id) no padrão da migração 20260906T1815; CASCADE em tudo, coerente com o
-- resto do catálogo: apagar a rede (ou reimportar o pacote, que substitui o catálogo) leva as feições e
-- as conexões junto — a feição pertence à revisão do catálogo (limitação registrada no ADR).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- 1. plat.rede_regra ---------------------------------------------------------------------------------

ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_tipo_check;
UPDATE plat.rede_regra SET tipo = CASE tipo
  WHEN 'conectividade_no_trecho' THEN 'juncao_aresta'
  WHEN 'conectividade_entre_nos' THEN 'juncao_juncao'
  WHEN 'fixacao_estrutural' THEN 'estrutura'
  ELSE tipo END;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tipo_check
  CHECK (tipo IN ('juncao_juncao', 'juncao_aresta', 'aresta_juncao_aresta', 'contencao', 'estrutura'));

ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS de_terminal text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS para_terminal text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS via_tipo_id uuid;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS via_terminal text;
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_terminais_check;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_terminais_check CHECK (
  (de_terminal IS NULL OR (btrim(de_terminal) <> '' AND length(de_terminal) <= 62)) AND
  (para_terminal IS NULL OR (btrim(para_terminal) <> '' AND length(para_terminal) <= 62)) AND
  (via_terminal IS NULL OR (btrim(via_terminal) <> '' AND length(via_terminal) <= 62)));

ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_tenant_via_tipo_fkey;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_via_tipo_fkey
  FOREIGN KEY (tenant_id, via_tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- porta para as FKs compostas de rede_conexao/rede_associacao -> rede_regra (a migração 20260906T1815 deu
-- UNIQUE (tenant_id, id) a todas as tabelas do catálogo MENOS a esta, que não era alvo de FK composta)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_regra' AND c.conname = 'rede_regra_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_id_id_key UNIQUE (tenant_id, id);
  END IF;
END $$;

-- forma por tipo: só a aresta-junção-aresta tem lado VIA, e ele é obrigatório nela
ALTER TABLE plat.rede_regra DROP CONSTRAINT IF EXISTS rede_regra_forma_check;
ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_forma_check CHECK (
  (tipo = 'aresta_juncao_aresta' AND via_tipo_id IS NOT NULL)
  OR (tipo <> 'aresta_juncao_aresta' AND via_tipo_id IS NULL AND via_terminal IS NULL));

DROP INDEX IF EXISTS plat.ux_rede_regra;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_regra ON plat.rede_regra
  (rede_id, tipo, de_tipo_id, para_tipo_id,
   coalesce(via_tipo_id, '00000000-0000-0000-0000-000000000000'::uuid),
   coalesce(de_terminal, ''), coalesce(para_terminal, ''), coalesce(via_terminal, ''));

-- 2. comporta de avaliação na rede --------------------------------------------------------------------

ALTER TABLE plat.rede ADD COLUMN IF NOT EXISTS regras_ativas boolean NOT NULL DEFAULT true;

-- 3. feição, conexão e associação ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plat.rede_feicao (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  rede_id         uuid NOT NULL,
  grupo_id        uuid NOT NULL,
  tipo_id         uuid NOT NULL,
  geometria       geometry(Geometry, 4326),
  atributos       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  terminal_inicio text CHECK (terminal_inicio IS NULL OR (btrim(terminal_inicio) <> '' AND length(terminal_inicio) <= 62)),
  terminal_fim    text CHECK (terminal_fim IS NULL OR (btrim(terminal_fim) <> '' AND length(terminal_fim) <= 62)),
  criado_por      int REFERENCES plat.usuario(id),
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_feicao' AND c.conname = 'rede_feicao_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.rede_feicao ADD CONSTRAINT rede_feicao_tenant_id_id_key UNIQUE (tenant_id, id);
  END IF;
END $$;
ALTER TABLE plat.rede_feicao DROP CONSTRAINT IF EXISTS rede_feicao_tenant_rede_fkey;
ALTER TABLE plat.rede_feicao ADD CONSTRAINT rede_feicao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_feicao DROP CONSTRAINT IF EXISTS rede_feicao_tenant_grupo_fkey;
ALTER TABLE plat.rede_feicao ADD CONSTRAINT rede_feicao_tenant_grupo_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.rede_grupo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_feicao DROP CONSTRAINT IF EXISTS rede_feicao_tenant_tipo_fkey;
ALTER TABLE plat.rede_feicao ADD CONSTRAINT rede_feicao_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_rede_feicao_rede ON plat.rede_feicao (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_tenant ON plat.rede_feicao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_geo ON plat.rede_feicao USING gist (geometria);

DROP TRIGGER IF EXISTS rede_feicao_atualizado_em ON plat.rede_feicao;
CREATE TRIGGER rede_feicao_atualizado_em BEFORE UPDATE ON plat.rede_feicao
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_atualizado_em();

-- conexão DERIVADA da geometria pelo applyEdits: jj = junção-junção coincidentes; je = junção na ponta da
-- aresta (de = a junção, para = a aresta, de_terminal = o terminal da junção naquela ponta). regra_id é a
-- regra que permitiu a conexão; NULL quando gravada com a avaliação desligada (comporta do admin).
CREATE TABLE IF NOT EXISTS plat.rede_conexao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  tipo           text NOT NULL CHECK (tipo IN ('jj', 'je')),
  de_feicao_id   uuid NOT NULL,
  para_feicao_id uuid NOT NULL,
  de_terminal    text CHECK (de_terminal IS NULL OR (btrim(de_terminal) <> '' AND length(de_terminal) <= 62)),
  regra_id       uuid,
  criado_em      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_tenant_rede_fkey;
ALTER TABLE plat.rede_conexao ADD CONSTRAINT rede_conexao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_tenant_de_fkey;
ALTER TABLE plat.rede_conexao ADD CONSTRAINT rede_conexao_tenant_de_fkey
  FOREIGN KEY (tenant_id, de_feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_tenant_para_fkey;
ALTER TABLE plat.rede_conexao ADD CONSTRAINT rede_conexao_tenant_para_fkey
  FOREIGN KEY (tenant_id, para_feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_conexao DROP CONSTRAINT IF EXISTS rede_conexao_tenant_regra_fkey;
ALTER TABLE plat.rede_conexao ADD CONSTRAINT rede_conexao_tenant_regra_fkey
  FOREIGN KEY (tenant_id, regra_id) REFERENCES plat.rede_regra (tenant_id, id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_conexao ON plat.rede_conexao
  (rede_id, tipo, de_feicao_id, para_feicao_id, coalesce(de_terminal, ''));
CREATE INDEX IF NOT EXISTS ix_rede_conexao_tenant ON plat.rede_conexao (tenant_id);

-- associação EXPLÍCITA (contenção e estrutura): de = recipiente/estrutura, para = conteúdo/anexado
CREATE TABLE IF NOT EXISTS plat.rede_associacao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  tipo           text NOT NULL CHECK (tipo IN ('contencao', 'estrutura')),
  de_feicao_id   uuid NOT NULL,
  para_feicao_id uuid NOT NULL,
  regra_id       uuid,
  criado_em      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tenant_rede_fkey;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tenant_de_fkey;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_de_fkey
  FOREIGN KEY (tenant_id, de_feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tenant_para_fkey;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_para_fkey
  FOREIGN KEY (tenant_id, para_feicao_id) REFERENCES plat.rede_feicao (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tenant_regra_fkey;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_regra_fkey
  FOREIGN KEY (tenant_id, regra_id) REFERENCES plat.rede_regra (tenant_id, id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_associacao ON plat.rede_associacao
  (rede_id, tipo, de_feicao_id, para_feicao_id);
CREATE INDEX IF NOT EXISTS ix_rede_associacao_tenant ON plat.rede_associacao (tenant_id);

-- RLS + GRANT: o mesmo padrão do catálogo (migração 20260906T1553)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_feicao', 'rede_conexao', 'rede_associacao'] LOOP
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
  ('redes/apply_edits', 'lote de edições de feições da rede (adicionar/atualizar/apagar, associações)'),
  ('redes/validar_regras', 'validação em lote das regras de conectividade (erros por feição)'),
  ('redes/importar_regras_csv', 'conjunto de regras substituído por CSV no formato de colunas da Esri'),
  ('redes/regras_ativacao', 'avaliação de regras ligada/desligada por admin da rede')
ON CONFLICT (nome) DO NOTHING;
