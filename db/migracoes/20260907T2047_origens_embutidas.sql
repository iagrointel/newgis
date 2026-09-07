-- origens_embutidas: lista de origens que podem embutir as páginas de um inquilino em iframe
-- (Content-Security-Policy: frame-ancestors, item L7-03-e). O valor mora em plat.tenant.config, a mesma
-- coluna jsonb que o L0-02 e o L0-07-a já usam; esta migração só acrescenta a função de leitura.
--
-- Por que SECURITY DEFINER: o cabeçalho é montado no middleware, ANTES de haver contexto de inquilino na
-- conexão em toda página pública (/mapa, /entrar) — sem contexto a RLS de plat.tenant devolve zero linhas e
-- a política sairia sempre fechada. A função devolve UM campo de configuração de UM inquilino, nada mais:
-- não vê usuário, não vê dado, e o próprio valor volta ao mundo no cabeçalho da resposta.
-- Idempotente. Sem BEGIN/COMMIT.

CREATE OR REPLACE FUNCTION plat.origens_embutidas(p_slug text, p_tenant_id int)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT COALESCE(t.config -> 'origens_embutidas', '[]'::jsonb)
  FROM plat.tenant t
  WHERE t.ativo AND (
    (p_tenant_id IS NOT NULL AND t.id = p_tenant_id) OR
    (p_tenant_id IS NULL AND p_slug IS NOT NULL AND t.slug = p_slug)
  )
$$;
REVOKE ALL ON FUNCTION plat.origens_embutidas(text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.origens_embutidas(text, int) TO plat_app;
