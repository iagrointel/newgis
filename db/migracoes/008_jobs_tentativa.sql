-- 008_jobs_tentativa (integração T2; ADR 0003 seção 2.1 e tabela da seção 6): reinício e ceifa NÃO consomem tentativa.
-- job_pegar incrementa `tentativa` a cada retirada; a devolução por reinício/ceifa (p_conta_tentativa = false) passa a
-- desfazer esse incremento, de modo que a retomada volte ao mesmo número (tentativa 1, reinicios 1 depois de um
-- `systemctl restart plat-worker`). Só a exceção da tarefa (p_conta_tentativa = true) consome tentativa. Idempotente.
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
      tentativa = greatest(tentativa - 1, 0),   -- a retomada refaz job_pegar (+1): reinício não é tentativa
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
REVOKE EXECUTE ON FUNCTION plat.job_devolver(uuid, text, text, boolean, int, int, jsonb) FROM PUBLIC, plat_app;
GRANT EXECUTE ON FUNCTION plat.job_devolver(uuid, text, text, boolean, int, int, jsonb) TO plat_worker;
