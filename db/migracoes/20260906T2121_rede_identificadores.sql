-- 20260906T2121_rede_identificadores: identidade de ativo da rede de utilidades
-- (item L4-28-identificadores-e-numeracao; ADR docs/adr/20260906T2121-rede-identificadores.md).
--
-- Três garantias, todas no banco (nunca só na aplicação):
--   1. global_id (uuid) interno e estável: nunca muda, nem quando o código externo é renomeado;
--   2. código externo do cliente (ex.: COD_ID da BDGD) único por REDE — índice único parcial;
--   3. numeração automática por TIPO de ativo, com faixa reservada por usuário (o conceito que a Esri
--      chama "unit identifiers"): quem trabalha desconectado reserva um bloco de N números e consome em
--      campo sem colidir com ninguém. O contador de cada tipo anda numa linha só (plat.rede_numeracao),
--      sempre para a frente: reservar N números FAZ o contador pular N, então a criação conectada nunca
--      recebe um número que já foi entregue a uma faixa — e duas reservas concorrentes recebem blocos
--      disjuntos, porque a alocação é INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING (trava de linha).
--
-- FKs compostas (tenant_id, alvo_id) em TUDO, como manda a trava tests/api/test_fk_composta_por_inquilino.py
-- (achado A1 do L4-01-a). plat.usuario ganha UNIQUE (tenant_id, id) — trivial, id já é chave — para servir
-- de porta às FKs de dono da faixa / criador do ativo / autor da renomeação.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- porta para FK composta apontando para plat.usuario (mesmo padrão de 20260906T1815)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'usuario' AND c.conname = 'usuario_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT usuario_tenant_id_id_key UNIQUE (tenant_id, id);
  END IF;
END $$;

-- contador da numeração automática: uma linha por tipo de ativo; `proximo` é o primeiro número livre.
-- A alocação de um bloco de N números é uma só instrução (INSERT ... ON CONFLICT DO UPDATE RETURNING),
-- que trava a linha do tipo até o fim da transação — duas alocações concorrentes nunca leem o mesmo valor.
CREATE TABLE IF NOT EXISTS plat.rede_numeracao (
  tenant_id  int    NOT NULL REFERENCES plat.tenant(id),
  tipo_id    uuid   NOT NULL,
  proximo    bigint NOT NULL DEFAULT 1 CHECK (proximo >= 1),
  PRIMARY KEY (tenant_id, tipo_id)
);
ALTER TABLE plat.rede_numeracao DROP CONSTRAINT IF EXISTS rede_numeracao_tenant_tipo_fkey;
ALTER TABLE plat.rede_numeracao ADD CONSTRAINT rede_numeracao_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- faixa reservada: bloco [inicio, fim] do espaço de numeração do tipo, de propriedade de UM usuário,
-- para criação desconectada. `consumidos` conta quantos números da faixa já viraram ativo; a faixa
-- "esgotada" é a que tem consumidos = fim - inicio + 1; `liberada_em` fecha a faixa antes disso
-- (o que sobrou não volta ao contador — o contador nunca anda para trás).
CREATE TABLE IF NOT EXISTS plat.rede_faixa (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int  NOT NULL REFERENCES plat.tenant(id),
  rede_id     uuid NOT NULL,
  tipo_id     uuid NOT NULL,
  usuario_id  int  NOT NULL,
  inicio      bigint NOT NULL CHECK (inicio >= 1),
  fim         bigint NOT NULL CHECK (fim >= inicio),
  consumidos  int  NOT NULL DEFAULT 0,
  criado_em   timestamptz NOT NULL DEFAULT now(),
  liberada_em timestamptz,
  CHECK (consumidos >= 0 AND consumidos <= fim - inicio + 1)
);
ALTER TABLE plat.rede_faixa DROP CONSTRAINT IF EXISTS rede_faixa_tenant_rede_fkey;
ALTER TABLE plat.rede_faixa ADD CONSTRAINT rede_faixa_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_faixa DROP CONSTRAINT IF EXISTS rede_faixa_tenant_tipo_fkey;
ALTER TABLE plat.rede_faixa ADD CONSTRAINT rede_faixa_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_faixa DROP CONSTRAINT IF EXISTS rede_faixa_tenant_usuario_fkey;
ALTER TABLE plat.rede_faixa ADD CONSTRAINT rede_faixa_tenant_usuario_fkey
  FOREIGN KEY (tenant_id, usuario_id) REFERENCES plat.usuario (tenant_id, id);
CREATE INDEX IF NOT EXISTS ix_rede_faixa_tenant ON plat.rede_faixa (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_faixa_tipo ON plat.rede_faixa (tipo_id);
-- duas faixas ABERTAS do mesmo tipo nunca se sobrepõem: a alocação atômica do contador já garante por
-- construção; esta EXCLUSÃO é a prova independente no banco (int8range + btree_gist, já instalado na casa)
ALTER TABLE plat.rede_faixa DROP CONSTRAINT IF EXISTS ex_rede_faixa_sem_sobreposicao;
ALTER TABLE plat.rede_faixa ADD CONSTRAINT ex_rede_faixa_sem_sobreposicao
  EXCLUDE USING gist (tipo_id WITH =, int8range(inicio, fim, '[]') WITH &&) WHERE (liberada_em IS NULL);

-- identidade do ativo: global_id estável + número automático por tipo + código externo único por rede.
-- A linha NÃO é a feição (a feição vive na camada, item L4-01-b); é o registro de identidade ao qual a
-- feição aponta pelo global_id.
CREATE TABLE IF NOT EXISTS plat.rede_ativo (
  global_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       int  NOT NULL REFERENCES plat.tenant(id),
  rede_id         uuid NOT NULL,
  tipo_id         uuid NOT NULL,
  numero          bigint NOT NULL CHECK (numero >= 1),
  codigo_externo  text CHECK (codigo_externo IS NULL OR (btrim(codigo_externo) <> '' AND length(codigo_externo) <= 100)),
  criado_por      int  NOT NULL,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.rede_ativo DROP CONSTRAINT IF EXISTS rede_ativo_tenant_rede_fkey;
ALTER TABLE plat.rede_ativo ADD CONSTRAINT rede_ativo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_ativo DROP CONSTRAINT IF EXISTS rede_ativo_tenant_tipo_fkey;
ALTER TABLE plat.rede_ativo ADD CONSTRAINT rede_ativo_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_ativo DROP CONSTRAINT IF EXISTS rede_ativo_tenant_criador_fkey;
ALTER TABLE plat.rede_ativo ADD CONSTRAINT rede_ativo_tenant_criador_fkey
  FOREIGN KEY (tenant_id, criado_por) REFERENCES plat.usuario (tenant_id, id);
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'rede_ativo' AND c.conname = 'rede_ativo_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.rede_ativo ADD CONSTRAINT rede_ativo_tenant_id_id_key UNIQUE (tenant_id, global_id);
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_ativo_tipo_numero ON plat.rede_ativo (tipo_id, numero);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_ativo_codigo_externo
  ON plat.rede_ativo (rede_id, codigo_externo) WHERE codigo_externo IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_rede_ativo_tenant ON plat.rede_ativo (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_ativo_rede ON plat.rede_ativo (rede_id);

DROP TRIGGER IF EXISTS rede_ativo_atualizado_em ON plat.rede_ativo;
CREATE TRIGGER rede_ativo_atualizado_em BEFORE UPDATE ON plat.rede_ativo
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_atualizado_em();

-- histórico de renomeação do código externo: o global_id nunca muda; cada troca grava uma linha
CREATE TABLE IF NOT EXISTS plat.rede_ativo_renomeacao (
  id                       bigserial PRIMARY KEY,
  tenant_id                int  NOT NULL REFERENCES plat.tenant(id),
  ativo_global_id          uuid NOT NULL,
  codigo_externo_anterior  text,
  codigo_externo_novo      text NOT NULL,
  renomeado_por            int  NOT NULL,
  renomeado_em             timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.rede_ativo_renomeacao DROP CONSTRAINT IF EXISTS rede_ativo_renomeacao_tenant_ativo_fkey;
ALTER TABLE plat.rede_ativo_renomeacao ADD CONSTRAINT rede_ativo_renomeacao_tenant_ativo_fkey
  FOREIGN KEY (tenant_id, ativo_global_id) REFERENCES plat.rede_ativo (tenant_id, global_id) ON DELETE CASCADE;
ALTER TABLE plat.rede_ativo_renomeacao DROP CONSTRAINT IF EXISTS rede_ativo_renomeacao_tenant_autor_fkey;
ALTER TABLE plat.rede_ativo_renomeacao ADD CONSTRAINT rede_ativo_renomeacao_tenant_autor_fkey
  FOREIGN KEY (tenant_id, renomeado_por) REFERENCES plat.usuario (tenant_id, id);
CREATE INDEX IF NOT EXISTS ix_rede_ativo_renomeacao_tenant ON plat.rede_ativo_renomeacao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_ativo_renomeacao_ativo ON plat.rede_ativo_renomeacao (ativo_global_id);

-- RLS: o mesmo padrão de plat.rede_* (migração 20260906T1553)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_numeracao','rede_faixa','rede_ativo','rede_ativo_renomeacao'] LOOP
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
-- histórico é por bigserial: a sequência precisa de GRANT à parte
GRANT USAGE, SELECT ON SEQUENCE plat.rede_ativo_renomeacao_id_seq TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/ativos/criar', 'ativo de rede criado (tipo, número automático, código externo)'),
  ('redes/ativos/renomear', 'código externo de ativo renomeado (anterior, novo; global_id preservado)'),
  ('redes/faixas/reservar', 'faixa de numeração reservada (tipo, início, fim, usuário)'),
  ('redes/faixas/liberar', 'faixa de numeração liberada (tipo, início, fim, números consumidos)')
ON CONFLICT (nome) DO NOTHING;
