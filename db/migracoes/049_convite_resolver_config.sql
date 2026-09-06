-- 049_convite_resolver_config: mesma classe de defeito da 048 (verificação manual do item L0-07-d, antes do
-- adversário) — `POST /api/convites/aceitar` buscava `tenant.config` numa segunda consulta SEM contexto de
-- inquilino (`db.db()` sem `Contexto`, porque a conta ainda não existe: não há usuario_id para montar um);
-- RLS de `plat.tenant` (`id = plat.tenant_atual()`) filtra a linha com o GUC vazio e `cur.fetchone()` volta
-- `None` → 500 em vez de aceitar o convite. Em vez de repetir o padrão de contexto sintético,
-- `plat.convite_resolver` passa a devolver `config` também (já faz LEFT JOIN com `plat.tenant`): o Python
-- lê a política de senha do MESMO resultado que já usava para o e-mail/perfil, sem segunda consulta.

-- muda o tipo de retorno (coluna nova): CREATE OR REPLACE sozinho recusa ("cannot change return type"),
-- precisa do DROP explícito antes.
DROP FUNCTION IF EXISTS plat.convite_resolver(text);

CREATE OR REPLACE FUNCTION plat.convite_resolver(p_token_hash text)
RETURNS TABLE (motivo text, tenant_slug text, tenant_nome text, email text, perfil text, expira_em timestamptz,
               config jsonb)
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
    t.slug, t.nome, c.email, c.perfil, c.expira_em, t.config
  FROM (SELECT 1) uma
  LEFT JOIN plat.convite c ON c.token_hash = p_token_hash
  LEFT JOIN plat.tenant t ON t.id = c.tenant_id
$$;

REVOKE EXECUTE ON FUNCTION plat.convite_resolver(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.convite_resolver(text) TO plat_app;
