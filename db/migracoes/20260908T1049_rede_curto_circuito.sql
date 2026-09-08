-- Item L4-27-curto-circuito-e-protecao: corrente de curto por barra e coordenação por dispositivo.
-- depende: 20260907T2243_rede_subrede_resumo.sql
--
-- Três tabelas porque são três coisas com ciclos de vida diferentes:
--   `rede_curto_execucao`    — UMA linha por cálculo, com as PREMISSAS que o produziram. As premissas
--                              não são configuração da rede: são a hipótese daquele cálculo (potência de
--                              curto da fonte, fator de tensão, razão de sequência zero). Guardá-las
--                              junto é o que faz o número ser lido de novo com sentido meses depois;
--                              sem elas a corrente é um número solto.
--   `rede_curto_barra`       — uma linha por barra do alimentador, com a corrente trifásica e a
--                              fase-terra e a impedância acumulada em por unidade. A geometria NÃO é
--                              copiada: o nome da barra é `b` + o identificador do nó (regra de
--                              `opendss._barra`), e a camada lê o ponto de `plat.rede_topo_no` na hora.
--                              Copiar geometria criaria uma segunda verdade que envelhece sozinha.
--   `rede_curto_dispositivo` — uma linha por barra também, mas dizendo QUEM protege aquela barra e se a
--                              corrente calculada cai na faixa de interrupção cadastrada do dispositivo.
--                              Separada da barra porque a mesma barra pode, em outro cálculo, ter outro
--                              dispositivo a montante (a chave mudou de estado), e porque o painel de
--                              proteção lê só esta.
--
-- Cálculo NOVO da mesma subrede APAGA o anterior (uma execução viva por subrede): o resultado é derivado
-- e descartável, e manter histórico sem alguém pedir seria guardar o que ninguém lê. A trilha de auditoria
-- de que o cálculo aconteceu fica no `evento`, que é append-only.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.rede_curto_execucao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  subrede_id     uuid NOT NULL,
  subrede_nome   text NOT NULL CHECK (btrim(subrede_nome) <> '' AND length(subrede_nome) <= 200),
  -- a hipótese do cálculo, campo a campo (ver o cabeçalho de app/rede_utilidades/curto_circuito.py)
  premissas      jsonb NOT NULL CHECK (jsonb_typeof(premissas) = 'object'),
  resumo         jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(resumo) = 'object'),
  avisos         jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(avisos) = 'array'),
  barras         int NOT NULL DEFAULT 0 CHECK (barras >= 0),
  duracao_ms     int NOT NULL DEFAULT 0 CHECK (duracao_ms >= 0),
  calculado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, subrede_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_curto_execucao_rede ON plat.rede_curto_execucao (rede_id, subrede_nome);
CREATE INDEX IF NOT EXISTS ix_rede_curto_execucao_tenant ON plat.rede_curto_execucao (tenant_id);
ALTER TABLE plat.rede_curto_execucao DROP CONSTRAINT IF EXISTS rede_curto_execucao_tenant_rede_fkey;
ALTER TABLE plat.rede_curto_execucao ADD CONSTRAINT rede_curto_execucao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_curto_execucao DROP CONSTRAINT IF EXISTS rede_curto_execucao_tenant_subrede_fkey;
ALTER TABLE plat.rede_curto_execucao ADD CONSTRAINT rede_curto_execucao_tenant_subrede_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS plat.rede_curto_barra (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  execucao_id  uuid NOT NULL,
  barra        text NOT NULL CHECK (btrim(barra) <> '' AND length(barra) <= 64),
  -- nó da topologia que dá a coordenada da barra na camada; nulo quando o nome não é `b`+uuid
  no_id        uuid,
  kv           double precision CHECK (kv IS NULL OR kv > 0),
  alcancada    boolean NOT NULL,
  -- corrente NULA significa "não calculada" (barra sem caminho até a fonte ou sem tensão de base).
  -- Nunca zero: zero seria uma medida, e o que existe aqui é ausência.
  ik3_a        double precision CHECK (ik3_a IS NULL OR ik3_a >= 0),
  ik1_a        double precision CHECK (ik1_a IS NULL OR ik1_a >= 0),
  z1_pu_r      double precision,
  z1_pu_x      double precision,
  z0_pu_r      double precision,
  z0_pu_x      double precision,
  UNIQUE (tenant_id, id),
  UNIQUE (execucao_id, barra)
);
CREATE INDEX IF NOT EXISTS ix_rede_curto_barra_exec ON plat.rede_curto_barra (execucao_id);
CREATE INDEX IF NOT EXISTS ix_rede_curto_barra_tenant ON plat.rede_curto_barra (tenant_id);
ALTER TABLE plat.rede_curto_barra DROP CONSTRAINT IF EXISTS rede_curto_barra_tenant_exec_fkey;
ALTER TABLE plat.rede_curto_barra ADD CONSTRAINT rede_curto_barra_tenant_exec_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.rede_curto_execucao (tenant_id, id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS plat.rede_curto_dispositivo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  execucao_id    uuid NOT NULL,
  barra          text NOT NULL CHECK (btrim(barra) <> '' AND length(barra) <= 64),
  no_id          uuid,
  feicao_id      uuid,
  codigo         text CHECK (codigo IS NULL OR length(codigo) <= 200),
  tipo           text CHECK (tipo IS NULL OR length(tipo) <= 200),
  estado         text CHECK (estado IS NULL OR estado IN ('aberta', 'fechada')),
  ik3_a          double precision CHECK (ik3_a IS NULL OR ik3_a >= 0),
  faixa_min_a    double precision CHECK (faixa_min_a IS NULL OR faixa_min_a >= 0),
  faixa_max_a    double precision CHECK (faixa_max_a IS NULL OR faixa_max_a > 0),
  veredito       text NOT NULL CHECK (veredito IN ('interrompe', 'abaixo_da_faixa',
                 'acima_da_capacidade', 'sem_dado', 'sem_dispositivo_a_montante')),
  UNIQUE (tenant_id, id),
  UNIQUE (execucao_id, barra)
);
CREATE INDEX IF NOT EXISTS ix_rede_curto_disp_exec ON plat.rede_curto_dispositivo (execucao_id);
CREATE INDEX IF NOT EXISTS ix_rede_curto_disp_tenant ON plat.rede_curto_dispositivo (tenant_id);
ALTER TABLE plat.rede_curto_dispositivo DROP CONSTRAINT IF EXISTS rede_curto_disp_tenant_exec_fkey;
ALTER TABLE plat.rede_curto_dispositivo ADD CONSTRAINT rede_curto_disp_tenant_exec_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.rede_curto_execucao (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260907T2243.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_curto_execucao', 'rede_curto_barra', 'rede_curto_dispositivo'] LOOP
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
  ('redes/curto_circuito', 'curto-circuito calculado numa subrede (premissas, barras, vereditos)')
ON CONFLICT (nome) DO NOTHING;
