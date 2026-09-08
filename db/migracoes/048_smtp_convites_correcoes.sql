-- 048_smtp_convites_correcoes: três defeitos achados na verificação manual do item L0-07-d-smtp-convites
-- (migração 047), ANTES do adversário — registrados aqui em vez de reescrever 047 (migração aplicada é
-- imutável, ADR 0001 seção 5):
--  1. plat.redefinicao_solicitar: a variável PL/pgSQL `chave` tinha o MESMO nome da coluna
--     `redefinicao_pedido.chave`, e o Postgres não decide sozinho qual é qual ("column reference is
--     ambiguous") — todo POST /api/senha/redefinir/solicitar caía em 500. Renomeada para `v_chave`.
--  2. Sete tipos de evento novos (SMTP, convite, redefinição por e-mail) nunca foram inseridos em
--     `plat.evento_tipo` — toda `registrar_evento(...)` correspondente violava a FK e também caía em 500
--     (`PUT/DELETE /api/org/smtp`, `POST /api/convites`, aceitar convite, aplicar redefinição).
--  3. As 6 funções SECURITY DEFINER/normais da 047 nasceram com EXECUTE aberto a PUBLIC (ACL padrão do
--     Postgres para função nova, `=X/postgres`) — a suíte (`test_nenhuma_funcao_com_execute_para_public`)
--     e o padrão de toda função da casa (ADR 0002 seção 12, ex.: migração 034) exigem REVOKE explícito +
--     GRANT só a plat_app.

CREATE OR REPLACE FUNCTION plat.redefinicao_solicitar(p_slug text, p_email text, p_ip text, p_janela_min int,
  p_max_janela int, p_horas_validade int)
RETURNS TABLE (permitido boolean, tenant_id int, usuario_id int, login text, tenant_nome text, token text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_chave text; n int; u RECORD; tok text;
BEGIN
  v_chave := lower(trim(p_slug)) || '|' || lower(trim(p_email));
  SELECT count(*) INTO n FROM plat.redefinicao_pedido rp
    WHERE rp.chave = v_chave AND rp.criado_em > now() - make_interval(mins => p_janela_min);
  IF n >= p_max_janela THEN
    RETURN QUERY SELECT false, NULL::int, NULL::int, NULL::text, NULL::text, NULL::text; RETURN;
  END IF;
  INSERT INTO plat.redefinicao_pedido(chave, ip) VALUES (v_chave, p_ip);
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

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/smtp_configurar', 'SMTP do inquilino configurado (host/porta/tls/remetente; nunca a senha)'),
  ('org/smtp_remover', 'override de SMTP do inquilino removido (volta à instalação/caminho manual)'),
  ('org/smtp_testar', 'envio de teste de SMTP disparado (propriedades.ok indica sucesso/falha)'),
  ('convites/criar', 'convite de membro criado (e-mail, perfil)'),
  ('convites/cancelar', 'convite de membro cancelado antes de usado'),
  ('usuarios/convite_aceito', 'conta criada a partir de um convite aceito'),
  ('usuarios/redefinir_senha_email', 'senha trocada por redefinição pública via e-mail')
ON CONFLICT (nome) DO NOTHING;

DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.convite_resolver(text)', 'plat.convite_aceitar(text,text,text,text)',
    'plat.redefinicao_solicitar(text,text,text,int,int,int)', 'plat.redefinicao_resolver(text)',
    'plat.redefinicao_contexto(text)', 'plat.redefinicao_marcar_usada(text,int)'
  ] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
