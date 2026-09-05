-- 004_jobs: fila de jobs própria em SQL (ADR 0003 seções 2, 4.2 e 7): tabelas job, job_log, worker, agenda;
-- RLS por inquilino; estado final imutável por gatilho; NOTIFY por gatilho (plat_job para o navegador,
-- plat_worker para acordar o worker); funções SECURITY DEFINER do worker (únicas que enxergam além do inquilino),
-- cotas por inquilino, inquilino técnico 'plataforma' para os periódicos, schema plat_trabalho para efeito
-- parcial das tarefas. Idempotente. Sem BEGIN/COMMIT. Numeração 004 é da trilha B (a trilha A usa 003 e 005).

-- ---------------------------------------------------------------- tabelas
CREATE TABLE IF NOT EXISTS plat.job (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  usuario_id          int REFERENCES plat.usuario(id),
  tipo                text NOT NULL,
  parametros          jsonb NOT NULL DEFAULT '{}'::jsonb,
  estado              text NOT NULL DEFAULT 'pendente'
                      CHECK (estado IN ('pendente','rodando','concluido','falhou','cancelado')),
  prioridade          smallint NOT NULL DEFAULT 5 CHECK (prioridade BETWEEN 1 AND 9),
  chave               text,
  pesado              boolean NOT NULL,
  memoria_mb          int NOT NULL,
  timeout_s           int NOT NULL,
  executor            text NOT NULL DEFAULT 'local' CHECK (executor IN ('local','gpu')),
  max_tentativas      smallint NOT NULL DEFAULT 3,
  tentativa           smallint NOT NULL DEFAULT 0,
  reinicios           smallint NOT NULL DEFAULT 0,
  agendado_para       timestamptz NOT NULL DEFAULT now(),
  agenda_id           uuid,
  programado_para     timestamptz,
  criado_em           timestamptz NOT NULL DEFAULT now(),
  iniciado_em         timestamptz,
  heartbeat_em        timestamptz,
  terminado_em        timestamptz,
  worker              text,
  processo_pid        int,
  progresso           smallint NOT NULL DEFAULT 0 CHECK (progresso BETWEEN 0 AND 100),
  mensagem            text,
  cancelar_solicitado boolean NOT NULL DEFAULT false,
  cancelado_por       int,
  cancelado_em        timestamptz,
  resultado           jsonb,
  erro                text,
  proveniencia        jsonb,
  linhas_log          int NOT NULL DEFAULT 0,
  UNIQUE (agenda_id, programado_para)
);
CREATE INDEX IF NOT EXISTS ix_job_fila    ON plat.job (prioridade, agendado_para, criado_em) WHERE estado = 'pendente';
CREATE INDEX IF NOT EXISTS ix_job_rodando ON plat.job (heartbeat_em) WHERE estado = 'rodando';
CREATE INDEX IF NOT EXISTS ix_job_tenant  ON plat.job (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_job_chave   ON plat.job (chave) WHERE estado IN ('pendente','rodando') AND chave IS NOT NULL;

CREATE TABLE IF NOT EXISTS plat.job_log (
  id         bigserial PRIMARY KEY,
  job_id     uuid NOT NULL REFERENCES plat.job(id) ON DELETE CASCADE,
  tenant_id  int NOT NULL,
  em         timestamptz NOT NULL DEFAULT clock_timestamp(),
  nivel      text NOT NULL CHECK (nivel IN ('DEBUG','INFO','AVISO','ERRO')),
  mensagem   text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_job_log_job ON plat.job_log (job_id, id);

CREATE TABLE IF NOT EXISTS plat.worker (
  nome         text PRIMARY KEY,
  pid          int NOT NULL,
  versao       text NOT NULL,
  git_sha      text NOT NULL,
  processos    int NOT NULL,
  iniciado_em  timestamptz NOT NULL DEFAULT now(),
  heartbeat_em timestamptz NOT NULL DEFAULT now(),
  rss_kb       int,
  rodando      int NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS plat.agenda (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  usuario_id       int REFERENCES plat.usuario(id),
  nome             text NOT NULL,
  tipo             text NOT NULL,
  parametros       jsonb NOT NULL DEFAULT '{}'::jsonb,
  cron             text NOT NULL,
  fuso             text NOT NULL DEFAULT 'America/Sao_Paulo',
  ativa            boolean NOT NULL DEFAULT true,
  proxima_em       timestamptz,
  ultima_em        timestamptz,
  ultimo_job_id    uuid,
  ultimo_estado    text,
  falhas_seguidas  smallint NOT NULL DEFAULT 0,
  expira_em        timestamptz,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, nome)
);
CREATE INDEX IF NOT EXISTS ix_agenda_proxima ON plat.agenda (proxima_em) WHERE ativa AND proxima_em IS NOT NULL;

-- schema de trabalho: efeito parcial das tarefas (ADR 0003 seção 6). Tipos podem criar tabela própria aqui (GRANT
-- CREATE), mas DDL custa 0,5-1 s neste servidor (MEDIDO em T2: CREATE TABLE 528-1.030 ms); efeito parcial pequeno
-- vai em linhas de uma tabela compartilhada chaveada por job_id, como faz prova.progresso em plat_trabalho.passos.
CREATE SCHEMA IF NOT EXISTS plat_trabalho AUTHORIZATION postgres;
GRANT USAGE, CREATE ON SCHEMA plat_trabalho TO plat_app;
CREATE TABLE IF NOT EXISTS plat_trabalho.passos (
  job_id uuid NOT NULL,
  passo  int NOT NULL,
  em     timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (job_id, passo)
);
GRANT SELECT, INSERT, DELETE ON plat_trabalho.passos TO plat_app;
-- marcador de fim de execução do tipo de diagnóstico prova.progresso: gravado só no último passo
CREATE TABLE IF NOT EXISTS plat_trabalho.marcadores (
  job_id   uuid NOT NULL,
  marcador uuid NOT NULL,
  em       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (job_id, marcador)
);
GRANT SELECT, INSERT, DELETE ON plat_trabalho.marcadores TO plat_app;

-- ---------------------------------------------------------------- RLS (D20)
ALTER TABLE plat.job     ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.job_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.agenda  ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_job ON plat.job;
CREATE POLICY p_job ON plat.job FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_job_log ON plat.job_log;
CREATE POLICY p_job_log ON plat.job_log FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_agenda ON plat.agenda;
CREATE POLICY p_agenda ON plat.agenda FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
-- worker é infraestrutura: plat_app só lê pela função plat.fila_estado()
REVOKE ALL ON plat.worker FROM plat_app;

-- ---------------------------------------------------------------- gatilhos
-- estado final é imutável: "repetir" cria job novo (ADR 0003 seção 2.3)
CREATE OR REPLACE FUNCTION plat.job_estado_final_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('concluido','falhou','cancelado') AND (
       NEW.estado IS DISTINCT FROM OLD.estado OR NEW.progresso IS DISTINCT FROM OLD.progresso
    OR NEW.mensagem IS DISTINCT FROM OLD.mensagem OR NEW.resultado IS DISTINCT FROM OLD.resultado
    OR NEW.erro IS DISTINCT FROM OLD.erro OR NEW.cancelar_solicitado IS DISTINCT FROM OLD.cancelar_solicitado
    OR NEW.tentativa IS DISTINCT FROM OLD.tentativa OR NEW.reinicios IS DISTINCT FROM OLD.reinicios
    OR NEW.worker IS DISTINCT FROM OLD.worker OR NEW.iniciado_em IS DISTINCT FROM OLD.iniciado_em
    OR NEW.terminado_em IS DISTINCT FROM OLD.terminado_em OR NEW.proveniencia IS DISTINCT FROM OLD.proveniencia) THEN
    RAISE EXCEPTION 'job em estado final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS job_estado_final_imutavel ON plat.job;
CREATE TRIGGER job_estado_final_imutavel BEFORE UPDATE ON plat.job
  FOR EACH ROW EXECUTE FUNCTION plat.job_estado_final_imutavel();

-- NOTIFY: plat_job para o navegador (SSE); plat_worker para acordar o worker (job novo ou cancelamento)
CREATE OR REPLACE FUNCTION plat.job_notificar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE carga text;
BEGIN
  carga := json_build_object('job', NEW.id, 'tenant_id', NEW.tenant_id, 'estado', NEW.estado,
                             'progresso', NEW.progresso, 'mensagem', left(NEW.mensagem, 200),
                             'tentativa', NEW.tentativa, 'cancelar_solicitado', NEW.cancelar_solicitado,
                             'seq', extract(epoch from clock_timestamp()))::text;
  PERFORM pg_notify('plat_job', carga);
  IF NEW.estado = 'pendente' AND (TG_OP = 'INSERT' OR OLD.estado IS DISTINCT FROM 'pendente'
                                  OR NEW.agendado_para IS DISTINCT FROM OLD.agendado_para) THEN
    PERFORM pg_notify('plat_worker', json_build_object('job', NEW.id, 'pendente', true)::text);
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.cancelar_solicitado AND NOT OLD.cancelar_solicitado THEN
    PERFORM pg_notify('plat_worker', json_build_object('job', NEW.id, 'cancelar', true)::text);
  END IF;
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS job_notificar ON plat.job;
CREATE TRIGGER job_notificar AFTER INSERT OR UPDATE OF estado, progresso, mensagem, cancelar_solicitado, agendado_para
  ON plat.job FOR EACH ROW EXECUTE FUNCTION plat.job_notificar();

CREATE OR REPLACE FUNCTION plat.job_log_notificar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('plat_job', json_build_object('job', NEW.job_id, 'tenant_id', NEW.tenant_id,
    'log', json_build_object('id', NEW.id, 'em', NEW.em, 'nivel', NEW.nivel, 'mensagem', left(NEW.mensagem, 1000)))::text);
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS job_log_notificar ON plat.job_log;
CREATE TRIGGER job_log_notificar AFTER INSERT ON plat.job_log FOR EACH ROW EXECUTE FUNCTION plat.job_log_notificar();

-- ---------------------------------------------------------------- cotas por inquilino (D16)
CREATE OR REPLACE FUNCTION plat.cota_jobs_simultaneos(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_jobs_simultaneos')::int, 2) FROM plat.tenant WHERE id = p_tenant
$$;
CREATE OR REPLACE FUNCTION plat.cota_jobs_dia(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_jobs_dia')::int, 1000) FROM plat.tenant WHERE id = p_tenant
$$;
-- jobs criados hoje (dia UTC) pelo inquilino: a API conta sob RLS; o relógio do worker (sem inquilino) usa esta função
CREATE OR REPLACE FUNCTION plat.jobs_no_dia(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*)::int FROM plat.job WHERE tenant_id = p_tenant AND criado_em >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
$$;
CREATE OR REPLACE FUNCTION plat.cota_agendas(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_agendas')::int, 50) FROM plat.tenant WHERE id = p_tenant
$$;

-- ---------------------------------------------------------------- funções do worker (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job;
BEGIN
  WITH c AS (
    SELECT j.id FROM plat.job j
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r WHERE r.chave = j.chave AND r.estado = 'rodando'))
      AND (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando')
          < plat.cota_jobs_simultaneos(j.tenant_id)
    ORDER BY j.prioridade, j.agendado_para, j.criado_em
    FOR UPDATE OF j SKIP LOCKED LIMIT 1)
  UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                      tentativa = tentativa + 1, progresso = 0, mensagem = NULL
  FROM c WHERE plat.job.id = c.id RETURNING plat.job.* INTO pego;
  RETURN pego;
END $$;

CREATE OR REPLACE FUNCTION plat.job_pid(p_id uuid, p_worker text, p_pid int) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.job SET processo_pid = p_pid WHERE id = p_id AND worker = p_worker AND estado = 'rodando'
$$;

CREATE OR REPLACE FUNCTION plat.job_heartbeat(p_id uuid, p_worker text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.job SET heartbeat_em = now() WHERE id = p_id AND worker = p_worker AND estado = 'rodando'
  RETURNING cancelar_solicitado
$$;

CREATE OR REPLACE FUNCTION plat.job_terminar(p_id uuid, p_worker text, p_estado text, p_resultado jsonb, p_erro text,
                                             p_proveniencia jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; a uuid;
BEGIN
  IF p_estado NOT IN ('concluido','falhou','cancelado') THEN RAISE EXCEPTION 'estado final inválido: %', p_estado; END IF;
  UPDATE plat.job SET estado = p_estado, terminado_em = now(), resultado = p_resultado, erro = left(p_erro, 2000),
                      proveniencia = coalesce(proveniencia, '{}'::jsonb) || coalesce(p_proveniencia, '{}'::jsonb),
                      progresso = CASE WHEN p_estado = 'concluido' THEN 100 ELSE progresso END, processo_pid = NULL
  WHERE id = p_id AND worker = p_worker AND estado = 'rodando' RETURNING agenda_id INTO a;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n = 1 AND a IS NOT NULL THEN PERFORM plat.agenda_registrar_fim(p_id, a, p_estado); END IF;
  RETURN n = 1;
END $$;

-- devolve o job à fila. Reinício/ceifa não conta tentativa (reinicios += 1; teto p_max_reinicios → falhou);
-- exceção da tarefa conta tentativa (tentativa >= max_tentativas → falhou). Devolve o estado resultante.
-- (assinatura de 6 parâmetros do rascunho de T2 removida: CREATE OR REPLACE não substitui sobrecarga diferente)
DROP FUNCTION IF EXISTS plat.job_devolver(uuid, text, text, boolean, int, int);
CREATE OR REPLACE FUNCTION plat.job_devolver(p_id uuid, p_worker text, p_motivo text, p_conta_tentativa boolean,
                                             p_espera_s int, p_max_reinicios int DEFAULT 5,
                                             p_proveniencia jsonb DEFAULT NULL) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE j plat.job; novo text; a uuid;
BEGIN
  SELECT * INTO j FROM plat.job WHERE id = p_id AND estado = 'rodando' AND (p_worker IS NULL OR worker = p_worker) FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF p_conta_tentativa THEN
    novo := CASE WHEN j.tentativa >= j.max_tentativas THEN 'falhou' ELSE 'pendente' END;
    UPDATE plat.job SET estado = novo, erro = left(p_motivo, 2000), worker = NULL, processo_pid = NULL,
      heartbeat_em = NULL, agendado_para = now() + make_interval(secs => greatest(p_espera_s, 0)),
      terminado_em = CASE WHEN novo = 'falhou' THEN now() ELSE NULL END,
      proveniencia = coalesce(proveniencia, '{}'::jsonb) || coalesce(p_proveniencia, '{}'::jsonb)
    WHERE id = p_id;
  ELSE
    novo := CASE WHEN j.reinicios + 1 >= p_max_reinicios THEN 'falhou' ELSE 'pendente' END;
    UPDATE plat.job SET estado = novo, reinicios = reinicios + 1, worker = NULL, processo_pid = NULL, heartbeat_em = NULL,
      erro = CASE WHEN novo = 'falhou' THEN format('devolvido %s vezes sem terminar (%s)', p_max_reinicios, p_motivo)
                  ELSE left(p_motivo, 2000) END,
      agendado_para = now() + make_interval(secs => greatest(p_espera_s, 0)),
      terminado_em = CASE WHEN novo = 'falhou' THEN now() ELSE NULL END
    WHERE id = p_id;
  END IF;
  IF novo = 'falhou' AND j.agenda_id IS NOT NULL THEN PERFORM plat.agenda_registrar_fim(p_id, j.agenda_id, novo); END IF;
  RETURN novo;
END $$;

-- rodando sem sinal há mais de p_limite_s, ou do worker p_worker (que acabou de nascer e sabe que morreu)
CREATE OR REPLACE FUNCTION plat.job_ceifar(p_limite_s int, p_worker text DEFAULT NULL, p_max_reinicios int DEFAULT 5) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT id, worker FROM plat.job WHERE estado = 'rodando'
             AND (coalesce(heartbeat_em, iniciado_em) < now() - make_interval(secs => p_limite_s)
                  OR (p_worker IS NOT NULL AND worker = p_worker)) LOOP
    PERFORM plat.job_devolver(r.id, r.worker, 'worker sem sinal', false, 0, p_max_reinicios);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.worker_registrar(p_nome text, p_pid int, p_versao text, p_git_sha text, p_processos int) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.worker(nome, pid, versao, git_sha, processos) VALUES (p_nome, p_pid, p_versao, p_git_sha, p_processos)
  ON CONFLICT (nome) DO UPDATE SET pid = EXCLUDED.pid, versao = EXCLUDED.versao, git_sha = EXCLUDED.git_sha,
    processos = EXCLUDED.processos, iniciado_em = now(), heartbeat_em = now(), rodando = 0
$$;
CREATE OR REPLACE FUNCTION plat.worker_heartbeat(p_nome text, p_rss_kb int, p_rodando int) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.worker SET heartbeat_em = now(), rss_kb = p_rss_kb, rodando = p_rodando WHERE nome = p_nome
$$;
CREATE OR REPLACE FUNCTION plat.worker_desregistrar(p_nome text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  DELETE FROM plat.worker WHERE nome = p_nome
$$;
CREATE OR REPLACE FUNCTION plat.worker_ceifar(p_limite_s int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  DELETE FROM plat.worker WHERE heartbeat_em < now() - make_interval(secs => p_limite_s);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.fila_estado()
RETURNS TABLE (pendentes int, rodando int, workers_vivos int, ultimo_heartbeat timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT (SELECT count(*)::int FROM plat.job WHERE estado = 'pendente'),
         (SELECT count(*)::int FROM plat.job WHERE estado = 'rodando'),
         (SELECT count(*)::int FROM plat.worker WHERE heartbeat_em > now() - interval '90 seconds'),
         (SELECT max(heartbeat_em) FROM plat.worker)
$$;

-- ---------------------------------------------------------------- agenda (o worker é o relógio; ADR 0003 seção 7)
CREATE OR REPLACE FUNCTION plat.agenda_vencidas(p_agora timestamptz DEFAULT now()) RETURNS SETOF plat.agenda
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT * FROM plat.agenda WHERE ativa AND proxima_em IS NOT NULL AND proxima_em <= p_agora
    AND (expira_em IS NULL OR expira_em > p_agora)
  ORDER BY proxima_em FOR UPDATE SKIP LOCKED
$$;

-- enfileira UMA ocorrência (UNIQUE (agenda_id, programado_para) é a segunda trava) e avança proxima_em.
-- Os limites do tipo (pesado, memoria_mb, timeout_s, executor, tentativas, chave) vêm do registro em código, pelo
-- worker, como na criação pela API. p_enfileirar = false só avança (cota do dia esgotada). Devolve o id do job ou NULL.
CREATE OR REPLACE FUNCTION plat.agenda_enfileirar(p_agenda uuid, p_programado_para timestamptz, p_proxima_em timestamptz,
  p_enfileirar boolean, p_pesado boolean, p_memoria_mb int, p_timeout_s int, p_executor text, p_max_tentativas int,
  p_chave text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE a plat.agenda; jid uuid;
BEGIN
  SELECT * INTO a FROM plat.agenda WHERE id = p_agenda FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF p_enfileirar THEN
    INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s, executor, max_tentativas,
                         chave, agenda_id, programado_para, agendado_para)
    VALUES (a.tenant_id, a.usuario_id, a.tipo, a.parametros, p_pesado, p_memoria_mb, p_timeout_s, p_executor,
            p_max_tentativas, p_chave, a.id, p_programado_para, now())
    ON CONFLICT (agenda_id, programado_para) DO NOTHING RETURNING id INTO jid;
  END IF;
  UPDATE plat.agenda SET proxima_em = p_proxima_em,
    ultima_em = CASE WHEN jid IS NOT NULL THEN now() ELSE ultima_em END,
    ultimo_job_id = coalesce(jid, ultimo_job_id)
  WHERE id = p_agenda;
  RETURN jid;
END $$;

-- chamada por job_terminar/job_devolver: último estado e falhas seguidas; 5 seguidas pausam (B9)
CREATE OR REPLACE FUNCTION plat.agenda_registrar_fim(p_job uuid, p_agenda uuid, p_estado text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.agenda SET ultimo_estado = p_estado, ultimo_job_id = p_job,
    falhas_seguidas = CASE WHEN p_estado = 'falhou' THEN falhas_seguidas + 1 WHEN p_estado = 'concluido' THEN 0 ELSE falhas_seguidas END,
    ativa = CASE WHEN p_estado = 'falhou' AND falhas_seguidas + 1 >= 5 THEN false ELSE ativa END,
    proxima_em = CASE WHEN p_estado = 'falhou' AND falhas_seguidas + 1 >= 5 THEN NULL ELSE proxima_em END
  WHERE id = p_agenda
$$;

-- periódicos da plataforma: upsert no inquilino técnico 'plataforma' (só cron/parametros mudam; ativa é do operador)
CREATE OR REPLACE FUNCTION plat.agenda_periodica_sincronizar(p_nome text, p_tipo text, p_parametros jsonb, p_cron text,
                                                             p_fuso text, p_proxima_em timestamptz) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; aid uuid;
BEGIN
  SELECT id INTO tid FROM plat.tenant WHERE slug = 'plataforma';
  IF tid IS NULL THEN RAISE EXCEPTION 'inquilino técnico plataforma ausente (migração 004)'; END IF;
  INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron, fuso, proxima_em)
  VALUES (tid, NULL, p_nome, p_tipo, p_parametros, p_cron, p_fuso, p_proxima_em)
  ON CONFLICT (tenant_id, nome) DO UPDATE SET tipo = EXCLUDED.tipo, parametros = EXCLUDED.parametros,
    cron = EXCLUDED.cron, fuso = EXCLUDED.fuso,
    proxima_em = CASE WHEN plat.agenda.cron <> EXCLUDED.cron OR plat.agenda.proxima_em IS NULL AND plat.agenda.ativa
                      THEN EXCLUDED.proxima_em ELSE plat.agenda.proxima_em END
  RETURNING id INTO aid;
  RETURN aid;
END $$;

-- expurgo (tipo jobs.expurgo, roda no inquilino plataforma): job terminado há > p_dias_job, job_log > p_dias_log.
-- Devolve também os ids rodando, para o expurgo de diretórios de trabalho não apagar o de um job vivo.
CREATE OR REPLACE FUNCTION plat.jobs_expurgar(p_dias_job int, p_dias_log int)
RETURNS TABLE (jobs_apagados int, logs_apagados int, rodando uuid[])
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE nj int; nl int;
BEGIN
  DELETE FROM plat.job_log WHERE em < now() - make_interval(days => p_dias_log);
  GET DIAGNOSTICS nl = ROW_COUNT;
  DELETE FROM plat.job WHERE estado IN ('concluido','falhou','cancelado') AND terminado_em < now() - make_interval(days => p_dias_job);
  GET DIAGNOSTICS nj = ROW_COUNT;
  RETURN QUERY SELECT nj, nl, coalesce((SELECT array_agg(id) FROM plat.job WHERE estado = 'rodando'), '{}'::uuid[]);
END $$;

-- ---------------------------------------------------------------- EXECUTE só plat_app (achado do adversário do T1)
DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.cota_jobs_simultaneos(int)', 'plat.cota_jobs_dia(int)', 'plat.cota_agendas(int)', 'plat.jobs_no_dia(int)',
    'plat.job_pegar(text, boolean)', 'plat.job_pid(uuid, text, int)', 'plat.job_heartbeat(uuid, text)',
    'plat.job_terminar(uuid, text, text, jsonb, text, jsonb)', 'plat.job_devolver(uuid, text, text, boolean, int, int, jsonb)',
    'plat.job_ceifar(int, text, int)', 'plat.worker_registrar(text, int, text, text, int)',
    'plat.worker_heartbeat(text, int, int)', 'plat.worker_desregistrar(text)', 'plat.worker_ceifar(int)',
    'plat.fila_estado()', 'plat.agenda_vencidas(timestamptz)', 'plat.agenda_enfileirar(uuid, timestamptz, timestamptz, boolean, boolean, int, int, text, int, text)',
    'plat.agenda_registrar_fim(uuid, uuid, text)', 'plat.agenda_periodica_sincronizar(text, text, jsonb, text, text, timestamptz)',
    'plat.jobs_expurgar(int, int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;

-- ---------------------------------------------------------------- inquilino técnico dos periódicos (ADR 0003 seção 7)
-- A 003 (identidade) cria e governa o mesmo inquilino (superadmin vive nele, ADR 0002 seção 10); aqui só se garante
-- que exista quando a 004 rodar sozinha. Nada de ativo/config: quem decide é a 003.
INSERT INTO plat.tenant(slug, nome) VALUES ('plataforma', 'Operação da plataforma')
ON CONFLICT (slug) DO NOTHING;
