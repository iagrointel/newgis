-- 006_jobs_transicoes (alterado em T2, achado do testador do L0-05): a role plat_app com contexto de inquilino
-- conseguia, por SQL, levar um job pendente -> rodando -> concluido com resultado forjado, sem worker (o gatilho da 004
-- só protegia o estado FINAL). Correção em três camadas, todas verificáveis:
--   1. role própria do worker, plat_worker (LOGIN, sem BYPASSRLS, sem privilégio de tabela): só ela tem EXECUTE nas
--      funções que mudam de estado (job_pegar/terminar/devolver/ceifar, worker_*, agenda_*, jobs_no_dia); plat_app perde;
--   2. REVOKE UPDATE em plat.job para plat_app: a API cancela por plat.job_cancelar e o filho reporta progresso por
--      plat.job_progresso (só progresso/mensagem/heartbeat); linhas_log passa a ser contado por gatilho;
--   3. gatilho plat.job_transicao (BEFORE INSERT OR UPDATE): job nasce pendente e limpo; entrar em rodando/concluido/
--      falhou, ou mudar resultado/tentativa/reinicios/worker/iniciado_em/terminado_em/proveniencia, exige o GUC
--      plat.via_worker = 'sim', que só as funções SECURITY DEFINER do worker ligam (e desligam) na própria transação.
-- Também: jobs_expurgar apaga marcadores e passos órfãos em plat_trabalho (acumulavam). Idempotente; sem BEGIN/COMMIT.
-- A 004 aplicada não é editada (arquivo aplicado é imutável).

-- ---------------------------------------------------------------- 1. role do worker
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_worker') THEN
    CREATE ROLE plat_worker LOGIN;             -- senha: install.sh (ALTER ROLE), nunca no SQL do repositório
  END IF;
END $$;
GRANT USAGE ON SCHEMA plat TO plat_worker;
-- nenhum privilégio de tabela: o worker enxerga a fila só pelas funções SECURITY DEFINER

-- ---------------------------------------------------------------- 2. plat_app não altera plat.job diretamente
REVOKE UPDATE ON plat.job FROM plat_app;

-- ---------------------------------------------------------------- 3. gatilho de transição
CREATE OR REPLACE FUNCTION plat.job_transicao() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE via_worker boolean := coalesce(current_setting('plat.via_worker', true), '') = 'sim';
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.estado <> 'pendente' OR NEW.resultado IS NOT NULL OR NEW.tentativa <> 0 OR NEW.reinicios <> 0
       OR NEW.worker IS NOT NULL OR NEW.iniciado_em IS NOT NULL OR NEW.terminado_em IS NOT NULL
       OR NEW.progresso <> 0 OR NEW.erro IS NOT NULL OR NEW.cancelar_solicitado THEN
      RAISE EXCEPTION 'job nasce pendente e sem resultado' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT via_worker THEN
    IF NEW.estado IS DISTINCT FROM OLD.estado AND NEW.estado IN ('rodando', 'concluido', 'falhou') THEN
      RAISE EXCEPTION 'transição para % só pelo worker', NEW.estado USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.resultado IS DISTINCT FROM OLD.resultado OR NEW.tentativa IS DISTINCT FROM OLD.tentativa
       OR NEW.reinicios IS DISTINCT FROM OLD.reinicios OR NEW.worker IS DISTINCT FROM OLD.worker
       OR NEW.iniciado_em IS DISTINCT FROM OLD.iniciado_em OR NEW.proveniencia IS DISTINCT FROM OLD.proveniencia
       OR NEW.processo_pid IS DISTINCT FROM OLD.processo_pid THEN
      RAISE EXCEPTION 'resultado, tentativa, reinicios, worker, iniciado_em, proveniencia e pid só pelo worker'
        USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS job_transicao ON plat.job;
CREATE TRIGGER job_transicao BEFORE INSERT OR UPDATE ON plat.job FOR EACH ROW EXECUTE FUNCTION plat.job_transicao();
-- ordem: gatilhos BEFORE disparam em ordem alfabética de nome; job_estado_final_imutavel (004) continua antes deste

-- ---------------------------------------------------------------- funções do worker ligam o GUC na própria transação
CREATE OR REPLACE FUNCTION plat.via_worker_ligar() RETURNS void LANGUAGE sql AS $$ SELECT set_config('plat.via_worker', 'sim', true) $$;
CREATE OR REPLACE FUNCTION plat.via_worker_desligar() RETURNS void LANGUAGE sql AS $$ SELECT set_config('plat.via_worker', '', true) $$;
-- a 001 dá EXECUTE a plat_app por privilégio padrão em toda função nova do schema: aqui o REVOKE tem de ser explícito
REVOKE EXECUTE ON FUNCTION plat.via_worker_ligar() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.via_worker_desligar() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.job_transicao() FROM PUBLIC, plat_app;

CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job;
BEGIN
  PERFORM plat.via_worker_ligar();
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
  PERFORM plat.via_worker_desligar();
  RETURN pego;
END $$;

CREATE OR REPLACE FUNCTION plat.job_pid(p_id uuid, p_worker text, p_pid int) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET processo_pid = p_pid WHERE id = p_id AND worker = p_worker AND estado = 'rodando';
  PERFORM plat.via_worker_desligar();
END $$;

CREATE OR REPLACE FUNCTION plat.job_terminar(p_id uuid, p_worker text, p_estado text, p_resultado jsonb, p_erro text,
                                             p_proveniencia jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; a uuid;
BEGIN
  IF p_estado NOT IN ('concluido','falhou','cancelado') THEN RAISE EXCEPTION 'estado final inválido: %', p_estado; END IF;
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET estado = p_estado, terminado_em = now(), resultado = p_resultado, erro = left(p_erro, 2000),
                      proveniencia = coalesce(proveniencia, '{}'::jsonb) || coalesce(p_proveniencia, '{}'::jsonb),
                      progresso = CASE WHEN p_estado = 'concluido' THEN 100 ELSE progresso END, processo_pid = NULL
  WHERE id = p_id AND worker = p_worker AND estado = 'rodando' RETURNING agenda_id INTO a;
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM plat.via_worker_desligar();
  IF n = 1 AND a IS NOT NULL THEN PERFORM plat.agenda_registrar_fim(p_id, a, p_estado); END IF;
  RETURN n = 1;
END $$;

CREATE OR REPLACE FUNCTION plat.job_devolver(p_id uuid, p_worker text, p_motivo text, p_conta_tentativa boolean,
                                             p_espera_s int, p_max_reinicios int DEFAULT 5,
                                             p_proveniencia jsonb DEFAULT NULL) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE j plat.job; novo text;
BEGIN
  SELECT * INTO j FROM plat.job WHERE id = p_id AND estado = 'rodando' AND (p_worker IS NULL OR worker = p_worker) FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  PERFORM plat.via_worker_ligar();
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
  PERFORM plat.via_worker_desligar();
  IF novo = 'falhou' AND j.agenda_id IS NOT NULL THEN PERFORM plat.agenda_registrar_fim(p_id, j.agenda_id, novo); END IF;
  RETURN novo;
END $$;

-- job_heartbeat só toca heartbeat_em (coluna livre); job_ceifar chama job_devolver (liga o GUC lá dentro)

-- ---------------------------------------------------------------- o que a API e o filho podem fazer
-- API: cancelar (pendente -> cancelado; rodando -> pedido). Exige o contexto do inquilino do job (RLS por função).
CREATE OR REPLACE FUNCTION plat.job_cancelar(p_id uuid, p_usuario int) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE j plat.job;
BEGIN
  SELECT * INTO j FROM plat.job WHERE id = p_id AND tenant_id = plat.tenant_atual() FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF j.estado = 'pendente' THEN
    UPDATE plat.job SET estado = 'cancelado', cancelado_por = p_usuario, cancelado_em = now(), terminado_em = now(),
      erro = 'cancelado antes de iniciar' WHERE id = p_id;
    RETURN 'cancelado';
  ELSIF j.estado = 'rodando' THEN
    UPDATE plat.job SET cancelar_solicitado = true, cancelado_por = coalesce(cancelado_por, p_usuario),
      cancelado_em = coalesce(cancelado_em, now()) WHERE id = p_id;
    RETURN 'solicitado';
  END IF;
  RETURN j.estado;
END $$;

-- filho: progresso/mensagem/heartbeat do job que ele executa (mesmo inquilino, mesmo worker, rodando); devolve
-- cancelar_solicitado ou NULL quando o job já não é dele (devolvido, ceifado, cancelado)
CREATE OR REPLACE FUNCTION plat.job_progresso(p_id uuid, p_worker text, p_progresso int, p_mensagem text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.job SET progresso = greatest(0, least(100, p_progresso)), mensagem = left(p_mensagem, 200), heartbeat_em = now()
  WHERE id = p_id AND worker = p_worker AND estado = 'rodando' AND tenant_id = plat.tenant_atual()
  RETURNING cancelar_solicitado
$$;

-- linhas_log contado por gatilho (SECURITY DEFINER: o filho não tem mais UPDATE em plat.job)
CREATE OR REPLACE FUNCTION plat.job_log_notificar() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = plat, public AS $$
BEGIN
  UPDATE plat.job SET linhas_log = linhas_log + 1 WHERE id = NEW.job_id;
  PERFORM pg_notify('plat_job', json_build_object('job', NEW.job_id, 'tenant_id', NEW.tenant_id,
    'log', json_build_object('id', NEW.id, 'em', NEW.em, 'nivel', NEW.nivel, 'mensagem', left(NEW.mensagem, 1000)))::text);
  RETURN NULL;
END $$;

-- ---------------------------------------------------------------- expurgo: também marcadores e passos órfãos
DROP FUNCTION IF EXISTS plat.jobs_expurgar(int, int);
CREATE OR REPLACE FUNCTION plat.jobs_expurgar(p_dias_job int, p_dias_log int)
RETURNS TABLE (jobs_apagados int, logs_apagados int, marcadores_apagados int, passos_apagados int, rodando uuid[])
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE nj int; nl int; nm int; np int;
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT id FROM plat.tenant WHERE slug = 'plataforma') THEN
    RAISE EXCEPTION 'expurgo só no contexto do inquilino técnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  DELETE FROM plat.job_log WHERE em < now() - make_interval(days => p_dias_log);
  GET DIAGNOSTICS nl = ROW_COUNT;
  DELETE FROM plat.job WHERE estado IN ('concluido','falhou','cancelado') AND terminado_em < now() - make_interval(days => p_dias_job);
  GET DIAGNOSTICS nj = ROW_COUNT;
  DELETE FROM plat_trabalho.marcadores m WHERE NOT EXISTS (SELECT 1 FROM plat.job j WHERE j.id = m.job_id);
  GET DIAGNOSTICS nm = ROW_COUNT;
  DELETE FROM plat_trabalho.passos p WHERE NOT EXISTS (SELECT 1 FROM plat.job j WHERE j.id = p.job_id AND j.estado = 'rodando');
  GET DIAGNOSTICS np = ROW_COUNT;
  RETURN QUERY SELECT nj, nl, nm, np, coalesce((SELECT array_agg(id) FROM plat.job WHERE estado = 'rodando'), '{}'::uuid[]);
END $$;

-- ---------------------------------------------------------------- EXECUTE: worker x API x filho
DO $$
DECLARE f text;
BEGIN
  -- só o worker (pai): muda estado, registra worker, relógio das agendas
  FOREACH f IN ARRAY ARRAY[
    'plat.job_pegar(text, boolean)', 'plat.job_pid(uuid, text, int)', 'plat.job_heartbeat(uuid, text)',
    'plat.job_terminar(uuid, text, text, jsonb, text, jsonb)', 'plat.job_devolver(uuid, text, text, boolean, int, int, jsonb)',
    'plat.job_ceifar(int, text, int)', 'plat.worker_registrar(text, int, text, text, int)',
    'plat.worker_heartbeat(text, int, int)', 'plat.worker_desregistrar(text)', 'plat.worker_ceifar(int)',
    'plat.agenda_vencidas(timestamptz)', 'plat.agenda_enfileirar(uuid, timestamptz, timestamptz, boolean, boolean, int, int, text, int, text)',
    'plat.agenda_periodica_sincronizar(text, text, jsonb, text, text, timestamptz)', 'plat.jobs_no_dia(int)',
    'plat.cota_jobs_dia(int)', 'plat.cota_jobs_simultaneos(int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM plat_app', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_worker', f);
  END LOOP;
  -- a API precisa das cotas para responder 413 e do estado da fila para /saude
  FOREACH f IN ARRAY ARRAY['plat.cota_jobs_dia(int)', 'plat.cota_jobs_simultaneos(int)', 'plat.cota_agendas(int)',
                           'plat.fila_estado()', 'plat.job_cancelar(uuid, int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
  -- o filho (plat_app, dentro do inquilino do job): progresso e expurgo (este só no inquilino plataforma)
  FOREACH f IN ARRAY ARRAY['plat.job_progresso(uuid, text, int, text)', 'plat.jobs_expurgar(int, int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
-- privilégio padrão futuro: funções novas no schema plat nascem sem EXECUTE para PUBLIC (achado do adversário do T1)
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
