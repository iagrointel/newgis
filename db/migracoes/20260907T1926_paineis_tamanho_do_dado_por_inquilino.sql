-- item L7-06-d-paineis: tamanho do schema de dado por inquilino, para o painel "por inquilino".
--
-- Achado que obriga a isto (medido em 07/09/2026): a família `plat_tenant_schema_bytes` do
-- postgres_exporter (item L7-06-a) NUNCA teve série, nem em produção nem em homologação. A consulta
-- do exporter faz JOIN com `plat.tenant`, que tem RLS por inquilino; o papel de métrica não é dono e
-- não tem BYPASSRLS, então a consulta devolve zero linha em silêncio — o exporter não acusa erro, a
-- métrica simplesmente não nasce. Mesma causa da `plat_bucket_*` (ver 20260907T1919). A saída é a
-- mesma: função SECURITY DEFINER lida pela API.
--
-- depende: 20260907T1919_paineis_uso_de_bucket.sql

CREATE OR REPLACE FUNCTION plat.tenant_dado_bytes()
RETURNS TABLE(tenant_id int, bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.id, coalesce(sum(pg_total_relation_size(c.oid)), 0)::bigint
  FROM plat.tenant t
  LEFT JOIN pg_namespace n ON n.nspname = 'd_' || t.slug
  LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relkind IN ('r', 'm', 'p')
  GROUP BY t.id
$$;
REVOKE EXECUTE ON FUNCTION plat.tenant_dado_bytes() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenant_dado_bytes() TO plat_app;
