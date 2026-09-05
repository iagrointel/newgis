-- 010_jobs_gatilhos_execute (integração T2; achado de tests/api/test_funcoes_seguras.py): as três funções de gatilho
-- da 004 (job_estado_final_imutavel, job_notificar, job_log_notificar) nasceram com EXECUTE para PUBLIC e para
-- plat_app pelo privilégio padrão da 001. Gatilho é disparado pelo dono da tabela; ninguém chama essas funções
-- diretamente. Idempotente.
REVOKE EXECUTE ON FUNCTION plat.job_estado_final_imutavel() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.job_notificar() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.job_log_notificar() FROM PUBLIC, plat_app;
