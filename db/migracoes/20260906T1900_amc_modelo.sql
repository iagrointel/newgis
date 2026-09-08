-- 20260906T1900_amc_modelo: primeira entrega da linha L3 (motor de análise multicritério explicável),
-- item L3-01-a-modelo-dado (laco/decomposicao/L3L6_CONCEITO.md, seção A: A1/A3/A10/A14).
--
-- Cinco tabelas `plat.amc_*`, esquema ESTREITO (fator é linha, nunca coluna): `amc_modelo` guarda o
-- documento JSON do modelo (validado por JSON Schema fora do banco, em app/amc/esquema.py, contra
-- docs/esquemas/amc_modelo.v1.json) com `versao_hash` = sha256 do JSON canônico; `amc_conjunto_unidade`
-- é o cabeçalho de um conjunto de unidades de análise (a geração da grade/feição é item futuro, L3-01-b);
-- `amc_execucao` congela modelo+versão, pesos escolhidos pelo usuário, proveniência de cada camada de
-- entrada (sha256/contagem), versão do motor e semente; `amc_fator_bruto` e `amc_resultado` são valor por
-- (execução, unidade, fator) — materializados uma vez, nunca editados (A2/A9/A10).
--
-- Imutabilidade em duas camadas: (1) `amc_modelo` fica IMUTÁVEL (`definicao`/`versao_hash`) assim que
-- alguma `amc_execucao` o referencia (`executado = true`, marcado por gatilho); (2) `amc_execucao` nunca
-- muda a proveniência que gravou (modelo, versão, conjunto, pesos, camadas, motor, semente), só o estado
-- da fila; `amc_fator_bruto`/`amc_resultado` nunca aceitam UPDATE e só aceitam DELETE enquanto a execução
-- não estiver `concluida` (limpeza de execução falha/cancelada, nunca de resultado publicado).
--
-- RLS por inquilino nas cinco tabelas, policy única FOR ALL (mesmo padrão de 002_identidade.sql, decisão
-- A14 do CONCEITO): `USING/WITH CHECK (tenant_id = plat.tenant_atual())`. Defesa extra (cinto e suspensório,
-- barata): `amc_execucao` recusa INSERT/UPDATE cujo `modelo_id`/`conjunto_id` não seja do MESMO tenant_id
-- do registro (`amc_execucao_tenant_incoerente`), e `amc_fator_bruto`/`amc_resultado` NUNCA confiam no
-- `tenant_id` que o chamador manda: um gatilho o substitui pelo da execução-mãe antes do INSERT.
--
-- Numeração por carimbo de tempo (ADR 0014) — sem a dor de renumeração do primeiro rascunho deste item
-- (registrada em laco/handoffs/T3/L3-01-a-modelo-dado.md: 031→037→044→045). Idempotente (IF NOT EXISTS /
-- CREATE OR REPLACE / DROP ... IF EXISTS). Sem BEGIN/COMMIT: o aplicador abre a transação. Aplicada como
-- postgres. Privilégio `analise.amc` já existe (003_identidade_acesso.sql linha 54); nenhuma migração de
-- privilégio nova aqui.

CREATE TABLE IF NOT EXISTS plat.amc_modelo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  nome           text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 250),
  definicao      jsonb NOT NULL,
  versao_hash    text NOT NULL CHECK (versao_hash ~ '^[0-9a-f]{64}$'),
  executado      boolean NOT NULL DEFAULT false,
  criado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_por int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  atualizado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_amc_modelo_tenant ON plat.amc_modelo (tenant_id, atualizado_em DESC);

CREATE TABLE IF NOT EXISTS plat.amc_conjunto_unidade (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  nome        text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 250),
  tipo        text NOT NULL CHECK (tipo IN ('hexagonal', 'quadrada', 'feicoes')),
  lado_m      double precision CHECK (lado_m IS NULL OR lado_m > 0),
  n_unidades  int CHECK (n_unidades IS NULL OR n_unidades >= 0),
  config      jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_por  int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_amc_conjunto_tenant ON plat.amc_conjunto_unidade (tenant_id, criado_em DESC);

CREATE TABLE IF NOT EXISTS plat.amc_execucao (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  modelo_id          uuid NOT NULL REFERENCES plat.amc_modelo(id),
  modelo_versao_hash text NOT NULL CHECK (modelo_versao_hash ~ '^[0-9a-f]{64}$'),
  conjunto_id        uuid NOT NULL REFERENCES plat.amc_conjunto_unidade(id),
  pesos              jsonb NOT NULL DEFAULT '{}'::jsonb,
  camadas            jsonb NOT NULL DEFAULT '[]'::jsonb,
  motor_versao       text NOT NULL CHECK (btrim(motor_versao) <> ''),
  semente            bigint NOT NULL,
  estado             text NOT NULL DEFAULT 'registrada'
                       CHECK (estado IN ('registrada', 'extraindo', 'concluida', 'falhou', 'cancelada')),
  criado_por         int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_amc_execucao_tenant ON plat.amc_execucao (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_amc_execucao_modelo ON plat.amc_execucao (modelo_id, modelo_versao_hash);

CREATE TABLE IF NOT EXISTS plat.amc_fator_bruto (
  execucao_id  uuid NOT NULL REFERENCES plat.amc_execucao(id) ON DELETE CASCADE,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  unidade_id   text NOT NULL CHECK (btrim(unidade_id) <> '' AND length(unidade_id) <= 128),
  fator        text NOT NULL CHECK (fator ~ '^[a-z][a-z0-9_]{0,31}$'),
  valor        double precision,
  cobertura    double precision CHECK (cobertura IS NULL OR (cobertura >= 0 AND cobertura <= 1)),
  PRIMARY KEY (execucao_id, unidade_id, fator)
);
CREATE INDEX IF NOT EXISTS ix_amc_fator_bruto_tenant ON plat.amc_fator_bruto (tenant_id);

CREATE TABLE IF NOT EXISTS plat.amc_resultado (
  execucao_id      uuid NOT NULL REFERENCES plat.amc_execucao(id) ON DELETE CASCADE,
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  unidade_id       text NOT NULL CHECK (btrim(unidade_id) <> '' AND length(unidade_id) <= 128),
  favorabilidade   double precision CHECK (favorabilidade IS NULL OR (favorabilidade >= 0 AND favorabilidade <= 100)),
  vetado           boolean NOT NULL DEFAULT false,
  motivo           text,
  cobertura        double precision CHECK (cobertura IS NULL OR (cobertura >= 0 AND cobertura <= 1)),
  PRIMARY KEY (execucao_id, unidade_id),
  CONSTRAINT amc_resultado_vetado_tem_motivo CHECK (NOT vetado OR (favorabilidade IS NULL AND motivo IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_amc_resultado_tenant ON plat.amc_resultado (tenant_id);

-- ---------------------------------------------------------------- atualizado_em (mesmo padrão de 030_conexao.sql)
CREATE OR REPLACE FUNCTION plat.tg_amc_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_modelo_atualizado_em ON plat.amc_modelo;
CREATE TRIGGER amc_modelo_atualizado_em BEFORE UPDATE ON plat.amc_modelo
  FOR EACH ROW EXECUTE FUNCTION plat.tg_amc_atualizado_em();
DROP TRIGGER IF EXISTS amc_execucao_atualizado_em ON plat.amc_execucao;
CREATE TRIGGER amc_execucao_atualizado_em BEFORE UPDATE ON plat.amc_execucao
  FOR EACH ROW EXECUTE FUNCTION plat.tg_amc_atualizado_em();

-- ---------------------------------------------------------------- imutabilidade do modelo executado
CREATE OR REPLACE FUNCTION plat.amc_modelo_guarda() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.executado THEN
      RAISE EXCEPTION 'amc_modelo_nao_apaga' USING HINT = 'modelo já executado nunca se apaga; rode outro modelo';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'amc_modelo_tenant_imutavel';
  END IF;
  IF OLD.executado AND (NEW.definicao IS DISTINCT FROM OLD.definicao OR NEW.versao_hash IS DISTINCT FROM OLD.versao_hash) THEN
    RAISE EXCEPTION 'amc_modelo_identidade_imutavel'
      USING HINT = 'modelo já executado: definição e hash não mudam mais; crie um modelo novo';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_modelo_guarda ON plat.amc_modelo;
CREATE TRIGGER amc_modelo_guarda BEFORE UPDATE OR DELETE ON plat.amc_modelo
  FOR EACH ROW EXECUTE FUNCTION plat.amc_modelo_guarda();

-- ---------------------------------------------------------------- proveniência da execução (imutável) + coerência de tenant
CREATE OR REPLACE FUNCTION plat.amc_execucao_guarda() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  t_modelo   int;
  t_conjunto int;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.estado = 'concluida' THEN
      RAISE EXCEPTION 'amc_execucao_concluida_imutavel' USING HINT = 'execução concluída não se apaga';
    END IF;
    RETURN OLD;
  END IF;
  SELECT tenant_id INTO t_modelo FROM plat.amc_modelo WHERE id = NEW.modelo_id;
  SELECT tenant_id INTO t_conjunto FROM plat.amc_conjunto_unidade WHERE id = NEW.conjunto_id;
  IF t_modelo IS DISTINCT FROM NEW.tenant_id OR t_conjunto IS DISTINCT FROM NEW.tenant_id THEN
    RAISE EXCEPTION 'amc_execucao_tenant_incoerente'
      USING HINT = 'modelo e conjunto de unidades precisam ser do mesmo inquilino da execução';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.modelo_id IS DISTINCT FROM OLD.modelo_id
       OR NEW.modelo_versao_hash IS DISTINCT FROM OLD.modelo_versao_hash
       OR NEW.conjunto_id IS DISTINCT FROM OLD.conjunto_id
       OR NEW.pesos IS DISTINCT FROM OLD.pesos
       OR NEW.camadas IS DISTINCT FROM OLD.camadas
       OR NEW.motor_versao IS DISTINCT FROM OLD.motor_versao
       OR NEW.semente IS DISTINCT FROM OLD.semente THEN
      RAISE EXCEPTION 'amc_execucao_proveniencia_imutavel'
        USING HINT = 'o que rodou não muda; só o estado avança (registrada→extraindo→concluida/falhou/cancelada)';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_execucao_guarda ON plat.amc_execucao;
CREATE TRIGGER amc_execucao_guarda BEFORE INSERT OR UPDATE OR DELETE ON plat.amc_execucao
  FOR EACH ROW EXECUTE FUNCTION plat.amc_execucao_guarda();

-- marca o modelo como executado (permanente) assim que a primeira execução o referencia
CREATE OR REPLACE FUNCTION plat.amc_marcar_modelo_executado() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE plat.amc_modelo SET executado = true WHERE id = NEW.modelo_id AND NOT executado;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_execucao_marca_modelo ON plat.amc_execucao;
CREATE TRIGGER amc_execucao_marca_modelo AFTER INSERT ON plat.amc_execucao
  FOR EACH ROW EXECUTE FUNCTION plat.amc_marcar_modelo_executado();

-- ---------------------------------------------------------------- fator bruto e resultado: tenant herdado, nunca editado
CREATE OR REPLACE FUNCTION plat.amc_materializado_tenant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- nunca confia no tenant_id que o chamador mandou: herda sempre da execução-mãe
  SELECT tenant_id INTO NEW.tenant_id FROM plat.amc_execucao WHERE id = NEW.execucao_id;
  IF NEW.tenant_id IS NULL THEN
    RAISE EXCEPTION 'amc_execucao_inexistente';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_fator_bruto_tenant ON plat.amc_fator_bruto;
CREATE TRIGGER amc_fator_bruto_tenant BEFORE INSERT ON plat.amc_fator_bruto
  FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_tenant();
DROP TRIGGER IF EXISTS amc_resultado_tenant ON plat.amc_resultado;
CREATE TRIGGER amc_resultado_tenant BEFORE INSERT ON plat.amc_resultado
  FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_tenant();

CREATE OR REPLACE FUNCTION plat.amc_materializado_guarda() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  e text;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'amc_materializado_imutavel'
      USING HINT = 'fator bruto e resultado não se editam; rode outra execução';
  END IF;
  -- TG_OP = 'DELETE': só bloqueia quando a execução-mãe já está concluída (limpeza de execução
  -- falha/cancelada continua livre; resultado publicado, nunca)
  SELECT estado INTO e FROM plat.amc_execucao WHERE id = OLD.execucao_id;
  IF e = 'concluida' THEN
    RAISE EXCEPTION 'amc_materializado_imutavel'
      USING HINT = 'fator bruto e resultado de execução concluída não se apagam';
  END IF;
  RETURN OLD;
END $$;
DROP TRIGGER IF EXISTS amc_fator_bruto_guarda ON plat.amc_fator_bruto;
CREATE TRIGGER amc_fator_bruto_guarda BEFORE UPDATE OR DELETE ON plat.amc_fator_bruto
  FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_guarda();
DROP TRIGGER IF EXISTS amc_resultado_guarda ON plat.amc_resultado;
CREATE TRIGGER amc_resultado_guarda BEFORE UPDATE OR DELETE ON plat.amc_resultado
  FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_guarda();

-- ---------------------------------------------------------------- RLS por inquilino (decisão A14: policy única FOR ALL)
ALTER TABLE plat.amc_modelo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_amc_modelo ON plat.amc_modelo;
CREATE POLICY p_amc_modelo ON plat.amc_modelo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.amc_conjunto_unidade ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_amc_conjunto_unidade ON plat.amc_conjunto_unidade;
CREATE POLICY p_amc_conjunto_unidade ON plat.amc_conjunto_unidade FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.amc_execucao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_amc_execucao ON plat.amc_execucao;
CREATE POLICY p_amc_execucao ON plat.amc_execucao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.amc_fator_bruto ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_amc_fator_bruto ON plat.amc_fator_bruto;
CREATE POLICY p_amc_fator_bruto ON plat.amc_fator_bruto FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.amc_resultado ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_amc_resultado ON plat.amc_resultado;
CREATE POLICY p_amc_resultado ON plat.amc_resultado FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- vocabulário de eventos (mesmo padrão de 030_conexao.sql)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('amc/modelo_criar', 'modelo AMC criado (nome, versao_hash)'),
  ('amc/modelo_editar', 'modelo AMC editado (versao_hash novo)'),
  ('amc/modelo_apagar', 'modelo AMC apagado (nome)'),
  ('amc/conjunto_criar', 'conjunto de unidades AMC criado (nome, tipo)'),
  ('amc/conjunto_apagar', 'conjunto de unidades AMC apagado (nome)'),
  ('amc/execucao_criar', 'execução AMC registrada (modelo, versao_hash, conjunto, semente)'),
  ('amc/execucao_apagar', 'execução AMC apagada (estado)')
ON CONFLICT (nome) DO NOTHING;
