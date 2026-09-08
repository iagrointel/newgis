-- Trinco de aconselhamento em plat.camada_tile_garantir (ADR 0025). Idempotente. Sem BEGIN/COMMIT.
-- depende: 20260906T1955_martin_generalizacao.sql
-- depende: 20260907T0240_ddl_concorrente_trinco.sql
--
-- Achado ao juntar este ramo com master: a 20260907T0240 pôs o trinco na CLASSE das funções SECURITY
-- DEFINER que fazem DDL, mas `camada_tile_garantir` foi redefinida por um carimbo ANTERIOR
-- (20260906T1955) e por isso ficou de fora — exatamente o risco que o cabeçalho da 0240 anuncia. A
-- guarda `tests/api/test_camada_schema_corrida.py::test_toda_funcao_com_ddl_tem_trinco` acusa. Aqui a
-- função é redefinida inteira, igual à 20260906T1955, com os dois trincos acrescentados.

CREATE OR REPLACE FUNCTION plat.camada_tile_garantir(p_schema text, p_tabela text, p_item uuid DEFAULT NULL)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  papel text := plat.papel_leitor();
  curto text; nome text; tid int; srid int; colunas text; corpo text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF to_regclass(format('%I.%I', p_schema, p_tabela)) IS NULL THEN
    RAISE EXCEPTION 'camada_inexistente';
  END IF;
  SELECT id INTO tid FROM plat.tenant WHERE 'd_' || slug = p_schema;
  IF tid IS NULL THEN RAISE EXCEPTION 'schema_sem_inquilino'; END IF;

  -- Trinco de aconselhamento por transação (ADR 0025). Esta função emite GRANT USAGE no schema (linha de
  -- pg_namespace, a mesma que camada_schema_garantir atualiza) e GRANT SELECT + CREATE POLICY na tabela da
  -- camada (a mesma que camada_preparar toca). Sem serialização, duas publicações simultâneas do mesmo
  -- inquilino levam `tuple concurrently updated`. As chaves são as MESMAS das outras duas funções, para
  -- que o trinco valha entre funções diferentes, e são tomadas sempre nesta ordem (schema antes de
  -- tabela); nenhuma outra função toma as duas, logo não há ciclo de espera.
  PERFORM pg_advisory_xact_lock(hashtext('camada_schema_garantir:' || substr(p_schema, 3)));
  PERFORM pg_advisory_xact_lock(hashtext('camada_preparar:' || p_schema || '.' || p_tabela));
  curto := substr(p_tabela, 3);
  nome  := 't_' || curto;
  SELECT coalesce(nullif(postgis_typmod_srid(a.atttypmod), 0), 4326) INTO srid
  FROM pg_attribute a WHERE a.attrelid = to_regclass(format('%I.%I', p_schema, p_tabela))
    AND a.attname = 'geom' AND NOT a.attisdropped;
  IF srid IS NULL THEN RAISE EXCEPTION 'camada_sem_geometria'; END IF;

  -- atributos: tudo menos a geometria e as colunas de controle interno
  SELECT string_agg(format('t.%I', a.attname), ', ' ORDER BY a.attnum) INTO colunas
  FROM pg_attribute a WHERE a.attrelid = to_regclass(format('%I.%I', p_schema, p_tabela))
    AND a.attnum > 0 AND NOT a.attisdropped
    AND a.attname NOT IN ('geom', 'tenant_id', 'criado_por', 'atualizado_por');

  corpo := format($f$
CREATE OR REPLACE FUNCTION %1$I.%2$I(z integer, x integer, y integer, query_params json DEFAULT '{}'::json)
RETURNS bytea LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $corpo$
DECLARE ctx int; env geometry; mvt bytea; tol double precision; total bigint;
BEGIN
  IF z < 0 OR z > 24 OR x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
    RAISE EXCEPTION 'zxy_invalido' USING ERRCODE = '22023';
  END IF;
  ctx := plat.contexto_por_token(query_params->>'token', query_params->>'ip', query_params->>'origem',
                                 %6$L::uuid, 'camada:ler', %7$L);
  IF ctx IS DISTINCT FROM %3$L::int THEN
    RAISE EXCEPTION 'tile_de_outro_inquilino' USING ERRCODE = '42501';
  END IF;
  env := ST_TileEnvelope(z, x, y);
  tol := CASE WHEN z < 12 THEN (ST_XMax(env) - ST_XMin(env)) / 4096.0 / 2.0 ELSE 0 END;
  SELECT count(*) INTO total FROM %1$I.%4$I t WHERE t.geom && ST_Transform(env, %8$L::int);
  SELECT ST_AsMVT(q, %2$L, 4096, 'geom') INTO mvt FROM (
    SELECT ST_AsMVTGeom(
             CASE WHEN tol > 0 THEN ST_SimplifyPreserveTopology(ST_Transform(t.geom, 3857), tol)
                  ELSE ST_Transform(t.geom, 3857) END,
             env, 4096, 64, true) AS geom%5$s, (total > 10000) AS _truncado
    FROM %1$I.%4$I t
    WHERE t.geom && ST_Transform(env, %8$L::int)
    ORDER BY t.fid
    LIMIT 10000
  ) q;
  RETURN coalesce(mvt, ''::bytea);
END $corpo$
$f$,
    p_schema, nome, tid, p_tabela,
    CASE WHEN colunas IS NULL OR colunas = '' THEN '' ELSE ', ' || colunas END,
    p_item, '/tiles/' || p_schema || '/' || nome, srid);
  EXECUTE corpo;

  -- Política de RLS do papel de leitura: separada da de plat_app e ancorada na PROVA, não na GUC crua.
  EXECUTE format('DROP POLICY IF EXISTS p_c_%s ON %I.%I', curto, p_schema, p_tabela);
  EXECUTE format('CREATE POLICY p_c_%s ON %I.%I FOR ALL TO plat_app '
                 'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
                 curto, p_schema, p_tabela);
  EXECUTE format('DROP POLICY IF EXISTS p_c_%s_leitor ON %I.%I', curto, p_schema, p_tabela);
  EXECUTE format('CREATE POLICY p_c_%s_leitor ON %I.%I FOR SELECT TO %I '
                 'USING (tenant_id = (SELECT plat.tenant_leitor()))',
                 curto, p_schema, p_tabela, papel);

  EXECUTE format('COMMENT ON FUNCTION %I.%I(integer,integer,integer,json) IS %L', p_schema, nome,
                 'tile MVT da camada ' || p_tabela || ' (itens L2-04-a/L2-01-b); contexto por token, '
                 'generalização por zoom, limite de 10.000 feições');
  EXECUTE format('REVOKE ALL ON FUNCTION %I.%I(integer,integer,integer,json) FROM PUBLIC', p_schema, nome);
  IF NOT has_schema_privilege(papel, p_schema, 'USAGE') THEN
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', p_schema, papel);
  END IF;
  IF NOT has_table_privilege(papel, format('%I.%I', p_schema, p_tabela), 'SELECT') THEN
    EXECUTE format('GRANT SELECT ON %I.%I TO %I', p_schema, p_tabela, papel);
  END IF;
  EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(integer,integer,integer,json) TO %I, plat_app',
                 p_schema, nome, papel);
  RETURN nome;
END $$;
