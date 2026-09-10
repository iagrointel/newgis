-- 20260906T2136_cotas_uso_tenants (item L0-07-c-cotas-uso): plat.uso_tenants_ativos() — os inquilinos que o
-- periódico jobs.uso_medir percorre. Separada da 20260906T2124_cotas_uso.sql porque plat_worker não tem
-- política de RLS em plat.tenant (as políticas da 002 são TO plat_app), então a lista tem de vir de função
-- SECURITY DEFINER, mesmo padrão de plat.uso_buckets_listar. Idempotente. Sem BEGIN/COMMIT.

CREATE OR REPLACE FUNCTION plat.uso_tenants_ativos() RETURNS SETOF int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT id FROM plat.tenant WHERE ativo ORDER BY id
$$;

REVOKE EXECUTE ON FUNCTION plat.uso_tenants_ativos() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.uso_tenants_ativos() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.uso_tenants_ativos() TO plat_worker;
