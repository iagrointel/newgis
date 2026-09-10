-- 20260906T2156_rede_categorias_restricoes: feição instanciada, ligação, restrição de feição e área suja
-- (item L4-06-d-categorias-e-restricoes; ADR 20260906T2156-rede-categorias-restricoes).
--
-- O item L4-01-a entregou o ESQUEMA da rede (pacote de ativos: categorias, tipos, terminais). Este item entrega
-- o que as cláusulas do portão exigem sobre feições de verdade:
--   * alterar a categoria de um tipo marca área suja em TODAS as feições do tipo (a contagem sai da resposta);
--   * a refutação exige recusar a remoção da categoria 'controlador' de um tipo com controladores ATIVOS —
--     logo a feição precisa existir e precisa do estado controlador_ativo;
--   * a restrição 'sem_ponto_partida' impede o traçado a partir de feição daquele tipo (o caso do portão é a
--     unidade consumidora), logo existe grafo: feição + ligação.
--
-- ESCOPO DECLARADO (para os itens seguintes da linha L4 não refazerem decisão): plat.rede_feicao é a feição
-- mínima — sem geometria e sem origem em camada (a topologia derivada do dado é L4-01-b; a área suja como
-- EXTENSÃO ESPACIAL e o ciclo de validação são L4-03-d; controladores com nome de subrede e terminal são
-- L4-04-a). Aqui a área suja é a MARCA por feição e o controlador é o estado ligado/desligado. Quem vier
-- depois ACRESCENTA coluna/tabela; não recria estas.
--
-- Tudo é dado do INQUILINO (tenant_id + RLS), no mesmo padrão da migração 20260906T1553 (pacote de ativos).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- feição: um ativo instanciado de um tipo do catálogo, com identificador próprio dentro do tipo
CREATE TABLE IF NOT EXISTS plat.rede_feicao (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  rede_id            uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  tipo_id            uuid NOT NULL REFERENCES plat.rede_tipo(id) ON DELETE CASCADE,
  codigo             text NOT NULL CHECK (codigo ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$'),
  controlador_ativo  boolean NOT NULL DEFAULT false,
  suja               boolean NOT NULL DEFAULT true,  -- toda feição nasce suja, como na topologia Esri
  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_feicao ON plat.rede_feicao (rede_id, tipo_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_tenant ON plat.rede_feicao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_tipo ON plat.rede_feicao (tipo_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_suja ON plat.rede_feicao (rede_id) WHERE suja;

CREATE OR REPLACE FUNCTION plat.tg_rede_feicao_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS rede_feicao_atualizado_em ON plat.rede_feicao;
CREATE TRIGGER rede_feicao_atualizado_em BEFORE UPDATE ON plat.rede_feicao
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_feicao_atualizado_em();

-- ligação: aresta de conectividade entre duas feições da MESMA rede. Guardada uma vez, com o par ordenado
-- (de < para na forma texto do uuid — a aplicação normaliza antes de gravar); o traçado trata como não
-- dirigida. A derivação desta aresta a partir da geometria é o item L4-01-b.
CREATE TABLE IF NOT EXISTS plat.rede_feicao_ligacao (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  rede_id         uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  de_feicao_id    uuid NOT NULL REFERENCES plat.rede_feicao(id) ON DELETE CASCADE,
  para_feicao_id  uuid NOT NULL REFERENCES plat.rede_feicao(id) ON DELETE CASCADE,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  CHECK (de_feicao_id <> para_feicao_id),
  CHECK (de_feicao_id::text < para_feicao_id::text)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_feicao_ligacao ON plat.rede_feicao_ligacao (de_feicao_id, para_feicao_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ligacao_tenant ON plat.rede_feicao_ligacao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ligacao_de ON plat.rede_feicao_ligacao (de_feicao_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ligacao_para ON plat.rede_feicao_ligacao (para_feicao_id);

-- restrição de feição por tipo de ativo (o equivalente configurável das 'feature restrictions'):
--   sem_ponto_partida — feição do tipo não pode ser ponto de partida de traçado (o caso da UC);
--   sem_terminal      — o tipo não admite configuração de terminal nem controlador ativo (controlador se
--                       atribui a um terminal; sem terminal não há onde pendurar o controlador).
CREATE TABLE IF NOT EXISTS plat.rede_tipo_restricao (
  tenant_id  int NOT NULL REFERENCES plat.tenant(id),
  rede_id    uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  tipo_id    uuid NOT NULL REFERENCES plat.rede_tipo(id) ON DELETE CASCADE,
  restricao  text NOT NULL CHECK (restricao IN ('sem_ponto_partida', 'sem_terminal')),
  PRIMARY KEY (tipo_id, restricao)
);
CREATE INDEX IF NOT EXISTS ix_rede_tipo_restricao_tenant ON plat.rede_tipo_restricao (tenant_id);

-- RLS e GRANTs: mesmo padrão da migração 20260906T1553 (pacote de ativos).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_feicao', 'rede_feicao_ligacao', 'rede_tipo_restricao'] LOOP
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
  ('redes/categorias_definir', 'conjunto de categorias de um tipo de ativo redefinido (antes, depois, áreas sujas)'),
  ('redes/restricoes_definir', 'conjunto de restrições de feição de um tipo de ativo redefinido (antes, depois)'),
  ('redes/feicao_criar', 'feição de rede criada (tipo, código, controlador)'),
  ('redes/feicao_alterar', 'feição de rede alterada (controlador ativado/desativado)'),
  ('redes/feicoes_ligar', 'ligação de conectividade criada entre duas feições')
ON CONFLICT (nome) DO NOTHING;
