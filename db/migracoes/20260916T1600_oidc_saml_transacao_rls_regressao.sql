-- Conserto de regressão (achado 16/09/2026, tests/api/adversario/test_l0_tenancy.py::
-- test_toda_tabela_com_tenant_id_tem_rls_e_politica): plat.oidc_transacao (20260907T0147_provedor_oidc.sql)
-- e plat.saml_transacao/plat.saml_sessao/plat.saml_assercao_usada (20260907T2050_provedor_saml.sql) têm
-- coluna tenant_id e NENHUMA tem RLS ligada. O comentário original das duas migrações ("tabela pré-sessão
-- não tem RLS nem GRANT direto; só passa pelas funções SECURITY DEFINER") ficou falso na prática: a 001
-- (`ALTER DEFAULT PRIVILEGES ... GRANT ... ON TABLES TO plat_app`) concede SELECT/INSERT/UPDATE/DELETE a
-- QUALQUER tabela nova do schema automaticamente, e nenhuma das duas migrações revogou depois (o padrão
-- que 047_smtp_convites_redefinicao.sql segue para `redefinicao_pedido`, tabela SEM tenant_id). MEDIDO
-- na trilha: plat_app tinha SELECT/INSERT/UPDATE/DELETE direto nas quatro tabelas, RLS desligada nas
-- quatro — uma consulta direta de plat_app (fora das funções) lê/edita transação de login OIDC/SAML de
-- OUTRO inquilino.
--
-- Como as quatro têm tenant_id (ao contrário de redefinicao_pedido), o conserto segue o padrão de
-- plat.sso_transacao (20260906T2122_provedor_sso.sql, a MESMA classe de tabela pré-sessão, mas com RLS +
-- política por tenant): ENABLE ROW LEVEL SECURITY + política FOR ALL TO plat_app filtrando por
-- tenant_id = plat.tenant_atual(). As funções SECURITY DEFINER (oidc_transacao_abrir/consumir/limpar,
-- saml_transacao_abrir/consumir, saml_sessao_*, etc.) continuam livres: rodam como o dono da função/tabela,
-- que por padrão do Postgres ignora RLS (sem FORCE ROW LEVEL SECURITY, que não é preciso aqui). Idempotente.

ALTER TABLE plat.oidc_transacao      ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.saml_transacao      ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.saml_sessao         ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.saml_assercao_usada ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_oidc_transacao ON plat.oidc_transacao;
CREATE POLICY p_oidc_transacao ON plat.oidc_transacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_saml_transacao ON plat.saml_transacao;
CREATE POLICY p_saml_transacao ON plat.saml_transacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_saml_sessao ON plat.saml_sessao;
CREATE POLICY p_saml_sessao ON plat.saml_sessao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_saml_assercao_usada ON plat.saml_assercao_usada;
CREATE POLICY p_saml_assercao_usada ON plat.saml_assercao_usada FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
