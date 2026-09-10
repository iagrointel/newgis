-- Item L4-04-d-diagrama-esquematico: diagrama de rede (network diagram) derivado de um traçado/subrede/seleção.
-- depende: 20260907T2031_rede_controlador_de_subrede.sql
--
-- Um DIAGRAMA é um GRAFO derivado, nunca a fonte da verdade: os nós e as arestas dele vêm da topologia
-- (`plat.rede_topo_no`/`rede_topo_aresta`, item L4-01-b) recortada por uma origem (a subrede atualizada, um
-- traçado com pontos de partida, ou uma seleção de feições), passam pelas REGRAS do modelo (reduzir junção de
-- passagem, colapsar contêiner, remover tipos) e recebem coordenadas de um LAYOUT. As coordenadas x,y vivem no
-- ESPAÇO DO DIAGRAMA (unidades adimensionais), não em graus: o diagrama esquemático existe justamente para
-- deixar de ser mapa. A ligação com o mapa é feita pela CHAVE do nó (`chave`, ver abaixo), não pela geometria.
--
-- Por que `no_id`/`feicao_id` não têm chave estrangeira para a topologia: `topologia.habilitar()` apaga e refaz
-- o índice derivado inteiro, e uma FK levaria o diagrama junto na primeira reconstrução. O diagrama guarda a
-- ÂNCORA DURÁVEL (`chave`: `terminal:<feicao>:<n>`, `conexao:<no>` ou `conteiner:<feicao>`) e é marcado
-- INCONSISTENTE quando a rede é editada — o mesmo ciclo de vida da subrede (limpa/suja) aplicado ao desenho.
-- `feicao_id` tem FK composta por inquilino porque a feição é dado do usuário e apagar a feição tem de levar o
-- nó do diagrama junto.

CREATE TABLE IF NOT EXISTS plat.rede_diagrama_modelo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  codigo        text NOT NULL CHECK (btrim(codigo) <> '' AND length(codigo) <= 60),
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  regras        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(regras) = 'array'),
  layout        text NOT NULL,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_diagrama_modelo ON plat.rede_diagrama_modelo (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_diagrama_modelo_tenant ON plat.rede_diagrama_modelo (tenant_id);
ALTER TABLE plat.rede_diagrama_modelo DROP CONSTRAINT IF EXISTS rede_diagrama_modelo_tenant_rede_fkey;
ALTER TABLE plat.rede_diagrama_modelo ADD CONSTRAINT rede_diagrama_modelo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS plat.rede_diagrama (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  modelo_id     uuid,
  modelo_codigo text NOT NULL,
  layout        text NOT NULL,
  origem        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(origem) = 'object'),
  estado        text NOT NULL DEFAULT 'consistente' CHECK (estado IN ('consistente','inconsistente')),
  resumo        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(resumo) = 'object'),
  gerado_em     timestamptz NOT NULL DEFAULT now(),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_diagrama_nome ON plat.rede_diagrama (rede_id, nome);
CREATE INDEX IF NOT EXISTS ix_rede_diagrama_tenant ON plat.rede_diagrama (tenant_id);
ALTER TABLE plat.rede_diagrama DROP CONSTRAINT IF EXISTS rede_diagrama_tenant_rede_fkey;
ALTER TABLE plat.rede_diagrama ADD CONSTRAINT rede_diagrama_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_diagrama DROP CONSTRAINT IF EXISTS rede_diagrama_tenant_modelo_fkey;
ALTER TABLE plat.rede_diagrama ADD CONSTRAINT rede_diagrama_tenant_modelo_fkey
  FOREIGN KEY (tenant_id, modelo_id) REFERENCES plat.rede_diagrama_modelo (tenant_id, id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS plat.rede_diagrama_no (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  diagrama_id   uuid NOT NULL,
  chave         text NOT NULL,
  papel         text NOT NULL CHECK (papel IN ('terminal','conexao','conteiner')),
  feicao_id     uuid,
  terminal_num  int CHECK (terminal_num IS NULL OR terminal_num BETWEEN 1 AND 8),
  tipo_id       uuid,
  tipo_chave    text,
  rotulo        text,
  x             double precision NOT NULL,
  y             double precision NOT NULL,
  lon           double precision,
  lat           double precision,
  agregados     int NOT NULL DEFAULT 1 CHECK (agregados >= 1),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_diagrama_no ON plat.rede_diagrama_no (diagrama_id, chave);
CREATE INDEX IF NOT EXISTS ix_rede_diagrama_no_tenant ON plat.rede_diagrama_no (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_diagrama_no_feicao ON plat.rede_diagrama_no (feicao_id);
ALTER TABLE plat.rede_diagrama_no DROP CONSTRAINT IF EXISTS rede_diagrama_no_tenant_diagrama_fkey;
ALTER TABLE plat.rede_diagrama_no ADD CONSTRAINT rede_diagrama_no_tenant_diagrama_fkey
  FOREIGN KEY (tenant_id, diagrama_id) REFERENCES plat.rede_diagrama (tenant_id, id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS plat.rede_diagrama_aresta (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  diagrama_id   uuid NOT NULL,
  chave         text NOT NULL,
  no_de_id      uuid NOT NULL,
  no_para_id    uuid NOT NULL,
  origem        text NOT NULL CHECK (origem IN ('topologia','dispositivo','reduzida')),
  feicoes       jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(feicoes) = 'array'),
  tipo_chave    text,
  agregadas     int NOT NULL DEFAULT 1 CHECK (agregadas >= 1),
  comprimento_m double precision,
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_diagrama_aresta ON plat.rede_diagrama_aresta (diagrama_id, chave);
CREATE INDEX IF NOT EXISTS ix_rede_diagrama_aresta_tenant ON plat.rede_diagrama_aresta (tenant_id);
ALTER TABLE plat.rede_diagrama_aresta DROP CONSTRAINT IF EXISTS rede_diagrama_aresta_tenant_diagrama_fkey;
ALTER TABLE plat.rede_diagrama_aresta ADD CONSTRAINT rede_diagrama_aresta_tenant_diagrama_fkey
  FOREIGN KEY (tenant_id, diagrama_id) REFERENCES plat.rede_diagrama (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_diagrama_aresta DROP CONSTRAINT IF EXISTS rede_diagrama_aresta_tenant_de_fkey;
ALTER TABLE plat.rede_diagrama_aresta ADD CONSTRAINT rede_diagrama_aresta_tenant_de_fkey
  FOREIGN KEY (tenant_id, no_de_id) REFERENCES plat.rede_diagrama_no (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_diagrama_aresta DROP CONSTRAINT IF EXISTS rede_diagrama_aresta_tenant_para_fkey;
ALTER TABLE plat.rede_diagrama_aresta ADD CONSTRAINT rede_diagrama_aresta_tenant_para_fkey
  FOREIGN KEY (tenant_id, no_para_id) REFERENCES plat.rede_diagrama_no (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260907T2031.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_diagrama_modelo','rede_diagrama','rede_diagrama_no','rede_diagrama_aresta'] LOOP
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
  ('redes/diagrama_gerar', 'diagrama de rede gerado a partir de subrede, traçado ou seleção'),
  ('redes/diagrama_layout', 'layout do diagrama reaplicado (nós reposicionados)'),
  ('redes/diagrama_apagar', 'diagrama de rede apagado'),
  ('redes/diagrama_modelo_definir', 'modelo de diagrama definido (regras de construção e layout padrão)')
ON CONFLICT (nome) DO NOTHING;
