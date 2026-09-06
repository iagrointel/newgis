-- 20260906T1758_ldap_provisionar_isolamento
--
-- ACHADO DA VARREDURA (laco/handoffs/T3/VARREDURA-funcoes-privilegiadas.md): `plat.ldap_provisionar` é
-- alvo de DOIS consertos concorrentes, aplicados em ORDEM DE COLISÃO direta:
--   - 20260906T1601_funcoes_privilegiadas_isolamento.sql (este ramo, wt/secdef): acrescentou a guarda de
--     isolamento `alvo := plat.inquilino_do_argumento(p_tenant_id)` — a função recebe o inquilino por
--     argumento e roda SECURITY DEFINER, fora da RLS.
--   - 20260906T1611_g1_identidade_conserto.sql (wt/g1fix, aplicada DIRETO em produção às 16:31 UTC,
--     11 minutos DEPOIS da 1601): trocou a chave de busca de `login` para `(tenant_id, origem='ldap',
--     sujeito_externo)`, corrigindo o achado G1-l3 (login cru virava identidade local). Não tocou em
--     permissão nem em isolamento — o handoff dela diz isso explicitamente.
--
-- Medido em 06/09 17:5x: a base de PRODUÇÃO tem a versão da 1611 (semântica de identidade correta,
-- SEM a guarda de inquilino); a base desta TRILHA (plat_tsecdef) tem a versão da 1601 (guarda de
-- inquilino, SEM a correção de identidade). Nenhum arquivo do repositório tem as duas coisas juntas —
-- promover qualquer um dos dois ramos sozinho, na ordem que for, desfaz o conserto do outro. Esta
-- migração é a MESCLA: a lógica de identidade da 1611, com `p_tenant_id` substituído por
-- `plat.inquilino_do_argumento(p_tenant_id)` em toda leitura/escrita de `plat.usuario`. Idempotente
-- (CREATE OR REPLACE), mesma assinatura e mesmo retorno das duas — não quebra quem já chama.

CREATE OR REPLACE FUNCTION plat.ldap_provisionar(p_tenant_id int, p_login text, p_nome text, p_email text,
  p_perfil text, p_sujeito_externo text, p_ativo boolean DEFAULT true)
RETURNS TABLE(criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record; por_login record; v_login text := lower(p_login); alvo int;
BEGIN
  alvo := plat.inquilino_do_argumento(p_tenant_id);
  IF p_sujeito_externo IS NULL OR btrim(p_sujeito_externo) = '' THEN
    RAISE EXCEPTION 'sujeito_externo_ausente';
  END IF;
  -- a identidade é o DN, não o login (G1-l3): quem já tem este DN neste inquilino é esta pessoa
  SELECT u.id, u.origem, u.perfil, u.login INTO existente FROM plat.usuario u
    WHERE u.tenant_id = alvo AND u.origem = 'ldap' AND u.sujeito_externo = p_sujeito_externo;
  IF existente.id IS NULL THEN
    SELECT u.id, u.origem, u.perfil, u.login, u.sujeito_externo INTO por_login FROM plat.usuario u
      WHERE u.tenant_id = alvo AND u.login = v_login;
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
    VALUES (alvo, v_login, p_nome, p_email, p_perfil, 'ldap', p_sujeito_externo, p_ativo, NULL);
    RETURN QUERY SELECT true, NULL::text;
  ELSE
    -- o login local acompanha o diretório, a menos que o novo login já seja de OUTRA linha do inquilino
    IF v_login IS DISTINCT FROM existente.login
       AND EXISTS (SELECT 1 FROM plat.usuario u WHERE u.tenant_id = alvo AND u.login = v_login
                     AND u.id <> existente.id) THEN
      RAISE EXCEPTION 'login_em_uso_externo';
    END IF;
    UPDATE plat.usuario u SET login = v_login, nome = p_nome, email = coalesce(p_email, u.email),
      perfil = p_perfil, sujeito_externo = p_sujeito_externo, ativo = p_ativo
    WHERE u.id = existente.id;
    RETURN QUERY SELECT false, existente.perfil;
  END IF;
END $$;

REVOKE EXECUTE ON FUNCTION
  plat.ldap_provisionar(int, text, text, text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  plat.ldap_provisionar(int, text, text, text, text, text, boolean) TO plat_app;
