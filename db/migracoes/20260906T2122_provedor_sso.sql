-- Migração 20260906T2122 — login federado OIDC e SAML 2.0 por inquilino (item L0-08-sso, pai do L0-08-d-ldap;
-- ADR 0002 seção 13 "Gancho para SSO" já deixou `usuario.origem` aceitar 'oidc'/'saml' e
-- `usuario.sujeito_externo` único por (tenant_id, origem); docs/adr/20260906T2122-sso-oidc-saml.md tem o
-- raciocínio completo). Idempotente; sem BEGIN/COMMIT (padrão das demais migrações desta linha).
--
-- Decisões deste item:
--  * config do PROVEDOR federado (emissor/entidade do IdP, cliente, certificado, mapa grupo→perfil) é por
--    inquilino E por protocolo, numa tabela própria `plat.provedor_sso` (mesmo padrão de plat.provedor_ldap:
--    tenant_id + RLS FOR ALL; UNIQUE (tenant_id, tipo) — um inquilino pode ter OIDC e SAML ao mesmo tempo,
--    como um órgão que tem gov.br (OIDC) para pessoa física e ADFS (SAML) para a rede interna);
--  * o segredo de cliente OIDC (quando o IdP exige cliente confidencial) é gravado CIFRADO com o mesmo
--    esquema AES-GCM do segredo TOTP/da senha de bind LDAP (prefixo próprio 'encsso:v1:', chave derivada de
--    PLAT_SECRET com AAD própria, nunca em texto puro, nunca devolvido pela API);
--  * o certificado do IdP SAML é chave PÚBLICA (valida assinatura de assertion) e vai em claro por definição;
--  * a transação do fluxo navegador (state/nonce/verificador PKCE do OIDC; ID do AuthnRequest do SAML) vive
--    em `plat.sso_transacao` com validade curta e consumo ATÔMICO (DELETE ... RETURNING): um state usado duas
--    vezes é replay e a segunda tentativa falha, mesmo com dois workers atendendo ao mesmo tempo;
--  * três funções SECURITY DEFINER sem exigir contexto de sessão (mesmo padrão de plat.provedor_ldap_de/
--    plat.auth_login, chamadas ANTES de existir sessão): plat.provedor_sso_de (lê a config pelo slug+tipo),
--    plat.sso_provisionar (upsert do usuário local após token/assertion validados) e plat.sso_transacao_*
--    (criar/consumir/limpar a transação pré-login); depois do upsert, o backend chama plat.auth_login de
--    novo e reaproveita _abrir_sessao (app/auth/rotas_login.py) — o mesmo caminho do login local e do LDAP
--    a partir do momento em que a identidade foi provada pelo provedor externo.

CREATE TABLE IF NOT EXISTS plat.provedor_sso (
  id                 serial PRIMARY KEY,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  tipo               text NOT NULL CHECK (tipo IN ('oidc','saml')),
  habilitado         boolean NOT NULL DEFAULT true,
  -- OIDC: emissor = issuer (a descoberta é <emissor>/.well-known/openid-configuration);
  -- SAML: idp_entidade = entityID do IdP e idp_url_sso = endpoint HTTP-Redirect de autenticação
  emissor            text,
  cliente_id         text,
  cliente_segredo_cifrado text,          -- 'encsso:v1:...'; NULL = cliente público (só PKCE)
  idp_entidade       text,
  idp_url_sso        text,
  idp_certificado    text,               -- PEM da chave PÚBLICA que assina assertions; nunca chave privada
  claim_grupos       text NOT NULL DEFAULT 'groups',  -- OIDC: nome do claim; SAML: nome do atributo
  claim_login        text,               -- OIDC: claim do login (NULL = preferred_username, caindo para email);
                                         -- SAML: atributo do login (NULL = NameID)
  perfil_padrao      text CHECK (perfil_padrao IS NULL OR perfil_padrao IN ('admin','editor','visualizador','campo')),
  mapa_grupo_perfil  jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"<grupo do IdP>": "<perfil da plataforma>"}
  criado_por         int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, tipo),
  -- coerência por protocolo: cada tipo exige os SEUS campos e nunca mistura vocabulário
  CHECK ((tipo = 'oidc' AND emissor IS NOT NULL AND cliente_id IS NOT NULL
          AND idp_entidade IS NULL AND idp_url_sso IS NULL AND idp_certificado IS NULL)
      OR (tipo = 'saml' AND idp_entidade IS NOT NULL AND idp_url_sso IS NOT NULL AND idp_certificado IS NOT NULL
          AND emissor IS NULL AND cliente_id IS NULL AND cliente_segredo_cifrado IS NULL))
);

ALTER TABLE plat.provedor_sso ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_provedor_sso ON plat.provedor_sso;
CREATE POLICY p_provedor_sso ON plat.provedor_sso FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- transação de login federado em andamento (pré-sessão; o navegador vai ao IdP e volta). `estado` é o
-- parâmetro state do OIDC e o RelayState do SAML — aleatório de 128 bits gerado pelo backend, nunca pelo
-- navegador. Consumo atômico por plat.sso_transacao_consumir (anti-replay).
CREATE TABLE IF NOT EXISTS plat.sso_transacao (
  estado             text PRIMARY KEY,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  tipo               text NOT NULL CHECK (tipo IN ('oidc','saml')),
  nonce              text,               -- OIDC: conferido contra o claim nonce do id_token
  verificador_pkce   text,               -- OIDC: code_verifier (S256); o desafio vai ao IdP, o verificador fica aqui
  pedido_id          text,               -- SAML: ID do AuthnRequest, conferido contra InResponseTo
  criado_em          timestamptz NOT NULL DEFAULT now(),
  expira_em          timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sso_transacao_expira ON plat.sso_transacao (expira_em);

-- RLS por tenant (a criação/consumo são pré-contexto via SECURITY DEFINER; a política protege leituras
-- diretas de sessão autenticada, padrão das demais tabelas com tenant_id)
ALTER TABLE plat.sso_transacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_sso_transacao ON plat.sso_transacao;
CREATE POLICY p_sso_transacao ON plat.sso_transacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- vocabulário novo de evento (append à tabela existente da 003; ON CONFLICT preserva reaplicação)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/sso_configurar', 'provedor de login federado (OIDC ou SAML) do inquilino criado ou alterado')
ON CONFLICT (nome) DO NOTHING;

-- pré-contexto (como plat.provedor_ldap_de): resolve pelo SLUG + tipo, sem sessão ainda. LEFT JOIN para o
-- tenant vir sempre (a rota decide 503 de suspenso igual ao login local) com os campos de provedor NULL
-- quando não há linha configurada.
DROP FUNCTION IF EXISTS plat.provedor_sso_de(text, text);
CREATE OR REPLACE FUNCTION plat.provedor_sso_de(p_tenant text, p_tipo text)
RETURNS TABLE (tenant_id int, tenant_ativo boolean, tenant_slug text, tenant_nome text, config jsonb,
               provedor_id int, habilitado boolean, emissor text, cliente_id text,
               cliente_segredo_cifrado text, idp_entidade text, idp_url_sso text, idp_certificado text,
               claim_grupos text, claim_login text, perfil_padrao text, mapa_grupo_perfil jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.id, t.ativo, t.slug, t.nome, t.config, p.id, p.habilitado, p.emissor, p.cliente_id,
         p.cliente_segredo_cifrado, p.idp_entidade, p.idp_url_sso, p.idp_certificado,
         p.claim_grupos, p.claim_login, p.perfil_padrao, p.mapa_grupo_perfil
  FROM plat.tenant t LEFT JOIN plat.provedor_sso p ON p.tenant_id = t.id AND p.tipo = p_tipo
  WHERE t.slug = p_tenant
$$;

-- upsert de identidade federada OIDC/SAML. NUNCA sobrescreve conta de OUTRA origem com o mesmo login
-- ('login_em_uso_outra_origem' — um adversário que descubra o login de um admin local não a assume
-- criando um homônimo no IdP; e um usuário LDAP não vira OIDC sem decisão do administrador, que apaga a
-- conta antiga primeiro). Devolve (criado, perfil_anterior) para o evento de domínio que a rota registra.
DROP FUNCTION IF EXISTS plat.sso_provisionar(int, text, text, text, text, text, text, boolean);
CREATE OR REPLACE FUNCTION plat.sso_provisionar(
  p_tenant_id int, p_origem text, p_login text, p_nome text, p_email text, p_perfil text,
  p_sujeito_externo text, p_ativo boolean DEFAULT true
) RETURNS TABLE (criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record;
BEGIN
  IF p_origem NOT IN ('oidc','saml') THEN
    RAISE EXCEPTION 'origem_invalida';
  END IF;
  SELECT id, origem, perfil INTO existente FROM plat.usuario
    WHERE tenant_id = p_tenant_id AND login = lower(p_login);
  IF existente.id IS NOT NULL AND existente.origem <> p_origem THEN
    RAISE EXCEPTION 'login_em_uso_outra_origem';
  END IF;
  IF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (p_tenant_id, lower(p_login), p_nome, p_email, p_perfil, p_origem, p_sujeito_externo, p_ativo, NULL);
    RETURN QUERY SELECT true, NULL::text;
  ELSE
    UPDATE plat.usuario SET nome = p_nome, email = coalesce(p_email, email), perfil = p_perfil,
      sujeito_externo = p_sujeito_externo, ativo = p_ativo
    WHERE id = existente.id;
    RETURN QUERY SELECT false, existente.perfil;
  END IF;
END $$;

-- cria a transação pré-login. `p_minutos` é a validade (curta; o módulo passa o limite de app/limites.py,
-- nunca um número solto na rota). Limpa de passagem as transações vencidas do MESMO inquilino (a limpeza
-- global fica com plat.sso_transacao_limpar, chamada também na criação — barata, tabela pequena por
-- construção: uma linha por tentativa de login em andamento).
DROP FUNCTION IF EXISTS plat.sso_transacao_criar(int, text, text, text, text, text, int);
CREATE OR REPLACE FUNCTION plat.sso_transacao_criar(
  p_tenant_id int, p_tipo text, p_estado text, p_nonce text, p_verificador_pkce text, p_pedido_id text,
  p_minutos int
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  DELETE FROM plat.sso_transacao WHERE expira_em < now();
  INSERT INTO plat.sso_transacao(estado, tenant_id, tipo, nonce, verificador_pkce, pedido_id, expira_em)
  VALUES (p_estado, p_tenant_id, p_tipo, p_nonce, p_verificador_pkce, p_pedido_id,
          now() + make_interval(mins => p_minutos));
END $$;

-- consome a transação ATOMICAMENTE (DELETE ... RETURNING): devolve a linha se ela existia e não estava
-- vencida, e a apaga no mesmo gesto — a segunda apresentação do mesmo state (replay) encontra nada e falha,
-- mesmo com dois workers atendendo em paralelo (o DELETE trava a linha até o commit).
DROP FUNCTION IF EXISTS plat.sso_transacao_consumir(text, text);
CREATE OR REPLACE FUNCTION plat.sso_transacao_consumir(p_estado text, p_tipo text)
RETURNS TABLE (tenant_id int, nonce text, verificador_pkce text, pedido_id text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  DELETE FROM plat.sso_transacao t
  WHERE t.estado = p_estado AND t.tipo = p_tipo AND t.expira_em >= now()
  RETURNING t.tenant_id, t.nonce, t.verificador_pkce, t.pedido_id
$$;

-- P6/segurança (mesmo raciocínio da 025): CREATE FUNCTION concede EXECUTE a PUBLIC por padrão; a revogação
-- explícita por função é o que test_nenhuma_funcao_com_execute_para_public confere — reafirmada aqui para
-- as 4 funções novas, nunca deixando PUBLIC executar identidade federada.
REVOKE EXECUTE ON FUNCTION plat.provedor_sso_de(text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.sso_provisionar(int, text, text, text, text, text, text, boolean) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.sso_transacao_criar(int, text, text, text, text, text, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.sso_transacao_consumir(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.provedor_sso_de(text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.sso_provisionar(int, text, text, text, text, text, text, boolean) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.sso_transacao_criar(int, text, text, text, text, text, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.sso_transacao_consumir(text, text) TO plat_app;
