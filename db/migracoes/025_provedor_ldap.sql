-- Migração 025 — provedor LDAP/Active Directory por inquilino (item L0-08-d-ldap, filho de L0-08-sso; ADR 0002
-- seção 13 "Gancho para SSO", que já deixou `usuario.origem` aceitar 'ldap' e `usuario.sujeito_externo` único
-- por (tenant_id, origem)). Idempotente; sem BEGIN/COMMIT (padrão das demais migrações desta linha).
--
-- Decisões deste item (docs/adr/0008-ldap-ad.md tem o raciocínio completo):
--  * config do PROVEDOR (endereço, DN de busca, filtro, atributo de grupo, mapa grupo→perfil) é por inquilino,
--    numa tabela própria (mesmo padrão de plat.papel_personalizado/plat.grupo: tenant_id + RLS FOR ALL);
--  * PLAT_LDAP_URL/PLAT_LDAP_BASE_DN (variáveis de ambiente, lidas em app/auth/ldap.py, nunca aqui) são o
--    endereço do diretório de TESTE desta máquina (contêiner glauth efêmero) e servem de PADRÃO quando a linha
--    do inquilino não informa url/base_dn próprios — nunca o único lugar de configuração;
--  * a senha do usuário do LDAP NUNCA é gravada (usuario.senha_hash fica NULL para origem='ldap', já garantido
--    pela 003); só a senha de BIND DE SERVIÇO (opcional, para a busca) é gravada, cifrada com o mesmo esquema
--    AES-GCM do segredo TOTP (prefixo 'enc:v1:', chave derivada de PLAT_SECRET), nunca em texto puro;
--  * duas funções SECURITY DEFINER sem exigir contexto de sessão (mesmo padrão de plat.auth_login/
--    plat.tenant_publico, chamadas ANTES de existir sessão): plat.provedor_ldap_de (lê a config pelo slug) e
--    plat.ldap_provisionar (upsert do usuário local após bind LDAP bem-sucedido); depois do upsert, o backend
--    chama plat.auth_login de novo e reaproveita _abrir_sessao (app/auth/rotas_login.py) sem duplicar a
--    criação de sessão — o mesmo caminho do login local a partir do momento em que a credencial foi validada.

CREATE TABLE IF NOT EXISTS plat.provedor_ldap (
  id                 serial PRIMARY KEY,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  habilitado         boolean NOT NULL DEFAULT true,
  url                text,                     -- 'ldap://host:389' ou 'ldaps://host:636'; NULL usa PLAT_LDAP_URL
  base_dn            text,                     -- 'dc=exemplo,dc=org'; NULL usa PLAT_LDAP_BASE_DN
  start_tls          boolean NOT NULL DEFAULT true,   -- StartTLS sobre 'ldap://'; ignorado com 'ldaps://' (já cifrado)
  bind_dn            text,                     -- DN da conta de serviço p/ a BUSCA; NULL = busca anônima
  bind_senha_cifrada text,                     -- 'enc:v1:...'; NULL quando bind_dn é NULL (bind anônimo)
  filtro_usuario     text NOT NULL DEFAULT '(uid={login})',  -- {login} é sempre escapado (RFC 4515) antes de entrar aqui
  atributo_grupos    text NOT NULL DEFAULT 'memberOf',
  perfil_padrao      text CHECK (perfil_padrao IS NULL OR perfil_padrao IN ('admin','editor','visualizador','campo')),
  mapa_grupo_perfil  jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"<DN ou CN do grupo>": "<perfil da plataforma>"}
  criado_por         int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_por     int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id)
);

ALTER TABLE plat.provedor_ldap ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_provedor_ldap ON plat.provedor_ldap;
CREATE POLICY p_provedor_ldap ON plat.provedor_ldap FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- vocabulário novo de evento (append à tabela existente da 003; ON CONFLICT preserva reaplicação)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/ldap_configurar', 'provedor LDAP do inquilino criado ou alterado (nunca grava a senha em claro no evento)'),
  ('org/ldap_importar', 'importação de grupo LDAP em massa: usuários criados desabilitados até o primeiro login')
ON CONFLICT (nome) DO NOTHING;

-- pré-contexto (como plat.auth_login/plat.tenant_publico): resolve pelo SLUG, sem sessão ainda. Devolve
-- NULL em todo campo de provedor_ldap quando o inquilino não tem linha configurada (tenant_ativo continua
-- vindo para a rota decidir 503 igual ao login local).
DROP FUNCTION IF EXISTS plat.provedor_ldap_de(text);
CREATE OR REPLACE FUNCTION plat.provedor_ldap_de(p_tenant text)
RETURNS TABLE (tenant_id int, tenant_ativo boolean, tenant_slug text, tenant_nome text, config jsonb,
               habilitado boolean, url text, base_dn text, start_tls boolean, bind_dn text,
               bind_senha_cifrada text, filtro_usuario text, atributo_grupos text, perfil_padrao text,
               mapa_grupo_perfil jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  -- config vai junto (mesmo bloco tenant.config.auth do login local) para o bloqueio de força bruta desta
  -- rota usar OS MESMOS bloqueio_tentativas/bloqueio_minutos do inquilino, nunca um limiar hardcoded à parte
  SELECT t.id, t.ativo, t.slug, t.nome, t.config, pl.habilitado, pl.url, pl.base_dn, pl.start_tls, pl.bind_dn,
         pl.bind_senha_cifrada, pl.filtro_usuario, pl.atributo_grupos, pl.perfil_padrao, pl.mapa_grupo_perfil
  FROM plat.tenant t LEFT JOIN plat.provedor_ldap pl ON pl.tenant_id = t.id
  WHERE t.slug = p_tenant
$$;

-- upsert de identidade federada. NUNCA sobrescreve conta de origem 'local' com o mesmo login (409 lógico
-- 'login_em_uso_local' — um adversário que descubra o login de um admin local não a assume criando um
-- homônimo no diretório). Devolve (criado, perfil_anterior) para o evento de domínio que a rota registra.
DROP FUNCTION IF EXISTS plat.ldap_provisionar(int, text, text, text, text, text, boolean);
CREATE OR REPLACE FUNCTION plat.ldap_provisionar(
  p_tenant_id int, p_login text, p_nome text, p_email text, p_perfil text, p_sujeito_externo text,
  p_ativo boolean DEFAULT true
) RETURNS TABLE (criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record;
BEGIN
  SELECT id, origem, perfil INTO existente FROM plat.usuario
    WHERE tenant_id = p_tenant_id AND login = lower(p_login);
  IF existente.id IS NOT NULL AND existente.origem <> 'ldap' THEN
    RAISE EXCEPTION 'login_em_uso_local';
  END IF;
  IF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (p_tenant_id, lower(p_login), p_nome, p_email, p_perfil, 'ldap', p_sujeito_externo, p_ativo, NULL);
    RETURN QUERY SELECT true, NULL::text;
  ELSE
    UPDATE plat.usuario SET nome = p_nome, email = coalesce(p_email, email), perfil = p_perfil,
      sujeito_externo = p_sujeito_externo, ativo = p_ativo
    WHERE id = existente.id;
    RETURN QUERY SELECT false, existente.perfil;
  END IF;
END $$;

-- importação em massa (opção do portão): cria usuários DESABILITADOS a partir de uma lista de (login, nome,
-- email, sujeito_externo) já resolvida pelo backend (a busca no diretório é do Python/ldap3; esta função só
-- grava). Pula quem já existe com origem <> 'ldap' (não derruba a importação inteira por um homônimo local).
DROP FUNCTION IF EXISTS plat.ldap_importar_lote(int, jsonb, text);
CREATE OR REPLACE FUNCTION plat.ldap_importar_lote(p_tenant_id int, p_usuarios jsonb, p_perfil text)
RETURNS TABLE (criados int, ja_existentes int, recusados int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE u jsonb; n_criados int := 0; n_existentes int := 0; n_recusados int := 0; existente record;
BEGIN
  FOR u IN SELECT * FROM jsonb_array_elements(p_usuarios) LOOP
    SELECT id, origem INTO existente FROM plat.usuario
      WHERE tenant_id = p_tenant_id AND login = lower(u->>'login');
    IF existente.id IS NOT NULL AND existente.origem <> 'ldap' THEN
      n_recusados := n_recusados + 1;
    ELSIF existente.id IS NOT NULL THEN
      n_existentes := n_existentes + 1;
    ELSE
      INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
      VALUES (p_tenant_id, lower(u->>'login'), u->>'nome', u->>'email', p_perfil, 'ldap', u->>'sujeito_externo',
              false, NULL);
      n_criados := n_criados + 1;
    END IF;
  END LOOP;
  RETURN QUERY SELECT n_criados, n_existentes, n_recusados;
END $$;

-- P6/segurança (ADR 0002 seção 8.4, migração 003 linha 834): `CREATE FUNCTION` concede EXECUTE a PUBLIC por
-- padrão; a 003 revogou isso de uma vez para TODAS as funções que já existiam e ajustou o privilégio padrão
-- de objetos futuros do papel `postgres`, mas a revogação explícita por função (como as outras migrações desta
-- linha fazem) é o que o teste `test_nenhuma_funcao_com_execute_para_public` de fato confere — reafirmada aqui
-- para as 3 funções novas, nunca deixando PUBLIC executar identidade federada.
REVOKE EXECUTE ON FUNCTION plat.provedor_ldap_de(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.ldap_provisionar(int, text, text, text, text, text, boolean) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.ldap_importar_lote(int, jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.provedor_ldap_de(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.ldap_provisionar(int, text, text, text, text, text, boolean) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.ldap_importar_lote(int, jsonb, text) TO plat_app;
