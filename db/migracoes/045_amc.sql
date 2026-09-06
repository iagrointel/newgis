-- 044_amc: motor multicritério (AMC) — modelo de dado (item L3-01-a-modelo-dado) e conjunto de unidades de análise
-- (item L3-01-b-unidades). Decisões de conceito em laco/decomposicao/L3L6_CONCEITO.md, parte A (A1, A3, A5, A6, A7,
-- A10, A14) e docs/adr/0016-motor-amc-modelo-e-unidades.md. Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Forma: o MODELO é um documento JSON (validado pela API contra docs/esquemas/amc_modelo.v1.json) cuja versão é o
-- sha256 do JSON canônico (json.dumps sort_keys=True, separators=(',', ':'), ensure_ascii=False). plat.amc_modelo é a
-- cabeça editável (nome + versão atual); plat.amc_modelo_versao guarda TODA versão que já existiu e é imutável para a
-- aplicação (gatilho): editar um modelo cria uma versão nova e move a cabeça; uma execução referencia (modelo_id,
-- versao_hash) e por isso continua apontando para a versão que rodou, mesmo depois de o modelo ser editado.
-- Fator bruto e resultado são LINHAS (execução × unidade × fator), nunca uma coluna por fator.

-- ---------------------------------------------------------------- modelo (cabeça) e versões
CREATE TABLE IF NOT EXISTS plat.amc_modelo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  nome           text NOT NULL CHECK (length(nome) BETWEEN 1 AND 250),
  versao_hash    text NOT NULL CHECK (versao_hash ~ '^[0-9a-f]{64}$'),   -- versão ATUAL (cabeça)
  n_versoes      int NOT NULL DEFAULT 1 CHECK (n_versoes >= 1),
  criado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  atualizado_por int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  apagado_em     timestamptz                                             -- apagar = esconder; as versões ficam
);
CREATE INDEX IF NOT EXISTS ix_amc_modelo_tenant ON plat.amc_modelo (tenant_id, atualizado_em DESC) WHERE apagado_em IS NULL;

CREATE TABLE IF NOT EXISTS plat.amc_modelo_versao (
  modelo_id    uuid NOT NULL REFERENCES plat.amc_modelo(id) ON DELETE CASCADE,
  versao_hash  text NOT NULL CHECK (versao_hash ~ '^[0-9a-f]{64}$'),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  numero       int NOT NULL CHECK (numero >= 1),
  definicao    jsonb NOT NULL,                       -- o documento inteiro; o hash é recomputável só daqui
  criado_por   int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (modelo_id, versao_hash),
  UNIQUE (modelo_id, numero)
);

-- a cabeça tem de apontar para uma versão que existe (FK composta; a versão é inserida antes da cabeça ser atualizada)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_amc_modelo_versao_atual') THEN
    ALTER TABLE plat.amc_modelo ADD CONSTRAINT fk_amc_modelo_versao_atual
      FOREIGN KEY (id, versao_hash) REFERENCES plat.amc_modelo_versao(modelo_id, versao_hash)
      DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $$;

-- ---------------------------------------------------------------- conjunto de unidades de análise (L3-01-b)
CREATE TABLE IF NOT EXISTS plat.amc_conjunto_unidade (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  nome           text NOT NULL CHECK (length(nome) BETWEEN 1 AND 250),
  tipo           text NOT NULL CHECK (tipo IN ('hexagonal', 'quadrada', 'feicoes')),
  lado_m         double precision CHECK (lado_m IS NULL OR lado_m > 0),      -- lado da célula (grade); NULL em feições
  srid_trabalho  int NOT NULL REFERENCES public.spatial_ref_sys(srid),       -- UTM SIRGAS 2000 da zona do centróide
  area_estudo    geometry(MultiPolygon, 4326),                               -- polígono de recorte (grade); NULL em feições
  estado         text NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente', 'pronto', 'falhou')),
  job_id         uuid,                                                       -- job amc.gerar_unidades (grade)
  n_unidades     int,
  area_total_m2  double precision,                                           -- soma das áreas geodésicas
  ficha          jsonb NOT NULL DEFAULT '{}'::jsonb,                         -- CRS, distorção, contagem esperada, tempo
  erro           text,
  criado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  pronto_em      timestamptz,
  CHECK (tipo = 'feicoes' OR (lado_m IS NOT NULL AND area_estudo IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_amc_conjunto_tenant ON plat.amc_conjunto_unidade (tenant_id, criado_em DESC);

CREATE TABLE IF NOT EXISTS plat.amc_unidade (
  conjunto_id  uuid NOT NULL REFERENCES plat.amc_conjunto_unidade(id) ON DELETE CASCADE,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  unidade_id   text NOT NULL CHECK (length(unidade_id) BETWEEN 1 AND 200),   -- '<i>_<j>' na grade; id do usuário em feições
  geom         geometry(MultiPolygon, 4326) NOT NULL,                        -- para o mapa; agregação reprojeta para srid_trabalho
  area_m2      double precision NOT NULL CHECK (area_m2 >= 0),               -- geodésica (geography, GRS80)
  PRIMARY KEY (conjunto_id, unidade_id)
);
CREATE INDEX IF NOT EXISTS ix_amc_unidade_geom ON plat.amc_unidade USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_amc_unidade_tenant ON plat.amc_unidade (tenant_id);

-- ---------------------------------------------------------------- execução (proveniência) e materializações
CREATE TABLE IF NOT EXISTS plat.amc_execucao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  modelo_id      uuid NOT NULL REFERENCES plat.amc_modelo(id),
  versao_hash    text NOT NULL,
  conjunto_id    uuid NOT NULL REFERENCES plat.amc_conjunto_unidade(id) ON DELETE RESTRICT,
  pesos          jsonb NOT NULL,        -- {fator_id: peso} usados nesta execução (pesos escolhidos pelo usuário, não medidos)
  camadas        jsonb NOT NULL,        -- [{fator, camada_tipo, camada_id, titulo, sha256, contagem, versao}] no instante da execução
  motor_versao   text NOT NULL,         -- 'amc/<versão do motor>+<VERSAO>+<git sha>'
  semente        bigint NOT NULL,       -- reprodutibilidade de qualquer sorteio (robustez, L3-02)
  estado         text NOT NULL DEFAULT 'registrada'
                 CHECK (estado IN ('registrada', 'extraindo', 'concluida', 'falhou', 'cancelada')),
  job_id         uuid,
  erro           text,
  criado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  iniciado_em    timestamptz,
  terminado_em   timestamptz,
  FOREIGN KEY (modelo_id, versao_hash) REFERENCES plat.amc_modelo_versao(modelo_id, versao_hash)
);
CREATE INDEX IF NOT EXISTS ix_amc_execucao_tenant ON plat.amc_execucao (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_amc_execucao_modelo ON plat.amc_execucao (modelo_id, versao_hash);

CREATE TABLE IF NOT EXISTS plat.amc_fator_bruto (
  execucao_id  uuid NOT NULL REFERENCES plat.amc_execucao(id) ON DELETE CASCADE,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  unidade_id   text NOT NULL,
  fator        text NOT NULL,
  valor        double precision,                          -- valor BRUTO na unidade de medida do extrator; NULL = sem dado
  cobertura    real CHECK (cobertura IS NULL OR (cobertura >= 0 AND cobertura <= 1)),
  PRIMARY KEY (execucao_id, unidade_id, fator)
);

CREATE TABLE IF NOT EXISTS plat.amc_resultado (
  execucao_id    uuid NOT NULL REFERENCES plat.amc_execucao(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  unidade_id     text NOT NULL,
  favorabilidade double precision CHECK (favorabilidade IS NULL OR (favorabilidade >= 0 AND favorabilidade <= 100)),
  vetado         boolean NOT NULL DEFAULT false,
  motivo         text,
  cobertura      real CHECK (cobertura IS NULL OR (cobertura >= 0 AND cobertura <= 1)),
  PRIMARY KEY (execucao_id, unidade_id),
  -- A3: unidade vetada nunca carrega número na escala; o motivo é obrigatório
  CHECK (NOT vetado OR (favorabilidade IS NULL AND motivo IS NOT NULL))
);

-- ---------------------------------------------------------------- RLS por inquilino (mesmo padrão de 002/022)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['amc_modelo', 'amc_modelo_versao', 'amc_conjunto_unidade', 'amc_unidade', 'amc_execucao',
                           'amc_fator_bruto', 'amc_resultado'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR ALL TO plat_app USING (tenant_id = plat.tenant_atual()) '
                   'WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------- imutabilidade (gatilhos)
-- Só um superusuário (migração, expurgo de inquilino pela função SECURITY DEFINER de 009, DBA) passa; para a aplicação
-- (plat_app) o que já foi versionado ou executado nunca muda. Códigos curtos → app.auth.comum.erro_do_banco.
CREATE OR REPLACE FUNCTION plat.amc_superusuario() RETURNS boolean LANGUAGE sql STABLE AS
  $$ SELECT coalesce((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) $$;

CREATE OR REPLACE FUNCTION plat.amc_versao_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  RAISE EXCEPTION 'amc_versao_imutavel' USING HINT = 'uma versão de modelo nunca muda; edite o modelo para criar outra';
END $$;
DROP TRIGGER IF EXISTS amc_modelo_versao_imutavel ON plat.amc_modelo_versao;
CREATE TRIGGER amc_modelo_versao_imutavel BEFORE UPDATE OR DELETE ON plat.amc_modelo_versao
  FOR EACH ROW EXECUTE FUNCTION plat.amc_versao_imutavel();

-- a cabeça do modelo pode mudar de versão, mas nunca deixa de apontar para uma versão do MESMO modelo, e o modelo
-- nunca é apagado fisicamente pela aplicação (apagado_em): as execuções referenciam a versão
CREATE OR REPLACE FUNCTION plat.amc_modelo_guarda() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'amc_modelo_nao_apaga' USING HINT = 'apagar = apagado_em; versões executadas ficam para a proveniência';
  END IF;
  IF NEW.tenant_id <> OLD.tenant_id OR NEW.id <> OLD.id OR NEW.criado_em <> OLD.criado_em THEN
    RAISE EXCEPTION 'amc_modelo_identidade_imutavel';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_modelo_guarda ON plat.amc_modelo;
CREATE TRIGGER amc_modelo_guarda BEFORE UPDATE OR DELETE ON plat.amc_modelo
  FOR EACH ROW EXECUTE FUNCTION plat.amc_modelo_guarda();

-- execução: a proveniência (o que rodou, sobre o quê, com que pesos e que motor) é gravada uma vez; só o estado anda.
-- Execução concluída não se apaga (os resultados são o que se audita).
CREATE OR REPLACE FUNCTION plat.amc_execucao_guarda() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  IF TG_OP = 'DELETE' THEN
    IF OLD.estado = 'concluida' THEN
      RAISE EXCEPTION 'amc_execucao_concluida_imutavel' USING HINT = 'execução concluída não se apaga';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.modelo_id <> OLD.modelo_id OR NEW.versao_hash <> OLD.versao_hash OR NEW.conjunto_id <> OLD.conjunto_id
     OR NEW.pesos <> OLD.pesos OR NEW.camadas <> OLD.camadas OR NEW.motor_versao <> OLD.motor_versao
     OR NEW.semente <> OLD.semente OR NEW.tenant_id <> OLD.tenant_id OR NEW.criado_em <> OLD.criado_em THEN
    RAISE EXCEPTION 'amc_execucao_proveniencia_imutavel'
      USING HINT = 'modelo, versão, conjunto, pesos, camadas, motor e semente de uma execução nunca mudam';
  END IF;
  IF OLD.estado = 'concluida' AND NEW.estado <> OLD.estado THEN
    RAISE EXCEPTION 'amc_execucao_concluida_imutavel';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS amc_execucao_guarda ON plat.amc_execucao;
CREATE TRIGGER amc_execucao_guarda BEFORE UPDATE OR DELETE ON plat.amc_execucao
  FOR EACH ROW EXECUTE FUNCTION plat.amc_execucao_guarda();

-- resultado e fator bruto: gravados pelo motor, nunca editados; apagados só junto da execução (cascata) enquanto ela
-- não está concluída. Depois de concluída, a execução não se apaga, logo nada disto muda.
CREATE OR REPLACE FUNCTION plat.amc_materializado_guarda() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e text;
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'amc_resultado_imutavel' USING HINT = 'resultado e fator bruto não se editam; rode outra execução';
  END IF;
  SELECT estado INTO e FROM plat.amc_execucao WHERE id = OLD.execucao_id;
  IF e = 'concluida' THEN
    RAISE EXCEPTION 'amc_resultado_imutavel' USING HINT = 'resultado de execução concluída não se apaga';
  END IF;
  RETURN OLD;
END $$;
DROP TRIGGER IF EXISTS amc_resultado_guarda ON plat.amc_resultado;
CREATE TRIGGER amc_resultado_guarda BEFORE UPDATE OR DELETE ON plat.amc_resultado
  FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_guarda();
DROP TRIGGER IF EXISTS amc_fator_bruto_guarda ON plat.amc_fator_bruto;
CREATE TRIGGER amc_fator_bruto_guarda BEFORE UPDATE OR DELETE ON plat.amc_fator_bruto
  FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_guarda();

-- ---------------------------------------------------------------- vocabulário de eventos (append; ON CONFLICT preserva)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('amc/modelo_criar', 'modelo multicritério criado (propriedades.versao_hash)'),
  ('amc/modelo_atualizar', 'modelo multicritério editado: versão nova (propriedades.versao_hash, versao_anterior)'),
  ('amc/modelo_apagar', 'modelo multicritério escondido (apagado_em); versões e execuções permanecem'),
  ('amc/conjunto_criar', 'conjunto de unidades de análise criado (propriedades.tipo, lado_m, srid_trabalho)'),
  ('amc/conjunto_apagar', 'conjunto de unidades apagado com as suas unidades'),
  ('amc/execucao_criar', 'execução registrada: versão do modelo, pesos, camadas, motor e semente fixados'),
  ('amc/execucao_apagar', 'execução não concluída apagada (registrada/falhou/cancelada)')
ON CONFLICT (nome) DO NOTHING;

-- funções auxiliares: só plat_app (mesmo padrão de 025)
REVOKE EXECUTE ON FUNCTION plat.amc_superusuario() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.amc_superusuario() TO plat_app;
