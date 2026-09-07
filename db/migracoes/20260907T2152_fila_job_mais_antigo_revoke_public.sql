-- fila_job_mais_antigo_revoke_public: a função plat.fila_job_mais_antigo_pendente_s() nasceu (migração
-- 20260907T1320_fila_job_mais_antigo.sql) com EXECUTE para PUBLIC — achado pelos portões transversais
-- tests/api/test_funcoes_seguras.py::test_nenhuma_funcao_com_execute_para_public e
-- tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app.
-- É o mesmo caso já tratado por 024_arquivos_revoke_public.sql: o default privilege de 003/006 não impede o
-- `=X/postgres` que toda função nova recebe, então cada função precisa do REVOKE explícito. A migração de origem
-- já foi aplicada, e migração aplicada não se edita (ADR 0014) — a correção vem neste arquivo novo.
-- Idempotente: REVOKE sem privilégio concedido não erra, e o GRANT ao papel da aplicação é repetido de propósito
-- para que uma base que só receba este arquivo fique com o mesmo estado final.
-- depende: 20260907T1320_fila_job_mais_antigo.sql
REVOKE EXECUTE ON FUNCTION plat.fila_job_mais_antigo_pendente_s() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.fila_job_mais_antigo_pendente_s() TO plat_app;
