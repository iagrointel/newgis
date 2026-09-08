-- L4-parcelas-02-fluxos-cogo: fluxos de edição cadastral da malha de parcelas (dividir, unir,
-- recortar, build, sementes, atribuir a registro) e a fachada REST em /api/parcelas/fabrica/*.
-- Par: docs/PARIDADE_PARCELAS.md (seções 11-13), app/parcelas/fluxos.py, app/parcelas/dxf.py.
--
-- O que este item adiciona de modelo é UMA tabela: plat.parcela_semente (a semente do build —
-- Is Seed da paridade, classe própria na referência e classe própria aqui). O resto é
-- comportamento sobre as tabelas do item 01 (20260908T2140_parcelas.sql) e semeadura dos tipos
-- de evento da fachada.

CREATE TABLE IF NOT EXISTS plat.parcela_semente (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  geom          geometry(Polygon, 31982) NOT NULL,  -- a face fechada pelas linhas (o anel da futura parcela)
  criada_por_registro  uuid NOT NULL REFERENCES plat.parcela_registro(id),
  retirada_por_registro uuid REFERENCES plat.parcela_registro(id),
  retirada_em   timestamptz,
  atributos     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  ativa         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CHECK (retirada_por_registro IS NULL OR NOT ativa),  -- retirada = histórica (mesma regra da parcela)
  CHECK ((retirada_por_registro IS NULL) = (retirada_em IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_parcela_semente_tenant ON plat.parcela_semente (tenant_id) WHERE ativa;
CREATE INDEX IF NOT EXISTS ix_parcela_semente_geom ON plat.parcela_semente USING gist (geom);
COMMENT ON TABLE plat.parcela_semente IS
  'Semente do build de parcelas (Is Seed da paridade com parcel fabric): face fechada por linhas
  ainda sem parcela, criada por createSeeds e convertida em parcela por reconstructFromSeeds.
  Inquilino por tenant_id com RLS, como as demais tabelas da malha (20260908T2140_parcelas.sql).';

ALTER TABLE plat.parcela_semente ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_semente ON plat.parcela_semente;
CREATE POLICY p_parcela_semente ON plat.parcela_semente FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

GRANT SELECT ON plat.parcela_semente TO plat_leitor;

-- Tipos de evento da fachada REST (tests/api/eventos_esperados.py cita cada um; sem a linha aqui
-- a rota cai em 500 na hora de registrar o evento — mesma classe de erro da migração multiescala).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('parcelas/build', 'build de parcelas a partir de linhas fechadas (quantidade de faces geradas)'),
  ('parcelas/divide', 'divisão de parcela (área/proporção/largura ou linha de corte)'),
  ('parcelas/merge', 'união de parcelas (linhas externas mantidas, interna retirada)'),
  ('parcelas/clip', 'recorte de parcela (interseção e/ou resto, conforme clipOption)'),
  ('parcelas/create_seeds', 'sementes criadas sobre faces fechadas (createSeeds)'),
  ('parcelas/reconstruct_from_seeds', 'parcelas reconstruídas de sementes (reconstructFromSeeds)'),
  ('parcelas/assign_features_to_record', 'feições atribuídas a registro (assignFeaturesToRecord)')
ON CONFLICT (nome) DO NOTHING;
