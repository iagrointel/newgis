-- 20260906T1804_acervo_frescor_rls: RLS que faltou em `plat.acervo_frescor_execucao` (item
-- L6-01-h-frescor-verificacao, migração 20260906T1617_acervo_frescor.sql).
--
-- Achado rodando `tests/api/test_migracoes.py::test_toda_tabela_com_tenant_id_tem_rls_e_politica` (invariante
-- da casa: toda tabela com `tenant_id` tem RLS + política): a 20260906T1617 dá `GRANT SELECT` de
-- `plat.acervo_frescor_execucao` a `plat_app` (para `GET /api/acervo/frescor/execucoes`) mas nunca ligou RLS
-- na tabela — sem isto qualquer inquilino lê a linha de execução de QUALQUER outro (na prática, hoje só o
-- inquilino técnico `plataforma` grava ali, mas a política tem de existir mesmo assim; é a mesma classe de
-- lacuna que `plat.conexao_saude_historico`, 036, já resolveu). As outras duas tabelas da mesma migração
-- (`acervo_camada_verificacao`, `acervo_endpoint_verificacao`) não têm coluna `tenant_id` — ficam de fora
-- de propósito, a chave delas é `acervo_camada_id`/`fonte_id`, registro global do acervo (027).
--
-- Correção em arquivo NOVO (a 20260906T1617 já foi aplicada nesta e talvez em outras bases; editar arquivo
-- aplicado para migrar.sh com código 3). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.acervo_frescor_execucao ENABLE ROW LEVEL SECURITY;

-- só leitura para plat_app, por inquilino; nenhuma política de escrita — só as funções SECURITY DEFINER da
-- 20260906T1617 gravam ali (dono da tabela, ignoram RLS), mesmo padrão de `plat.conexao_saude_historico` (036).
DROP POLICY IF EXISTS p_acervo_frescor_execucao_ler ON plat.acervo_frescor_execucao;
CREATE POLICY p_acervo_frescor_execucao_ler ON plat.acervo_frescor_execucao FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
