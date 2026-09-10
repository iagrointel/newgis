-- Conserto do grupo G1 (identidade/sessão/2FA/LDAP) depois do ataque adversarial do turno 3
-- (laco/handoffs/T3/ataque-g1-ADVERSARIO.md). Três mudanças, todas com CREATE OR REPLACE — nenhum GRANT ou
-- REVOKE novo: as ACL das funções continuam exatamente as que 003/025 escreveram.
--
-- 1) plat.sessoes_expurgar(): o corte de ociosidade era `interval '24 hours'` FIXO, enquanto a sessão deixa de
--    valer pela política do inquilino (`config.auth.sessao_ociosa_horas`, padrão 12 h, faixa 1–24 h; é o mesmo
--    cálculo que plat.auth_sessao já fazia para devolver 401). Achado G1-a1: com 13 h de ociosidade a sessão
--    respondia 401 e a linha ficava no banco por mais 11 h. Agora o periódico usa o MESMO corte por inquilino.
-- 2) plat.ldap_provisionar(): a identidade externa passa a ser procurada primeiro pelo SUJEITO EXTERNO (o DN),
--    não pelo login. O DN é o que o diretório garante único; o login é atributo e pode mudar. Achado G1-l3: o
--    login vinha do texto cru do cliente, tomava o DN de outra pessoa e trancava o login canônico com um 409
--    de índice único, sem rota administrativa para desfazer. Com a busca por DN, o segundo login da MESMA
--    identidade ATUALIZA a linha (inclusive corrigindo o login) em vez de colidir; a colisão que sobra — dois
--    DNs diferentes disputando o mesmo login — vira o código curto `login_em_uso_externo`, que a API traduz
--    sem citar nome de restrição do banco.
-- 3) evento novo `usuarios/vinculo_externo_remover`, do caminho administrativo de desfazer um vínculo errado
--    (DELETE /api/usuarios/{id}/vinculo-externo).

-- 1 -----------------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION plat.sessoes_expurgar() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; m int;
BEGIN
  DELETE FROM plat.sessao s
  USING plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE u.id = s.usuario_id
    AND (s.expira_em < now()
         OR coalesce(s.ultimo_uso, s.criado_em) < now() - make_interval(secs => 3600 * (
              CASE WHEN nullif(t.config #>> '{auth,sessao_ociosa_horas}', '') IS NULL THEN 12
                   ELSE least(greatest((t.config #>> '{auth,sessao_ociosa_horas}')::numeric, 1), 24) END)));
  GET DIAGNOSTICS n = ROW_COUNT;
  -- sessão órfã (usuário apagado sem cascata, ou linha sem dono): some pelo teto absoluto de 24 h, que é o
  -- maior valor que a política aceita — sem inquilino não há política a consultar
  DELETE FROM plat.sessao s
  WHERE NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = s.usuario_id)
    AND (s.expira_em < now() OR coalesce(s.ultimo_uso, s.criado_em) < now() - interval '24 hours');
  GET DIAGNOSTICS m = ROW_COUNT;
  n := n + m;
  UPDATE plat.usuario SET desafio_2fa_hash = NULL, desafio_2fa_ate = NULL
  WHERE desafio_2fa_ate IS NOT NULL AND desafio_2fa_ate < now();
  RETURN n;
END $$;

-- 2 -----------------------------------------------------------------------------------------------------
-- CREATE OR REPLACE com a MESMA assinatura e o MESMO tipo de retorno de 025: as ACL da função ficam intactas
-- (nada de DROP + CREATE, que apagaria o GRANT ... TO plat_app e o REVOKE ... FROM PUBLIC de 025).
CREATE OR REPLACE FUNCTION plat.ldap_provisionar(
  p_tenant_id int, p_login text, p_nome text, p_email text, p_perfil text, p_sujeito_externo text,
  p_ativo boolean DEFAULT true
) RETURNS TABLE (criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record; por_login record; v_login text := lower(p_login);
BEGIN
  IF p_sujeito_externo IS NULL OR btrim(p_sujeito_externo) = '' THEN
    RAISE EXCEPTION 'sujeito_externo_ausente';
  END IF;
  -- a identidade é o DN, não o login: quem já tem este DN neste inquilino é esta pessoa
  SELECT u.id, u.origem, u.perfil, u.login INTO existente FROM plat.usuario u
    WHERE u.tenant_id = p_tenant_id AND u.origem = 'ldap' AND u.sujeito_externo = p_sujeito_externo;
  IF existente.id IS NULL THEN
    SELECT u.id, u.origem, u.perfil, u.login, u.sujeito_externo INTO por_login FROM plat.usuario u
      WHERE u.tenant_id = p_tenant_id AND u.login = v_login;
    IF por_login.id IS NOT NULL AND por_login.origem <> 'ldap' THEN
      RAISE EXCEPTION 'login_em_uso_local';
    END IF;
    IF por_login.id IS NOT NULL AND por_login.sujeito_externo IS DISTINCT FROM p_sujeito_externo THEN
      -- mesmo login, OUTRO DN: nunca sequestra a linha existente nem estoura índice único
      RAISE EXCEPTION 'login_em_uso_externo';
    END IF;
    existente := por_login;
  END IF;
  IF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (p_tenant_id, v_login, p_nome, p_email, p_perfil, 'ldap', p_sujeito_externo, p_ativo, NULL);
    RETURN QUERY SELECT true, NULL::text;
  ELSE
    -- o login local acompanha o diretório, a menos que o novo login já seja de OUTRA linha do inquilino
    IF v_login IS DISTINCT FROM existente.login
       AND EXISTS (SELECT 1 FROM plat.usuario u WHERE u.tenant_id = p_tenant_id AND u.login = v_login
                     AND u.id <> existente.id) THEN
      RAISE EXCEPTION 'login_em_uso_externo';
    END IF;
    UPDATE plat.usuario u SET login = v_login, nome = p_nome, email = coalesce(p_email, u.email),
      perfil = p_perfil, sujeito_externo = p_sujeito_externo, ativo = p_ativo
    WHERE u.id = existente.id;
    RETURN QUERY SELECT false, existente.perfil;
  END IF;
END $$;

-- 3 -----------------------------------------------------------------------------------------------------
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('usuarios/vinculo_externo_remover',
   'vínculo com a identidade do diretório (sujeito_externo) removido por administrador')
ON CONFLICT (nome) DO NOTHING;
