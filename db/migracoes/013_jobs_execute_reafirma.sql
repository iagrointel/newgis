-- 013_jobs_execute_reafirma (correção T2 (2)): a 011_catalogo faz `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO
-- plat_app` (padrão copiado da 001) e desfaz a separação da 006 — medido depois da reinstalação destrutiva de T2:
-- todas as funções do worker, inclusive via_worker_ligar, voltaram a ter EXECUTE para plat_app. Esta migração
-- reafirma o contrato (só plat_worker muda estado de job) e é idempotente. A rede de segurança permanente é
-- tests/api/jobs/test_jobs_transicoes.py::test_plat_app_nao_executa_as_funcoes_do_worker. Regra para as próximas
-- migrações: grant EXPLÍCITO por função, nunca ON ALL FUNCTIONS depois da 006.
DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.job_pegar(text, boolean)', 'plat.job_pid(uuid, text, int)', 'plat.job_heartbeat(uuid, text)',
    'plat.job_terminar(uuid, text, text, jsonb, text, jsonb)', 'plat.job_devolver(uuid, text, text, boolean, int, int, jsonb)',
    'plat.job_ceifar(int, int)', 'plat.worker_registrar(text, int, text, text, int)',
    'plat.worker_heartbeat(text, int, int)', 'plat.worker_desregistrar(text)', 'plat.worker_ceifar(int)',
    'plat.agenda_vencidas(timestamptz)', 'plat.agenda_enfileirar(uuid, timestamptz, timestamptz, boolean, boolean, int, int, text, int, text)',
    'plat.agenda_periodica_sincronizar(text, text, jsonb, text, text, timestamptz)', 'plat.jobs_no_dia(int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, plat_app', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_worker', f);
  END LOOP;
  FOREACH f IN ARRAY ARRAY['plat.via_worker_ligar()', 'plat.via_worker_desligar()', 'plat.job_transicao()',
                           'plat.job_estado_final_imutavel()', 'plat.job_notificar()', 'plat.job_log_notificar()'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, plat_app', f);
  END LOOP;
END $$;
