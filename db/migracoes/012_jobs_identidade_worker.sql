-- 012_jobs_identidade_worker (correção T2 (2), achado do testador do L0-05): um worker lançado fora do systemd sem
-- PLAT_WORKER_NOME usava o nome padrão (hostname) e `job_ceifar(60, nome)` na partida DEVOLVIA os jobs do worker vivo
-- homônimo (reexecução do zero, reinicios += 1, nada no journal). A partir daqui:
--   - a identidade do worker é única por processo: `<nome-base>:<pid>` (app/jobs/worker.py), registrada em
--     plat.worker com heartbeat; job.worker guarda essa identidade;
--   - a ceifa devolve só jobs cujo sinal venceu: heartbeat do job > p_limite_s E o worker dono sem heartbeat recente
--     em plat.worker (ou já desregistrado). Nunca por igualdade de nome. A assinatura com p_worker é removida.
-- Idempotente.
DROP FUNCTION IF EXISTS plat.job_ceifar(int, text, int);
CREATE OR REPLACE FUNCTION plat.job_ceifar(p_limite_s int, p_max_reinicios int DEFAULT 5) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT j.id, j.worker FROM plat.job j
           WHERE j.estado = 'rodando'
             AND coalesce(j.heartbeat_em, j.iniciado_em) < now() - make_interval(secs => p_limite_s)
             AND NOT EXISTS (SELECT 1 FROM plat.worker w WHERE w.nome = j.worker
                             AND w.heartbeat_em >= now() - make_interval(secs => p_limite_s)) LOOP
    PERFORM plat.job_devolver(r.id, r.worker, 'worker sem sinal', false, 0, p_max_reinicios);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION plat.job_ceifar(int, int) FROM PUBLIC, plat_app;
GRANT EXECUTE ON FUNCTION plat.job_ceifar(int, int) TO plat_worker;
