-- 20260908T1255_garage_por_inquilino: balde por inquilino no Garage com cota em BYTES e em OBJETOS, endpoint web ligável e
-- registro sem segredo (item L1-01-d-garage-por-inquilino; ADR 20260908T1255, que estende o ADR 0006). Estende
-- plat.arquivo_bucket (criada na 022) em vez de criar tabela nova; plat.tenant_bucket é a VISÃO sem os segredos
-- das chaves (security_invoker: a RLS de arquivo_bucket vale para quem consulta, nunca a do dono da visão).
-- As duas funções leitoras SECURITY DEFINER da 022 mudam de assinatura de retorno (colunas novas): DROP + CREATE
-- na mesma transação do migrar.sh (psql -1), depois REVOKE PUBLIC + GRANT plat_app como a 024/025.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS cota_objetos bigint NOT NULL DEFAULT 200000;
ALTER TABLE plat.arquivo_bucket ADD COLUMN IF NOT EXISTS cota_objetos bigint NOT NULL DEFAULT 200000;
ALTER TABLE plat.arquivo_bucket ADD COLUMN IF NOT EXISTS web_ativo boolean NOT NULL DEFAULT false;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_tenant_cota_objetos') THEN
    ALTER TABLE plat.tenant ADD CONSTRAINT ck_tenant_cota_objetos CHECK (cota_objetos > 0);
  END IF;
END $$;

DROP FUNCTION IF EXISTS plat.arquivo_bucket_resolver(text);
CREATE FUNCTION plat.arquivo_bucket_resolver(p_slug text)
RETURNS TABLE (
  tenant_id int, bucket_id text, bucket_alias text,
  chave_rw_id text, chave_rw_segredo text, chave_ro_id text, chave_ro_segredo text,
  cota_bytes bigint, cota_objetos bigint, web_ativo boolean
) LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes, b.cota_objetos, b.web_ativo
  FROM plat.arquivo_bucket b JOIN plat.tenant t ON t.id = b.tenant_id
  WHERE t.slug = p_slug;
$$;

DROP FUNCTION IF EXISTS plat.arquivo_bucket_por_tenant(int);
CREATE FUNCTION plat.arquivo_bucket_por_tenant(p_tenant_id int)
RETURNS TABLE (
  tenant_id int, bucket_id text, bucket_alias text,
  chave_rw_id text, chave_rw_segredo text, chave_ro_id text, chave_ro_segredo text,
  cota_bytes bigint, cota_objetos bigint, web_ativo boolean
) LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes, b.cota_objetos, b.web_ativo
  FROM plat.arquivo_bucket b WHERE b.tenant_id = p_tenant_id;
$$;

-- cota em bytes E em objetos e o estado do endpoint web, gravados juntos (a 022 só tinha cota_bytes)
CREATE OR REPLACE FUNCTION plat.arquivo_bucket_cotas_atualizar(
  p_tenant_id int, p_cota_bytes bigint, p_cota_objetos bigint, p_web_ativo boolean
) RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.arquivo_bucket
     SET cota_bytes = p_cota_bytes, cota_objetos = p_cota_objetos, web_ativo = p_web_ativo, atualizado_em = now()
   WHERE tenant_id = p_tenant_id;
$$;

REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_resolver(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_por_tenant(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_cotas_atualizar(int, bigint, bigint, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.arquivo_bucket_resolver(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.arquivo_bucket_por_tenant(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.arquivo_bucket_cotas_atualizar(int, bigint, bigint, boolean) TO plat_app;

-- registro do balde por inquilino SEM os segredos das chaves: o que uma tela de administração pode mostrar
-- (id do balde, alias, id da chave só-leitura, cotas, web). security_invoker = a RLS de arquivo_bucket
-- (tenant_id = plat.tenant_atual()) vale para plat_app, como na tabela.
CREATE OR REPLACE VIEW plat.tenant_bucket WITH (security_invoker = true) AS
  SELECT tenant_id, bucket_id, bucket_alias, chave_ro_id, cota_bytes, cota_objetos, web_ativo, criado_em, atualizado_em
  FROM plat.arquivo_bucket;
GRANT SELECT ON plat.tenant_bucket TO plat_app;
