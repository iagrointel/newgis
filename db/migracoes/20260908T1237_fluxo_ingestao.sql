-- 20260908T1237_fluxo_ingestao: entrada de eventos em tempo real (item L2-14-a-ingestao-de-fluxos;
-- decisão C14 de laco/decomposicao/L2_CONCEITO.md). Equivalente de feed do ArcGIS Velocity/GeoEvent.
--
-- Três tabelas:
--   plat.fluxo_fonte   -- a FONTE (objeto do inquilino): tipo em vocabulário fechado, config, mapeamento de
--                         campos, filtro de entrada, teto de eventos por segundo, estado ativa/pausada.
--   plat.fluxo_metrica -- contadores por fonte (recebidos, aceitos, descartados por motivo, atraso), escritos
--                         pelo processo plat-fluxo em lote; uma linha por fonte, nunca série temporal (o
--                         histórico de eventos já é a série; contador é estado corrente).
--   plat.fluxo_evento  -- o EVENTO, particionado nativamente por MÊS de recebido_em (C14: nada de TimescaleDB,
--                         cuja compressão e agregado contínuo são TSL — DOC.md 22), BRIN em recebido_em,
--                         GIST em geom, índice por (fonte_id, recebido_em). Expurgo por DROP de partição.
--
-- Por que o evento NÃO ganha uma tabela por fonte com colunas tipadas ("esquema de destino" como DDL): cada
-- fonte exigiria CREATE TABLE + política de RLS + partição + índice próprios, criados por uma role com DDL a
-- partir de dado do inquilino. O esquema de destino é GERADO e guardado em `fluxo_fonte.esquema_destino`
-- (nome + tipo por campo, derivado do mapeamento) e os valores já convertidos vão em `atributos jsonb`; quem
-- consome (camada, painel, API) lê o esquema declarado, não adivinha o tipo. Ver docs/adr.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.fluxo_fonte (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  -- vocabulário fechado; a MESMA lista está em app/fluxo/tipos.py (as duas mudam juntas, como conexao/limites)
  tipo               text NOT NULL CHECK (tipo IN (
                       'http', 'websocket_servidor', 'websocket_cliente', 'mqtt', 'sondagem',
                       'ais', 'gps_frota', 'sensor'
                     )),
  nome               text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  estado             text NOT NULL DEFAULT 'ativa' CHECK (estado IN ('ativa', 'pausada')),
  config             jsonb NOT NULL DEFAULT '{}'::jsonb,
  mapeamento         jsonb NOT NULL DEFAULT '{}'::jsonb,
  esquema_destino    jsonb NOT NULL DEFAULT '[]'::jsonb,   -- gerado do mapeamento, nunca escrito à mão
  filtro             text CHECK (filtro IS NULL OR length(filtro) <= 20000),
  limite_eventos_s   int NOT NULL DEFAULT 1000 CHECK (limite_eventos_s BETWEEN 1 AND 100000),
  credencial_cifrada text,   -- AES-GCM 'encconexao:v1:' (app/conexao/credencial.py); NUNCA texto puro
  dono_id            int NOT NULL REFERENCES plat.usuario(id),
  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_fluxo_fonte_tenant ON plat.fluxo_fonte (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fluxo_fonte_nome ON plat.fluxo_fonte (tenant_id, lower(nome));

CREATE OR REPLACE FUNCTION plat.tg_fluxo_fonte_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS fluxo_fonte_atualizado_em ON plat.fluxo_fonte;
CREATE TRIGGER fluxo_fonte_atualizado_em BEFORE UPDATE ON plat.fluxo_fonte
  FOR EACH ROW EXECUTE FUNCTION plat.tg_fluxo_fonte_atualizado_em();

ALTER TABLE plat.fluxo_fonte ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_fluxo_fonte_ler ON plat.fluxo_fonte;
CREATE POLICY p_fluxo_fonte_ler ON plat.fluxo_fonte FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_fluxo_fonte_inserir ON plat.fluxo_fonte;
CREATE POLICY p_fluxo_fonte_inserir ON plat.fluxo_fonte FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND dono_id = plat.usuario_atual() AND plat.usuario_do_inquilino());
DROP POLICY IF EXISTS p_fluxo_fonte_alterar ON plat.fluxo_fonte;
CREATE POLICY p_fluxo_fonte_alterar ON plat.fluxo_fonte FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')))
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_fluxo_fonte_apagar ON plat.fluxo_fonte;
CREATE POLICY p_fluxo_fonte_apagar ON plat.fluxo_fonte FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')));

-- ---------------------------------------------------------------- métrica por fonte
CREATE TABLE IF NOT EXISTS plat.fluxo_metrica (
  fonte_id             uuid PRIMARY KEY REFERENCES plat.fluxo_fonte(id) ON DELETE CASCADE,
  tenant_id            int NOT NULL REFERENCES plat.tenant(id),
  recebidos            bigint NOT NULL DEFAULT 0,
  aceitos              bigint NOT NULL DEFAULT 0,
  descartados_filtro   bigint NOT NULL DEFAULT 0,
  descartados_limite   bigint NOT NULL DEFAULT 0,
  descartados_invalido bigint NOT NULL DEFAULT 0,
  -- bigint, não int: o atraso é (recebimento - tempo do evento) e uma carga histórica legítima tem meses
  -- de atraso, o que estoura int4 em 24 dias. Achado no teste do receptor, com um evento de janeiro.
  atraso_ms_ultimo     bigint,
  atraso_ms_p50        bigint,
  ultimo_evento_em     timestamptz,
  atualizado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_fluxo_metrica_tenant ON plat.fluxo_metrica (tenant_id);
ALTER TABLE plat.fluxo_metrica ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_fluxo_metrica ON plat.fluxo_metrica;
CREATE POLICY p_fluxo_metrica ON plat.fluxo_metrica FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- evento (partição nativa por mês)
CREATE TABLE IF NOT EXISTS plat.fluxo_evento (
  tenant_id    int NOT NULL,
  fonte_id     uuid NOT NULL,
  rastro_id    text,
  tempo_evento timestamptz NOT NULL,
  recebido_em  timestamptz NOT NULL DEFAULT now(),
  geom         geometry(Point, 4326),
  atributos    jsonb NOT NULL DEFAULT '{}'::jsonb
) PARTITION BY RANGE (recebido_em);

-- Sem chave estrangeira para fluxo_fonte: uma FK em tabela particionada de alto volume custa uma verificação
-- por linha no COPY, e a fonte é apagada com o expurgo dos eventos pela rotina de apagar (app/fluxo/rotas.py).
CREATE INDEX IF NOT EXISTS ix_fluxo_evento_recebido ON plat.fluxo_evento USING brin (recebido_em);
CREATE INDEX IF NOT EXISTS ix_fluxo_evento_fonte ON plat.fluxo_evento (fonte_id, recebido_em DESC);
CREATE INDEX IF NOT EXISTS ix_fluxo_evento_geom ON plat.fluxo_evento USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_fluxo_evento_rastro ON plat.fluxo_evento (fonte_id, rastro_id, recebido_em DESC);

ALTER TABLE plat.fluxo_evento ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_fluxo_evento_ler ON plat.fluxo_evento;
CREATE POLICY p_fluxo_evento_ler ON plat.fluxo_evento FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_fluxo_evento_inserir ON plat.fluxo_evento;
CREATE POLICY p_fluxo_evento_inserir ON plat.fluxo_evento FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_fluxo_evento_apagar ON plat.fluxo_evento;
CREATE POLICY p_fluxo_evento_apagar ON plat.fluxo_evento FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual());

-- Partição do mês de `quando` (idempotente; devolve o nome). A partição DEFAULT abaixo garante que nenhum
-- evento se perca se o relógio virar o mês antes de a rotina periódica criar a próxima.
CREATE OR REPLACE FUNCTION plat.fluxo_particao_garantir(quando timestamptz DEFAULT now()) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
  ini date := date_trunc('month', quando AT TIME ZONE 'UTC')::date;
  fim date := (date_trunc('month', quando AT TIME ZONE 'UTC') + interval '1 month')::date;
  nome text := 'fluxo_evento_' || to_char(ini, 'YYYYMM');
BEGIN
  IF to_regclass('plat.' || nome) IS NULL THEN
    EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.fluxo_evento FOR VALUES FROM (%L) TO (%L)',
                   nome, ini, fim);
  END IF;
  RETURN nome;
END $$;

DO $$
BEGIN
  IF to_regclass('plat.fluxo_evento_resto') IS NULL THEN
    CREATE TABLE plat.fluxo_evento_resto PARTITION OF plat.fluxo_evento DEFAULT;
  END IF;
END $$;
SELECT plat.fluxo_particao_garantir(now());
SELECT plat.fluxo_particao_garantir(now() + interval '1 month');

GRANT SELECT, INSERT, DELETE ON plat.fluxo_evento TO plat_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.fluxo_fonte, plat.fluxo_metrica TO plat_app;
GRANT EXECUTE ON FUNCTION plat.fluxo_particao_garantir(timestamptz) TO plat_app;

-- O processo plat-fluxo atende TODOS os inquilinos e conecta como `plat_app`, que sob RLS não enxerga
-- nada sem contexto de inquilino — nem `plat.tenant`, nem `plat.fluxo_fonte`. Para saber QUAIS inquilinos
-- têm fonte (e então ler a lista de cada um já com o contexto certo), existe esta função SECURITY DEFINER,
-- no mesmo padrão de `plat.auth_login`/`plat.auth_token`: ela devolve SÓ os identificadores de inquilino que
-- têm ao menos uma fonte de fluxo — nenhum nome, nenhuma configuração, nenhuma credencial. Sem ela o
-- processo teria de conectar como uma role sem RLS, que é justamente o que o isolamento não admite.
CREATE OR REPLACE FUNCTION plat.fluxo_inquilinos() RETURNS SETOF int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS
  $$ SELECT DISTINCT tenant_id FROM plat.fluxo_fonte $$;
REVOKE EXECUTE ON FUNCTION plat.fluxo_inquilinos() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.fluxo_inquilinos() TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('fluxos/criar', 'fonte de fluxo criada (tipo, nome)'),
  ('fluxos/editar', 'fonte de fluxo editada (campos alterados)'),
  ('fluxos/apagar', 'fonte de fluxo apagada (nome; eventos expurgados junto)'),
  ('fluxos/pausar', 'fonte de fluxo pausada (o receptor passa a guardar em buffer)'),
  ('fluxos/retomar', 'fonte de fluxo retomada (o buffer é drenado)'),
  ('fluxos/expurgar', 'eventos de uma fonte apagados por corte de tempo')
ON CONFLICT (nome) DO NOTHING;
