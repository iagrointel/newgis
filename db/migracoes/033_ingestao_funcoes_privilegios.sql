-- 033_ingestao_funcoes_privilegios: fecha o PUBLIC (e o EXECUTE direto de plat_app nas de gatilho) das funções
-- criadas pela 029 (item L0-04-ingest-vetor). Achado do testador (test_eventos_e_seguranca.py::
-- test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app): toda função nova em `plat` nasce com
-- EXECUTE para PUBLIC nesta instalação (a regra ADR 0001/0002 é reforçada por REVOKE explícito depois de
-- CREATE, não só por ALTER DEFAULT PRIVILEGES — mesmo padrão já usado em 010_jobs_gatilhos_execute.sql para
-- plat.job_estado_final_imutavel e em 016_catalogo_apagar_usuario.sql para plat.tg_item_antes).
--
-- Gatilho puro (nunca chamado direto pela API): fecha para PUBLIC e plat_app também — só o mecanismo de
-- gatilho do Postgres precisa rodar, sem checagem de EXECUTE.
REVOKE EXECUTE ON FUNCTION plat.importacao_estado_final_imutavel() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.feicao_inserir() FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.feicao_versao() FROM PUBLIC, plat_app;

-- Chamadas diretamente por app/ingestao/carregar.py via `SELECT plat.<fn>(...)` como plat_app: fecha só PUBLIC.
REVOKE EXECUTE ON FUNCTION plat.camada_schema_garantir(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) TO plat_app;
