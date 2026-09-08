-- 20260908T2140_parcelas: malha de parcelas (item L4-parcelas-01-modelo-de-parcelas).
-- Modelo orientado a REGISTRO (paridade com o parcel fabric: docs/PARIDADE_PARCELAS.md): um
-- registro é o documento legal que cria e retira feições (matrícula, escritura, loteamento,
-- desmembramento, remembramento, aprovação); a feição histórica é a que tem
-- retirada_por_registro preenchido — "Retired By Record" do modelo de referência. Seis tabelas
-- por inquilino com RLS: parcela_registro, parcela_ponto (precisão declarada), parcela_linha
-- (atributos COGO: rumo, distância, raio, comprimento de arco), parcela_linha_parcela (linha
-- partilhada entre parcelas — n:n), parcela (polígono por TIPO: lote, gleba, quadra, servidão,
-- estrato; área declarada e calculada; erro de fechamento COGO) e parcela_conexao (medida entre
-- pontos que NÃO é limite de parcela). Duas visões: v_parcela_atual (ativa) e
-- v_parcela_historico (retirada, com o registro). O versionamento do ciclo de vida É a
-- linhagem por registro (criada_por/retirada_por); versionamento de ramo (branch versioning do
-- produto de referência) é a linha L2-13 e entra depois, sem mudar estas tabelas. Nenhuma
-- matrícula real e nenhum nome: o vocabulário de tipo é fechado e o código é texto livre do
-- inquilino. Idempotente.

-- ---------------------------------------------------------------- plat.parcela_registro
CREATE TABLE IF NOT EXISTS plat.parcela_registro (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  codigo       text NOT NULL CHECK (codigo <> ''),  -- nome do documento (nunca matrícula real)
  tipo         text NOT NULL CHECK (tipo IN
                 ('matricula','escritura','loteamento','desmembramento','remembramento','aprovacao','outro')),
  origem       text NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual','importado','sintetico')),
  data_registro date,                                -- data no documento (Recorded Date)
  descricao    text,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo)
);
CREATE INDEX IF NOT EXISTS ix_parcela_registro_tenant ON plat.parcela_registro (tenant_id, tipo);

-- ---------------------------------------------------------------- plat.parcela_ponto
CREATE TABLE IF NOT EXISTS plat.parcela_ponto (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  nome          text,                                 -- rótulo do vértice (sem pessoa)
  geom          geometry(Point, 31982) NOT NULL,
  precisao_xy_m numeric CHECK (precisao_xy_m IS NULL OR precisao_xy_m >= 0),  -- declarada, não inferida
  fixo          boolean NOT NULL DEFAULT false,       -- ponto de controle (Fixed Shape)
  origem        text NOT NULL DEFAULT 'medida' CHECK (origem IN ('medida','escaneada','derivada')),
  criada_por_registro uuid REFERENCES plat.parcela_registro(id),
  retirada_por_registro uuid REFERENCES plat.parcela_registro(id),
  ativa         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_parcela_ponto_tenant ON plat.parcela_ponto (tenant_id) WHERE ativa;
CREATE INDEX IF NOT EXISTS ix_parcela_ponto_geom ON plat.parcela_ponto USING gist (geom);

-- ---------------------------------------------------------------- plat.parcela_linha
CREATE TABLE IF NOT EXISTS plat.parcela_linha (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  de_ponto_id   uuid NOT NULL REFERENCES plat.parcela_ponto(id),
  para_ponto_id uuid NOT NULL REFERENCES plat.parcela_ponto(id),
  geom          geometry(LineString, 31982) NOT NULL,
  rumo_graus    numeric CHECK (rumo_graus IS NULL OR (rumo_graus >= 0 AND rumo_graus < 360)),
  distancia_m   numeric CHECK (distancia_m IS NULL OR distancia_m >= 0),
  raio_m        numeric CHECK (raio_m IS NULL OR raio_m <> 0),  -- COM SINAL: positivo curva à direita
  arco_m        numeric CHECK (arco_m IS NULL OR arco_m >= 0),   -- comprimento de arco (arco = raio+arco)
  tipo_cogo     text CHECK (tipo_cogo IN ('reta','arco') OR tipo_cogo IS NULL),
  precisao_rumo_s numeric CHECK (precisao_rumo_s IS NULL OR precisao_rumo_s >= 0),  -- s de arco
  precisao_dist_cm numeric CHECK (precisao_dist_cm IS NULL OR precisao_dist_cm >= 0), -- cm
  origem        text NOT NULL DEFAULT 'medida' CHECK (origem IN ('medida','escaneada','derivada')),
  criada_por_registro uuid REFERENCES plat.parcela_registro(id),
  retirada_por_registro uuid REFERENCES plat.parcela_registro(id),
  ativa         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CHECK (de_ponto_id <> para_ponto_id),
  CHECK ((tipo_cogo = 'arco') = (raio_m IS NOT NULL))  -- arco declara raio; reta não
);
CREATE INDEX IF NOT EXISTS ix_parcela_linha_tenant ON plat.parcela_linha (tenant_id) WHERE ativa;
CREATE INDEX IF NOT EXISTS ix_parcela_linha_pontos ON plat.parcela_linha (tenant_id, de_ponto_id, para_ponto_id);

-- ---------------------------------------------------------------- plat.parcela
CREATE TABLE IF NOT EXISTS plat.parcela (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  tipo          text NOT NULL CHECK (tipo IN ('lote','gleba','quadra','servidao','estrato')),
  codigo        text NOT NULL CHECK (codigo <> ''),
  geom          geometry(Polygon, 31982) NOT NULL,
  area_declarada_m2 numeric CHECK (area_declarada_m2 IS NULL OR area_declarada_m2 >= 0),
  area_calculada_m2 numeric,          -- ST_Area na gravação (o motor preenche, o inquilino não)
  erro_fechamento_m numeric,          -- distância do fechamento do trajeto COGO
  erro_fechamento_razao numeric,      -- razão de fechamento (perímetro / erro)
  atributos     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criada_por_registro  uuid NOT NULL REFERENCES plat.parcela_registro(id),
  retirada_por_registro uuid REFERENCES plat.parcela_registro(id),
  retirada_em   timestamptz,
  ativa         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, tipo, codigo, criada_por_registro),
  CHECK (retirada_por_registro IS NULL OR NOT ativa),  -- retirada = histórica
  CHECK ((retirada_por_registro IS NULL) = (retirada_em IS NULL)),
  CHECK (retirada_por_registro IS NULL OR retirada_por_registro <> criada_por_registro)
);
CREATE INDEX IF NOT EXISTS ix_parcela_tenant_tipo ON plat.parcela (tenant_id, tipo) WHERE ativa;
CREATE INDEX IF NOT EXISTS ix_parcela_tenant_historico ON plat.parcela (tenant_id, tipo) WHERE NOT ativa;
CREATE INDEX IF NOT EXISTS ix_parcela_geom ON plat.parcela USING gist (geom);

-- ---------------------------------------------------------------- plat.parcela_linha_parcela
-- Linha PARTILHADA: uma linha de limite pode servir a duas parcelas (n:n). É esta tabela que
-- faz existir "linha partilhada" no modelo — a mesma linha física, dois usos.
CREATE TABLE IF NOT EXISTS plat.parcela_linha_parcela (
  tenant_id  int NOT NULL REFERENCES plat.tenant(id),
  linha_id   uuid NOT NULL REFERENCES plat.parcela_linha(id) ON DELETE CASCADE,
  parcela_id uuid NOT NULL REFERENCES plat.parcela(id) ON DELETE CASCADE,
  PRIMARY KEY (linha_id, parcela_id)
);
CREATE INDEX IF NOT EXISTS ix_parcela_linha_parcela_parc ON plat.parcela_linha_parcela (parcela_id);

-- ---------------------------------------------------------------- plat.parcela_conexao
-- Medida entre dois pontos que NÃO é limite de parcela (Connection Lines do modelo de
-- referência): esquina de quadra a esquina de quadra, referência de topografia, etc.
CREATE TABLE IF NOT EXISTS plat.parcela_conexao (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  de_ponto_id   uuid NOT NULL REFERENCES plat.parcela_ponto(id),
  para_ponto_id uuid NOT NULL REFERENCES plat.parcela_ponto(id),
  geom          geometry(LineString, 31982) NOT NULL,
  rumo_graus    numeric CHECK (rumo_graus IS NULL OR (rumo_graus >= 0 AND rumo_graus < 360)),
  distancia_m   numeric CHECK (distancia_m IS NULL OR distancia_m >= 0),
  descricao     text,
  criada_por_registro uuid REFERENCES plat.parcela_registro(id),
  retirada_por_registro uuid REFERENCES plat.parcela_registro(id),
  ativa         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CHECK (de_ponto_id <> para_ponto_id)
);
CREATE INDEX IF NOT EXISTS ix_parcela_conexao_tenant ON plat.parcela_conexao (tenant_id) WHERE ativa;

-- ---------------------------------------------------------------- visões atual × histórico
-- security_invoker: a visão responde com a RLS de QUEM CONSULTA, não com a do dono (dono =
-- postgres, que passa por cima da RLS — sem isso a visão do histórico vazaría inquilino).
CREATE OR REPLACE VIEW plat.v_parcela_atual WITH (security_invoker = true) AS
  SELECT id, tenant_id, tipo, codigo, geom, area_declarada_m2, area_calculada_m2,
         atributos, criada_por_registro, criado_em, atualizado_em
  FROM plat.parcela WHERE ativa;

CREATE OR REPLACE VIEW plat.v_parcela_historico WITH (security_invoker = true) AS
  SELECT p.id, p.tenant_id, p.tipo, p.codigo, p.geom, p.area_declarada_m2, p.area_calculada_m2,
         p.atributos, p.criada_por_registro, p.retirada_por_registro,
         r.codigo AS retirada_por_codigo, r.tipo AS retirada_por_tipo,
         p.retirada_em, p.criado_em
  FROM plat.parcela p
  JOIN plat.parcela_registro r ON r.id = p.retirada_por_registro;

-- ---------------------------------------------------------------- RLS (todas as seis tabelas + visões herdam do dono)
ALTER TABLE plat.parcela_registro ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_registro ON plat.parcela_registro;
CREATE POLICY p_parcela_registro ON plat.parcela_registro FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.parcela_ponto ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_ponto ON plat.parcela_ponto;
CREATE POLICY p_parcela_ponto ON plat.parcela_ponto FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.parcela_linha ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_linha ON plat.parcela_linha;
CREATE POLICY p_parcela_linha ON plat.parcela_linha FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.parcela_linha_parcela ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_linha_parcela ON plat.parcela_linha_parcela;
CREATE POLICY p_parcela_linha_parcela ON plat.parcela_linha_parcela FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.parcela ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela ON plat.parcela;
CREATE POLICY p_parcela ON plat.parcela FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.parcela_conexao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_conexao ON plat.parcela_conexao;
CREATE POLICY p_parcela_conexao ON plat.parcela_conexao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- privilégio
-- Leitor: leitura nas seis tabelas e nas duas visões (a RLS é quem decide as linhas; sem
-- política para o leitor ele lê zero — igual ao acesso direto de tabela).
GRANT SELECT ON plat.parcela_registro, plat.parcela_ponto, plat.parcela_linha,
  plat.parcela_linha_parcela, plat.parcela, plat.parcela_conexao,
  plat.v_parcela_atual, plat.v_parcela_historico TO plat_leitor;
-- App: leitura explícita nas visões. A fundação (001) dá os privilégios padrão e vale para
-- tabela nova; visão só deste ramo não nasce com privilégio nos ambientes de trilha, que copiam
-- a matriz de produção (onde a visão ainda não existe) e só alargam TABELA.
GRANT SELECT ON plat.v_parcela_atual, plat.v_parcela_historico TO plat_app;
