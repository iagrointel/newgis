-- reaplicavel
-- 20260918T0120_rede_regra_politica_redundante: plat.rede_regra terminou com CINCO políticas RLS por
-- colisão de dois desenhos. A migração 20260906T2058_rede_regras_conectividade.sql (item
-- L4-03-a-regras-de-conectividade) deu à tabela o padrão do catálogo rede_* — 4 políticas por comando
-- (p_rede_regra_ler/inserir/alterar/apagar, todas `TO plat_app` com `tenant_id = plat.tenant_atual()`,
-- e a de INSERT mais estrita: exige também plat.usuario_do_inquilino()). A migração
-- 20260908T1934_regras_atributo_rede.sql (item L4-29), escrita numa árvore onde 2058 estava apagada
-- por fusão, fez DROP POLICY IF EXISTS p_rede_regra + CREATE POLICY p_rede_regra FOR ALL no padrão
-- ANTIGO de política única — sem perceber que a tabela já tinha as 4 do padrão novo. Resultado medido
-- no schema da trilha: 5 políticas, e tests/api/test_rede_pacote.py::
-- test_toda_tabela_do_catalogo_tem_rls_ligada (contrato "4 políticas por tabela de catálogo") reprova.
--
-- A FOR ALL é redundante estrita: políticas permissivas combinam por OU, e os 4 comandos já cobrem
-- r/w/a/d para o mesmo papel com o MESMO predicado. Efeito colateral bom: o INSERT hoje passava pela
-- FOR ALL só com tenant; sem ela vale a política de INSERT estrita (tenant E usuário do inquilino) —
-- toda escrita em rede_regra acontece dentro de requisição autenticada (importação de pacote,
-- importação de CSV de regras), nunca em job sem usuário, então nada legítimo muda.
-- Idempotente (DROP POLICY IF EXISTS). Sem BEGIN/COMMIT. Aplicada como postgres.

DROP POLICY IF EXISTS p_rede_regra ON plat.rede_regra;
