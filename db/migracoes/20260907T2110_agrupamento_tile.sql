-- item L2-02-c-editor-simbologia-vetor: agrupamento de pontos (clusters) NO TILE, por função do Martin.
-- plat.camada_agrupar: agrupa os pontos de uma camada por célula de grade alinhada ao mundo, com o lado da
-- célula = 2 x raio_px em unidades de mapa do zoom pedido (512 px por tile, como o MapLibre); devolve o
-- centroide dos pontos da célula e point_count (NULL quando a célula tem 1 ponto: o MVT omite a propriedade e a
-- camada "não agrupado" do estilo o desenha). É a MESMA consulta que a função de tile usa — o teste do portão
-- chama esta função direto e confere a contagem contra COUNT(*) independente.
-- plat.camada_tile_agrupado_garantir: cria d_<slug>.t_<hex>_ag(z, x, y, query_params) ao lado da t_<hex> do
-- L2-01-b, com a mesma prova de token (plat.contexto_por_token) e o raio lido de query_params->>'raio'.
CREATE OR REPLACE FUNCTION plat.celula_agrupamento(z integer, raio_px numeric)
RETURNS double precision LANGUAGE sql IMMUTABLE AS $$
  SELECT (40075016.6855785 / (2 ^ z)) / 512.0 * 2.0 * raio_px
$$;

CREATE OR REPLACE FUNCTION plat.camada_agrupar(p_schema text, p_tabela text, z integer, x integer, y integer,
                                               raio_px numeric DEFAULT 40)
RETURNS TABLE (geom geometry, point_count bigint, cx double precision, cy double precision)
LANGUAGE plpgsql STABLE SECURITY INVOKER AS $$
DECLARE env geometry; cel double precision; srid int;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF z < 0 OR z > 24 OR x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
    RAISE EXCEPTION 'zxy_invalido' USING ERRCODE = '22023';
  END IF;
  IF raio_px IS NULL OR raio_px < 1 OR raio_px > 400 THEN
    RAISE EXCEPTION 'raio_invalido' USING ERRCODE = '22023';
  END IF;
  env := ST_TileEnvelope(z, x, y);
  cel := plat.celula_agrupamento(z, raio_px);
  SELECT coalesce(nullif(postgis_typmod_srid(a.atttypmod), 0), 4326) INTO srid
  FROM pg_attribute a WHERE a.attrelid = to_regclass(format('%I.%I', p_schema, p_tabela))
    AND a.attname = 'geom' AND NOT a.attisdropped;
  RETURN QUERY EXECUTE format($q$
    SELECT ST_Centroid(ST_Collect(g)) AS geom,
           CASE WHEN count(*) > 1 THEN count(*) END AS point_count,
           floor(ST_X(g) / %3$s) AS cx, floor(ST_Y(g) / %3$s) AS cy
    FROM (SELECT ST_Transform(t.geom, 3857) AS g FROM %1$I.%2$I t
          WHERE t.geom && ST_Transform($1, %4$s)) p
    GROUP BY floor(ST_X(g) / %3$s), floor(ST_Y(g) / %3$s)
  $q$, p_schema, p_tabela, cel, srid) USING env;
END $$;
REVOKE ALL ON FUNCTION plat.camada_agrupar(text, text, integer, integer, integer, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_agrupar(text, text, integer, integer, integer, numeric) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.celula_agrupamento(integer, numeric) TO PUBLIC;

CREATE OR REPLACE FUNCTION plat.camada_tile_agrupado_garantir(p_schema text, p_tabela text, p_item uuid)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE papel text := plat.papel_leitor(); curto text; nome text; tid int; corpo text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF to_regclass(format('%I.%I', p_schema, p_tabela)) IS NULL THEN
    RAISE EXCEPTION 'camada_inexistente';
  END IF;
  SELECT id INTO tid FROM plat.tenant WHERE 'd_' || slug = p_schema;
  IF tid IS NULL THEN RAISE EXCEPTION 'schema_sem_inquilino'; END IF;
  curto := substr(p_tabela, 3);
  nome := 't_' || curto || '_ag';
  corpo := format($f$
CREATE OR REPLACE FUNCTION %1$I.%2$I(z integer, x integer, y integer, query_params json DEFAULT '{}'::json)
RETURNS bytea LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $corpo$
DECLARE ctx int; env geometry; mvt bytea; raio numeric;
BEGIN
  ctx := plat.contexto_por_token(query_params->>'token', query_params->>'ip', query_params->>'origem',
                                 %5$L::uuid, 'camada:ler', %6$L);
  IF ctx IS DISTINCT FROM %3$L::int THEN
    RAISE EXCEPTION 'tile_de_outro_inquilino' USING ERRCODE = '42501';
  END IF;
  raio := coalesce(nullif(query_params->>'raio', '')::numeric, 40);
  env := ST_TileEnvelope(z, x, y);
  SELECT ST_AsMVT(q, %2$L, 4096, 'geom') INTO mvt FROM (
    SELECT ST_AsMVTGeom(a.geom, env, 4096, 64, true) AS geom, a.point_count
    FROM plat.camada_agrupar(%7$L, %4$L, z, x, y, raio) a
  ) q;
  RETURN coalesce(mvt, ''::bytea);
END $corpo$
$f$, p_schema, nome, tid, p_tabela, p_item, '/tiles/' || p_schema || '/' || nome, p_schema);
  EXECUTE corpo;
  EXECUTE format('COMMENT ON FUNCTION %I.%I(integer,integer,integer,json) IS %L', p_schema, nome,
                 'tile MVT agrupado (clusters por célula) da camada ' || p_tabela || ' (item L2-02-c)');
  EXECUTE format('REVOKE ALL ON FUNCTION %I.%I(integer,integer,integer,json) FROM PUBLIC', p_schema, nome);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(integer,integer,integer,json) TO %I, plat_app', p_schema, nome, papel);
  EXECUTE format('GRANT EXECUTE ON FUNCTION plat.camada_agrupar(text, text, integer, integer, integer, numeric) TO %I', papel);
  RETURN nome;
END $$;
REVOKE ALL ON FUNCTION plat.camada_tile_agrupado_garantir(text, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_tile_agrupado_garantir(text, text, uuid) TO plat_app;
