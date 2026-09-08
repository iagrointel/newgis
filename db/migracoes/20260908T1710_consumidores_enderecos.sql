-- 20260908T1710_consumidores_enderecos: consumidores como ativo terminal da rede e cruzamento com
-- endereços do censo (item L4-20-consumidores-e-enderecos). Quatro tabelas por inquilino com RLS:
-- plat.rede_trecho (trecho de rede mt/bt, do importador), plat.rede_trafo (transformador com ponto),
-- plat.rede_uc (unidade consumidora SEM campo identificável: código da distribuidora e atributos de
-- rede, nunca nome/CPF/telefone), plat.rede_uc_consumo (consumo POR unidade, gravado só para alimentar
-- agregação; nenhuma rota o devolve por unidade — a regra de agregação mínima vive em
-- app/limites.py::REDE_AGREGACAO_MIN_UCS), plat.rede_endereco (endereço do censo, ponto público) e
-- plat.rede_endereco_sem_rede (a camada gerada: endereço com rede de média tensão a até N m e sem
-- rede de baixa tensão próxima). As geometrias guardam SRID 4674 (SIRGAS 2000) e uma coluna gerada
-- em projeção métrica 31983 (UTM 23S) para distância em metro. Idempotente. Sem BEGIN/COMMIT.

-- ---------------------------------------------------------------- plat.rede_trecho
CREATE TABLE IF NOT EXISTS plat.rede_trecho (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  nivel          text NOT NULL CHECK (nivel IN ('mt','bt')),
  codigo         text NOT NULL CHECK (codigo <> ''),
  ctmt           text NOT NULL CHECK (ctmt <> ''),
  geometria      geometry(LineString,4674) NOT NULL,
  geometria_calc geometry(LineString,31983) GENERATED ALWAYS AS (ST_Transform(geometria,31983)) STORED,
  comprimento_m  real,
  clientes_jusante int,                       -- preenchido por POST /api/rede/consumidores/jusante/calcular;
                                              -- NULL = fora da árvore (trecho em malha) ou não calculado
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, nivel, codigo)
);
CREATE INDEX IF NOT EXISTS ix_rede_trecho_tenant ON plat.rede_trecho (tenant_id, ctmt);
CREATE INDEX IF NOT EXISTS ix_rede_trecho_calc   ON plat.rede_trecho USING gist (geometria_calc);

ALTER TABLE plat.rede_trecho ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_trecho ON plat.rede_trecho;
CREATE POLICY p_rede_trecho ON plat.rede_trecho FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.rede_trafo
CREATE TABLE IF NOT EXISTS plat.rede_trafo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  codigo         text NOT NULL CHECK (codigo <> ''),
  ctmt           text NOT NULL CHECK (ctmt <> ''),
  tensao_kv      real,
  geometria      geometry(Point,4674),
  geometria_calc geometry(Point,31983) GENERATED ALWAYS AS (ST_Transform(geometria,31983)) STORED,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo)
);
CREATE INDEX IF NOT EXISTS ix_rede_trafo_tenant ON plat.rede_trafo (tenant_id, ctmt);
CREATE INDEX IF NOT EXISTS ix_rede_trafo_calc   ON plat.rede_trafo USING gist (geometria_calc);

ALTER TABLE plat.rede_trafo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_trafo ON plat.rede_trafo;
CREATE POLICY p_rede_trafo ON plat.rede_trafo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.rede_uc (sem campo identificável)
CREATE TABLE IF NOT EXISTS plat.rede_uc (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  codigo    text NOT NULL CHECK (codigo <> ''),     -- código da unidade na distribuidora (não é pessoa)
  ctmt      text NOT NULL CHECK (ctmt <> ''),
  uni_tr_mt text,                                    -- transformador (código), quando conhecido
  situacao  text,                                    -- situação de atividade declarada pela fonte
  grupo_tensao text,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo)
);
CREATE INDEX IF NOT EXISTS ix_rede_uc_tenant_trafo ON plat.rede_uc (tenant_id, uni_tr_mt);
CREATE INDEX IF NOT EXISTS ix_rede_uc_tenant_ctmt  ON plat.rede_uc (tenant_id, ctmt);

ALTER TABLE plat.rede_uc ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_uc ON plat.rede_uc;
CREATE POLICY p_rede_uc ON plat.rede_uc FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.rede_uc_consumo (só agregado)
-- Um registro por unidade/ano, lido apenas pelas funções de agregação (mínimo de
-- REDE_AGREGACAO_MIN_UCS unidades). Nenhuma rota devolve esta linha identificada.
CREATE TABLE IF NOT EXISTS plat.rede_uc_consumo (
  uc_id     uuid NOT NULL REFERENCES plat.rede_uc(id) ON DELETE CASCADE,
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  ano       int NOT NULL,
  ene_kwh   double precision NOT NULL CHECK (ene_kwh >= 0),
  PRIMARY KEY (uc_id, ano)
);
CREATE INDEX IF NOT EXISTS ix_rede_uc_consumo_tenant ON plat.rede_uc_consumo (tenant_id, ano);

ALTER TABLE plat.rede_uc_consumo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_uc_consumo ON plat.rede_uc_consumo;
CREATE POLICY p_rede_uc_consumo ON plat.rede_uc_consumo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.rede_endereco (ponto do censo)
CREATE TABLE IF NOT EXISTS plat.rede_endereco (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  fonte          text NOT NULL DEFAULT 'censo',
  endereco_id    bigint NOT NULL,                    -- identificador numérico da fonte pública
  geometria      geometry(Point,4674) NOT NULL,
  geometria_calc geometry(Point,31983) GENERATED ALWAYS AS (ST_Transform(geometria,31983)) STORED,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, fonte, endereco_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_endereco_calc ON plat.rede_endereco USING gist (geometria_calc);

ALTER TABLE plat.rede_endereco ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_endereco ON plat.rede_endereco;
CREATE POLICY p_rede_endereco ON plat.rede_endereco FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.rede_endereco_sem_rede (camada gerada)
CREATE TABLE IF NOT EXISTS plat.rede_endereco_sem_rede (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  endereco_id    bigint NOT NULL,
  geometria      geometry(Point,4674) NOT NULL,
  geometria_calc geometry(Point,31983) GENERATED ALWAYS AS (ST_Transform(geometria,31983)) STORED,
  dist_rede_m    real NOT NULL CHECK (dist_rede_m >= 0),
  situacao       text NOT NULL CHECK (situacao IN ('candidato_ligacao','cadastro_faltante')),
  gerado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, endereco_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_esr_tenant  ON plat.rede_endereco_sem_rede (tenant_id, situacao);
CREATE INDEX IF NOT EXISTS ix_rede_esr_calc    ON plat.rede_endereco_sem_rede USING gist (geometria_calc);

ALTER TABLE plat.rede_endereco_sem_rede ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_endereco_sem_rede ON plat.rede_endereco_sem_rede;
CREATE POLICY p_rede_endereco_sem_rede ON plat.rede_endereco_sem_rede FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- privilégio de leitura para o papel leitor
GRANT SELECT ON plat.rede_trecho, plat.rede_trafo, plat.rede_uc, plat.rede_endereco,
                plat.rede_endereco_sem_rede TO plat_leitor;

-- ---------------------------------------------------------------- tipos de evento das rotas de escrita
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('rede/enderecos_sem_rede', 'camada de endereços sem rede próxima gerada'),
  ('rede/jusante_calcular', 'número de consumidores a jusante calculado por trecho de média tensão')
ON CONFLICT (nome) DO NOTHING;
