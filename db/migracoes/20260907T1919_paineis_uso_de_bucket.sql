-- item L7-06-d-paineis: uso de armazenamento por inquilino para o painel "Objetos".
--
-- Por que NÃO no postgres_exporter (que era o caminho óbvio): `plat.arquivo_bucket` e `plat.arquivo`
-- têm RLS por inquilino, e o papel de métrica não é dono nem tem BYPASSRLS — medido em 07/09/2026, a
-- consulta direta devolve ZERO linha e o painel ficaria vazio para sempre. Aqui a leitura passa por
-- função SECURITY DEFINER, igual ao que plat.fila_estado() já faz para a fila.
--
-- depende: 20260907T1902_paineis_backup_medida_e_usuarios_24h.sql

CREATE OR REPLACE FUNCTION plat.arquivo_bucket_uso()
RETURNS TABLE(tenant_id int, cota_bytes bigint, usado_bytes bigint, objetos bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id,
         b.cota_bytes,
         coalesce(sum(a.bytes), 0)::bigint,
         count(a.id)::bigint
  FROM plat.arquivo_bucket b
  LEFT JOIN plat.arquivo a ON a.tenant_id = b.tenant_id AND a.apagado_em IS NULL
  GROUP BY b.tenant_id, b.cota_bytes
$$;
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_uso() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.arquivo_bucket_uso() TO plat_app;
