-- Migração 034 — configurações da organização/inquilino (item L0-07-a-configuracoes-org): GET/PUT /api/org
-- (app/auth/rotas_org.py). Não cria tabela nova: nome fica em plat.tenant.nome, cota de armazenamento em
-- plat.tenant.cota_bytes (já existentes, já lidos ao vivo por GET /api/arquivos), e o resto (cor, logo,
-- mapa padrão, idioma padrão, cota de usuários, auth) em plat.tenant.config — mesmo padrão de
-- plat.cota_itens/plat.cota_jobs_dia (011/004): número em tenant.config, função lê com COALESCE do padrão,
-- nunca hardcoded na rota. `config.auth` já existe desde o L0-02 (app/auth/politica.py); esta migração só
-- acrescenta a cota de usuários e o vocabulário de evento da tela nova.
-- Idempotente; sem BEGIN/COMMIT.

-- cota de usuários do inquilino: tenant.config.cota_usuarios, padrão em app/limites.py ORG_COTA_USUARIOS_PADRAO
-- (2000: bem acima do maior lote de criação, LOTE_MAX=100, e do uso medido no inquilino de demonstração em T3,
-- 59 usuários — um padrão baixo quebraria a suíte inteira toda vez que outra trilha cria usuário de teste).
CREATE OR REPLACE FUNCTION plat.cota_usuarios(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_usuarios')::int, 2000) FROM plat.tenant WHERE id = p_tenant
$$;

-- usuários ATIVOS contam para a cota (desabilitar libera vaga; apagar também, mas apagar já exige "sem grupo
-- e sem conteúdo" — regra que já existia antes desta migração)
CREATE OR REPLACE FUNCTION plat.usuarios_ativos(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*)::int FROM plat.usuario WHERE tenant_id = p_tenant AND ativo
$$;

-- vocabulário novo de evento (append à tabela existente da 003; ON CONFLICT preserva reaplicação)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/configurar', 'configuração do inquilino alterada (nome, cor, mapa padrão, idioma, cotas, política de senha, exigir 2FA, domínios de e-mail)'),
  ('org/logo_enviar', 'logotipo do inquilino enviado (reaproveita plat.arquivo, classe org_logo)'),
  ('org/logo_remover', 'logotipo do inquilino removido')
ON CONFLICT (nome) DO NOTHING;

-- P6/segurança (migração 003 linha 834 em diante; teste test_nenhuma_funcao_com_execute_para_public): toda
-- função nova revoga PUBLIC explicitamente e concede só a plat_app.
REVOKE EXECUTE ON FUNCTION plat.cota_usuarios(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuarios_ativos(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.cota_usuarios(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.usuarios_ativos(int) TO plat_app;
