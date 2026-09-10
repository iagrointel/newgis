-- chaves_api (item L7-08-d, ADR 0018): fecha o buraco do prazo da chave de API e passa a contar o uso.
--
-- 1. `plat.token_servico.expira_em` nasceu ANULÁVEL na 002 e `plat.auth_token` aceitava a chave com
--    "(k.expira_em IS NULL OR k.expira_em > now())" — isto é, uma chave sem prazo valeria para sempre.
--    A API nunca gravou NULL ali (app/auth/rotas_tokens.py sempre soma make_interval), mas o banco
--    admitia, e é exatamente o que a refutação do item tenta ("chave sem expiração pela API"). Agora é
--    NOT NULL, com teto de 366 dias sobre a criação conferido pelo próprio banco, e a função perde o
--    ramo do NULL: mesmo que uma carga futura escreva NULL por outro caminho, o INSERT falha.
-- 2. `usos` conta cada requisição aceita com a chave (o portal mostra "último uso" e "usos"). É a MESMA
--    linha de UPDATE que já gravava `ultimo_uso` — nenhuma consulta, nenhum gatilho novo.
-- A assinatura de `plat.auth_token` NÃO muda (só o corpo): trocar o RETURNS TABLE exigiria DROP, e a
-- função é SECURITY DEFINER com GRANT próprio — corpo por CREATE OR REPLACE é a mudança menor.
-- Idempotente. Sem BEGIN/COMMIT (db/migrar.sh envolve).

-- --------------------------------------------------------------- 1. prazo obrigatório
UPDATE plat.token_servico SET expira_em = criado_em + interval '90 days' WHERE expira_em IS NULL;

ALTER TABLE plat.token_servico ALTER COLUMN expira_em SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_token_prazo_teto'
                   AND conrelid = 'plat.token_servico'::regclass) THEN
    ALTER TABLE plat.token_servico
      ADD CONSTRAINT ck_token_prazo_teto CHECK (expira_em <= criado_em + interval '366 days');
  END IF;
END $$;

-- --------------------------------------------------------------- 2. contagem de uso
ALTER TABLE plat.token_servico ADD COLUMN IF NOT EXISTS usos bigint NOT NULL DEFAULT 0;

-- --------------------------------------------------------------- 3. auth_token sem o ramo do NULL, contando
-- corpo idêntico ao da 003 exceto duas coisas: `k.expira_em > now()` sem o "IS NULL OR", e `usos = k.usos + 1`.
CREATE OR REPLACE FUNCTION plat.auth_token(p_hash text, p_ip text)
RETURNS TABLE (usuario_id int, tenant_id int, login text, perfil text, nome text, email text, escopos text[],
               restricao jsonb, token_id int, token_nome text, privilegios text[], trocar_senha boolean,
               expira_em timestamptz, revogado_em timestamptz, renovado_por int, superadmin boolean,
               totp_ativo boolean, origem text, tenant_slug text, tenant_nome text, config jsonb, papel_id int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  UPDATE plat.token_servico k SET ultimo_uso = now(), ultimo_ip = p_ip, usos = k.usos + 1
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE k.token_hash = p_hash AND k.usuario_id = u.id AND k.revogado_em IS NULL
    AND k.expira_em > now() AND u.ativo AND t.ativo AND NOT u.trocar_senha;
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, u.email, k.escopos, k.restricao, k.id, k.nome,
           plat.privilegios_de(u.id), u.trocar_senha, k.expira_em, k.revogado_em, k.renovado_por, u.superadmin,
           u.totp_ativo, u.origem, t.slug, t.nome, t.config, u.papel_id
    FROM plat.token_servico k JOIN plat.usuario u ON u.id = k.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
    WHERE k.token_hash = p_hash AND u.ativo AND t.ativo;
END $$;

REVOKE ALL ON FUNCTION plat.auth_token(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.auth_token(text, text) TO plat_app;
