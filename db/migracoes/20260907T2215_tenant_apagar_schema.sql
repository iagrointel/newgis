-- item L0-02-z-apagar-inquilino-apaga-schema: apagar inquilino apaga o schema de dado d_<slug> dele.
-- Incidente laco/handoffs/T4/INCIDENTE-schemas-zt.md (07/09): plat.tenant_apagar_interno apagava as linhas de
-- toda tabela com tenant_id, mas o schema de dado (criado por plat.tenant_criar/plat.camada_schema_garantir, com
-- as tabelas de camada e as funções de tile) ficava para trás — 1.219 schemas d_zt* acumulados pela suíte.
-- Agora o DROP SCHEMA ... CASCADE acontece na MESMA transação da função (DDL transacional: se algo falhar, volta
-- tudo), sob um trinco de transação por slug (pg_advisory_xact_lock) que plat.camada_schema_garantir também
-- passa a tomar: criar e apagar o schema do mesmo inquilino nunca correm ao mesmo tempo.
-- Correção de função já aplicada = arquivo novo (regra do ADR 0014); 009_inquilino_apagar.sql e 029 ficam como estão.
CREATE OR REPLACE FUNCTION plat.trinco_schema_dado(p_slug text) RETURNS void
LANGUAGE sql AS $$ SELECT pg_advisory_xact_lock(hashtext('plat.schema_dado:' || p_slug)) $$;

CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  PERFORM plat.trinco_schema_dado(p_slug);
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
END $$;

CREATE OR REPLACE FUNCTION plat.tenant_apagar_interno(p_id int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s text; r record; passo int; restantes int; apagadas int := 0;
BEGIN
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' THEN RAISE EXCEPTION 'plataforma_nao_apaga'; END IF;
  PERFORM plat.trinco_schema_dado(s);
  -- o gatilho do último admin recusaria apagar o admin do inquilino que está sendo apagado: desligado só aqui, na
  -- mesma transação (DDL transacional: volta sozinho se algo falhar). Nunca por GUC, que plat_app poderia forjar.
  ALTER TABLE plat.usuario DISABLE TRIGGER usuario_ultimo_admin;
  UPDATE plat.usuario SET papel_id = NULL WHERE tenant_id = p_id;
  UPDATE plat.token_servico SET renovado_por = NULL WHERE tenant_id = p_id;
  FOR passo IN 1..6 LOOP
    restantes := 0;
    FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
             WHERE n.nspname = 'plat' AND c.relkind IN ('r', 'p') AND c.relname <> 'tenant'
               AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)
             ORDER BY c.relname LOOP
      BEGIN
        EXECUTE format('DELETE FROM plat.%I WHERE tenant_id = $1', r.relname) USING p_id;
        GET DIAGNOSTICS apagadas = ROW_COUNT;
      EXCEPTION WHEN foreign_key_violation THEN
        restantes := restantes + 1;
      END;
    END LOOP;
    EXIT WHEN restantes = 0;
  END LOOP;
  IF restantes > 0 THEN RAISE EXCEPTION 'inquilino_com_dependencias'; END IF;
  DELETE FROM plat.tenant WHERE id = p_id;
  -- o schema de dado vai junto: tabelas de camada, funções de tile, políticas e índices (CASCADE), na mesma transação
  EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', 'd_' || s);
  ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
  RETURN p_id;
END $$;

REVOKE EXECUTE ON FUNCTION plat.tenant_apagar_interno(int) FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.trinco_schema_dado(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.trinco_schema_dado(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;
