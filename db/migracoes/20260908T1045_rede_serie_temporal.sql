-- 20260908T1045_rede_serie_temporal: SÉRIE TEMPORAL DA REDE (item L4-15-serie-temporal-da-rede).
-- depende: 20260906T1553_rede_pacote_de_ativos.sql
-- depende: 20260906T2126_rede_modelo_elementos.sql
--
-- Várias safras da MESMA rede convivem no mesmo inquilino. O modelo de elementos (20260906T2126) guarda
-- uma safra por `plat.rede` — a chave única (rede_id, papel, codigo_externo) impede que o mesmo COD_ID
-- apareça duas vezes na mesma rede, e é isso que se quer: cada safra é uma rede, e a SÉRIE é o que as
-- amarra em ordem de ano.
--
-- O que entra aqui:
--   * `rede_serie`        — a série (nome do inquilino), e quando o cálculo rodou pela última vez;
--   * `rede_serie_safra`  — (série, ano) -> rede importada daquele ano, com o veredito sobre a placa
--                           (POT_NOM) daquela safra;
--   * `rede_linhagem`     — uma linha por COD_ID por par de safras consecutivas, classificado em
--                           persistente / recodificado / novo / extinto, com a evidência que decidiu;
--   * `rede_trafo_safra`  — carregamento por transformador por safra (a tabela de tendência exportável);
--   * `rede_alimentador_safra` — crescimento de rede (km, UC, trafos) por alimentador por safra.
--
-- Tudo é dado do inquilino (tenant_id + RLS), como o resto da linha L4. Idempotente. Sem BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS plat.rede_serie (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  nome          text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  descricao     text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  dono_id       int NOT NULL REFERENCES plat.usuario(id),
  calculado_em  timestamptz,
  metodo        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metodo) = 'object'),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_serie_tenant ON plat.rede_serie (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_serie_nome ON plat.rede_serie (tenant_id, lower(nome));

DROP TRIGGER IF EXISTS rede_serie_atualizado_em ON plat.rede_serie;
CREATE TRIGGER rede_serie_atualizado_em BEFORE UPDATE ON plat.rede_serie
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_atualizado_em();

-- uma safra da série: o ano e a rede que carrega aquele ano. A rede só entra numa série (uma safra é a
-- rede inteira daquele ano), e o ano é único dentro da série.
CREATE TABLE IF NOT EXISTS plat.rede_serie_safra (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  serie_id          uuid NOT NULL,
  rede_id           uuid NOT NULL,
  ano               smallint NOT NULL CHECK (ano BETWEEN 1990 AND 2100),
  pot_nom_confiavel boolean NOT NULL DEFAULT true,
  pot_nom_motivo    text CHECK (pot_nom_motivo IS NULL OR length(pot_nom_motivo) <= 2000),
  criado_em         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (serie_id, ano),
  UNIQUE (serie_id, rede_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_serie_safra_tenant ON plat.rede_serie_safra (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_serie_safra_rede ON plat.rede_serie_safra (rede_id);
ALTER TABLE plat.rede_serie_safra DROP CONSTRAINT IF EXISTS rede_serie_safra_tenant_serie_fkey;
ALTER TABLE plat.rede_serie_safra ADD CONSTRAINT rede_serie_safra_tenant_serie_fkey
  FOREIGN KEY (tenant_id, serie_id) REFERENCES plat.rede_serie (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_serie_safra DROP CONSTRAINT IF EXISTS rede_serie_safra_tenant_rede_fkey;
ALTER TABLE plat.rede_serie_safra ADD CONSTRAINT rede_serie_safra_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- linhagem: uma linha por COD_ID por par de safras consecutivas.
--   persistente   — o mesmo COD_ID está nas duas safras (codigo_base = codigo_alvo);
--   recodificado  — o COD_ID some e outro nasce, e a evidência (UCs em comum / geometria) os casa;
--   novo          — só existe na safra alvo e nada o casa com a base;
--   extinto       — só existe na safra base e nada o casa com o alvo.
-- `confianca` é o número que decidiu (Jaccard das UCs identificadas, ou o valor fixo do casamento por
-- geometria) e `evidencia` guarda o que foi medido, para a conferência não depender de refazer a conta.
CREATE TABLE IF NOT EXISTS plat.rede_linhagem (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  serie_id     uuid NOT NULL,
  entidade     text NOT NULL CHECK (entidade IN ('trafo', 'uc')),
  ano_base     smallint NOT NULL,
  ano_alvo     smallint NOT NULL CHECK (ano_alvo > ano_base),
  codigo_base  text,
  codigo_alvo  text,
  classe       text NOT NULL CHECK (classe IN ('persistente', 'recodificado', 'novo', 'extinto')),
  confianca    double precision NOT NULL DEFAULT 1.0 CHECK (confianca >= 0 AND confianca <= 1),
  evidencia    jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidencia) = 'object'),
  criado_em    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  CHECK (num_nonnulls(codigo_base, codigo_alvo) >= 1),
  CHECK ((classe = 'novo') = (codigo_base IS NULL)),
  CHECK ((classe = 'extinto') = (codigo_alvo IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_rede_linhagem_tenant ON plat.rede_linhagem (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_linhagem_serie ON plat.rede_linhagem (serie_id, entidade, ano_base);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_linhagem_base
  ON plat.rede_linhagem (serie_id, entidade, ano_base, ano_alvo, codigo_base) WHERE codigo_base IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_linhagem_alvo
  ON plat.rede_linhagem (serie_id, entidade, ano_base, ano_alvo, codigo_alvo) WHERE codigo_alvo IS NOT NULL;
ALTER TABLE plat.rede_linhagem DROP CONSTRAINT IF EXISTS rede_linhagem_tenant_serie_fkey;
ALTER TABLE plat.rede_linhagem ADD CONSTRAINT rede_linhagem_tenant_serie_fkey
  FOREIGN KEY (tenant_id, serie_id) REFERENCES plat.rede_serie (tenant_id, id) ON DELETE CASCADE;

-- carregamento por transformador por safra. `carga_pct` é PROXY, não medição: usa a energia declarada
-- na UCBT da fonte com fator de carga e fator de potência fixos (os fatores ficam em `plat.rede_serie.metodo`,
-- escritos pelo cálculo). `pot_nom_confiavel` copia o veredito da safra, para que a exportação carregue a
-- ressalva junto com o número.
CREATE TABLE IF NOT EXISTS plat.rede_trafo_safra (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  serie_id          uuid NOT NULL,
  ano               smallint NOT NULL,
  codigo            text NOT NULL,
  alimentador       text,
  pot_nom_kva       double precision CHECK (pot_nom_kva IS NULL OR pot_nom_kva >= 0),
  energia_ano_kwh   double precision NOT NULL DEFAULT 0 CHECK (energia_ano_kwh >= 0),
  n_uc              int NOT NULL DEFAULT 0 CHECK (n_uc >= 0),
  carga_pct         double precision,
  pot_nom_confiavel boolean NOT NULL DEFAULT true,
  UNIQUE (tenant_id, id),
  UNIQUE (serie_id, ano, codigo)
);
CREATE INDEX IF NOT EXISTS ix_rede_trafo_safra_tenant ON plat.rede_trafo_safra (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_trafo_safra_serie ON plat.rede_trafo_safra (serie_id, codigo);
ALTER TABLE plat.rede_trafo_safra DROP CONSTRAINT IF EXISTS rede_trafo_safra_tenant_serie_fkey;
ALTER TABLE plat.rede_trafo_safra ADD CONSTRAINT rede_trafo_safra_tenant_serie_fkey
  FOREIGN KEY (tenant_id, serie_id) REFERENCES plat.rede_serie (tenant_id, id) ON DELETE CASCADE;

-- crescimento de rede por alimentador por safra: km de trecho, unidades consumidoras, transformadores.
CREATE TABLE IF NOT EXISTS plat.rede_alimentador_safra (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  serie_id     uuid NOT NULL,
  ano          smallint NOT NULL,
  codigo       text NOT NULL,
  km_rede      double precision NOT NULL DEFAULT 0 CHECK (km_rede >= 0),
  n_uc         int NOT NULL DEFAULT 0 CHECK (n_uc >= 0),
  n_trafo      int NOT NULL DEFAULT 0 CHECK (n_trafo >= 0),
  pot_inst_kva double precision NOT NULL DEFAULT 0 CHECK (pot_inst_kva >= 0),
  UNIQUE (tenant_id, id),
  UNIQUE (serie_id, ano, codigo)
);
CREATE INDEX IF NOT EXISTS ix_rede_alimentador_safra_tenant ON plat.rede_alimentador_safra (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_alimentador_safra_serie ON plat.rede_alimentador_safra (serie_id, codigo);
ALTER TABLE plat.rede_alimentador_safra DROP CONSTRAINT IF EXISTS rede_alimentador_safra_tenant_serie_fkey;
ALTER TABLE plat.rede_alimentador_safra ADD CONSTRAINT rede_alimentador_safra_tenant_serie_fkey
  FOREIGN KEY (tenant_id, serie_id) REFERENCES plat.rede_serie (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão das demais tabelas da linha L4 (20260906T1553).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_serie','rede_serie_safra','rede_linhagem','rede_trafo_safra',
                           'rede_alimentador_safra'] LOOP
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
  ('redes/serie_criar', 'série temporal de rede criada (nome)'),
  ('redes/serie_apagar', 'série temporal de rede apagada (nome)'),
  ('redes/serie_safra_anexar', 'safra anexada à série (ano, rede)'),
  ('redes/serie_safra_remover', 'safra removida da série (ano)'),
  ('redes/serie_calcular', 'linhagem, carregamento e crescimento recalculados (contagens por classe)')
ON CONFLICT (nome) DO NOTHING;
