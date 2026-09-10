-- 20260906T1620_auditoria — trilha de auditoria de negócio (item L7-20-trilha-auditoria).
--
-- O que já existia e por que não bastava:
--   * `plat.log_acesso` (003, seção 12.8) responde "que requisição entrou": método, rota, status, bytes,
--     tempo. Não diz O QUE MUDOU e é retido por 12 meses em partição mensal, que se derruba inteira.
--   * `plat.evento` (003, seção 12.7) responde "que ato de negócio aconteceu", mas é PARTICIONADO POR MÊS e
--     o expurgo (`plat.evento_expurgar`) é `DROP TABLE` da partição — não há como reter por inquilino, e não
--     existe trigger que impeça UPDATE/DELETE: a proteção é só `REVOKE` para `plat_app`.
--   * Nenhuma rota de escrita SEM evento declarado (POST /api/arquivos, POST /api/rota, /api/matriz,
--     /api/isocrona, POST /api/eu/2fa/iniciar — ver tests/api/eventos_esperados.py) deixa rastro de negócio.
--
-- Esta migração cria a trilha de auditoria propriamente dita:
--   1. `plat.auditoria`: tabela append-only, NÃO particionada (a retenção é por inquilino, logo o expurgo é
--      por linha, não por partição), com RLS por `tenant_id`.
--   2. Imutabilidade por TRIGGER, além do REVOKE: UPDATE/DELETE/TRUNCATE levantam `auditoria_imutavel`. A
--      única exceção é o expurgo, que precisa de DUAS condições ao mesmo tempo — a marca de transação
--      `plat.auditoria_expurgo` E ser o DONO da tabela. `plat_app` consegue pôr a marca (`set_config` é livre)
--      mas nunca é o dono, então continua barrado; e o dono sem a marca também é barrado.
--   3. Escrita na MESMA transação do ato, por dois caminhos que se completam:
--      a) trigger `AFTER INSERT` em `plat.evento` (propagada às partições — PostgreSQL >= 13): todo evento de
--         domínio já registrado pelas rotas vira linha de auditoria sem tocar em nenhuma rota;
--      b) `plat.auditoria_cobrir()`, chamada por `app/db.py` no fim de toda transação de requisição de
--         ESCRITA: se aquele `req_id` ainda não deixou linha nenhuma, grava a linha de cobertura. É o que
--         torna verdadeira, mecanicamente, a cláusula "toda rota de escrita do OpenAPI gera linha", inclusive
--         para as rotas que por decisão não têm evento de domínio.
--   4. Retenção CONFIGURÁVEL POR INQUILINO (`tenant.config.auditoria_retencao_dias`, padrão 730 = 2 anos,
--      piso de 90 dias) com expurgo por pg_cron.
--   5. Exportação: `plat.auditoria_exportar` devolve o MESMO conjunto que a listagem, para que a contagem da
--      exportação bata com a contagem em tabela.
--
-- ⚠ pg_cron é recurso GLOBAL da máquina (ver docs/adr/0031-trilha-auditoria.md, seção "Regra para quem usar
-- pg_cron"): o nome do job é derivado de `current_schema()`, nunca constante, senão o job de uma trilha de
-- teste expurga a auditoria de produção. Mesmo defeito de fila/trinco/cota sem dimensão de inquilino.
--
-- Idempotente. Sem BEGIN/COMMIT (o aplicador envolve em transação).

-- ---------------------------------------------------------------- 1. tabela
CREATE TABLE IF NOT EXISTS plat.auditoria (
  id             bigserial PRIMARY KEY,
  em             timestamptz NOT NULL DEFAULT now(),
  tenant_id      int         NOT NULL,
  ator_id        int,                       -- plat.usuario.id do ator (NULL = sem sessão, ex. token puro)
  ator_login     text,                      -- congelado no momento do ato: o usuário pode ser apagado depois
  token_id       int,                       -- plat.token_servico.id quando o ato veio por token de serviço
  acao           text        NOT NULL,      -- vocabulário de plat.evento_tipo quando vem de evento
  recurso_tipo   text,
  recurso_id     text,
  antes          jsonb,                     -- resumo, nunca o registro inteiro e nunca segredo
  depois         jsonb,
  req_id         text,
  ip             text,
  metodo         text,
  rota           text,
  origem         text        NOT NULL DEFAULT 'evento'
                 CHECK (origem IN ('evento', 'cobertura', 'aplicacao'))
);
COMMENT ON TABLE plat.auditoria IS
  'Trilha de auditoria de negócio (item L7-20): append-only, RLS por inquilino, retenção por inquilino.';
COMMENT ON COLUMN plat.auditoria.origem IS
  'evento = trigger sobre plat.evento; cobertura = fim de transação de escrita sem evento; aplicacao = chamada explícita da API (exportação, leitura de camada pessoal).';

CREATE INDEX IF NOT EXISTS ix_auditoria_tenant_em    ON plat.auditoria (tenant_id, em DESC);
CREATE INDEX IF NOT EXISTS ix_auditoria_tenant_ator  ON plat.auditoria (tenant_id, ator_id, em DESC);
CREATE INDEX IF NOT EXISTS ix_auditoria_tenant_acao  ON plat.auditoria (tenant_id, acao, em DESC);
CREATE INDEX IF NOT EXISTS ix_auditoria_req          ON plat.auditoria (req_id) WHERE req_id IS NOT NULL;

ALTER TABLE plat.auditoria ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_auditoria ON plat.auditoria;
CREATE POLICY p_auditoria ON plat.auditoria FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual());
GRANT SELECT ON plat.auditoria TO plat_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON plat.auditoria FROM plat_app;
REVOKE ALL ON SEQUENCE plat.auditoria_id_seq FROM plat_app;

-- ---------------------------------------------------------------- 2. imutabilidade por trigger
-- Duas condições ao mesmo tempo. A marca de transação sozinha não basta: `plat_app` pode chamar set_config.
-- Ser o dono sozinho também não basta: um DELETE distraído como postgres teria de passar pela marca.
CREATE OR REPLACE FUNCTION plat.tg_auditoria_imutavel() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE dono text;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO dono FROM pg_class c WHERE c.oid = 'plat.auditoria'::regclass;
  IF coalesce(current_setting('plat.auditoria_expurgo', true), '') = '1' AND current_user = dono THEN
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  RAISE EXCEPTION 'auditoria_imutavel'
    USING HINT = 'plat.auditoria é append-only: só plat.auditoria_expurgar(), como dono da tabela, remove linha';
END $$;

DROP TRIGGER IF EXISTS auditoria_imutavel ON plat.auditoria;
CREATE TRIGGER auditoria_imutavel BEFORE UPDATE OR DELETE ON plat.auditoria
  FOR EACH ROW EXECUTE FUNCTION plat.tg_auditoria_imutavel();

CREATE OR REPLACE FUNCTION plat.tg_auditoria_sem_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'auditoria_imutavel' USING HINT = 'TRUNCATE em plat.auditoria é proibido';
END $$;
DROP TRIGGER IF EXISTS auditoria_sem_truncate ON plat.auditoria;
CREATE TRIGGER auditoria_sem_truncate BEFORE TRUNCATE ON plat.auditoria
  FOR EACH STATEMENT EXECUTE FUNCTION plat.tg_auditoria_sem_truncate();

-- ---------------------------------------------------------------- 3. escrita
-- Contexto da requisição: `app/db.py` grava req_id/ip/token_id/método/rota em GUC de transação a cada
-- preparação de cursor, do mesmo jeito que já grava plat.tenant_id/plat.usuario_id. Sem requisição (worker,
-- psql) as GUC vêm vazias e as colunas ficam NULL.
-- p_nome é o sufixo ('req_id', 'ip', ...), nunca a chave inteira: o reescritor de schema das trilhas
-- (laco/trilha_reescrever.py) só poupa o `plat` que vem colado em current_setting('/set_config(', então
-- passar 'plat.req_id' como argumento viraria 'plat_t<trilha>.req_id' e nunca casaria com quem gravou.
CREATE OR REPLACE FUNCTION plat.req_guc(p_nome text) RETURNS text
LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('plat.' || p_nome, true), '') $$;

CREATE OR REPLACE FUNCTION plat.auditoria_registrar(
  p_acao text, p_recurso_tipo text DEFAULT NULL, p_recurso_id text DEFAULT NULL,
  p_antes jsonb DEFAULT NULL, p_depois jsonb DEFAULT NULL,
  p_origem text DEFAULT 'aplicacao', p_tenant int DEFAULT NULL, p_ator int DEFAULT NULL,
  p_ip text DEFAULT NULL, p_req_id text DEFAULT NULL, p_em timestamptz DEFAULT NULL) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE novo bigint; t int; a int;
BEGIN
  t := coalesce(p_tenant, plat.tenant_atual());
  IF t IS NULL THEN
    RAISE EXCEPTION 'auditoria_sem_contexto' USING HINT = 'auditoria_registrar exige o contexto do inquilino';
  END IF;
  a := coalesce(p_ator, plat.usuario_atual());
  INSERT INTO plat.auditoria(em, tenant_id, ator_id, ator_login, token_id, acao, recurso_tipo, recurso_id,
                             antes, depois, req_id, ip, metodo, rota, origem)
  VALUES (coalesce(p_em, now()), t, a,
          (SELECT u.login FROM plat.usuario u WHERE u.id = a),
          plat.req_guc('token_id')::int,
          p_acao, p_recurso_tipo, p_recurso_id, p_antes, p_depois,
          coalesce(p_req_id, plat.req_guc('req_id')),
          coalesce(p_ip, plat.req_guc('ip')),
          plat.req_guc('metodo'), plat.req_guc('rota'), p_origem)
  RETURNING id INTO novo;
  RETURN novo;
END $$;

-- 3a. todo evento de domínio vira linha de auditoria, na MESMA transação do ato (é a mesma instrução).
-- `propriedades.antes/depois` é o formato que as rotas já usam (ver tests/api/test_eventos.py); quando não
-- houver esse par, as propriedades inteiras vão para `depois` — nunca se perde o que a rota narrou.
CREATE OR REPLACE FUNCTION plat.tg_evento_auditoria() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE p jsonb := coalesce(NEW.propriedades, '{}'::jsonb);
BEGIN
  INSERT INTO plat.auditoria(em, tenant_id, ator_id, ator_login, token_id, acao, recurso_tipo, recurso_id,
                             antes, depois, req_id, ip, metodo, rota, origem)
  VALUES (NEW.em, NEW.tenant_id, NEW.ator_id,
          (SELECT u.login FROM plat.usuario u WHERE u.id = NEW.ator_id),
          plat.req_guc('token_id')::int,
          NEW.tipo, NEW.alvo_tipo, NEW.alvo_id,
          p -> 'antes',
          CASE WHEN p ? 'depois' THEN p -> 'depois'
               WHEN p = '{}'::jsonb THEN NULL
               WHEN p ? 'antes' THEN NULL
               ELSE p END,
          coalesce(NEW.req_id, plat.req_guc('req_id')),
          coalesce(NEW.ip, plat.req_guc('ip')),
          plat.req_guc('metodo'), plat.req_guc('rota'), 'evento');
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS evento_auditoria ON plat.evento;
CREATE TRIGGER evento_auditoria AFTER INSERT ON plat.evento
  FOR EACH ROW EXECUTE FUNCTION plat.tg_evento_auditoria();

-- 3b. cobertura: fim de transação de requisição de ESCRITA sem nenhuma linha para aquele req_id.
-- Devolve o id da linha criada, ou NULL quando não havia o que cobrir (já tinha linha, ou sem contexto).
CREATE OR REPLACE FUNCTION plat.auditoria_cobrir() RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r text := plat.req_guc('req_id'); m text := plat.req_guc('metodo');
BEGIN
  IF plat.tenant_atual() IS NULL OR r IS NULL OR m IS NULL THEN RETURN NULL; END IF;
  IF m NOT IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN RETURN NULL; END IF;
  IF EXISTS (SELECT 1 FROM plat.auditoria WHERE req_id = r) THEN RETURN NULL; END IF;
  RETURN plat.auditoria_registrar(lower(m) || ' ' || coalesce(plat.req_guc('rota'), '?'),
                                  'rota', plat.req_guc('rota'), NULL, NULL, 'cobertura');
END $$;

-- ---------------------------------------------------------------- 4. retenção por inquilino + expurgo
-- Padrão 730 dias (2 anos). O PISO de 90 dias é a resposta ao "expurgo prematuro": um admin do inquilino não
-- consegue encolher a própria trilha abaixo dele, e a mudança de retenção é ela mesma auditada (evento
-- `auditoria/retencao`, registrado pela rota PUT /api/auditoria/config).
CREATE OR REPLACE FUNCTION plat.auditoria_retencao_dias(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT greatest(90, least(3650, coalesce((config->>'auditoria_retencao_dias')::int, 730)))
  FROM plat.tenant WHERE id = p_tenant
$$;

-- Expurgo POR INQUILINO: cada um com a sua retenção. Linha de inquilino já apagado sai pelo padrão de 730 d.
CREATE OR REPLACE FUNCTION plat.auditoria_expurgar(p_lote int DEFAULT 50000) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int := 0; k int;
BEGIN
  PERFORM set_config('plat.auditoria_expurgo', '1', true);
  WITH alvo AS (
    SELECT a.id FROM plat.auditoria a
    LEFT JOIN plat.tenant t ON t.id = a.tenant_id
    WHERE a.em < now() - make_interval(days => greatest(90, least(3650,
            coalesce((t.config->>'auditoria_retencao_dias')::int, 730))))
    LIMIT p_lote)
  DELETE FROM plat.auditoria d USING alvo WHERE d.id = alvo.id;
  GET DIAGNOSTICS k = ROW_COUNT;
  n := k;
  PERFORM set_config('plat.auditoria_expurgo', '', true);
  RETURN n;
END $$;

-- ---------------------------------------------------------------- 5. leitura e exportação
-- UMA função para os dois caminhos (tela e exportação): é o que faz a contagem da exportação bater com a
-- contagem da tabela por construção, não por coincidência de dois SQL parecidos.
DROP FUNCTION IF EXISTS plat.auditoria_listar(timestamptz, timestamptz, int, text, text, int, int);
CREATE OR REPLACE FUNCTION plat.auditoria_listar(
  p_desde timestamptz, p_ate timestamptz, p_ator int DEFAULT NULL, p_acao text DEFAULT NULL,
  p_recurso_tipo text DEFAULT NULL, p_origem text DEFAULT NULL,
  p_limite int DEFAULT 50, p_deslocamento int DEFAULT 0)
RETURNS TABLE (id bigint, em timestamptz, ator_id int, ator_login text, token_id int, acao text,
               recurso_tipo text, recurso_id text, antes jsonb, depois jsonb, req_id text, ip text,
               metodo text, rota text, origem text)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = plat, public AS $$
  SELECT a.id, a.em, a.ator_id, a.ator_login, a.token_id, a.acao, a.recurso_tipo, a.recurso_id,
         a.antes, a.depois, a.req_id, a.ip, a.metodo, a.rota, a.origem
  FROM plat.auditoria a
  WHERE a.em >= p_desde AND a.em < p_ate
    AND (p_ator IS NULL OR a.ator_id = p_ator)
    AND (p_acao IS NULL OR a.acao = p_acao)
    AND (p_recurso_tipo IS NULL OR a.recurso_tipo = p_recurso_tipo)
    AND (p_origem IS NULL OR a.origem = p_origem)
  ORDER BY a.em DESC, a.id DESC
  LIMIT p_limite OFFSET p_deslocamento
$$;

DROP FUNCTION IF EXISTS plat.auditoria_contar(timestamptz, timestamptz, int, text, text);
CREATE OR REPLACE FUNCTION plat.auditoria_contar(
  p_desde timestamptz, p_ate timestamptz, p_ator int DEFAULT NULL, p_acao text DEFAULT NULL,
  p_recurso_tipo text DEFAULT NULL, p_origem text DEFAULT NULL) RETURNS bigint
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = plat, public AS $$
  SELECT count(*) FROM plat.auditoria a
  WHERE a.em >= p_desde AND a.em < p_ate
    AND (p_ator IS NULL OR a.ator_id = p_ator)
    AND (p_acao IS NULL OR a.acao = p_acao)
    AND (p_recurso_tipo IS NULL OR a.recurso_tipo = p_recurso_tipo)
    AND (p_origem IS NULL OR a.origem = p_origem)
$$;

-- ---------------------------------------------------------------- 6. vocabulário de evento
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('auditoria/retencao', 'retenção da trilha de auditoria do inquilino alterada (antes/depois em dias; piso de 90 d)'),
  ('auditoria/exportar', 'trilha de auditoria exportada (formato, período e nº de linhas em propriedades)')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- 7. privilégios das funções (P6)
-- ⚠ `REVOKE ... FROM PUBLIC` NÃO basta neste schema: a migração 001_fundacao tem
--   ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT EXECUTE ON FUNCTIONS TO plat_app
-- ou seja, TODA função nova criada por postgres já nasce executável por plat_app. Medido nesta trilha antes
-- da correção: `SELECT plat.auditoria_expurgar()` como plat_app RODOU. Cada função que não é para a aplicação
-- precisa de REVOKE explícito FROM plat_app — é o mesmo padrão de recurso partilhado sem dimensão de dono que
-- derrubou fila, trinco e cota; aqui o partilhado é o privilégio padrão do schema.
REVOKE EXECUTE ON FUNCTION plat.tg_auditoria_imutavel() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tg_auditoria_sem_truncate() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tg_evento_auditoria() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.req_guc(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_registrar(text, text, text, jsonb, jsonb, text, int, int, text, text, timestamptz) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_cobrir() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_retencao_dias(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_expurgar(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_listar(timestamptz, timestamptz, int, text, text, text, int, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_contar(timestamptz, timestamptz, int, text, text, text) FROM PUBLIC;
-- ⛔ REVOKE explícito de tudo o que a aplicação NÃO pode chamar (o default privilege já concedeu):
--   auditoria_registrar: gravaria linha com inquilino, ator e instante escolhidos por quem chama — forjaria
--     trilha de OUTRO inquilino. Só o trigger e auditoria_cobrir() a chamam, e os dois são SECURITY DEFINER.
--   auditoria_expurgar: apagaria a própria trilha pela API (é a refutação nomeada do item).
--   auditoria_cron_*: pg_cron é recurso global da máquina; a aplicação não agenda nem desagenda nada.
REVOKE EXECUTE ON FUNCTION plat.auditoria_registrar(text, text, text, jsonb, jsonb, text, int, int, text, text, timestamptz) FROM plat_app;
REVOKE EXECUTE ON FUNCTION plat.auditoria_expurgar(int) FROM plat_app;
REVOKE EXECUTE ON FUNCTION plat.tg_auditoria_imutavel() FROM plat_app;
REVOKE EXECUTE ON FUNCTION plat.tg_auditoria_sem_truncate() FROM plat_app;
REVOKE EXECUTE ON FUNCTION plat.tg_evento_auditoria() FROM plat_app;
GRANT EXECUTE ON FUNCTION plat.req_guc(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.auditoria_cobrir() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.auditoria_retencao_dias(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.auditoria_listar(timestamptz, timestamptz, int, text, text, text, int, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.auditoria_contar(timestamptz, timestamptz, int, text, text, text) TO plat_app;
-- auditoria_expurgar NÃO é concedida a plat_app: só o dono (postgres) e o pg_cron a executam. Se plat_app
-- pudesse chamá-la, o admin de um inquilino apagaria a própria trilha pela API — a refutação do item.

-- ---------------------------------------------------------------- 8. agendamento pg_cron
-- Ver docs/adr/0031-trilha-auditoria.md, seção "Regra para quem usar pg_cron nesta plataforma".
-- (a) nome derivado de current_schema(); (b) idempotente (desagenda o mesmo nome antes de agendar);
-- (c) a trilha desagenda o seu ao terminar; (d) nome de job = recurso partilhado, com dimensão de inquilino
--     (aqui, de schema) igual à que se exige da fila e do trinco consultivo.
CREATE OR REPLACE FUNCTION plat.auditoria_cron_nome() RETURNS text
LANGUAGE sql STABLE SET search_path = plat, public AS $$
  SELECT current_schema() || '_auditoria_expurgo'
$$;

CREATE OR REPLACE FUNCTION plat.auditoria_cron_agendar(p_horario text DEFAULT '17 3 * * *') RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE nome text := plat.auditoria_cron_nome(); esquema text := current_schema(); n int;
BEGIN
  -- to_regproc('cron.schedule') NÃO serve de guarda: o nome é sobrecarregado (2 e 3 argumentos) e a função
  -- levanta erro em vez de devolver NULL. A presença da extensão é a pergunta certa.
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN RETURN NULL; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING nome;
  IF n > 0 THEN EXECUTE 'SELECT cron.unschedule($1)' USING nome; END IF;   -- (b) idempotente
  EXECUTE 'SELECT cron.schedule($1, $2, $3)'
    USING nome, p_horario, format('SELECT %I.auditoria_expurgar()', esquema);
  RETURN nome;
END $$;

CREATE OR REPLACE FUNCTION plat.auditoria_cron_desagendar() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE nome text := plat.auditoria_cron_nome(); n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN RETURN false; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING nome;
  IF n > 0 THEN EXECUTE 'SELECT cron.unschedule($1)' USING nome; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING nome;
  RETURN n = 0;
END $$;

-- quantos jobs deste schema estão agendados (o teste da regra (b) confere que agendar duas vezes dá 1)
CREATE OR REPLACE FUNCTION plat.auditoria_cron_contar() RETURNS int
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN RETURN -1; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING plat.auditoria_cron_nome();
  RETURN n;
END $$;

REVOKE EXECUTE ON FUNCTION plat.auditoria_cron_nome() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_cron_agendar(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_cron_desagendar() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_cron_contar() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.auditoria_cron_agendar(text) FROM plat_app;
REVOKE EXECUTE ON FUNCTION plat.auditoria_cron_desagendar() FROM plat_app;
GRANT EXECUTE ON FUNCTION plat.auditoria_cron_contar() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.auditoria_cron_nome() TO plat_app;   -- a tela de saúde mostra o nome do job

-- Agenda AQUI, com o nome derivado do schema corrente: produção agenda `plat_auditoria_expurgo`, a trilha
-- `plat_t<trilha>_auditoria_expurgo`, e um nunca expurga a tabela do outro. O DO chama a FUNÇÃO (que tem
-- SET search_path) em vez de current_schema() direto: no corpo de um DO o search_path é o do psql, `public`.
DO $$
BEGIN
  PERFORM plat.auditoria_cron_agendar();
END $$;
