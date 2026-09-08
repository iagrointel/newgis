-- 20260908T0815 (item L2-03-f): plat.camada_schema_garantir só concede USAGE ao plat_leitor quando ainda falta.
-- Antes, todo chamador (ingestão, fábrica de camada dos testes) reescrevia a ACL de d_<slug> em pg_namespace a
-- cada chamada; com dezenas de sessões concorrentes no MESMO schema (d_demo é partilhado por todas as trilhas
-- de teste) o Postgres responde "tuple concurrently updated" e a chamada morre. Mesma assinatura e semântica.
CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);
  IF NOT has_schema_privilege('plat_leitor', 'd_' || p_slug, 'USAGE') THEN
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
  END IF;
END $$;
