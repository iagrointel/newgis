-- 047_smtp_convites_redefinicao: item L0-07-d-smtp-convites (ADR 0013). SMTP por inquilino vive em
-- `plat.tenant.config->'smtp'` (mesma coluna jsonb que L0-07-a já usa, chave nova, sem migrar dado nenhum);
-- convite de membro (plat.convite) e redefinição de senha por e-mail (plat.redefinicao_senha) com token de
-- uso único; plat.redefinicao_pedido só para o limite de taxa (chave = inquilino|e-mail, sem FK: tem de
-- registrar a tentativa mesmo quando o inquilino/e-mail não existe, senão o limite vaza existência por
-- omissão). Funções SECURITY DEFINER (mesmo padrão de auth_login/auth_sessao da 002): o convite e a
-- redefinição são resolvidos e aceitos ANTES de existir sessão, então têm de contornar a RLS por token, nunca
-- por tenant_id de sessão. Idempotente; sem BEGIN/COMMIT (padrão das demais migrações desta linha).

CREATE TABLE IF NOT EXISTS plat.convite (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  email             text NOT NULL,
  nome_sugerido     text,
  perfil            text NOT NULL CHECK (perfil IN ('admin','editor','visualizador','campo')),
  papel_id          int REFERENCES plat.papel_personalizado(id),
  token_hash        text NOT NULL UNIQUE,
  criado_por        int REFERENCES plat.usuario(id),
  criado_em         timestamptz NOT NULL DEFAULT now(),
  expira_em         timestamptz NOT NULL,
  usado_em          timestamptz,
  cancelado_em      timestamptz,
  usuario_criado_id int REFERENCES plat.usuario(id)
);
CREATE INDEX IF NOT EXISTS ix_convite_tenant ON plat.convite (tenant_id, criado_em DESC);

CREATE TABLE IF NOT EXISTS plat.redefinicao_senha (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  usuario_id   int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  token_hash   text NOT NULL UNIQUE,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  expira_em    timestamptz NOT NULL,
  usado_em     timestamptz,
  ip           text
);
CREATE INDEX IF NOT EXISTS ix_redefinicao_usuario ON plat.redefinicao_senha (usuario_id, criado_em DESC);

-- sem FK de propósito (limite de taxa vale mesmo para inquilino/e-mail inexistente; ver cabeçalho)
CREATE TABLE IF NOT EXISTS plat.redefinicao_pedido (
  id          bigserial PRIMARY KEY,
  chave       text NOT NULL,
  ip          text,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_redefinicao_pedido_chave_em ON plat.redefinicao_pedido (chave, criado_em DESC);

ALTER TABLE plat.convite            ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.redefinicao_senha  ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.redefinicao_pedido ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_convite ON plat.convite;
CREATE POLICY p_convite ON plat.convite FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_redefinicao_senha ON plat.redefinicao_senha;
CREATE POLICY p_redefinicao_senha ON plat.redefinicao_senha FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
-- redefinicao_pedido: só a função SECURITY DEFINER grava e lê (nunca tem contexto de inquilino resolvido
-- ainda); plat_app não recebe privilégio nenhum diretamente na tabela.
REVOKE ALL ON plat.redefinicao_pedido FROM plat_app;

-- convite: criar não precisa de função nova — a rota já está numa sessão normal (RLS isola por tenant_id) e
-- gera o token em Python com o MESMO padrão de app/auth/rotas_tokens.py (secrets.token_urlsafe + sha256_hex).

-- ---------------------------------------------------------------- convite: resolver (público, por token)
CREATE OR REPLACE FUNCTION plat.convite_resolver(p_token_hash text)
RETURNS TABLE (motivo text, tenant_slug text, tenant_nome text, email text, perfil text, expira_em timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT
    CASE
      WHEN c.id IS NULL THEN 'invalido'
      WHEN c.cancelado_em IS NOT NULL THEN 'cancelado'
      WHEN c.usado_em IS NOT NULL THEN 'usado'
      WHEN c.expira_em <= now() THEN 'expirado'
      WHEN NOT t.ativo THEN 'inquilino_suspenso'
      ELSE 'ok'
    END,
    t.slug, t.nome, c.email, c.perfil, c.expira_em
  FROM (SELECT 1) uma
  LEFT JOIN plat.convite c ON c.token_hash = p_token_hash
  LEFT JOIN plat.tenant t ON t.id = c.tenant_id
$$;

-- ---------------------------------------------------------------- convite: aceitar (público, por token; cria a conta)
CREATE OR REPLACE FUNCTION plat.convite_aceitar(p_token_hash text, p_login text, p_nome text, p_senha_hash text)
RETURNS TABLE (motivo text, usuario_id int, tenant_id int, login text, perfil text, papel_id int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE c plat.convite%ROWTYPE; ativo boolean; uid int;
BEGIN
  SELECT * INTO c FROM plat.convite WHERE token_hash = p_token_hash FOR UPDATE;
  IF c.id IS NULL THEN
    RETURN QUERY SELECT 'invalido', NULL::int, NULL::int, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  IF c.cancelado_em IS NOT NULL THEN
    RETURN QUERY SELECT 'cancelado', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  IF c.usado_em IS NOT NULL THEN
    RETURN QUERY SELECT 'usado', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  IF c.expira_em <= now() THEN
    RETURN QUERY SELECT 'expirado', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  SELECT t.ativo INTO ativo FROM plat.tenant t WHERE t.id = c.tenant_id;
  IF NOT coalesce(ativo, false) THEN
    RETURN QUERY SELECT 'inquilino_suspenso', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  INSERT INTO plat.usuario(tenant_id, login, nome, email, senha_hash, perfil, papel_id, trocar_senha, senha_alterada_em)
  VALUES (c.tenant_id, lower(p_login), p_nome, c.email, p_senha_hash, c.perfil, c.papel_id, false, now())
  RETURNING id INTO uid;
  UPDATE plat.convite SET usado_em = now(), usuario_criado_id = uid WHERE id = c.id;
  RETURN QUERY SELECT 'ok', uid, c.tenant_id, lower(p_login), c.perfil, c.papel_id;
END $$;

-- ---------------------------------------------------------------- redefinição: solicitar (público; limite de taxa embutido)
CREATE OR REPLACE FUNCTION plat.redefinicao_solicitar(p_slug text, p_email text, p_ip text, p_janela_min int,
  p_max_janela int, p_horas_validade int)
RETURNS TABLE (permitido boolean, tenant_id int, usuario_id int, login text, tenant_nome text, token text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE chave text; n int; u RECORD; tok text;
BEGIN
  chave := lower(trim(p_slug)) || '|' || lower(trim(p_email));
  SELECT count(*) INTO n FROM plat.redefinicao_pedido rp
    WHERE rp.chave = chave AND rp.criado_em > now() - make_interval(mins => p_janela_min);
  IF n >= p_max_janela THEN
    RETURN QUERY SELECT false, NULL::int, NULL::int, NULL::text, NULL::text, NULL::text; RETURN;
  END IF;
  INSERT INTO plat.redefinicao_pedido(chave, ip) VALUES (chave, p_ip);
  SELECT u2.id, u2.tenant_id, u2.login, t2.nome AS tenant_nome INTO u
    FROM plat.usuario u2 JOIN plat.tenant t2 ON t2.id = u2.tenant_id
    WHERE t2.slug = lower(trim(p_slug)) AND u2.email IS NOT NULL AND lower(u2.email) = lower(trim(p_email))
      AND u2.ativo AND t2.ativo AND u2.origem = 'local'
    ORDER BY u2.id LIMIT 1;
  IF u.id IS NULL THEN
    RETURN QUERY SELECT true, NULL::int, NULL::int, NULL::text, NULL::text, NULL::text; RETURN;
  END IF;
  tok := encode(gen_random_bytes(32), 'hex');
  INSERT INTO plat.redefinicao_senha(tenant_id, usuario_id, token_hash, expira_em, ip)
  VALUES (u.tenant_id, u.id, encode(sha256(convert_to(tok, 'UTF8')), 'hex'),
          now() + make_interval(hours => p_horas_validade), p_ip);
  RETURN QUERY SELECT true, u.tenant_id, u.id, u.login, u.tenant_nome, tok;
END $$;

-- ---------------------------------------------------------------- redefinição: resolver (público, só para exibir a tela)
CREATE OR REPLACE FUNCTION plat.redefinicao_resolver(p_token_hash text)
RETURNS TABLE (motivo text, login text, tenant_nome text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT
    CASE
      WHEN r.id IS NULL THEN 'invalido'
      WHEN r.usado_em IS NOT NULL THEN 'usado'
      WHEN r.expira_em <= now() THEN 'expirado'
      ELSE 'ok'
    END,
    u.login, t.nome
  FROM (SELECT 1) uma
  LEFT JOIN plat.redefinicao_senha r ON r.token_hash = p_token_hash
  LEFT JOIN plat.usuario u ON u.id = r.usuario_id
  LEFT JOIN plat.tenant t ON t.id = r.tenant_id
$$;

-- ---------------------------------------------------------------- redefinição: contexto para aplicar (público; sem
-- mexer em senha aqui — devolve tenant/usuário para o backend abrir um Contexto normal e reusar a MESMA rotina
-- de troca de senha/histórico/sessões de app/auth/rotas_eu.py::trocar_senha, sem duplicá-la)
CREATE OR REPLACE FUNCTION plat.redefinicao_contexto(p_token_hash text)
RETURNS TABLE (motivo text, tenant_id int, usuario_id int, login text, tenant_slug text, tenant_nome text,
               config jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT
    CASE
      WHEN r.id IS NULL THEN 'invalido'
      WHEN r.usado_em IS NOT NULL THEN 'usado'
      WHEN r.expira_em <= now() THEN 'expirado'
      WHEN NOT coalesce(t.ativo, false) OR NOT coalesce(u.ativo, false) THEN 'inquilino_suspenso'
      ELSE 'ok'
    END,
    r.tenant_id, r.usuario_id, u.login, t.slug, t.nome, t.config
  FROM (SELECT 1) uma
  LEFT JOIN plat.redefinicao_senha r ON r.token_hash = p_token_hash
  LEFT JOIN plat.usuario u ON u.id = r.usuario_id
  LEFT JOIN plat.tenant t ON t.id = r.tenant_id
$$;

-- ---------------------------------------------------------------- redefinição: marcar usada (dentro do Contexto
-- normal do usuário-alvo, na MESMA transação que troca a senha; FOR UPDATE fecha a corrida de duplo-envio)
CREATE OR REPLACE FUNCTION plat.redefinicao_marcar_usada(p_token_hash text, p_usuario_id int) RETURNS boolean
LANGUAGE plpgsql AS $$
DECLARE r plat.redefinicao_senha%ROWTYPE;
BEGIN
  SELECT * INTO r FROM plat.redefinicao_senha WHERE token_hash = p_token_hash AND usuario_id = p_usuario_id FOR UPDATE;
  IF r.id IS NULL OR r.usado_em IS NOT NULL OR r.expira_em <= now() THEN
    RETURN false;
  END IF;
  UPDATE plat.redefinicao_senha SET usado_em = now() WHERE id = r.id;
  RETURN true;
END $$;

-- privilégio de convite: reusa `membros.gerir`/`membros.papel` já semeados (003) — convidar é criar um usuário
-- que ainda não existe, mesmo teto de quem já pode criar um usuário direto (POST /api/usuarios).
