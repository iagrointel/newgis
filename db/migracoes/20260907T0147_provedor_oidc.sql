-- Migração 20260907T0147 — provedor OpenID Connect por inquilino (item L0-08-a-oidc, irmão do L0-08-d-ldap;
-- mesma família L0-08-sso). Idempotente; sem BEGIN/COMMIT (padrão das demais migrações desta linha).
--
-- Decisões deste item (docs/adr/20260907T0147-oidc-authlib.md tem o raciocínio completo):
--  * um inquilino pode ter MAIS DE UM provedor OIDC (Esri deixa vários botões de entrada na mesma tela de
--    login: "rótulo" + "ordem" são exatamente isso), por isso a tabela é (tenant_id, id) e não (tenant_id)
--    único como o LDAP — o LDAP é sempre um único diretório corporativo, o OIDC pode ser vários IdPs;
--  * client_secret NUNCA em texto puro: mesma cifra AES-GCM (PLAT_SECRET) do LDAP/TOTP, prefixo próprio
--    'encoidc:v1:' (AAD distinta evita reuso cruzado entre módulos);
--  * a transação de login (state, nonce, verificador PKCE) fica em tabela própria, TTL curto, consumo
--    ATÔMICO por DELETE...RETURNING (linha usada uma vez só nunca serve de novo para reenviar outro
--    id_token — é a defesa direta contra a refutação "adversário reusa um code, troca o state");
--  * claim de identificador de login é 'sub' (nunca email — muda de titular, sub não; ADR Esri citado no
--    item), configurado no provedor UMA VEZ (mapa_claim_login), e usuario.sujeito_externo guarda 'sub' já
--    prefixado pelo issuer (dois IdPs diferentes podem reusar o mesmo valor de sub por coincidência);
--  * conta de origem 'oidc' nunca tem senha local nem TOTP local (fica inteiramente no IdP, como a Esri
--    documenta) — reforçado aqui pelo mesmo desenho da 003 (senha_hash NULL para origem <> 'local').

CREATE TABLE IF NOT EXISTS plat.provedor_oidc (
  id                  serial PRIMARY KEY,
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  habilitado          boolean NOT NULL DEFAULT true,
  rotulo              text NOT NULL DEFAULT 'Entrar com a organização',  -- texto do botão na tela de login
  ordem               int NOT NULL DEFAULT 0,                            -- ordem entre múltiplos provedores
  issuer              text NOT NULL,             -- 'https://idp/realms/x' (descoberta em /.well-known/openid-configuration)
  client_id           text NOT NULL,
  client_secret_cifrada text,                    -- NULL = client público (PKCE puro, sem segredo)
  escopos             text NOT NULL DEFAULT 'openid profile email',
  atributo_grupos     text NOT NULL DEFAULT 'groups',   -- nome do claim de grupos no id_token
  perfil_padrao       text CHECK (perfil_padrao IS NULL OR perfil_padrao IN ('admin','editor','visualizador','campo')),
  mapa_grupo_perfil   jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_por          int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_por      int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em           timestamptz NOT NULL DEFAULT now(),
  atualizado_em       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, issuer, client_id)
);

ALTER TABLE plat.provedor_oidc ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_provedor_oidc ON plat.provedor_oidc;
CREATE POLICY p_provedor_oidc ON plat.provedor_oidc FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- transação de login (state é a chave; nasce ANTES de existir sessão, por isso RLS não se aplica -- é lida/
-- apagada por função SECURITY DEFINER, nunca por SELECT direto do app). TTL de 10 minutos é conferido na
-- própria função de consumo (expirada = tratada como inexistente).
CREATE TABLE IF NOT EXISTS plat.oidc_transacao (
  state           text PRIMARY KEY,
  provedor_id     int NOT NULL REFERENCES plat.provedor_oidc(id) ON DELETE CASCADE,
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  nonce           text NOT NULL,
  code_verifier   text NOT NULL,
  redirect_uri    text NOT NULL,
  criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_oidc_transacao_criado_em ON plat.oidc_transacao(criado_em);

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/oidc_configurar', 'provedor OIDC do inquilino criado ou alterado (nunca grava o client_secret em claro no evento)'),
  ('org/oidc_remover', 'provedor OIDC do inquilino removido')
ON CONFLICT (nome) DO NOTHING;

-- pré-contexto (como plat.provedor_ldap_de/plat.auth_login): lista os provedores HABILITADOS do inquilino,
-- por slug, ordenados para a tela de login. Usado tanto por /api/login/provedores (botões) quanto por
-- /api/sso/oidc/iniciar (resolve o provedor escolhido).
DROP FUNCTION IF EXISTS plat.provedores_oidc_de(text);
CREATE OR REPLACE FUNCTION plat.provedores_oidc_de(p_tenant text)
RETURNS TABLE (provedor_id int, tenant_id int, tenant_ativo boolean, rotulo text, ordem int, issuer text,
               client_id text, client_secret_cifrada text, escopos text, atributo_grupos text,
               perfil_padrao text, mapa_grupo_perfil jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT po.id, t.id, t.ativo, po.rotulo, po.ordem, po.issuer, po.client_id, po.client_secret_cifrada,
         po.escopos, po.atributo_grupos, po.perfil_padrao, po.mapa_grupo_perfil
  FROM plat.tenant t JOIN plat.provedor_oidc po ON po.tenant_id = t.id
  WHERE t.slug = p_tenant AND po.habilitado = true
  ORDER BY po.ordem, po.id
$$;

-- um provedor específico por id (para /api/sso/oidc/retorno, que já sabe o provedor pela transação).
DROP FUNCTION IF EXISTS plat.provedor_oidc_por_id(int);
CREATE OR REPLACE FUNCTION plat.provedor_oidc_por_id(p_id int)
RETURNS TABLE (provedor_id int, tenant_id int, tenant_ativo boolean, tenant_slug text, config jsonb,
               habilitado boolean, rotulo text, issuer text, client_id text, client_secret_cifrada text,
               escopos text, atributo_grupos text, perfil_padrao text, mapa_grupo_perfil jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT po.id, t.id, t.ativo, t.slug, t.config, po.habilitado, po.rotulo, po.issuer, po.client_id,
         po.client_secret_cifrada, po.escopos, po.atributo_grupos, po.perfil_padrao, po.mapa_grupo_perfil
  FROM plat.provedor_oidc po JOIN plat.tenant t ON t.id = po.tenant_id
  WHERE po.id = p_id
$$;

-- abre a transação (INSERT simples, chamado com o state/nonce/verifier já gerados pelo Python -- segredos.
-- token gerados por secrets.token_urlsafe nunca no banco).
DROP FUNCTION IF EXISTS plat.oidc_transacao_abrir(int, int, text, text, text, text);
CREATE OR REPLACE FUNCTION plat.oidc_transacao_abrir(
  p_provedor_id int, p_tenant_id int, p_state text, p_nonce text, p_code_verifier text, p_redirect_uri text
) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.oidc_transacao(state, provedor_id, tenant_id, nonce, code_verifier, redirect_uri)
  VALUES (p_state, p_provedor_id, p_tenant_id, p_nonce, p_code_verifier, p_redirect_uri)
$$;

-- consumo ATÔMICO e de uso único: DELETE...RETURNING garante que duas requisições concorrentes com o MESMO
-- state nunca vejam as duas a linha (a segunda vê 0 linhas = 'state inválido ou já usado'). TTL de 10 min
-- aplicado aqui mesmo (linha expirada é apagada e tratada como ausente, sem exceção especial).
DROP FUNCTION IF EXISTS plat.oidc_transacao_consumir(text);
CREATE OR REPLACE FUNCTION plat.oidc_transacao_consumir(p_state text)
RETURNS TABLE (provedor_id int, tenant_id int, nonce text, code_verifier text, redirect_uri text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  -- um único DELETE...RETURNING: a linha só sai (e só serve) quando AINDA não expirou; uma linha
  -- expirada não-apagada aqui seria apagada pela limpeza periódica (oidc_transacao_limpar), nunca
  -- devolvida como válida por esta função
  RETURN QUERY DELETE FROM plat.oidc_transacao t
    WHERE t.state = p_state AND t.criado_em > now() - interval '10 minutes'
    RETURNING t.provedor_id, t.tenant_id, t.nonce, t.code_verifier, t.redirect_uri;
END $$;

-- limpeza de transações expiradas (chamada pela manutenção periódica, mesmo padrão de outras tabelas de
-- transação curta da casa; não é o único jeito de expirar -- oidc_transacao_consumir também recusa expirada).
DROP FUNCTION IF EXISTS plat.oidc_transacao_limpar();
CREATE OR REPLACE FUNCTION plat.oidc_transacao_limpar() RETURNS int
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  WITH apagadas AS (
    DELETE FROM plat.oidc_transacao WHERE criado_em <= now() - interval '10 minutes' RETURNING 1
  ) SELECT count(*)::int FROM apagadas
$$;

-- upsert de identidade federada por 'sub' (nunca por e-mail: o portão do item exige claim de identificador
-- ESTÁVEL). sujeito_externo grava '<issuer>#<sub>' para não colidir entre dois IdPs que reusem o mesmo sub.
-- Mesma regra do LDAP: nunca sobrescreve conta de origem 'local' com o mesmo login.
DROP FUNCTION IF EXISTS plat.oidc_provisionar(int, text, text, text, text, text, boolean);
CREATE OR REPLACE FUNCTION plat.oidc_provisionar(
  p_tenant_id int, p_login text, p_nome text, p_email text, p_perfil text, p_sujeito_externo text,
  p_ativo boolean DEFAULT true
) RETURNS TABLE (usuario_id int, criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record; existente_por_sub record;
BEGIN
  SELECT id, origem, perfil INTO existente FROM plat.usuario
    WHERE tenant_id = p_tenant_id AND login = lower(p_login);
  IF existente.id IS NOT NULL AND existente.origem <> 'oidc' THEN
    RAISE EXCEPTION 'login_em_uso_local';
  END IF;
  -- mesmo sub já provisionado sob outro login (usuário mudou o e-mail no IdP, por exemplo): atualiza pelo
  -- sub, nunca cria um segundo usuário para a mesma identidade estável.
  SELECT id, perfil INTO existente_por_sub FROM plat.usuario
    WHERE tenant_id = p_tenant_id AND origem = 'oidc' AND sujeito_externo = p_sujeito_externo;
  IF existente_por_sub.id IS NOT NULL THEN
    UPDATE plat.usuario SET login = lower(p_login), nome = p_nome, email = coalesce(p_email, email),
      perfil = p_perfil, ativo = p_ativo WHERE id = existente_por_sub.id;
    RETURN QUERY SELECT existente_por_sub.id, false, existente_por_sub.perfil;
  ELSIF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (p_tenant_id, lower(p_login), p_nome, p_email, p_perfil, 'oidc', p_sujeito_externo, p_ativo, NULL)
    RETURNING id INTO existente.id;
    RETURN QUERY SELECT existente.id, true, NULL::text;
  ELSE
    UPDATE plat.usuario SET nome = p_nome, email = coalesce(p_email, email), perfil = p_perfil,
      sujeito_externo = p_sujeito_externo, ativo = p_ativo WHERE id = existente.id;
    RETURN QUERY SELECT existente.id, false, existente.perfil;
  END IF;
END $$;

REVOKE EXECUTE ON FUNCTION plat.provedores_oidc_de(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.provedor_oidc_por_id(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.oidc_transacao_abrir(int, int, text, text, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.oidc_transacao_consumir(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.oidc_transacao_limpar() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.oidc_provisionar(int, text, text, text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.provedores_oidc_de(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.provedor_oidc_por_id(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.oidc_transacao_abrir(int, int, text, text, text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.oidc_transacao_consumir(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.oidc_transacao_limpar() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.oidc_provisionar(int, text, text, text, text, text, boolean) TO plat_app;
