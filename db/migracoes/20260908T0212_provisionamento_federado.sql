-- 20260908T0212_provisionamento_federado: item L0-08-e-mapeamento-provisionamento. Regras de provisionamento por
-- provedor de login externo (LDAP 025, OIDC 20260907T0147, SAML 20260907T2050): criação automática ou só por
-- convite prévio, padrões para membro novo (papel, grupos internos, pasta), mapeamento valor exato do grupo do
-- IdP -> papel + grupos internos (o perfil continua em mapa_grupo_perfil, que a mesma tela edita), atualização a
-- cada login (opcional), desligamento quando o IdP deixa de mandar grupo mapeado (opcional) e 'desregistrar'
-- conta federada. Uma coluna jsonb `provisionamento` por tabela de provedor (as funções de leitura dos
-- provedores devolvem tipos fixos; por isso um acessor próprio, plat.provisionamento_de). Só funções SECURITY
-- DEFINER escrevem em plat.usuario/grupo_membro/pasta durante o login (não há contexto de inquilino ainda).
-- depende: 20260907T2050_provedor_saml.sql

ALTER TABLE plat.provedor_ldap ADD COLUMN IF NOT EXISTS provisionamento jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE plat.provedor_oidc ADD COLUMN IF NOT EXISTS provisionamento jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE plat.provedor_saml ADD COLUMN IF NOT EXISTS provisionamento jsonb NOT NULL DEFAULT '{}'::jsonb;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/logins_configurar', 'regras de provisionamento, rótulo, ordem ou habilitação de um provedor de login alteradas'),
  ('usuarios/desregistrar', 'conta federada desregistrada pelo admin (vínculo com o IdP removido, conta desativada; a conta no IdP continua)'),
  ('usuarios/desligar_federado', 'conta federada desativada no login porque o IdP deixou de mandar grupo mapeado (regra do provedor)'),
  ('usuarios/regras_aplicadas', 'papel, grupos internos ou pasta aplicados no login federado pelas regras do provedor')
ON CONFLICT (nome) DO NOTHING;

-- pré-contexto: regras do provedor (ldap: id = tenant_id, único por inquilino)
CREATE OR REPLACE FUNCTION plat.provisionamento_de(p_origem text, p_id int) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT coalesce(CASE p_origem
    WHEN 'ldap' THEN (SELECT provisionamento FROM plat.provedor_ldap WHERE tenant_id = p_id)
    WHEN 'oidc' THEN (SELECT provisionamento FROM plat.provedor_oidc WHERE id = p_id)
    WHEN 'saml' THEN (SELECT provisionamento FROM plat.provedor_saml WHERE id = p_id)
  END, '{}'::jsonb)
$$;

-- pré-contexto: a conta federada, se existe (pelo sujeito externo ou pelo login com a mesma origem)
CREATE OR REPLACE FUNCTION plat.usuario_federado_localizar(p_tenant_id int, p_origem text, p_login text, p_sujeito text)
RETURNS TABLE (id int, ativo boolean, perfil text, papel_id int, sujeito_externo text, origem text)
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT u.id, u.ativo, u.perfil, u.papel_id, u.sujeito_externo, u.origem
  FROM plat.usuario u
  WHERE u.tenant_id = p_tenant_id
    AND ((u.origem = p_origem AND u.sujeito_externo = p_sujeito) OR u.login = lower(p_login))
  ORDER BY (u.sujeito_externo = p_sujeito) DESC NULLS LAST
  LIMIT 1
$$;

-- pré-contexto: convite pendente para o e-mail (modo 'só por convite'); nunca devolve o token
CREATE OR REPLACE FUNCTION plat.convite_pendente_por_email(p_tenant_id int, p_email text)
RETURNS TABLE (id uuid, perfil text, papel_id int, nome_sugerido text)
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT c.id, c.perfil, c.papel_id, c.nome_sugerido
  FROM plat.convite c
  WHERE c.tenant_id = p_tenant_id AND lower(c.email) = lower(p_email)
    AND c.usado_em IS NULL AND c.cancelado_em IS NULL AND c.expira_em > now()
  ORDER BY c.criado_em DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION plat.convite_consumir_federado(p_convite uuid, p_usuario int) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.convite SET usado_em = now(), usuario_criado_id = p_usuario
  WHERE id = p_convite AND usado_em IS NULL AND cancelado_em IS NULL
$$;

-- pré-contexto: aplica papel, grupos internos e pasta a uma conta federada recém-provisionada.
-- p_grupos = grupos em que a conta deve estar; p_regidos = todos os grupos citados nas regras do provedor
-- (a conta SAI dos regidos que não estão em p_grupos — sincronização como a Esri faz, nunca de grupos que o
-- provedor não governa; dono e grupo administrativo/protegido nunca são removidos). Papel/grupo de outro
-- inquilino são ignorados (nunca aplicados). Pasta: nome com {login}, criada só se não existir na raiz.
CREATE OR REPLACE FUNCTION plat.usuario_federado_regras(
  p_tenant_id int, p_usuario int, p_papel_id int, p_grupos uuid[], p_regidos uuid[], p_pasta text, p_login text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE g uuid; entrou uuid[] := '{}'; saiu uuid[] := '{}'; papel_ok int := NULL; pasta_criada boolean := false;
        nome_pasta text; u record;
BEGIN
  SELECT id, perfil INTO u FROM plat.usuario WHERE id = p_usuario AND tenant_id = p_tenant_id;
  IF u.id IS NULL THEN RAISE EXCEPTION 'usuario_inexistente'; END IF;
  IF p_papel_id IS NOT NULL THEN
    SELECT p.id INTO papel_ok FROM plat.papel_personalizado p WHERE p.id = p_papel_id AND p.tenant_id = p_tenant_id;
  END IF;
  UPDATE plat.usuario SET papel_id = papel_ok WHERE id = p_usuario AND papel_id IS DISTINCT FROM papel_ok;
  FOREACH g IN ARRAY coalesce(p_grupos, '{}'::uuid[]) LOOP
    IF EXISTS (SELECT 1 FROM plat.grupo gr WHERE gr.id = g AND gr.tenant_id = p_tenant_id)
       AND NOT EXISTS (SELECT 1 FROM plat.grupo_membro m WHERE m.grupo_id = g AND m.usuario_id = p_usuario) THEN
      INSERT INTO plat.grupo_membro(grupo_id, tenant_id, usuario_id, papel, estado)
      VALUES (g, p_tenant_id, p_usuario, 'membro', 'ativo');
      entrou := entrou || g;
    ELSIF EXISTS (SELECT 1 FROM plat.grupo_membro m WHERE m.grupo_id = g AND m.usuario_id = p_usuario AND m.estado <> 'ativo') THEN
      UPDATE plat.grupo_membro SET estado = 'ativo' WHERE grupo_id = g AND usuario_id = p_usuario;
      entrou := entrou || g;
    END IF;
  END LOOP;
  FOREACH g IN ARRAY coalesce(p_regidos, '{}'::uuid[]) LOOP
    IF NOT (g = ANY (coalesce(p_grupos, '{}'::uuid[]))) THEN
      DELETE FROM plat.grupo_membro m USING plat.grupo gr
      WHERE m.grupo_id = g AND m.usuario_id = p_usuario AND gr.id = m.grupo_id AND gr.tenant_id = p_tenant_id
        AND m.papel <> 'dono' AND NOT gr.administrativo AND NOT gr.protegido;
      IF FOUND THEN saiu := saiu || g; END IF;
    END IF;
  END LOOP;
  IF p_pasta IS NOT NULL AND btrim(p_pasta) <> '' THEN
    nome_pasta := left(btrim(replace(p_pasta, '{login}', coalesce(p_login, ''))), 128);
    IF nome_pasta <> '' AND nome_pasta !~ '[/\\]'
       AND NOT EXISTS (SELECT 1 FROM plat.pasta p WHERE p.tenant_id = p_tenant_id AND p.pai_id IS NULL AND lower(p.nome) = lower(nome_pasta)) THEN
      INSERT INTO plat.pasta(tenant_id, nome, dono_id) VALUES (p_tenant_id, nome_pasta, p_usuario);
      pasta_criada := true;
    END IF;
  END IF;
  RETURN jsonb_build_object('papel_id', papel_ok, 'grupos_entrou', to_jsonb(entrou), 'grupos_saiu', to_jsonb(saiu),
                            'pasta_criada', pasta_criada);
END $$;

-- pré-contexto: desliga a conta federada (regra 'desligar quando o IdP deixa de mandar o grupo'); sessões caem
CREATE OR REPLACE FUNCTION plat.usuario_federado_desligar(p_tenant_id int, p_usuario int) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  UPDATE plat.usuario SET ativo = false WHERE id = p_usuario AND tenant_id = p_tenant_id AND origem <> 'local';
  DELETE FROM plat.sessao WHERE usuario_id = p_usuario AND tenant_id = p_tenant_id;
END $$;

REVOKE EXECUTE ON FUNCTION plat.provisionamento_de(text, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuario_federado_localizar(int, text, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.convite_pendente_por_email(int, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.convite_consumir_federado(uuid, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuario_federado_regras(int, int, int, uuid[], uuid[], text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.usuario_federado_desligar(int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.provisionamento_de(text, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.usuario_federado_localizar(int, text, text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.convite_pendente_por_email(int, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.convite_consumir_federado(uuid, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.usuario_federado_regras(int, int, int, uuid[], uuid[], text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.usuario_federado_desligar(int, int) TO plat_app;
