-- depende: 20260907T0147_provedor_oidc.sql
-- SAML 2.0 Web SSO por inquilino (item L0-08-b-saml). UMA identidade: a conta externa continua sendo
-- plat.usuario (origem='saml', sujeito_externo = entityId do IdP + '#' + NameID; índice único já existe em
-- 003_identidade_acesso.sql) e o provisionamento é a MESMA função do OIDC, generalizada pela origem
-- (plat.usuario_externo_provisionar; plat.oidc_provisionar vira apenas um atalho). Só a configuração do provedor
-- é própria (plat.provedor_saml espelha plat.provedor_oidc: vários por inquilino, rótulo, ordem, RLS).

CREATE TABLE IF NOT EXISTS plat.provedor_saml (
  id serial PRIMARY KEY,
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  habilitado boolean NOT NULL DEFAULT true,
  rotulo text NOT NULL DEFAULT 'Entrar com a organização (SAML)',
  ordem int NOT NULL DEFAULT 0,
  idp_entity_id text NOT NULL,
  idp_sso_url text NOT NULL,
  idp_slo_url text,
  idp_certificados text[] NOT NULL,             -- base64 DER (sem cabeçalho PEM); vários = rotação de chave no IdP
  idp_metadado_url text,                        -- de onde o metadado veio (URL), quando veio de URL
  idp_metadado_xml text,                        -- cópia do metadado lido (URL ou arquivo), para auditoria
  sp_chave_privada_cifrada text NOT NULL,       -- AES-GCM com PLAT_SECRET (prefixo encsaml:v1:), nunca em claro
  sp_certificado text NOT NULL,                 -- base64 DER do certificado autoassinado do SP (público)
  assercao_cifrada boolean NOT NULL DEFAULT false,  -- exigir EncryptedAssertion (a decifra é sempre aceita)
  formato_nameid text NOT NULL DEFAULT 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified',
  atributo_login text,                          -- NULL = o NameID é o login
  atributo_email text NOT NULL DEFAULT 'email',
  atributo_nome text NOT NULL DEFAULT 'name',
  atributo_grupos text NOT NULL DEFAULT 'groups',
  perfil_padrao text CHECK (perfil_padrao IS NULL OR perfil_padrao IN ('admin','editor','visualizador','campo')),
  mapa_grupo_perfil jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_por int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_por int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idp_entity_id)
);
ALTER TABLE plat.provedor_saml ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_provedor_saml ON plat.provedor_saml;
CREATE POLICY p_provedor_saml ON plat.provedor_saml FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.provedor_saml TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.provedor_saml_id_seq TO plat_app;

-- transação pré-sessão (AuthnRequest e LogoutRequest emitidos por nós): id da mensagem = chave; uso único.
CREATE TABLE IF NOT EXISTS plat.saml_transacao (
  id text PRIMARY KEY,
  tipo text NOT NULL CHECK (tipo IN ('login','logout')),
  provedor_id int NOT NULL REFERENCES plat.provedor_saml(id) ON DELETE CASCADE,
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  relay text,
  criado_em timestamptz NOT NULL DEFAULT now()
);
-- cache de IDs de asserção aceitos, até o NotOnOrAfter delas: a mesma asserção nunca abre duas sessões.
CREATE TABLE IF NOT EXISTS plat.saml_assercao_usada (
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  id text NOT NULL,
  expira_em timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, id)
);
-- vínculo sessão local <-> sessão no IdP (NameID + SessionIndex) para o logout propagado nos dois sentidos.
CREATE TABLE IF NOT EXISTS plat.saml_sessao (
  sessao_hash text PRIMARY KEY,
  provedor_id int NOT NULL REFERENCES plat.provedor_saml(id) ON DELETE CASCADE,
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  name_id text NOT NULL,
  name_id_format text,
  session_index text,
  criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_saml_sessao_nameid ON plat.saml_sessao (provedor_id, name_id);

-- ---------------------------------------------------------------- funções (SECURITY DEFINER: as tabelas
-- pré-sessão não têm RLS nem GRANT direto; só passam por aqui)
DROP FUNCTION IF EXISTS plat.provedores_saml_de(text);
CREATE OR REPLACE FUNCTION plat.provedores_saml_de(p_tenant text)
RETURNS TABLE (provedor_id int, tenant_id int, rotulo text, ordem int)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT ps.id, ps.tenant_id, ps.rotulo, ps.ordem
  FROM plat.provedor_saml ps JOIN plat.tenant t ON t.id = ps.tenant_id
  WHERE t.slug = p_tenant AND ps.habilitado
  ORDER BY ps.ordem, ps.id
$$;

DROP FUNCTION IF EXISTS plat.provedor_saml_por_id(int);
CREATE OR REPLACE FUNCTION plat.provedor_saml_por_id(p_id int)
RETURNS TABLE (provedor_id int, tenant_id int, tenant_ativo boolean, tenant_slug text, config jsonb,
               habilitado boolean, rotulo text, idp_entity_id text, idp_sso_url text, idp_slo_url text,
               idp_certificados text[], sp_chave_privada_cifrada text, sp_certificado text,
               assercao_cifrada boolean, formato_nameid text, atributo_login text, atributo_email text,
               atributo_nome text, atributo_grupos text, perfil_padrao text, mapa_grupo_perfil jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT ps.id, t.id, t.ativo, t.slug, t.config, ps.habilitado, ps.rotulo, ps.idp_entity_id, ps.idp_sso_url,
         ps.idp_slo_url, ps.idp_certificados, ps.sp_chave_privada_cifrada, ps.sp_certificado,
         ps.assercao_cifrada, ps.formato_nameid, ps.atributo_login, ps.atributo_email, ps.atributo_nome,
         ps.atributo_grupos, ps.perfil_padrao, ps.mapa_grupo_perfil
  FROM plat.provedor_saml ps JOIN plat.tenant t ON t.id = ps.tenant_id
  WHERE ps.id = p_id
$$;

DROP FUNCTION IF EXISTS plat.provedores_saml_por_issuer(text);
CREATE OR REPLACE FUNCTION plat.provedores_saml_por_issuer(p_entity_id text)
RETURNS TABLE (provedor_id int, tenant_id int)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT ps.id, ps.tenant_id FROM plat.provedor_saml ps
  WHERE ps.idp_entity_id = p_entity_id AND ps.habilitado ORDER BY ps.id
$$;

DROP FUNCTION IF EXISTS plat.saml_transacao_abrir(text, text, int, int, text);
CREATE OR REPLACE FUNCTION plat.saml_transacao_abrir(p_id text, p_tipo text, p_provedor_id int, p_tenant_id int, p_relay text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.saml_transacao(id, tipo, provedor_id, tenant_id, relay) VALUES (p_id, p_tipo, p_provedor_id, p_tenant_id, p_relay)
$$;

DROP FUNCTION IF EXISTS plat.saml_transacao_consumir(text);
CREATE OR REPLACE FUNCTION plat.saml_transacao_consumir(p_id text)
RETURNS TABLE (tipo text, provedor_id int, tenant_id int, relay text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  RETURN QUERY DELETE FROM plat.saml_transacao t
    WHERE t.id = p_id AND t.criado_em > now() - interval '10 minutes'
    RETURNING t.tipo, t.provedor_id, t.tenant_id, t.relay;
END $$;

DROP FUNCTION IF EXISTS plat.saml_transacao_limpar();
CREATE OR REPLACE FUNCTION plat.saml_transacao_limpar() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  DELETE FROM plat.saml_transacao WHERE criado_em < now() - interval '10 minutes';
  GET DIAGNOSTICS n = ROW_COUNT;
  DELETE FROM plat.saml_assercao_usada WHERE expira_em < now() - interval '1 hour';
  DELETE FROM plat.saml_sessao s WHERE NOT EXISTS (SELECT 1 FROM plat.sessao x WHERE x.token_hash = s.sessao_hash);
  RETURN n;
END $$;

-- true na primeira vez; false quando o id já foi aceito (replay). A linha vive até expirar + 1 h.
DROP FUNCTION IF EXISTS plat.saml_assercao_registrar(int, text, timestamptz);
CREATE OR REPLACE FUNCTION plat.saml_assercao_registrar(p_tenant_id int, p_id text, p_expira timestamptz)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  INSERT INTO plat.saml_assercao_usada(tenant_id, id, expira_em) VALUES (p_tenant_id, p_id, coalesce(p_expira, now() + interval '1 hour'))
  ON CONFLICT DO NOTHING;
  RETURN FOUND;
END $$;

DROP FUNCTION IF EXISTS plat.saml_sessao_abrir(text, int, int, text, text, text);
CREATE OR REPLACE FUNCTION plat.saml_sessao_abrir(p_hash text, p_provedor_id int, p_tenant_id int, p_name_id text, p_formato text, p_session_index text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.saml_sessao(sessao_hash, provedor_id, tenant_id, name_id, name_id_format, session_index)
  VALUES (p_hash, p_provedor_id, p_tenant_id, p_name_id, p_formato, p_session_index)
  ON CONFLICT (sessao_hash) DO UPDATE SET provedor_id = EXCLUDED.provedor_id, name_id = EXCLUDED.name_id,
    name_id_format = EXCLUDED.name_id_format, session_index = EXCLUDED.session_index
$$;

DROP FUNCTION IF EXISTS plat.saml_sessao_apagar(text);
CREATE OR REPLACE FUNCTION plat.saml_sessao_apagar(p_hash text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  DELETE FROM plat.saml_sessao WHERE sessao_hash = p_hash
$$;

DROP FUNCTION IF EXISTS plat.saml_sessao_por_hash(text);
CREATE OR REPLACE FUNCTION plat.saml_sessao_por_hash(p_hash text)
RETURNS TABLE (provedor_id int, tenant_id int, name_id text, name_id_format text, session_index text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT s.provedor_id, s.tenant_id, s.name_id, s.name_id_format, s.session_index FROM plat.saml_sessao s WHERE s.sessao_hash = p_hash
$$;

-- logout vindo do IdP (LogoutRequest): encerra TODA sessão local ligada ao NameID (e ao SessionIndex, se veio).
DROP FUNCTION IF EXISTS plat.saml_sessao_encerrar(int, text, text);
CREATE OR REPLACE FUNCTION plat.saml_sessao_encerrar(p_provedor_id int, p_name_id text, p_session_index text)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT sessao_hash FROM plat.saml_sessao
           WHERE provedor_id = p_provedor_id AND name_id = p_name_id
             AND (p_session_index IS NULL OR session_index IS NULL OR session_index = p_session_index) LOOP
    PERFORM plat.auth_sessao_encerrar(r.sessao_hash);
    DELETE FROM plat.saml_sessao WHERE sessao_hash = r.sessao_hash;
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;

-- identidade externa: uma função para toda origem federada; a do OIDC passa a delegar (mesmo contrato).
DROP FUNCTION IF EXISTS plat.usuario_externo_provisionar(int, text, text, text, text, text, text, boolean);
CREATE OR REPLACE FUNCTION plat.usuario_externo_provisionar(
  p_tenant_id int, p_origem text, p_login text, p_nome text, p_email text, p_perfil text, p_sujeito_externo text,
  p_ativo boolean DEFAULT true
) RETURNS TABLE (usuario_id int, criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record; existente_por_sub record;
BEGIN
  IF p_origem NOT IN ('oidc', 'saml', 'ldap') THEN
    RAISE EXCEPTION 'origem_invalida';
  END IF;
  SELECT id, origem, perfil INTO existente FROM plat.usuario
    WHERE tenant_id = p_tenant_id AND login = lower(p_login);
  IF existente.id IS NOT NULL AND existente.origem <> p_origem THEN
    RAISE EXCEPTION 'login_em_uso_local';
  END IF;
  SELECT id, perfil INTO existente_por_sub FROM plat.usuario
    WHERE tenant_id = p_tenant_id AND origem = p_origem AND sujeito_externo = p_sujeito_externo;
  IF existente_por_sub.id IS NOT NULL THEN
    UPDATE plat.usuario SET login = lower(p_login), nome = p_nome, email = coalesce(p_email, email),
      perfil = p_perfil, ativo = p_ativo WHERE id = existente_por_sub.id;
    RETURN QUERY SELECT existente_por_sub.id, false, existente_por_sub.perfil;
  ELSIF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (p_tenant_id, lower(p_login), p_nome, p_email, p_perfil, p_origem, p_sujeito_externo, p_ativo, NULL)
    RETURNING id INTO existente.id;
    RETURN QUERY SELECT existente.id, true, NULL::text;
  ELSE
    UPDATE plat.usuario SET nome = p_nome, email = coalesce(p_email, email), perfil = p_perfil,
      sujeito_externo = p_sujeito_externo, ativo = p_ativo WHERE id = existente.id;
    RETURN QUERY SELECT existente.id, false, existente.perfil;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION plat.oidc_provisionar(
  p_tenant_id int, p_login text, p_nome text, p_email text, p_perfil text, p_sujeito_externo text,
  p_ativo boolean DEFAULT true
) RETURNS TABLE (usuario_id int, criado boolean, perfil_anterior text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT * FROM plat.usuario_externo_provisionar(p_tenant_id, 'oidc', p_login, p_nome, p_email, p_perfil, p_sujeito_externo, p_ativo)
$$;

REVOKE EXECUTE ON FUNCTION plat.provedores_saml_de(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.provedor_saml_por_id(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.provedores_saml_por_issuer(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_transacao_abrir(text, text, int, int, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_transacao_consumir(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_transacao_limpar() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_assercao_registrar(int, text, timestamptz) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_sessao_abrir(text, int, int, text, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_sessao_por_hash(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_sessao_apagar(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.saml_sessao_encerrar(int, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuario_externo_provisionar(int, text, text, text, text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.provedores_saml_de(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.provedor_saml_por_id(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.provedores_saml_por_issuer(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_transacao_abrir(text, text, int, int, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_transacao_consumir(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_transacao_limpar() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_assercao_registrar(int, text, timestamptz) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_sessao_abrir(text, int, int, text, text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_sessao_por_hash(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_sessao_apagar(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.saml_sessao_encerrar(int, text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.usuario_externo_provisionar(int, text, text, text, text, text, text, boolean) TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/saml_configurar', 'provedor SAML criado ou alterado (L0-08-b)'),
  ('org/saml_remover', 'provedor SAML removido (L0-08-b)')
ON CONFLICT (nome) DO NOTHING;
