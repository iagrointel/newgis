-- 002_identidade: tenant, usuario, sessao, token_servico, log_acesso; RLS por inquilino; funções auth_*
-- SECURITY DEFINER (ADR 0001 seção 6; corpos seguem esquema do SIG de teste interno, adaptados a token_hash e a
-- tenant_id em sessao). Semeia os inquilinos demo e demo2; os administradores nascem no install.sh
-- (senha nunca em SQL do repositório). Idempotente. Sem BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS plat.tenant (
  id           serial PRIMARY KEY,
  slug         text UNIQUE NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,38}$'),
  nome         text NOT NULL,
  ativo        boolean NOT NULL DEFAULT true,
  config       jsonb NOT NULL DEFAULT '{}'::jsonb,
  cota_bytes   bigint NOT NULL DEFAULT 21474836480,
  criado_em    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plat.usuario (
  id                 serial PRIMARY KEY,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  login              text NOT NULL CHECK (login = lower(login)),
  nome               text NOT NULL,
  email              text,
  senha_hash         text NOT NULL,
  perfil             text NOT NULL CHECK (perfil IN ('admin','editor','visualizador','campo')),
  superadmin         boolean NOT NULL DEFAULT false,
  ativo              boolean NOT NULL DEFAULT true,
  totp_secret        text,
  totp_ativo         boolean NOT NULL DEFAULT false,
  senha_alterada_em  timestamptz,
  falhas_login       int NOT NULL DEFAULT 0,
  bloqueado_ate      timestamptz,
  ultimo_login       timestamptz,
  criado_em          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, login)
);

CREATE TABLE IF NOT EXISTS plat.sessao (
  token_hash   text PRIMARY KEY,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  usuario_id   int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  expira_em    timestamptz NOT NULL,
  ultimo_uso   timestamptz,
  ip           text,
  agente       text
);

CREATE TABLE IF NOT EXISTS plat.token_servico (
  id           serial PRIMARY KEY,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  usuario_id   int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  nome         text NOT NULL,
  token_hash   text NOT NULL UNIQUE,
  prefixo      text NOT NULL,
  escopos      text[] NOT NULL DEFAULT '{}',
  restricao    jsonb NOT NULL DEFAULT '{}'::jsonb,
  expira_em    timestamptz,
  revogado_em  timestamptz,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  ultimo_uso   timestamptz,
  ultimo_ip    text
);

CREATE TABLE IF NOT EXISTS plat.log_acesso (
  id           bigserial PRIMARY KEY,
  em           timestamptz NOT NULL DEFAULT now(),
  tenant_id    int,
  usuario_id   int,
  token_id     int,
  ip           text,
  metodo       text NOT NULL,
  rota         text NOT NULL,
  status       int NOT NULL,
  bytes        bigint NOT NULL DEFAULT 0,
  tempo_ms     int NOT NULL,
  agente       text,
  resultado    text
);
CREATE INDEX IF NOT EXISTS ix_log_acesso_tenant_em ON plat.log_acesso (tenant_id, em DESC);
CREATE INDEX IF NOT EXISTS ix_log_acesso_token_em  ON plat.log_acesso (token_id, em DESC) WHERE token_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_sessao_usuario       ON plat.sessao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_token_tenant         ON plat.token_servico (tenant_id);

-- ---------------------------------------------------------------- RLS (FOR ALL, USING + WITH CHECK)
ALTER TABLE plat.tenant        ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.usuario       ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.sessao        ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.token_servico ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.log_acesso    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_tenant ON plat.tenant;
CREATE POLICY p_tenant ON plat.tenant FOR ALL TO plat_app
  USING (id = plat.tenant_atual()) WITH CHECK (id = plat.tenant_atual());
DROP POLICY IF EXISTS p_usuario ON plat.usuario;
CREATE POLICY p_usuario ON plat.usuario FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_sessao ON plat.sessao;
CREATE POLICY p_sessao ON plat.sessao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_token_servico ON plat.token_servico;
CREATE POLICY p_token_servico ON plat.token_servico FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
-- log_acesso: leitura pelo inquilino; escrita só pela função plat.log_registrar (SECURITY DEFINER)
DROP POLICY IF EXISTS p_log_acesso ON plat.log_acesso;
CREATE POLICY p_log_acesso ON plat.log_acesso FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
REVOKE INSERT, UPDATE, DELETE ON plat.log_acesso FROM plat_app;

-- ---------------------------------------------------------------- funções de autenticação (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION plat.auth_login(p_tenant text, p_login text)
RETURNS TABLE (usuario_id int, tenant_id int, senha_hash text, perfil text, nome text, tenant_nome text,
               totp_ativo boolean, totp_secret text, bloqueado_ate timestamptz, falhas_login int, superadmin boolean)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT u.id, u.tenant_id, u.senha_hash, u.perfil, u.nome, t.nome, u.totp_ativo, u.totp_secret,
         u.bloqueado_ate, u.falhas_login, u.superadmin
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE t.slug = p_tenant AND u.login = p_login AND u.ativo AND t.ativo
$$;

CREATE OR REPLACE FUNCTION plat.auth_falha(p_usuario int, p_max int, p_min int) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.usuario SET falhas_login = falhas_login + 1,
    bloqueado_ate = CASE WHEN falhas_login + 1 >= p_max THEN now() + (p_min || ' minutes')::interval ELSE bloqueado_ate END
  WHERE id = p_usuario
$$;

CREATE OR REPLACE FUNCTION plat.auth_ok(p_usuario int) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.usuario SET falhas_login = 0, bloqueado_ate = NULL, ultimo_login = now() WHERE id = p_usuario
$$;

CREATE OR REPLACE FUNCTION plat.auth_sessao_criar(p_usuario int, p_horas int, p_ip text, p_agente text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tok text; tid int;
BEGIN
  SELECT u.tenant_id INTO tid FROM plat.usuario u WHERE u.id = p_usuario AND u.ativo;
  IF tid IS NULL THEN RAISE EXCEPTION 'usuário inexistente ou inativo'; END IF;
  tok := encode(gen_random_bytes(32), 'hex');
  INSERT INTO plat.sessao(token_hash, tenant_id, usuario_id, expira_em, ip, agente, ultimo_uso)
  VALUES (encode(sha256(convert_to(tok, 'UTF8')), 'hex'), tid, p_usuario, now() + (p_horas || ' hours')::interval,
          p_ip, left(p_agente, 200), now());
  RETURN tok;
END $$;

CREATE OR REPLACE FUNCTION plat.auth_sessao(p_hash text)
RETURNS TABLE (usuario_id int, tenant_id int, login text, perfil text, nome text, tenant_slug text, tenant_nome text,
               superadmin boolean, config jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.sessao SET ultimo_uso = now() WHERE token_hash = p_hash AND expira_em > now();
  SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, t.slug, t.nome, u.superadmin, t.config
  FROM plat.sessao s JOIN plat.usuario u ON u.id = s.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE s.token_hash = p_hash AND s.expira_em > now() AND u.ativo AND t.ativo
$$;

CREATE OR REPLACE FUNCTION plat.auth_sessao_encerrar(p_hash text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  DELETE FROM plat.sessao WHERE token_hash = p_hash
$$;

CREATE OR REPLACE FUNCTION plat.auth_token(p_hash text, p_ip text)
RETURNS TABLE (usuario_id int, tenant_id int, login text, perfil text, escopos text[], restricao jsonb, token_id int)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.token_servico SET ultimo_uso = now(), ultimo_ip = p_ip
  WHERE token_hash = p_hash AND revogado_em IS NULL AND (expira_em IS NULL OR expira_em > now());
  SELECT u.id, u.tenant_id, u.login, u.perfil, k.escopos, k.restricao, k.id
  FROM plat.token_servico k JOIN plat.usuario u ON u.id = k.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE k.token_hash = p_hash AND k.revogado_em IS NULL AND (k.expira_em IS NULL OR k.expira_em > now())
    AND u.ativo AND t.ativo
$$;

CREATE OR REPLACE FUNCTION plat.log_registrar(p_tenant int, p_usuario int, p_token int, p_ip text, p_metodo text,
  p_rota text, p_status int, p_bytes bigint, p_tempo_ms int, p_agente text, p_resultado text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente, resultado)
  VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
          p_tempo_ms, left(p_agente, 200), p_resultado)
$$;

CREATE OR REPLACE FUNCTION plat.tenant_criar(p_slug text, p_nome text, p_config jsonb, p_admin_login text,
  p_admin_nome text, p_senha_hash text)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; uid int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.usuario WHERE id = plat.usuario_atual() AND superadmin AND ativo) THEN
    RAISE EXCEPTION 'só superadmin cria inquilino';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config) VALUES (p_slug, p_nome, coalesce(p_config, '{}'::jsonb)) RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin') RETURNING id INTO uid;
  RETURN QUERY SELECT tid, uid;
END $$;

-- ---------------------------------------------------------------- inquilinos de demonstração (dado aberto, sem nome de cliente)
INSERT INTO plat.tenant(slug, nome, config)
VALUES ('demo', 'Inquilino de demonstração', '{"centro": [-47.93, -15.78], "zoom": 4}'::jsonb),
       ('demo2', 'Segundo inquilino de demonstração', '{"centro": [-43.17, -22.91], "zoom": 4}'::jsonb)
ON CONFLICT (slug) DO NOTHING;
