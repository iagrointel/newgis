-- plat.camada_schema_garantir ganha trava de transação por slug (item L6-02-i-google-sheets; achado da
-- rodada completa da suíte de conexões). Com dois processos de worker carregando a 1ª camada do MESMO
-- inquilino ao mesmo tempo, os dois executavam CREATE SCHEMA IF NOT EXISTS + GRANT USAGE no mesmo schema
-- concorrentemente; o GRANT reescreve a ACL da mesma tupla do catálogo e o Postgres recusa a atualização
-- simultânea com "tuple concurrently updated" — o job falhava sem defeito no dado. A trava
-- pg_advisory_xact_lock serializa as duas chamadas por slug: a segunda espera a primeira commitar e reconfere
-- o IF NOT EXISTS sobre o estado novo. Trava de transação: some com o commit, sem ponto de falha novo.

CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('plat:camada_schema_garantir:' || p_slug)::bigint);
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
END $$;
