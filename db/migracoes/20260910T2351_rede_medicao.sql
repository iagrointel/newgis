-- 20260910T2351_rede_medicao (item L4-13-integracao-telemetria, 10/09/2026): telemetria ligada ao ATIVO da
-- rede de utilidades — corrente/tensão/temperatura do trafo, 100% pilha aberta, sem TimescaleDB (o portão da
-- casa proíbe TSL para dado de cliente; ver estado.json). `ativo` é só o `id` (uuid) de uma feição — de
-- `plat.rede_feicao_ponto` tipicamente, mas a tabela NUNCA referencia essa tabela por FK: a mesma decisão de
-- desenho do módulo campo (`plat.campo_alvo`, migração 20260910T2245): "visitar/medir algo que já saiu da
-- camada continua sendo um FATO". Isso também deixa a medição reutilizável fora de rede_utilidades (poste,
-- caixa, qualquer coisa com um id).
--
-- Partição NATIVA por mês (PARTITION BY RANGE (ts)), MESMO padrão de `plat.evento`
-- (db/migracoes/003_identidade_acesso.sql + 20260907T0240_ddl_concorrente_trinco.sql): função SECURITY
-- DEFINER com `pg_advisory_xact_lock` antes do DDL (a corrida é a mesma: duas leituras publicadas ao mesmo
-- tempo na virada do mês), REVOKE ALL + RLS própria em cada partição nova (defesa em profundidade contra
-- acesso direto à partição pelo nome; a consulta/gravação normal passa pelo pai e usa só a política do pai —
-- documentado: INSERT/SELECT nomeando a tabela particionada checam privilégio e RLS do PAI, não da partição).
--
-- Vocabulário de grandeza é CATÁLOGO (como plat.evento_tipo): só o backend semeia; ingestão que citar uma
-- grandeza ou unidade fora daqui é recusada com mensagem — "recusa honesta de grandeza/unidade desconhecida"
-- do portão, aqui é FK + conferência de unidade em app/rede_medicao/servico.py, nunca uma lista solta em
-- Python. `carregamento_pct` é DERIVADA (o motor de alarme escreve, ninguém publica de fora): assim a ficha
-- do ativo e o gráfico de 7 dias reusam o MESMO mecanismo de "última leitura"/"série" para mostrar o
-- carregamento, sem tabela nem rota paralela.
--
-- Sem BEGIN/COMMIT. Idempotente. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.rede_medicao_grandeza (
  codigo      text PRIMARY KEY CHECK (codigo ~ '^[a-z][a-z0-9_]{0,39}$'),
  nome        text NOT NULL,
  unidade     text NOT NULL CHECK (length(unidade) <= 10),
  tipo        text NOT NULL CHECK (tipo IN ('bruto', 'derivado')),
  descricao   text NOT NULL
);
REVOKE INSERT, UPDATE, DELETE ON plat.rede_medicao_grandeza FROM plat_app;

INSERT INTO plat.rede_medicao_grandeza(codigo, nome, unidade, tipo, descricao) VALUES
  ('corrente_a', 'Corrente de fase A', 'A', 'bruto',
   'corrente RMS na fase A do trafo, amostrada a cada 5 min (PRODIST Módulo 8)'),
  ('corrente_b', 'Corrente de fase B', 'A', 'bruto',
   'corrente RMS na fase B do trafo, amostrada a cada 5 min (PRODIST Módulo 8)'),
  ('corrente_c', 'Corrente de fase C', 'A', 'bruto',
   'corrente RMS na fase C do trafo, amostrada a cada 5 min (PRODIST Módulo 8)'),
  ('tensao_a', 'Tensão de fase A', 'V', 'bruto',
   'tensão agregada da fase A, janela de 10 min (PRODIST Módulo 8, indicadores DRP/DRC)'),
  ('tensao_b', 'Tensão de fase B', 'V', 'bruto',
   'tensão agregada da fase B, janela de 10 min (PRODIST Módulo 8, indicadores DRP/DRC)'),
  ('tensao_c', 'Tensão de fase C', 'V', 'bruto',
   'tensão agregada da fase C, janela de 10 min (PRODIST Módulo 8, indicadores DRP/DRC)'),
  ('temperatura', 'Temperatura do tanque', 'C', 'bruto',
   'temperatura do tanque/óleo do trafo em graus Celsius'),
  ('carregamento_pct', 'Carregamento aparente', '%', 'derivado',
   'S(kVA) estimado das 3 correntes de fase e da tensão nominal cadastrada, ÷ kVA de placa × 100 — escrito '
   'pelo motor de alarme (app/rede_medicao/servico.py::avaliar_alarme_carregamento), nunca publicado de fora')
ON CONFLICT (codigo) DO UPDATE SET nome = EXCLUDED.nome, unidade = EXCLUDED.unidade, tipo = EXCLUDED.tipo,
  descricao = EXCLUDED.descricao;

-- ---------------------------------------------------------------- placa do ativo (nameplate)
-- kVA/tensão nominal do trafo — não existe hoje em `rede_feicao_ponto.atributos` para redes que não vieram
-- de importação BDGD (a de demonstração desta trilha tem `atributos = '{}'`; ver handoff do item), então o
-- módulo guarda a própria config, chaveada só por `ativo` (uuid), sem depender de nenhuma tabela de feição.
CREATE TABLE IF NOT EXISTS plat.rede_medicao_ativo (
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  ativo             uuid NOT NULL,
  cod_id            text CHECK (cod_id IS NULL OR length(cod_id) <= 80),
  kva_nominal       numeric CHECK (kva_nominal IS NULL OR kva_nominal > 0),
  tensao_nominal_v  numeric CHECK (tensao_nominal_v IS NULL OR tensao_nominal_v > 0),
  atualizado_por    int REFERENCES plat.usuario(id),
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, ativo)
);
CREATE INDEX IF NOT EXISTS ix_rede_medicao_ativo_cod_id ON plat.rede_medicao_ativo (tenant_id, cod_id);

-- ---------------------------------------------------------------- leituras (particionada por mês)
CREATE TABLE IF NOT EXISTS plat.rede_medicao (
  id            bigserial,
  tenant_id     int NOT NULL,
  ativo         uuid NOT NULL,
  cod_id        text CHECK (cod_id IS NULL OR length(cod_id) <= 80),
  ts            timestamptz NOT NULL,
  fonte         text NOT NULL CHECK (fonte ~ '^[a-z][a-z0-9_]{0,39}$'),
  grandeza      text NOT NULL REFERENCES plat.rede_medicao_grandeza(codigo),
  valor         double precision NOT NULL,
  unidade       text NOT NULL,
  leitura       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(leitura) = 'object'),
  recebido_em   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, ts),
  UNIQUE (tenant_id, ativo, grandeza, ts)
) PARTITION BY RANGE (ts);
CREATE INDEX IF NOT EXISTS ix_rede_medicao_busca ON plat.rede_medicao (tenant_id, ativo, grandeza, ts DESC);
ALTER TABLE plat.rede_medicao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_medicao_ler ON plat.rede_medicao;
CREATE POLICY p_rede_medicao_ler ON plat.rede_medicao FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_rede_medicao_inserir ON plat.rede_medicao;
CREATE POLICY p_rede_medicao_inserir ON plat.rede_medicao FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino());
GRANT SELECT, INSERT ON plat.rede_medicao TO plat_app;

CREATE OR REPLACE FUNCTION plat.rede_medicao_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
  fim := (ini + interval '1 month')::date;
  nome := format('rede_medicao_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('particao:plat.' || nome));
    IF to_regclass('plat.' || nome) IS NULL THEN
      EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.rede_medicao FOR VALUES FROM (%L) TO (%L)',
                      nome, ini, fim);
      EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
      EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
      EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())',
                      nome, nome);
    END IF;
  END IF;
  RETURN nome;
END $$;
GRANT EXECUTE ON FUNCTION plat.rede_medicao_particao_garantir(date) TO plat_app;

-- partições do mês corrente e do próximo (item 1 do pedido); a tarefa periódica (app/rede_medicao/tarefas.py,
-- pausada até o operador ligar — mesmo padrão de agenda 'ativa=false' documentado em 004_jobs.sql: "ativa é
-- do operador") cria as seguintes antes da virada.
SELECT plat.rede_medicao_particao_garantir(date_trunc('month', now())::date);
SELECT plat.rede_medicao_particao_garantir((date_trunc('month', now()) + interval '1 month')::date);

-- agenda do periódico já PAUSADA (ativa=false, proxima_em NULL): inserida ANTES de o worker sincronizar
-- (app/jobs/agenda.py::sincronizar_periodicos faz UPDATE ... SET proxima_em só quando o cron muda OU quando
-- `proxima_em IS NULL AND ativa` — com ativa=false aqui, o sync nunca acorda sozinho; o operador ativa com
-- UPDATE plat.agenda SET ativa=true WHERE nome='rede_medicao: criar partições futuras' e o PRÓXIMO sync liga
-- proxima_em, sem precisar editar SQL nenhuma). Idempotente por UNIQUE(tenant_id, nome); DO NOTHING para
-- nunca reativar algo que o operador já desligou de propósito.
INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron, fuso, ativa, proxima_em)
SELECT t.id, NULL, 'rede_medicao: criar partições futuras', 'rede_medicao.particoes_criar', '{}'::jsonb,
       '0 5 1 * *', 'America/Sao_Paulo', false, NULL
FROM plat.tenant t WHERE t.slug = 'plataforma'
ON CONFLICT (tenant_id, nome) DO NOTHING;

-- ---------------------------------------------------------------- alarme declarado (estado, para disparar só na
-- transição — repetir o cheque a cada ingestão não pode reabrir um evento por leitura)
CREATE TABLE IF NOT EXISTS plat.rede_medicao_alarme_estado (
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  ativo          uuid NOT NULL,
  tipo           text NOT NULL CHECK (tipo IN ('carregamento_30min')),
  disparado      boolean NOT NULL DEFAULT false,
  desde          timestamptz,
  ultimo_valor   double precision,
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, ativo, tipo)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_medicao_ativo', 'rede_medicao_alarme_estado'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_ler ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_ler ON plat.%1$s FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_inserir ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_inserir ON plat.%1$s FOR INSERT TO plat_app '
      'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_alterar ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_alterar ON plat.%1$s FOR UPDATE TO plat_app '
      'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_apagar ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_apagar ON plat.%1$s FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------- privilégio novo (mesmo padrão da migração
-- 015_privilegio_jobs_ver: vocabulário +1, espelho em app/auth/privilegios.py, teste
-- tests/api/test_privilegios_declarados.py confere as duas listas)
INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('rede.medir', 'rede', 'publicar leitura de telemetria e cadastrar a placa (kVA/tensão nominal) de um ativo',
   false)
ON CONFLICT (nome) DO UPDATE SET grupo = EXCLUDED.grupo, descricao = EXCLUDED.descricao,
                                 administrativo = EXCLUDED.administrativo;
INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES
  ('campo',  'rede.medir'),
  ('editor', 'rede.medir'),
  ('admin',  'rede.medir')
ON CONFLICT (perfil, privilegio) DO NOTHING;
INSERT INTO plat.papel_privilegio(papel_id, privilegio)
SELECT papel_id, 'rede.medir' FROM plat.papel_privilegio WHERE privilegio = 'rede.editar'
ON CONFLICT DO NOTHING;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('rede_medicao/ativo_configurar', 'rede_medicao (L4-13): placa (kVA/tensão nominal) de um ativo cadastrada'),
  ('rede_medicao/alarme_disparado', 'rede_medicao (L4-13): alarme de carregamento > 100% por 30 min disparado'),
  ('rede_medicao/alarme_resolvido', 'rede_medicao (L4-13): alarme de carregamento resolvido (voltou a ≤ 100%)')
ON CONFLICT (nome) DO NOTHING;
