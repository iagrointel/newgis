--
-- PostgreSQL database dump
--

\restrict 3o8SEWEytSkB4vtaO3j7UB27JcLMb0qcDGtjI0C90pOeLgojX7ZeIpxp3mhSYqU

-- Dumped from database version 16.13 (Ubuntu 16.13-1.pgdg24.04+1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-1.pgdg24.04+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgstac; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA pgstac;


--
-- Name: plat; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA plat;


--
-- Name: plat_trabalho; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA plat_trabalho;


--
-- Name: additional_properties(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.additional_properties() RETURNS boolean
    LANGUAGE sql
    AS $$

    SELECT pgstac.get_setting_bool('additional_properties');

$$;


--
-- Name: age_ms(timestamp with time zone, timestamp with time zone); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.age_ms(a timestamp with time zone, b timestamp with time zone DEFAULT clock_timestamp()) RETURNS double precision
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT abs(extract(epoch from age(a,b)) * 1000);

$$;


--
-- Name: all_collections(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.all_collections() RETURNS jsonb
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    SELECT coalesce(jsonb_agg(content), '[]'::jsonb) FROM collections;

$$;


--
-- Name: analyze_items(); Type: PROCEDURE; Schema: pgstac; Owner: -
--

CREATE PROCEDURE pgstac.analyze_items()
    LANGUAGE plpgsql
    AS $$

DECLARE

    q text;

    timeout_ts timestamptz;

BEGIN

    timeout_ts := statement_timestamp() + queue_timeout();

    WHILE clock_timestamp() < timeout_ts LOOP

        SELECT format('ANALYZE (VERBOSE, SKIP_LOCKED) %I;', relname) INTO q

        FROM pg_stat_user_tables

        WHERE relname like '_item%' AND (n_mod_since_analyze>0 OR last_analyze IS NULL) LIMIT 1;

        IF NOT FOUND THEN

            EXIT;

        END IF;

        RAISE NOTICE '%', q;

        EXECUTE q;

        COMMIT;

    END LOOP;

END;

$$;


--
-- Name: array_intersection(anyarray, anyarray); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.array_intersection(_a anyarray, _b anyarray) RETURNS anyarray
    LANGUAGE sql IMMUTABLE
    AS $$

  SELECT ARRAY ( SELECT unnest(_a) INTERSECT SELECT UNNEST(_b) );

$$;


--
-- Name: array_map_ident(text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.array_map_ident(_a text[]) RETURNS text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

  SELECT array_agg(quote_ident(v)) FROM unnest(_a) v;

$$;


--
-- Name: array_map_literal(text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.array_map_literal(_a text[]) RETURNS text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

  SELECT array_agg(quote_literal(v)) FROM unnest(_a) v;

$$;


--
-- Name: array_reverse(anyarray); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.array_reverse(anyarray) RETURNS anyarray
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$

SELECT ARRAY(

    SELECT $1[i]

    FROM generate_subscripts($1,1) AS s(i)

    ORDER BY i DESC

);

$_$;


--
-- Name: array_to_path(text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.array_to_path(arr text[]) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$

    SELECT string_agg(

        quote_literal(v),

        '->'

    ) FROM unnest(arr) v;

$$;


--
-- Name: base_url(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.base_url(conf jsonb DEFAULT NULL::jsonb) RETURNS text
    LANGUAGE sql
    AS $$

  SELECT COALESCE(pgstac.get_setting('base_url', conf), '.');

$$;


--
-- Name: bbox_geom(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.bbox_geom(_bbox jsonb) RETURNS public.geometry
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$

SELECT CASE jsonb_array_length(_bbox)

    WHEN 4 THEN

        ST_SetSRID(ST_MakeEnvelope(

            (_bbox->>0)::float,

            (_bbox->>1)::float,

            (_bbox->>2)::float,

            (_bbox->>3)::float

        ),4326)

    WHEN 6 THEN

    ST_SetSRID(ST_3DMakeBox(

        ST_MakePoint(

            (_bbox->>0)::float,

            (_bbox->>1)::float,

            (_bbox->>2)::float

        ),

        ST_MakePoint(

            (_bbox->>3)::float,

            (_bbox->>4)::float,

            (_bbox->>5)::float

        )

    ),4326)

    ELSE null END;

;

$$;


--
-- Name: check_partition(text, tstzrange, tstzrange); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.check_partition(_collection text, _dtrange tstzrange, _edtrange tstzrange) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    c RECORD;

    pm RECORD;

    _partition_name text;

    _partition_dtrange tstzrange;

    _constraint_dtrange tstzrange;

    _constraint_edtrange tstzrange;

    q text;

    err_context text;

BEGIN

    SELECT * INTO c FROM pgstac.collections WHERE id=_collection;

    IF NOT FOUND THEN

        RAISE EXCEPTION 'Collection % does not exist', _collection USING ERRCODE = 'foreign_key_violation', HINT = 'Make sure collection exists before adding items';

    END IF;



    IF c.partition_trunc IS NOT NULL THEN

        _partition_dtrange := tstzrange(

            date_trunc(c.partition_trunc, lower(_dtrange)),

            date_trunc(c.partition_trunc, lower(_dtrange)) + (concat('1 ', c.partition_trunc))::interval,

            '[)'

        );

    ELSE

        _partition_dtrange :=  '[-infinity, infinity]'::tstzrange;

    END IF;



    IF NOT _partition_dtrange @> _dtrange THEN

        RAISE EXCEPTION 'dtrange % is greater than the partition size % for collection %', _dtrange, c.partition_trunc, _collection;

    END IF;





    IF c.partition_trunc = 'year' THEN

        _partition_name := format('_items_%s_%s', c.key, to_char(lower(_partition_dtrange),'YYYY'));

    ELSIF c.partition_trunc = 'month' THEN

        _partition_name := format('_items_%s_%s', c.key, to_char(lower(_partition_dtrange),'YYYYMM'));

    ELSE

        _partition_name := format('_items_%s', c.key);

    END IF;



    -- Constraint ranges are maintained asynchronously, so they come from the

    -- catalog rather than partition_stats.

    SELECT ps.partition, m.constraint_dtrange, m.constraint_edtrange

        INTO pm

    FROM partition_stats ps

        JOIN LATERAL partition_catalog_meta(ps.partition) m ON TRUE

    WHERE ps.collection = _collection AND ps.partition_dtrange @> _dtrange

    LIMIT 1;

    IF FOUND THEN

        RAISE NOTICE '% % %', _edtrange, _dtrange, pm;

        _constraint_edtrange :=

            tstzrange(

                least(

                    lower(_edtrange),

                    nullif(lower(pm.constraint_edtrange), '-infinity')

                ),

                greatest(

                    upper(_edtrange),

                    nullif(upper(pm.constraint_edtrange), 'infinity')

                ),

                '[]'

            );

        _constraint_dtrange :=

            tstzrange(

                least(

                    lower(_dtrange),

                    nullif(lower(pm.constraint_dtrange), '-infinity')

                ),

                greatest(

                    upper(_dtrange),

                    nullif(upper(pm.constraint_dtrange), 'infinity')

                ),

                '[]'

            );



        IF pm.constraint_edtrange @> _edtrange AND pm.constraint_dtrange @> _dtrange THEN

            RETURN pm.partition;

        ELSE

            PERFORM drop_table_constraints(_partition_name);

        END IF;

    ELSE

        _constraint_edtrange := _edtrange;

        _constraint_dtrange := _dtrange;

    END IF;

    RAISE NOTICE 'EXISTING CONSTRAINTS % %, NEW % %', pm.constraint_dtrange, pm.constraint_edtrange, _constraint_dtrange, _constraint_edtrange;

    RAISE NOTICE 'Creating partition % %', _partition_name, _partition_dtrange;

    IF c.partition_trunc IS NULL THEN

        q := format(

            $q$

                CREATE TABLE IF NOT EXISTS %I partition OF items FOR VALUES IN (%L);

                CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I (id);

                GRANT ALL ON %I to pgstac_ingest;

            $q$,

            _partition_name,

            _collection,

            concat(_partition_name,'_pk'),

            _partition_name,

            _partition_name

        );

    ELSE

        q := format(

            $q$

                CREATE TABLE IF NOT EXISTS %I partition OF items FOR VALUES IN (%L) PARTITION BY RANGE (datetime);

                CREATE TABLE IF NOT EXISTS %I partition OF %I FOR VALUES FROM (%L) TO (%L);

                CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I (id);

                GRANT ALL ON %I TO pgstac_ingest;

            $q$,

            format('_items_%s', c.key),

            _collection,

            _partition_name,

            format('_items_%s', c.key),

            lower(_partition_dtrange),

            upper(_partition_dtrange),

            format('%s_pk', _partition_name),

            _partition_name,

            _partition_name

        );

    END IF;



    BEGIN

        EXECUTE q;

    EXCEPTION

        WHEN duplicate_table THEN

            RAISE NOTICE 'Partition % already exists.', _partition_name;

        WHEN others THEN

            GET STACKED DIAGNOSTICS err_context = PG_EXCEPTION_CONTEXT;

            RAISE INFO 'Error Name:%',SQLERRM;

            RAISE INFO 'Error State:%', SQLSTATE;

            RAISE INFO 'Error Context:%', err_context;

    END;

    -- The _constraint_ ranges are the union of the existing constraint and the

    -- incoming batch, so they hold for rows already present as well as the ones

    -- about to be added. Queueable: rebuilding validates the partition under an

    -- ACCESS EXCLUSIVE lock.

    PERFORM run_or_queue(format(

        'SELECT create_table_constraints(%L, %L, %L);',

        _partition_name,

        _constraint_dtrange,

        _constraint_edtrange

    ));

    PERFORM maintain_partitions(_partition_name);

    -- Search finds partitions through partition_stats, so the row has to exist

    -- before this transaction commits. A queued stats update has not written it.

    IF NOT update_partition_stats_q(_partition_name, true) THEN

        INSERT INTO partition_stats (partition, collection, partition_dtrange)

            VALUES (_partition_name, _collection, _partition_dtrange)

            ON CONFLICT (partition) DO UPDATE

                SET collection = EXCLUDED.collection,

                    partition_dtrange = EXCLUDED.partition_dtrange

                WHERE

                    partition_stats.collection IS DISTINCT FROM EXCLUDED.collection

                    OR partition_stats.partition_dtrange IS DISTINCT FROM EXCLUDED.partition_dtrange

        ;

    END IF;

    RETURN _partition_name;

END;

$_$;


--
-- Name: check_pgstac_settings(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.check_pgstac_settings(_sysmem text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    SET client_min_messages TO 'notice'
    AS $$

DECLARE

    settingval text;

    sysmem bigint := pg_size_bytes(_sysmem);

    effective_cache_size bigint := pg_size_bytes(current_setting('effective_cache_size', TRUE));

    shared_buffers bigint := pg_size_bytes(current_setting('shared_buffers', TRUE));

    work_mem bigint := pg_size_bytes(current_setting('work_mem', TRUE));

    max_connections int := current_setting('max_connections', TRUE);

    maintenance_work_mem bigint := pg_size_bytes(current_setting('maintenance_work_mem', TRUE));

    seq_page_cost float := current_setting('seq_page_cost', TRUE);

    random_page_cost float := current_setting('random_page_cost', TRUE);

    temp_buffers bigint := pg_size_bytes(current_setting('temp_buffers', TRUE));

    r record;

BEGIN

    IF _sysmem IS NULL THEN

      RAISE NOTICE 'Call function with the size of your system memory `SELECT check_pgstac_settings(''4GB'')` to get pg system setting recommendations.';

    ELSE

        IF effective_cache_size < (sysmem * 0.5) THEN

            RAISE WARNING 'effective_cache_size of % is set low for a system with %. Recomended value between % and %', pg_size_pretty(effective_cache_size), pg_size_pretty(sysmem), pg_size_pretty(sysmem * 0.5), pg_size_pretty(sysmem * 0.75);

        ELSIF effective_cache_size > (sysmem * 0.75) THEN

            RAISE WARNING 'effective_cache_size of % is set high for a system with %. Recomended value between % and %', pg_size_pretty(effective_cache_size), pg_size_pretty(sysmem), pg_size_pretty(sysmem * 0.5), pg_size_pretty(sysmem * 0.75);

        ELSE

            RAISE NOTICE 'effective_cache_size of % is set appropriately for a system with %', pg_size_pretty(effective_cache_size), pg_size_pretty(sysmem);

        END IF;



        IF shared_buffers < (sysmem * 0.2) THEN

            RAISE WARNING 'shared_buffers of % is set low for a system with %. Recomended value between % and %', pg_size_pretty(shared_buffers), pg_size_pretty(sysmem), pg_size_pretty(sysmem * 0.2), pg_size_pretty(sysmem * 0.3);

        ELSIF shared_buffers > (sysmem * 0.3) THEN

            RAISE WARNING 'shared_buffers of % is set high for a system with %. Recomended value between % and %', pg_size_pretty(shared_buffers), pg_size_pretty(sysmem), pg_size_pretty(sysmem * 0.2), pg_size_pretty(sysmem * 0.3);

        ELSE

            RAISE NOTICE 'shared_buffers of % is set appropriately for a system with %', pg_size_pretty(shared_buffers), pg_size_pretty(sysmem);

        END IF;

        shared_buffers = sysmem * 0.3;

        IF maintenance_work_mem < (sysmem * 0.2) THEN

            RAISE WARNING 'maintenance_work_mem of % is set low for shared_buffers of %. Recomended value between % and %', pg_size_pretty(maintenance_work_mem), pg_size_pretty(shared_buffers), pg_size_pretty(shared_buffers * 0.2), pg_size_pretty(shared_buffers * 0.3);

        ELSIF maintenance_work_mem > (shared_buffers * 0.3) THEN

            RAISE WARNING 'maintenance_work_mem of % is set high for shared_buffers of %. Recomended value between % and %', pg_size_pretty(maintenance_work_mem), pg_size_pretty(shared_buffers), pg_size_pretty(shared_buffers * 0.2), pg_size_pretty(shared_buffers * 0.3);

        ELSE

            RAISE NOTICE 'maintenance_work_mem of % is set appropriately for shared_buffers of %', pg_size_pretty(shared_buffers), pg_size_pretty(shared_buffers);

        END IF;



        IF work_mem * max_connections > shared_buffers THEN

            RAISE WARNING 'work_mem setting of % is set high for % max_connections please reduce work_mem to % or decrease max_connections to %', pg_size_pretty(work_mem), max_connections, pg_size_pretty(shared_buffers/max_connections), floor(shared_buffers/work_mem);

        ELSIF work_mem * max_connections < (shared_buffers * 0.75) THEN

            RAISE WARNING 'work_mem setting of % is set low for % max_connections you may consider raising work_mem to % or increasing max_connections to %', pg_size_pretty(work_mem), max_connections, pg_size_pretty(shared_buffers/max_connections), floor(shared_buffers/work_mem);

        ELSE

            RAISE NOTICE 'work_mem setting of % and max_connections of % are adequate for shared_buffers of %', pg_size_pretty(work_mem), max_connections, pg_size_pretty(shared_buffers);

        END IF;



        IF random_page_cost / seq_page_cost != 1.1 THEN

            RAISE WARNING 'random_page_cost (%) /seq_page_cost (%) should be set to 1.1 for SSD. Change random_page_cost to %', random_page_cost, seq_page_cost, 1.1 * seq_page_cost;

        ELSE

            RAISE NOTICE 'random_page_cost and seq_page_cost set appropriately for SSD';

        END IF;



        IF temp_buffers < greatest(pg_size_bytes('128MB'),(maintenance_work_mem / 2)) THEN

            RAISE WARNING 'pgstac makes heavy use of temp tables, consider raising temp_buffers from % to %', pg_size_pretty(temp_buffers), greatest('128MB', pg_size_pretty((shared_buffers / 16)));

        END IF;

    END IF;



    RAISE NOTICE 'VALUES FOR PGSTAC VARIABLES';

    RAISE NOTICE 'These can be set either as GUC system variables or by setting in the pgstac_settings table.';



    FOR r IN SELECT name, get_setting(name) as setting, CASE WHEN current_setting(concat('pgstac.',name), TRUE) IS NOT NULL THEN concat('pgstac.',name, ' GUC') WHEN value IS NOT NULL THEN 'pgstac_settings table' ELSE 'Not Set' END as loc FROM pgstac_settings LOOP

      RAISE NOTICE '% is set to % from the %', r.name, r.setting, r.loc;

    END LOOP;



    SELECT installed_version INTO settingval from pg_available_extensions WHERE name = 'pg_cron';

    IF NOT FOUND OR settingval IS NULL THEN

        RAISE NOTICE 'Consider intalling pg_cron which can be used to automate tasks';

    ELSE

        RAISE NOTICE 'pg_cron % is installed', settingval;

    END IF;



    SELECT installed_version INTO settingval from pg_available_extensions WHERE name = 'pgstattuple';

    IF NOT FOUND OR settingval IS NULL THEN

        RAISE NOTICE 'Consider installing the pgstattuple extension which can be used to help maintain tables and indexes.';

    ELSE

        RAISE NOTICE 'pgstattuple % is installed', settingval;

    END IF;



    SELECT installed_version INTO settingval from pg_available_extensions WHERE name = 'pg_stat_statements';

    IF NOT FOUND OR settingval IS NULL THEN

        RAISE NOTICE 'Consider installing the pg_stat_statements extension which is very helpful for tracking the types of queries on the system';

    ELSE

        RAISE NOTICE 'pg_stat_statements % is installed', settingval;

        IF current_setting('pg_stat_statements.track_statements', TRUE) IS DISTINCT FROM 'all' THEN

            RAISE WARNING 'SET pg_stat_statements.track_statements TO ''all''; --In order to track statements within functions.';

        END IF;

    END IF;



    -- Undrained queue means stale statistics and constraints, silently.

    SELECT count(*) INTO settingval FROM query_queue;

    IF settingval::bigint > 0 THEN

        RAISE WARNING '% queries are waiting in query_queue. Run "CALL run_queued_queries();" (pypgstac runqueue) to drain it -- until then partition statistics and constraints are stale.', settingval;

    END IF;



END;

$$;


--
-- Name: chunker(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.chunker(_where text, OUT s timestamp with time zone, OUT e timestamp with time zone) RETURNS SETOF record
    LANGUAGE plpgsql
    AS $_$

DECLARE

    explain jsonb;

BEGIN

    IF _where IS NULL THEN

        _where := ' TRUE ';

    END IF;

    EXECUTE format('EXPLAIN (format json) SELECT 1 FROM items WHERE %s;', _where)

    INTO explain;

    RAISE DEBUG 'EXPLAIN: %', explain;



    RETURN QUERY

    WITH t AS (

        SELECT j->>0 as p FROM

            jsonb_path_query(

                explain,

                'strict $.**."Relation Name" ? (@ != null)'

            ) j

    ),

    parts AS (

        -- = ANY(array) uses the partition_stats primary key; the planner

        -- cannot estimate jsonb_path_query, so a join plans as a full scan.

        SELECT

            date_trunc('month', lower(partition_dtrange)) as sdate,

            date_trunc('month', upper(partition_dtrange)) + '1 month'::interval as edate

        FROM partition_stats

        WHERE

            partition = ANY (ARRAY(SELECT p FROM t))

            AND partition_dtrange IS NOT NULL

            AND partition_dtrange != 'empty'::tstzrange

    ),

    times AS (

        SELECT sdate FROM parts

        UNION

        SELECT edate FROM parts

    ),

    uniq AS (

        SELECT DISTINCT sdate FROM times ORDER BY sdate

    ),

    last AS (

    SELECT sdate, lead(sdate, 1) over () as edate FROM uniq

    )

    SELECT sdate, edate FROM last WHERE edate IS NOT NULL;

END;

$_$;


--
-- Name: collection_base_item(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_base_item(content jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT jsonb_build_object(

        'type', 'Feature',

        'stac_version', content->'stac_version',

        'assets', content->'item_assets',

        'collection', content->'id'

    );

$$;


--
-- Name: collection_base_item(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_base_item(cid text) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT pgstac.collection_base_item(content) FROM pgstac.collections WHERE id = cid LIMIT 1;

$$;


--
-- Name: collection_bbox(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_bbox(id text) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET search_path TO 'pgstac', 'public'
    AS $_$

    SELECT (replace(replace(replace(st_extent(geometry)::text,'BOX(','[['),')',']]'),' ',','))::jsonb

    FROM items WHERE collection=$1;

    ;

$_$;


--
-- Name: collection_datetime(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_datetime(content jsonb) RETURNS timestamp with time zone
    LANGUAGE sql IMMUTABLE STRICT
    AS $$

    SELECT

        CASE

            WHEN

                (content->'extent'->'temporal'->'interval'->0->>0) IS NULL

            THEN '-infinity'::timestamptz

            ELSE

                (content->'extent'->'temporal'->'interval'->0->>0)::timestamptz

        END

    ;

$$;


--
-- Name: collection_delete_trigger_func(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_delete_trigger_func() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$

DECLARE

    collection_base_partition text := concat('_items_', OLD.key);

BEGIN

    -- Tables before rows: check_partition takes these locks in the same order,

    -- and the reverse deadlocks against a concurrent partition create.

    EXECUTE format($q$

        DROP TABLE IF EXISTS %I CASCADE;

        DELETE FROM partition_stats WHERE collection=%L;

        $q$,

        collection_base_partition,

        OLD.id

    );

    RETURN OLD;

END;

$_$;


--
-- Name: collection_enddatetime(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_enddatetime(content jsonb) RETURNS timestamp with time zone
    LANGUAGE sql IMMUTABLE STRICT
    AS $$

    SELECT

        CASE

            WHEN

                (content->'extent'->'temporal'->'interval'->0->>1) IS NULL

            THEN 'infinity'::timestamptz

            ELSE

                (content->'extent'->'temporal'->'interval'->0->>1)::timestamptz

        END

    ;

$$;


--
-- Name: collection_extent(text, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_extent(_collection text, runupdate boolean DEFAULT false) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$

DECLARE

    geom_extent geometry;

    mind timestamptz;

    maxd timestamptz;

    extent jsonb;

    _partition text;

BEGIN

    IF runupdate THEN

        -- Not queued: the aggregate below reads what this writes. Ordered by

        -- partition, as every other multi-partition writer is.

        FOR _partition IN

            SELECT partition FROM partition_stats

            WHERE collection=_collection

            ORDER BY partition

        LOOP

            PERFORM update_partition_stats(_partition, false, true);

        END LOOP;

    END IF;

    SELECT

        min(lower(dtrange)),

        max(upper(edtrange)),

        st_extent(spatial)

    INTO

        mind,

        maxd,

        geom_extent

    FROM partition_stats

    WHERE collection=_collection;



    IF geom_extent IS NOT NULL AND mind IS NOT NULL AND maxd IS NOT NULL THEN

        extent := jsonb_build_object(

                'spatial', jsonb_build_object(

                    'bbox', to_jsonb(array[array[st_xmin(geom_extent), st_ymin(geom_extent), st_xmax(geom_extent), st_ymax(geom_extent)]])

                ),

                'temporal', jsonb_build_object(

                    'interval', to_jsonb(array[array[mind, maxd]])

                )

        );

        RETURN extent;

    END IF;

    RETURN NULL;

END;

$$;


--
-- Name: collection_geom(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_geom(content jsonb) RETURNS public.geometry
    LANGUAGE sql IMMUTABLE STRICT
    AS $$

    WITH box AS (SELECT content->'extent'->'spatial'->'bbox'->0 as box)

    SELECT

        st_makeenvelope(

            (box->>0)::float,

            (box->>1)::float,

            (box->>2)::float,

            (box->>3)::float,

            4326

        )

    FROM box;

$$;


--
-- Name: collection_search(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_search(_search jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
    LANGUAGE plpgsql STABLE PARALLEL SAFE
    AS $$

DECLARE

    out_records jsonb;

    number_matched bigint := collection_search_matched(_search);

    number_returned bigint;

    _limit int := coalesce((_search->>'limit')::float::int, 10);

    _offset int := coalesce((_search->>'offset')::float::int, 0);

    links jsonb := '[]';

    ret jsonb;

    base_url text:= concat(rtrim(base_url(_search->'conf'),'/'), '/collections');

    prevoffset int;

    nextoffset int;

BEGIN

    SELECT

        coalesce(jsonb_agg(c), '[]')

    INTO out_records

    FROM collection_search_rows(_search) c;



    number_returned := jsonb_array_length(out_records);

    RAISE DEBUG 'nm: %, nr: %, l:%, o:%', number_matched, number_returned, _limit, _offset;







    IF _limit <= number_matched AND number_matched > 0 THEN --need to have paging links

        nextoffset := least(_offset + _limit, number_matched - 1);

        prevoffset := greatest(_offset - _limit, 0);



        IF _offset > 0 THEN

            links := links || jsonb_build_object(

                    'rel', 'prev',

                    'type', 'application/json',

                    'method', 'GET' ,

                    'href', base_url,

                    'body', jsonb_build_object('offset', prevoffset),

                    'merge', TRUE

                );

        END IF;



        IF (_offset + _limit < number_matched)  THEN

            links := links || jsonb_build_object(

                    'rel', 'next',

                    'type', 'application/json',

                    'method', 'GET' ,

                    'href', base_url,

                    'body', jsonb_build_object('offset', nextoffset),

                    'merge', TRUE

                );

        END IF;



    END IF;



    ret := jsonb_build_object(

        'collections', out_records,

        'numberMatched', number_matched,

        'numberReturned', number_returned,

        'links', links

    );

    RETURN ret;



END;

$$;


--
-- Name: collection_search_matched(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_search_matched(_search jsonb DEFAULT '{}'::jsonb, OUT matched bigint) RETURNS bigint
    LANGUAGE plpgsql STABLE PARALLEL SAFE
    AS $_$

DECLARE

    _where text := stac_search_to_where(_search);

BEGIN

    EXECUTE format(

        $query$

            SELECT

                count(*)

            FROM

                collections_asitems

            WHERE %s

            ;

        $query$,

        _where

    ) INTO matched;

    RETURN;

END;

$_$;


--
-- Name: collection_search_rows(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_search_rows(_search jsonb DEFAULT '{}'::jsonb) RETURNS SETOF jsonb
    LANGUAGE plpgsql
    AS $_$

DECLARE

    _where text := stac_search_to_where(_search);

    _limit int := coalesce((_search->>'limit')::int, 10);

    _fields jsonb := coalesce(_search->'fields', '{}'::jsonb);

    _orderby text;

    _offset int := COALESCE((_search->>'offset')::int, 0);

BEGIN

    _orderby := sort_sqlorderby(

        jsonb_build_object(

            'sortby',

            coalesce(

                _search->'sortby',

                '[{"field": "id", "direction": "asc"}]'::jsonb

            )

        )

    );

    RETURN QUERY EXECUTE format(

        $query$

            SELECT

                jsonb_fields(collectionjson, %L) as c

            FROM

                collections_asitems

            WHERE %s

            ORDER BY %s

            LIMIT %L

            OFFSET %L

            ;

        $query$,

        _fields,

        _where,

        _orderby,

        _limit,

        _offset

    );

END;

$_$;


--
-- Name: collection_temporal_extent(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collection_temporal_extent(id text) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET search_path TO 'pgstac', 'public'
    AS $_$

    SELECT to_jsonb(array[array[min(datetime), max(datetime)]])

    FROM items WHERE collection=$1;

;

$_$;


--
-- Name: collections_trigger_func(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.collections_trigger_func() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

DECLARE

    q text;

    partition_name text := format('_items_%s', NEW.key);

    partition_exists boolean := false;

    partition_empty boolean := true;

    err_context text;

    loadtemp boolean := FALSE;

BEGIN

    RAISE NOTICE 'Collection Trigger. % %', NEW.id, NEW.key;

    IF TG_OP = 'UPDATE' AND NEW.partition_trunc IS DISTINCT FROM OLD.partition_trunc THEN

        PERFORM repartition(NEW.id, NEW.partition_trunc, TRUE);

    END IF;

    RETURN NEW;

END;

$$;


--
-- Name: constraint_tstzrange(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.constraint_tstzrange(expr text) RETURNS tstzrange
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$

    WITH t AS (

        SELECT regexp_matches(

            expr,

            E'\\(''\([0-9 :+-]*\)''\\).*\\(''\([0-9 :+-]*\)''\\)'

        ) AS m

    ) SELECT tstzrange(m[1]::timestamptz, m[2]::timestamptz) FROM t

    ;

$$;


SET default_tablespace = '';

--
-- Name: items; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.items (
    id text NOT NULL,
    geometry public.geometry NOT NULL,
    collection text NOT NULL,
    datetime timestamp with time zone NOT NULL,
    end_datetime timestamp with time zone NOT NULL,
    content jsonb NOT NULL,
    private jsonb
)
PARTITION BY LIST (collection);


--
-- Name: content_dehydrate(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.content_dehydrate(content jsonb) RETURNS pgstac.items
    LANGUAGE sql STABLE
    AS $$

    SELECT

            content->>'id' as id,

            stac_geom(content) as geometry,

            content->>'collection' as collection,

            stac_datetime(content) as datetime,

            stac_end_datetime(content) as end_datetime,

            content_slim(content) as content,

            null::jsonb as private

    ;

$$;


--
-- Name: content_hydrate(pgstac.items, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.content_hydrate(_item pgstac.items, fields jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
    LANGUAGE sql STABLE
    AS $$

    SELECT content_hydrate(

        _item,

        (SELECT c FROM collections c WHERE id=_item.collection LIMIT 1),

        fields

    );

$$;


--
-- Name: content_hydrate(jsonb, jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.content_hydrate(_item jsonb, _base_item jsonb, fields jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT merge_jsonb(

            jsonb_fields(_item, fields),

            jsonb_fields(_base_item, fields)

    );

$$;


SET default_table_access_method = heap;

--
-- Name: collections; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.collections (
    key bigint NOT NULL,
    id text GENERATED ALWAYS AS ((content ->> 'id'::text)) STORED NOT NULL,
    content jsonb NOT NULL,
    base_item jsonb GENERATED ALWAYS AS (pgstac.collection_base_item(content)) STORED,
    geometry public.geometry GENERATED ALWAYS AS (pgstac.collection_geom(content)) STORED,
    datetime timestamp with time zone GENERATED ALWAYS AS (pgstac.collection_datetime(content)) STORED,
    end_datetime timestamp with time zone GENERATED ALWAYS AS (pgstac.collection_enddatetime(content)) STORED,
    private jsonb,
    partition_trunc text,
    CONSTRAINT collections_partition_trunc_check CHECK ((partition_trunc = ANY (ARRAY['year'::text, 'month'::text])))
);


--
-- Name: content_hydrate(pgstac.items, pgstac.collections, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.content_hydrate(_item pgstac.items, _collection pgstac.collections, fields jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
    LANGUAGE plpgsql STABLE PARALLEL SAFE
    AS $$

DECLARE

    geom jsonb;

    bbox jsonb;

    output jsonb;

    content jsonb;

    base_item jsonb := _collection.base_item;

BEGIN

    IF include_field('geometry', fields) THEN

        geom := ST_ASGeoJson(_item.geometry, 20)::jsonb;

    END IF;

    output := content_hydrate(

        jsonb_build_object(

            'id', _item.id,

            'geometry', geom,

            'collection', _item.collection,

            'type', 'Feature'

        ) || _item.content,

        _collection.base_item,

        fields

    );



    RETURN output;

END;

$$;


--
-- Name: content_nonhydrated(pgstac.items, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.content_nonhydrated(_item pgstac.items, fields jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
    LANGUAGE plpgsql STABLE PARALLEL SAFE
    AS $$

DECLARE

    geom jsonb;

    bbox jsonb;

    output jsonb;

BEGIN

    IF include_field('geometry', fields) THEN

        geom := ST_ASGeoJson(_item.geometry, 20)::jsonb;

    END IF;

    output := jsonb_build_object(

                'id', _item.id,

                'geometry', geom,

                'collection', _item.collection,

                'type', 'Feature'

            ) || _item.content;

    RETURN output;

END;

$$;


--
-- Name: content_slim(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.content_slim(_item jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT strip_jsonb(_item - '{id,geometry,collection,type}'::text[], collection_base_item(_item->>'collection')) - '{id,geometry,collection,type}'::text[];

$$;


--
-- Name: context(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.context(conf jsonb DEFAULT NULL::jsonb) RETURNS text
    LANGUAGE sql
    AS $$

  SELECT pgstac.get_setting('context', conf);

$$;


--
-- Name: context_estimated_cost(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.context_estimated_cost(conf jsonb DEFAULT NULL::jsonb) RETURNS double precision
    LANGUAGE sql
    AS $$

  SELECT pgstac.get_setting('context_estimated_cost', conf)::float;

$$;


--
-- Name: context_estimated_count(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.context_estimated_count(conf jsonb DEFAULT NULL::jsonb) RETURNS integer
    LANGUAGE sql
    AS $$

  SELECT pgstac.get_setting('context_estimated_count', conf)::int;

$$;


--
-- Name: context_stats_ttl(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.context_stats_ttl(conf jsonb DEFAULT NULL::jsonb) RETURNS interval
    LANGUAGE sql
    AS $$

  SELECT pgstac.get_setting('context_stats_ttl', conf)::interval;

$$;


--
-- Name: cql1_to_cql2(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.cql1_to_cql2(j jsonb) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE STRICT
    AS $$

DECLARE

    args jsonb;

    ret jsonb;

BEGIN

    RAISE NOTICE 'CQL1_TO_CQL2: %', j;

    IF j ? 'filter' THEN

        RETURN cql1_to_cql2(j->'filter');

    END IF;

    IF j ? 'property' THEN

        RETURN j;

    END IF;

    IF jsonb_typeof(j) = 'array' THEN

        SELECT jsonb_agg(cql1_to_cql2(el)) INTO args FROM jsonb_array_elements(j) el;

        RETURN args;

    END IF;

    IF jsonb_typeof(j) = 'number' THEN

        RETURN j;

    END IF;

    IF jsonb_typeof(j) = 'string' THEN

        RETURN j;

    END IF;



    IF jsonb_typeof(j) = 'object' THEN

        SELECT jsonb_build_object(

                'op', key,

                'args', cql1_to_cql2(value)

            ) INTO ret

        FROM jsonb_each(j)

        WHERE j IS NOT NULL;

        RETURN ret;

    END IF;

    RETURN NULL;

END;

$$;


--
-- Name: cql2_query(jsonb, text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.cql2_query(j jsonb, wrapper text DEFAULT NULL::text) RETURNS text
    LANGUAGE plpgsql STABLE
    AS $_$

#variable_conflict use_variable

DECLARE

    args jsonb := j->'args';

    arg jsonb;

    op text := lower(j->>'op');

    cql2op RECORD;

    literal text;

    _wrapper text;

    leftarg text;

    rightarg text;

    prop text;

    extra_props bool := pgstac.additional_properties();

BEGIN

    IF j IS NULL OR (op IS NOT NULL AND args IS NULL) THEN

        RETURN NULL;

    END IF;

    RAISE NOTICE 'CQL2_QUERY: %', j;



    -- check if all properties are represented in the queryables

    IF NOT extra_props THEN

        FOR prop IN

            SELECT DISTINCT p->>0

            FROM jsonb_path_query(j, 'strict $.**.property') p

            WHERE p->>0 NOT IN ('id', 'datetime', 'geometry', 'end_datetime', 'collection')

        LOOP

            IF (queryable(prop)).nulled_wrapper IS NULL THEN

                RAISE EXCEPTION 'Term % is not found in queryables.', prop;

            END IF;

        END LOOP;

    END IF;



    IF j ? 'filter' THEN

        RETURN cql2_query(j->'filter');

    END IF;



    IF j ? 'upper' THEN

        RETURN  cql2_query(jsonb_build_object('op', 'upper', 'args', j->'upper'));

    END IF;



    IF j ? 'lower' THEN

        RETURN  cql2_query(jsonb_build_object('op', 'lower', 'args', j->'lower'));

    END IF;



    -- Temporal Query

    IF op ilike 't_%' or op = 'anyinteracts' THEN

        RETURN temporal_op_query(op, args);

    END IF;



    -- If property is a timestamp convert it to text to use with

    -- general operators

    IF j ? 'timestamp' THEN

        RETURN format('%L::timestamptz', to_tstz(j->'timestamp'));

    END IF;

    IF j ? 'interval' THEN

        RAISE EXCEPTION 'Please use temporal operators when using intervals.';

        RETURN NONE;

    END IF;



    -- Spatial Query

    IF op ilike 's_%' or op = 'intersects' THEN

        RETURN spatial_op_query(op, args);

    END IF;



    IF op IN ('a_equals','a_contains','a_contained_by','a_overlaps') THEN

        IF args->0 ? 'property' THEN

            leftarg := format('to_text_array(%s)', (queryable(args->0->>'property')).path);

        END IF;

        IF args->1 ? 'property' THEN

            rightarg := format('to_text_array(%s)', (queryable(args->1->>'property')).path);

        END IF;

        RETURN FORMAT(

            '%s %s %s',

            COALESCE(leftarg, quote_literal(to_text_array(args->0))),

            CASE op

                WHEN 'a_equals' THEN '='

                WHEN 'a_contains' THEN '@>'

                WHEN 'a_contained_by' THEN '<@'

                WHEN 'a_overlaps' THEN '&&'

            END,

            COALESCE(rightarg, quote_literal(to_text_array(args->1)))

        );

    END IF;



    IF op = 'in' THEN

        RAISE NOTICE 'IN : % % %', args, jsonb_build_array(args->0), args->1;

        args := jsonb_build_array(args->0) || (args->1);

        RAISE NOTICE 'IN2 : %', args;

    END IF;







    IF op = 'between' THEN

        args = jsonb_build_array(

            args->0,

            args->1,

            args->2

        );

    END IF;



    -- Make sure that args is an array and run cql2_query on

    -- each element of the array

    RAISE NOTICE 'ARGS PRE: %', args;

    IF j ? 'args' THEN

        IF jsonb_typeof(args) != 'array' THEN

            args := jsonb_build_array(args);

        END IF;



        IF jsonb_path_exists(args, '$[*] ? (@.property == "id" || @.property == "datetime" || @.property == "end_datetime" || @.property == "collection")') THEN

            wrapper := NULL;

        ELSE

            -- if any of the arguments are a property, try to get the property_wrapper

            FOR arg IN SELECT jsonb_path_query(args, '$[*] ? (@.property != null)') LOOP

                RAISE NOTICE 'Arg: %', arg;

                wrapper := (queryable(arg->>'property')).nulled_wrapper;

                RAISE NOTICE 'Property: %, Wrapper: %', arg, wrapper;

                IF wrapper IS NOT NULL THEN

                    EXIT;

                END IF;

            END LOOP;



            -- if the property was not in queryables, see if any args were numbers

            IF

                wrapper IS NULL

                AND jsonb_path_exists(args, '$[*] ? (@.type()=="number")')

            THEN

                wrapper := 'to_float';

            END IF;

            wrapper := coalesce(wrapper, 'to_text');

        END IF;



        SELECT jsonb_agg(cql2_query(a, wrapper))

            INTO args

        FROM jsonb_array_elements(args) a;

    END IF;

    RAISE NOTICE 'ARGS: %', args;



    IF op IN ('and', 'or') THEN

        RETURN

            format(

                '(%s)',

                array_to_string(to_text_array(args), format(' %s ', upper(op)))

            );

    END IF;



    IF op = 'in' THEN

        RAISE NOTICE 'IN --  % %', args->0, to_text(args->0);

        RETURN format(

            '%s IN (%s)',

            to_text(args->0),

            array_to_string((to_text_array(args))[2:], ',')

        );

    END IF;



    -- Look up template from cql2_ops

    IF j ? 'op' THEN

        SELECT * INTO cql2op FROM cql2_ops WHERE  cql2_ops.op ilike op;

        IF FOUND THEN

            -- If specific index set in queryables for a property cast other arguments to that type



            RETURN format(

                cql2op.template,

                VARIADIC (to_text_array(args))

            );

        ELSE

            RAISE EXCEPTION 'Operator % Not Supported.', op;

        END IF;

    END IF;





    IF wrapper IS NOT NULL THEN

        RAISE NOTICE 'Wrapping % with %', j, wrapper;

        IF j ? 'property' THEN

            RETURN format('%I(%s)', wrapper, (queryable(j->>'property')).path);

        ELSE

            RETURN format('%I(%L)', wrapper, j);

        END IF;

    ELSIF j ? 'property' THEN

        RETURN quote_ident(j->>'property');

    END IF;



    RETURN quote_literal(to_text(j));

END;

$_$;


--
-- Name: create_collection(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.create_collection(data jsonb) RETURNS void
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    INSERT INTO collections (content)

    VALUES (data)

    ;

$$;


--
-- Name: create_item(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.create_item(data jsonb) RETURNS void
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    INSERT INTO items_staging (content) VALUES (data);

$$;


--
-- Name: create_items(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.create_items(data jsonb) RETURNS void
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    INSERT INTO items_staging (content)

    SELECT * FROM jsonb_array_elements(data);

$$;


--
-- Name: create_table_constraints(text, tstzrange, tstzrange); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.create_table_constraints(t text, _dtrange tstzrange, _edtrange tstzrange) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    q text;

    _oid oid := partition_oid(t);

BEGIN

    IF _oid IS NULL THEN

        RETURN NULL;

    END IF;

    -- Only partitions of items. This runs elevated, so without the check it

    -- would alter any table pgstac_admin owns that the caller names.

    IF NOT EXISTS (SELECT 1 FROM partition_catalog_meta(t)) THEN

        RETURN NULL;

    END IF;

    -- Reduce to the bare name so the ALTER statements below quote it correctly

    -- even when the caller passed a schema qualified name.

    t := get_partition_name(_oid);

    RAISE NOTICE 'Creating Table Constraints for % % %', t, _dtrange, _edtrange;

    IF _dtrange = 'empty' AND _edtrange = 'empty' THEN

        q :=format(

            $q$

                DO $block$

                BEGIN

                    ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I;

                    ALTER TABLE %I

                        ADD CONSTRAINT %I

                            CHECK (((datetime IS NULL) AND (end_datetime IS NULL))) NOT VALID

                    ;

                    ALTER TABLE %I

                        VALIDATE CONSTRAINT %I

                    ;







                EXCEPTION WHEN others THEN

                    RAISE WARNING '%%, Issue Altering Constraints. Please run update_partition_stats(%I)', SQLERRM USING ERRCODE = SQLSTATE;

                END;

                $block$;

            $q$,

            t,

            format('%s_dt', t),

            t,

            format('%s_dt', t),

            t,

            format('%s_dt', t),

            t

        );

    ELSE

        q :=format(

            $q$

                DO $block$

                BEGIN



                    ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I;

                    ALTER TABLE %I

                        ADD CONSTRAINT %I

                            CHECK (

                                (datetime >= %L)

                                AND (datetime <= %L)

                                AND (end_datetime >= %L)

                                AND (end_datetime <= %L)

                            ) NOT VALID

                    ;

                    ALTER TABLE %I

                        VALIDATE CONSTRAINT %I

                    ;







                EXCEPTION WHEN others THEN

                    RAISE WARNING '%%, Issue Altering Constraints. Please run update_partition_stats(%I)', SQLERRM USING ERRCODE = SQLSTATE;

                END;

                $block$;

            $q$,

            t,

            format('%s_dt', t),

            t,

            format('%s_dt', t),

            lower(_dtrange),

            upper(_dtrange),

            lower(_edtrange),

            upper(_edtrange),

            t,

            format('%s_dt', t),

            t

        );

    END IF;

    -- Run, not queued: the queue runner is not a definer, so queued DDL

    -- executes as whoever drains it. Defer by queueing a call to this function.

    EXECUTE q;

    RETURN t;

END;

$_$;


--
-- Name: delete_collection(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.delete_collection(_id text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pgstac', 'public'
    AS $$

BEGIN

    DELETE FROM collections WHERE id = _id;

    IF NOT FOUND THEN

        RAISE EXCEPTION 'Collection % does not exist', _id USING ERRCODE = 'no_data_found';

    END IF;

END;

$$;


--
-- Name: delete_item(text, text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.delete_item(_id text, _collection text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql
    AS $$

DECLARE

out items%ROWTYPE;

BEGIN

    DELETE FROM items WHERE id = _id AND (_collection IS NULL OR collection=_collection) RETURNING * INTO STRICT out;

END;

$$;


--
-- Name: drop_table_constraints(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.drop_table_constraints(t text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    q text;

    _oid oid := partition_oid(t);

BEGIN

    IF _oid IS NULL THEN

        RETURN NULL;

    END IF;

    -- Only partitions of items. This runs elevated, so without the check it

    -- would alter any table pgstac_admin owns that the caller names.

    IF NOT EXISTS (SELECT 1 FROM partition_catalog_meta(t)) THEN

        RETURN NULL;

    END IF;

    -- Reduce to the bare name so the ALTER statements below quote it correctly

    -- even when the caller passed a schema qualified name.

    t := get_partition_name(_oid);

    FOR q IN SELECT FORMAT(

        $q$

            ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I;

        $q$,

        t,

        conname

    ) FROM pg_constraint

        WHERE conrelid=_oid AND contype='c'

    LOOP

        EXECUTE q;

    END LOOP;

    RETURN t;

END;

$_$;


--
-- Name: empty_arr(anyarray); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.empty_arr(anyarray) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $_$

SELECT CASE

  WHEN $1 IS NULL THEN TRUE

  WHEN cardinality($1)<1 THEN TRUE

ELSE FALSE

END;

$_$;


--
-- Name: explode_dotpaths(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.explode_dotpaths(j jsonb) RETURNS SETOF text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT string_to_array(p, '.') as e FROM jsonb_array_elements_text(j) p;

$$;


--
-- Name: explode_dotpaths_recurse(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.explode_dotpaths_recurse(j jsonb) RETURNS SETOF text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    WITH RECURSIVE t AS (

        SELECT e FROM explode_dotpaths(j) e

        UNION ALL

        SELECT e[1:cardinality(e)-1]

        FROM t

        WHERE cardinality(e)>1

    ) SELECT e FROM t;

$$;


--
-- Name: first_notnull_sfunc(anyelement, anyelement); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.first_notnull_sfunc(anyelement, anyelement) RETURNS anyelement
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $_$

    SELECT COALESCE($1,$2);

$_$;


--
-- Name: flip_jsonb_array(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.flip_jsonb_array(j jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT jsonb_agg(value) FROM (SELECT value FROM jsonb_array_elements(j) WITH ORDINALITY ORDER BY ordinality DESC) as t;

$$;


--
-- Name: format_item(pgstac.items, jsonb, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.format_item(_item pgstac.items, _fields jsonb DEFAULT '{}'::jsonb, _hydrated boolean DEFAULT true) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$

DECLARE

    cache bool := get_setting_bool('format_cache');

    _output jsonb := null;

    t timestamptz := clock_timestamp();

BEGIN

    IF cache THEN

        SELECT output INTO _output FROM format_item_cache

        WHERE id=_item.id AND collection=_item.collection AND fields=_fields::text AND hydrated=_hydrated;

    END IF;

    IF _output IS NULL THEN

        IF _hydrated THEN

            _output := content_hydrate(_item, _fields);

        ELSE

            _output := content_nonhydrated(_item, _fields);

        END IF;

    END IF;

    IF cache THEN

        INSERT INTO format_item_cache (id, collection, fields, hydrated, output, timetoformat)

            VALUES (_item.id, _item.collection, _fields::text, _hydrated, _output, age_ms(t))

            ON CONFLICT(collection, id, fields, hydrated) DO

                UPDATE

                    SET lastused=now(), usecount = format_item_cache.usecount + 1

        ;

    END IF;

    RETURN _output;



END;

$$;


--
-- Name: ftime(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.ftime() RETURNS interval
    LANGUAGE sql
    AS $$

SELECT age(clock_timestamp(), transaction_timestamp());

$$;


--
-- Name: geojsonsearch(jsonb, text, jsonb, integer, integer, interval, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.geojsonsearch(geojson jsonb, queryhash text, fields jsonb DEFAULT NULL::jsonb, _scanlimit integer DEFAULT 10000, _limit integer DEFAULT 100, _timelimit interval DEFAULT '00:00:05'::interval, exitwhenfull boolean DEFAULT true, skipcovered boolean DEFAULT true) RETURNS jsonb
    LANGUAGE sql
    AS $$

    SELECT * FROM geometrysearch(

        st_geomfromgeojson(geojson),

        queryhash,

        fields,

        _scanlimit,

        _limit,

        _timelimit,

        exitwhenfull,

        skipcovered

    );

$$;


--
-- Name: geom_bbox(public.geometry); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.geom_bbox(_geom public.geometry) RETURNS jsonb
    LANGUAGE sql IMMUTABLE STRICT
    AS $$

    SELECT jsonb_build_array(

        st_xmin(_geom),

        st_ymin(_geom),

        st_xmax(_geom),

        st_ymax(_geom)

    );

$$;


--
-- Name: geometrysearch(public.geometry, text, jsonb, integer, integer, interval, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.geometrysearch(geom public.geometry, queryhash text, fields jsonb DEFAULT NULL::jsonb, _scanlimit integer DEFAULT 10000, _limit integer DEFAULT 100, _timelimit interval DEFAULT '00:00:05'::interval, exitwhenfull boolean DEFAULT true, skipcovered boolean DEFAULT true) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$

DECLARE

    search searches%ROWTYPE;

    curs refcursor;

    _where text;

    query text;

    iter_record items%ROWTYPE;

    out_records jsonb := '{}'::jsonb[];

    exit_flag boolean := FALSE;

    counter int := 1;

    scancounter int := 1;

    remaining_limit int := _scanlimit;

    tilearea float;

    unionedgeom geometry;

    clippedgeom geometry;

    unionedgeom_area float := 0;

    prev_area float := 0;

    excludes text[];

    includes text[];



BEGIN

    DROP TABLE IF EXISTS pgstac_results;

    CREATE TEMP TABLE pgstac_results (content jsonb) ON COMMIT DROP;



    -- If the passed in geometry is not an area set exitwhenfull and skipcovered to false

    IF ST_GeometryType(geom) !~* 'polygon' THEN

        RAISE NOTICE 'GEOMETRY IS NOT AN AREA';

        skipcovered = FALSE;

        exitwhenfull = FALSE;

    END IF;



    -- If skipcovered is true then you will always want to exit when the passed in geometry is full

    IF skipcovered THEN

        exitwhenfull := TRUE;

    END IF;



    search := search_fromhash(queryhash);



    IF search IS NULL THEN

        RAISE EXCEPTION 'Search with Query Hash % Not Found', queryhash;

    END IF;



    tilearea := st_area(geom);

    _where := format('%s AND st_intersects(geometry, %L::geometry)', search._where, geom);





    FOR query IN SELECT * FROM partition_queries(_where, search.orderby) LOOP

        query := format('%s LIMIT %L', query, remaining_limit);

        RAISE NOTICE '%', query;

        OPEN curs FOR EXECUTE query;

        LOOP

            FETCH curs INTO iter_record;

            EXIT WHEN NOT FOUND;

            IF exitwhenfull OR skipcovered THEN -- If we are not using exitwhenfull or skipcovered, we do not need to do expensive geometry operations

                clippedgeom := st_intersection(geom, iter_record.geometry);



                IF unionedgeom IS NULL THEN

                    unionedgeom := clippedgeom;

                ELSE

                    unionedgeom := st_union(unionedgeom, clippedgeom);

                END IF;



                unionedgeom_area := st_area(unionedgeom);



                IF skipcovered AND prev_area = unionedgeom_area THEN

                    scancounter := scancounter + 1;

                    CONTINUE;

                END IF;



                prev_area := unionedgeom_area;



                RAISE NOTICE '% % % %', unionedgeom_area/tilearea, counter, scancounter, ftime();

            END IF;

            RAISE NOTICE '% %', iter_record, content_hydrate(iter_record, fields);

            INSERT INTO pgstac_results (content) VALUES (content_hydrate(iter_record, fields));



            IF counter >= _limit

                OR scancounter > _scanlimit

                OR ftime() > _timelimit

                OR (exitwhenfull AND unionedgeom_area >= tilearea)

            THEN

                exit_flag := TRUE;

                EXIT;

            END IF;

            counter := counter + 1;

            scancounter := scancounter + 1;



        END LOOP;

        CLOSE curs;

        EXIT WHEN exit_flag;

        remaining_limit := _scanlimit - scancounter;

    END LOOP;



    SELECT jsonb_agg(content) INTO out_records FROM pgstac_results WHERE content IS NOT NULL;



    RETURN jsonb_build_object(

        'type', 'FeatureCollection',

        'features', coalesce(out_records, '[]'::jsonb)

    );

END;

$$;


--
-- Name: get_collection(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_collection(id text) RETURNS jsonb
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $_$

    SELECT content FROM collections

    WHERE id=$1

    ;

$_$;


--
-- Name: get_item(text, text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_item(_id text, _collection text DEFAULT NULL::text) RETURNS jsonb
    LANGUAGE sql STABLE
    SET search_path TO 'pgstac', 'public'
    AS $$

    SELECT content_hydrate(items) FROM items WHERE id=_id AND (_collection IS NULL OR collection=_collection);

$$;


--
-- Name: get_partition_name(regclass); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_partition_name(relid regclass) RETURNS text
    LANGUAGE sql STABLE STRICT
    AS $$

    SELECT (parse_ident(relid::text))[cardinality(parse_ident(relid::text))];

$$;


--
-- Name: get_queryables(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_queryables() RETURNS jsonb
    LANGUAGE sql
    AS $$

    SELECT get_queryables(NULL::text[]);

$$;


--
-- Name: get_queryables(text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_queryables(_collection_ids text[] DEFAULT NULL::text[]) RETURNS jsonb
    LANGUAGE plpgsql STABLE
    AS $_$

DECLARE

BEGIN

    -- Build up queryables if the input contains valid collection ids or is empty

    IF EXISTS (

        SELECT 1 FROM collections

        WHERE

            _collection_ids IS NULL

            OR cardinality(_collection_ids) = 0

            OR id = ANY(_collection_ids)

    )

    THEN

        RETURN (

            WITH base AS (

                SELECT

                    unnest(collection_ids) as collection_id,

                    name,

                    coalesce(definition, '{"type":"string"}'::jsonb) as definition

                FROM queryables

                WHERE

                    _collection_ids IS NULL OR

                    _collection_ids = '{}'::text[] OR

                    _collection_ids && collection_ids

                UNION ALL

                SELECT null, name, coalesce(definition, '{"type":"string"}'::jsonb) as definition

                FROM queryables WHERE collection_ids IS NULL OR collection_ids = '{}'::text[]

            ), g AS (

                SELECT

                    name,

                    first_notnull(definition) as definition,

                    jsonb_array_unique_merge(definition->'enum') as enum,

                    jsonb_min(definition->'minimum') as minimum,

                    jsonb_min(definition->'maxiumn') as maximum

                FROM base

                GROUP BY 1

            )

            SELECT

                jsonb_build_object(

                    '$schema', 'http://json-schema.org/draft-07/schema#',

                    '$id', '',

                    'type', 'object',

                    'title', 'STAC Queryables.',

                    'properties', jsonb_object_agg(

                        name,

                        definition

                        ||

                        jsonb_strip_nulls(jsonb_build_object(

                            'enum', enum,

                            'minimum', minimum,

                            'maximum', maximum

                        ))

                    ),

                    'additionalProperties', pgstac.additional_properties()

                )

                FROM g

        );

    ELSE

        RETURN NULL;

    END IF;

END;

$_$;


--
-- Name: get_queryables(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_queryables(_collection text DEFAULT NULL::text) RETURNS jsonb
    LANGUAGE sql
    AS $$

    SELECT

        CASE

            WHEN _collection IS NULL THEN get_queryables(NULL::text[])

            ELSE get_queryables(ARRAY[_collection])

        END

    ;

$$;


--
-- Name: get_setting(text, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_setting(_setting text, conf jsonb DEFAULT NULL::jsonb) RETURNS text
    LANGUAGE sql
    AS $$

SELECT COALESCE(

  nullif(conf->>_setting, ''),

  nullif(current_setting(concat('pgstac.',_setting), TRUE),''),

  nullif((SELECT value FROM pgstac.pgstac_settings WHERE name=_setting),'')

);

$$;


--
-- Name: get_setting_bool(text, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_setting_bool(_setting text, conf jsonb DEFAULT NULL::jsonb) RETURNS boolean
    LANGUAGE sql
    AS $$

SELECT COALESCE(

  nullif(conf->>_setting, ''),

  nullif(current_setting(concat('pgstac.',_setting), TRUE),''),

  nullif((SELECT value FROM pgstac.pgstac_settings WHERE name=_setting),''),

  'FALSE'

)::boolean;

$$;


--
-- Name: get_sort_dir(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_sort_dir(sort_item jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT CASE WHEN sort_item->>'direction' ILIKE 'desc%' THEN 'DESC' ELSE 'ASC' END;

$$;


--
-- Name: get_token_filter(jsonb, pgstac.items, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_token_filter(_sortby jsonb DEFAULT '[{"field": "datetime", "direction": "desc"}]'::jsonb, token_item pgstac.items DEFAULT NULL::pgstac.items, prev boolean DEFAULT false, inclusive boolean DEFAULT false) RETURNS text
    LANGUAGE plpgsql
    SET transform_null_equals TO 'true'
    AS $_$

DECLARE

    ltop text := '<';

    gtop text := '>';

    dir text;

    sort record;

    orfilter text := '';

    orfilters text[] := '{}'::text[];

    andfilters text[] := '{}'::text[];

    output text;

    token_where text;

BEGIN

    IF _sortby IS NULL OR _sortby = '[]'::jsonb THEN

        _sortby := '[{"field":"datetime","direction":"desc"}]'::jsonb;

    END IF;

    _sortby := _sortby || jsonb_build_object('field','id','direction',_sortby->0->>'direction');

    RAISE NOTICE 'Getting Token Filter. % %', _sortby, token_item;

    IF inclusive THEN

        orfilters := orfilters || format('( id=%L AND collection=%L )' , token_item.id, token_item.collection);

    END IF;



    FOR sort IN

        WITH s1 AS (

            SELECT

                _row,

                (queryable(value->>'field')).expression as _field,

                (value->>'field' = 'id') as _isid,

                get_sort_dir(value) as _dir

            FROM jsonb_array_elements(_sortby)

            WITH ORDINALITY AS t(value, _row)

        )

        SELECT

            _row,

            _field,

            _dir,

            get_token_val_str(_field, token_item) as _val

        FROM s1

        WHERE _row <= (SELECT min(_row) FROM s1 WHERE _isid)

    LOOP

        orfilter := NULL;

        RAISE NOTICE 'SORT: %', sort;

        IF sort._val IS NOT NULL AND  ((prev AND sort._dir = 'ASC') OR (NOT prev AND sort._dir = 'DESC')) THEN

            orfilter := format($f$(

                (%s %s %s) OR (%s IS NULL)

            )$f$,

            sort._field,

            ltop,

            sort._val,

            sort._val

            );

        ELSIF sort._val IS NULL AND  ((prev AND sort._dir = 'ASC') OR (NOT prev AND sort._dir = 'DESC')) THEN

            RAISE NOTICE '< but null';

            orfilter := format('%s IS NOT NULL', sort._field);

        ELSIF sort._val IS NULL THEN

            RAISE NOTICE '> but null';

        ELSE

            orfilter := format($f$(

                (%s %s %s) OR (%s IS NULL)

            )$f$,

            sort._field,

            gtop,

            sort._val,

            sort._field

            );

        END IF;

        RAISE NOTICE 'ORFILTER: %', orfilter;



        IF orfilter IS NOT NULL THEN

            IF sort._row = 1 THEN

                orfilters := orfilters || orfilter;

            ELSE

                orfilters := orfilters || format('(%s AND %s)', array_to_string(andfilters, ' AND '), orfilter);

            END IF;

        END IF;

        IF sort._val IS NOT NULL THEN

            andfilters := andfilters || format('%s = %s', sort._field, sort._val);

        ELSE

            andfilters := andfilters || format('%s IS NULL', sort._field);

        END IF;

    END LOOP;



    output := array_to_string(orfilters, ' OR ');



    token_where := concat('(',coalesce(output,'true'),')');

    IF trim(token_where) = '' THEN

        token_where := NULL;

    END IF;

    RAISE NOTICE 'TOKEN_WHERE: %',token_where;

    RETURN token_where;

    END;

$_$;


--
-- Name: get_token_record(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_token_record(_token text, OUT prev boolean, OUT item pgstac.items) RETURNS record
    LANGUAGE plpgsql STABLE STRICT
    AS $$

DECLARE

    _itemid text := _token;

    _collectionid text;

BEGIN

    IF _token IS NULL THEN

        RETURN;

    END IF;

    RAISE NOTICE 'Looking for token: %', _token;

    prev := FALSE;

    IF _token ILIKE 'prev:%' THEN

        _itemid := replace(_token, 'prev:','');

        prev := TRUE;

    ELSIF _token ILIKE 'next:%' THEN

        _itemid := replace(_token, 'next:', '');

    END IF;

    SELECT id INTO _collectionid FROM collections WHERE _itemid LIKE concat(id,':%');

    IF FOUND THEN

        _itemid := replace(_itemid, concat(_collectionid,':'), '');

        SELECT * INTO item FROM items WHERE id=_itemid AND collection=_collectionid;

    ELSE

        SELECT * INTO item FROM items WHERE id=_itemid;

    END IF;

    IF item IS NULL THEN

        RAISE EXCEPTION 'Could not find item using token: % item: % collection: %', _token, _itemid, _collectionid;

    END IF;

    RETURN;

END;

$$;


--
-- Name: get_token_val_str(text, pgstac.items); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_token_val_str(_field text, _item pgstac.items) RETURNS text
    LANGUAGE plpgsql
    AS $_$

DECLARE

    q text;

    literal text;

BEGIN

    q := format($q$ SELECT quote_literal(%s) FROM (SELECT $1.*) as r;$q$, _field);

    EXECUTE q INTO literal USING _item;

    RETURN literal;

END;

$_$;


--
-- Name: get_tstz_constraint(oid, text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_tstz_constraint(reloid oid, colname text) RETURNS tstzrange
    LANGUAGE plpgsql STABLE STRICT
    AS $_$

DECLARE

    expr text := NULL;

    m text[];

    ts_lower timestamptz := NULL;

    ts_upper timestamptz := NULL;

    lower_inclusive text := '[';

    upper_inclusive text := ']';

    ts timestamptz;

BEGIN

    SELECT INTO expr

        string_agg(def, ' AND ')

    FROM pg_constraint JOIN LATERAL pg_get_constraintdef(oid) AS def ON TRUE

    WHERE

        conrelid = reloid

        AND contype = 'c'

        AND def LIKE '%' || colname || '%'

    ;



    IF expr IS NULL THEN

        RETURN NULL;

    END IF;



    RAISE DEBUG 'Constraint expression for % on %: %', colname, reloid::regclass, expr;

    -- collect all constraints for the specified column

    FOR m IN SELECT regexp_matches(expr, '[ (]' || colname || $expr$\s*([<>=]{1,2})\s*'([0-9 :.+\-]+)'$expr$, 'g') LOOP

        ts := m[2]::timestamptz;

        IF m[1] IN ('>', '>=')

        THEN

            IF ts_lower IS NULL OR ts > ts_lower OR (ts = ts_lower AND m[1] = '>') THEN

                ts_lower := ts;

                lower_inclusive := CASE WHEN m[1] = '>' THEN '(' ELSE '[' END;

            END IF;

        ELSIF m[1] IN ('<', '<=')

        THEN

            IF ts_upper IS NULL OR ts < ts_upper OR (ts = ts_upper AND m[1] = '<') THEN

                ts_upper := ts;

                upper_inclusive := CASE WHEN m[1] = '<' THEN ')' ELSE ']' END;

            END IF;

        END IF;

    END LOOP;

    RAISE DEBUG 'Constraint % for %: % %', colname, reloid::regclass, ts_lower, ts_upper;

    RETURN tstzrange(ts_lower, ts_upper, lower_inclusive || upper_inclusive);

END;

$_$;


--
-- Name: get_version(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.get_version() RETURNS text
    LANGUAGE sql
    AS $$

  SELECT version FROM pgstac.migrations ORDER BY datetime DESC, version DESC LIMIT 1;

$$;


--
-- Name: include_field(text, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.include_field(f text, fields jsonb DEFAULT '{}'::jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$

DECLARE

    includes jsonb := fields->'include';

    excludes jsonb := fields->'exclude';

BEGIN

    IF f IS NULL THEN

        RETURN NULL;

    END IF;





    IF

        jsonb_typeof(excludes) = 'array'

        AND jsonb_array_length(excludes)>0

        AND excludes ? f

    THEN

        RETURN FALSE;

    END IF;



    IF

        (

            jsonb_typeof(includes) = 'array'

            AND jsonb_array_length(includes) > 0

            AND includes ? f

        ) OR

        (

            includes IS NULL

            OR jsonb_typeof(includes) = 'null'

            OR jsonb_array_length(includes) = 0

        )

    THEN

        RETURN TRUE;

    END IF;



    RETURN FALSE;

END;

$$;


--
-- Name: queryables; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.queryables (
    id bigint NOT NULL,
    name text NOT NULL,
    collection_ids text[],
    definition jsonb,
    property_path text,
    property_wrapper text,
    property_index_type text
);


--
-- Name: indexdef(pgstac.queryables); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.indexdef(q pgstac.queryables) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $_$

    DECLARE

        out text;

    BEGIN

        IF q.name = 'id' THEN

            out := 'CREATE UNIQUE INDEX ON %I USING btree (id)';

        ELSIF q.name = 'datetime' THEN

            out := 'CREATE INDEX ON %I USING btree (datetime DESC, end_datetime)';

        ELSIF q.name = 'geometry' THEN

            out := 'CREATE INDEX ON %I USING gist (geometry)';

        ELSE

            out := format($q$CREATE INDEX ON %%I USING %s (%s(((content -> 'properties'::text) -> %L::text)))$q$,

                lower(COALESCE(q.property_index_type, 'BTREE')),

                lower(COALESCE(q.property_wrapper, 'to_text')),

                q.name

            );

        END IF;

        RETURN btrim(out, ' \n\t');

    END;

$_$;


--
-- Name: item_by_id(text, text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.item_by_id(_id text, _collection text DEFAULT NULL::text) RETURNS pgstac.items
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pgstac', 'public'
    AS $$

DECLARE

    i items%ROWTYPE;

BEGIN

    SELECT * INTO i FROM items WHERE id=_id AND (_collection IS NULL OR collection=_collection) LIMIT 1;

    RETURN i;

END;

$$;


--
-- Name: items_staging_triggerfunc(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.items_staging_triggerfunc() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

DECLARE

    part text;

    ts timestamptz := clock_timestamp();

    nrows int;

BEGIN

    RAISE NOTICE 'Creating Partitions. %', clock_timestamp() - ts;



    FOR part IN WITH t AS (

        SELECT

            n.content->>'collection' as collection,

            stac_daterange(n.content->'properties') as dtr,

            partition_trunc

        FROM newdata n JOIN collections ON (n.content->>'collection'=collections.id)

    ), p AS (

        SELECT

            collection,

            COALESCE(date_trunc(partition_trunc::text, lower(dtr)),'-infinity') as d,

            tstzrange(min(lower(dtr)),max(lower(dtr)),'[]') as dtrange,

            tstzrange(min(upper(dtr)),max(upper(dtr)),'[]') as edtrange

        FROM t

        GROUP BY 1,2

    -- Ordered: check_partition holds DDL and row locks until commit.

    ) SELECT check_partition(collection, dtrange, edtrange) FROM (

        SELECT * FROM p ORDER BY collection, d

    ) ordered LOOP

        RAISE NOTICE 'Partition %', part;

    END LOOP;



    RAISE NOTICE 'Creating temp table with data to be added. %', clock_timestamp() - ts;

    DROP TABLE IF EXISTS tmpdata;

    CREATE TEMP TABLE tmpdata ON COMMIT DROP AS

    SELECT

        (content_dehydrate(content)).*

    FROM newdata;

    GET DIAGNOSTICS nrows = ROW_COUNT;

    RAISE NOTICE 'Added % rows to tmpdata. %', nrows, clock_timestamp() - ts;



    RAISE NOTICE 'Doing the insert. %', clock_timestamp() - ts;

    IF TG_TABLE_NAME = 'items_staging' THEN

        INSERT INTO items

        SELECT * FROM tmpdata;

        GET DIAGNOSTICS nrows = ROW_COUNT;

        RAISE NOTICE 'Inserted % rows to items. %', nrows, clock_timestamp() - ts;

    ELSIF TG_TABLE_NAME = 'items_staging_ignore' THEN

        INSERT INTO items

        SELECT * FROM tmpdata

        ON CONFLICT DO NOTHING;

        GET DIAGNOSTICS nrows = ROW_COUNT;

        RAISE NOTICE 'Inserted % rows to items. %', nrows, clock_timestamp() - ts;

    ELSIF TG_TABLE_NAME = 'items_staging_upsert' THEN

        -- Locked in a fixed order first, so concurrent upserts over an

        -- overlapping id set cannot deadlock. A bare DELETE gives no ordering;

        -- ORDER BY ... FOR UPDATE does, because LockRows sits above the sort.

        WITH locked AS (

            SELECT o.collection, o.id

            FROM tmpdata s

                JOIN items o ON (o.id = s.id AND o.collection = s.collection)

            WHERE o IS DISTINCT FROM s

            ORDER BY o.collection, o.id

            FOR UPDATE OF o

        )

        DELETE FROM items i

        USING locked l

        WHERE i.collection = l.collection AND i.id = l.id

        ;

        GET DIAGNOSTICS nrows = ROW_COUNT;

        RAISE NOTICE 'Deleted % rows from items. %', nrows, clock_timestamp() - ts;

        INSERT INTO items AS t

        SELECT * FROM tmpdata

        ON CONFLICT DO NOTHING;

        GET DIAGNOSTICS nrows = ROW_COUNT;

        RAISE NOTICE 'Inserted % rows to items. %', nrows, clock_timestamp() - ts;

    END IF;



    RAISE NOTICE 'Deleting data from staging table. %', clock_timestamp() - ts;

    EXECUTE format('DELETE FROM %I', TG_TABLE_NAME);

    RAISE NOTICE 'Done. %', clock_timestamp() - ts;



    RETURN NULL;



END;

$$;


--
-- Name: jsonb_array_unique(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_array_unique(j jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT nullif_jsonbnullempty(jsonb_agg(DISTINCT a)) v FROM jsonb_array_elements(j) a;

$$;


--
-- Name: jsonb_concat_ignorenull(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_concat_ignorenull(a jsonb, b jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT coalesce(a,'[]'::jsonb) || coalesce(b,'[]'::jsonb);

$$;


--
-- Name: jsonb_exclude(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_exclude(j jsonb, f jsonb) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE
    AS $$

DECLARE

    excludes jsonb := f-> 'exclude';

    outj jsonb := j;

    path text[];

BEGIN

    IF

        excludes IS NULL

        OR jsonb_array_length(excludes) = 0

    THEN

        RETURN j;

    ELSE

        FOR path IN SELECT explode_dotpaths(excludes) LOOP

            outj := outj #- path;

        END LOOP;

    END IF;

    RETURN outj;

END;

$$;


--
-- Name: jsonb_fields(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_fields(j jsonb, f jsonb DEFAULT '{"fields": []}'::jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT jsonb_exclude(jsonb_include(j, f), f);

$$;


--
-- Name: jsonb_greatest(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_greatest(a jsonb, b jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT nullif_jsonbnullempty(greatest(a, b));

$$;


--
-- Name: jsonb_include(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_include(j jsonb, f jsonb) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE
    AS $$

DECLARE

    includes jsonb := f-> 'include';

    outj jsonb := '{}'::jsonb;

    path text[];

BEGIN

    IF

        includes IS NULL

        OR jsonb_array_length(includes) = 0

    THEN

        RETURN j;

    ELSE

        includes := includes || (

            CASE WHEN j ? 'collection' THEN

                '["id","collection"]'

            ELSE

                '["id"]'

            END)::jsonb;

        FOR path IN SELECT explode_dotpaths(includes) LOOP

            outj := jsonb_set_nested(outj, path, j #> path);

        END LOOP;

    END IF;

    RETURN outj;

END;

$$;


--
-- Name: jsonb_least(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_least(a jsonb, b jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT nullif_jsonbnullempty(least(nullif_jsonbnullempty(a), nullif_jsonbnullempty(b)));

$$;


--
-- Name: jsonb_set_nested(jsonb, text[], jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.jsonb_set_nested(j jsonb, path text[], val jsonb) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE
    AS $$

DECLARE

BEGIN

    IF cardinality(path) > 1 THEN

        FOR i IN 1..(cardinality(path)-1) LOOP

            IF j #> path[:i] IS NULL THEN

                j := jsonb_set_lax(j, path[:i], '{}', TRUE);

            END IF;

        END LOOP;

    END IF;

    RETURN jsonb_set_lax(j, path, val, true);



END;

$$;


--
-- Name: maintain_index(text, text, bigint, boolean, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.maintain_index(_partition text, _indexname text, _queryable_id bigint, dropindexes boolean DEFAULT false, rebuildindexes boolean DEFAULT false, idxconcurrently boolean DEFAULT false) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pgstac', 'public'
    AS $$

DECLARE

    _queryable_idx text;

BEGIN

    -- Runs elevated, so it may only touch partitions of items.

    IF NOT EXISTS (SELECT 1 FROM partition_catalog_meta(_partition)) THEN

        RETURN;

    END IF;

    IF _queryable_id IS NOT NULL AND _partition IS NOT NULL THEN

        SELECT format(indexdef(q), _partition) INTO _queryable_idx

        FROM queryables q WHERE q.id = _queryable_id;

    END IF;

    IF _indexname IS NOT NULL THEN

        IF dropindexes OR _queryable_idx IS NOT NULL THEN

            EXECUTE format('DROP INDEX IF EXISTS %I;', _indexname);

        ELSIF rebuildindexes THEN

            IF idxconcurrently THEN

                EXECUTE format('REINDEX INDEX CONCURRENTLY %I;', _indexname);

            ELSE

                EXECUTE format('REINDEX INDEX %I;', _indexname);

            END IF;

        END IF;

    END IF;

    IF _queryable_idx IS NOT NULL THEN

        IF idxconcurrently THEN

            EXECUTE replace(_queryable_idx, 'INDEX', 'INDEX CONCURRENTLY');

        ELSE EXECUTE _queryable_idx;

        END IF;

    END IF;

END;

$$;


--
-- Name: maintain_partition_queries(text, boolean, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.maintain_partition_queries(part text DEFAULT 'items'::text, dropindexes boolean DEFAULT false, rebuildindexes boolean DEFAULT false, idxconcurrently boolean DEFAULT false) RETURNS SETOF text
    LANGUAGE plpgsql
    AS $$

DECLARE

   rec record;

   q text;

BEGIN

    FOR rec IN (

        SELECT * FROM queryable_indexes(part,true)

    ) LOOP

        q := format(

            'SELECT maintain_index(

                %L,%L,%L,%L,%L,%L

            );',

            rec.partition,

            rec.indexname,

            rec.queryable_id,

            dropindexes,

            rebuildindexes,

            idxconcurrently

        );

        RAISE NOTICE 'Q: %', q;

        RETURN NEXT q;

    END LOOP;

    RETURN;

END;

$$;


--
-- Name: maintain_partitions(text, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.maintain_partitions(part text DEFAULT 'items'::text, dropindexes boolean DEFAULT false, rebuildindexes boolean DEFAULT false) RETURNS void
    LANGUAGE sql
    AS $$

    WITH t AS (

        SELECT run_or_queue(q) FROM maintain_partition_queries(part, dropindexes, rebuildindexes) q

    ) SELECT count(*) FROM t;

$$;


--
-- Name: merge_jsonb(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.merge_jsonb(_a jsonb, _b jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT

    CASE

        WHEN _a = '"𒍟※"'::jsonb THEN NULL

        WHEN _a IS NULL OR jsonb_typeof(_a) = 'null' THEN _b

        WHEN jsonb_typeof(_a) = 'object' AND jsonb_typeof(_b) = 'object' THEN

            (

                SELECT

                    jsonb_strip_nulls(

                        jsonb_object_agg(

                            key,

                            merge_jsonb(a.value, b.value)

                        )

                    )

                FROM

                    jsonb_each(coalesce(_a,'{}'::jsonb)) as a

                FULL JOIN

                    jsonb_each(coalesce(_b,'{}'::jsonb)) as b

                USING (key)

            )

        WHEN

            jsonb_typeof(_a) = 'array'

            AND jsonb_typeof(_b) = 'array'

            AND jsonb_array_length(_a) = jsonb_array_length(_b)

        THEN

            (

                SELECT jsonb_agg(m) FROM

                    ( SELECT

                        merge_jsonb(

                            jsonb_array_elements(_a),

                            jsonb_array_elements(_b)

                        ) as m

                    ) as l

            )

        ELSE _a

    END

    ;

$$;


--
-- Name: missing_queryables(double precision); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.missing_queryables(_tablesample double precision DEFAULT 5) RETURNS TABLE(collection_ids text[], name text, definition jsonb, property_wrapper text)
    LANGUAGE sql
    AS $$

    SELECT

        array_agg(collection),

        name,

        definition,

        property_wrapper

    FROM

        collections

        JOIN LATERAL

        missing_queryables(id, _tablesample) c

        ON TRUE

    GROUP BY

        2,3,4

    ORDER BY 2,1

    ;

$$;


--
-- Name: missing_queryables(text, double precision, double precision); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.missing_queryables(_collection text, _tablesample double precision DEFAULT 5, minrows double precision DEFAULT 10) RETURNS TABLE(collection text, name text, definition jsonb, property_wrapper text)
    LANGUAGE plpgsql
    AS $_$

DECLARE

    q text;

    _partition text;

    explain_json json;

    psize float;

    estrows float;

BEGIN

    SELECT format('_items_%s', key) INTO _partition FROM collections WHERE id=_collection;



    EXECUTE format('EXPLAIN (format json) SELECT 1 FROM %I;', _partition)

    INTO explain_json;

    psize := explain_json->0->'Plan'->'Plan Rows';

    estrows := _tablesample * .01 * psize;

    IF estrows < minrows THEN

        _tablesample := least(100,greatest(_tablesample, (estrows / psize) / 100));

        RAISE NOTICE '%', (psize / estrows) / 100;

    END IF;

    RAISE NOTICE 'Using tablesample % to find missing queryables from % % that has ~% rows estrows: %', _tablesample, _collection, _partition, psize, estrows;



    q := format(

        $q$

            WITH q AS (

                SELECT * FROM queryables

                WHERE

                    collection_ids IS NULL

                    OR %L = ANY(collection_ids)

            ), t AS (

                SELECT

                    content->'properties' AS properties

                FROM

                    %I

                TABLESAMPLE SYSTEM(%L)

            ), p AS (

                SELECT DISTINCT ON (key)

                    key,

                    value,

                    s.definition

                FROM t

                JOIN LATERAL jsonb_each(properties) ON TRUE

                LEFT JOIN q ON (q.name=key)

                LEFT JOIN stac_extension_queryables s ON (s.name=key)

                WHERE q.definition IS NULL

            )

            SELECT

                %L,

                key,

                COALESCE(definition, jsonb_build_object('type',jsonb_typeof(value))) as definition,

                CASE

                    WHEN definition->>'type' = 'integer' THEN 'to_int'

                    WHEN COALESCE(definition->>'type', jsonb_typeof(value)) = 'number' THEN 'to_float'

                    WHEN COALESCE(definition->>'type', jsonb_typeof(value)) = 'array' THEN 'to_text_array'

                    ELSE 'to_text'

                END

            FROM p;

        $q$,

        _collection,

        _partition,

        _tablesample,

        _collection

    );

    RETURN QUERY EXECUTE q;

END;

$_$;


--
-- Name: normalize_indexdef(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.normalize_indexdef(def text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
    AS $$

DECLARE

BEGIN

    def := btrim(def, ' \n\t');

	def := regexp_replace(def, '^CREATE (UNIQUE )?INDEX ([^ ]* )?ON (ONLY )?([^ ]* )?', '', 'i');

    RETURN def;

END;

$$;


--
-- Name: notice(text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.notice(VARIADIC text[]) RETURNS boolean
    LANGUAGE plpgsql
    AS $_$

DECLARE

debug boolean := current_setting('pgstac.debug', true);

BEGIN

    IF debug THEN

        RAISE NOTICE 'NOTICE FROM FUNC: %  >>>>> %', concat_ws(' | ', $1), clock_timestamp();

        RETURN TRUE;

    END IF;

    RETURN FALSE;

END;

$_$;


--
-- Name: nullif_jsonbnullempty(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.nullif_jsonbnullempty(j jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$

    SELECT nullif(nullif(nullif(j,'null'::jsonb),'{}'::jsonb),'[]'::jsonb);

$$;


--
-- Name: paging_collections(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.paging_collections(j jsonb) RETURNS text[]
    LANGUAGE plpgsql STABLE STRICT
    AS $_$

DECLARE

    filter jsonb := j->'filter';

    jpitem jsonb;

    op text;

    args jsonb;

    arg jsonb;

    collections text[];

BEGIN

    IF j ? 'collections' THEN

        collections := to_text_array(j->'collections');

    END IF;

    IF NOT (filter  @? '$.**.op ? (@ == "or" || @ == "not")') THEN

        FOR jpitem IN SELECT j FROM jsonb_path_query(filter,'strict $.** ? (@.args[*].property == "collection")'::jsonpath) j LOOP

            RAISE NOTICE 'JPITEM: %', jpitem;

            op := jpitem->>'op';

            args := jpitem->'args';

            IF op IN ('=', 'eq', 'in') THEN

                FOR arg IN SELECT a FROM jsonb_array_elements(args) a LOOP

                    IF jsonb_typeof(arg) IN ('string', 'array') THEN

                        RAISE NOTICE 'arg: %, collections: %', arg, collections;

                        IF collections IS NULL OR collections = '{}'::text[] THEN

                            collections := to_text_array(arg);

                        ELSE

                            collections := array_intersection(collections, to_text_array(arg));

                        END IF;

                    END IF;

                END LOOP;

            END IF;

        END LOOP;

    END IF;

    IF collections = '{}'::text[] THEN

        RETURN NULL;

    END IF;

    RETURN collections;

END;

$_$;


--
-- Name: paging_dtrange(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.paging_dtrange(j jsonb) RETURNS tstzrange
    LANGUAGE plpgsql STABLE STRICT
    SET "TimeZone" TO 'UTC'
    AS $_$

DECLARE

    op text;

    filter jsonb := j->'filter';

    dtrange tstzrange := tstzrange('-infinity'::timestamptz,'infinity'::timestamptz);

    sdate timestamptz := '-infinity'::timestamptz;

    edate timestamptz := 'infinity'::timestamptz;

    jpitem jsonb;

BEGIN



    IF j ? 'datetime' THEN

        dtrange := parse_dtrange(j->'datetime');

        sdate := lower(dtrange);

        edate := upper(dtrange);

    END IF;

    IF NOT (filter  @? '$.**.op ? (@ == "or" || @ == "not")') THEN

        FOR jpitem IN SELECT j FROM jsonb_path_query(filter,'strict $.** ? (@.args[*].property == "datetime")'::jsonpath) j LOOP

            op := lower(jpitem->>'op');

            dtrange := parse_dtrange(jpitem->'args'->1);

            IF op IN ('<=', 'lt', 'lte', '<', 'le', 't_before') THEN

                sdate := greatest(sdate,'-infinity');

                edate := least(edate, upper(dtrange));

            ELSIF op IN ('>=', '>', 'gt', 'gte', 'ge', 't_after') THEN

                edate := least(edate, 'infinity');

                sdate := greatest(sdate, lower(dtrange));

            ELSIF op IN ('=', 'eq') THEN

                edate := least(edate, upper(dtrange));

                sdate := greatest(sdate, lower(dtrange));

            END IF;

            RAISE NOTICE '2 OP: %, ARGS: %, DTRANGE: %, SDATE: %, EDATE: %', op, jpitem->'args'->1, dtrange, sdate, edate;

        END LOOP;

    END IF;

    IF sdate > edate THEN

        RETURN 'empty'::tstzrange;

    END IF;

    RETURN tstzrange(sdate,edate, '[]');

END;

$_$;


--
-- Name: parse_dtrange(jsonb, timestamp with time zone); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.parse_dtrange(_indate jsonb, relative_base timestamp with time zone DEFAULT date_trunc('hour'::text, CURRENT_TIMESTAMP)) RETURNS tstzrange
    LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE
    SET "TimeZone" TO 'UTC'
    AS $$

DECLARE

    timestrs text[];

    s timestamptz;

    e timestamptz;

BEGIN

    timestrs :=

    CASE

        WHEN _indate ? 'timestamp' THEN

            ARRAY[_indate->>'timestamp']

        WHEN _indate ? 'interval' THEN

            to_text_array(_indate->'interval')

        WHEN jsonb_typeof(_indate) = 'array' THEN

            to_text_array(_indate)

        ELSE

            regexp_split_to_array(

                _indate->>0,

                '/'

            )

    END;

    RAISE NOTICE 'TIMESTRS %', timestrs;

    IF cardinality(timestrs) = 1 THEN

        IF timestrs[1] ILIKE 'P%' THEN

            RETURN tstzrange(relative_base - upper(timestrs[1])::interval, relative_base, '[)');

        END IF;

        s := timestrs[1]::timestamptz;

        RETURN tstzrange(s, s, '[]');

    END IF;



    IF cardinality(timestrs) != 2 THEN

        RAISE EXCEPTION 'Timestamp cannot have more than 2 values';

    END IF;



    IF timestrs[1] = '..' OR timestrs[1] = '' THEN

        s := '-infinity'::timestamptz;

        e := timestrs[2]::timestamptz;

        RETURN tstzrange(s,e,'[)');

    END IF;



    IF timestrs[2] = '..' OR timestrs[2] = '' THEN

        s := timestrs[1]::timestamptz;

        e := 'infinity'::timestamptz;

        RETURN tstzrange(s,e,'[)');

    END IF;



    IF timestrs[1] ILIKE 'P%' AND timestrs[2] NOT ILIKE 'P%' THEN

        e := timestrs[2]::timestamptz;

        s := e - upper(timestrs[1])::interval;

        RETURN tstzrange(s,e,'[)');

    END IF;



    IF timestrs[2] ILIKE 'P%' AND timestrs[1] NOT ILIKE 'P%' THEN

        s := timestrs[1]::timestamptz;

        e := s + upper(timestrs[2])::interval;

        RETURN tstzrange(s,e,'[)');

    END IF;



    s := timestrs[1]::timestamptz;

    e := timestrs[2]::timestamptz;



    RETURN tstzrange(s,e,'[)');



    RETURN NULL;



END;

$$;


--
-- Name: parse_dtrange(text, timestamp with time zone); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.parse_dtrange(_indate text, relative_base timestamp with time zone DEFAULT CURRENT_TIMESTAMP) RETURNS tstzrange
    LANGUAGE sql STABLE STRICT PARALLEL SAFE
    AS $$

    SELECT parse_dtrange(to_jsonb(_indate), relative_base);

$$;


--
-- Name: parse_sort_dir(text, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.parse_sort_dir(_dir text, reverse boolean DEFAULT false) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    WITH t AS (

        SELECT COALESCE(upper(_dir), 'ASC') as d

    ) SELECT

        CASE

            WHEN NOT reverse THEN d

            WHEN d = 'ASC' THEN 'DESC'

            WHEN d = 'DESC' THEN 'ASC'

        END

    FROM t;

$$;


--
-- Name: partition_after_triggerfunc(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.partition_after_triggerfunc() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $$

DECLARE

    p text;

    t timestamptz := clock_timestamp();

BEGIN

    RAISE NOTICE 'Updating partition stats %', t;

    -- Ordered: each iteration holds a partition_stats row lock until commit.

    FOR p IN SELECT DISTINCT partition

        FROM newdata n JOIN partition_stats p

        ON (n.collection=p.collection AND n.datetime <@ p.partition_dtrange)

        ORDER BY 1

    LOOP

        PERFORM run_or_queue(format('SELECT update_partition_stats(%L, %L);', p, true));

    END LOOP;

    IF TG_OP IN ('DELETE','UPDATE') THEN

        DELETE FROM format_item_cache c USING newdata n WHERE c.collection = n.collection AND c.id = n.id;

    END IF;

    RAISE NOTICE 't: % %', t, clock_timestamp() - t;

    RETURN NULL;

END;

$$;


--
-- Name: partition_catalog_meta(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.partition_catalog_meta(_partition text) RETURNS TABLE(collection text, partition_dtrange tstzrange, constraint_dtrange tstzrange, constraint_edtrange tstzrange)
    LANGUAGE plpgsql STABLE
    AS $$

DECLARE

    _oid oid;

    _parent oid;

    _expr text;

    _inf tstzrange := tstzrange('-infinity', 'infinity', '[]');

    _dtrange tstzrange;

BEGIN

    _oid := partition_oid(_partition);

    -- Leaves only, matching partitions_view: an intermediate partition has no

    -- meaningful range of its own.

    IF _oid IS NULL OR EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = _oid) THEN

        RETURN;

    END IF;



    SELECT inhparent INTO _parent FROM pg_inherits WHERE inhrelid = _oid;



    -- Partitions of items only. The SECURITY DEFINER functions below use this

    -- to decide what they may alter, so any other relation must return nothing.

    IF _parent IS NULL

        OR (

            _parent <> 'pgstac.items'::regclass

            AND NOT EXISTS (

                SELECT 1 FROM pg_inherits

                WHERE inhrelid = _parent AND inhparent = 'pgstac.items'::regclass

            )

        )

    THEN

        RETURN;

    END IF;



    -- A partition of a sub-partitioned collection carries a datetime range

    -- bound; its collection is on the parent. A direct partition of items

    -- carries the collection itself.

    IF _parent = 'pgstac.items'::regclass THEN

        SELECT pg_get_expr(relpartbound, oid) INTO _expr FROM pg_class WHERE oid = _oid;

    ELSE

        SELECT pg_get_expr(relpartbound, oid) INTO _expr FROM pg_class WHERE oid = _parent;

    END IF;



    SELECT COALESCE(

        constraint_tstzrange(pg_get_expr(relpartbound, oid)),

        _inf

    ) INTO _dtrange FROM pg_class WHERE oid = _oid;



    RETURN QUERY SELECT

        replace(replace(_expr, 'FOR VALUES IN (''', ''), ''')', ''),

        _dtrange,

        COALESCE(get_tstz_constraint(_oid, 'datetime'), _dtrange, _inf),

        COALESCE(get_tstz_constraint(_oid, 'end_datetime'), _inf);

END;

$$;


--
-- Name: partition_name(text, timestamp with time zone); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.partition_name(collection text, dt timestamp with time zone, OUT partition_name text, OUT partition_range tstzrange) RETURNS record
    LANGUAGE plpgsql STABLE
    AS $$

DECLARE

    c RECORD;

    parent_name text;

BEGIN

    SELECT * INTO c FROM pgstac.collections WHERE id=collection;

    IF NOT FOUND THEN

        RAISE EXCEPTION 'Collection % does not exist', collection USING ERRCODE = 'foreign_key_violation', HINT = 'Make sure collection exists before adding items';

    END IF;

    parent_name := format('_items_%s', c.key);





    IF c.partition_trunc = 'year' THEN

        partition_name := format('%s_%s', parent_name, to_char(dt,'YYYY'));

    ELSIF c.partition_trunc = 'month' THEN

        partition_name := format('%s_%s', parent_name, to_char(dt,'YYYYMM'));

    ELSE

        partition_name := parent_name;

        partition_range := tstzrange('-infinity'::timestamptz, 'infinity'::timestamptz, '[]');

    END IF;

    IF partition_range IS NULL THEN

        partition_range := tstzrange(

            date_trunc(c.partition_trunc::text, dt),

            date_trunc(c.partition_trunc::text, dt) + concat('1 ', c.partition_trunc)::interval

        );

    END IF;

    RETURN;



END;

$$;


--
-- Name: partition_oid(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.partition_oid(_partition text) RETURNS oid
    LANGUAGE sql STABLE STRICT
    AS $$

    SELECT CASE

        WHEN cardinality(parts) > 1 AND parts[cardinality(parts) - 1] <> 'pgstac' THEN NULL

        ELSE to_regclass(format('pgstac.%I', parts[cardinality(parts)]))

    END

    FROM parse_ident(_partition) AS parts;

$$;


--
-- Name: partition_queries(text, text, text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.partition_queries(_where text DEFAULT 'TRUE'::text, _orderby text DEFAULT 'datetime DESC, id DESC'::text, partitions text[] DEFAULT NULL::text[]) RETURNS SETOF text
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    query text;

    sdate timestamptz;

    edate timestamptz;

BEGIN

IF _where IS NULL OR trim(_where) = '' THEN

    _where = ' TRUE ';

END IF;

RAISE NOTICE 'Getting chunks for % %', _where, _orderby;

IF _orderby ILIKE 'datetime d%' THEN

    FOR sdate, edate IN SELECT * FROM chunker(_where) ORDER BY 1 DESC LOOP

        RETURN NEXT format($q$

            SELECT * FROM items

            WHERE

            datetime >= %L AND datetime < %L

            AND (%s)

            ORDER BY %s

            $q$,

            sdate,

            edate,

            _where,

            _orderby

        );

    END LOOP;

ELSIF _orderby ILIKE 'datetime a%' THEN

    FOR sdate, edate IN SELECT * FROM chunker(_where) ORDER BY 1 ASC LOOP

        RETURN NEXT format($q$

            SELECT * FROM items

            WHERE

            datetime >= %L AND datetime < %L

            AND (%s)

            ORDER BY %s

            $q$,

            sdate,

            edate,

            _where,

            _orderby

        );

    END LOOP;

ELSE

    query := format($q$

        SELECT * FROM items

        WHERE %s

        ORDER BY %s

    $q$, _where, _orderby

    );



    RETURN NEXT query;

    RETURN;

END IF;



RETURN;

END;

$_$;


--
-- Name: partition_query_view(text, text, integer); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.partition_query_view(_where text DEFAULT 'TRUE'::text, _orderby text DEFAULT 'datetime DESC, id DESC'::text, _limit integer DEFAULT 10) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $_$

    WITH p AS (

        SELECT * FROM partition_queries(_where, _orderby) p

    )

    SELECT

        CASE WHEN EXISTS (SELECT 1 FROM p) THEN

            (SELECT format($q$

                SELECT * FROM (

                    %s

                ) total LIMIT %s

                $q$,

                string_agg(

                    format($q$ SELECT * FROM ( %s ) AS sub $q$, p),

                    '

                    UNION ALL

                    '

                ),

                _limit

            ))

        ELSE NULL

        END FROM p;

$_$;


--
-- Name: q_to_tsquery(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.q_to_tsquery(jinput jsonb) RETURNS tsquery
    LANGUAGE plpgsql
    AS $_$

DECLARE

    input text;

    processed_text text;

    temp_text text;

    quote_array text[];

    placeholder text := '@QUOTE@';

BEGIN

    IF jsonb_typeof(jinput) = 'string' THEN

        input := jinput->>0;

    ELSIF jsonb_typeof(jinput) = 'array' THEN

        input := array_to_string(

            array(select jsonb_array_elements_text(jinput)),

            ' OR '

        );

    ELSE

        RAISE EXCEPTION 'Input must be a string or an array of strings.';

    END IF;

    -- Extract all quoted phrases and store in array

    quote_array := regexp_matches(input, '"[^"]*"', 'g');



    -- Replace each quoted part with a unique placeholder if there are any quoted phrases

    IF array_length(quote_array, 1) IS NOT NULL THEN

        processed_text := input;

        FOR i IN array_lower(quote_array, 1) .. array_upper(quote_array, 1) LOOP

            processed_text := replace(processed_text, quote_array[i], placeholder || i || placeholder);

        END LOOP;

    ELSE

        processed_text := input;

    END IF;



    -- Replace non-quoted text using regular expressions



    -- , -> |

    processed_text := regexp_replace(processed_text, ',(?=(?:[^"]*"[^"]*")*[^"]*$)', ' | ', 'g');



    -- and -> &

    processed_text := regexp_replace(processed_text, '\s+AND\s+', ' & ', 'gi');



    -- or -> |

    processed_text := regexp_replace(processed_text, '\s+OR\s+', ' | ', 'gi');



    -- + ->

    processed_text := regexp_replace(processed_text, '^\s*\+([a-zA-Z0-9_]+)', '\1', 'g'); -- +term at start

    processed_text := regexp_replace(processed_text, '\s*\+([a-zA-Z0-9_]+)', ' & \1', 'g'); -- +term elsewhere



    -- - ->  !

    processed_text := regexp_replace(processed_text, '^\s*\-([a-zA-Z0-9_]+)', '! \1', 'g'); -- -term at start

    processed_text := regexp_replace(processed_text, '\s*\-([a-zA-Z0-9_]+)', ' & ! \1', 'g'); -- -term elsewhere



    -- terms separated with spaces are assumed to represent adjacent terms. loop through these

    -- occurrences and replace them with the adjacency operator (<->)

    LOOP

        temp_text := regexp_replace(processed_text, '([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_]+)(?!\s*[&|<>])', '\1 <-> \2', 'g');

        IF temp_text = processed_text THEN

            EXIT; -- No more replacements were made

        END IF;

        processed_text := temp_text;

    END LOOP;





    -- Replace placeholders back with quoted phrases if there were any

    IF array_length(quote_array, 1) IS NOT NULL THEN

        FOR i IN array_lower(quote_array, 1) .. array_upper(quote_array, 1) LOOP

            processed_text := replace(processed_text, placeholder || i || placeholder, '''' || substring(quote_array[i] from 2 for length(quote_array[i]) - 2) || '''');

        END LOOP;

    END IF;



    -- Print processed_text to the console for debugging purposes

    RAISE NOTICE 'processed_text: %', processed_text;



    RETURN to_tsquery('english', processed_text);

END;

$_$;


--
-- Name: query_to_cql2(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.query_to_cql2(q jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE STRICT
    AS $$

-- Translates anything passed in through the deprecated "query" into equivalent CQL2

WITH t AS (

    SELECT key as property, value as ops

        FROM jsonb_each(q)

), t2 AS (

    SELECT property, (jsonb_each(ops)).*

        FROM t WHERE jsonb_typeof(ops) = 'object'

    UNION ALL

    SELECT property, 'eq', ops

        FROM t WHERE jsonb_typeof(ops) != 'object'

)

SELECT

    jsonb_strip_nulls(jsonb_build_object(

        'op', 'and',

        'args', jsonb_agg(

            jsonb_build_object(

                'op', key,

                'args', jsonb_build_array(

                    jsonb_build_object('property',property),

                    value

                )

            )

        )

    )

) as qcql FROM t2

;

$$;


--
-- Name: queryable(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.queryable(dotpath text, OUT path text, OUT expression text, OUT wrapper text, OUT nulled_wrapper text) RETURNS record
    LANGUAGE plpgsql STABLE STRICT
    AS $_$

DECLARE

    q RECORD;

    path_elements text[];

BEGIN

    dotpath := replace(dotpath, 'properties.', '');

    IF dotpath = 'start_datetime' THEN

        dotpath := 'datetime';

    END IF;

    IF dotpath IN ('id', 'geometry', 'datetime', 'end_datetime', 'collection') THEN

        path := dotpath;

        expression := dotpath;

        wrapper := NULL;

        RETURN;

    END IF;



    SELECT * INTO q FROM queryables

        WHERE

            name=dotpath

            OR name = 'properties.' || dotpath

            OR name = replace(dotpath, 'properties.', '')

    ;

    IF q.property_wrapper IS NULL THEN

        IF q.definition->>'type' = 'number' THEN

            wrapper := 'to_float';

            nulled_wrapper := wrapper;

        ELSIF q.definition->>'format' = 'date-time' THEN

            wrapper := 'to_tstz';

            nulled_wrapper := wrapper;

        ELSE

            nulled_wrapper := NULL;

            wrapper := 'to_text';

        END IF;

    ELSE

        wrapper := q.property_wrapper;

        nulled_wrapper := wrapper;

    END IF;

    IF q.property_path IS NOT NULL THEN

        path := q.property_path;

    ELSE

        path_elements := string_to_array(dotpath, '.');

        IF path_elements[1] IN ('links', 'assets', 'stac_version', 'stac_extensions') THEN

            path := format('content->%s', array_to_path(path_elements));

        ELSIF path_elements[1] = 'properties' THEN

            path := format('content->%s', array_to_path(path_elements));

        ELSE

            path := format($F$content->'properties'->%s$F$, array_to_path(path_elements));

        END IF;

    END IF;

    expression := format('%I(%s)', wrapper, path);

    RETURN;

END;

$_$;


--
-- Name: queryable_indexes(text, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.queryable_indexes(treeroot text DEFAULT 'items'::text, changes boolean DEFAULT false, OUT collection text, OUT partition text, OUT field text, OUT indexname text, OUT existing_idx text, OUT queryable_idx text, OUT queryable_id bigint) RETURNS SETOF record
    LANGUAGE sql
    AS $$

WITH p AS (

        SELECT

            relid::text as partition,

            replace(replace(

                CASE

                    WHEN parentrelid::regclass::text='items' THEN pg_get_expr(c.relpartbound, c.oid)

                    ELSE pg_get_expr(parent.relpartbound, parent.oid)

                END,

                'FOR VALUES IN (''',''), ''')',

                ''

            ) AS collection

        FROM pg_partition_tree(treeroot)

        JOIN pg_class c ON (relid::regclass = c.oid)

        JOIN pg_class parent ON (parentrelid::regclass = parent.oid AND isleaf)

    ), i AS (

        SELECT

            partition,

            indexname,

            regexp_replace(btrim(replace(replace(indexdef, indexname, ''),'pgstac.',''),' \t\n'), '[ ]+', ' ', 'g') as iidx,

            COALESCE(

                (regexp_match(indexdef, '\(([a-zA-Z]+)\)'))[1],

                (regexp_match(indexdef,  '\(content -> ''properties''::text\) -> ''([a-zA-Z0-9\:\_-]+)''::text'))[1],

                CASE WHEN indexdef ~* '\(datetime desc, end_datetime\)' THEN 'datetime' ELSE NULL END

            ) AS field

        FROM

            pg_indexes

            JOIN p ON (tablename=partition)

    ), q AS (

        SELECT

            name AS field,

            collection,

            partition,

            format(indexdef(queryables), partition) as qidx,

            queryables.id as qid

        FROM queryables, unnest_collection(queryables.collection_ids) collection

            JOIN p USING (collection)

        WHERE property_index_type IS NOT NULL OR name IN ('datetime','geometry','id')

    )

    SELECT

        collection,

        partition,

        field,

        indexname,

        iidx as existing_idx,

        qidx as queryable_idx,

        qid as queryable_id

    FROM i FULL JOIN q USING (field, partition)

    WHERE CASE WHEN changes THEN lower(iidx) IS DISTINCT FROM lower(qidx) ELSE TRUE END;

;

$$;


--
-- Name: queryable_signature(text, text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.queryable_signature(n text, c text[]) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    SELECT concat(n, c);

$$;


--
-- Name: queryables_constraint_triggerfunc(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.queryables_constraint_triggerfunc() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

DECLARE

    allcollections text[];

BEGIN

    RAISE NOTICE 'Making sure that name/collection is unique for queryables %', NEW;

    IF NEW.collection_ids IS NOT NULL THEN

        IF EXISTS (

            SELECT 1

                FROM unnest(NEW.collection_ids) c

                LEFT JOIN

                collections

                ON (collections.id = c)

                WHERE collections.id IS NULL

        ) THEN

            RAISE foreign_key_violation USING MESSAGE = format(

                'One or more collections in %s do not exist.', NEW.collection_ids

            );

            RETURN NULL;

        END IF;

    END IF;

    IF TG_OP = 'INSERT' THEN

        IF EXISTS (

            SELECT 1 FROM queryables q

            WHERE

                q.name = NEW.name

                AND (

                    q.collection_ids && NEW.collection_ids

                    OR

                    q.collection_ids IS NULL

                    OR

                    NEW.collection_ids IS NULL

                )

        ) THEN

            RAISE unique_violation USING MESSAGE = format(

                'There is already a queryable for %s for a collection in %s: %s',

                NEW.name,

                NEW.collection_ids,

				(SELECT json_agg(row_to_json(q)) FROM queryables q WHERE

                q.name = NEW.name

                AND (

                    q.collection_ids && NEW.collection_ids

                    OR

                    q.collection_ids IS NULL

                    OR

                    NEW.collection_ids IS NULL

                ))

            );

            RETURN NULL;

        END IF;

    END IF;

    IF TG_OP = 'UPDATE' THEN

        IF EXISTS (

            SELECT 1 FROM queryables q

            WHERE

                q.id != NEW.id

                AND

                q.name = NEW.name

                AND (

                    q.collection_ids && NEW.collection_ids

                    OR

                    q.collection_ids IS NULL

                    OR

                    NEW.collection_ids IS NULL

                )

        ) THEN

            RAISE unique_violation

            USING MESSAGE = format(

                'There is already a queryable for %s for a collection in %s',

                NEW.name,

                NEW.collection_ids

            );

            RETURN NULL;

        END IF;

    END IF;



    RETURN NEW;

END;

$$;


--
-- Name: queryables_trigger_func(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.queryables_trigger_func() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

DECLARE

BEGIN

    PERFORM maintain_partitions();

    RETURN NULL;

END;

$$;


--
-- Name: queue_timeout(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.queue_timeout() RETURNS interval
    LANGUAGE sql
    AS $$

    SELECT t2s(coalesce(

            get_setting('queue_timeout'),

            '1h'

        ))::interval;

$$;


--
-- Name: readonly(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.readonly(conf jsonb DEFAULT NULL::jsonb) RETURNS boolean
    LANGUAGE sql
    AS $$

    SELECT pgstac.get_setting_bool('readonly', conf);

$$;


--
-- Name: repartition(text, text, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.repartition(_collection text, _partition_trunc text, triggered boolean DEFAULT false) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    c RECORD;

BEGIN

    SELECT * INTO c FROM pgstac.collections WHERE id=_collection;

    IF NOT FOUND THEN

        RAISE EXCEPTION 'Collection % does not exist', _collection USING ERRCODE = 'foreign_key_violation', HINT = 'Make sure collection exists before adding items';

    END IF;

    IF triggered THEN

        RAISE NOTICE 'Converting % to % partitioning via Trigger', _collection, _partition_trunc;

    ELSE

        RAISE NOTICE 'Converting % from using % to % partitioning', _collection, c.partition_trunc, _partition_trunc;

        IF c.partition_trunc IS NOT DISTINCT FROM _partition_trunc THEN

            RAISE NOTICE 'Collection % already set to use partition by %', _collection, _partition_trunc;

            RETURN _collection;

        END IF;

    END IF;



    IF EXISTS (SELECT 1 FROM partitions_view WHERE collection=_collection LIMIT 1) THEN

        EXECUTE format(

            $q$

                CREATE TEMP TABLE changepartitionstaging ON COMMIT DROP AS SELECT * FROM %I;

                DROP TABLE IF EXISTS %I CASCADE;

                DELETE FROM partition_stats WHERE collection = %L;

                WITH p AS (

                    SELECT

                        collection,

                        CASE

                            WHEN %L IS NULL THEN '-infinity'::timestamptz

                            ELSE date_trunc(%L, datetime)

                        END as d,

                        tstzrange(min(datetime),max(datetime),'[]') as dtrange,

                        tstzrange(min(end_datetime),max(end_datetime),'[]') as edtrange

                    FROM changepartitionstaging

                    GROUP BY 1,2

                ) SELECT check_partition(collection, dtrange, edtrange) FROM p;

                INSERT INTO items SELECT * FROM changepartitionstaging;

                DROP TABLE changepartitionstaging;

            $q$,

            concat('_items_', c.key),

            concat('_items_', c.key),

            _collection,

            c.partition_trunc,

            c.partition_trunc

        );

    END IF;

    RETURN _collection;

END;

$_$;


--
-- Name: run_or_queue(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.run_or_queue(query text) RETURNS boolean
    LANGUAGE plpgsql
    AS $$

DECLARE

    use_queue boolean := COALESCE(get_setting('use_queue'), 'FALSE')::boolean;

BEGIN

    IF get_setting_bool('debug') THEN

        RAISE NOTICE '%', query;

    END IF;

    IF use_queue THEN

        INSERT INTO query_queue (query) VALUES (query) ON CONFLICT DO NOTHING;

        RETURN FALSE;

    END IF;

    EXECUTE query;

    RETURN TRUE;

END;

$$;


--
-- Name: run_queued_queries(); Type: PROCEDURE; Schema: pgstac; Owner: -
--

CREATE PROCEDURE pgstac.run_queued_queries()
    LANGUAGE plpgsql
    AS $$

DECLARE

    qitem query_queue%ROWTYPE;

    timeout_ts timestamptz;

    error text;

    cnt int := 0;

BEGIN

    timeout_ts := statement_timestamp() + queue_timeout();

    WHILE clock_timestamp() < timeout_ts LOOP

        DELETE FROM query_queue WHERE query = (SELECT query FROM query_queue ORDER BY added DESC LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING * INTO qitem;

        IF NOT FOUND THEN

            EXIT;

        END IF;

        cnt := cnt + 1;

        BEGIN

            RAISE NOTICE 'RUNNING QUERY: %', qitem.query;

            EXECUTE qitem.query;

            EXCEPTION WHEN others THEN

                error := format('%s | %s', SQLERRM, SQLSTATE);

        END;

        INSERT INTO query_queue_history (query, added, finished, error)

            VALUES (qitem.query, qitem.added, clock_timestamp(), error);

        COMMIT;

    END LOOP;

END;

$$;


--
-- Name: run_queued_queries_intransaction(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.run_queued_queries_intransaction() RETURNS integer
    LANGUAGE plpgsql
    AS $$

DECLARE

    qitem query_queue%ROWTYPE;

    timeout_ts timestamptz;

    error text;

    cnt int := 0;

BEGIN

    timeout_ts := statement_timestamp() + queue_timeout();

    WHILE clock_timestamp() < timeout_ts LOOP

        DELETE FROM query_queue WHERE query = (SELECT query FROM query_queue ORDER BY added DESC LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING * INTO qitem;

        IF NOT FOUND THEN

            RETURN cnt;

        END IF;

        cnt := cnt + 1;

        BEGIN

            qitem.query := regexp_replace(qitem.query, 'CONCURRENTLY', '');

            RAISE NOTICE 'RUNNING QUERY: %', qitem.query;



            EXECUTE qitem.query;

            EXCEPTION WHEN others THEN

                error := format('%s | %s', SQLERRM, SQLSTATE);

                RAISE WARNING '%', error;

        END;

        INSERT INTO query_queue_history (query, added, finished, error)

            VALUES (qitem.query, qitem.added, clock_timestamp(), error);

    END LOOP;

    RETURN cnt;

END;

$$;


--
-- Name: schema_qualify_refs(text, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.schema_qualify_refs(url text, j jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$

    SELECT regexp_replace(j::text, '"\$ref": "#', concat('"$ref": "', url, '#'), 'g')::jsonb;

$_$;


--
-- Name: search(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.search(_search jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$

DECLARE

    searches searches%ROWTYPE;

    _where text;

    orderby text;

    search_where search_wheres%ROWTYPE;

    total_count bigint;

    token record;

    token_prev boolean;

    token_item items%ROWTYPE;

    token_where text;

    full_where text;

    init_ts timestamptz := clock_timestamp();

    timer timestamptz := clock_timestamp();

    hydrate bool := NOT (_search->'conf'->>'nohydrate' IS NOT NULL AND (_search->'conf'->>'nohydrate')::boolean = true);

    prev text;

    next text;

    context jsonb;

    collection jsonb;

    out_records jsonb;

    out_len int;

    _limit int := coalesce((_search->>'limit')::int, 10);

    _querylimit int;

    _fields jsonb := coalesce(_search->'fields', '{}'::jsonb);

    has_prev boolean := FALSE;

    has_next boolean := FALSE;

    links jsonb := '[]'::jsonb;

    base_url text:= concat(rtrim(base_url(_search->'conf'),'/'));

BEGIN

    searches := search_query(_search);

    _where := searches._where;

    orderby := searches.orderby;

    search_where := where_stats(_where);

    total_count := coalesce(search_where.total_count, search_where.estimated_count);

    RAISE NOTICE 'SEARCH:TOKEN: %', _search->>'token';

    token := get_token_record(_search->>'token');

    RAISE NOTICE '***TOKEN: %', token;

    _querylimit := _limit + 1;

    IF token IS NOT NULL THEN

        token_prev := token.prev;

        token_item := token.item;

        token_where := get_token_filter(_search->'sortby', token_item, token_prev, FALSE);

        RAISE DEBUG 'TOKEN_WHERE: % (%ms from search start)', token_where, age_ms(timer);

        IF token_prev THEN -- if we are using a prev token, we know has_next is true

            RAISE DEBUG 'There is a previous token, so automatically setting has_next to true';

            has_next := TRUE;

            orderby := sort_sqlorderby(_search, TRUE);

        ELSE

            RAISE DEBUG 'There is a next token, so automatically setting has_prev to true';

            has_prev := TRUE;



        END IF;

    ELSE -- if there was no token, we know there is no prev

        RAISE DEBUG 'There is no token, so we know there is no prev. setting has_prev to false';

        has_prev := FALSE;

    END IF;



    full_where := concat_ws(' AND ', _where, token_where);

    RAISE NOTICE 'FULL WHERE CLAUSE: %', full_where;

    RAISE NOTICE 'Time to get counts and build query %', age_ms(timer);

    timer := clock_timestamp();



    IF hydrate THEN

        RAISE NOTICE 'Getting hydrated data.';

    ELSE

        RAISE NOTICE 'Getting non-hydrated data.';

    END IF;

    RAISE NOTICE 'CACHE SET TO %', get_setting_bool('format_cache');

    RAISE NOTICE 'Time to set hydration/formatting %', age_ms(timer);

    timer := clock_timestamp();

    SELECT jsonb_agg(format_item(i, _fields, hydrate)) INTO out_records

    FROM search_rows(

        full_where,

        orderby,

        search_where.partitions,

        _querylimit

    ) as i;



    RAISE NOTICE 'Time to fetch rows %', age_ms(timer);

    timer := clock_timestamp();





    IF token_prev THEN

        out_records := flip_jsonb_array(out_records);

    END IF;



    RAISE NOTICE 'Query returned % records.', jsonb_array_length(out_records);

    RAISE DEBUG 'TOKEN:   % %', token_item.id, token_item.collection;

    RAISE DEBUG 'RECORD_1: % %', out_records->0->>'id', out_records->0->>'collection';

    RAISE DEBUG 'RECORD-1: % %', out_records->-1->>'id', out_records->-1->>'collection';



    -- REMOVE records that were from our token

    IF out_records->0->>'id' = token_item.id AND out_records->0->>'collection' = token_item.collection THEN

        out_records := out_records - 0;

    ELSIF out_records->-1->>'id' = token_item.id AND out_records->-1->>'collection' = token_item.collection THEN

        out_records := out_records - -1;

    END IF;



    out_len := jsonb_array_length(out_records);



    IF out_len = _limit + 1 THEN

        IF token_prev THEN

            has_prev := TRUE;

            out_records := out_records - 0;

        ELSE

            has_next := TRUE;

            out_records := out_records - -1;

        END IF;

    END IF;





    links := links || jsonb_build_object(

        'rel', 'root',

        'type', 'application/json',

        'href', base_url

    ) || jsonb_build_object(

        'rel', 'self',

        'type', 'application/json',

        'href', concat(base_url, '/search')

    );



    IF has_next THEN

        next := concat(out_records->-1->>'collection', ':', out_records->-1->>'id');

        RAISE NOTICE 'HAS NEXT | %', next;

        links := links || jsonb_build_object(

            'rel', 'next',

            'type', 'application/geo+json',

            'method', 'GET',

            'href', concat(base_url, '/search?token=next:', next)

        );

    END IF;



    IF has_prev THEN

        prev := concat(out_records->0->>'collection', ':', out_records->0->>'id');

        RAISE NOTICE 'HAS PREV | %', prev;

        links := links || jsonb_build_object(

            'rel', 'prev',

            'type', 'application/geo+json',

            'method', 'GET',

            'href', concat(base_url, '/search?token=prev:', prev)

        );

    END IF;



    RAISE NOTICE 'Time to get prev/next %', age_ms(timer);

    timer := clock_timestamp();





    collection := jsonb_build_object(

        'type', 'FeatureCollection',

        'features', coalesce(out_records, '[]'::jsonb),

        'links', links

    );







    IF context(_search->'conf') != 'off' THEN

        collection := collection || jsonb_strip_nulls(jsonb_build_object(

            'numberMatched', total_count,

            'numberReturned', coalesce(jsonb_array_length(out_records), 0)

        ));

    ELSE

        collection := collection || jsonb_strip_nulls(jsonb_build_object(

            'numberReturned', coalesce(jsonb_array_length(out_records), 0)

        ));

    END IF;



    IF get_setting_bool('timing', _search->'conf') THEN

        collection = collection || jsonb_build_object('timing', age_ms(init_ts));

    END IF;



    RAISE NOTICE 'Time to build final json %', age_ms(timer);

    timer := clock_timestamp();



    RAISE NOTICE 'Total Time: %', age_ms(current_timestamp);

    RAISE NOTICE 'RETURNING % records. NEXT: %. PREV: %', collection->>'numberReturned', collection->>'next', collection->>'prev';

    RETURN collection;

END;

$$;


--
-- Name: search_cursor(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.search_cursor(_search jsonb DEFAULT '{}'::jsonb) RETURNS refcursor
    LANGUAGE plpgsql
    AS $_$

DECLARE

    curs refcursor;

    searches searches%ROWTYPE;

    _where text;

    _orderby text;

    q text;



BEGIN

    searches := search_query(_search);

    _where := searches._where;

    _orderby := searches.orderby;



    OPEN curs FOR

        WITH p AS (

            SELECT * FROM partition_queries(_where, _orderby) p

        )

        SELECT

            CASE WHEN EXISTS (SELECT 1 FROM p) THEN

                (SELECT format($q$

                    SELECT * FROM (

                        %s

                    ) total

                    $q$,

                    string_agg(

                        format($q$ SELECT * FROM ( %s ) AS sub $q$, p),

                        '

                        UNION ALL

                        '

                    )

                ))

            ELSE NULL

            END FROM p;

    RETURN curs;

END;

$_$;


--
-- Name: search_hash(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.search_hash(jsonb, jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $_$

    SELECT md5(concat(($1 - '{token,limit,context,includes,excludes}'::text[])::text,$2::text));

$_$;


--
-- Name: searches; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.searches (
    hash text GENERATED ALWAYS AS (pgstac.search_hash(search, metadata)) STORED NOT NULL,
    search jsonb NOT NULL,
    _where text,
    orderby text,
    lastused timestamp with time zone DEFAULT now(),
    usecount bigint DEFAULT 0,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: search_fromhash(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.search_fromhash(_hash text) RETURNS pgstac.searches
    LANGUAGE sql STRICT
    AS $$

    SELECT * FROM search_query((SELECT search FROM searches WHERE hash=_hash LIMIT 1));

$$;


--
-- Name: search_query(jsonb, boolean, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.search_query(_search jsonb DEFAULT '{}'::jsonb, updatestats boolean DEFAULT false, _metadata jsonb DEFAULT '{}'::jsonb) RETURNS pgstac.searches
    LANGUAGE plpgsql
    AS $$

DECLARE

    search searches%ROWTYPE;

    cached_search searches%ROWTYPE;

    pexplain jsonb;

    t timestamptz;

    i interval;

    doupdate boolean := FALSE;

    insertfound boolean := FALSE;

    ro boolean := pgstac.readonly();

    found_search text;

BEGIN

    RAISE NOTICE 'SEARCH: %', _search;

    -- Calculate hash, where clause, and order by statement

    search.search := _search;

    search.metadata := _metadata;

    search.hash := search_hash(_search, _metadata);

    search._where := stac_search_to_where(_search);

    search.orderby := sort_sqlorderby(_search);

    search.lastused := now();

    search.usecount := 1;



    -- If we are in read only mode, directly return search

    IF ro THEN

        RETURN search;

    END IF;



    RAISE NOTICE 'Updating Statistics for search: %s', search;

    -- Update statistics for times used and and when last used

    -- If the entry is locked, rather than waiting, skip updating the stats

    INSERT INTO searches (search, lastused, usecount, metadata)

        VALUES (search.search, now(), 1, search.metadata)

        ON CONFLICT DO NOTHING

        RETURNING * INTO cached_search

    ;



    IF NOT FOUND OR cached_search IS NULL THEN

        UPDATE searches SET

            lastused = now(),

            usecount = searches.usecount + 1

        WHERE hash = (

            SELECT hash FROM searches WHERE hash=search.hash FOR UPDATE SKIP LOCKED

        )

        RETURNING * INTO cached_search

        ;

    END IF;



    IF cached_search IS NOT NULL THEN

        cached_search._where = search._where;

        cached_search.orderby = search.orderby;

        RETURN cached_search;

    END IF;

    RETURN search;



END;

$$;


--
-- Name: search_rows(text, text, text[], integer); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.search_rows(_where text DEFAULT 'TRUE'::text, _orderby text DEFAULT 'datetime DESC, id DESC'::text, partitions text[] DEFAULT NULL::text[], _limit integer DEFAULT 10) RETURNS SETOF pgstac.items
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    base_query text;

    query text;

    sdate timestamptz;

    edate timestamptz;

    n int;

    records_left int := _limit;

    timer timestamptz := clock_timestamp();

    full_timer timestamptz := clock_timestamp();

BEGIN

IF _where IS NULL OR trim(_where) = '' THEN

    _where = ' TRUE ';

END IF;

RAISE NOTICE 'Getting chunks for % %', _where, _orderby;



base_query := $q$

    SELECT * FROM items

    WHERE

    datetime >= %L AND datetime < %L

    AND (%s)

    ORDER BY %s

    LIMIT %L

$q$;



IF _orderby ILIKE 'datetime d%' THEN

    FOR sdate, edate IN SELECT * FROM chunker(_where) ORDER BY 1 DESC LOOP

        RAISE NOTICE 'Running Query for % to %. %', sdate, edate, age_ms(full_timer);

        query := format(

            base_query,

            sdate,

            edate,

            _where,

            _orderby,

            records_left

        );

        RAISE DEBUG 'QUERY: %', query;

        timer := clock_timestamp();

        RETURN QUERY EXECUTE query;



        GET DIAGNOSTICS n = ROW_COUNT;

        records_left := records_left - n;

        RAISE NOTICE 'Returned %/% Rows From % to %. % to go. Time: %ms', n, _limit, sdate, edate, records_left, age_ms(timer);

        timer := clock_timestamp();

        IF records_left <= 0 THEN

            RAISE NOTICE 'SEARCH_ROWS TOOK %ms', age_ms(full_timer);

            RETURN;

        END IF;

    END LOOP;

ELSIF _orderby ILIKE 'datetime a%' THEN

    FOR sdate, edate IN SELECT * FROM chunker(_where) ORDER BY 1 ASC LOOP

        RAISE NOTICE 'Running Query for % to %. %', sdate, edate, age_ms(full_timer);

        query := format(

            base_query,

            sdate,

            edate,

            _where,

            _orderby,

            records_left

        );

        RAISE DEBUG 'QUERY: %', query;

        timer := clock_timestamp();

        RETURN QUERY EXECUTE query;



        GET DIAGNOSTICS n = ROW_COUNT;

        records_left := records_left - n;

        RAISE NOTICE 'Returned %/% Rows From % to %. % to go. Time: %ms', n, _limit, sdate, edate, records_left, age_ms(timer);

        timer := clock_timestamp();

        IF records_left <= 0 THEN

            RAISE NOTICE 'SEARCH_ROWS TOOK %ms', age_ms(full_timer);

            RETURN;

        END IF;

    END LOOP;

ELSE

    query := format($q$

        SELECT * FROM items

        WHERE %s

        ORDER BY %s

        LIMIT %L

    $q$, _where, _orderby, _limit

    );

    RAISE DEBUG 'QUERY: %', query;

    timer := clock_timestamp();

    RETURN QUERY EXECUTE query;

    RAISE NOTICE 'FULL QUERY TOOK %ms', age_ms(timer);

END IF;

RAISE NOTICE 'SEARCH_ROWS TOOK %ms', age_ms(full_timer);

RETURN;

END;

$_$;


--
-- Name: set_version(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.set_version(text) RETURNS text
    LANGUAGE sql
    AS $_$

  INSERT INTO pgstac.migrations (version) VALUES ($1)

  ON CONFLICT DO NOTHING

  RETURNING version;

$_$;


--
-- Name: sort_dir_to_op(text, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.sort_dir_to_op(_dir text, prev boolean DEFAULT false) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

    WITH t AS (

        SELECT COALESCE(upper(_dir), 'ASC') as d

    ) SELECT

        CASE

            WHEN d = 'ASC' AND prev THEN '<='

            WHEN d = 'DESC' AND prev THEN '>='

            WHEN d = 'ASC' THEN '>='

            WHEN d = 'DESC' THEN '<='

        END

    FROM t;

$$;


--
-- Name: sort_sqlorderby(jsonb, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.sort_sqlorderby(_search jsonb DEFAULT NULL::jsonb, reverse boolean DEFAULT false) RETURNS text
    LANGUAGE sql
    AS $_$

    WITH sortby AS (

        SELECT coalesce(_search->'sortby','[{"field":"datetime", "direction":"desc"}]') as sort

    ), withid AS (

        SELECT CASE

            WHEN sort @? '$[*] ? (@.field == "id")' THEN sort

            ELSE sort || '[{"field":"id", "direction":"desc"}]'::jsonb

            END as sort

        FROM sortby

    ), withid_rows AS (

        SELECT jsonb_array_elements(sort) as value FROM withid

    ),sorts AS (

        SELECT

            coalesce(

                (queryable(value->>'field')).expression

            ) as key,

            parse_sort_dir(value->>'direction', reverse) as dir

        FROM withid_rows

    )

    SELECT array_to_string(

        array_agg(concat(key, ' ', dir)),

        ', '

    ) FROM sorts;

$_$;


--
-- Name: spatial_op_query(text, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.spatial_op_query(op text, args jsonb) RETURNS text
    LANGUAGE plpgsql
    AS $$

DECLARE

    geom text;

    j jsonb := args->1;

BEGIN

    op := lower(op);

    RAISE NOTICE 'Constructing spatial query OP: %, ARGS: %', op, args;

    IF op NOT IN ('s_equals','s_disjoint','s_touches','s_within','s_overlaps','s_crosses','s_intersects','intersects','s_contains') THEN

        RAISE EXCEPTION 'Spatial Operator % Not Supported', op;

    END IF;

    op := regexp_replace(op, '^s_', 'st_');

    IF op = 'intersects' THEN

        op := 'st_intersects';

    END IF;

    -- Convert geometry to WKB string

    IF j ? 'type' AND j ? 'coordinates' THEN

        geom := st_geomfromgeojson(j)::text;

    ELSIF jsonb_typeof(j) = 'array' THEN

        geom := bbox_geom(j)::text;

    END IF;



    RETURN format('%s(geometry, %L::geometry)', op, geom);

END;

$$;


--
-- Name: stac_daterange(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.stac_daterange(value jsonb) RETURNS tstzrange
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
    SET "TimeZone" TO 'UTC'
    AS $$

DECLARE

    props jsonb := value;

    dt timestamptz;

    edt timestamptz;

BEGIN

    IF props ? 'properties' THEN

        props := props->'properties';

    END IF;

    IF

        props ? 'start_datetime'

        AND props->>'start_datetime' IS NOT NULL

        AND props ? 'end_datetime'

        AND props->>'end_datetime' IS NOT NULL

    THEN

        dt := props->>'start_datetime';

        edt := props->>'end_datetime';

        IF dt > edt THEN

            RAISE EXCEPTION 'start_datetime must be < end_datetime';

        END IF;

    ELSE

        dt := props->>'datetime';

        edt := props->>'datetime';

    END IF;

    IF dt is NULL OR edt IS NULL THEN

        RAISE NOTICE 'DT: %, EDT: %', dt, edt;

        RAISE EXCEPTION 'Either datetime (%) or both start_datetime (%) and end_datetime (%) must be set.', props->>'datetime',props->>'start_datetime',props->>'end_datetime';

    END IF;

    RETURN tstzrange(dt, edt, '[]');

END;

$$;


--
-- Name: stac_datetime(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.stac_datetime(value jsonb) RETURNS timestamp with time zone
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET "TimeZone" TO 'UTC'
    AS $$

    SELECT lower(stac_daterange(value));

$$;


--
-- Name: stac_end_datetime(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.stac_end_datetime(value jsonb) RETURNS timestamp with time zone
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET "TimeZone" TO 'UTC'
    AS $$

    SELECT upper(stac_daterange(value));

$$;


--
-- Name: stac_geom(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.stac_geom(value jsonb) RETURNS public.geometry
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

SELECT

    CASE

            WHEN value ? 'intersects' THEN

                ST_GeomFromGeoJSON(value->>'intersects')

            WHEN value ? 'geometry' THEN

                ST_GeomFromGeoJSON(value->>'geometry')

            WHEN value ? 'bbox' THEN

                pgstac.bbox_geom(value->'bbox')

            ELSE NULL

        END as geometry

;

$$;


--
-- Name: stac_search_to_where(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.stac_search_to_where(j jsonb) RETURNS text
    LANGUAGE plpgsql STABLE
    AS $_$

DECLARE

    where_segments text[];

    _where text;

    dtrange tstzrange;

    collections text[];

    geom geometry;

    sdate timestamptz;

    edate timestamptz;

    filterlang text;

    filter jsonb := j->'filter';

    ft_query tsquery;

BEGIN

    IF j ? 'ids' THEN

        where_segments := where_segments || format('id = ANY (%L) ', to_text_array(j->'ids'));

    END IF;



    IF j ? 'collections' THEN

        collections := to_text_array(j->'collections');

        where_segments := where_segments || format('collection = ANY (%L) ', collections);

    END IF;



    IF j ? 'datetime' THEN

        dtrange := parse_dtrange(j->'datetime');

        sdate := lower(dtrange);

        edate := upper(dtrange);



        where_segments := where_segments || format(' datetime <= %L::timestamptz AND end_datetime >= %L::timestamptz ',

            edate,

            sdate

        );

    END IF;



    IF j ? 'q' THEN

        ft_query := q_to_tsquery(j->'q');

        where_segments := where_segments || format(

            $quote$

            (

                to_tsvector('english', content->'properties'->>'description') ||

                to_tsvector('english', coalesce(content->'properties'->>'title', '')) ||

                to_tsvector('english', coalesce(content->'properties'->>'keywords', ''))

            ) @@ %L

            $quote$,

            ft_query

        );

    END IF;



    geom := stac_geom(j);

    IF geom IS NOT NULL THEN

        where_segments := where_segments || format('st_intersects(geometry, %L)',geom);

    END IF;



    filterlang := COALESCE(

        j->>'filter-lang',

        get_setting('default_filter_lang', j->'conf')

    );

    IF NOT filter @? '$.**.op' THEN

        filterlang := 'cql-json';

    END IF;



    IF filterlang NOT IN ('cql-json','cql2-json') AND j ? 'filter' THEN

        RAISE EXCEPTION '% is not a supported filter-lang. Please use cql-json or cql2-json.', filterlang;

    END IF;



    IF j ? 'query' AND j ? 'filter' THEN

        RAISE EXCEPTION 'Can only use either query or filter at one time.';

    END IF;



    IF j ? 'query' THEN

        filter := query_to_cql2(j->'query');

    ELSIF filterlang = 'cql-json' THEN

        filter := cql1_to_cql2(filter);

    END IF;

    RAISE NOTICE 'FILTER: %', filter;

    where_segments := where_segments || cql2_query(filter);

    IF cardinality(where_segments) < 1 THEN

        RETURN ' TRUE ';

    END IF;



    _where := array_to_string(array_remove(where_segments, NULL), ' AND ');



    IF _where IS NULL OR BTRIM(_where) = '' THEN

        RETURN ' TRUE ';

    END IF;

    RETURN _where;



END;

$_$;


--
-- Name: strip_jsonb(jsonb, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.strip_jsonb(_a jsonb, _b jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$

    SELECT

    CASE



        WHEN (_a IS NULL OR jsonb_typeof(_a) = 'null') AND _b IS NOT NULL AND jsonb_typeof(_b) != 'null' THEN '"𒍟※"'::jsonb

        WHEN _b IS NULL OR jsonb_typeof(_a) = 'null' THEN _a

        WHEN _a = _b AND jsonb_typeof(_a) = 'object' THEN '{}'::jsonb

        WHEN _a = _b THEN NULL

        WHEN jsonb_typeof(_a) = 'object' AND jsonb_typeof(_b) = 'object' THEN

            (

                SELECT

                    jsonb_strip_nulls(

                        jsonb_object_agg(

                            key,

                            strip_jsonb(a.value, b.value)

                        )

                    )

                FROM

                    jsonb_each(_a) as a

                FULL JOIN

                    jsonb_each(_b) as b

                USING (key)

            )

        WHEN

            jsonb_typeof(_a) = 'array'

            AND jsonb_typeof(_b) = 'array'

            AND jsonb_array_length(_a) = jsonb_array_length(_b)

        THEN

            (

                SELECT jsonb_agg(m) FROM

                    ( SELECT

                        strip_jsonb(

                            jsonb_array_elements(_a),

                            jsonb_array_elements(_b)

                        ) as m

                    ) as l

            )

        ELSE _a

    END

    ;

$$;


--
-- Name: sync_partition_stats(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.sync_partition_stats() RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $$

BEGIN

    -- Ordered by partition, as every other writer of these rows is.

    INSERT INTO partition_stats (partition, collection, partition_dtrange)

        SELECT partition, collection, partition_dtrange FROM partitions_view

        ORDER BY partition

        ON CONFLICT (partition) DO UPDATE

            SET collection = EXCLUDED.collection,

                partition_dtrange = EXCLUDED.partition_dtrange

            WHERE

                partition_stats.collection IS DISTINCT FROM EXCLUDED.collection

                OR partition_stats.partition_dtrange IS DISTINCT FROM EXCLUDED.partition_dtrange

    ;



    DELETE FROM partition_stats ps

    WHERE ps.partition IN (

        SELECT partition FROM partition_stats stale

        WHERE NOT EXISTS (

            SELECT 1 FROM partitions_view pv WHERE pv.partition = stale.partition

        )

        ORDER BY partition

        FOR UPDATE

    );

END;

$$;


--
-- Name: t2s(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.t2s(text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$

    SELECT extract(epoch FROM $1::interval)::text || ' s';

$_$;


--
-- Name: table_empty(text); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.table_empty(text) RETURNS boolean
    LANGUAGE plpgsql
    AS $_$

DECLARE

    retval boolean;

BEGIN

    EXECUTE format($q$

        SELECT NOT EXISTS (SELECT 1 FROM %I LIMIT 1)

        $q$,

        $1

    ) INTO retval;

    RETURN retval;

END;

$_$;


--
-- Name: temporal_op_query(text, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.temporal_op_query(op text, args jsonb) RETURNS text
    LANGUAGE plpgsql STABLE STRICT
    AS $$

DECLARE

    ll text := 'datetime';

    lh text := 'end_datetime';

    rrange tstzrange;

    rl text;

    rh text;

    outq text;

BEGIN

    rrange := parse_dtrange(args->1);

    RAISE NOTICE 'Constructing temporal query OP: %, ARGS: %, RRANGE: %', op, args, rrange;

    op := lower(op);

    rl := format('%L::timestamptz', lower(rrange));

    rh := format('%L::timestamptz', upper(rrange));

    outq := CASE op

        WHEN 't_before'       THEN 'lh < rl'

        WHEN 't_after'        THEN 'll > rh'

        WHEN 't_meets'        THEN 'lh = rl'

        WHEN 't_metby'        THEN 'll = rh'

        WHEN 't_overlaps'     THEN 'll < rl AND rl < lh < rh'

        WHEN 't_overlappedby' THEN 'rl < ll < rh AND lh > rh'

        WHEN 't_starts'       THEN 'll = rl AND lh < rh'

        WHEN 't_startedby'    THEN 'll = rl AND lh > rh'

        WHEN 't_during'       THEN 'll > rl AND lh < rh'

        WHEN 't_contains'     THEN 'll < rl AND lh > rh'

        WHEN 't_finishes'     THEN 'll > rl AND lh = rh'

        WHEN 't_finishedby'   THEN 'll < rl AND lh = rh'

        WHEN 't_equals'       THEN 'll = rl AND lh = rh'

        WHEN 't_disjoint'     THEN 'NOT (ll <= rh AND lh >= rl)'

        WHEN 't_intersects'   THEN 'll <= rh AND lh >= rl'

        WHEN 'anyinteracts'   THEN 'll <= rh AND lh >= rl'

    END;

    outq := regexp_replace(outq, '\mll\M', ll);

    outq := regexp_replace(outq, '\mlh\M', lh);

    outq := regexp_replace(outq, '\mrl\M', rl);

    outq := regexp_replace(outq, '\mrh\M', rh);

    outq := format('(%s)', outq);

    RETURN outq;

END;

$$;


--
-- Name: tileenvelope(integer, integer, integer); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.tileenvelope(zoom integer, x integer, y integer) RETURNS public.geometry
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$

WITH t AS (

    SELECT

        20037508.3427892 as merc_max,

        -20037508.3427892 as merc_min,

        (2 * 20037508.3427892) / (2 ^ zoom) as tile_size

)

SELECT st_makeenvelope(

    merc_min + (tile_size * x),

    merc_max - (tile_size * (y + 1)),

    merc_min + (tile_size * (x + 1)),

    merc_max - (tile_size * y),

    3857

) FROM t;

$$;


--
-- Name: to_float(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.to_float(jsonb) RETURNS double precision
    LANGUAGE sql IMMUTABLE STRICT COST 5000 PARALLEL SAFE
    AS $_$

    SELECT ($1->>0)::float;

$_$;


--
-- Name: to_int(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.to_int(jsonb) RETURNS integer
    LANGUAGE sql IMMUTABLE STRICT COST 5000 PARALLEL SAFE
    AS $_$

    SELECT floor(($1->>0)::float)::int;

$_$;


--
-- Name: to_text(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.to_text(jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT COST 5000 PARALLEL SAFE
    AS $_$

    SELECT CASE WHEN jsonb_typeof($1) IN ('array','object') THEN $1::text ELSE $1->>0 END;

$_$;


--
-- Name: to_text_array(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.to_text_array(jsonb) RETURNS text[]
    LANGUAGE sql IMMUTABLE STRICT COST 5000 PARALLEL SAFE
    AS $_$

    SELECT

        CASE jsonb_typeof($1)

            WHEN 'array' THEN ARRAY(SELECT jsonb_array_elements_text($1))

            ELSE ARRAY[$1->>0]

        END

    ;

$_$;


--
-- Name: to_tstz(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.to_tstz(jsonb) RETURNS timestamp with time zone
    LANGUAGE sql IMMUTABLE STRICT COST 5000 PARALLEL SAFE
    SET "TimeZone" TO 'UTC'
    AS $_$

    SELECT ($1->>0)::timestamptz;

$_$;


--
-- Name: unnest_collection(text[]); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.unnest_collection(collection_ids text[] DEFAULT NULL::text[]) RETURNS SETOF text
    LANGUAGE plpgsql STABLE
    AS $$

    DECLARE

    BEGIN

        IF collection_ids IS NULL THEN

            RETURN QUERY SELECT id FROM collections;

        END IF;

        RETURN QUERY SELECT unnest(collection_ids);

    END;

$$;


--
-- Name: update_collection(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.update_collection(data jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $$

DECLARE

    out collections%ROWTYPE;

BEGIN

    UPDATE collections SET content=data WHERE id = data->>'id' RETURNING * INTO STRICT out;

END;

$$;


--
-- Name: update_collection_extents(); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.update_collection_extents() RETURNS void
    LANGUAGE sql
    AS $$

UPDATE collections

    SET content = jsonb_set_lax(

        content,

        '{extent}'::text[],

        collection_extent(id, TRUE),

        true,

        'return_target'

    )

;

$$;


--
-- Name: update_item(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.update_item(content jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $$

DECLARE

    old items %ROWTYPE;

    out items%ROWTYPE;

BEGIN

    PERFORM delete_item(content->>'id', content->>'collection');

    PERFORM create_item(content);

END;

$$;


--
-- Name: update_partition_stats(text, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.update_partition_stats(_partition text, istrigger boolean DEFAULT false, _extent boolean DEFAULT NULL::boolean) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pgstac', 'public'
    AS $_$

DECLARE

    dtrange tstzrange;

    edtrange tstzrange;

    cdtrange tstzrange;

    cedtrange tstzrange;

    extent geometry;

    collection text;

    pdtrange tstzrange;

    auto_extent boolean := get_setting_bool('update_collection_extent');

    do_extent boolean := COALESCE(_extent, auto_extent);

BEGIN

    -- Cannot be STRICT: _extent is three valued, and STRICT would skip the

    -- body whenever it is NULL.

    IF _partition IS NULL OR istrigger IS NULL THEN

        RETURN;

    END IF;

    RAISE NOTICE 'Updating stats for %.', _partition;



    SELECT m.collection, m.partition_dtrange, m.constraint_dtrange, m.constraint_edtrange

        INTO collection, pdtrange, cdtrange, cedtrange

    FROM partition_catalog_meta(_partition) m;



    -- A queued update can outlive the partition it names.

    IF NOT FOUND THEN

        RAISE NOTICE 'Partition % no longer exists, skipping stats update.', _partition;

        RETURN;

    END IF;



    -- Taken before the partition is read. The constraint rebuild below needs

    -- ACCESS EXCLUSIVE, and escalating to that mid-transaction deadlocks

    -- against another session doing the same. SHARE UPDATE EXCLUSIVE conflicts

    -- with itself but not with readers.

    IF NOT istrigger THEN

        EXECUTE format('LOCK TABLE %I IN SHARE UPDATE EXCLUSIVE MODE', _partition);

    END IF;



    -- The observed ranges feed the constraint tightening below and collection

    -- extents. When neither will read them, only the partition's identity is

    -- written, which is what keeps it visible to search.

    IF NOT istrigger OR do_extent THEN

        -- st_extent visits every geometry, so it is only run when wanted.

        IF do_extent THEN

            EXECUTE format(

                $q$

                    SELECT

                        tstzrange(min(datetime), max(datetime),'[]'),

                        tstzrange(min(end_datetime), max(end_datetime), '[]'),

                        st_extent(geometry)::geometry

                    FROM %I

                $q$,

                _partition

            ) INTO dtrange, edtrange, extent;

            RAISE DEBUG 'Extent: %', extent;

        ELSE

            EXECUTE format(

                $q$

                    SELECT

                        tstzrange(min(datetime), max(datetime),'[]'),

                        tstzrange(min(end_datetime), max(end_datetime), '[]')

                    FROM %I

                $q$,

                _partition

            ) INTO dtrange, edtrange;

        END IF;



        INSERT INTO partition_stats

            (partition, collection, partition_dtrange, dtrange, edtrange, spatial, last_updated)

            VALUES (_partition, collection, pdtrange, dtrange, edtrange, extent, now())

            ON CONFLICT (partition) DO

                UPDATE SET

                    collection=EXCLUDED.collection,

                    partition_dtrange=EXCLUDED.partition_dtrange,

                    dtrange=EXCLUDED.dtrange,

                    edtrange=EXCLUDED.edtrange,

                    spatial=COALESCE(EXCLUDED.spatial, partition_stats.spatial),

                    last_updated=EXCLUDED.last_updated

        ;

    ELSE

        INSERT INTO partition_stats (partition, collection, partition_dtrange)

            VALUES (_partition, collection, pdtrange)

            ON CONFLICT (partition) DO UPDATE

                SET collection = EXCLUDED.collection,

                    partition_dtrange = EXCLUDED.partition_dtrange

                WHERE

                    partition_stats.collection IS DISTINCT FROM EXCLUDED.collection

                    OR partition_stats.partition_dtrange IS DISTINCT FROM EXCLUDED.partition_dtrange

        ;

    END IF;



    RAISE NOTICE 'Checking if we need to modify constraints...';

    RAISE NOTICE 'cdtrange: % dtrange: % cedtrange: % edtrange: %',cdtrange, dtrange, cedtrange, edtrange;

    IF

        (cdtrange IS DISTINCT FROM dtrange OR edtrange IS DISTINCT FROM cedtrange)

        AND NOT istrigger

    THEN

        RAISE NOTICE 'Modifying Constraints';

        RAISE NOTICE 'Existing % %', cdtrange, cedtrange;

        RAISE NOTICE 'New      % %', dtrange, edtrange;

        PERFORM drop_table_constraints(_partition);

        PERFORM create_table_constraints(_partition, dtrange, edtrange);

    END IF;

    -- auto_extent, not do_extent: a caller that passed _extent aggregates the

    -- extent itself, and update_collection_extents would then be updating

    -- collections from inside its own UPDATE of collections.

    RAISE NOTICE 'Checking if we need to update collection extents.';

    IF auto_extent THEN

        RAISE NOTICE 'updating collection extent for %', collection;

        PERFORM run_or_queue(format($q$

            UPDATE collections

            SET content = jsonb_set_lax(

                content,

                '{extent}'::text[],

                collection_extent(%L, FALSE),

                true,

                'use_json_null'

            ) WHERE id=%L

            ;

        $q$, collection, collection));

    ELSE

        RAISE NOTICE 'Not updating collection extent for %', collection;

    END IF;



END;

$_$;


--
-- Name: update_partition_stats_q(text, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.update_partition_stats_q(_partition text, istrigger boolean DEFAULT false) RETURNS boolean
    LANGUAGE plpgsql
    AS $$

DECLARE

BEGIN

    RETURN run_or_queue(

        format('SELECT update_partition_stats(%L, %L);', _partition, istrigger)

    );

END;

$$;


--
-- Name: upsert_collection(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.upsert_collection(data jsonb) RETURNS void
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    INSERT INTO collections (content)

    VALUES (data)

    ON CONFLICT (id) DO

    UPDATE

        SET content=EXCLUDED.content

    ;

$$;


--
-- Name: upsert_item(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.upsert_item(data jsonb) RETURNS void
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    INSERT INTO items_staging_upsert (content) VALUES (data);

$$;


--
-- Name: upsert_items(jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.upsert_items(data jsonb) RETURNS void
    LANGUAGE sql
    SET search_path TO 'pgstac', 'public'
    AS $$

    INSERT INTO items_staging_upsert (content)

    SELECT * FROM jsonb_array_elements(data);

$$;


--
-- Name: validate_constraints(); Type: PROCEDURE; Schema: pgstac; Owner: -
--

CREATE PROCEDURE pgstac.validate_constraints()
    LANGUAGE plpgsql
    AS $$

DECLARE

    q text;

BEGIN

    FOR q IN

    SELECT

        FORMAT(

            'ALTER TABLE %I.%I VALIDATE CONSTRAINT %I;',

            nsp.nspname,

            cls.relname,

            con.conname

        )



    FROM pg_constraint AS con

        JOIN pg_class AS cls

        ON con.conrelid = cls.oid

        JOIN pg_namespace AS nsp

        ON cls.relnamespace = nsp.oid

    WHERE convalidated = FALSE AND contype in ('c','f')

    AND nsp.nspname = 'pgstac'

    LOOP

        RAISE NOTICE '%', q;

        PERFORM run_or_queue(q);

        COMMIT;

    END LOOP;

END;

$$;


--
-- Name: search_wheres; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.search_wheres (
    id bigint NOT NULL,
    _where text NOT NULL,
    lastused timestamp with time zone DEFAULT now(),
    usecount bigint DEFAULT 0,
    statslastupdated timestamp with time zone,
    estimated_count bigint,
    estimated_cost double precision,
    time_to_estimate double precision,
    total_count bigint,
    time_to_count double precision,
    partitions text[]
);


--
-- Name: where_stats(text, boolean, jsonb); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.where_stats(inwhere text, updatestats boolean DEFAULT false, conf jsonb DEFAULT NULL::jsonb) RETURNS pgstac.search_wheres
    LANGUAGE plpgsql
    AS $$

DECLARE

    t timestamptz;

    i interval;

    explain_json jsonb;

    sw search_wheres%ROWTYPE;

    inwhere_hash text := md5(inwhere);

    _context text := lower(context(conf));

    _stats_ttl interval := context_stats_ttl(conf);

    _estimated_cost_threshold float := context_estimated_cost(conf);

    _estimated_count_threshold int := context_estimated_count(conf);

    ro bool := pgstac.readonly(conf);

BEGIN

    -- If updatestats is true then set ttl to 0

    IF updatestats THEN

        RAISE DEBUG 'Updatestats set to TRUE, setting TTL to 0';

        _stats_ttl := '0'::interval;

    END IF;



    -- If we don't need to calculate context, just return

    IF _context = 'off' THEN

        sw._where = inwhere;

        RETURN sw;

    END IF;



    -- Unlocked read. A fresh hit only bumps bookkeeping counters, and that is

    -- the common case when identical searches run concurrently.

    SELECT * INTO sw FROM search_wheres WHERE md5(_where)=inwhere_hash;



    -- Within ttl: bump usage counters and return. The bump skips locked rows so

    -- identical searches do not serialize; a missed increment is harmless.

    -- sw.id, not "sw IS NOT NULL": a composite is only IS NOT NULL when every

    -- field is, and search_wheres.partitions is never populated.

    IF

        sw.id IS NOT NULL

        AND sw.statslastupdated IS NOT NULL

        AND sw.total_count IS NOT NULL

        AND now() - sw.statslastupdated <= _stats_ttl

    THEN

        RAISE DEBUG 'Stats present in table and lastupdated within ttl: %', sw;

        IF NOT ro THEN

            UPDATE search_wheres SET

                lastused = now(),

                usecount = search_wheres.usecount + 1

            WHERE id = (

                SELECT id FROM search_wheres

                WHERE md5(_where) = inwhere_hash

                FOR UPDATE SKIP LOCKED

            );

        END IF;

        RAISE DEBUG 'Returning cached counts. %', sw;

        RETURN sw;

    END IF;



    -- Missing or stale, so lock the row to compute once, then re-check

    -- freshness in case another session finished while we waited.

    IF NOT ro THEN

        SELECT * INTO sw FROM search_wheres WHERE md5(_where)=inwhere_hash FOR UPDATE;

        IF

            sw.statslastupdated IS NOT NULL

            AND sw.total_count IS NOT NULL

            AND now() - sw.statslastupdated <= _stats_ttl

        THEN

            RAISE DEBUG 'Another process refreshed stats while we waited: %', sw;

            UPDATE search_wheres SET

                lastused = now(),

                usecount = search_wheres.usecount + 1

            WHERE md5(_where) = inwhere_hash

            RETURNING * INTO sw;

            RETURN sw;

        END IF;

    END IF;



    -- Calculate estimated cost and rows

    -- Use explain to get estimated count/cost

    IF sw.estimated_count IS NULL OR sw.estimated_cost IS NULL THEN

        RAISE DEBUG 'Calculating estimated stats';

        t := clock_timestamp();

        EXECUTE format('EXPLAIN (format json) SELECT 1 FROM items WHERE %s', inwhere)

            INTO explain_json;

        RAISE DEBUG 'Time for just the explain: %', clock_timestamp() - t;

        i := clock_timestamp() - t;



        sw.estimated_count := (explain_json->0->'Plan'->>'Plan Rows')::bigint;

        sw.estimated_cost := (explain_json->0->'Plan'->>'Total Cost')::float;

        sw.time_to_estimate := extract(epoch from i);

    END IF;



    RAISE DEBUG 'ESTIMATED_COUNT: %, THRESHOLD %', sw.estimated_count, _estimated_count_threshold;

    RAISE DEBUG 'ESTIMATED_COST: %, THRESHOLD %', sw.estimated_cost, _estimated_cost_threshold;



    -- If context is set to auto and the costs are within the threshold return the estimated costs

    IF

        _context = 'auto'

        AND sw.estimated_count >= _estimated_count_threshold

        AND sw.estimated_cost >= _estimated_cost_threshold

    THEN

        IF NOT ro THEN

            INSERT INTO search_wheres (

                _where,

                lastused,

                usecount,

                statslastupdated,

                estimated_count,

                estimated_cost,

                time_to_estimate,

                total_count,

                time_to_count

            ) VALUES (

                inwhere,

                now(),

                1,

                now(),

                sw.estimated_count,

                sw.estimated_cost,

                sw.time_to_estimate,

                null,

                null

            ) ON CONFLICT ((md5(_where)))

            DO UPDATE SET

                lastused = EXCLUDED.lastused,

                usecount = search_wheres.usecount + 1,

                statslastupdated = EXCLUDED.statslastupdated,

                estimated_count = EXCLUDED.estimated_count,

                estimated_cost = EXCLUDED.estimated_cost,

                time_to_estimate = EXCLUDED.time_to_estimate,

                total_count = EXCLUDED.total_count,

                time_to_count = EXCLUDED.time_to_count

            RETURNING * INTO sw;

        END IF;

        RAISE DEBUG 'Estimates are within thresholds, returning estimates. %', sw;

        RETURN sw;

    END IF;



    -- Calculate Actual Count

    t := clock_timestamp();

    RAISE NOTICE 'Calculating actual count...';

    EXECUTE format(

        'SELECT count(*) FROM items WHERE %s',

        inwhere

    ) INTO sw.total_count;

    i := clock_timestamp() - t;

    RAISE NOTICE 'Actual Count: % -- %', sw.total_count, i;

    sw.time_to_count := extract(epoch FROM i);



    IF NOT ro THEN

        INSERT INTO search_wheres (

            _where,

            lastused,

            usecount,

            statslastupdated,

            estimated_count,

            estimated_cost,

            time_to_estimate,

            total_count,

            time_to_count

        ) VALUES (

            inwhere,

            now(),

            1,

            now(),

            sw.estimated_count,

            sw.estimated_cost,

            sw.time_to_estimate,

            sw.total_count,

            sw.time_to_count

        ) ON CONFLICT ((md5(_where)))

        DO UPDATE SET

            lastused = EXCLUDED.lastused,

            usecount = search_wheres.usecount + 1,

            statslastupdated = EXCLUDED.statslastupdated,

            estimated_count = EXCLUDED.estimated_count,

            estimated_cost = EXCLUDED.estimated_cost,

            time_to_estimate = EXCLUDED.time_to_estimate,

            total_count = EXCLUDED.total_count,

            time_to_count = EXCLUDED.time_to_count

        RETURNING * INTO sw;

    END IF;

    RAISE DEBUG 'Returning with actual count. %', sw;

    RETURN sw;

END;

$$;


--
-- Name: xyzsearch(integer, integer, integer, text, jsonb, integer, integer, interval, boolean, boolean); Type: FUNCTION; Schema: pgstac; Owner: -
--

CREATE FUNCTION pgstac.xyzsearch(_x integer, _y integer, _z integer, queryhash text, fields jsonb DEFAULT NULL::jsonb, _scanlimit integer DEFAULT 10000, _limit integer DEFAULT 100, _timelimit interval DEFAULT '00:00:05'::interval, exitwhenfull boolean DEFAULT true, skipcovered boolean DEFAULT true) RETURNS jsonb
    LANGUAGE sql
    AS $$

    SELECT * FROM geometrysearch(

        st_transform(tileenvelope(_z, _x, _y), 4326),

        queryhash,

        fields,

        _scanlimit,

        _limit,

        _timelimit,

        exitwhenfull,

        skipcovered

    );

$$;


--
-- Name: acervo_pode_ler(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.acervo_pode_ler(camada text) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'pg_temp'
    AS $$
  SELECT EXISTS (
    SELECT 1 FROM plat.acervo_assinatura a
    WHERE a.acervo_camada_id = camada
      AND a.tenant_id = NULLIF(current_setting('plat.tenant_id', true), '')::int
  )
$$;


--
-- Name: FUNCTION acervo_pode_ler(camada text); Type: COMMENT; Schema: plat; Owner: -
--

COMMENT ON FUNCTION plat.acervo_pode_ler(camada text) IS 'Porteiro das views de plat_acervo (item L6-01-b): verdadeiro só quando o inquilino da sessão assina a camada. Recebe argumento constante e não olha coluna nenhuma — por isso vira One-Time Filter no plano e a tabela de base nem chega a ser varrida quando é falso.';


--
-- Name: agenda_enfileirar(uuid, timestamp with time zone, timestamp with time zone, boolean, boolean, integer, integer, text, integer, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.agenda_enfileirar(p_agenda uuid, p_programado_para timestamp with time zone, p_proxima_em timestamp with time zone, p_enfileirar boolean, p_pesado boolean, p_memoria_mb integer, p_timeout_s integer, p_executor text, p_max_tentativas integer, p_chave text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE a plat.agenda; jid uuid;
BEGIN
  SELECT * INTO a FROM plat.agenda WHERE id = p_agenda FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF p_enfileirar THEN
    INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s, executor, max_tentativas,
                         chave, agenda_id, programado_para, agendado_para)
    VALUES (a.tenant_id, a.usuario_id, a.tipo, a.parametros, p_pesado, p_memoria_mb, p_timeout_s, p_executor,
            p_max_tentativas, p_chave, a.id, p_programado_para, now())
    ON CONFLICT (agenda_id, programado_para) DO NOTHING RETURNING id INTO jid;
  END IF;
  UPDATE plat.agenda SET proxima_em = p_proxima_em,
    ultima_em = CASE WHEN jid IS NOT NULL THEN now() ELSE ultima_em END,
    ultimo_job_id = coalesce(jid, ultimo_job_id)
  WHERE id = p_agenda;
  RETURN jid;
END $$;


--
-- Name: agenda_periodica_sincronizar(text, text, jsonb, text, text, timestamp with time zone); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.agenda_periodica_sincronizar(p_nome text, p_tipo text, p_parametros jsonb, p_cron text, p_fuso text, p_proxima_em timestamp with time zone) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE tid int; aid uuid;
BEGIN
  SELECT id INTO tid FROM plat.tenant WHERE slug = 'plataforma';
  IF tid IS NULL THEN RAISE EXCEPTION 'inquilino técnico plataforma ausente (migração 004)'; END IF;
  INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron, fuso, proxima_em)
  VALUES (tid, NULL, p_nome, p_tipo, p_parametros, p_cron, p_fuso, p_proxima_em)
  ON CONFLICT (tenant_id, nome) DO UPDATE SET tipo = EXCLUDED.tipo, parametros = EXCLUDED.parametros,
    cron = EXCLUDED.cron, fuso = EXCLUDED.fuso,
    proxima_em = CASE WHEN plat.agenda.cron <> EXCLUDED.cron OR plat.agenda.proxima_em IS NULL AND plat.agenda.ativa
                      THEN EXCLUDED.proxima_em ELSE plat.agenda.proxima_em END
  RETURNING id INTO aid;
  RETURN aid;
END $$;


--
-- Name: agenda_registrar_fim(uuid, uuid, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.agenda_registrar_fim(p_job uuid, p_agenda uuid, p_estado text) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  UPDATE plat.agenda SET ultimo_estado = p_estado, ultimo_job_id = p_job,
    falhas_seguidas = CASE WHEN p_estado = 'falhou' THEN falhas_seguidas + 1 WHEN p_estado = 'concluido' THEN 0 ELSE falhas_seguidas END,
    ativa = CASE WHEN p_estado = 'falhou' AND falhas_seguidas + 1 >= 5 THEN false ELSE ativa END,
    proxima_em = CASE WHEN p_estado = 'falhou' AND falhas_seguidas + 1 >= 5 THEN NULL ELSE proxima_em END
  WHERE id = p_agenda
$$;


--
-- Name: agenda; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.agenda (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer,
    nome text NOT NULL,
    tipo text NOT NULL,
    parametros jsonb DEFAULT '{}'::jsonb NOT NULL,
    cron text NOT NULL,
    fuso text DEFAULT 'America/Sao_Paulo'::text NOT NULL,
    ativa boolean DEFAULT true NOT NULL,
    proxima_em timestamp with time zone,
    ultima_em timestamp with time zone,
    ultimo_job_id uuid,
    ultimo_estado text,
    falhas_seguidas smallint DEFAULT 0 NOT NULL,
    expira_em timestamp with time zone,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agenda_vencidas(timestamp with time zone); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.agenda_vencidas(p_agora timestamp with time zone DEFAULT now()) RETURNS SETOF plat.agenda
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT * FROM plat.agenda WHERE ativa AND proxima_em IS NOT NULL AND proxima_em <= p_agora
    AND (expira_em IS NULL OR expira_em > p_agora)
  ORDER BY proxima_em FOR UPDATE SKIP LOCKED
$$;


--
-- Name: ambiente_atual(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.ambiente_atual() RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce((SELECT nome FROM plat.ambiente WHERE unico), 'producao') $$;


--
-- Name: amc_execucao_guarda(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.amc_execucao_guarda() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  IF TG_OP = 'DELETE' THEN
    IF OLD.estado = 'concluida' THEN
      RAISE EXCEPTION 'amc_execucao_concluida_imutavel' USING HINT = 'execução concluída não se apaga';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.modelo_id <> OLD.modelo_id OR NEW.versao_hash <> OLD.versao_hash OR NEW.conjunto_id <> OLD.conjunto_id
     OR NEW.pesos <> OLD.pesos OR NEW.camadas <> OLD.camadas OR NEW.motor_versao <> OLD.motor_versao
     OR NEW.semente <> OLD.semente OR NEW.tenant_id <> OLD.tenant_id OR NEW.criado_em <> OLD.criado_em THEN
    RAISE EXCEPTION 'amc_execucao_proveniencia_imutavel'
      USING HINT = 'modelo, versão, conjunto, pesos, camadas, motor e semente de uma execução nunca mudam';
  END IF;
  IF OLD.estado = 'concluida' AND NEW.estado <> OLD.estado THEN
    RAISE EXCEPTION 'amc_execucao_concluida_imutavel';
  END IF;
  RETURN NEW;
END $$;


--
-- Name: amc_materializado_guarda(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.amc_materializado_guarda() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE e text;
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'amc_resultado_imutavel' USING HINT = 'resultado e fator bruto não se editam; rode outra execução';
  END IF;
  SELECT estado INTO e FROM plat.amc_execucao WHERE id = OLD.execucao_id;
  IF e = 'concluida' THEN
    RAISE EXCEPTION 'amc_resultado_imutavel' USING HINT = 'resultado de execução concluída não se apaga';
  END IF;
  RETURN OLD;
END $$;


--
-- Name: amc_modelo_guarda(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.amc_modelo_guarda() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'amc_modelo_nao_apaga' USING HINT = 'apagar = apagado_em; versões executadas ficam para a proveniência';
  END IF;
  IF NEW.tenant_id <> OLD.tenant_id OR NEW.id <> OLD.id OR NEW.criado_em <> OLD.criado_em THEN
    RAISE EXCEPTION 'amc_modelo_identidade_imutavel';
  END IF;
  RETURN NEW;
END $$;


--
-- Name: amc_superusuario(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.amc_superusuario() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) $$;


--
-- Name: amc_versao_imutavel(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.amc_versao_imutavel() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF plat.amc_superusuario() THEN RETURN coalesce(NEW, OLD); END IF;
  RAISE EXCEPTION 'amc_versao_imutavel' USING HINT = 'uma versão de modelo nunca muda; edite o modelo para criar outra';
END $$;


--
-- Name: arquivo_apagado_marcar(integer, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.arquivo_apagado_marcar(p_tenant_id integer, p_chave text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int;
BEGIN
  UPDATE plat.arquivo SET apagado_em = now()
   WHERE tenant_id = p_tenant_id AND chave = p_chave AND apagado_em IS NULL;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;


--
-- Name: arquivo_bucket_cota_atualizar(integer, bigint); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.arquivo_bucket_cota_atualizar(p_tenant_id integer, p_cota_bytes bigint) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  UPDATE plat.arquivo_bucket SET cota_bytes = p_cota_bytes, atualizado_em = now() WHERE tenant_id = p_tenant_id;
$$;


--
-- Name: arquivo_bucket_cotas_atualizar(integer, bigint, bigint, boolean); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.arquivo_bucket_cotas_atualizar(p_tenant_id integer, p_cota_bytes bigint, p_cota_objetos bigint, p_web_ativo boolean) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  UPDATE plat.arquivo_bucket
     SET cota_bytes = p_cota_bytes, cota_objetos = p_cota_objetos, web_ativo = p_web_ativo, atualizado_em = now()
   WHERE tenant_id = p_tenant_id;
$$;


--
-- Name: arquivo_bucket_por_tenant(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.arquivo_bucket_por_tenant(p_tenant_id integer) RETURNS TABLE(tenant_id integer, bucket_id text, bucket_alias text, chave_rw_id text, chave_rw_segredo text, chave_ro_id text, chave_ro_segredo text, cota_bytes bigint, cota_objetos bigint, web_ativo boolean)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes, b.cota_objetos, b.web_ativo
  FROM plat.arquivo_bucket b WHERE b.tenant_id = p_tenant_id;
$$;


--
-- Name: arquivo_bucket_registrar(integer, text, text, text, text, text, text, bigint); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.arquivo_bucket_registrar(p_tenant_id integer, p_bucket_id text, p_bucket_alias text, p_chave_rw_id text, p_chave_rw_segredo text, p_chave_ro_id text, p_chave_ro_segredo text, p_cota_bytes bigint) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  INSERT INTO plat.arquivo_bucket
    (tenant_id, bucket_id, bucket_alias, chave_rw_id, chave_rw_segredo, chave_ro_id, chave_ro_segredo, cota_bytes)
  VALUES (p_tenant_id, p_bucket_id, p_bucket_alias, p_chave_rw_id, p_chave_rw_segredo, p_chave_ro_id,
          p_chave_ro_segredo, p_cota_bytes)
  ON CONFLICT (tenant_id) DO NOTHING;
$$;


--
-- Name: arquivo_bucket_resolver(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.arquivo_bucket_resolver(p_slug text) RETURNS TABLE(tenant_id integer, bucket_id text, bucket_alias text, chave_rw_id text, chave_rw_segredo text, chave_ro_id text, chave_ro_segredo text, cota_bytes bigint, cota_objetos bigint, web_ativo boolean)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes, b.cota_objetos, b.web_ativo
  FROM plat.arquivo_bucket b JOIN plat.tenant t ON t.id = b.tenant_id
  WHERE t.slug = p_slug;
$$;


--
-- Name: auditoria_cobrir(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_cobrir() RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE r text := plat.req_guc('req_id'); m text := plat.req_guc('metodo');
BEGIN
  IF plat.tenant_atual() IS NULL OR r IS NULL OR m IS NULL THEN RETURN NULL; END IF;
  IF m NOT IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN RETURN NULL; END IF;
  IF EXISTS (SELECT 1 FROM plat.auditoria WHERE req_id = r) THEN RETURN NULL; END IF;
  RETURN plat.auditoria_registrar(lower(m) || ' ' || coalesce(plat.req_guc('rota'), '?'),
                                  'rota', plat.req_guc('rota'), NULL, NULL, 'cobertura');
END $$;


--
-- Name: auditoria_contar(timestamp with time zone, timestamp with time zone, integer, text, text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_contar(p_desde timestamp with time zone, p_ate timestamp with time zone, p_ator integer DEFAULT NULL::integer, p_acao text DEFAULT NULL::text, p_recurso_tipo text DEFAULT NULL::text, p_origem text DEFAULT NULL::text) RETURNS bigint
    LANGUAGE sql STABLE
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT count(*) FROM plat.auditoria a
  WHERE a.em >= p_desde AND a.em < p_ate
    AND (p_ator IS NULL OR a.ator_id = p_ator)
    AND (p_acao IS NULL OR a.acao = p_acao)
    AND (p_recurso_tipo IS NULL OR a.recurso_tipo = p_recurso_tipo)
    AND (p_origem IS NULL OR a.origem = p_origem)
$$;


--
-- Name: auditoria_cron_agendar(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_cron_agendar(p_horario text DEFAULT '17 3 * * *'::text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE nome text := plat.auditoria_cron_nome(); esquema text := current_schema(); n int;
BEGIN
  -- to_regproc('cron.schedule') NÃO serve de guarda: o nome é sobrecarregado (2 e 3 argumentos) e a função
  -- levanta erro em vez de devolver NULL. A presença da extensão é a pergunta certa.
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN RETURN NULL; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING nome;
  IF n > 0 THEN EXECUTE 'SELECT cron.unschedule($1)' USING nome; END IF;   -- (b) idempotente
  EXECUTE 'SELECT cron.schedule($1, $2, $3)'
    USING nome, p_horario, format('SELECT %I.auditoria_expurgar()', esquema);
  RETURN nome;
END $_$;


--
-- Name: auditoria_cron_contar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_cron_contar() RETURNS integer
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN RETURN -1; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING plat.auditoria_cron_nome();
  RETURN n;
END $_$;


--
-- Name: auditoria_cron_desagendar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_cron_desagendar() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE nome text := plat.auditoria_cron_nome(); n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN RETURN false; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING nome;
  IF n > 0 THEN EXECUTE 'SELECT cron.unschedule($1)' USING nome; END IF;
  EXECUTE 'SELECT count(*) FROM cron.job WHERE jobname = $1' INTO n USING nome;
  RETURN n = 0;
END $_$;


--
-- Name: auditoria_cron_nome(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_cron_nome() RETURNS text
    LANGUAGE sql STABLE
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT current_schema() || '_auditoria_expurgo'
$$;


--
-- Name: auditoria_expurgar(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_expurgar(p_lote integer DEFAULT 50000) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int := 0; k int;
BEGIN
  PERFORM set_config('plat.auditoria_expurgo', '1', true);
  WITH alvo AS (
    SELECT a.id FROM plat.auditoria a
    LEFT JOIN plat.tenant t ON t.id = a.tenant_id
    WHERE a.em < now() - make_interval(days => greatest(90, least(3650,
            coalesce((t.config->>'auditoria_retencao_dias')::int, 730))))
    LIMIT p_lote)
  DELETE FROM plat.auditoria d USING alvo WHERE d.id = alvo.id;
  GET DIAGNOSTICS k = ROW_COUNT;
  n := k;
  PERFORM set_config('plat.auditoria_expurgo', '', true);
  RETURN n;
END $$;


--
-- Name: auditoria_listar(timestamp with time zone, timestamp with time zone, integer, text, text, text, integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_listar(p_desde timestamp with time zone, p_ate timestamp with time zone, p_ator integer DEFAULT NULL::integer, p_acao text DEFAULT NULL::text, p_recurso_tipo text DEFAULT NULL::text, p_origem text DEFAULT NULL::text, p_limite integer DEFAULT 50, p_deslocamento integer DEFAULT 0) RETURNS TABLE(id bigint, em timestamp with time zone, ator_id integer, ator_login text, token_id integer, acao text, recurso_tipo text, recurso_id text, antes jsonb, depois jsonb, req_id text, ip text, metodo text, rota text, origem text)
    LANGUAGE sql STABLE
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT a.id, a.em, a.ator_id, a.ator_login, a.token_id, a.acao, a.recurso_tipo, a.recurso_id,
         a.antes, a.depois, a.req_id, a.ip, a.metodo, a.rota, a.origem
  FROM plat.auditoria a
  WHERE a.em >= p_desde AND a.em < p_ate
    AND (p_ator IS NULL OR a.ator_id = p_ator)
    AND (p_acao IS NULL OR a.acao = p_acao)
    AND (p_recurso_tipo IS NULL OR a.recurso_tipo = p_recurso_tipo)
    AND (p_origem IS NULL OR a.origem = p_origem)
  ORDER BY a.em DESC, a.id DESC
  LIMIT p_limite OFFSET p_deslocamento
$$;


--
-- Name: auditoria_registrar(text, text, text, jsonb, jsonb, text, integer, integer, text, text, timestamp with time zone); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_registrar(p_acao text, p_recurso_tipo text DEFAULT NULL::text, p_recurso_id text DEFAULT NULL::text, p_antes jsonb DEFAULT NULL::jsonb, p_depois jsonb DEFAULT NULL::jsonb, p_origem text DEFAULT 'aplicacao'::text, p_tenant integer DEFAULT NULL::integer, p_ator integer DEFAULT NULL::integer, p_ip text DEFAULT NULL::text, p_req_id text DEFAULT NULL::text, p_em timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE novo bigint; t int; a int;
BEGIN
  t := coalesce(p_tenant, plat.tenant_atual());
  IF t IS NULL THEN
    RAISE EXCEPTION 'auditoria_sem_contexto' USING HINT = 'auditoria_registrar exige o contexto do inquilino';
  END IF;
  a := coalesce(p_ator, plat.usuario_atual());
  INSERT INTO plat.auditoria(em, tenant_id, ator_id, ator_login, token_id, acao, recurso_tipo, recurso_id,
                             antes, depois, req_id, ip, metodo, rota, origem)
  VALUES (coalesce(p_em, now()), t, a,
          (SELECT u.login FROM plat.usuario u WHERE u.id = a),
          plat.req_guc('token_id')::int,
          p_acao, p_recurso_tipo, p_recurso_id, p_antes, p_depois,
          coalesce(p_req_id, plat.req_guc('req_id')),
          coalesce(p_ip, plat.req_guc('ip')),
          plat.req_guc('metodo'), plat.req_guc('rota'), p_origem)
  RETURNING id INTO novo;
  RETURN novo;
END $$;


--
-- Name: auditoria_retencao_dias(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auditoria_retencao_dias(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT greatest(90, least(3650, coalesce((config->>'auditoria_retencao_dias')::int, 730)))
  FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: auth_desafio_2fa_criar(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_desafio_2fa_criar(p_usuario integer) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE d text;
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  d := encode(gen_random_bytes(32), 'hex');
  UPDATE plat.usuario SET desafio_2fa_hash = encode(sha256(convert_to(d, 'UTF8')), 'hex'),
    desafio_2fa_ate = now() + interval '5 minutes' WHERE id = p_usuario;
  RETURN d;
END $$;


--
-- Name: auth_desafio_2fa_resolver(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_desafio_2fa_resolver(p_hash text) RETURNS TABLE(usuario_id integer, tenant_id integer, login text, nome text, totp_secret text, totp_ativo boolean, totp_ultimo_passo bigint, codigos_recuperacao text[], desafio_2fa_ate timestamp with time zone, bloqueado_ate timestamp with time zone, ativo boolean, ativo_tenant boolean, config jsonb, superadmin boolean)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT u.id, u.tenant_id, u.login, u.nome, u.totp_secret, u.totp_ativo, u.totp_ultimo_passo, u.codigos_recuperacao,
         u.desafio_2fa_ate, u.bloqueado_ate, u.ativo, t.ativo, t.config, u.superadmin
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE u.desafio_2fa_hash = p_hash
$$;


--
-- Name: auth_falha(integer, integer, integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_falha(p_usuario integer, p_max integer, p_min integer, p_janela_min integer) RETURNS timestamp with time zone
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE u record; falhas int; desde timestamptz; ate timestamptz;
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  SELECT falhas_login, falhas_desde INTO u FROM plat.usuario WHERE id = p_usuario;
  IF u.falhas_desde IS NULL OR u.falhas_desde < now() - make_interval(mins => p_janela_min) THEN
    falhas := 1; desde := now();
  ELSE
    falhas := u.falhas_login + 1; desde := u.falhas_desde;
  END IF;
  UPDATE plat.usuario SET falhas_login = falhas, falhas_desde = desde,
    bloqueado_ate = CASE WHEN falhas >= p_max THEN now() + make_interval(mins => p_min) ELSE bloqueado_ate END
  WHERE id = p_usuario RETURNING bloqueado_ate INTO ate;
  RETURN ate;
END $$;


--
-- Name: auth_login(text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_login(p_tenant text, p_login text) RETURNS TABLE(usuario_id integer, tenant_id integer, senha_hash text, perfil text, nome text, tenant_nome text, totp_ativo boolean, bloqueado_ate timestamp with time zone, falhas_login integer, superadmin boolean, origem text, trocar_senha boolean, ativo boolean, ativo_tenant boolean, config jsonb, senha_alterada_em timestamp with time zone)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT u.id, u.tenant_id, u.senha_hash, u.perfil, u.nome, t.nome, u.totp_ativo, u.bloqueado_ate, u.falhas_login,
         u.superadmin, u.origem, u.trocar_senha, u.ativo, t.ativo, t.config, u.senha_alterada_em
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE t.slug = p_tenant AND u.login = lower(p_login)
$$;


--
-- Name: auth_ok(integer, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_ok(p_usuario integer, p_ip text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  UPDATE plat.usuario SET falhas_login = 0, falhas_desde = NULL, bloqueado_ate = NULL, ultimo_login = now(),
    ultimo_ip = p_ip WHERE id = p_usuario;
END $$;


--
-- Name: auth_sessao(text, numeric); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_sessao(p_hash text, p_ociosa_horas numeric) RETURNS TABLE(usuario_id integer, tenant_id integer, login text, perfil text, nome text, email text, tenant_slug text, tenant_nome text, superadmin boolean, config jsonb, privilegios text[], trocar_senha boolean, totp_ativo boolean, origem text, papel_id integer, expira_em timestamp with time zone, ultimo_uso timestamp with time zone, criado_em timestamp with time zone, ip text, ociosa_horas numeric)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE s record; ociosa numeric;
BEGIN
  SELECT x.token_hash, x.expira_em, x.ultimo_uso, x.criado_em, x.ip, u.ativo AS u_ativo, t.ativo AS t_ativo,
         t.config AS cfg
  INTO s
  FROM plat.sessao x JOIN plat.usuario u ON u.id = x.usuario_id JOIN plat.tenant t ON t.id = x.tenant_id
  WHERE x.token_hash = p_hash;
  IF NOT FOUND THEN RETURN; END IF;
  -- GREATEST/LEAST ignoram NULL no PostgreSQL: sem a chave no config, vale p_ociosa_horas (padrão da plataforma
  -- ou o valor de teste em dev); com a chave, corta para 1–24 h
  ociosa := CASE WHEN nullif(s.cfg #>> '{auth,sessao_ociosa_horas}', '') IS NULL THEN p_ociosa_horas
                 ELSE least(greatest((s.cfg #>> '{auth,sessao_ociosa_horas}')::numeric, 1), 24) END;
  IF NOT (s.expira_em > now() AND coalesce(s.ultimo_uso, s.criado_em) >= now() - make_interval(secs => ociosa * 3600)
          AND s.u_ativo AND s.t_ativo) THEN
    RETURN;
  END IF;
  UPDATE plat.sessao SET ultimo_uso = now() WHERE token_hash = p_hash;
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, u.email, t.slug, t.nome, u.superadmin, t.config,
           plat.privilegios_de(u.id), u.trocar_senha, u.totp_ativo, u.origem, u.papel_id, x.expira_em, x.ultimo_uso,
           x.criado_em, x.ip, ociosa
    FROM plat.sessao x JOIN plat.usuario u ON u.id = x.usuario_id JOIN plat.tenant t ON t.id = x.tenant_id
    WHERE x.token_hash = p_hash;
END $$;


--
-- Name: auth_sessao_criar(integer, integer, text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_sessao_criar(p_usuario integer, p_max_dias integer, p_ip text, p_agente text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE tok text; tid int;
BEGIN
  tid := plat.contexto_confere(p_usuario);
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
                 WHERE u.id = p_usuario AND u.ativo AND t.ativo) THEN
    RAISE EXCEPTION 'usuario_inativo_ou_inquilino_suspenso';
  END IF;
  tok := encode(gen_random_bytes(32), 'hex');
  INSERT INTO plat.sessao(token_hash, tenant_id, usuario_id, expira_em, ip, agente, ultimo_uso)
  VALUES (encode(sha256(convert_to(tok, 'UTF8')), 'hex'), tid, p_usuario,
          now() + make_interval(days => greatest(p_max_dias, 1)), p_ip, left(p_agente, 200), now());
  RETURN tok;
END $$;


--
-- Name: auth_sessao_encerrar(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_sessao_encerrar(p_hash text) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  DELETE FROM plat.sessao WHERE token_hash = p_hash
$$;


--
-- Name: auth_token(text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.auth_token(p_hash text, p_ip text) RETURNS TABLE(usuario_id integer, tenant_id integer, login text, perfil text, nome text, email text, escopos text[], restricao jsonb, token_id integer, token_nome text, privilegios text[], trocar_senha boolean, expira_em timestamp with time zone, revogado_em timestamp with time zone, renovado_por integer, superadmin boolean, totp_ativo boolean, origem text, tenant_slug text, tenant_nome text, config jsonb, papel_id integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  UPDATE plat.token_servico k SET ultimo_uso = now(), ultimo_ip = p_ip, usos = k.usos + 1
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE k.token_hash = p_hash AND k.usuario_id = u.id AND k.revogado_em IS NULL
    AND k.expira_em > now() AND u.ativo AND t.ativo AND NOT u.trocar_senha;
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, u.email, k.escopos, k.restricao, k.id, k.nome,
           plat.privilegios_de(u.id), u.trocar_senha, k.expira_em, k.revogado_em, k.renovado_por, u.superadmin,
           u.totp_ativo, u.origem, t.slug, t.nome, t.config, u.papel_id
    FROM plat.token_servico k JOIN plat.usuario u ON u.id = k.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
    WHERE k.token_hash = p_hash AND u.ativo AND t.ativo;
END $$;


--
-- Name: camada_preparar(text, text, integer, text, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.camada_preparar(p_schema text, p_tabela text, p_srid integer, p_tipo text, p_usuario integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE t_atual int; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND 'd_' || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  nome_curto := substr(p_tabela, 3);  -- os 16 hex, sem o prefixo c_ (nome de índice/política/trigger não colide)

  EXECUTE format(
    'ALTER TABLE %1$I.%2$I '
    '  ADD COLUMN IF NOT EXISTS globalid       uuid        NOT NULL DEFAULT gen_random_uuid(), '
    '  ADD COLUMN IF NOT EXISTS versao         int         NOT NULL DEFAULT 1, '
    '  ADD COLUMN IF NOT EXISTS tenant_id      int         NOT NULL DEFAULT %3$L, '
    '  ADD COLUMN IF NOT EXISTS criado_em      timestamptz NOT NULL DEFAULT now(), '
    '  ADD COLUMN IF NOT EXISTS atualizado_em  timestamptz NOT NULL DEFAULT now(), '
    '  ADD COLUMN IF NOT EXISTS criado_por     int, '
    '  ADD COLUMN IF NOT EXISTS atualizado_por int',
    p_schema, p_tabela, t_atual
  );
  EXECUTE format('UPDATE %1$I.%2$I SET criado_por = %3$L, atualizado_por = %3$L WHERE criado_por IS NULL',
                  p_schema, p_tabela, p_usuario);
  BEGIN
    EXECUTE format('ALTER TABLE %1$I.%2$I ADD CONSTRAINT c_%3$s_globalid_u UNIQUE (globalid)',
                    p_schema, p_tabela, nome_curto);
  EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL; END;
  BEGIN
    EXECUTE format('ALTER SEQUENCE %1$I.%2$I_fid_seq MAXVALUE 2147483647 NO CYCLE', p_schema, p_tabela);
  EXCEPTION WHEN undefined_table THEN NULL; END;
  EXECUTE format('CREATE INDEX IF NOT EXISTS c_%2$s_geom_gix ON %1$I.%3$I USING gist (geom)',
                  p_schema, nome_curto, p_tabela);
  EXECUTE format('CREATE INDEX IF NOT EXISTS c_%2$s_versao_ix ON %1$I.%3$I (atualizado_em)',
                  p_schema, nome_curto, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I ENABLE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I FORCE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('DROP POLICY IF EXISTS p_c_%2$s ON %1$I.%3$I', p_schema, nome_curto, p_tabela);
  EXECUTE format(
    'CREATE POLICY p_c_%2$s ON %1$I.%3$I FOR ALL TO plat_app, plat_leitor '
    'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
    p_schema, nome_curto, p_tabela
  );
  EXECUTE format('DROP TRIGGER IF EXISTS tg_versao ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_versao BEFORE UPDATE ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_versao()', p_schema, p_tabela);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_tenant ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_tenant BEFORE INSERT ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_inserir()', p_schema, p_tabela);
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, p_tabela, 'plat camada (L0-04)');
  EXECUTE format('GRANT SELECT ON %1$I.%2$I TO plat_leitor', p_schema, p_tabela);
END $_$;


--
-- Name: camada_schema_garantir(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
END $_$;


--
-- Name: catalogo_uso(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.catalogo_uso(p_tenant integer) RETURNS TABLE(itens bigint, na_lixeira bigint, bytes bigint)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT count(*) FILTER (WHERE apagado_em IS NULL), count(*) FILTER (WHERE apagado_em IS NOT NULL),
         coalesce(sum(tamanho_bytes), 0)::bigint
  FROM plat.item WHERE tenant_id = p_tenant
$$;


--
-- Name: categorias_max(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.categorias_max(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT least(900, greatest(50, coalesce((config->'catalogo'->>'categorias_max')::int, 200))) FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: conexao_saude_candidatas(interval, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.conexao_saude_candidatas(p_intervalo interval, p_limite integer) RETURNS TABLE(id uuid, tenant_id integer, tipo text, url text, credencial_cifrada text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'verificacao de saude de conexao so no contexto do inquilino tecnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN QUERY
  SELECT c.id, c.tenant_id, c.tipo, c.url, c.credencial_cifrada
  FROM plat.conexao c
  WHERE c.saude_verificada_em IS NULL OR c.saude_verificada_em < now() - p_intervalo
  ORDER BY c.saude_verificada_em ASC NULLS FIRST
  LIMIT p_limite;
END $$;


--
-- Name: conexao_saude_registrar(uuid, boolean, integer, text, integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.conexao_saude_registrar(p_id uuid, p_ok boolean, p_status integer, p_mensagem text, p_latencia_ms integer, p_manter integer DEFAULT 30) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE v_tenant int; v_saude text; v_atual int;
BEGIN
  SELECT tenant_id INTO v_tenant FROM plat.conexao WHERE id = p_id;
  IF v_tenant IS NULL THEN
    RETURN; -- a conexão foi apagada entre a candidatura e o registro (ou nunca existiu): nunca erro
  END IF;
  v_atual := plat.tenant_atual();
  IF v_atual IS DISTINCT FROM v_tenant
     AND v_atual IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'sem permissao para registrar a saude desta conexao' USING ERRCODE = 'insufficient_privilege';
  END IF;
  v_saude := CASE WHEN p_ok THEN 'ok' ELSE 'erro' END;
  UPDATE plat.conexao
     SET saude = v_saude, saude_mensagem = p_mensagem, saude_latencia_ms = p_latencia_ms, saude_verificada_em = now()
   WHERE id = p_id;
  INSERT INTO plat.conexao_saude_historico(conexao_id, tenant_id, ok, status, mensagem, latencia_ms)
  VALUES (p_id, v_tenant, p_ok, p_status, p_mensagem, p_latencia_ms);
  DELETE FROM plat.conexao_saude_historico
   WHERE conexao_id = p_id
     AND id NOT IN (
       SELECT id FROM plat.conexao_saude_historico WHERE conexao_id = p_id ORDER BY verificada_em DESC LIMIT p_manter
     );
END $$;


--
-- Name: contexto_confere(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.contexto_confere(p_usuario integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE tid int;
BEGIN
  SELECT tenant_id INTO tid FROM plat.usuario WHERE id = p_usuario;
  IF tid IS NULL THEN RAISE EXCEPTION 'usuario_inexistente'; END IF;
  IF plat.tenant_atual() IS DISTINCT FROM tid THEN
    RAISE EXCEPTION 'contexto_de_outro_inquilino' USING HINT = 'a função exige o contexto do inquilino do usuário';
  END IF;
  RETURN tid;
END $$;


--
-- Name: convite_aceitar(text, text, text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.convite_aceitar(p_token_hash text, p_login text, p_nome text, p_senha_hash text) RETURNS TABLE(motivo text, usuario_id integer, tenant_id integer, login text, perfil text, papel_id integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE c plat.convite%ROWTYPE; ativo boolean; uid int;
BEGIN
  SELECT * INTO c FROM plat.convite WHERE token_hash = p_token_hash FOR UPDATE;
  IF c.id IS NULL THEN
    RETURN QUERY SELECT 'invalido', NULL::int, NULL::int, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  IF c.cancelado_em IS NOT NULL THEN
    RETURN QUERY SELECT 'cancelado', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  IF c.usado_em IS NOT NULL THEN
    RETURN QUERY SELECT 'usado', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  IF c.expira_em <= now() THEN
    RETURN QUERY SELECT 'expirado', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  SELECT t.ativo INTO ativo FROM plat.tenant t WHERE t.id = c.tenant_id;
  IF NOT coalesce(ativo, false) THEN
    RETURN QUERY SELECT 'inquilino_suspenso', NULL::int, c.tenant_id, NULL::text, NULL::text, NULL::int; RETURN;
  END IF;
  INSERT INTO plat.usuario(tenant_id, login, nome, email, senha_hash, perfil, papel_id, trocar_senha, senha_alterada_em)
  VALUES (c.tenant_id, lower(p_login), p_nome, c.email, p_senha_hash, c.perfil, c.papel_id, false, now())
  RETURNING id INTO uid;
  UPDATE plat.convite SET usado_em = now(), usuario_criado_id = uid WHERE id = c.id;
  RETURN QUERY SELECT 'ok', uid, c.tenant_id, lower(p_login), c.perfil, c.papel_id;
END $$;


--
-- Name: convite_resolver(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.convite_resolver(p_token_hash text) RETURNS TABLE(motivo text, tenant_slug text, tenant_nome text, email text, perfil text, expira_em timestamp with time zone, config jsonb)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT
    CASE
      WHEN c.id IS NULL THEN 'invalido'
      WHEN c.cancelado_em IS NOT NULL THEN 'cancelado'
      WHEN c.usado_em IS NOT NULL THEN 'usado'
      WHEN c.expira_em <= now() THEN 'expirado'
      WHEN NOT t.ativo THEN 'inquilino_suspenso'
      ELSE 'ok'
    END,
    t.slug, t.nome, c.email, c.perfil, c.expira_em, t.config
  FROM (SELECT 1) uma
  LEFT JOIN plat.convite c ON c.token_hash = p_token_hash
  LEFT JOIN plat.tenant t ON t.id = c.tenant_id
$$;


--
-- Name: cota_agendas(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.cota_agendas(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT coalesce((config->>'cota_agendas')::int, 50) FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: cota_itens(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.cota_itens(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT coalesce((config->'catalogo'->>'cota_itens')::int, 100000) FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: cota_jobs_dia(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.cota_jobs_dia(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT coalesce((config->>'cota_jobs_dia')::int, 1000) FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: cota_jobs_simultaneos(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.cota_jobs_simultaneos(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT coalesce((config->>'cota_jobs_simultaneos')::int, 2) FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: cota_usuarios(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.cota_usuarios(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT least(coalesce((config->>'cota_usuarios')::int, 2000), cota_usuarios_teto)
    FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: eh_superadmin(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.eh_superadmin() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = plat.usuario_atual() AND u.superadmin AND u.ativo)
$$;


--
-- Name: evento_expurgar(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.evento_expurgar(p_meses integer DEFAULT 12) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE r record; n int := 0; limite date;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  limite := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
  IF limite >= date_trunc('month', now())::date THEN
    RAISE EXCEPTION 'limite_no_presente' USING HINT = 'o expurgo nunca alcança a partição do mês corrente';
  END IF;
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.evento'::regclass LOOP
    IF to_date(substring(r.relname FROM 'y(\d{4})m(\d{2})$'), 'YYYY') IS NOT NULL
       AND (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $_$;


--
-- Name: evento_expurgar_inquilino(integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.evento_expurgar_inquilino(p_tenant_id integer, p_meses integer DEFAULT 12) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int; limite timestamptz;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  IF p_tenant_id IS NULL OR NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant_id) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  limite := date_trunc('month', now()) - make_interval(months => p_meses);
  DELETE FROM plat.evento WHERE tenant_id = p_tenant_id AND em < limite;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;


--
-- Name: evento_particao_garantir(date); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.evento_particao_garantir(p_mes date) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
  fim := (ini + interval '1 month')::date;
  nome := format('evento_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.evento FOR VALUES FROM (%L) TO (%L)', nome, ini, fim);
    EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
    EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', nome, nome);
  END IF;
  RETURN nome;
END $$;


--
-- Name: evento_registrar(text, text, text, jsonb, text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.evento_registrar(p_tipo text, p_alvo_tipo text, p_alvo_id text, p_propriedades jsonb, p_ip text, p_req_id text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE novo bigint;
BEGIN
  IF plat.tenant_atual() IS NULL THEN
    RAISE EXCEPTION 'evento_sem_contexto' USING HINT = 'evento_registrar exige o contexto do inquilino';
  END IF;
  BEGIN
    INSERT INTO plat.evento(tenant_id, ator_id, tipo, alvo_tipo, alvo_id, propriedades, ip, req_id)
    VALUES (plat.tenant_atual(), plat.usuario_atual(), p_tipo, p_alvo_tipo, p_alvo_id,
            coalesce(p_propriedades, '{}'::jsonb), p_ip, p_req_id) RETURNING id INTO novo;
  EXCEPTION WHEN check_violation THEN
    PERFORM plat.evento_particao_garantir(now()::date);
    INSERT INTO plat.evento(tenant_id, ator_id, tipo, alvo_tipo, alvo_id, propriedades, ip, req_id)
    VALUES (plat.tenant_atual(), plat.usuario_atual(), p_tipo, p_alvo_tipo, p_alvo_id,
            coalesce(p_propriedades, '{}'::jsonb), p_ip, p_req_id) RETURNING id INTO novo;
  END;
  RETURN novo;
END $$;


--
-- Name: feicao_inserir(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.feicao_inserir() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.tenant_id IS NULL THEN
    NEW.tenant_id := plat.tenant_atual();
  END IF;
  IF NEW.tenant_id IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  NEW.criado_por := coalesce(NEW.criado_por, plat.usuario_atual());
  NEW.atualizado_por := coalesce(NEW.atualizado_por, plat.usuario_atual());
  RETURN NEW;
END $$;


--
-- Name: feicao_versao(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.feicao_versao() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.versao := OLD.versao + 1;
  NEW.atualizado_em := now();
  NEW.atualizado_por := plat.usuario_atual();
  RETURN NEW;
END $$;


--
-- Name: fila_estado(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.fila_estado() RETURNS TABLE(pendentes integer, rodando integer, workers_vivos integer, ultimo_heartbeat timestamp with time zone)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT (SELECT count(*)::int FROM plat.job WHERE estado = 'pendente'),
         (SELECT count(*)::int FROM plat.job WHERE estado = 'rodando'),
         (SELECT count(*)::int FROM plat.worker WHERE heartbeat_em > now() - interval '90 seconds'),
         (SELECT max(heartbeat_em) FROM plat.worker)
$$;


--
-- Name: importacao_estado_final_imutavel(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.importacao_estado_final_imutavel() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF OLD.estado IN ('concluida','falhou','cancelada','expirada') AND NEW.estado IS DISTINCT FROM OLD.estado THEN
    RAISE EXCEPTION 'importacao_em_estado_final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;


--
-- Name: item_contagens(uuid); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_contagens(p_item uuid) RETURNS TABLE(usado_por integer, criado_a_partir_de integer, grupos integer, links_ativos integer)
    LANGUAGE sql STABLE SECURITY DEFINER ROWS 1
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT (SELECT count(*)::int FROM plat.item_relacao r JOIN plat.item i ON i.id = r.origem AND i.apagado_em IS NULL WHERE r.destino = p_item),
         (SELECT count(*)::int FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL WHERE r.origem = p_item),
         (SELECT count(*)::int FROM plat.item_grupo ig WHERE ig.item_id = p_item),
         (SELECT count(*)::int FROM plat.compartilhamento_link k WHERE k.item_id = p_item AND k.revogado_em IS NULL
             AND (k.expira_em IS NULL OR k.expira_em > now()))
  WHERE plat.pode_ler(p_item)
$$;


--
-- Name: item_contagens_lote(uuid[]); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_contagens_lote(p_itens uuid[]) RETURNS TABLE(item_id uuid, usado_por integer, criado_a_partir_de integer, grupos integer, links_ativos integer)
    LANGUAGE sql STABLE SECURITY DEFINER ROWS 50
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT x.id,
         coalesce(up.n, 0)::int,
         coalesce(cp.n, 0)::int,
         coalesce(gr.n, 0)::int,
         coalesce(lk.n, 0)::int
  FROM unnest(p_itens) AS x(id)
  LEFT JOIN (
    SELECT r.destino AS id, count(*) AS n
    FROM plat.item_relacao r JOIN plat.item i ON i.id = r.origem AND i.apagado_em IS NULL
    WHERE r.destino = ANY (p_itens)
    GROUP BY r.destino
  ) up ON up.id = x.id
  LEFT JOIN (
    SELECT r.origem AS id, count(*) AS n
    FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL
    WHERE r.origem = ANY (p_itens)
    GROUP BY r.origem
  ) cp ON cp.id = x.id
  LEFT JOIN (
    SELECT ig.item_id AS id, count(*) AS n
    FROM plat.item_grupo ig
    WHERE ig.item_id = ANY (p_itens)
    GROUP BY ig.item_id
  ) gr ON gr.id = x.id
  LEFT JOIN (
    SELECT k.item_id AS id, count(*) AS n
    FROM plat.compartilhamento_link k
    WHERE k.item_id = ANY (p_itens) AND k.revogado_em IS NULL AND (k.expira_em IS NULL OR k.expira_em > now())
    GROUP BY k.item_id
  ) lk ON lk.id = x.id
$$;


--
-- Name: item_criado_a_partir_de(uuid); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_criado_a_partir_de(p_item uuid) RETURNS TABLE(id uuid, tipo_relacao text, posicao integer, visivel boolean)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT r.destino, r.tipo, r.posicao, plat.pode_ler(r.destino)
  FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL
  WHERE r.origem = p_item AND r.tenant_id = plat.tenant_atual() AND plat.pode_ler(p_item)
  ORDER BY r.posicao NULLS LAST, r.criado_em
$$;


--
-- Name: item_expurgar(uuid); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_expurgar(p_item uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int; t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  DELETE FROM plat.item WHERE id = p_item AND apagado_em IS NOT NULL AND (t_plataforma OR tenant_id = t_ctx);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;


--
-- Name: item_lixeira(uuid, boolean); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_lixeira(p_item uuid, p_apagar boolean) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int;
BEGIN
  IF plat.tenant_atual() IS NULL OR plat.usuario_atual() IS NULL THEN RETURN false; END IF;
  IF NOT (plat.pode_editar(p_item) OR (plat.usuario_do_inquilino() AND plat.tem('conteudo.apagar_tudo')) OR plat.modo_superadmin()) THEN
    RETURN false;
  END IF;
  IF p_apagar THEN
    UPDATE plat.item SET apagado_em = now(), apagado_por = plat.usuario_atual()
     WHERE id = p_item AND tenant_id = plat.tenant_atual() AND apagado_em IS NULL;
  ELSE
    UPDATE plat.item SET apagado_em = NULL, apagado_por = NULL
     WHERE id = p_item AND tenant_id = plat.tenant_atual() AND apagado_em IS NOT NULL;
  END IF;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;


--
-- Name: tags_texto(text[]); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tags_texto(text[]) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $_$ SELECT array_to_string($1, ' ') $_$;


--
-- Name: tags_validas(text[]); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tags_validas(text[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $_$
  SELECT coalesce(bool_and(length(t) BETWEEN 1 AND 128 AND t !~ '[,\n\r\t]' AND t = btrim(t)), true) FROM unnest($1) t $_$;


--
-- Name: pt_sem_acento; Type: TEXT SEARCH CONFIGURATION; Schema: plat; Owner: -
--

CREATE TEXT SEARCH CONFIGURATION plat.pt_sem_acento (
    PARSER = pg_catalog."default" );

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR asciiword WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR word WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR numword WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR email WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR url WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR host WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR sfloat WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR version WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR hword_numpart WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR hword_part WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR hword_asciipart WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR numhword WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR asciihword WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR hword WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR url_path WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR file WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR "float" WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR "int" WITH simple;

ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
    ADD MAPPING FOR uint WITH simple;


--
-- Name: item; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.item (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    tipo text NOT NULL,
    titulo text NOT NULL,
    resumo text,
    descricao text,
    descricao_html text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    creditos text,
    termos_de_uso text,
    termos_de_uso_html text,
    dono_id integer NOT NULL,
    pasta_id uuid,
    extent public.geometry(Polygon,4326),
    extent_origem text,
    miniatura_chave text,
    miniatura_sha256 text,
    dados jsonb DEFAULT '{}'::jsonb NOT NULL,
    acesso text DEFAULT 'privado'::text NOT NULL,
    status text,
    protegido boolean DEFAULT false NOT NULL,
    classificacao jsonb,
    categorias uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    origem text DEFAULT 'hospedado'::text NOT NULL,
    url text,
    tamanho_bytes bigint DEFAULT 0 NOT NULL,
    versao_atual integer DEFAULT 0 NOT NULL,
    versao_publicada integer,
    pontuacao smallint DEFAULT 0 NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    modificado_por integer,
    modificado_em timestamp with time zone DEFAULT now() NOT NULL,
    apagado_em timestamp with time zone,
    apagado_por integer,
    busca tsvector GENERATED ALWAYS AS ((((setweight(to_tsvector('plat.pt_sem_acento'::regconfig, COALESCE(titulo, ''::text)), 'A'::"char") || setweight(to_tsvector('plat.pt_sem_acento'::regconfig, COALESCE(plat.tags_texto(tags), ''::text)), 'B'::"char")) || setweight(to_tsvector('plat.pt_sem_acento'::regconfig, COALESCE(resumo, ''::text)), 'C'::"char")) || setweight(to_tsvector('plat.pt_sem_acento'::regconfig, COALESCE(descricao, ''::text)), 'D'::"char"))) STORED,
    CONSTRAINT item_acesso_check CHECK ((acesso = ANY (ARRAY['privado'::text, 'inquilino'::text, 'publico'::text]))),
    CONSTRAINT item_categorias_check CHECK ((cardinality(categorias) <= 20)),
    CONSTRAINT item_creditos_check CHECK ((length(creditos) <= 2048)),
    CONSTRAINT item_dados_check CHECK ((jsonb_typeof(dados) = 'object'::text)),
    CONSTRAINT item_descricao_check CHECK ((length(descricao) <= 65536)),
    CONSTRAINT item_extent_check CHECK (((extent IS NULL) OR ((public.st_xmin((extent)::public.box3d) >= ('-180'::integer)::double precision) AND (public.st_xmax((extent)::public.box3d) <= (180)::double precision) AND (public.st_ymin((extent)::public.box3d) >= ('-90'::integer)::double precision) AND (public.st_ymax((extent)::public.box3d) <= (90)::double precision) AND public.st_isvalid(extent)))),
    CONSTRAINT item_extent_origem_check CHECK ((extent_origem = ANY (ARRAY['dado'::text, 'usuario'::text, 'inquilino'::text]))),
    CONSTRAINT item_origem_check CHECK ((origem = ANY (ARRAY['hospedado'::text, 'referenciado'::text]))),
    CONSTRAINT item_pontuacao_check CHECK (((pontuacao >= 0) AND (pontuacao <= 10))),
    CONSTRAINT item_resumo_check CHECK ((length(resumo) <= 2048)),
    CONSTRAINT item_status_check CHECK ((status = ANY (ARRAY['autoritativo'::text, 'obsoleto'::text]))),
    CONSTRAINT item_tags_check CHECK (((cardinality(tags) <= 50) AND plat.tags_validas(tags))),
    CONSTRAINT item_termos_de_uso_check CHECK ((length(termos_de_uso) <= 65536)),
    CONSTRAINT item_titulo_check CHECK (((length(titulo) >= 1) AND (length(titulo) <= 250))),
    CONSTRAINT item_url_check CHECK (((url IS NULL) OR ((length(url) <= 2048) AND (url ~ '^https?://'::text))))
);


--
-- Name: item_pontuacao(plat.item); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_pontuacao(i plat.item) RETURNS smallint
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT (1
    + (coalesce(length(i.resumo), 0) > 0)::int
    + (coalesce(length(i.descricao), 0) >= 100)::int
    + (cardinality(i.tags) >= 3)::int
    + (coalesce(length(i.creditos), 0) > 0)::int
    + (coalesce(length(i.termos_de_uso), 0) > 0)::int
    + (i.extent IS NOT NULL)::int
    + (i.miniatura_chave IS NOT NULL)::int
    + (cardinality(i.categorias) >= 1)::int
    + (i.dados #>> '{procedencia,fonte}' IS NOT NULL)::int)::smallint
$$;


--
-- Name: item_retrato(plat.item); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_retrato(i plat.item) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT jsonb_build_object(
    'titulo', i.titulo, 'resumo', i.resumo, 'descricao', i.descricao, 'tags', to_jsonb(i.tags),
    'creditos', i.creditos, 'termos_de_uso', i.termos_de_uso,
    'extent', CASE WHEN i.extent IS NULL THEN NULL ELSE jsonb_build_array(ST_XMin(i.extent), ST_YMin(i.extent), ST_XMax(i.extent), ST_YMax(i.extent)) END,
    'extent_origem', i.extent_origem, 'categorias', to_jsonb(i.categorias), 'classificacao', i.classificacao,
    'url', i.url, 'dados', i.dados)
$$;


--
-- Name: item_usado_por(uuid, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_usado_por(p_item uuid, p_prof integer DEFAULT 2) RETURNS TABLE(id uuid, tipo_relacao text, profundidade integer, caminho uuid[], visivel boolean, apaga_junto boolean)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  WITH RECURSIVE dep AS (
    SELECT r.origem AS id, r.tipo, 1 AS profundidade, ARRAY[p_item, r.origem] AS caminho, rt.apaga_junto
      FROM plat.item_relacao r JOIN plat.relacao_tipo rt ON rt.nome = r.tipo
     WHERE r.destino = p_item AND r.tenant_id = plat.tenant_atual()
    UNION ALL
    SELECT r.origem, r.tipo, dep.profundidade + 1, dep.caminho || r.origem, rt.apaga_junto
      FROM dep JOIN plat.item_relacao r ON r.destino = dep.id JOIN plat.relacao_tipo rt ON rt.nome = r.tipo
     WHERE dep.profundidade < least(p_prof, 20) AND NOT r.origem = ANY (dep.caminho)
  )
  SELECT DISTINCT ON (dep.id) dep.id, dep.tipo, dep.profundidade, dep.caminho, plat.pode_ler(dep.id), dep.apaga_junto
  FROM dep JOIN plat.item i ON i.id = dep.id AND i.apagado_em IS NULL
  WHERE plat.pode_ler(p_item)
  ORDER BY dep.id, dep.profundidade
$$;


--
-- Name: item_versoes_compactar(uuid, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.item_versoes_compactar(p_item uuid, p_manter integer DEFAULT 50) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE corte int; removidas int := 0; r record; bloco int[]; n int;
BEGIN
  SELECT versao INTO corte FROM plat.item_versao WHERE item_id = p_item ORDER BY versao DESC OFFSET p_manter LIMIT 1;
  IF corte IS NULL THEN RETURN 0; END IF;
  FOR r IN SELECT array_agg(versao ORDER BY versao) AS vs, max(versao) AS topo,
                  sum(greatest(compactou, 1))::int AS resumidas
           FROM (SELECT versao, compactou, (row_number() OVER (ORDER BY versao) - 1) / 10 AS grupo
                 FROM plat.item_versao WHERE item_id = p_item AND versao <= corte) x
           GROUP BY grupo HAVING count(*) > 1 LOOP
    DELETE FROM plat.item_versao WHERE item_id = p_item AND versao = ANY (r.vs) AND versao <> r.topo;
    GET DIAGNOSTICS n = ROW_COUNT;
    removidas := removidas + n;
    UPDATE plat.item_versao SET rotulo = 'compactada', compactou = r.resumidas WHERE item_id = p_item AND versao = r.topo;
  END LOOP;
  RETURN removidas;
END $$;


--
-- Name: itens_com_versoes_acima(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.itens_com_versoes_acima(p_manter integer DEFAULT 50) RETURNS SETOF uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY SELECT v.item_id FROM plat.item_versao v WHERE (t_plataforma OR v.tenant_id = t_ctx)
               GROUP BY v.item_id HAVING count(*) > p_manter;
END $$;


--
-- Name: job_cancelar(uuid, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_cancelar(p_id uuid, p_usuario integer) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE j plat.job;
BEGIN
  SELECT * INTO j FROM plat.job WHERE id = p_id AND tenant_id = plat.tenant_atual() FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF j.estado = 'pendente' THEN
    UPDATE plat.job SET estado = 'cancelado', cancelado_por = p_usuario, cancelado_em = now(), terminado_em = now(),
      erro = 'cancelado antes de iniciar' WHERE id = p_id;
    RETURN 'cancelado';
  ELSIF j.estado = 'rodando' THEN
    UPDATE plat.job SET cancelar_solicitado = true, cancelado_por = coalesce(cancelado_por, p_usuario),
      cancelado_em = coalesce(cancelado_em, now()) WHERE id = p_id;
    RETURN 'solicitado';
  END IF;
  RETURN j.estado;
END $$;


--
-- Name: job_ceifar(integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_ceifar(p_limite_s integer, p_max_reinicios integer DEFAULT 5) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT j.id, j.worker FROM plat.job j
           WHERE j.estado = 'rodando'
             AND coalesce(j.heartbeat_em, j.iniciado_em) < now() - make_interval(secs => p_limite_s)
             AND NOT EXISTS (SELECT 1 FROM plat.worker w WHERE w.nome = j.worker
                             AND w.heartbeat_em >= now() - make_interval(secs => p_limite_s)) LOOP
    PERFORM plat.job_devolver(r.id, r.worker, 'worker sem sinal', false, 0, p_max_reinicios);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;


--
-- Name: job_devolver(uuid, text, text, boolean, integer, integer, jsonb); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_devolver(p_id uuid, p_worker text, p_motivo text, p_conta_tentativa boolean, p_espera_s integer, p_max_reinicios integer DEFAULT 5, p_proveniencia jsonb DEFAULT NULL::jsonb) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE j plat.job; novo text;
BEGIN
  SELECT * INTO j FROM plat.job WHERE id = p_id AND estado = 'rodando' AND (p_worker IS NULL OR worker = p_worker) FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  PERFORM plat.via_worker_ligar();
  IF p_conta_tentativa THEN
    novo := CASE WHEN j.tentativa >= j.max_tentativas THEN 'falhou' ELSE 'pendente' END;
    UPDATE plat.job SET estado = novo, erro = left(p_motivo, 2000), worker = NULL, processo_pid = NULL,
      heartbeat_em = NULL, agendado_para = now() + make_interval(secs => greatest(p_espera_s, 0)),
      terminado_em = CASE WHEN novo = 'falhou' THEN now() ELSE NULL END,
      proveniencia = coalesce(proveniencia, '{}'::jsonb) || coalesce(p_proveniencia, '{}'::jsonb)
    WHERE id = p_id;
  ELSE
    novo := CASE WHEN j.reinicios + 1 >= p_max_reinicios THEN 'falhou' ELSE 'pendente' END;
    UPDATE plat.job SET estado = novo, reinicios = reinicios + 1, worker = NULL, processo_pid = NULL, heartbeat_em = NULL,
      tentativa = greatest(tentativa - 1, 0),   -- a retomada refaz job_pegar (+1): reinício não é tentativa
      erro = CASE WHEN novo = 'falhou' THEN format('devolvido %s vezes sem terminar (%s)', p_max_reinicios, p_motivo)
                  ELSE left(p_motivo, 2000) END,
      agendado_para = now() + make_interval(secs => greatest(p_espera_s, 0)),
      terminado_em = CASE WHEN novo = 'falhou' THEN now() ELSE NULL END
    WHERE id = p_id;
  END IF;
  PERFORM plat.via_worker_desligar();
  IF novo = 'falhou' AND j.agenda_id IS NOT NULL THEN PERFORM plat.agenda_registrar_fim(p_id, j.agenda_id, novo); END IF;
  RETURN novo;
END $$;


--
-- Name: job_estado_final_imutavel(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_estado_final_imutavel() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF OLD.estado IN ('concluido','falhou','cancelado') AND (
       NEW.estado IS DISTINCT FROM OLD.estado OR NEW.progresso IS DISTINCT FROM OLD.progresso
    OR NEW.mensagem IS DISTINCT FROM OLD.mensagem OR NEW.resultado IS DISTINCT FROM OLD.resultado
    OR NEW.erro IS DISTINCT FROM OLD.erro OR NEW.cancelar_solicitado IS DISTINCT FROM OLD.cancelar_solicitado
    OR NEW.tentativa IS DISTINCT FROM OLD.tentativa OR NEW.reinicios IS DISTINCT FROM OLD.reinicios
    OR NEW.worker IS DISTINCT FROM OLD.worker OR NEW.iniciado_em IS DISTINCT FROM OLD.iniciado_em
    OR NEW.terminado_em IS DISTINCT FROM OLD.terminado_em OR NEW.proveniencia IS DISTINCT FROM OLD.proveniencia) THEN
    RAISE EXCEPTION 'job em estado final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;


--
-- Name: job_heartbeat(uuid, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_heartbeat(p_id uuid, p_worker text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  UPDATE plat.job SET heartbeat_em = now() WHERE id = p_id AND worker = p_worker AND estado = 'rodando'
  RETURNING cancelar_solicitado
$$;


--
-- Name: job_log_notificar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_log_notificar() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  UPDATE plat.job SET linhas_log = linhas_log + 1 WHERE id = NEW.job_id;
  PERFORM pg_notify('plat_job', json_build_object('job', NEW.job_id, 'tenant_id', NEW.tenant_id,
    'log', json_build_object('id', NEW.id, 'em', NEW.em, 'nivel', NEW.nivel, 'mensagem', left(NEW.mensagem, 1000)))::text);
  RETURN NULL;
END $$;


--
-- Name: job_notificar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_notificar() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE carga text;
BEGIN
  carga := json_build_object('job', NEW.id, 'tenant_id', NEW.tenant_id, 'estado', NEW.estado,
                             'progresso', NEW.progresso, 'mensagem', left(NEW.mensagem, 200),
                             'tentativa', NEW.tentativa, 'cancelar_solicitado', NEW.cancelar_solicitado,
                             'seq', extract(epoch from clock_timestamp()))::text;
  PERFORM pg_notify('plat_job', carga);
  IF NEW.estado = 'pendente' AND (TG_OP = 'INSERT' OR OLD.estado IS DISTINCT FROM 'pendente'
                                  OR NEW.agendado_para IS DISTINCT FROM OLD.agendado_para) THEN
    PERFORM pg_notify('plat_worker', json_build_object('job', NEW.id, 'pendente', true)::text);
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.cancelar_solicitado AND NOT OLD.cancelar_solicitado THEN
    PERFORM pg_notify('plat_worker', json_build_object('job', NEW.id, 'cancelar', true)::text);
  END IF;
  RETURN NULL;
END $$;


--
-- Name: job; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.job (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer,
    tipo text NOT NULL,
    parametros jsonb DEFAULT '{}'::jsonb NOT NULL,
    estado text DEFAULT 'pendente'::text NOT NULL,
    prioridade smallint DEFAULT 5 NOT NULL,
    chave text,
    pesado boolean NOT NULL,
    memoria_mb integer NOT NULL,
    timeout_s integer NOT NULL,
    executor text DEFAULT 'local'::text NOT NULL,
    max_tentativas smallint DEFAULT 3 NOT NULL,
    tentativa smallint DEFAULT 0 NOT NULL,
    reinicios smallint DEFAULT 0 NOT NULL,
    agendado_para timestamp with time zone DEFAULT now() NOT NULL,
    agenda_id uuid,
    programado_para timestamp with time zone,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    iniciado_em timestamp with time zone,
    heartbeat_em timestamp with time zone,
    terminado_em timestamp with time zone,
    worker text,
    processo_pid integer,
    progresso smallint DEFAULT 0 NOT NULL,
    mensagem text,
    cancelar_solicitado boolean DEFAULT false NOT NULL,
    cancelado_por integer,
    cancelado_em timestamp with time zone,
    resultado jsonb,
    erro text,
    proveniencia jsonb,
    linhas_log integer DEFAULT 0 NOT NULL,
    CONSTRAINT job_estado_check CHECK ((estado = ANY (ARRAY['pendente'::text, 'rodando'::text, 'concluido'::text, 'falhou'::text, 'cancelado'::text]))),
    CONSTRAINT job_executor_check CHECK ((executor = ANY (ARRAY['local'::text, 'gpu'::text]))),
    CONSTRAINT job_prioridade_check CHECK (((prioridade >= 1) AND (prioridade <= 9))),
    CONSTRAINT job_progresso_check CHECK (((progresso >= 0) AND (progresso <= 100)))
);


--
-- Name: job_pegar(text, boolean); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE pego plat.job;
BEGIN
  PERFORM plat.via_worker_ligar();
  WITH c AS (
    SELECT j.id FROM plat.job j
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r WHERE r.chave = j.chave AND r.estado = 'rodando'))
      AND (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando')
          < plat.cota_jobs_simultaneos(j.tenant_id)
    ORDER BY j.prioridade, j.agendado_para, j.criado_em
    FOR UPDATE OF j SKIP LOCKED LIMIT 1)
  UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                      tentativa = tentativa + 1, progresso = 0, mensagem = NULL
  FROM c WHERE plat.job.id = c.id RETURNING plat.job.* INTO pego;
  PERFORM plat.via_worker_desligar();
  RETURN pego;
END $$;


--
-- Name: job_pid(uuid, text, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_pid(p_id uuid, p_worker text, p_pid integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET processo_pid = p_pid WHERE id = p_id AND worker = p_worker AND estado = 'rodando';
  PERFORM plat.via_worker_desligar();
END $$;


--
-- Name: job_progresso(uuid, text, integer, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_progresso(p_id uuid, p_worker text, p_progresso integer, p_mensagem text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  UPDATE plat.job SET progresso = greatest(0, least(100, p_progresso)), mensagem = left(p_mensagem, 200), heartbeat_em = now()
  WHERE id = p_id AND worker = p_worker AND estado = 'rodando' AND tenant_id = plat.tenant_atual()
  RETURNING cancelar_solicitado
$$;


--
-- Name: job_terminar(uuid, text, text, jsonb, text, jsonb); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_terminar(p_id uuid, p_worker text, p_estado text, p_resultado jsonb, p_erro text, p_proveniencia jsonb) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int; a uuid;
BEGIN
  IF p_estado NOT IN ('concluido','falhou','cancelado') THEN RAISE EXCEPTION 'estado final inválido: %', p_estado; END IF;
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET estado = p_estado, terminado_em = now(), resultado = p_resultado, erro = left(p_erro, 2000),
                      proveniencia = coalesce(proveniencia, '{}'::jsonb) || coalesce(p_proveniencia, '{}'::jsonb),
                      progresso = CASE WHEN p_estado = 'concluido' THEN 100 ELSE progresso END, processo_pid = NULL
  WHERE id = p_id AND worker = p_worker AND estado = 'rodando' RETURNING agenda_id INTO a;
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM plat.via_worker_desligar();
  IF n = 1 AND a IS NOT NULL THEN PERFORM plat.agenda_registrar_fim(p_id, a, p_estado); END IF;
  RETURN n = 1;
END $$;


--
-- Name: job_transicao(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.job_transicao() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE via_worker boolean := coalesce(current_setting('plat.via_worker', true), '') = 'sim';
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.estado <> 'pendente' OR NEW.resultado IS NOT NULL OR NEW.tentativa <> 0 OR NEW.reinicios <> 0
       OR NEW.worker IS NOT NULL OR NEW.iniciado_em IS NOT NULL OR NEW.terminado_em IS NOT NULL
       OR NEW.progresso <> 0 OR NEW.erro IS NOT NULL OR NEW.cancelar_solicitado THEN
      RAISE EXCEPTION 'job nasce pendente e sem resultado' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT via_worker THEN
    IF NEW.estado IS DISTINCT FROM OLD.estado AND NEW.estado IN ('rodando', 'concluido', 'falhou') THEN
      RAISE EXCEPTION 'transição para % só pelo worker', NEW.estado USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.resultado IS DISTINCT FROM OLD.resultado OR NEW.tentativa IS DISTINCT FROM OLD.tentativa
       OR NEW.reinicios IS DISTINCT FROM OLD.reinicios OR NEW.worker IS DISTINCT FROM OLD.worker
       OR NEW.iniciado_em IS DISTINCT FROM OLD.iniciado_em OR NEW.proveniencia IS DISTINCT FROM OLD.proveniencia
       OR NEW.processo_pid IS DISTINCT FROM OLD.processo_pid THEN
      RAISE EXCEPTION 'resultado, tentativa, reinicios, worker, iniciado_em, proveniencia e pid só pelo worker'
        USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;


--
-- Name: jobs_expurgar(integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.jobs_expurgar(p_dias_job integer, p_dias_log integer) RETURNS TABLE(jobs_apagados integer, logs_apagados integer, marcadores_apagados integer, passos_apagados integer, rodando uuid[])
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE nj int; nl int; nm int; np int;
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT id FROM plat.tenant WHERE slug = 'plataforma') THEN
    RAISE EXCEPTION 'expurgo só no contexto do inquilino técnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  DELETE FROM plat.job_log WHERE em < now() - make_interval(days => p_dias_log);
  GET DIAGNOSTICS nl = ROW_COUNT;
  DELETE FROM plat.job WHERE estado IN ('concluido','falhou','cancelado') AND terminado_em < now() - make_interval(days => p_dias_job);
  GET DIAGNOSTICS nj = ROW_COUNT;
  DELETE FROM plat_trabalho.marcadores m WHERE NOT EXISTS (SELECT 1 FROM plat.job j WHERE j.id = m.job_id);
  GET DIAGNOSTICS nm = ROW_COUNT;
  DELETE FROM plat_trabalho.passos p WHERE NOT EXISTS (SELECT 1 FROM plat.job j WHERE j.id = p.job_id AND j.estado = 'rodando');
  GET DIAGNOSTICS np = ROW_COUNT;
  RETURN QUERY SELECT nj, nl, nm, np, coalesce((SELECT array_agg(id) FROM plat.job WHERE estado = 'rodando'), '{}'::uuid[]);
END $$;


--
-- Name: jobs_no_dia(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.jobs_no_dia(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT count(*)::int FROM plat.job WHERE tenant_id = p_tenant AND criado_em >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
$$;


--
-- Name: jobs_semear_demo(integer, text, jsonb, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.jobs_semear_demo(p_quantos integer, p_tipo text, p_parametros jsonb DEFAULT '{}'::jsonb, p_estado text DEFAULT 'concluido'::text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE t int := plat.tenant_atual(); u int := plat.usuario_atual(); slug text; n int; ids uuid[];
BEGIN
  IF NOT plat.semente_demo_habilitada() THEN
    RAISE EXCEPTION 'semeadura de demonstração desligada (plat.ambiente.semear_demo = false, ambiente %)',
      plat.ambiente_atual() USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF t IS NULL OR u IS NULL THEN
    RAISE EXCEPTION 'jobs_semear_demo exige contexto de inquilino e usuário' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT tn.slug INTO slug FROM plat.tenant tn WHERE tn.id = t;
  IF slug IS NULL OR NOT (slug IN ('demo', 'demo2') OR slug LIKE 'zt-%') THEN
    RAISE EXCEPTION 'jobs_semear_demo só semeia inquilino de demonstração (demo, demo2, zt-%%), não %', slug
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_estado NOT IN ('concluido', 'falhou', 'cancelado') THEN
    RAISE EXCEPTION 'jobs_semear_demo só cria job em estado final (concluido, falhou, cancelado), não %', p_estado
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_quantos IS NULL OR p_quantos < 1 OR p_quantos > 5000 THEN
    RAISE EXCEPTION 'jobs_semear_demo aceita de 1 a 5000 por chamada, recebeu %', p_quantos USING ERRCODE = 'check_violation';
  END IF;
  IF p_tipo IS NULL OR p_tipo = '' THEN
    RAISE EXCEPTION 'jobs_semear_demo exige o nome do tipo' USING ERRCODE = 'check_violation';
  END IF;

  -- 2.1 nasce pendente e limpo: exatamente o que o gatilho de INSERT da 006 permite a qualquer chamador
  WITH novos AS (
    INSERT INTO plat.job (tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s,
                          agendado_para, criado_em)
    SELECT t, u, p_tipo,
           coalesce(p_parametros, '{}'::jsonb) || jsonb_build_object('semente_demo', true),
           false, 256, 60,
           now() + interval '100 years',            -- nem por acidente sai da fila entre o INSERT e o UPDATE
           now() - (g || ' seconds')::interval
    FROM generate_series(1, p_quantos) AS g
    RETURNING id)
  SELECT array_agg(id) INTO ids FROM novos;

  -- 2.2 transição para o estado final pelo MESMO caminho do worker (a 006 exige o GUC plat.via_worker, cujas
  -- funções plat_app não pode executar; aqui vale porque esta função é SECURITY DEFINER)
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET estado = p_estado,
                      progresso = CASE WHEN p_estado = 'concluido' THEN 100 ELSE progresso END,
                      tentativa = 1,
                      worker = 'semente_demo',
                      agendado_para = now() - interval '2 minutes',
                      iniciado_em = now() - interval '2 minutes',
                      terminado_em = now() - interval '1 minute',
                      resultado = CASE WHEN p_estado = 'concluido' THEN jsonb_build_object('semente_demo', true) END,
                      erro = CASE WHEN p_estado <> 'concluido' THEN 'semente de demonstração' END,
                      proveniencia = jsonb_build_object('semente_demo', true, 'em', now())
  WHERE id = ANY(ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM plat.via_worker_desligar();
  RETURN n;
END $$;


--
-- Name: ldap_importar_lote(integer, jsonb, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.ldap_importar_lote(p_tenant_id integer, p_usuarios jsonb, p_perfil text) RETURNS TABLE(criados integer, ja_existentes integer, recusados integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE u jsonb; n_criados int := 0; n_existentes int := 0; n_recusados int := 0; existente record;
BEGIN
  FOR u IN SELECT * FROM jsonb_array_elements(p_usuarios) LOOP
    SELECT id, origem INTO existente FROM plat.usuario
      WHERE tenant_id = p_tenant_id AND login = lower(u->>'login');
    IF existente.id IS NOT NULL AND existente.origem <> 'ldap' THEN
      n_recusados := n_recusados + 1;
    ELSIF existente.id IS NOT NULL THEN
      n_existentes := n_existentes + 1;
    ELSE
      INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
      VALUES (p_tenant_id, lower(u->>'login'), u->>'nome', u->>'email', p_perfil, 'ldap', u->>'sujeito_externo',
              false, NULL);
      n_criados := n_criados + 1;
    END IF;
  END LOOP;
  RETURN QUERY SELECT n_criados, n_existentes, n_recusados;
END $$;


--
-- Name: ldap_provisionar(integer, text, text, text, text, text, boolean); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.ldap_provisionar(p_tenant_id integer, p_login text, p_nome text, p_email text, p_perfil text, p_sujeito_externo text, p_ativo boolean DEFAULT true) RETURNS TABLE(criado boolean, perfil_anterior text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE existente record; por_login record; v_login text := lower(p_login);
BEGIN
  IF p_sujeito_externo IS NULL OR btrim(p_sujeito_externo) = '' THEN
    RAISE EXCEPTION 'sujeito_externo_ausente';
  END IF;
  -- a identidade é o DN, não o login: quem já tem este DN neste inquilino é esta pessoa
  SELECT u.id, u.origem, u.perfil, u.login INTO existente FROM plat.usuario u
    WHERE u.tenant_id = p_tenant_id AND u.origem = 'ldap' AND u.sujeito_externo = p_sujeito_externo;
  IF existente.id IS NULL THEN
    SELECT u.id, u.origem, u.perfil, u.login, u.sujeito_externo INTO por_login FROM plat.usuario u
      WHERE u.tenant_id = p_tenant_id AND u.login = v_login;
    IF por_login.id IS NOT NULL AND por_login.origem <> 'ldap' THEN
      RAISE EXCEPTION 'login_em_uso_local';
    END IF;
    IF por_login.id IS NOT NULL AND por_login.sujeito_externo IS DISTINCT FROM p_sujeito_externo THEN
      -- mesmo login, OUTRO DN: nunca sequestra a linha existente nem estoura índice único
      RAISE EXCEPTION 'login_em_uso_externo';
    END IF;
    existente := por_login;
  END IF;
  IF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (p_tenant_id, v_login, p_nome, p_email, p_perfil, 'ldap', p_sujeito_externo, p_ativo, NULL);
    RETURN QUERY SELECT true, NULL::text;
  ELSE
    -- o login local acompanha o diretório, a menos que o novo login já seja de OUTRA linha do inquilino
    IF v_login IS DISTINCT FROM existente.login
       AND EXISTS (SELECT 1 FROM plat.usuario u WHERE u.tenant_id = p_tenant_id AND u.login = v_login
                     AND u.id <> existente.id) THEN
      RAISE EXCEPTION 'login_em_uso_externo';
    END IF;
    UPDATE plat.usuario u SET login = v_login, nome = p_nome, email = coalesce(p_email, u.email),
      perfil = p_perfil, sujeito_externo = p_sujeito_externo, ativo = p_ativo
    WHERE u.id = existente.id;
    RETURN QUERY SELECT false, existente.perfil;
  END IF;
END $$;


--
-- Name: link_resolver(text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.link_resolver(p_hash text, p_ip text) RETURNS TABLE(motivo text, tenant_id integer, item_id uuid, itens_incluidos uuid[], permite_download boolean, link_id uuid)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE l plat.compartilhamento_link; inc uuid[];
BEGIN
  SELECT * INTO l FROM plat.compartilhamento_link k WHERE k.token_hash = p_hash;
  IF l.id IS NULL THEN RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, NULL::uuid; RETURN; END IF;
  IF l.revogado_em IS NOT NULL THEN RETURN QUERY SELECT 'revogado', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, l.id; RETURN; END IF;
  IF l.expira_em IS NOT NULL AND l.expira_em <= now() THEN RETURN QUERY SELECT 'expirado', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, l.id; RETURN; END IF;
  IF EXISTS (SELECT 1 FROM plat.item i JOIN plat.tenant t ON t.id = i.tenant_id WHERE i.id = l.item_id AND (i.apagado_em IS NOT NULL OR NOT t.ativo)) THEN
    RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, l.id; RETURN;
  END IF;
  UPDATE plat.compartilhamento_link SET acessos = acessos + 1, ultimo_acesso_em = now(), ultimo_ip = p_ip WHERE id = l.id;
  SELECT coalesce(array_agg(li.item_id), '{}'::uuid[]) INTO inc FROM plat.compartilhamento_link_item li
    JOIN plat.item i ON i.id = li.item_id AND i.apagado_em IS NULL WHERE li.link_id = l.id;
  RETURN QUERY SELECT 'ok', l.tenant_id, l.item_id, ARRAY[l.item_id] || inc, l.permite_download, l.id;
END $$;


--
-- Name: lixeira_expurgar(integer, timestamp with time zone, uuid[]); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.lixeira_expurgar(p_dias integer DEFAULT 30, p_agora timestamp with time zone DEFAULT now(), p_ids uuid[] DEFAULT NULL::uuid[]) RETURNS TABLE(item_id uuid, tenant_id integer, tipo text, dados jsonb, miniatura_chave text, tamanho_bytes bigint, titulo text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY
    SELECT i.id, i.tenant_id, i.tipo, i.dados, i.miniatura_chave, i.tamanho_bytes, i.titulo
    FROM plat.item i
    WHERE i.apagado_em IS NOT NULL AND i.apagado_em < p_agora - make_interval(days => p_dias)
      AND (t_plataforma OR i.tenant_id = t_ctx)
      AND (p_ids IS NULL OR i.id = ANY (p_ids))
    ORDER BY i.apagado_em;
END $$;


--
-- Name: log_expurgar(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.log_expurgar(p_meses integer DEFAULT 12) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE r record; n int := 0; limite date;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  limite := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
  IF limite >= date_trunc('month', now())::date THEN
    RAISE EXCEPTION 'limite_no_presente' USING HINT = 'o expurgo nunca alcança a partição do mês corrente';
  END IF;
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.log_acesso'::regclass LOOP
    IF (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $_$;


--
-- Name: log_expurgar_inquilino(integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.log_expurgar_inquilino(p_tenant_id integer, p_meses integer DEFAULT 12) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int; limite timestamptz;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  IF p_tenant_id IS NULL OR NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant_id) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  limite := date_trunc('month', now()) - make_interval(months => p_meses);
  DELETE FROM plat.log_acesso WHERE tenant_id = p_tenant_id AND em < limite;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;


--
-- Name: log_particao_garantir(date); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.log_particao_garantir(p_mes date) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
  fim := (ini + interval '1 month')::date;
  nome := format('log_acesso_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.log_acesso FOR VALUES FROM (%L) TO (%L)', nome, ini, fim);
    EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
    EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', nome, nome);
  END IF;
  RETURN nome;
END $$;


--
-- Name: log_registrar(integer, integer, integer, text, text, text, integer, bigint, integer, text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.log_registrar(p_tenant integer, p_usuario integer, p_token integer, p_ip text, p_metodo text, p_rota text, p_status integer, p_bytes bigint, p_tempo_ms integer, p_agente text, p_resultado text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF p_tenant IS NOT NULL AND plat.tenant_atual() IS NOT NULL AND p_tenant <> plat.tenant_atual() THEN
    RAISE EXCEPTION 'contexto_de_outro_inquilino';
  END IF;
  BEGIN
    INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente, resultado)
    VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
            p_tempo_ms, left(p_agente, 200), p_resultado);
  EXCEPTION WHEN check_violation THEN
    PERFORM plat.log_particao_garantir(now()::date);
    INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente, resultado)
    VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
            p_tempo_ms, left(p_agente, 200), p_resultado);
  END;
END $$;


--
-- Name: manutencao_analyze(text[]); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.manutencao_analyze(p_tabelas text[] DEFAULT ARRAY['job'::text, 'job_log'::text, 'item'::text, 'item_versao'::text, 'agenda'::text, 'usuario'::text, 'evento'::text]) RETURNS text[]
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE t text; feitas text[] := '{}';
BEGIN
  FOREACH t IN ARRAY coalesce(p_tabelas, '{}') LOOP
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'plat' AND tablename = t) THEN
      EXECUTE format('ANALYZE plat.%I', t);
      feitas := array_append(feitas, t);
    END IF;
  END LOOP;
  RETURN feitas;
END $$;


--
-- Name: modo_superadmin(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.modo_superadmin() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT current_setting('plat.superadmin', true) = 'on' AND plat.eh_superadmin()
$$;


--
-- Name: plataforma_operador(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.plataforma_operador(p_sessao_hash text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE uid int;
BEGIN
  SELECT u.id INTO uid
  FROM plat.sessao s JOIN plat.usuario u ON u.id = s.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE s.token_hash = p_sessao_hash AND u.superadmin AND u.ativo AND t.slug = 'plataforma'
    AND s.expira_em > now() AND coalesce(s.ultimo_uso, s.criado_em) >= now() - interval '24 hours';
  IF uid IS NULL THEN RAISE EXCEPTION 'so_superadmin'; END IF;
  RETURN uid;
END $$;


--
-- Name: plataforma_tenant_id(text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.plataforma_tenant_id(p_sessao_hash text, p_slug text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE tid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT id INTO tid FROM plat.tenant WHERE slug = p_slug;
  IF tid IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  RETURN tid;
END $$;


--
-- Name: pode_editar(uuid); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.pode_editar(p_item uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT plat.usuario_atual() IS NOT NULL AND plat.usuario_do_inquilino() AND EXISTS (
    SELECT 1 FROM plat.item i
    WHERE i.id = p_item AND i.tenant_id = plat.tenant_atual()
      AND (i.dono_id = plat.usuario_atual()
        OR plat.tem('conteudo.editar_tudo')
        OR EXISTS (SELECT 1 FROM plat.item_grupo ig JOIN plat.grupo g ON g.id = ig.grupo_id AND g.atualizacao_compartilhada
                   JOIN plat.grupo_membro gm ON gm.grupo_id = g.id AND gm.usuario_id = plat.usuario_atual() AND gm.estado = 'ativo'
                   WHERE ig.item_id = i.id)))
$$;


--
-- Name: pode_ler(uuid); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.pode_ler(p_item uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT EXISTS (
    SELECT 1 FROM plat.item i
    WHERE i.id = p_item
      AND i.tenant_id = plat.tenant_atual()
      AND (i.apagado_em IS NULL OR current_setting('plat.lixeira', true) = 'on')
      AND (
           -- link anônimo: só os itens listados no link desta requisição
           (plat.usuario_atual() IS NULL AND i.id::text = ANY (string_to_array(current_setting('plat.link_itens', true), ',')))
        OR -- público (anônimo ou autenticado), só com o inquilino autorizando
           (i.acesso = 'publico' AND plat.tenant_permite_publico(i.tenant_id))
        OR -- console do superadmin (variável + usuário superadmin real)
           plat.modo_superadmin()
        OR -- usuário autenticado DO inquilino
           (plat.usuario_do_inquilino() AND (
                i.dono_id = plat.usuario_atual()
             OR plat.tem('conteudo.ver_tudo')
             OR (i.acesso = 'inquilino' AND plat.tem('conteudo.ver_inquilino'))
             OR EXISTS (SELECT 1 FROM plat.item_grupo ig JOIN plat.grupo_membro gm
                          ON gm.grupo_id = ig.grupo_id AND gm.usuario_id = plat.usuario_atual() AND gm.estado = 'ativo'
                        WHERE ig.item_id = i.id)))
      )
  )
$$;


--
-- Name: privilegios_de(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.privilegios_de(p_usuario integer) RETURNS text[]
    LANGUAGE sql STABLE
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT coalesce(array_agg(pp.privilegio ORDER BY pp.privilegio), '{}'::text[])
  FROM plat.usuario u
  JOIN plat.perfil_privilegio pp ON pp.perfil = u.perfil
  WHERE u.id = p_usuario
    AND (u.papel_id IS NULL
         OR EXISTS (SELECT 1 FROM plat.papel_privilegio x WHERE x.papel_id = u.papel_id AND x.privilegio = pp.privilegio))
$$;


--
-- Name: provedor_ldap_de(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.provedor_ldap_de(p_tenant text) RETURNS TABLE(tenant_id integer, tenant_ativo boolean, tenant_slug text, tenant_nome text, config jsonb, habilitado boolean, url text, base_dn text, start_tls boolean, bind_dn text, bind_senha_cifrada text, filtro_usuario text, atributo_grupos text, perfil_padrao text, mapa_grupo_perfil jsonb)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  -- config vai junto (mesmo bloco tenant.config.auth do login local) para o bloqueio de força bruta desta
  -- rota usar OS MESMOS bloqueio_tentativas/bloqueio_minutos do inquilino, nunca um limiar hardcoded à parte
  SELECT t.id, t.ativo, t.slug, t.nome, t.config, pl.habilitado, pl.url, pl.base_dn, pl.start_tls, pl.bind_dn,
         pl.bind_senha_cifrada, pl.filtro_usuario, pl.atributo_grupos, pl.perfil_padrao, pl.mapa_grupo_perfil
  FROM plat.tenant t LEFT JOIN plat.provedor_ldap pl ON pl.tenant_id = t.id
  WHERE t.slug = p_tenant
$$;


--
-- Name: redefinicao_contexto(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.redefinicao_contexto(p_token_hash text) RETURNS TABLE(motivo text, tenant_id integer, usuario_id integer, login text, tenant_slug text, tenant_nome text, config jsonb)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT
    CASE
      WHEN r.id IS NULL THEN 'invalido'
      WHEN r.usado_em IS NOT NULL THEN 'usado'
      WHEN r.expira_em <= now() THEN 'expirado'
      WHEN NOT coalesce(t.ativo, false) OR NOT coalesce(u.ativo, false) THEN 'inquilino_suspenso'
      ELSE 'ok'
    END,
    r.tenant_id, r.usuario_id, u.login, t.slug, t.nome, t.config
  FROM (SELECT 1) uma
  LEFT JOIN plat.redefinicao_senha r ON r.token_hash = p_token_hash
  LEFT JOIN plat.usuario u ON u.id = r.usuario_id
  LEFT JOIN plat.tenant t ON t.id = r.tenant_id
$$;


--
-- Name: redefinicao_marcar_usada(text, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.redefinicao_marcar_usada(p_token_hash text, p_usuario_id integer) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE r plat.redefinicao_senha%ROWTYPE;
BEGIN
  SELECT * INTO r FROM plat.redefinicao_senha WHERE token_hash = p_token_hash AND usuario_id = p_usuario_id FOR UPDATE;
  IF r.id IS NULL OR r.usado_em IS NOT NULL OR r.expira_em <= now() THEN
    RETURN false;
  END IF;
  UPDATE plat.redefinicao_senha SET usado_em = now() WHERE id = r.id;
  RETURN true;
END $$;


--
-- Name: redefinicao_resolver(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.redefinicao_resolver(p_token_hash text) RETURNS TABLE(motivo text, login text, tenant_nome text)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT
    CASE
      WHEN r.id IS NULL THEN 'invalido'
      WHEN r.usado_em IS NOT NULL THEN 'usado'
      WHEN r.expira_em <= now() THEN 'expirado'
      ELSE 'ok'
    END,
    u.login, t.nome
  FROM (SELECT 1) uma
  LEFT JOIN plat.redefinicao_senha r ON r.token_hash = p_token_hash
  LEFT JOIN plat.usuario u ON u.id = r.usuario_id
  LEFT JOIN plat.tenant t ON t.id = r.tenant_id
$$;


--
-- Name: redefinicao_solicitar(text, text, text, integer, integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.redefinicao_solicitar(p_slug text, p_email text, p_ip text, p_janela_min integer, p_max_janela integer, p_horas_validade integer) RETURNS TABLE(permitido boolean, tenant_id integer, usuario_id integer, login text, tenant_nome text, token text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE v_chave text; n int; u RECORD; tok text;
BEGIN
  v_chave := lower(trim(p_slug)) || '|' || lower(trim(p_email));
  SELECT count(*) INTO n FROM plat.redefinicao_pedido rp
    WHERE rp.chave = v_chave AND rp.criado_em > now() - make_interval(mins => p_janela_min);
  IF n >= p_max_janela THEN
    RETURN QUERY SELECT false, NULL::int, NULL::int, NULL::text, NULL::text, NULL::text; RETURN;
  END IF;
  INSERT INTO plat.redefinicao_pedido(chave, ip) VALUES (v_chave, p_ip);
  SELECT u2.id, u2.tenant_id, u2.login, t2.nome AS tenant_nome INTO u
    FROM plat.usuario u2 JOIN plat.tenant t2 ON t2.id = u2.tenant_id
    WHERE t2.slug = lower(trim(p_slug)) AND u2.email IS NOT NULL AND lower(u2.email) = lower(trim(p_email))
      AND u2.ativo AND t2.ativo AND u2.origem = 'local'
    ORDER BY u2.id LIMIT 1;
  IF u.id IS NULL THEN
    RETURN QUERY SELECT true, NULL::int, NULL::int, NULL::text, NULL::text, NULL::text; RETURN;
  END IF;
  tok := encode(gen_random_bytes(32), 'hex');
  INSERT INTO plat.redefinicao_senha(tenant_id, usuario_id, token_hash, expira_em, ip)
  VALUES (u.tenant_id, u.id, encode(sha256(convert_to(tok, 'UTF8')), 'hex'),
          now() + make_interval(hours => p_horas_validade), p_ip);
  RETURN QUERY SELECT true, u.tenant_id, u.id, u.login, u.tenant_nome, tok;
END $$;


--
-- Name: req_guc(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.req_guc(p_nome text) RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('plat.' || p_nome, true), '') $$;


--
-- Name: semente_demo_habilitada(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.semente_demo_habilitada() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce((SELECT semear_demo FROM plat.ambiente WHERE unico), false) $$;


--
-- Name: sessoes_encerrar_usuario(integer, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.sessoes_encerrar_usuario(p_usuario integer, p_exceto_hash text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int;
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  DELETE FROM plat.sessao WHERE usuario_id = p_usuario AND (p_exceto_hash IS NULL OR token_hash <> p_exceto_hash);
  GET DIAGNOSTICS n = ROW_COUNT;
  UPDATE plat.usuario SET desafio_2fa_hash = NULL, desafio_2fa_ate = NULL WHERE id = p_usuario;
  RETURN n;
END $$;


--
-- Name: sessoes_expurgar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.sessoes_expurgar() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int; m int;
BEGIN
  DELETE FROM plat.sessao s
  USING plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE u.id = s.usuario_id
    AND (s.expira_em < now()
         OR coalesce(s.ultimo_uso, s.criado_em) < now() - make_interval(secs => 3600 * (
              CASE WHEN nullif(t.config #>> '{auth,sessao_ociosa_horas}', '') IS NULL THEN 12
                   ELSE least(greatest((t.config #>> '{auth,sessao_ociosa_horas}')::numeric, 1), 24) END)));
  GET DIAGNOSTICS n = ROW_COUNT;
  -- sessão órfã (usuário apagado sem cascata, ou linha sem dono): some pelo teto absoluto de 24 h, que é o
  -- maior valor que a política aceita — sem inquilino não há política a consultar
  DELETE FROM plat.sessao s
  WHERE NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = s.usuario_id)
    AND (s.expira_em < now() OR coalesce(s.ultimo_uso, s.criado_em) < now() - interval '24 hours');
  GET DIAGNOSTICS m = ROW_COUNT;
  n := n + m;
  UPDATE plat.usuario SET desafio_2fa_hash = NULL, desafio_2fa_ate = NULL
  WHERE desafio_2fa_ate IS NOT NULL AND desafio_2fa_ate < now();
  RETURN n;
END $$;


--
-- Name: tem(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tem(p_privilegio text) RETURNS boolean
    LANGUAGE sql STABLE
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT p_privilegio = ANY (plat.privilegios_de(plat.usuario_atual()))
$$;


--
-- Name: tenant_apagar(text, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_apagar(p_sessao_hash text, p_id integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN plat.tenant_apagar_interno(p_id);
END $$;


--
-- Name: tenant_apagar_interno(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_apagar_interno(p_id integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE s text; r record; passo int; restantes int; apagadas int := 0;
BEGIN
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' THEN RAISE EXCEPTION 'plataforma_nao_apaga'; END IF;
  -- o gatilho do último admin recusaria apagar o admin do inquilino que está sendo apagado: desligado só aqui, na
  -- mesma transação (DDL transacional: volta sozinho se algo falhar). Nunca por GUC, que plat_app poderia forjar.
  ALTER TABLE plat.usuario DISABLE TRIGGER usuario_ultimo_admin;
  -- referências que apontam para usuários do inquilino a partir de colunas sem cascata
  UPDATE plat.usuario SET papel_id = NULL WHERE tenant_id = p_id;
  UPDATE plat.token_servico SET renovado_por = NULL WHERE tenant_id = p_id;
  -- toda tabela do schema com tenant_id (inclusive as de outras linhas, como job/agenda), em passes até a ordem de
  -- FK fechar; partições ficam de fora (o pai apaga)
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
  ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
  RETURN p_id;
END $_$;


--
-- Name: tenant_atual(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_atual() RETURNS integer
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('plat.tenant_id', true), '')::int $$;


--
-- Name: tenant_cota_guarda(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_cota_guarda() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE pedido_usuarios int;
BEGIN
  IF (NEW.cota_bytes_teto IS DISTINCT FROM OLD.cota_bytes_teto
      OR NEW.cota_usuarios_teto IS DISTINCT FROM OLD.cota_usuarios_teto)
     AND coalesce(current_setting('plat.teto_definir', true), '') <> 'on' THEN
    RAISE EXCEPTION 'teto_e_da_plataforma'
      USING HINT = 'cota_bytes_teto/cota_usuarios_teto só mudam por plat.tenant_cotas_teto_definir';
  END IF;
  IF NEW.cota_bytes > NEW.cota_bytes_teto THEN
    RAISE EXCEPTION 'cota_acima_do_teto'
      USING HINT = format('cota_bytes %s acima do teto %s', NEW.cota_bytes, NEW.cota_bytes_teto);
  END IF;
  pedido_usuarios := CASE WHEN (NEW.config->>'cota_usuarios') ~ '^[0-9]+$'
                          THEN (NEW.config->>'cota_usuarios')::int ELSE NULL END;
  IF pedido_usuarios IS NOT NULL AND pedido_usuarios > NEW.cota_usuarios_teto THEN
    RAISE EXCEPTION 'cota_acima_do_teto'
      USING HINT = format('cota_usuarios %s acima do teto %s', pedido_usuarios, NEW.cota_usuarios_teto);
  END IF;
  RETURN NEW;
END $_$;


--
-- Name: tenant_cotas(text, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_cotas(p_sessao_hash text, p_id integer) RETURNS TABLE(id integer, slug text, cota_bytes bigint, cota_bytes_teto bigint, cota_usuarios integer, cota_usuarios_teto integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT t.id, t.slug, t.cota_bytes, t.cota_bytes_teto,
           least(coalesce((t.config->>'cota_usuarios')::int, 2000), t.cota_usuarios_teto), t.cota_usuarios_teto
      FROM plat.tenant t WHERE t.id = p_id;
END $$;


--
-- Name: tenant_cotas_teto_definir(text, integer, bigint, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_cotas_teto_definir(p_sessao_hash text, p_id integer, p_cota_bytes_teto bigint, p_cota_usuarios_teto integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $_$
DECLARE bytes_abs bigint := 1099511627776;  -- 1 TiB
        usuarios_abs int := 100000;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_cota_bytes_teto IS NULL OR p_cota_bytes_teto < 104857600 OR p_cota_bytes_teto > bytes_abs THEN
    RAISE EXCEPTION 'teto_fora_do_intervalo' USING HINT = format('cota_bytes_teto entre 104857600 e %s', bytes_abs);
  END IF;
  IF p_cota_usuarios_teto IS NULL OR p_cota_usuarios_teto < 1 OR p_cota_usuarios_teto > usuarios_abs THEN
    RAISE EXCEPTION 'teto_fora_do_intervalo' USING HINT = format('cota_usuarios_teto entre 1 e %s', usuarios_abs);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_id) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  PERFORM set_config('plat.teto_definir', 'on', true);
  UPDATE plat.tenant SET cota_bytes_teto = p_cota_bytes_teto, cota_usuarios_teto = p_cota_usuarios_teto,
         cota_bytes = least(cota_bytes, p_cota_bytes_teto),
         config = CASE WHEN (config->>'cota_usuarios') ~ '^[0-9]+$'
                            AND (config->>'cota_usuarios')::int > p_cota_usuarios_teto
                       THEN config || jsonb_build_object('cota_usuarios', p_cota_usuarios_teto)
                       ELSE config END
   WHERE id = p_id;
  PERFORM set_config('plat.teto_definir', 'off', true);
END $_$;


--
-- Name: tenant_criar(text, text, text, jsonb, text, text, text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb, p_admin_login text, p_admin_nome text, p_senha_hash text) RETURNS TABLE(tenant_id integer, usuario_id integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE tid int; uid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_slug IN ('plataforma','plat','public','admin','api','static','svc','ogc','tiles','saude','entrar','conta') THEN
    RAISE EXCEPTION 'slug_reservado';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config) VALUES (p_slug, p_nome, coalesce(p_config, '{}'::jsonb)) RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, trocar_senha)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin', true) RETURNING id INTO uid;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);  -- item L0-04
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
  RETURN QUERY SELECT tid, uid;
END $$;


--
-- Name: tenant_listar(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_listar(p_sessao_hash text) RETURNS TABLE(id integer, slug text, nome text, ativo boolean, usuarios bigint, criado_em timestamp with time zone, ultimo_acesso timestamp with time zone)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT t.id, t.slug, t.nome, t.ativo, count(u.id), t.criado_em, max(u.ultimo_login)
    FROM plat.tenant t LEFT JOIN plat.usuario u ON u.tenant_id = t.id
    GROUP BY t.id ORDER BY t.slug;
END $$;


--
-- Name: tenant_permite_publico(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_permite_publico(p_tenant integer) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT coalesce((config->'auth'->>'compartilhar_publico')::boolean, false) FROM plat.tenant WHERE id = p_tenant
$$;


--
-- Name: tenant_publico(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_publico(p_slug text) RETURNS TABLE(id integer, slug text, nome text, ativo boolean)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT t.id, t.slug, t.nome, t.ativo FROM plat.tenant t WHERE t.slug = p_slug
$$;


--
-- Name: tenant_publico_itens(uuid); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_publico_itens(p_item uuid) RETURNS TABLE(id integer)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT t.id FROM plat.item i JOIN plat.tenant t ON t.id = i.tenant_id
  WHERE i.id = p_item AND i.acesso = 'publico' AND i.apagado_em IS NULL AND t.ativo AND plat.tenant_permite_publico(t.id)
$$;


--
-- Name: tenant_suspender(text, integer, boolean); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tenant_suspender(p_sessao_hash text, p_id integer, p_ativo boolean) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE s text;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' AND NOT p_ativo THEN RAISE EXCEPTION 'plataforma_nao_suspende'; END IF;
  UPDATE plat.tenant SET ativo = p_ativo WHERE id = p_id;
END $$;


--
-- Name: tg_auditoria_imutavel(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_auditoria_imutavel() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE dono text;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO dono FROM pg_class c WHERE c.oid = 'plat.auditoria'::regclass;
  IF coalesce(current_setting('plat.auditoria_expurgo', true), '') = '1' AND current_user = dono THEN
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  RAISE EXCEPTION 'auditoria_imutavel'
    USING HINT = 'plat.auditoria é append-only: só plat.auditoria_expurgar(), como dono da tabela, remove linha';
END $$;


--
-- Name: tg_auditoria_sem_truncate(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_auditoria_sem_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  RAISE EXCEPTION 'auditoria_imutavel' USING HINT = 'TRUNCATE em plat.auditoria é proibido';
END $$;


--
-- Name: tg_categoria(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_categoria() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE pai plat.categoria; n int;
BEGIN
  IF NEW.pai_id IS NULL THEN
    NEW.nivel := 1; NEW.caminho := NEW.nome;
  ELSE
    SELECT * INTO pai FROM plat.categoria WHERE id = NEW.pai_id;
    IF pai.id IS NULL OR pai.tenant_id <> NEW.tenant_id THEN RAISE EXCEPTION 'categoria_de_outro_inquilino'; END IF;
    IF NEW.id = pai.id OR pai.caminho LIKE '%' || NEW.nome || '/%' AND pai.id = NEW.id THEN RAISE EXCEPTION 'pasta_ciclo'; END IF;
    IF pai.nivel >= 3 THEN RAISE EXCEPTION 'nivel_maximo'; END IF;
    NEW.nivel := pai.nivel + 1; NEW.caminho := pai.caminho || '/' || NEW.nome;
  END IF;
  IF TG_OP = 'INSERT' THEN
    SELECT count(*) INTO n FROM plat.categoria WHERE tenant_id = NEW.tenant_id;
    IF n >= plat.categorias_max(NEW.tenant_id) THEN RAISE EXCEPTION 'limite_categorias'; END IF;
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.nome <> OLD.nome OR NEW.pai_id IS DISTINCT FROM OLD.pai_id) THEN
    UPDATE plat.categoria c SET caminho = NEW.caminho || substr(c.caminho, length(OLD.caminho) + 1),
                                nivel = c.nivel - OLD.nivel + NEW.nivel
     WHERE c.tenant_id = NEW.tenant_id AND c.caminho LIKE OLD.caminho || '/%';
  END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_conexao_atualizado_em(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_conexao_atualizado_em() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;


--
-- Name: tg_evento_auditoria(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_evento_auditoria() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE p jsonb := coalesce(NEW.propriedades, '{}'::jsonb);
BEGIN
  INSERT INTO plat.auditoria(em, tenant_id, ator_id, ator_login, token_id, acao, recurso_tipo, recurso_id,
                             antes, depois, req_id, ip, metodo, rota, origem)
  VALUES (NEW.em, NEW.tenant_id, NEW.ator_id,
          (SELECT u.login FROM plat.usuario u WHERE u.id = NEW.ator_id),
          plat.req_guc('token_id')::int,
          NEW.tipo, NEW.alvo_tipo, NEW.alvo_id,
          p -> 'antes',
          CASE WHEN p ? 'depois' THEN p -> 'depois'
               WHEN p = '{}'::jsonb THEN NULL
               WHEN p ? 'antes' THEN NULL
               ELSE p END,
          coalesce(NEW.req_id, plat.req_guc('req_id')),
          coalesce(NEW.ip, plat.req_guc('ip')),
          plat.req_guc('metodo'), plat.req_guc('rota'), 'evento');
  RETURN NULL;
END $$;


--
-- Name: tg_grupo_dono_coerente(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_grupo_dono_coerente() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.dono_id AND u.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'dono_de_outro_inquilino';
  END IF;
  UPDATE plat.grupo_membro SET papel = 'gerente'
  WHERE grupo_id = NEW.id AND papel = 'dono' AND usuario_id <> NEW.dono_id;
  INSERT INTO plat.grupo_membro(grupo_id, tenant_id, usuario_id, papel, estado)
  VALUES (NEW.id, NEW.tenant_id, NEW.dono_id, 'dono', 'ativo')
  ON CONFLICT (grupo_id, usuario_id) DO UPDATE SET papel = 'dono', estado = 'ativo';
  RETURN NEW;
END $$;


--
-- Name: tg_grupo_membro_coerente(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_grupo_membro_coerente() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.usuario_id AND u.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'usuario_de_outro_inquilino';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM plat.grupo g WHERE g.id = NEW.grupo_id AND g.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'grupo_de_outro_inquilino';
    END IF;
  END IF;
  IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.papel = 'dono'
     AND (TG_OP = 'DELETE' OR NEW.papel <> 'dono' OR NEW.estado <> 'ativo')
     AND EXISTS (SELECT 1 FROM plat.grupo g WHERE g.id = OLD.grupo_id AND g.dono_id = OLD.usuario_id) THEN
    RAISE EXCEPTION 'dono_nao_sai';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_item_antes(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_item_antes() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE mudou_corpo boolean; c uuid;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    -- 2.2 imutáveis
    IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id OR NEW.tipo <> OLD.tipo OR NEW.criado_em <> OLD.criado_em
       OR (NEW.criado_por IS DISTINCT FROM OLD.criado_por AND NEW.criado_por IS NOT NULL)
       OR NEW.versao_atual <> OLD.versao_atual THEN
      RAISE EXCEPTION 'campo_imutavel';
    END IF;
    IF NEW.dono_id <> OLD.dono_id AND current_setting('plat.transferencia', true) IS DISTINCT FROM 'on' THEN
      RAISE EXCEPTION 'dono_so_por_transferencia';
    END IF;
    -- 9.2 proteção: exclusão lógica de item protegido só em modo superadmin (variável + usuário superadmin real)
    IF NEW.apagado_em IS NOT NULL AND OLD.apagado_em IS NULL AND OLD.protegido AND NOT plat.modo_superadmin() THEN
      RAISE EXCEPTION 'item_protegido';
    END IF;
  END IF;
  -- 2.2 coerência de inquilino
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.dono_id AND u.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'usuario_de_outro_inquilino';
  END IF;
  IF NEW.pasta_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM plat.pasta p WHERE p.id = NEW.pasta_id AND p.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'pasta_de_outro_inquilino';
  END IF;
  FOREACH c IN ARRAY NEW.categorias LOOP
    IF NOT EXISTS (SELECT 1 FROM plat.categoria k WHERE k.id = c AND k.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'categoria_de_outro_inquilino';
    END IF;
  END LOOP;
  -- 9.3 autoritativo liga proteção; 6.1 público exige o inquilino autorizar
  IF NEW.status = 'autoritativo' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'autoritativo') THEN
    NEW.protegido := true;
  END IF;
  IF NEW.acesso = 'publico' AND (TG_OP = 'INSERT' OR OLD.acesso <> 'publico') AND NOT plat.tenant_permite_publico(NEW.tenant_id) THEN
    RAISE EXCEPTION 'publico_desligado';
  END IF;
  -- versão: só quando o retrato muda (2.2, seção 4); pontuação sempre recalculada
  mudou_corpo := TG_OP = 'INSERT' OR plat.item_retrato(NEW) <> plat.item_retrato(OLD);
  NEW.pontuacao := plat.item_pontuacao(NEW);
  IF mudou_corpo THEN
    NEW.versao_atual := CASE WHEN TG_OP = 'INSERT' THEN 1 ELSE OLD.versao_atual + 1 END;
  END IF;
  IF TG_OP = 'UPDATE' AND (mudou_corpo OR NEW.pasta_id IS DISTINCT FROM OLD.pasta_id OR NEW.acesso <> OLD.acesso
     OR NEW.status IS DISTINCT FROM OLD.status OR NEW.protegido <> OLD.protegido
     OR NEW.miniatura_chave IS DISTINCT FROM OLD.miniatura_chave OR NEW.dono_id <> OLD.dono_id) THEN
    NEW.modificado_em := now();
    NEW.modificado_por := coalesce(plat.usuario_atual(), NEW.modificado_por);
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.modificado_por := coalesce(NEW.modificado_por, plat.usuario_atual());
    NEW.criado_por := coalesce(NEW.criado_por, plat.usuario_atual());
  END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_item_grupo(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_item_grupo() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE g plat.grupo; n int; papel text;
BEGIN
  SELECT * INTO g FROM plat.grupo WHERE id = NEW.grupo_id;
  IF g.id IS NULL OR g.tenant_id <> NEW.tenant_id OR NEW.tenant_id IS DISTINCT FROM plat.tenant_atual() THEN
    RAISE EXCEPTION 'grupo_de_outro_inquilino';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.id = NEW.item_id AND i.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'relacao_com_outro_inquilino';
  END IF;
  -- só se compartilha com grupo em que o ator pode contribuir (ADR 0002 4.2), salvo grupos.gerir_todos
  IF TG_OP = 'INSERT' AND NOT plat.tem('grupos.gerir_todos') THEN
    SELECT m.papel INTO papel FROM plat.grupo_membro m WHERE m.grupo_id = g.id AND m.usuario_id = plat.usuario_atual() AND m.estado = 'ativo';
    IF papel IS NULL OR (g.contribuicao = 'dono_gerentes' AND papel NOT IN ('dono','gerente')) THEN
      RAISE EXCEPTION 'sem_contribuicao_no_grupo';
    END IF;
  END IF;
  IF NEW.destaque THEN
    SELECT count(*) INTO n FROM plat.item_grupo WHERE grupo_id = NEW.grupo_id AND destaque AND item_id <> NEW.item_id;
    IF n >= 24 THEN RAISE EXCEPTION 'limite_destaques'; END IF;
  END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_item_relacao(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_item_relacao() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE o plat.item; d plat.item; rt plat.relacao_tipo; fo text; fd text; caminho uuid[]; n int;
BEGIN
  SELECT * INTO o FROM plat.item WHERE id = NEW.origem;
  SELECT * INTO d FROM plat.item WHERE id = NEW.destino;
  IF o.id IS NULL OR d.id IS NULL OR o.tenant_id <> NEW.tenant_id OR d.tenant_id <> NEW.tenant_id
     OR NEW.tenant_id IS DISTINCT FROM plat.tenant_atual() OR o.apagado_em IS NOT NULL OR d.apagado_em IS NOT NULL THEN
    RAISE EXCEPTION 'relacao_com_outro_inquilino';
  END IF;
  SELECT * INTO rt FROM plat.relacao_tipo WHERE nome = NEW.tipo;
  SELECT familia INTO fo FROM plat.tipo_item WHERE nome = o.tipo;
  SELECT familia INTO fd FROM plat.tipo_item WHERE nome = d.tipo;
  IF NOT (fo = ANY (rt.origem_familias)) OR NOT (fd = ANY (rt.destino_familias)) THEN
    RAISE EXCEPTION 'relacao_familia_invalida';
  END IF;
  -- tetos (5.2)
  SELECT count(*) INTO n FROM plat.item_relacao WHERE origem = NEW.origem;
  IF n >= 5000 THEN RAISE EXCEPTION 'limite_relacoes'; END IF;
  SELECT count(*) INTO n FROM plat.item_relacao WHERE destino = NEW.destino;
  IF n >= 50000 THEN RAISE EXCEPTION 'limite_relacoes'; END IF;
  -- ciclo: NEW.destino já depende (direta ou indiretamente) de NEW.origem?
  WITH RECURSIVE dep AS (
    SELECT r.destino AS no, ARRAY[NEW.destino, r.destino] AS caminho, 1 AS nivel
      FROM plat.item_relacao r WHERE r.origem = NEW.destino
    UNION ALL
    SELECT r.destino, dep.caminho || r.destino, dep.nivel + 1
      FROM dep JOIN plat.item_relacao r ON r.origem = dep.no
     WHERE dep.nivel < 20 AND NOT r.destino = ANY (dep.caminho)
  )
  SELECT dep.caminho INTO caminho FROM dep WHERE dep.no = NEW.origem LIMIT 1;
  IF caminho IS NOT NULL THEN
    RAISE EXCEPTION 'relacao_ciclo' USING DETAIL = array_to_string(caminho, ',');
  END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_item_versao(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_item_versao() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE corpo jsonb;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.versao_atual = OLD.versao_atual THEN RETURN NULL; END IF;
  corpo := plat.item_retrato(NEW);
  INSERT INTO plat.item_versao(item_id, versao, tenant_id, corpo, sha256, autor_id, comentario, rotulo)
  VALUES (NEW.id, NEW.versao_atual, NEW.tenant_id, corpo, encode(digest(corpo::text, 'sha256'), 'hex'),
          plat.usuario_atual(), NULLIF(current_setting('plat.versao_comentario', true), ''),
          coalesce(NULLIF(current_setting('plat.versao_rotulo', true), ''), 'edicao'))
  ON CONFLICT (item_id, versao) DO NOTHING;
  RETURN NULL;
END $$;


--
-- Name: tg_pasta_caminho(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_pasta_caminho() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE pai plat.pasta;
BEGIN
  IF NEW.pai_id IS NULL THEN
    NEW.ancestrais := '{}'; NEW.profundidade := 0;
  ELSE
    SELECT * INTO pai FROM plat.pasta WHERE id = NEW.pai_id;
    IF pai.id IS NULL OR pai.tenant_id <> NEW.tenant_id THEN RAISE EXCEPTION 'pasta_de_outro_inquilino'; END IF;
    IF NEW.id = pai.id OR NEW.id = ANY (pai.ancestrais) THEN RAISE EXCEPTION 'pasta_ciclo'; END IF;
    IF pai.profundidade >= 4 THEN RAISE EXCEPTION 'pasta_profunda'; END IF;
    NEW.ancestrais := pai.ancestrais || pai.id; NEW.profundidade := pai.profundidade + 1;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.pai_id IS DISTINCT FROM OLD.pai_id THEN
    -- descendentes: recalcula o caminho; a mais funda não pode passar de 4
    IF EXISTS (SELECT 1 FROM plat.pasta d WHERE OLD.id = ANY (d.ancestrais)
               AND d.profundidade - OLD.profundidade + NEW.profundidade > 4) THEN
      RAISE EXCEPTION 'pasta_profunda';
    END IF;
    UPDATE plat.pasta d
       SET ancestrais = NEW.ancestrais || NEW.id || d.ancestrais[array_position(d.ancestrais, OLD.id) + 1:],
           profundidade = d.profundidade - OLD.profundidade + NEW.profundidade
     WHERE OLD.id = ANY (d.ancestrais);
  END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_pasta_vazia(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_pasta_vazia() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM plat.pasta WHERE pai_id = OLD.id)
     OR EXISTS (SELECT 1 FROM plat.item WHERE pasta_id = OLD.id AND apagado_em IS NULL) THEN
    RAISE EXCEPTION 'pasta_nao_vazia';
  END IF;
  RETURN OLD;
END $$;


--
-- Name: tg_usuario_superadmin(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_usuario_superadmin() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF NEW.superadmin AND NOT EXISTS (SELECT 1 FROM plat.tenant t WHERE t.id = NEW.tenant_id AND t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'superadmin_so_plataforma';
  END IF;
  RETURN NEW;
END $$;


--
-- Name: tg_usuario_ultimo_admin(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.tg_usuario_ultimo_admin() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
BEGIN
  IF OLD.perfil = 'admin' AND OLD.ativo
     AND (TG_OP = 'DELETE' OR NEW.perfil <> 'admin' OR NOT NEW.ativo) THEN
    IF NOT EXISTS (SELECT 1 FROM plat.usuario u
                   WHERE u.tenant_id = OLD.tenant_id AND u.id <> OLD.id AND u.perfil = 'admin' AND u.ativo) THEN
      RAISE EXCEPTION 'ultimo_admin' USING HINT = 'nomeie outro administrador antes';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;


--
-- Name: upload_reservado_bytes(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.upload_reservado_bytes(p_tenant_id integer) RETURNS bigint
    LANGUAGE sql STABLE
    AS $$
  SELECT coalesce(sum(bytes_declarado), 0)::bigint FROM plat.upload
  WHERE tenant_id = p_tenant_id AND estado = 'iniciado';
$$;


--
-- Name: uploads_expirar_candidatos(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.uploads_expirar_candidatos(p_horas integer) RETURNS TABLE(id uuid, tenant_id integer, usuario_id integer, upload_s3_id text)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT u.id, u.tenant_id, u.usuario_id, u.upload_s3_id
  FROM plat.upload u
  WHERE u.estado = 'iniciado' AND u.atualizado_em < now() - (p_horas || ' hours')::interval
  ORDER BY u.atualizado_em;
$$;


--
-- Name: usuario_atual(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.usuario_atual() RETURNS integer
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('plat.usuario_id', true), '')::int $$;


--
-- Name: usuario_do_inquilino(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.usuario_do_inquilino() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = plat.usuario_atual() AND u.tenant_id = plat.tenant_atual() AND u.ativo)
$$;


--
-- Name: usuarios_ativos(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.usuarios_ativos(p_tenant integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  SELECT count(*)::int FROM plat.usuario WHERE tenant_id = p_tenant AND ativo
$$;


--
-- Name: via_worker_desligar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.via_worker_desligar() RETURNS void
    LANGUAGE sql
    AS $$ SELECT set_config('plat.via_worker', '', true) $$;


--
-- Name: via_worker_ligar(); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.via_worker_ligar() RETURNS void
    LANGUAGE sql
    AS $$ SELECT set_config('plat.via_worker', 'sim', true) $$;


--
-- Name: worker_ceifar(integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.worker_ceifar(p_limite_s integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
DECLARE n int;
BEGIN
  DELETE FROM plat.worker WHERE heartbeat_em < now() - make_interval(secs => p_limite_s);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;


--
-- Name: worker_desregistrar(text); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.worker_desregistrar(p_nome text) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  DELETE FROM plat.worker WHERE nome = p_nome
$$;


--
-- Name: worker_heartbeat(text, integer, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.worker_heartbeat(p_nome text, p_rss_kb integer, p_rodando integer) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  UPDATE plat.worker SET heartbeat_em = now(), rss_kb = p_rss_kb, rodando = p_rodando WHERE nome = p_nome
$$;


--
-- Name: worker_registrar(text, integer, text, text, integer); Type: FUNCTION; Schema: plat; Owner: -
--

CREATE FUNCTION plat.worker_registrar(p_nome text, p_pid integer, p_versao text, p_git_sha text, p_processos integer) RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'plat', 'public'
    AS $$
  INSERT INTO plat.worker(nome, pid, versao, git_sha, processos) VALUES (p_nome, p_pid, p_versao, p_git_sha, p_processos)
  ON CONFLICT (nome) DO UPDATE SET pid = EXCLUDED.pid, versao = EXCLUDED.versao, git_sha = EXCLUDED.git_sha,
    processos = EXCLUDED.processos, iniciado_em = now(), heartbeat_em = now(), rodando = 0
$$;


--
-- Name: first_notnull(anyelement); Type: AGGREGATE; Schema: pgstac; Owner: -
--

CREATE AGGREGATE pgstac.first_notnull(anyelement) (
    SFUNC = pgstac.first_notnull_sfunc,
    STYPE = anyelement
);


--
-- Name: jsonb_array_unique_merge(jsonb); Type: AGGREGATE; Schema: pgstac; Owner: -
--

CREATE AGGREGATE pgstac.jsonb_array_unique_merge(jsonb) (
    SFUNC = pgstac.jsonb_concat_ignorenull,
    STYPE = jsonb,
    FINALFUNC = pgstac.jsonb_array_unique
);


--
-- Name: jsonb_max(jsonb); Type: AGGREGATE; Schema: pgstac; Owner: -
--

CREATE AGGREGATE pgstac.jsonb_max(jsonb) (
    SFUNC = pgstac.jsonb_greatest,
    STYPE = jsonb
);


--
-- Name: jsonb_min(jsonb); Type: AGGREGATE; Schema: pgstac; Owner: -
--

CREATE AGGREGATE pgstac.jsonb_min(jsonb) (
    SFUNC = pgstac.jsonb_least,
    STYPE = jsonb
);


--
-- Name: collections_asitems; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.collections_asitems AS
 SELECT id,
    geometry,
    'collections'::text AS collection,
    datetime,
    end_datetime,
    jsonb_build_object('properties', (content - '{links,assets,stac_version,stac_extensions}'::text), 'links', (content -> 'links'::text), 'assets', (content -> 'assets'::text), 'stac_version', (content -> 'stac_version'::text), 'stac_extensions', (content -> 'stac_extensions'::text)) AS content,
    content AS collectionjson
   FROM pgstac.collections;


--
-- Name: collections_key_seq; Type: SEQUENCE; Schema: pgstac; Owner: -
--

ALTER TABLE pgstac.collections ALTER COLUMN key ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME pgstac.collections_key_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: cql2_ops; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.cql2_ops (
    op text NOT NULL,
    template text,
    types text[]
);


--
-- Name: format_item_cache; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE UNLOGGED TABLE pgstac.format_item_cache (
    id text NOT NULL,
    collection text NOT NULL,
    fields text NOT NULL,
    hydrated boolean NOT NULL,
    output jsonb,
    lastused timestamp with time zone DEFAULT now(),
    usecount integer DEFAULT 1,
    timetoformat double precision
);


--
-- Name: items_staging; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE UNLOGGED TABLE pgstac.items_staging (
    content jsonb NOT NULL
);


--
-- Name: items_staging_ignore; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE UNLOGGED TABLE pgstac.items_staging_ignore (
    content jsonb NOT NULL
);


--
-- Name: items_staging_upsert; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE UNLOGGED TABLE pgstac.items_staging_upsert (
    content jsonb NOT NULL
);


--
-- Name: migrations; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.migrations (
    version text NOT NULL,
    datetime timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


--
-- Name: partition_stats; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.partition_stats (
    partition text NOT NULL,
    collection text,
    partition_dtrange tstzrange,
    dtrange tstzrange,
    edtrange tstzrange,
    spatial public.geometry,
    last_updated timestamp with time zone,
    keys text[]
)
WITH (fillfactor='90');


--
-- Name: partition_sys_meta; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.partition_sys_meta AS
 SELECT partition.partition,
    replace(replace(
        CASE
            WHEN (pg_partition_tree.level = 1) THEN partition_expr.partition_expr
            ELSE parent_partition_expr.parent_partition_expr
        END, 'FOR VALUES IN ('''::text, ''::text), ''')'::text, ''::text) AS collection,
    pg_partition_tree.level,
    c.reltuples,
    c.relhastriggers,
    partition_dtrange.partition_dtrange,
    COALESCE(pgstac.get_tstz_constraint(c.oid, 'datetime'::text), partition_dtrange.partition_dtrange, inf_range.inf_range) AS constraint_dtrange,
    COALESCE(pgstac.get_tstz_constraint(c.oid, 'end_datetime'::text), inf_range.inf_range) AS constraint_edtrange
   FROM (((((((pg_partition_tree('pgstac.items'::regclass) pg_partition_tree(relid, parentrelid, isleaf, level)
     JOIN pg_class c ON (((pg_partition_tree.relid)::oid = c.oid)))
     JOIN pg_class parent ON ((((pg_partition_tree.parentrelid)::oid = parent.oid) AND pg_partition_tree.isleaf)))
     JOIN LATERAL pgstac.get_partition_name(pg_partition_tree.relid) partition(partition) ON (true))
     JOIN LATERAL pg_get_expr(c.relpartbound, c.oid) partition_expr(partition_expr) ON (true))
     JOIN LATERAL pg_get_expr(parent.relpartbound, parent.oid) parent_partition_expr(parent_partition_expr) ON (true))
     JOIN LATERAL tstzrange('-infinity'::timestamp with time zone, 'infinity'::timestamp with time zone, '[]'::text) inf_range(inf_range) ON (true))
     JOIN LATERAL COALESCE(pgstac.constraint_tstzrange(pg_get_expr(c.relpartbound, c.oid)), inf_range.inf_range) partition_dtrange(partition_dtrange) ON (true))
  WHERE pg_partition_tree.isleaf;


--
-- Name: partitions_view; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.partitions_view AS
 SELECT sm.partition,
    sm.collection,
    sm.level,
    sm.reltuples,
    sm.relhastriggers,
    sm.partition_dtrange,
    sm.constraint_dtrange,
    sm.constraint_edtrange,
    ps.dtrange,
    ps.edtrange,
    ps.spatial,
    ps.last_updated
   FROM (pgstac.partition_sys_meta sm
     LEFT JOIN pgstac.partition_stats ps USING (partition));


--
-- Name: partitions; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.partitions AS
 SELECT partition,
    collection,
    level,
    reltuples,
    relhastriggers,
    partition_dtrange,
    constraint_dtrange,
    constraint_edtrange,
    dtrange,
    edtrange,
    spatial,
    last_updated
   FROM pgstac.partitions_view;


--
-- Name: pgstac_indexes; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.pgstac_indexes AS
 SELECT schemaname,
    tablename,
    indexname,
    regexp_replace(btrim(replace(replace(indexdef, (indexname)::text, ''::text), 'pgstac.'::text, ''::text), ' \t\n'::text), '[ ]+'::text, ' '::text, 'g'::text) AS idx,
    COALESCE((regexp_match(indexdef, '\(([a-zA-Z]+)\)'::text))[1], (regexp_match(indexdef, '\(content -> ''properties''::text\) -> ''([a-zA-Z0-9\:\_-]+)''::text'::text))[1],
        CASE
            WHEN (indexdef ~* '\(datetime desc, end_datetime\)'::text) THEN 'datetime'::text
            ELSE NULL::text
        END) AS field,
    pg_table_size(((indexname)::text)::regclass) AS index_size,
    pg_size_pretty(pg_table_size(((indexname)::text)::regclass)) AS index_size_pretty
   FROM pg_indexes i
  WHERE ((schemaname = 'pgstac'::name) AND (tablename ~ '_items_'::text) AND (indexdef !~* ' only '::text));


--
-- Name: pgstac_indexes_stats; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.pgstac_indexes_stats AS
 SELECT i.schemaname,
    i.tablename,
    i.indexname,
    i.indexdef,
    COALESCE((regexp_match(i.indexdef, '\(([a-zA-Z]+)\)'::text))[1], (regexp_match(i.indexdef, '\(content -> ''properties''::text\) -> ''([a-zA-Z0-9\:\_]+)''::text'::text))[1],
        CASE
            WHEN (i.indexdef ~* '\(datetime desc, end_datetime\)'::text) THEN 'datetime_end_datetime'::text
            ELSE NULL::text
        END) AS field,
    pg_table_size(((i.indexname)::text)::regclass) AS index_size,
    pg_size_pretty(pg_table_size(((i.indexname)::text)::regclass)) AS index_size_pretty,
    s.n_distinct,
    ((s.most_common_vals)::text)::text[] AS most_common_vals,
    ((s.most_common_freqs)::text)::text[] AS most_common_freqs,
    ((s.histogram_bounds)::text)::text[] AS histogram_bounds,
    s.correlation
   FROM (pg_indexes i
     LEFT JOIN pg_stats s ON ((s.tablename = i.indexname)))
  WHERE ((i.schemaname = 'pgstac'::name) AND (i.tablename ~ '_items_'::text));


--
-- Name: pgstac_settings; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.pgstac_settings (
    name text NOT NULL,
    value text NOT NULL
);


--
-- Name: query_queue; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.query_queue (
    query text NOT NULL,
    added timestamp with time zone DEFAULT now()
);


--
-- Name: query_queue_history; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.query_queue_history (
    query text,
    added timestamp with time zone NOT NULL,
    finished timestamp with time zone DEFAULT now() NOT NULL,
    error text
);


--
-- Name: queryables_id_seq; Type: SEQUENCE; Schema: pgstac; Owner: -
--

ALTER TABLE pgstac.queryables ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME pgstac.queryables_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: search_wheres_id_seq; Type: SEQUENCE; Schema: pgstac; Owner: -
--

ALTER TABLE pgstac.search_wheres ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME pgstac.search_wheres_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: stac_extensions; Type: TABLE; Schema: pgstac; Owner: -
--

CREATE TABLE pgstac.stac_extensions (
    url text NOT NULL,
    content jsonb
);


--
-- Name: stac_extension_queryables; Type: VIEW; Schema: pgstac; Owner: -
--

CREATE VIEW pgstac.stac_extension_queryables AS
 SELECT DISTINCT j.key AS name,
    pgstac.schema_qualify_refs(e.url, j.value) AS definition
   FROM pgstac.stac_extensions e,
    LATERAL jsonb_each((((e.content -> 'definitions'::text) -> 'fields'::text) -> 'properties'::text)) j(key, value);


--
-- Name: acervo_assinatura; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.acervo_assinatura (
    tenant_id integer NOT NULL,
    acervo_camada_id text NOT NULL,
    assinado_em timestamp with time zone DEFAULT now() NOT NULL,
    assinado_por integer
);


--
-- Name: acervo_camada; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.acervo_camada (
    acervo_camada_id text NOT NULL,
    fonte_id text NOT NULL,
    servidor text NOT NULL,
    banco text NOT NULL,
    schema_nome text NOT NULL,
    tabela text NOT NULL,
    coluna_geom text NOT NULL,
    srid integer NOT NULL,
    tipo_geom text NOT NULL,
    colunas_expostas text[] DEFAULT '{}'::text[] NOT NULL,
    colunas_bloqueadas text[] DEFAULT '{}'::text[] NOT NULL,
    linhas_exatas bigint,
    linhas_contadas_em date,
    linhas_estimadas bigint,
    sha256 text,
    comando_reexecucao text,
    estado text NOT NULL,
    motivo_bloqueio text,
    sincronizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acervo_camada_estado_check CHECK ((estado = ANY (ARRAY['exposta'::text, 'bloqueada'::text, 'pendente_de_licenca'::text])))
);


--
-- Name: acervo_camada_execucao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.acervo_camada_execucao (
    id bigint NOT NULL,
    iniciado_em timestamp with time zone NOT NULL,
    concluido_em timestamp with time zone NOT NULL,
    duracao_ms integer NOT NULL,
    candidatas integer NOT NULL,
    expostas integer NOT NULL,
    bloqueadas integer NOT NULL,
    pendentes integer NOT NULL,
    fantasmas integer NOT NULL,
    nao_concluidas integer NOT NULL
);


--
-- Name: acervo_camada_execucao_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

ALTER TABLE plat.acervo_camada_execucao ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME plat.acervo_camada_execucao_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: acervo_endpoint; Type: VIEW; Schema: plat; Owner: -
--

CREATE VIEW plat.acervo_endpoint WITH (security_invoker='true') AS
 SELECT e.fonte_id,
    e.url,
    e.origem,
    e.http,
    e.content_type,
    e.bytes,
    e.ms,
    e.testado_em,
    e.confirmado,
    (COALESCE(e.confirmado, false) AND (e.http = '200'::text)) AS vivo
   FROM (acervo.endpoint e
     JOIN acervo.fonte f ON ((f.fonte_id = e.fonte_id)))
  WHERE ((f.licenca IS NOT NULL) AND (btrim(f.licenca) <> ''::text));


--
-- Name: acervo_ficha; Type: VIEW; Schema: plat; Owner: -
--

CREATE VIEW plat.acervo_ficha WITH (security_invoker='true') AS
 SELECT f.fonte_id,
    f.nome,
    f.orgao,
    f.dominio,
    f.url,
    f.url_http,
    f.url_conferida_em,
    f.licenca,
    f.frescor,
    f.data_dado,
    f.data_acesso,
    f.script_gerador,
    f.sha256,
    f.sha256_cmd AS comando_reexecucao,
    f.metodo,
    f.confianca,
    f.limites,
    f.proxima_verificacao,
    f.tabelas AS numero_tabelas,
    f.linhas_est AS registros_estimados,
    f.bytes,
    v.campos AS procedencia_campos,
    v.campos_possiveis AS procedencia_campos_possiveis,
    round((((v.campos)::numeric / (NULLIF(v.campos_possiveis, 0))::numeric) * (10)::numeric), 1) AS procedencia_pontuacao,
    f.atualizado_em
   FROM (acervo.fonte f
     LEFT JOIN acervo.v_completude v ON ((v.fonte_id = f.fonte_id)))
  WHERE ((f.licenca IS NOT NULL) AND (btrim(f.licenca) <> ''::text));


--
-- Name: acervo_lgpd; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.acervo_lgpd (
    fonte_id text NOT NULL,
    risco_pii boolean NOT NULL,
    motivo text NOT NULL,
    decidido_por text NOT NULL,
    decidido_em timestamp with time zone DEFAULT now() NOT NULL,
    revisar_em date,
    CONSTRAINT acervo_lgpd_decidido_por_check CHECK ((btrim(decidido_por) <> ''::text)),
    CONSTRAINT acervo_lgpd_motivo_check CHECK ((btrim(motivo) <> ''::text))
);


--
-- Name: acervo_licenca; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.acervo_licenca (
    fonte_id text NOT NULL,
    tipo text NOT NULL,
    url_licenca text NOT NULL,
    metodo text NOT NULL,
    identificador_remoto text,
    http_status integer NOT NULL,
    evidencia text NOT NULL,
    confianca text NOT NULL,
    verificado_em timestamp with time zone NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acervo_licenca_confianca_check CHECK ((btrim(confianca) <> ''::text)),
    CONSTRAINT acervo_licenca_evidencia_check CHECK ((btrim(evidencia) <> ''::text)),
    CONSTRAINT acervo_licenca_metodo_check CHECK ((btrim(metodo) <> ''::text)),
    CONSTRAINT acervo_licenca_tipo_check CHECK ((tipo = ANY (ARRAY['CC0'::text, 'CC-BY'::text, 'CC-BY-SA'::text, 'ODbL'::text, 'dado-aberto-com-termo-do-orgao'::text, 'Copernicus'::text, 'licenca-propria'::text, 'nao-declarada'::text]))),
    CONSTRAINT acervo_licenca_url_licenca_check CHECK ((btrim(url_licenca) <> ''::text))
);


--
-- Name: TABLE acervo_licenca; Type: COMMENT; Schema: plat; Owner: -
--

COMMENT ON TABLE plat.acervo_licenca IS 'Licença curada e testada por HTTP real (item L6-01-g-licenca-curada). Cada linha exige uma verificação de rede bem-sucedida no momento da escrita (scripts/acervo_licenca_sync.py, roda como postgres); plat_app só lê.';


--
-- Name: acervo_publicacao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.acervo_publicacao (
    acervo_camada_id text NOT NULL,
    view_nome text NOT NULL,
    schema_origem text NOT NULL,
    tabela_origem text NOT NULL,
    coluna_geom text NOT NULL,
    srid integer NOT NULL,
    colunas text[] NOT NULL,
    security_invoker boolean NOT NULL,
    security_barrier boolean NOT NULL,
    publicado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ambiente; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.ambiente (
    unico boolean DEFAULT true NOT NULL,
    nome text NOT NULL,
    semear_demo boolean DEFAULT false NOT NULL,
    definido_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ambiente_nome_check CHECK ((nome = ANY (ARRAY['dev'::text, 'producao'::text]))),
    CONSTRAINT ambiente_unico_check CHECK (unico)
);


--
-- Name: amc_conjunto_unidade; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_conjunto_unidade (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    nome text NOT NULL,
    tipo text NOT NULL,
    lado_m double precision,
    srid_trabalho integer NOT NULL,
    area_estudo public.geometry(MultiPolygon,4326),
    estado text DEFAULT 'pendente'::text NOT NULL,
    job_id uuid,
    n_unidades integer,
    area_total_m2 double precision,
    ficha jsonb DEFAULT '{}'::jsonb NOT NULL,
    erro text,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    pronto_em timestamp with time zone,
    CONSTRAINT amc_conjunto_unidade_check CHECK (((tipo = 'feicoes'::text) OR ((lado_m IS NOT NULL) AND (area_estudo IS NOT NULL)))),
    CONSTRAINT amc_conjunto_unidade_estado_check CHECK ((estado = ANY (ARRAY['pendente'::text, 'pronto'::text, 'falhou'::text]))),
    CONSTRAINT amc_conjunto_unidade_lado_m_check CHECK (((lado_m IS NULL) OR (lado_m > (0)::double precision))),
    CONSTRAINT amc_conjunto_unidade_nome_check CHECK (((length(nome) >= 1) AND (length(nome) <= 250))),
    CONSTRAINT amc_conjunto_unidade_tipo_check CHECK ((tipo = ANY (ARRAY['hexagonal'::text, 'quadrada'::text, 'feicoes'::text])))
);


--
-- Name: amc_execucao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_execucao (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    modelo_id uuid NOT NULL,
    versao_hash text NOT NULL,
    conjunto_id uuid NOT NULL,
    pesos jsonb NOT NULL,
    camadas jsonb NOT NULL,
    motor_versao text NOT NULL,
    semente bigint NOT NULL,
    estado text DEFAULT 'registrada'::text NOT NULL,
    job_id uuid,
    erro text,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    iniciado_em timestamp with time zone,
    terminado_em timestamp with time zone,
    CONSTRAINT amc_execucao_estado_check CHECK ((estado = ANY (ARRAY['registrada'::text, 'extraindo'::text, 'concluida'::text, 'falhou'::text, 'cancelada'::text])))
);


--
-- Name: amc_fator_bruto; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_fator_bruto (
    execucao_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    unidade_id text NOT NULL,
    fator text NOT NULL,
    valor double precision,
    cobertura real,
    CONSTRAINT amc_fator_bruto_cobertura_check CHECK (((cobertura IS NULL) OR ((cobertura >= (0)::double precision) AND (cobertura <= (1)::double precision))))
);


--
-- Name: amc_modelo; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_modelo (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    nome text NOT NULL,
    versao_hash text NOT NULL,
    n_versoes integer DEFAULT 1 NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_por integer,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    apagado_em timestamp with time zone,
    CONSTRAINT amc_modelo_n_versoes_check CHECK ((n_versoes >= 1)),
    CONSTRAINT amc_modelo_nome_check CHECK (((length(nome) >= 1) AND (length(nome) <= 250))),
    CONSTRAINT amc_modelo_versao_hash_check CHECK ((versao_hash ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: amc_modelo_versao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_modelo_versao (
    modelo_id uuid NOT NULL,
    versao_hash text NOT NULL,
    tenant_id integer NOT NULL,
    numero integer NOT NULL,
    definicao jsonb NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT amc_modelo_versao_numero_check CHECK ((numero >= 1)),
    CONSTRAINT amc_modelo_versao_versao_hash_check CHECK ((versao_hash ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: amc_resultado; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_resultado (
    execucao_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    unidade_id text NOT NULL,
    favorabilidade double precision,
    vetado boolean DEFAULT false NOT NULL,
    motivo text,
    cobertura real,
    CONSTRAINT amc_resultado_check CHECK (((NOT vetado) OR ((favorabilidade IS NULL) AND (motivo IS NOT NULL)))),
    CONSTRAINT amc_resultado_cobertura_check CHECK (((cobertura IS NULL) OR ((cobertura >= (0)::double precision) AND (cobertura <= (1)::double precision)))),
    CONSTRAINT amc_resultado_favorabilidade_check CHECK (((favorabilidade IS NULL) OR ((favorabilidade >= (0)::double precision) AND (favorabilidade <= (100)::double precision))))
);


--
-- Name: amc_unidade; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.amc_unidade (
    conjunto_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    unidade_id text NOT NULL,
    geom public.geometry(MultiPolygon,4326) NOT NULL,
    area_m2 double precision NOT NULL,
    CONSTRAINT amc_unidade_area_m2_check CHECK ((area_m2 >= (0)::double precision)),
    CONSTRAINT amc_unidade_unidade_id_check CHECK (((length(unidade_id) >= 1) AND (length(unidade_id) <= 200)))
);


--
-- Name: arquivo; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.arquivo (
    id bigint NOT NULL,
    tenant_id integer NOT NULL,
    classe text NOT NULL,
    referencia text,
    sha256 text NOT NULL,
    bytes bigint NOT NULL,
    content_type text NOT NULL,
    chave text NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    apagado_em timestamp with time zone,
    CONSTRAINT arquivo_bytes_check CHECK ((bytes >= 0)),
    CONSTRAINT arquivo_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: arquivo_bucket; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.arquivo_bucket (
    tenant_id integer NOT NULL,
    bucket_id text NOT NULL,
    bucket_alias text NOT NULL,
    chave_rw_id text NOT NULL,
    chave_rw_segredo text NOT NULL,
    chave_ro_id text NOT NULL,
    chave_ro_segredo text NOT NULL,
    cota_bytes bigint NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    cota_objetos bigint DEFAULT 200000 NOT NULL,
    web_ativo boolean DEFAULT false NOT NULL
);


--
-- Name: arquivo_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.arquivo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: arquivo_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.arquivo_id_seq OWNED BY plat.arquivo.id;


--
-- Name: arquivo_upload; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.arquivo_upload (
    upload_id text NOT NULL,
    tenant_id integer NOT NULL,
    classe text NOT NULL,
    referencia text,
    content_type text NOT NULL,
    chave_temp text NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: auditoria; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.auditoria (
    id bigint NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer NOT NULL,
    ator_id integer,
    ator_login text,
    token_id integer,
    acao text NOT NULL,
    recurso_tipo text,
    recurso_id text,
    antes jsonb,
    depois jsonb,
    req_id text,
    ip text,
    metodo text,
    rota text,
    origem text DEFAULT 'evento'::text NOT NULL,
    CONSTRAINT auditoria_origem_check CHECK ((origem = ANY (ARRAY['evento'::text, 'cobertura'::text, 'aplicacao'::text])))
);


--
-- Name: TABLE auditoria; Type: COMMENT; Schema: plat; Owner: -
--

COMMENT ON TABLE plat.auditoria IS 'Trilha de auditoria de negócio (item L7-20): append-only, RLS por inquilino, retenção por inquilino.';


--
-- Name: COLUMN auditoria.origem; Type: COMMENT; Schema: plat; Owner: -
--

COMMENT ON COLUMN plat.auditoria.origem IS 'evento = trigger sobre plat.evento; cobertura = fim de transação de escrita sem evento; aplicacao = chamada explícita da API (exportação, leitura de camada pessoal).';


--
-- Name: auditoria_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.auditoria_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auditoria_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.auditoria_id_seq OWNED BY plat.auditoria.id;


--
-- Name: categoria; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.categoria (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    pai_id uuid,
    nome text NOT NULL,
    caminho text DEFAULT ''::text NOT NULL,
    nivel smallint DEFAULT 1 NOT NULL,
    posicao integer DEFAULT 0 NOT NULL,
    origem text DEFAULT 'propria'::text NOT NULL,
    codigo text,
    CONSTRAINT categoria_nivel_check CHECK (((nivel >= 1) AND (nivel <= 3))),
    CONSTRAINT categoria_nome_check CHECK (((length(nome) >= 1) AND (length(nome) <= 100))),
    CONSTRAINT categoria_origem_check CHECK ((origem = ANY (ARRAY['iso19115'::text, 'inspire'::text, 'propria'::text])))
);


--
-- Name: compartilhamento_link; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.compartilhamento_link (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    item_id uuid NOT NULL,
    token_hash text NOT NULL,
    prefixo text NOT NULL,
    nome text,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    expira_em timestamp with time zone,
    revogado_em timestamp with time zone,
    revogado_por integer,
    acessos bigint DEFAULT 0 NOT NULL,
    ultimo_acesso_em timestamp with time zone,
    ultimo_ip text,
    permite_download boolean DEFAULT false NOT NULL,
    CONSTRAINT compartilhamento_link_check CHECK (((expira_em IS NULL) OR (expira_em <= (criado_em + '365 days'::interval)))),
    CONSTRAINT compartilhamento_link_nome_check CHECK ((length(nome) <= 128))
);


--
-- Name: compartilhamento_link_item; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.compartilhamento_link_item (
    link_id uuid NOT NULL,
    item_id uuid NOT NULL,
    tenant_id integer NOT NULL
);


--
-- Name: conexao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.conexao (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    tipo text NOT NULL,
    modo text DEFAULT 'referenciada'::text NOT NULL,
    nome text NOT NULL,
    url text NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    credencial_cifrada text,
    saude text DEFAULT 'nunca_testada'::text NOT NULL,
    saude_mensagem text,
    saude_verificada_em timestamp with time zone,
    saude_latencia_ms integer,
    dono_id integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT conexao_modo_check CHECK ((modo = ANY (ARRAY['referenciada'::text, 'copiada'::text]))),
    CONSTRAINT conexao_nome_check CHECK (((btrim(nome) <> ''::text) AND (length(nome) <= 200))),
    CONSTRAINT conexao_saude_check CHECK ((saude = ANY (ARRAY['nunca_testada'::text, 'ok'::text, 'erro'::text]))),
    CONSTRAINT conexao_tipo_check CHECK ((tipo = ANY (ARRAY['wms'::text, 'wmts'::text, 'wfs'::text, 'ogc_api'::text, 'esri_rest'::text, 'stac'::text, 'geoparquet'::text, 'pmtiles'::text, 'postgres_fdw'::text, 's3'::text, 'http'::text]))),
    CONSTRAINT conexao_url_check CHECK (((btrim(url) <> ''::text) AND (length(url) <= 2048)))
);


--
-- Name: conexao_saude_historico; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.conexao_saude_historico (
    id bigint NOT NULL,
    conexao_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    verificada_em timestamp with time zone DEFAULT now() NOT NULL,
    ok boolean NOT NULL,
    status integer,
    mensagem text,
    latencia_ms integer
);


--
-- Name: conexao_saude_historico_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.conexao_saude_historico_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conexao_saude_historico_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.conexao_saude_historico_id_seq OWNED BY plat.conexao_saude_historico.id;


--
-- Name: convite; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.convite (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    email text NOT NULL,
    nome_sugerido text,
    perfil text NOT NULL,
    papel_id integer,
    token_hash text NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    expira_em timestamp with time zone NOT NULL,
    usado_em timestamp with time zone,
    cancelado_em timestamp with time zone,
    usuario_criado_id integer,
    CONSTRAINT convite_perfil_check CHECK ((perfil = ANY (ARRAY['admin'::text, 'editor'::text, 'visualizador'::text, 'campo'::text])))
);


--
-- Name: evento; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.evento (
    id bigint NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer NOT NULL,
    ator_id integer,
    tipo text NOT NULL,
    alvo_tipo text,
    alvo_id text,
    propriedades jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip text,
    req_id text
)
PARTITION BY RANGE (em);


--
-- Name: evento_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.evento_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: evento_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.evento_id_seq OWNED BY plat.evento.id;


--
-- Name: evento_tipo; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.evento_tipo (
    nome text NOT NULL,
    descricao text NOT NULL
);


--
-- Name: evento_y2026m09; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.evento_y2026m09 (
    id bigint DEFAULT nextval('plat.evento_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer NOT NULL,
    ator_id integer,
    tipo text NOT NULL,
    alvo_tipo text,
    alvo_id text,
    propriedades jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip text,
    req_id text
);


--
-- Name: evento_y2026m10; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.evento_y2026m10 (
    id bigint DEFAULT nextval('plat.evento_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer NOT NULL,
    ator_id integer,
    tipo text NOT NULL,
    alvo_tipo text,
    alvo_id text,
    propriedades jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip text,
    req_id text
);


--
-- Name: evento_y2026m11; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.evento_y2026m11 (
    id bigint DEFAULT nextval('plat.evento_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer NOT NULL,
    ator_id integer,
    tipo text NOT NULL,
    alvo_tipo text,
    alvo_id text,
    propriedades jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip text,
    req_id text
);


--
-- Name: evento_y2026m12; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.evento_y2026m12 (
    id bigint DEFAULT nextval('plat.evento_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer NOT NULL,
    ator_id integer,
    tipo text NOT NULL,
    alvo_tipo text,
    alvo_id text,
    propriedades jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip text,
    req_id text
);


--
-- Name: favorito; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.favorito (
    usuario_id integer NOT NULL,
    item_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: geo_endereco; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.geo_endereco (
    id bigint NOT NULL,
    cod_unico_endereco bigint NOT NULL,
    cod_uf smallint NOT NULL,
    cod_municipio integer NOT NULL,
    cod_setor text,
    num_quadra text,
    num_face text,
    face_id text NOT NULL,
    cep text,
    localidade text,
    localidade_norm text,
    tipo_logradouro text,
    titulo_logradouro text,
    nome_logradouro text,
    logradouro_norm text NOT NULL,
    numero integer,
    sem_numero boolean DEFAULT false NOT NULL,
    modificador text,
    especie smallint,
    nivel_geo smallint,
    lat double precision NOT NULL,
    lon double precision NOT NULL,
    geom public.geometry(Point,4326) NOT NULL
);


--
-- Name: geo_endereco_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.geo_endereco_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: geo_endereco_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.geo_endereco_id_seq OWNED BY plat.geo_endereco.id;


--
-- Name: geo_instalacao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.geo_instalacao (
    cod_uf smallint NOT NULL,
    sigla text NOT NULL,
    fonte_url text NOT NULL,
    arquivo_bytes bigint NOT NULL,
    csv_bytes bigint NOT NULL,
    linhas bigint NOT NULL,
    municipios integer NOT NULL,
    duracao_s numeric NOT NULL,
    sha256_zip text NOT NULL,
    instalado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: geo_municipio; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.geo_municipio (
    cod integer NOT NULL,
    cod_uf smallint NOT NULL,
    nome text NOT NULL,
    nome_norm text NOT NULL,
    centro_lat double precision,
    centro_lon double precision,
    enderecos integer DEFAULT 0 NOT NULL
);


--
-- Name: geo_uf; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.geo_uf (
    cod smallint NOT NULL,
    sigla text NOT NULL,
    nome text NOT NULL
);


--
-- Name: grupo; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.grupo (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    nome text NOT NULL,
    resumo text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    visibilidade text DEFAULT 'membros'::text NOT NULL,
    entrada text DEFAULT 'convite'::text NOT NULL,
    contribuicao text DEFAULT 'todos'::text NOT NULL,
    atualizacao_compartilhada boolean DEFAULT false NOT NULL,
    administrativo boolean DEFAULT false NOT NULL,
    protegido boolean DEFAULT false NOT NULL,
    dono_id integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT grupo_check CHECK (((NOT atualizacao_compartilhada) OR (entrada = ANY (ARRAY['convite'::text, 'pedido'::text])))),
    CONSTRAINT grupo_contribuicao_check CHECK ((contribuicao = ANY (ARRAY['todos'::text, 'dono_gerentes'::text]))),
    CONSTRAINT grupo_entrada_check CHECK ((entrada = ANY (ARRAY['convite'::text, 'pedido'::text, 'livre'::text]))),
    CONSTRAINT grupo_nome_check CHECK (((length(nome) >= 1) AND (length(nome) <= 128))),
    CONSTRAINT grupo_resumo_check CHECK (((resumo IS NULL) OR (length(resumo) <= 2048))),
    CONSTRAINT grupo_tags_check CHECK ((cardinality(tags) <= 50)),
    CONSTRAINT grupo_visibilidade_check CHECK ((visibilidade = ANY (ARRAY['membros'::text, 'inquilino'::text])))
);


--
-- Name: grupo_membro; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.grupo_membro (
    grupo_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer NOT NULL,
    papel text DEFAULT 'membro'::text NOT NULL,
    estado text DEFAULT 'ativo'::text NOT NULL,
    convidado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT grupo_membro_estado_check CHECK ((estado = ANY (ARRAY['ativo'::text, 'convidado'::text, 'pedido'::text]))),
    CONSTRAINT grupo_membro_papel_check CHECK ((papel = ANY (ARRAY['dono'::text, 'gerente'::text, 'membro'::text])))
);


--
-- Name: importacao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.importacao (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer,
    arquivo_id uuid NOT NULL,
    item_id uuid NOT NULL,
    formato text NOT NULL,
    estado text DEFAULT 'inspecionando'::text NOT NULL,
    proposta jsonb,
    confirmacao jsonb,
    relatorio jsonb,
    job_inspecao uuid,
    job_carga uuid,
    erro text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    expira_em timestamp with time zone,
    CONSTRAINT importacao_estado_check CHECK ((estado = ANY (ARRAY['inspecionando'::text, 'proposta'::text, 'confirmada'::text, 'carregando'::text, 'concluida'::text, 'falhou'::text, 'cancelada'::text, 'expirada'::text])))
);


--
-- Name: item_grupo; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.item_grupo (
    item_id uuid NOT NULL,
    grupo_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    destaque boolean DEFAULT false NOT NULL
);


--
-- Name: item_relacao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.item_relacao (
    origem uuid NOT NULL,
    destino uuid NOT NULL,
    tipo text NOT NULL,
    tenant_id integer NOT NULL,
    posicao integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT item_relacao_check CHECK ((origem <> destino))
);


--
-- Name: item_versao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.item_versao (
    item_id uuid NOT NULL,
    versao integer NOT NULL,
    tenant_id integer NOT NULL,
    corpo jsonb NOT NULL,
    sha256 text NOT NULL,
    autor_id integer,
    comentario text,
    rotulo text,
    compactou integer DEFAULT 0 NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT item_versao_comentario_check CHECK ((length(comentario) <= 500)),
    CONSTRAINT item_versao_rotulo_check CHECK ((rotulo = ANY (ARRAY['edicao'::text, 'restauracao'::text, 'rascunho'::text, 'publicacao'::text, 'compactada'::text, 'migracao'::text])))
);


--
-- Name: job_log; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.job_log (
    id bigint NOT NULL,
    job_id uuid NOT NULL,
    tenant_id integer NOT NULL,
    em timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    nivel text NOT NULL,
    mensagem text NOT NULL,
    CONSTRAINT job_log_nivel_check CHECK ((nivel = ANY (ARRAY['DEBUG'::text, 'INFO'::text, 'AVISO'::text, 'ERRO'::text])))
);


--
-- Name: job_log_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.job_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: job_log_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.job_log_id_seq OWNED BY plat.job_log.id;


--
-- Name: log_acesso; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.log_acesso (
    id bigint NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer,
    usuario_id integer,
    token_id integer,
    ip text,
    metodo text NOT NULL,
    rota text NOT NULL,
    status integer NOT NULL,
    bytes bigint DEFAULT 0 NOT NULL,
    tempo_ms integer NOT NULL,
    agente text,
    resultado text
)
PARTITION BY RANGE (em);


--
-- Name: log_acesso_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.log_acesso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: log_acesso_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.log_acesso_id_seq OWNED BY plat.log_acesso.id;


--
-- Name: log_acesso_y2026m09; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.log_acesso_y2026m09 (
    id bigint DEFAULT nextval('plat.log_acesso_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer,
    usuario_id integer,
    token_id integer,
    ip text,
    metodo text NOT NULL,
    rota text NOT NULL,
    status integer NOT NULL,
    bytes bigint DEFAULT 0 NOT NULL,
    tempo_ms integer NOT NULL,
    agente text,
    resultado text
);


--
-- Name: log_acesso_y2026m10; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.log_acesso_y2026m10 (
    id bigint DEFAULT nextval('plat.log_acesso_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer,
    usuario_id integer,
    token_id integer,
    ip text,
    metodo text NOT NULL,
    rota text NOT NULL,
    status integer NOT NULL,
    bytes bigint DEFAULT 0 NOT NULL,
    tempo_ms integer NOT NULL,
    agente text,
    resultado text
);


--
-- Name: log_acesso_y2026m11; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.log_acesso_y2026m11 (
    id bigint DEFAULT nextval('plat.log_acesso_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer,
    usuario_id integer,
    token_id integer,
    ip text,
    metodo text NOT NULL,
    rota text NOT NULL,
    status integer NOT NULL,
    bytes bigint DEFAULT 0 NOT NULL,
    tempo_ms integer NOT NULL,
    agente text,
    resultado text
);


--
-- Name: log_acesso_y2026m12; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.log_acesso_y2026m12 (
    id bigint DEFAULT nextval('plat.log_acesso_id_seq'::regclass) NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id integer,
    usuario_id integer,
    token_id integer,
    ip text,
    metodo text NOT NULL,
    rota text NOT NULL,
    status integer NOT NULL,
    bytes bigint DEFAULT 0 NOT NULL,
    tempo_ms integer NOT NULL,
    agente text,
    resultado text
);


--
-- Name: papel_personalizado; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.papel_personalizado (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    nome text NOT NULL,
    descricao text,
    perfil_minimo text NOT NULL,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT papel_personalizado_descricao_check CHECK (((descricao IS NULL) OR (length(descricao) <= 250))),
    CONSTRAINT papel_personalizado_nome_check CHECK (((length(nome) >= 1) AND (length(nome) <= 128))),
    CONSTRAINT papel_personalizado_perfil_minimo_check CHECK ((perfil_minimo = ANY (ARRAY['admin'::text, 'editor'::text, 'visualizador'::text, 'campo'::text])))
);


--
-- Name: papel_personalizado_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.papel_personalizado_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: papel_personalizado_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.papel_personalizado_id_seq OWNED BY plat.papel_personalizado.id;


--
-- Name: papel_privilegio; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.papel_privilegio (
    papel_id integer NOT NULL,
    privilegio text NOT NULL
);


--
-- Name: pasta; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.pasta (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    pai_id uuid,
    nome text NOT NULL,
    ancestrais uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    profundidade smallint DEFAULT 0 NOT NULL,
    dono_id integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT pasta_nome_check CHECK ((((length(nome) >= 1) AND (length(nome) <= 128)) AND (nome !~ '[/\\]'::text) AND (nome = btrim(nome)))),
    CONSTRAINT pasta_profundidade_check CHECK (((profundidade >= 0) AND (profundidade <= 4)))
);


--
-- Name: perfil_privilegio; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.perfil_privilegio (
    perfil text NOT NULL,
    privilegio text NOT NULL,
    CONSTRAINT perfil_privilegio_perfil_check CHECK ((perfil = ANY (ARRAY['admin'::text, 'editor'::text, 'visualizador'::text, 'campo'::text])))
);


--
-- Name: privilegio; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.privilegio (
    nome text NOT NULL,
    grupo text NOT NULL,
    descricao text NOT NULL,
    administrativo boolean DEFAULT false NOT NULL,
    CONSTRAINT privilegio_nome_check CHECK ((nome ~ '^[a-z]+\.[a-z_]+$'::text))
);


--
-- Name: provedor_ldap; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.provedor_ldap (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    habilitado boolean DEFAULT true NOT NULL,
    url text,
    base_dn text,
    start_tls boolean DEFAULT true NOT NULL,
    bind_dn text,
    bind_senha_cifrada text,
    filtro_usuario text DEFAULT '(uid={login})'::text NOT NULL,
    atributo_grupos text DEFAULT 'memberOf'::text NOT NULL,
    perfil_padrao text,
    mapa_grupo_perfil jsonb DEFAULT '{}'::jsonb NOT NULL,
    criado_por integer,
    atualizado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT provedor_ldap_perfil_padrao_check CHECK (((perfil_padrao IS NULL) OR (perfil_padrao = ANY (ARRAY['admin'::text, 'editor'::text, 'visualizador'::text, 'campo'::text]))))
);


--
-- Name: provedor_ldap_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.provedor_ldap_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provedor_ldap_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.provedor_ldap_id_seq OWNED BY plat.provedor_ldap.id;


--
-- Name: raster_colecao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.raster_colecao (
    colecao text NOT NULL,
    tenant_id integer NOT NULL,
    slug text NOT NULL,
    titulo text,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_raster_colecao_prefixo CHECK ((colecao = (((tenant_id)::text || '-'::text) || slug))),
    CONSTRAINT ck_raster_colecao_slug CHECK ((slug ~ '^[a-z0-9][a-z0-9_-]{0,62}$'::text))
);


--
-- Name: raster_item; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.raster_item (
    colecao text NOT NULL,
    item_id text NOT NULL,
    tenant_id integer NOT NULL,
    sha256 text,
    perfil text DEFAULT 'visual'::text NOT NULL,
    bytes bigint DEFAULT 0 NOT NULL,
    estado text DEFAULT 'registrado'::text NOT NULL,
    origem text DEFAULT 'referenciado'::text NOT NULL,
    licenca text,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_raster_item_prefixo CHECK ((split_part(colecao, '-'::text, 1) = (tenant_id)::text)),
    CONSTRAINT raster_item_bytes_check CHECK ((bytes >= 0)),
    CONSTRAINT raster_item_estado_check CHECK ((estado = ANY (ARRAY['registrado'::text, 'ingerindo'::text, 'pronto'::text, 'falhou'::text, 'removido'::text]))),
    CONSTRAINT raster_item_origem_check CHECK ((origem = ANY (ARRAY['copiado'::text, 'referenciado'::text]))),
    CONSTRAINT raster_item_perfil_check CHECK ((perfil = ANY (ARRAY['visual'::text, 'cientifico'::text, 'referencia'::text]))),
    CONSTRAINT raster_item_sha256_check CHECK (((sha256 IS NULL) OR (sha256 ~ '^[0-9a-f]{64}$'::text)))
);


--
-- Name: redefinicao_pedido; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.redefinicao_pedido (
    id bigint NOT NULL,
    chave text NOT NULL,
    ip text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: redefinicao_pedido_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.redefinicao_pedido_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: redefinicao_pedido_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.redefinicao_pedido_id_seq OWNED BY plat.redefinicao_pedido.id;


--
-- Name: redefinicao_senha; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.redefinicao_senha (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer NOT NULL,
    token_hash text NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    expira_em timestamp with time zone NOT NULL,
    usado_em timestamp with time zone,
    ip text
);


--
-- Name: relacao_tipo; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.relacao_tipo (
    nome text NOT NULL,
    descricao text NOT NULL,
    origem_familias text[] NOT NULL,
    destino_familias text[] NOT NULL,
    arrasta_dono boolean DEFAULT false NOT NULL,
    apaga_junto boolean DEFAULT false NOT NULL
);


--
-- Name: senha_historico; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.senha_historico (
    id bigint NOT NULL,
    usuario_id integer NOT NULL,
    senha_hash text NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: senha_historico_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.senha_historico_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: senha_historico_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.senha_historico_id_seq OWNED BY plat.senha_historico.id;


--
-- Name: sessao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.sessao (
    token_hash text NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    expira_em timestamp with time zone NOT NULL,
    ultimo_uso timestamp with time zone,
    ip text,
    agente text
);


--
-- Name: tenant; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.tenant (
    id integer NOT NULL,
    slug text NOT NULL,
    nome text NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    cota_bytes bigint DEFAULT '21474836480'::bigint NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    uso_bytes bigint DEFAULT 0 NOT NULL,
    uso_reservado_bytes bigint DEFAULT 0 NOT NULL,
    cota_objetos bigint DEFAULT 200000 NOT NULL,
    cota_bytes_teto bigint DEFAULT '21474836480'::bigint NOT NULL,
    cota_usuarios_teto integer DEFAULT 2000 NOT NULL,
    CONSTRAINT ck_tenant_cota_objetos CHECK ((cota_objetos > 0)),
    CONSTRAINT tenant_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]{1,38}$'::text))
);


--
-- Name: tenant_bucket; Type: VIEW; Schema: plat; Owner: -
--

CREATE VIEW plat.tenant_bucket WITH (security_invoker='true') AS
 SELECT tenant_id,
    bucket_id,
    bucket_alias,
    chave_ro_id,
    cota_bytes,
    cota_objetos,
    web_ativo,
    criado_em,
    atualizado_em
   FROM plat.arquivo_bucket;


--
-- Name: tenant_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.tenant_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenant_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.tenant_id_seq OWNED BY plat.tenant.id;


--
-- Name: tipo_item; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.tipo_item (
    nome text NOT NULL,
    familia text NOT NULL,
    rotulo text NOT NULL,
    descricao text NOT NULL,
    esquema jsonb NOT NULL,
    esquema_versao integer DEFAULT 1 NOT NULL,
    icone text NOT NULL,
    modulo_front text NOT NULL,
    abre_em text[] DEFAULT '{}'::text[] NOT NULL,
    tem_dado_fisico boolean DEFAULT false NOT NULL,
    linha_dona text NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tipo_item_familia_check CHECK ((familia = ANY (ARRAY['camada'::text, 'raster'::text, 'mapa'::text, 'app'::text, 'painel'::text, 'formulario'::text, 'fluxo'::text, 'rede'::text, 'arquivo'::text, 'ferramenta'::text, 'documento'::text]))),
    CONSTRAINT tipo_item_nome_check CHECK ((nome ~ '^[a-z][a-z0-9_]{1,40}$'::text))
);


--
-- Name: token_servico; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.token_servico (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer NOT NULL,
    nome text NOT NULL,
    token_hash text NOT NULL,
    prefixo text NOT NULL,
    escopos text[] DEFAULT '{}'::text[] NOT NULL,
    restricao jsonb DEFAULT '{}'::jsonb NOT NULL,
    expira_em timestamp with time zone NOT NULL,
    revogado_em timestamp with time zone,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    ultimo_uso timestamp with time zone,
    ultimo_ip text,
    renovado_por integer,
    usos bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_token_prazo_teto CHECK ((expira_em <= (criado_em + '366 days'::interval)))
);


--
-- Name: token_servico_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.token_servico_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: token_servico_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.token_servico_id_seq OWNED BY plat.token_servico.id;


--
-- Name: upload; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.upload (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id integer NOT NULL,
    usuario_id integer NOT NULL,
    nome text NOT NULL,
    bytes_declarado bigint NOT NULL,
    tipo_declarado text NOT NULL,
    sha256_declarado text,
    upload_s3_id text NOT NULL,
    chave_temp text NOT NULL,
    parte_bytes bigint NOT NULL,
    partes_total integer NOT NULL,
    estado text DEFAULT 'iniciado'::text NOT NULL,
    arquivo_id uuid,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    expira_em timestamp with time zone NOT NULL,
    concluido_em timestamp with time zone,
    CONSTRAINT upload_bytes_declarado_check CHECK ((bytes_declarado > 0)),
    CONSTRAINT upload_estado_check CHECK ((estado = ANY (ARRAY['iniciado'::text, 'concluido'::text, 'abortado'::text, 'expirado'::text]))),
    CONSTRAINT upload_nome_check CHECK (((length(nome) >= 1) AND (length(nome) <= 255))),
    CONSTRAINT upload_partes_total_check CHECK ((partes_total >= 1)),
    CONSTRAINT upload_sha256_declarado_check CHECK (((sha256_declarado IS NULL) OR (sha256_declarado ~ '^[0-9a-f]{64}$'::text)))
);


--
-- Name: upload_parte; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.upload_parte (
    upload_id uuid NOT NULL,
    n integer NOT NULL,
    bytes bigint NOT NULL,
    etag text NOT NULL,
    sha256 text,
    recebida_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT upload_parte_bytes_check CHECK ((bytes >= 0)),
    CONSTRAINT upload_parte_n_check CHECK ((n >= 1))
);


--
-- Name: usuario; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.usuario (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    login text NOT NULL,
    nome text NOT NULL,
    email text,
    senha_hash text,
    perfil text NOT NULL,
    superadmin boolean DEFAULT false NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    totp_secret text,
    totp_ativo boolean DEFAULT false NOT NULL,
    senha_alterada_em timestamp with time zone,
    falhas_login integer DEFAULT 0 NOT NULL,
    bloqueado_ate timestamp with time zone,
    ultimo_login timestamp with time zone,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    papel_id integer,
    origem text DEFAULT 'local'::text NOT NULL,
    sujeito_externo text,
    trocar_senha boolean DEFAULT false NOT NULL,
    falhas_desde timestamp with time zone,
    totp_ultimo_passo bigint,
    codigos_recuperacao text[],
    desafio_2fa_hash text,
    desafio_2fa_ate timestamp with time zone,
    ultimo_ip text,
    idioma_preferido text DEFAULT 'pt-BR'::text NOT NULL,
    unidades text DEFAULT 'metrico'::text NOT NULL,
    formato_data text DEFAULT 'dd/mm/aaaa'::text NOT NULL,
    visibilidade_perfil text DEFAULT 'inquilino'::text NOT NULL,
    foto_sha256 text,
    CONSTRAINT ck_usuario_formato_data CHECK ((formato_data = ANY (ARRAY['dd/mm/aaaa'::text, 'mm/dd/aaaa'::text, 'aaaa-mm-dd'::text]))),
    CONSTRAINT ck_usuario_foto_sha256 CHECK (((foto_sha256 IS NULL) OR (foto_sha256 ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_usuario_idioma_preferido CHECK ((idioma_preferido = ANY (ARRAY['pt-BR'::text, 'en'::text, 'es'::text]))),
    CONSTRAINT ck_usuario_origem CHECK ((origem = ANY (ARRAY['local'::text, 'oidc'::text, 'saml'::text, 'ldap'::text]))),
    CONSTRAINT ck_usuario_senha_local CHECK (((origem <> 'local'::text) OR (senha_hash IS NOT NULL))),
    CONSTRAINT ck_usuario_unidades CHECK ((unidades = ANY (ARRAY['metrico'::text, 'imperial'::text]))),
    CONSTRAINT ck_usuario_visibilidade_perfil CHECK ((visibilidade_perfil = ANY (ARRAY['privado'::text, 'inquilino'::text]))),
    CONSTRAINT usuario_login_check CHECK ((login = lower(login))),
    CONSTRAINT usuario_perfil_check CHECK ((perfil = ANY (ARRAY['admin'::text, 'editor'::text, 'visualizador'::text, 'campo'::text])))
);


--
-- Name: usuario_id_seq; Type: SEQUENCE; Schema: plat; Owner: -
--

CREATE SEQUENCE plat.usuario_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: usuario_id_seq; Type: SEQUENCE OWNED BY; Schema: plat; Owner: -
--

ALTER SEQUENCE plat.usuario_id_seq OWNED BY plat.usuario.id;


--
-- Name: v_conexao_saude; Type: VIEW; Schema: plat; Owner: -
--

CREATE VIEW plat.v_conexao_saude WITH (security_invoker='true') AS
 SELECT c.id AS conexao_id,
        CASE
            WHEN (c.saude = 'nunca_testada'::text) THEN 'nunca_testada'::text
            WHEN (jan.ultima_ok IS FALSE) THEN 'fora'::text
            WHEN jan.alguma_falha THEN 'degradado'::text
            ELSE 'ok'::text
        END AS estado_saude,
    disp.total AS disponibilidade_30d_total,
    disp.ok AS disponibilidade_30d_ok,
        CASE
            WHEN (disp.total > 0) THEN round((((disp.ok)::numeric / (disp.total)::numeric) * (100)::numeric), 1)
            ELSE NULL::numeric
        END AS disponibilidade_30d_pct
   FROM ((plat.conexao c
     LEFT JOIN LATERAL ( SELECT (array_agg(h.ok ORDER BY h.verificada_em DESC))[1] AS ultima_ok,
            bool_or((NOT h.ok)) AS alguma_falha
           FROM ( SELECT conexao_saude_historico.ok,
                    conexao_saude_historico.verificada_em
                   FROM plat.conexao_saude_historico
                  WHERE (conexao_saude_historico.conexao_id = c.id)
                  ORDER BY conexao_saude_historico.verificada_em DESC
                 LIMIT 5) h) jan ON (true))
     LEFT JOIN LATERAL ( SELECT count(*) AS total,
            count(*) FILTER (WHERE conexao_saude_historico.ok) AS ok
           FROM plat.conexao_saude_historico
          WHERE ((conexao_saude_historico.conexao_id = c.id) AND (conexao_saude_historico.verificada_em >= (now() - '30 days'::interval)))) disp ON (true));


--
-- Name: versao_migracao; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.versao_migracao (
    nome text NOT NULL,
    sha256 text NOT NULL,
    aplicada_em timestamp with time zone DEFAULT now() NOT NULL,
    duracao_ms integer NOT NULL,
    aplicada_por text DEFAULT CURRENT_USER NOT NULL
);


--
-- Name: versao_pgstac; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.versao_pgstac (
    versao text NOT NULL,
    pypgstac text NOT NULL,
    aplicada_em timestamp with time zone DEFAULT now() NOT NULL,
    aplicada_por text DEFAULT CURRENT_USER NOT NULL
);


--
-- Name: worker; Type: TABLE; Schema: plat; Owner: -
--

CREATE TABLE plat.worker (
    nome text NOT NULL,
    pid integer NOT NULL,
    versao text NOT NULL,
    git_sha text NOT NULL,
    processos integer NOT NULL,
    iniciado_em timestamp with time zone DEFAULT now() NOT NULL,
    heartbeat_em timestamp with time zone DEFAULT now() NOT NULL,
    rss_kb integer,
    rodando integer DEFAULT 0 NOT NULL
);


--
-- Name: marcadores; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.marcadores (
    job_id uuid NOT NULL,
    marcador uuid NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: passos; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.passos (
    job_id uuid NOT NULL,
    passo integer NOT NULL,
    em timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


--
-- Name: zt_expurgo_014165; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_expurgo_014165 (
    id integer NOT NULL,
    geom public.geometry(Point,4326)
);


--
-- Name: zt_expurgo_014165_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_expurgo_014165_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_expurgo_014165_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_expurgo_014165_id_seq OWNED BY plat_trabalho.zt_expurgo_014165.id;


--
-- Name: zt_expurgo_267601; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_expurgo_267601 (
    id integer NOT NULL,
    geom public.geometry(Point,4326)
);


--
-- Name: zt_expurgo_267601_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_expurgo_267601_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_expurgo_267601_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_expurgo_267601_id_seq OWNED BY plat_trabalho.zt_expurgo_267601.id;


--
-- Name: zt_expurgo_4a33f9; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_expurgo_4a33f9 (
    id integer NOT NULL,
    geom public.geometry(Point,4326)
);


--
-- Name: zt_expurgo_4a33f9_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_expurgo_4a33f9_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_expurgo_4a33f9_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_expurgo_4a33f9_id_seq OWNED BY plat_trabalho.zt_expurgo_4a33f9.id;


--
-- Name: zt_expurgo_4c099b; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_expurgo_4c099b (
    id integer NOT NULL,
    geom public.geometry(Point,4326)
);


--
-- Name: zt_expurgo_4c099b_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_expurgo_4c099b_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_expurgo_4c099b_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_expurgo_4c099b_id_seq OWNED BY plat_trabalho.zt_expurgo_4c099b.id;


--
-- Name: zt_mini_230243; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_230243 (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_230243_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_230243_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_230243_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_230243_id_seq OWNED BY plat_trabalho.zt_mini_230243.id;


--
-- Name: zt_mini_8f66ef; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_8f66ef (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_8f66ef_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_8f66ef_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_8f66ef_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_8f66ef_id_seq OWNED BY plat_trabalho.zt_mini_8f66ef.id;


--
-- Name: zt_mini_bd33e7; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_bd33e7 (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_bd33e7_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_bd33e7_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_bd33e7_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_bd33e7_id_seq OWNED BY plat_trabalho.zt_mini_bd33e7.id;


--
-- Name: zt_mini_be12d3; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_be12d3 (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_be12d3_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_be12d3_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_be12d3_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_be12d3_id_seq OWNED BY plat_trabalho.zt_mini_be12d3.id;


--
-- Name: zt_mini_c5d81b; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_c5d81b (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_c5d81b_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_c5d81b_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_c5d81b_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_c5d81b_id_seq OWNED BY plat_trabalho.zt_mini_c5d81b.id;


--
-- Name: zt_mini_c99ac0; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_c99ac0 (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_c99ac0_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_c99ac0_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_c99ac0_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_c99ac0_id_seq OWNED BY plat_trabalho.zt_mini_c99ac0.id;


--
-- Name: zt_mini_d0bb6e; Type: TABLE; Schema: plat_trabalho; Owner: -
--

CREATE TABLE plat_trabalho.zt_mini_d0bb6e (
    id integer NOT NULL,
    geom public.geometry(Polygon,4326)
);


--
-- Name: zt_mini_d0bb6e_id_seq; Type: SEQUENCE; Schema: plat_trabalho; Owner: -
--

CREATE SEQUENCE plat_trabalho.zt_mini_d0bb6e_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zt_mini_d0bb6e_id_seq; Type: SEQUENCE OWNED BY; Schema: plat_trabalho; Owner: -
--

ALTER SEQUENCE plat_trabalho.zt_mini_d0bb6e_id_seq OWNED BY plat_trabalho.zt_mini_d0bb6e.id;


--
-- Name: evento_y2026m09; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento ATTACH PARTITION plat.evento_y2026m09 FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');


--
-- Name: evento_y2026m10; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento ATTACH PARTITION plat.evento_y2026m10 FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');


--
-- Name: evento_y2026m11; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento ATTACH PARTITION plat.evento_y2026m11 FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');


--
-- Name: evento_y2026m12; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento ATTACH PARTITION plat.evento_y2026m12 FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');


--
-- Name: log_acesso_y2026m09; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso ATTACH PARTITION plat.log_acesso_y2026m09 FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');


--
-- Name: log_acesso_y2026m10; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso ATTACH PARTITION plat.log_acesso_y2026m10 FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');


--
-- Name: log_acesso_y2026m11; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso ATTACH PARTITION plat.log_acesso_y2026m11 FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');


--
-- Name: log_acesso_y2026m12; Type: TABLE ATTACH; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso ATTACH PARTITION plat.log_acesso_y2026m12 FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');


--
-- Name: arquivo id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo ALTER COLUMN id SET DEFAULT nextval('plat.arquivo_id_seq'::regclass);


--
-- Name: auditoria id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.auditoria ALTER COLUMN id SET DEFAULT nextval('plat.auditoria_id_seq'::regclass);


--
-- Name: conexao_saude_historico id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao_saude_historico ALTER COLUMN id SET DEFAULT nextval('plat.conexao_saude_historico_id_seq'::regclass);


--
-- Name: evento id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento ALTER COLUMN id SET DEFAULT nextval('plat.evento_id_seq'::regclass);


--
-- Name: geo_endereco id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_endereco ALTER COLUMN id SET DEFAULT nextval('plat.geo_endereco_id_seq'::regclass);


--
-- Name: job_log id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job_log ALTER COLUMN id SET DEFAULT nextval('plat.job_log_id_seq'::regclass);


--
-- Name: log_acesso id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso ALTER COLUMN id SET DEFAULT nextval('plat.log_acesso_id_seq'::regclass);


--
-- Name: papel_personalizado id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_personalizado ALTER COLUMN id SET DEFAULT nextval('plat.papel_personalizado_id_seq'::regclass);


--
-- Name: provedor_ldap id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.provedor_ldap ALTER COLUMN id SET DEFAULT nextval('plat.provedor_ldap_id_seq'::regclass);


--
-- Name: redefinicao_pedido id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.redefinicao_pedido ALTER COLUMN id SET DEFAULT nextval('plat.redefinicao_pedido_id_seq'::regclass);


--
-- Name: senha_historico id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.senha_historico ALTER COLUMN id SET DEFAULT nextval('plat.senha_historico_id_seq'::regclass);


--
-- Name: tenant id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.tenant ALTER COLUMN id SET DEFAULT nextval('plat.tenant_id_seq'::regclass);


--
-- Name: token_servico id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.token_servico ALTER COLUMN id SET DEFAULT nextval('plat.token_servico_id_seq'::regclass);


--
-- Name: usuario id; Type: DEFAULT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.usuario ALTER COLUMN id SET DEFAULT nextval('plat.usuario_id_seq'::regclass);


--
-- Name: zt_expurgo_014165 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_014165 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_expurgo_014165_id_seq'::regclass);


--
-- Name: zt_expurgo_267601 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_267601 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_expurgo_267601_id_seq'::regclass);


--
-- Name: zt_expurgo_4a33f9 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_4a33f9 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_expurgo_4a33f9_id_seq'::regclass);


--
-- Name: zt_expurgo_4c099b id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_4c099b ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_expurgo_4c099b_id_seq'::regclass);


--
-- Name: zt_mini_230243 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_230243 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_230243_id_seq'::regclass);


--
-- Name: zt_mini_8f66ef id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_8f66ef ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_8f66ef_id_seq'::regclass);


--
-- Name: zt_mini_bd33e7 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_bd33e7 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_bd33e7_id_seq'::regclass);


--
-- Name: zt_mini_be12d3 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_be12d3 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_be12d3_id_seq'::regclass);


--
-- Name: zt_mini_c5d81b id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_c5d81b ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_c5d81b_id_seq'::regclass);


--
-- Name: zt_mini_c99ac0 id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_c99ac0 ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_c99ac0_id_seq'::regclass);


--
-- Name: zt_mini_d0bb6e id; Type: DEFAULT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_d0bb6e ALTER COLUMN id SET DEFAULT nextval('plat_trabalho.zt_mini_d0bb6e_id_seq'::regclass);


--
-- Name: collections collections_id_key; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.collections
    ADD CONSTRAINT collections_id_key UNIQUE (id);


--
-- Name: collections collections_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.collections
    ADD CONSTRAINT collections_pkey PRIMARY KEY (key);


--
-- Name: cql2_ops cql2_ops_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.cql2_ops
    ADD CONSTRAINT cql2_ops_pkey PRIMARY KEY (op);


--
-- Name: format_item_cache format_item_cache_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.format_item_cache
    ADD CONSTRAINT format_item_cache_pkey PRIMARY KEY (collection, id, fields, hydrated);


--
-- Name: migrations migrations_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.migrations
    ADD CONSTRAINT migrations_pkey PRIMARY KEY (version);


--
-- Name: partition_stats partition_stats_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.partition_stats
    ADD CONSTRAINT partition_stats_pkey PRIMARY KEY (partition);


--
-- Name: pgstac_settings pgstac_settings_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.pgstac_settings
    ADD CONSTRAINT pgstac_settings_pkey PRIMARY KEY (name);


--
-- Name: query_queue query_queue_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.query_queue
    ADD CONSTRAINT query_queue_pkey PRIMARY KEY (query);


--
-- Name: queryables queryables_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.queryables
    ADD CONSTRAINT queryables_pkey PRIMARY KEY (id);


--
-- Name: search_wheres search_wheres_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.search_wheres
    ADD CONSTRAINT search_wheres_pkey PRIMARY KEY (id);


--
-- Name: searches searches_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.searches
    ADD CONSTRAINT searches_pkey PRIMARY KEY (hash);


--
-- Name: stac_extensions stac_extensions_pkey; Type: CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE ONLY pgstac.stac_extensions
    ADD CONSTRAINT stac_extensions_pkey PRIMARY KEY (url);


--
-- Name: acervo_assinatura acervo_assinatura_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_assinatura
    ADD CONSTRAINT acervo_assinatura_pkey PRIMARY KEY (tenant_id, acervo_camada_id);


--
-- Name: acervo_camada_execucao acervo_camada_execucao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_camada_execucao
    ADD CONSTRAINT acervo_camada_execucao_pkey PRIMARY KEY (id);


--
-- Name: acervo_camada acervo_camada_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_camada
    ADD CONSTRAINT acervo_camada_pkey PRIMARY KEY (acervo_camada_id);


--
-- Name: acervo_lgpd acervo_lgpd_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_lgpd
    ADD CONSTRAINT acervo_lgpd_pkey PRIMARY KEY (fonte_id);


--
-- Name: acervo_licenca acervo_licenca_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_licenca
    ADD CONSTRAINT acervo_licenca_pkey PRIMARY KEY (fonte_id);


--
-- Name: acervo_publicacao acervo_publicacao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_publicacao
    ADD CONSTRAINT acervo_publicacao_pkey PRIMARY KEY (acervo_camada_id);


--
-- Name: acervo_publicacao acervo_publicacao_view_nome_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_publicacao
    ADD CONSTRAINT acervo_publicacao_view_nome_key UNIQUE (view_nome);


--
-- Name: agenda agenda_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.agenda
    ADD CONSTRAINT agenda_pkey PRIMARY KEY (id);


--
-- Name: agenda agenda_tenant_id_nome_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.agenda
    ADD CONSTRAINT agenda_tenant_id_nome_key UNIQUE (tenant_id, nome);


--
-- Name: ambiente ambiente_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.ambiente
    ADD CONSTRAINT ambiente_pkey PRIMARY KEY (unico);


--
-- Name: amc_conjunto_unidade amc_conjunto_unidade_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_conjunto_unidade
    ADD CONSTRAINT amc_conjunto_unidade_pkey PRIMARY KEY (id);


--
-- Name: amc_execucao amc_execucao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_execucao
    ADD CONSTRAINT amc_execucao_pkey PRIMARY KEY (id);


--
-- Name: amc_fator_bruto amc_fator_bruto_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_fator_bruto
    ADD CONSTRAINT amc_fator_bruto_pkey PRIMARY KEY (execucao_id, unidade_id, fator);


--
-- Name: amc_modelo amc_modelo_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo
    ADD CONSTRAINT amc_modelo_pkey PRIMARY KEY (id);


--
-- Name: amc_modelo_versao amc_modelo_versao_modelo_id_numero_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo_versao
    ADD CONSTRAINT amc_modelo_versao_modelo_id_numero_key UNIQUE (modelo_id, numero);


--
-- Name: amc_modelo_versao amc_modelo_versao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo_versao
    ADD CONSTRAINT amc_modelo_versao_pkey PRIMARY KEY (modelo_id, versao_hash);


--
-- Name: amc_resultado amc_resultado_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_resultado
    ADD CONSTRAINT amc_resultado_pkey PRIMARY KEY (execucao_id, unidade_id);


--
-- Name: amc_unidade amc_unidade_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_unidade
    ADD CONSTRAINT amc_unidade_pkey PRIMARY KEY (conjunto_id, unidade_id);


--
-- Name: arquivo_bucket arquivo_bucket_bucket_alias_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo_bucket
    ADD CONSTRAINT arquivo_bucket_bucket_alias_key UNIQUE (bucket_alias);


--
-- Name: arquivo_bucket arquivo_bucket_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo_bucket
    ADD CONSTRAINT arquivo_bucket_pkey PRIMARY KEY (tenant_id);


--
-- Name: arquivo arquivo_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo
    ADD CONSTRAINT arquivo_pkey PRIMARY KEY (id);


--
-- Name: arquivo_upload arquivo_upload_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo_upload
    ADD CONSTRAINT arquivo_upload_pkey PRIMARY KEY (upload_id);


--
-- Name: auditoria auditoria_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.auditoria
    ADD CONSTRAINT auditoria_pkey PRIMARY KEY (id);


--
-- Name: categoria categoria_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.categoria
    ADD CONSTRAINT categoria_pkey PRIMARY KEY (id);


--
-- Name: compartilhamento_link_item compartilhamento_link_item_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link_item
    ADD CONSTRAINT compartilhamento_link_item_pkey PRIMARY KEY (link_id, item_id);


--
-- Name: compartilhamento_link compartilhamento_link_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link
    ADD CONSTRAINT compartilhamento_link_pkey PRIMARY KEY (id);


--
-- Name: compartilhamento_link compartilhamento_link_token_hash_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link
    ADD CONSTRAINT compartilhamento_link_token_hash_key UNIQUE (token_hash);


--
-- Name: conexao conexao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao
    ADD CONSTRAINT conexao_pkey PRIMARY KEY (id);


--
-- Name: conexao_saude_historico conexao_saude_historico_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao_saude_historico
    ADD CONSTRAINT conexao_saude_historico_pkey PRIMARY KEY (id);


--
-- Name: convite convite_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.convite
    ADD CONSTRAINT convite_pkey PRIMARY KEY (id);


--
-- Name: convite convite_token_hash_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.convite
    ADD CONSTRAINT convite_token_hash_key UNIQUE (token_hash);


--
-- Name: evento evento_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento
    ADD CONSTRAINT evento_pkey PRIMARY KEY (id, em);


--
-- Name: evento_tipo evento_tipo_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento_tipo
    ADD CONSTRAINT evento_tipo_pkey PRIMARY KEY (nome);


--
-- Name: evento_y2026m09 evento_y2026m09_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento_y2026m09
    ADD CONSTRAINT evento_y2026m09_pkey PRIMARY KEY (id, em);


--
-- Name: evento_y2026m10 evento_y2026m10_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento_y2026m10
    ADD CONSTRAINT evento_y2026m10_pkey PRIMARY KEY (id, em);


--
-- Name: evento_y2026m11 evento_y2026m11_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento_y2026m11
    ADD CONSTRAINT evento_y2026m11_pkey PRIMARY KEY (id, em);


--
-- Name: evento_y2026m12 evento_y2026m12_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.evento_y2026m12
    ADD CONSTRAINT evento_y2026m12_pkey PRIMARY KEY (id, em);


--
-- Name: favorito favorito_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.favorito
    ADD CONSTRAINT favorito_pkey PRIMARY KEY (usuario_id, item_id);


--
-- Name: geo_endereco geo_endereco_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_endereco
    ADD CONSTRAINT geo_endereco_pkey PRIMARY KEY (id);


--
-- Name: geo_instalacao geo_instalacao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_instalacao
    ADD CONSTRAINT geo_instalacao_pkey PRIMARY KEY (cod_uf);


--
-- Name: geo_municipio geo_municipio_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_municipio
    ADD CONSTRAINT geo_municipio_pkey PRIMARY KEY (cod);


--
-- Name: geo_uf geo_uf_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_uf
    ADD CONSTRAINT geo_uf_pkey PRIMARY KEY (cod);


--
-- Name: geo_uf geo_uf_sigla_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_uf
    ADD CONSTRAINT geo_uf_sigla_key UNIQUE (sigla);


--
-- Name: grupo_membro grupo_membro_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo_membro
    ADD CONSTRAINT grupo_membro_pkey PRIMARY KEY (grupo_id, usuario_id);


--
-- Name: grupo grupo_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo
    ADD CONSTRAINT grupo_pkey PRIMARY KEY (id);


--
-- Name: importacao importacao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.importacao
    ADD CONSTRAINT importacao_pkey PRIMARY KEY (id);


--
-- Name: item_grupo item_grupo_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_grupo
    ADD CONSTRAINT item_grupo_pkey PRIMARY KEY (item_id, grupo_id);


--
-- Name: item item_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_pkey PRIMARY KEY (id);


--
-- Name: item_relacao item_relacao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_relacao
    ADD CONSTRAINT item_relacao_pkey PRIMARY KEY (origem, destino, tipo);


--
-- Name: item_versao item_versao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_versao
    ADD CONSTRAINT item_versao_pkey PRIMARY KEY (item_id, versao);


--
-- Name: job job_agenda_id_programado_para_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job
    ADD CONSTRAINT job_agenda_id_programado_para_key UNIQUE (agenda_id, programado_para);


--
-- Name: job_log job_log_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job_log
    ADD CONSTRAINT job_log_pkey PRIMARY KEY (id);


--
-- Name: job job_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job
    ADD CONSTRAINT job_pkey PRIMARY KEY (id);


--
-- Name: log_acesso log_acesso_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso
    ADD CONSTRAINT log_acesso_pkey PRIMARY KEY (id, em);


--
-- Name: log_acesso_y2026m09 log_acesso_y2026m09_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso_y2026m09
    ADD CONSTRAINT log_acesso_y2026m09_pkey PRIMARY KEY (id, em);


--
-- Name: log_acesso_y2026m10 log_acesso_y2026m10_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso_y2026m10
    ADD CONSTRAINT log_acesso_y2026m10_pkey PRIMARY KEY (id, em);


--
-- Name: log_acesso_y2026m11 log_acesso_y2026m11_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso_y2026m11
    ADD CONSTRAINT log_acesso_y2026m11_pkey PRIMARY KEY (id, em);


--
-- Name: log_acesso_y2026m12 log_acesso_y2026m12_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.log_acesso_y2026m12
    ADD CONSTRAINT log_acesso_y2026m12_pkey PRIMARY KEY (id, em);


--
-- Name: papel_personalizado papel_personalizado_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_personalizado
    ADD CONSTRAINT papel_personalizado_pkey PRIMARY KEY (id);


--
-- Name: papel_privilegio papel_privilegio_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_privilegio
    ADD CONSTRAINT papel_privilegio_pkey PRIMARY KEY (papel_id, privilegio);


--
-- Name: pasta pasta_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.pasta
    ADD CONSTRAINT pasta_pkey PRIMARY KEY (id);


--
-- Name: perfil_privilegio perfil_privilegio_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.perfil_privilegio
    ADD CONSTRAINT perfil_privilegio_pkey PRIMARY KEY (perfil, privilegio);


--
-- Name: privilegio privilegio_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.privilegio
    ADD CONSTRAINT privilegio_pkey PRIMARY KEY (nome);


--
-- Name: provedor_ldap provedor_ldap_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.provedor_ldap
    ADD CONSTRAINT provedor_ldap_pkey PRIMARY KEY (id);


--
-- Name: provedor_ldap provedor_ldap_tenant_id_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.provedor_ldap
    ADD CONSTRAINT provedor_ldap_tenant_id_key UNIQUE (tenant_id);


--
-- Name: raster_colecao raster_colecao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_colecao
    ADD CONSTRAINT raster_colecao_pkey PRIMARY KEY (colecao);


--
-- Name: raster_item raster_item_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_item
    ADD CONSTRAINT raster_item_pkey PRIMARY KEY (colecao, item_id);


--
-- Name: redefinicao_pedido redefinicao_pedido_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.redefinicao_pedido
    ADD CONSTRAINT redefinicao_pedido_pkey PRIMARY KEY (id);


--
-- Name: redefinicao_senha redefinicao_senha_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.redefinicao_senha
    ADD CONSTRAINT redefinicao_senha_pkey PRIMARY KEY (id);


--
-- Name: redefinicao_senha redefinicao_senha_token_hash_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.redefinicao_senha
    ADD CONSTRAINT redefinicao_senha_token_hash_key UNIQUE (token_hash);


--
-- Name: relacao_tipo relacao_tipo_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.relacao_tipo
    ADD CONSTRAINT relacao_tipo_pkey PRIMARY KEY (nome);


--
-- Name: senha_historico senha_historico_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.senha_historico
    ADD CONSTRAINT senha_historico_pkey PRIMARY KEY (id);


--
-- Name: sessao sessao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.sessao
    ADD CONSTRAINT sessao_pkey PRIMARY KEY (token_hash);


--
-- Name: tenant tenant_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.tenant
    ADD CONSTRAINT tenant_pkey PRIMARY KEY (id);


--
-- Name: tenant tenant_slug_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.tenant
    ADD CONSTRAINT tenant_slug_key UNIQUE (slug);


--
-- Name: tipo_item tipo_item_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.tipo_item
    ADD CONSTRAINT tipo_item_pkey PRIMARY KEY (nome);


--
-- Name: token_servico token_servico_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.token_servico
    ADD CONSTRAINT token_servico_pkey PRIMARY KEY (id);


--
-- Name: token_servico token_servico_token_hash_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.token_servico
    ADD CONSTRAINT token_servico_token_hash_key UNIQUE (token_hash);


--
-- Name: upload_parte upload_parte_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload_parte
    ADD CONSTRAINT upload_parte_pkey PRIMARY KEY (upload_id, n);


--
-- Name: upload upload_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload
    ADD CONSTRAINT upload_pkey PRIMARY KEY (id);


--
-- Name: upload upload_upload_s3_id_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload
    ADD CONSTRAINT upload_upload_s3_id_key UNIQUE (upload_s3_id);


--
-- Name: raster_colecao uq_raster_colecao_slug; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_colecao
    ADD CONSTRAINT uq_raster_colecao_slug UNIQUE (tenant_id, slug);


--
-- Name: usuario usuario_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.usuario
    ADD CONSTRAINT usuario_pkey PRIMARY KEY (id);


--
-- Name: usuario usuario_tenant_id_login_key; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.usuario
    ADD CONSTRAINT usuario_tenant_id_login_key UNIQUE (tenant_id, login);


--
-- Name: versao_migracao versao_migracao_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.versao_migracao
    ADD CONSTRAINT versao_migracao_pkey PRIMARY KEY (nome);


--
-- Name: versao_pgstac versao_pgstac_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.versao_pgstac
    ADD CONSTRAINT versao_pgstac_pkey PRIMARY KEY (versao);


--
-- Name: worker worker_pkey; Type: CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.worker
    ADD CONSTRAINT worker_pkey PRIMARY KEY (nome);


--
-- Name: marcadores marcadores_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.marcadores
    ADD CONSTRAINT marcadores_pkey PRIMARY KEY (job_id, marcador);


--
-- Name: passos passos_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.passos
    ADD CONSTRAINT passos_pkey PRIMARY KEY (job_id, passo);


--
-- Name: zt_expurgo_014165 zt_expurgo_014165_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_014165
    ADD CONSTRAINT zt_expurgo_014165_pkey PRIMARY KEY (id);


--
-- Name: zt_expurgo_267601 zt_expurgo_267601_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_267601
    ADD CONSTRAINT zt_expurgo_267601_pkey PRIMARY KEY (id);


--
-- Name: zt_expurgo_4a33f9 zt_expurgo_4a33f9_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_4a33f9
    ADD CONSTRAINT zt_expurgo_4a33f9_pkey PRIMARY KEY (id);


--
-- Name: zt_expurgo_4c099b zt_expurgo_4c099b_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_expurgo_4c099b
    ADD CONSTRAINT zt_expurgo_4c099b_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_230243 zt_mini_230243_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_230243
    ADD CONSTRAINT zt_mini_230243_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_8f66ef zt_mini_8f66ef_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_8f66ef
    ADD CONSTRAINT zt_mini_8f66ef_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_bd33e7 zt_mini_bd33e7_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_bd33e7
    ADD CONSTRAINT zt_mini_bd33e7_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_be12d3 zt_mini_be12d3_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_be12d3
    ADD CONSTRAINT zt_mini_be12d3_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_c5d81b zt_mini_c5d81b_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_c5d81b
    ADD CONSTRAINT zt_mini_c5d81b_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_c99ac0 zt_mini_c99ac0_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_c99ac0
    ADD CONSTRAINT zt_mini_c99ac0_pkey PRIMARY KEY (id);


--
-- Name: zt_mini_d0bb6e zt_mini_d0bb6e_pkey; Type: CONSTRAINT; Schema: plat_trabalho; Owner: -
--

ALTER TABLE ONLY plat_trabalho.zt_mini_d0bb6e
    ADD CONSTRAINT zt_mini_d0bb6e_pkey PRIMARY KEY (id);


--
-- Name: datetime_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX datetime_idx ON ONLY pgstac.items USING btree (datetime DESC, end_datetime);


--
-- Name: format_item_cache_lastused_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX format_item_cache_lastused_idx ON pgstac.format_item_cache USING btree (lastused);


--
-- Name: geometry_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX geometry_idx ON ONLY pgstac.items USING gist (geometry);


--
-- Name: partition_stats_collection_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX partition_stats_collection_idx ON pgstac.partition_stats USING btree (collection);


--
-- Name: queryables_collection_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX queryables_collection_idx ON pgstac.queryables USING gin (collection_ids);


--
-- Name: queryables_name_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX queryables_name_idx ON pgstac.queryables USING btree (name);


--
-- Name: queryables_property_wrapper_idx; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX queryables_property_wrapper_idx ON pgstac.queryables USING btree (property_wrapper);


--
-- Name: search_wheres_partitions; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE INDEX search_wheres_partitions ON pgstac.search_wheres USING gin (partitions);


--
-- Name: search_wheres_where; Type: INDEX; Schema: pgstac; Owner: -
--

CREATE UNIQUE INDEX search_wheres_where ON pgstac.search_wheres USING btree (md5(_where));


--
-- Name: ix_evento_tenant_em; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_evento_tenant_em ON ONLY plat.evento USING btree (tenant_id, em DESC);


--
-- Name: evento_y2026m09_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m09_tenant_id_em_idx ON plat.evento_y2026m09 USING btree (tenant_id, em DESC);


--
-- Name: ix_evento_tenant_tipo; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_evento_tenant_tipo ON ONLY plat.evento USING btree (tenant_id, tipo, em DESC);


--
-- Name: evento_y2026m09_tenant_id_tipo_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m09_tenant_id_tipo_em_idx ON plat.evento_y2026m09 USING btree (tenant_id, tipo, em DESC);


--
-- Name: evento_y2026m10_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m10_tenant_id_em_idx ON plat.evento_y2026m10 USING btree (tenant_id, em DESC);


--
-- Name: evento_y2026m10_tenant_id_tipo_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m10_tenant_id_tipo_em_idx ON plat.evento_y2026m10 USING btree (tenant_id, tipo, em DESC);


--
-- Name: evento_y2026m11_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m11_tenant_id_em_idx ON plat.evento_y2026m11 USING btree (tenant_id, em DESC);


--
-- Name: evento_y2026m11_tenant_id_tipo_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m11_tenant_id_tipo_em_idx ON plat.evento_y2026m11 USING btree (tenant_id, tipo, em DESC);


--
-- Name: evento_y2026m12_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m12_tenant_id_em_idx ON plat.evento_y2026m12 USING btree (tenant_id, em DESC);


--
-- Name: evento_y2026m12_tenant_id_tipo_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX evento_y2026m12_tenant_id_tipo_em_idx ON plat.evento_y2026m12 USING btree (tenant_id, tipo, em DESC);


--
-- Name: ix_acervo_assinatura_camada; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_acervo_assinatura_camada ON plat.acervo_assinatura USING btree (acervo_camada_id);


--
-- Name: ix_acervo_camada_estado; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_acervo_camada_estado ON plat.acervo_camada USING btree (estado);


--
-- Name: ix_acervo_camada_fonte; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_acervo_camada_fonte ON plat.acervo_camada USING btree (fonte_id);


--
-- Name: ix_acervo_licenca_tipo; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_acervo_licenca_tipo ON plat.acervo_licenca USING btree (tipo);


--
-- Name: ix_agenda_proxima; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_agenda_proxima ON plat.agenda USING btree (proxima_em) WHERE (ativa AND (proxima_em IS NOT NULL));


--
-- Name: ix_amc_conjunto_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_amc_conjunto_tenant ON plat.amc_conjunto_unidade USING btree (tenant_id, criado_em DESC);


--
-- Name: ix_amc_execucao_modelo; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_amc_execucao_modelo ON plat.amc_execucao USING btree (modelo_id, versao_hash);


--
-- Name: ix_amc_execucao_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_amc_execucao_tenant ON plat.amc_execucao USING btree (tenant_id, criado_em DESC);


--
-- Name: ix_amc_modelo_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_amc_modelo_tenant ON plat.amc_modelo USING btree (tenant_id, atualizado_em DESC) WHERE (apagado_em IS NULL);


--
-- Name: ix_amc_unidade_geom; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_amc_unidade_geom ON plat.amc_unidade USING gist (geom);


--
-- Name: ix_amc_unidade_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_amc_unidade_tenant ON plat.amc_unidade USING btree (tenant_id);


--
-- Name: ix_arquivo_chave; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_arquivo_chave ON plat.arquivo USING btree (chave);


--
-- Name: ix_arquivo_dedupe; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ix_arquivo_dedupe ON plat.arquivo USING btree (tenant_id, classe, referencia, sha256) WHERE (apagado_em IS NULL);


--
-- Name: ix_arquivo_tenant_criado; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_arquivo_tenant_criado ON plat.arquivo USING btree (tenant_id, criado_em DESC) WHERE (apagado_em IS NULL);


--
-- Name: ix_auditoria_req; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_auditoria_req ON plat.auditoria USING btree (req_id) WHERE (req_id IS NOT NULL);


--
-- Name: ix_auditoria_tenant_acao; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_auditoria_tenant_acao ON plat.auditoria USING btree (tenant_id, acao, em DESC);


--
-- Name: ix_auditoria_tenant_ator; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_auditoria_tenant_ator ON plat.auditoria USING btree (tenant_id, ator_id, em DESC);


--
-- Name: ix_auditoria_tenant_em; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_auditoria_tenant_em ON plat.auditoria USING btree (tenant_id, em DESC);


--
-- Name: ix_categoria_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_categoria_tenant ON plat.categoria USING btree (tenant_id, pai_id, posicao);


--
-- Name: ix_conexao_saude_historico_conexao; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_conexao_saude_historico_conexao ON plat.conexao_saude_historico USING btree (conexao_id, verificada_em DESC);


--
-- Name: ix_conexao_saude_historico_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_conexao_saude_historico_tenant ON plat.conexao_saude_historico USING btree (tenant_id);


--
-- Name: ix_conexao_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_conexao_tenant ON plat.conexao USING btree (tenant_id);


--
-- Name: ix_convite_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_convite_tenant ON plat.convite USING btree (tenant_id, criado_em DESC);


--
-- Name: ix_favorito_item; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_favorito_item ON plat.favorito USING btree (item_id);


--
-- Name: ix_geo_endereco_cep; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_cep ON plat.geo_endereco USING btree (cep);


--
-- Name: ix_geo_endereco_cod_unico; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_cod_unico ON plat.geo_endereco USING btree (cod_unico_endereco);


--
-- Name: ix_geo_endereco_face; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_face ON plat.geo_endereco USING btree (cod_municipio, face_id, numero);


--
-- Name: ix_geo_endereco_geom; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_geom ON plat.geo_endereco USING gist (geom);


--
-- Name: ix_geo_endereco_localidade_trgm; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_localidade_trgm ON plat.geo_endereco USING gin (localidade_norm public.gin_trgm_ops);


--
-- Name: ix_geo_endereco_logradouro_trgm; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_logradouro_trgm ON plat.geo_endereco USING gin (logradouro_norm public.gin_trgm_ops);


--
-- Name: ix_geo_endereco_municipio; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_endereco_municipio ON plat.geo_endereco USING btree (cod_municipio);


--
-- Name: ix_geo_municipio_nome_trgm; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_municipio_nome_trgm ON plat.geo_municipio USING gin (nome_norm public.gin_trgm_ops);


--
-- Name: ix_geo_municipio_uf; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_geo_municipio_uf ON plat.geo_municipio USING btree (cod_uf);


--
-- Name: ix_grupo_dono; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_grupo_dono ON plat.grupo USING btree (dono_id);


--
-- Name: ix_grupo_membro_usuario; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_grupo_membro_usuario ON plat.grupo_membro USING btree (usuario_id);


--
-- Name: ix_importacao_arquivo; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_importacao_arquivo ON plat.importacao USING btree (arquivo_id);


--
-- Name: ix_importacao_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_importacao_tenant ON plat.importacao USING btree (tenant_id, criado_em DESC);


--
-- Name: ix_item_busca; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_busca ON plat.item USING gin (busca);


--
-- Name: ix_item_categorias; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_categorias ON plat.item USING gin (categorias);


--
-- Name: ix_item_dono; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_dono ON plat.item USING btree (tenant_id, dono_id, modificado_em DESC) WHERE (apagado_em IS NULL);


--
-- Name: ix_item_extent; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_extent ON plat.item USING gist (extent) WHERE (extent IS NOT NULL);


--
-- Name: ix_item_grupo_grupo; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_grupo_grupo ON plat.item_grupo USING btree (grupo_id);


--
-- Name: ix_item_lista; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_lista ON plat.item USING btree (tenant_id, tipo, modificado_em DESC, id DESC) WHERE (apagado_em IS NULL);


--
-- Name: ix_item_lixeira; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_lixeira ON plat.item USING btree (tenant_id, apagado_em) WHERE (apagado_em IS NOT NULL);


--
-- Name: ix_item_pasta; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_pasta ON plat.item USING btree (pasta_id) WHERE (apagado_em IS NULL);


--
-- Name: ix_item_relacao_destino; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_relacao_destino ON plat.item_relacao USING btree (destino);


--
-- Name: ix_item_relacao_origem; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_relacao_origem ON plat.item_relacao USING btree (origem);


--
-- Name: ix_item_tags; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_tags ON plat.item USING gin (tags);


--
-- Name: ix_item_titulo_trgm; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_titulo_trgm ON plat.item USING gin (titulo public.gin_trgm_ops);


--
-- Name: ix_item_versao_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_item_versao_tenant ON plat.item_versao USING btree (tenant_id, criado_em DESC);


--
-- Name: ix_job_chave; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_job_chave ON plat.job USING btree (chave) WHERE ((estado = ANY (ARRAY['pendente'::text, 'rodando'::text])) AND (chave IS NOT NULL));


--
-- Name: ix_job_fila; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_job_fila ON plat.job USING btree (prioridade, agendado_para, criado_em) WHERE (estado = 'pendente'::text);


--
-- Name: ix_job_log_job; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_job_log_job ON plat.job_log USING btree (job_id, id);


--
-- Name: ix_job_rodando; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_job_rodando ON plat.job USING btree (heartbeat_em) WHERE (estado = 'rodando'::text);


--
-- Name: ix_job_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_job_tenant ON plat.job USING btree (tenant_id, criado_em DESC);


--
-- Name: ix_link_item; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_link_item ON plat.compartilhamento_link USING btree (item_id) WHERE (revogado_em IS NULL);


--
-- Name: ix_log_acesso_tenant_em; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_log_acesso_tenant_em ON ONLY plat.log_acesso USING btree (tenant_id, em DESC);


--
-- Name: ix_log_acesso_token_em; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_log_acesso_token_em ON ONLY plat.log_acesso USING btree (token_id, em DESC) WHERE (token_id IS NOT NULL);


--
-- Name: ix_log_acesso_usuario_em; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_log_acesso_usuario_em ON ONLY plat.log_acesso USING btree (tenant_id, usuario_id, em DESC);


--
-- Name: ix_pasta_ancestrais; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_pasta_ancestrais ON plat.pasta USING gin (ancestrais);


--
-- Name: ix_pasta_pai; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_pasta_pai ON plat.pasta USING btree (tenant_id, pai_id);


--
-- Name: ix_raster_colecao_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_raster_colecao_tenant ON plat.raster_colecao USING btree (tenant_id);


--
-- Name: ix_raster_item_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_raster_item_tenant ON plat.raster_item USING btree (tenant_id, colecao, estado);


--
-- Name: ix_redefinicao_pedido_chave_em; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_redefinicao_pedido_chave_em ON plat.redefinicao_pedido USING btree (chave, criado_em DESC);


--
-- Name: ix_redefinicao_usuario; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_redefinicao_usuario ON plat.redefinicao_senha USING btree (usuario_id, criado_em DESC);


--
-- Name: ix_senha_historico_usuario; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_senha_historico_usuario ON plat.senha_historico USING btree (usuario_id, criado_em DESC);


--
-- Name: ix_sessao_usuario; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_sessao_usuario ON plat.sessao USING btree (usuario_id);


--
-- Name: ix_token_tenant; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_token_tenant ON plat.token_servico USING btree (tenant_id);


--
-- Name: ix_upload_expurgo; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_upload_expurgo ON plat.upload USING btree (estado, atualizado_em) WHERE (estado = 'iniciado'::text);


--
-- Name: ix_upload_tenant_estado; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_upload_tenant_estado ON plat.upload USING btree (tenant_id, estado);


--
-- Name: ix_usuario_desafio; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX ix_usuario_desafio ON plat.usuario USING btree (desafio_2fa_hash) WHERE (desafio_2fa_hash IS NOT NULL);


--
-- Name: log_acesso_y2026m09_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m09_tenant_id_em_idx ON plat.log_acesso_y2026m09 USING btree (tenant_id, em DESC);


--
-- Name: log_acesso_y2026m09_tenant_id_usuario_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m09_tenant_id_usuario_id_em_idx ON plat.log_acesso_y2026m09 USING btree (tenant_id, usuario_id, em DESC);


--
-- Name: log_acesso_y2026m09_token_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m09_token_id_em_idx ON plat.log_acesso_y2026m09 USING btree (token_id, em DESC) WHERE (token_id IS NOT NULL);


--
-- Name: log_acesso_y2026m10_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m10_tenant_id_em_idx ON plat.log_acesso_y2026m10 USING btree (tenant_id, em DESC);


--
-- Name: log_acesso_y2026m10_tenant_id_usuario_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m10_tenant_id_usuario_id_em_idx ON plat.log_acesso_y2026m10 USING btree (tenant_id, usuario_id, em DESC);


--
-- Name: log_acesso_y2026m10_token_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m10_token_id_em_idx ON plat.log_acesso_y2026m10 USING btree (token_id, em DESC) WHERE (token_id IS NOT NULL);


--
-- Name: log_acesso_y2026m11_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m11_tenant_id_em_idx ON plat.log_acesso_y2026m11 USING btree (tenant_id, em DESC);


--
-- Name: log_acesso_y2026m11_tenant_id_usuario_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m11_tenant_id_usuario_id_em_idx ON plat.log_acesso_y2026m11 USING btree (tenant_id, usuario_id, em DESC);


--
-- Name: log_acesso_y2026m11_token_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m11_token_id_em_idx ON plat.log_acesso_y2026m11 USING btree (token_id, em DESC) WHERE (token_id IS NOT NULL);


--
-- Name: log_acesso_y2026m12_tenant_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m12_tenant_id_em_idx ON plat.log_acesso_y2026m12 USING btree (tenant_id, em DESC);


--
-- Name: log_acesso_y2026m12_tenant_id_usuario_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m12_tenant_id_usuario_id_em_idx ON plat.log_acesso_y2026m12 USING btree (tenant_id, usuario_id, em DESC);


--
-- Name: log_acesso_y2026m12_token_id_em_idx; Type: INDEX; Schema: plat; Owner: -
--

CREATE INDEX log_acesso_y2026m12_token_id_em_idx ON plat.log_acesso_y2026m12 USING btree (token_id, em DESC) WHERE (token_id IS NOT NULL);


--
-- Name: ux_categoria_codigo; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_categoria_codigo ON plat.categoria USING btree (tenant_id, codigo) WHERE (codigo IS NOT NULL);


--
-- Name: ux_categoria_irmas; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_categoria_irmas ON plat.categoria USING btree (tenant_id, pai_id, lower(nome)) WHERE (pai_id IS NOT NULL);


--
-- Name: ux_categoria_raiz; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_categoria_raiz ON plat.categoria USING btree (tenant_id, lower(nome)) WHERE (pai_id IS NULL);


--
-- Name: ux_conexao_nome; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_conexao_nome ON plat.conexao USING btree (tenant_id, lower(nome));


--
-- Name: ux_grupo_tenant_nome; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_grupo_tenant_nome ON plat.grupo USING btree (tenant_id, lower(nome));


--
-- Name: ux_importacao_item; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_importacao_item ON plat.importacao USING btree (item_id);


--
-- Name: ux_papel_tenant_nome; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_papel_tenant_nome ON plat.papel_personalizado USING btree (tenant_id, lower(nome));


--
-- Name: ux_pasta_irmas; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_pasta_irmas ON plat.pasta USING btree (tenant_id, pai_id, lower(nome)) WHERE (pai_id IS NOT NULL);


--
-- Name: ux_pasta_raiz; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_pasta_raiz ON plat.pasta USING btree (tenant_id, lower(nome)) WHERE (pai_id IS NULL);


--
-- Name: ux_usuario_sujeito_externo; Type: INDEX; Schema: plat; Owner: -
--

CREATE UNIQUE INDEX ux_usuario_sujeito_externo ON plat.usuario USING btree (tenant_id, origem, sujeito_externo) WHERE (sujeito_externo IS NOT NULL);


--
-- Name: evento_y2026m09_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.evento_pkey ATTACH PARTITION plat.evento_y2026m09_pkey;


--
-- Name: evento_y2026m09_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_em ATTACH PARTITION plat.evento_y2026m09_tenant_id_em_idx;


--
-- Name: evento_y2026m09_tenant_id_tipo_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_tipo ATTACH PARTITION plat.evento_y2026m09_tenant_id_tipo_em_idx;


--
-- Name: evento_y2026m10_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.evento_pkey ATTACH PARTITION plat.evento_y2026m10_pkey;


--
-- Name: evento_y2026m10_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_em ATTACH PARTITION plat.evento_y2026m10_tenant_id_em_idx;


--
-- Name: evento_y2026m10_tenant_id_tipo_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_tipo ATTACH PARTITION plat.evento_y2026m10_tenant_id_tipo_em_idx;


--
-- Name: evento_y2026m11_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.evento_pkey ATTACH PARTITION plat.evento_y2026m11_pkey;


--
-- Name: evento_y2026m11_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_em ATTACH PARTITION plat.evento_y2026m11_tenant_id_em_idx;


--
-- Name: evento_y2026m11_tenant_id_tipo_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_tipo ATTACH PARTITION plat.evento_y2026m11_tenant_id_tipo_em_idx;


--
-- Name: evento_y2026m12_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.evento_pkey ATTACH PARTITION plat.evento_y2026m12_pkey;


--
-- Name: evento_y2026m12_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_em ATTACH PARTITION plat.evento_y2026m12_tenant_id_em_idx;


--
-- Name: evento_y2026m12_tenant_id_tipo_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_evento_tenant_tipo ATTACH PARTITION plat.evento_y2026m12_tenant_id_tipo_em_idx;


--
-- Name: log_acesso_y2026m09_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.log_acesso_pkey ATTACH PARTITION plat.log_acesso_y2026m09_pkey;


--
-- Name: log_acesso_y2026m09_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_tenant_em ATTACH PARTITION plat.log_acesso_y2026m09_tenant_id_em_idx;


--
-- Name: log_acesso_y2026m09_tenant_id_usuario_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_usuario_em ATTACH PARTITION plat.log_acesso_y2026m09_tenant_id_usuario_id_em_idx;


--
-- Name: log_acesso_y2026m09_token_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_token_em ATTACH PARTITION plat.log_acesso_y2026m09_token_id_em_idx;


--
-- Name: log_acesso_y2026m10_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.log_acesso_pkey ATTACH PARTITION plat.log_acesso_y2026m10_pkey;


--
-- Name: log_acesso_y2026m10_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_tenant_em ATTACH PARTITION plat.log_acesso_y2026m10_tenant_id_em_idx;


--
-- Name: log_acesso_y2026m10_tenant_id_usuario_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_usuario_em ATTACH PARTITION plat.log_acesso_y2026m10_tenant_id_usuario_id_em_idx;


--
-- Name: log_acesso_y2026m10_token_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_token_em ATTACH PARTITION plat.log_acesso_y2026m10_token_id_em_idx;


--
-- Name: log_acesso_y2026m11_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.log_acesso_pkey ATTACH PARTITION plat.log_acesso_y2026m11_pkey;


--
-- Name: log_acesso_y2026m11_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_tenant_em ATTACH PARTITION plat.log_acesso_y2026m11_tenant_id_em_idx;


--
-- Name: log_acesso_y2026m11_tenant_id_usuario_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_usuario_em ATTACH PARTITION plat.log_acesso_y2026m11_tenant_id_usuario_id_em_idx;


--
-- Name: log_acesso_y2026m11_token_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_token_em ATTACH PARTITION plat.log_acesso_y2026m11_token_id_em_idx;


--
-- Name: log_acesso_y2026m12_pkey; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.log_acesso_pkey ATTACH PARTITION plat.log_acesso_y2026m12_pkey;


--
-- Name: log_acesso_y2026m12_tenant_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_tenant_em ATTACH PARTITION plat.log_acesso_y2026m12_tenant_id_em_idx;


--
-- Name: log_acesso_y2026m12_tenant_id_usuario_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_usuario_em ATTACH PARTITION plat.log_acesso_y2026m12_tenant_id_usuario_id_em_idx;


--
-- Name: log_acesso_y2026m12_token_id_em_idx; Type: INDEX ATTACH; Schema: plat; Owner: -
--

ALTER INDEX plat.ix_log_acesso_token_em ATTACH PARTITION plat.log_acesso_y2026m12_token_id_em_idx;


--
-- Name: datetime_stats; Type: STATISTICS; Schema: pgstac; Owner: -
--

CREATE STATISTICS pgstac.datetime_stats (dependencies) ON datetime, end_datetime FROM pgstac.items;


--
-- Name: collections collection_delete_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER collection_delete_trigger BEFORE DELETE ON pgstac.collections FOR EACH ROW EXECUTE FUNCTION pgstac.collection_delete_trigger_func();


--
-- Name: collections collections_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER collections_trigger AFTER INSERT OR UPDATE ON pgstac.collections FOR EACH ROW EXECUTE FUNCTION pgstac.collections_trigger_func();


--
-- Name: items items_after_delete_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER items_after_delete_trigger AFTER UPDATE ON pgstac.items REFERENCING NEW TABLE AS newdata FOR EACH STATEMENT EXECUTE FUNCTION pgstac.partition_after_triggerfunc();


--
-- Name: items items_after_insert_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER items_after_insert_trigger AFTER INSERT ON pgstac.items REFERENCING NEW TABLE AS newdata FOR EACH STATEMENT EXECUTE FUNCTION pgstac.partition_after_triggerfunc();


--
-- Name: items items_after_update_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER items_after_update_trigger AFTER DELETE ON pgstac.items REFERENCING OLD TABLE AS newdata FOR EACH STATEMENT EXECUTE FUNCTION pgstac.partition_after_triggerfunc();


--
-- Name: items_staging_ignore items_staging_insert_ignore_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER items_staging_insert_ignore_trigger AFTER INSERT ON pgstac.items_staging_ignore REFERENCING NEW TABLE AS newdata FOR EACH STATEMENT EXECUTE FUNCTION pgstac.items_staging_triggerfunc();


--
-- Name: items_staging items_staging_insert_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER items_staging_insert_trigger AFTER INSERT ON pgstac.items_staging REFERENCING NEW TABLE AS newdata FOR EACH STATEMENT EXECUTE FUNCTION pgstac.items_staging_triggerfunc();


--
-- Name: items_staging_upsert items_staging_insert_upsert_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER items_staging_insert_upsert_trigger AFTER INSERT ON pgstac.items_staging_upsert REFERENCING NEW TABLE AS newdata FOR EACH STATEMENT EXECUTE FUNCTION pgstac.items_staging_triggerfunc();


--
-- Name: queryables queryables_constraint_insert_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER queryables_constraint_insert_trigger BEFORE INSERT ON pgstac.queryables FOR EACH ROW EXECUTE FUNCTION pgstac.queryables_constraint_triggerfunc();


--
-- Name: queryables queryables_constraint_update_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER queryables_constraint_update_trigger BEFORE UPDATE ON pgstac.queryables FOR EACH ROW WHEN (((new.name = old.name) AND (new.collection_ids IS DISTINCT FROM old.collection_ids))) EXECUTE FUNCTION pgstac.queryables_constraint_triggerfunc();


--
-- Name: queryables queryables_trigger; Type: TRIGGER; Schema: pgstac; Owner: -
--

CREATE TRIGGER queryables_trigger AFTER INSERT OR UPDATE ON pgstac.queryables FOR EACH STATEMENT EXECUTE FUNCTION pgstac.queryables_trigger_func();


--
-- Name: amc_execucao amc_execucao_guarda; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER amc_execucao_guarda BEFORE DELETE OR UPDATE ON plat.amc_execucao FOR EACH ROW EXECUTE FUNCTION plat.amc_execucao_guarda();


--
-- Name: amc_fator_bruto amc_fator_bruto_guarda; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER amc_fator_bruto_guarda BEFORE DELETE OR UPDATE ON plat.amc_fator_bruto FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_guarda();


--
-- Name: amc_modelo amc_modelo_guarda; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER amc_modelo_guarda BEFORE DELETE OR UPDATE ON plat.amc_modelo FOR EACH ROW EXECUTE FUNCTION plat.amc_modelo_guarda();


--
-- Name: amc_modelo_versao amc_modelo_versao_imutavel; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER amc_modelo_versao_imutavel BEFORE DELETE OR UPDATE ON plat.amc_modelo_versao FOR EACH ROW EXECUTE FUNCTION plat.amc_versao_imutavel();


--
-- Name: amc_resultado amc_resultado_guarda; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER amc_resultado_guarda BEFORE DELETE OR UPDATE ON plat.amc_resultado FOR EACH ROW EXECUTE FUNCTION plat.amc_materializado_guarda();


--
-- Name: auditoria auditoria_imutavel; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER auditoria_imutavel BEFORE DELETE OR UPDATE ON plat.auditoria FOR EACH ROW EXECUTE FUNCTION plat.tg_auditoria_imutavel();


--
-- Name: auditoria auditoria_sem_truncate; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER auditoria_sem_truncate BEFORE TRUNCATE ON plat.auditoria FOR EACH STATEMENT EXECUTE FUNCTION plat.tg_auditoria_sem_truncate();


--
-- Name: categoria categoria_arvore; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER categoria_arvore BEFORE INSERT OR UPDATE OF nome, pai_id ON plat.categoria FOR EACH ROW EXECUTE FUNCTION plat.tg_categoria();


--
-- Name: conexao conexao_atualizado_em; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER conexao_atualizado_em BEFORE UPDATE ON plat.conexao FOR EACH ROW EXECUTE FUNCTION plat.tg_conexao_atualizado_em();


--
-- Name: evento evento_auditoria; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER evento_auditoria AFTER INSERT ON plat.evento FOR EACH ROW EXECUTE FUNCTION plat.tg_evento_auditoria();


--
-- Name: grupo grupo_dono_coerente; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER grupo_dono_coerente AFTER INSERT OR UPDATE OF dono_id ON plat.grupo FOR EACH ROW EXECUTE FUNCTION plat.tg_grupo_dono_coerente();


--
-- Name: grupo_membro grupo_membro_coerente; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER grupo_membro_coerente BEFORE INSERT OR DELETE OR UPDATE ON plat.grupo_membro FOR EACH ROW EXECUTE FUNCTION plat.tg_grupo_membro_coerente();


--
-- Name: importacao importacao_estado_final_imutavel; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER importacao_estado_final_imutavel BEFORE UPDATE ON plat.importacao FOR EACH ROW EXECUTE FUNCTION plat.importacao_estado_final_imutavel();


--
-- Name: item item_antes; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER item_antes BEFORE INSERT OR UPDATE ON plat.item FOR EACH ROW EXECUTE FUNCTION plat.tg_item_antes();


--
-- Name: item_grupo item_grupo_coerente; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER item_grupo_coerente BEFORE INSERT OR UPDATE ON plat.item_grupo FOR EACH ROW EXECUTE FUNCTION plat.tg_item_grupo();


--
-- Name: item_relacao item_relacao_coerente; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER item_relacao_coerente BEFORE INSERT OR UPDATE ON plat.item_relacao FOR EACH ROW EXECUTE FUNCTION plat.tg_item_relacao();


--
-- Name: item item_versao; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER item_versao AFTER INSERT OR UPDATE ON plat.item FOR EACH ROW EXECUTE FUNCTION plat.tg_item_versao();


--
-- Name: job job_estado_final_imutavel; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER job_estado_final_imutavel BEFORE UPDATE ON plat.job FOR EACH ROW EXECUTE FUNCTION plat.job_estado_final_imutavel();


--
-- Name: job_log job_log_notificar; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER job_log_notificar AFTER INSERT ON plat.job_log FOR EACH ROW EXECUTE FUNCTION plat.job_log_notificar();


--
-- Name: job job_notificar; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER job_notificar AFTER INSERT OR UPDATE OF estado, progresso, mensagem, cancelar_solicitado, agendado_para ON plat.job FOR EACH ROW EXECUTE FUNCTION plat.job_notificar();


--
-- Name: job job_transicao; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER job_transicao BEFORE INSERT OR UPDATE ON plat.job FOR EACH ROW EXECUTE FUNCTION plat.job_transicao();


--
-- Name: pasta pasta_caminho; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER pasta_caminho BEFORE INSERT OR UPDATE OF pai_id ON plat.pasta FOR EACH ROW EXECUTE FUNCTION plat.tg_pasta_caminho();


--
-- Name: pasta pasta_vazia; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER pasta_vazia BEFORE DELETE ON plat.pasta FOR EACH ROW EXECUTE FUNCTION plat.tg_pasta_vazia();


--
-- Name: tenant tg_tenant_cota_guarda; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER tg_tenant_cota_guarda BEFORE UPDATE ON plat.tenant FOR EACH ROW EXECUTE FUNCTION plat.tenant_cota_guarda();


--
-- Name: usuario usuario_superadmin_so_plataforma; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER usuario_superadmin_so_plataforma BEFORE INSERT OR UPDATE OF superadmin, tenant_id ON plat.usuario FOR EACH ROW EXECUTE FUNCTION plat.tg_usuario_superadmin();


--
-- Name: usuario usuario_ultimo_admin; Type: TRIGGER; Schema: plat; Owner: -
--

CREATE TRIGGER usuario_ultimo_admin BEFORE DELETE OR UPDATE ON plat.usuario FOR EACH ROW EXECUTE FUNCTION plat.tg_usuario_ultimo_admin();


--
-- Name: items items_collections_fk; Type: FK CONSTRAINT; Schema: pgstac; Owner: -
--

ALTER TABLE pgstac.items
    ADD CONSTRAINT items_collections_fk FOREIGN KEY (collection) REFERENCES pgstac.collections(id) ON DELETE CASCADE DEFERRABLE;


--
-- Name: acervo_assinatura acervo_assinatura_acervo_camada_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_assinatura
    ADD CONSTRAINT acervo_assinatura_acervo_camada_id_fkey FOREIGN KEY (acervo_camada_id) REFERENCES plat.acervo_camada(acervo_camada_id) ON DELETE CASCADE;


--
-- Name: acervo_assinatura acervo_assinatura_assinado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_assinatura
    ADD CONSTRAINT acervo_assinatura_assinado_por_fkey FOREIGN KEY (assinado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: acervo_assinatura acervo_assinatura_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_assinatura
    ADD CONSTRAINT acervo_assinatura_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id) ON DELETE CASCADE;


--
-- Name: acervo_lgpd acervo_lgpd_fonte_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_lgpd
    ADD CONSTRAINT acervo_lgpd_fonte_id_fkey FOREIGN KEY (fonte_id) REFERENCES acervo.fonte(fonte_id);


--
-- Name: acervo_licenca acervo_licenca_fonte_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_licenca
    ADD CONSTRAINT acervo_licenca_fonte_id_fkey FOREIGN KEY (fonte_id) REFERENCES acervo.fonte(fonte_id);


--
-- Name: acervo_publicacao acervo_publicacao_acervo_camada_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.acervo_publicacao
    ADD CONSTRAINT acervo_publicacao_acervo_camada_id_fkey FOREIGN KEY (acervo_camada_id) REFERENCES plat.acervo_camada(acervo_camada_id) ON DELETE CASCADE;


--
-- Name: agenda agenda_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.agenda
    ADD CONSTRAINT agenda_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: agenda agenda_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.agenda
    ADD CONSTRAINT agenda_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id);


--
-- Name: amc_conjunto_unidade amc_conjunto_unidade_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_conjunto_unidade
    ADD CONSTRAINT amc_conjunto_unidade_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: amc_conjunto_unidade amc_conjunto_unidade_srid_trabalho_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_conjunto_unidade
    ADD CONSTRAINT amc_conjunto_unidade_srid_trabalho_fkey FOREIGN KEY (srid_trabalho) REFERENCES public.spatial_ref_sys(srid);


--
-- Name: amc_conjunto_unidade amc_conjunto_unidade_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_conjunto_unidade
    ADD CONSTRAINT amc_conjunto_unidade_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: amc_execucao amc_execucao_conjunto_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_execucao
    ADD CONSTRAINT amc_execucao_conjunto_id_fkey FOREIGN KEY (conjunto_id) REFERENCES plat.amc_conjunto_unidade(id) ON DELETE RESTRICT;


--
-- Name: amc_execucao amc_execucao_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_execucao
    ADD CONSTRAINT amc_execucao_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: amc_execucao amc_execucao_modelo_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_execucao
    ADD CONSTRAINT amc_execucao_modelo_id_fkey FOREIGN KEY (modelo_id) REFERENCES plat.amc_modelo(id);


--
-- Name: amc_execucao amc_execucao_modelo_id_versao_hash_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_execucao
    ADD CONSTRAINT amc_execucao_modelo_id_versao_hash_fkey FOREIGN KEY (modelo_id, versao_hash) REFERENCES plat.amc_modelo_versao(modelo_id, versao_hash);


--
-- Name: amc_execucao amc_execucao_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_execucao
    ADD CONSTRAINT amc_execucao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: amc_fator_bruto amc_fator_bruto_execucao_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_fator_bruto
    ADD CONSTRAINT amc_fator_bruto_execucao_id_fkey FOREIGN KEY (execucao_id) REFERENCES plat.amc_execucao(id) ON DELETE CASCADE;


--
-- Name: amc_fator_bruto amc_fator_bruto_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_fator_bruto
    ADD CONSTRAINT amc_fator_bruto_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: amc_modelo amc_modelo_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo
    ADD CONSTRAINT amc_modelo_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: amc_modelo amc_modelo_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo
    ADD CONSTRAINT amc_modelo_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: amc_modelo amc_modelo_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo
    ADD CONSTRAINT amc_modelo_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: amc_modelo_versao amc_modelo_versao_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo_versao
    ADD CONSTRAINT amc_modelo_versao_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: amc_modelo_versao amc_modelo_versao_modelo_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo_versao
    ADD CONSTRAINT amc_modelo_versao_modelo_id_fkey FOREIGN KEY (modelo_id) REFERENCES plat.amc_modelo(id) ON DELETE CASCADE;


--
-- Name: amc_modelo_versao amc_modelo_versao_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo_versao
    ADD CONSTRAINT amc_modelo_versao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: amc_resultado amc_resultado_execucao_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_resultado
    ADD CONSTRAINT amc_resultado_execucao_id_fkey FOREIGN KEY (execucao_id) REFERENCES plat.amc_execucao(id) ON DELETE CASCADE;


--
-- Name: amc_resultado amc_resultado_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_resultado
    ADD CONSTRAINT amc_resultado_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: amc_unidade amc_unidade_conjunto_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_unidade
    ADD CONSTRAINT amc_unidade_conjunto_id_fkey FOREIGN KEY (conjunto_id) REFERENCES plat.amc_conjunto_unidade(id) ON DELETE CASCADE;


--
-- Name: amc_unidade amc_unidade_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_unidade
    ADD CONSTRAINT amc_unidade_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: arquivo_bucket arquivo_bucket_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo_bucket
    ADD CONSTRAINT arquivo_bucket_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: arquivo arquivo_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo
    ADD CONSTRAINT arquivo_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id);


--
-- Name: arquivo arquivo_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo
    ADD CONSTRAINT arquivo_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: arquivo_upload arquivo_upload_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.arquivo_upload
    ADD CONSTRAINT arquivo_upload_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: categoria categoria_pai_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.categoria
    ADD CONSTRAINT categoria_pai_id_fkey FOREIGN KEY (pai_id) REFERENCES plat.categoria(id) ON DELETE RESTRICT;


--
-- Name: categoria categoria_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.categoria
    ADD CONSTRAINT categoria_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: compartilhamento_link compartilhamento_link_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link
    ADD CONSTRAINT compartilhamento_link_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: compartilhamento_link compartilhamento_link_item_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link
    ADD CONSTRAINT compartilhamento_link_item_id_fkey FOREIGN KEY (item_id) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: compartilhamento_link_item compartilhamento_link_item_item_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link_item
    ADD CONSTRAINT compartilhamento_link_item_item_id_fkey FOREIGN KEY (item_id) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: compartilhamento_link_item compartilhamento_link_item_link_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link_item
    ADD CONSTRAINT compartilhamento_link_item_link_id_fkey FOREIGN KEY (link_id) REFERENCES plat.compartilhamento_link(id) ON DELETE CASCADE;


--
-- Name: compartilhamento_link compartilhamento_link_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.compartilhamento_link
    ADD CONSTRAINT compartilhamento_link_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: conexao conexao_dono_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao
    ADD CONSTRAINT conexao_dono_id_fkey FOREIGN KEY (dono_id) REFERENCES plat.usuario(id);


--
-- Name: conexao_saude_historico conexao_saude_historico_conexao_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao_saude_historico
    ADD CONSTRAINT conexao_saude_historico_conexao_id_fkey FOREIGN KEY (conexao_id) REFERENCES plat.conexao(id) ON DELETE CASCADE;


--
-- Name: conexao_saude_historico conexao_saude_historico_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao_saude_historico
    ADD CONSTRAINT conexao_saude_historico_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: conexao conexao_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.conexao
    ADD CONSTRAINT conexao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: convite convite_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.convite
    ADD CONSTRAINT convite_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id);


--
-- Name: convite convite_papel_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.convite
    ADD CONSTRAINT convite_papel_id_fkey FOREIGN KEY (papel_id) REFERENCES plat.papel_personalizado(id);


--
-- Name: convite convite_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.convite
    ADD CONSTRAINT convite_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: convite convite_usuario_criado_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.convite
    ADD CONSTRAINT convite_usuario_criado_id_fkey FOREIGN KEY (usuario_criado_id) REFERENCES plat.usuario(id);


--
-- Name: evento evento_tipo_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE plat.evento
    ADD CONSTRAINT evento_tipo_fkey FOREIGN KEY (tipo) REFERENCES plat.evento_tipo(nome);


--
-- Name: favorito favorito_item_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.favorito
    ADD CONSTRAINT favorito_item_id_fkey FOREIGN KEY (item_id) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: favorito favorito_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.favorito
    ADD CONSTRAINT favorito_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id) ON DELETE CASCADE;


--
-- Name: amc_modelo fk_amc_modelo_versao_atual; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.amc_modelo
    ADD CONSTRAINT fk_amc_modelo_versao_atual FOREIGN KEY (id, versao_hash) REFERENCES plat.amc_modelo_versao(modelo_id, versao_hash) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: geo_municipio geo_municipio_cod_uf_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.geo_municipio
    ADD CONSTRAINT geo_municipio_cod_uf_fkey FOREIGN KEY (cod_uf) REFERENCES plat.geo_uf(cod);


--
-- Name: grupo grupo_dono_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo
    ADD CONSTRAINT grupo_dono_id_fkey FOREIGN KEY (dono_id) REFERENCES plat.usuario(id);


--
-- Name: grupo_membro grupo_membro_convidado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo_membro
    ADD CONSTRAINT grupo_membro_convidado_por_fkey FOREIGN KEY (convidado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: grupo_membro grupo_membro_grupo_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo_membro
    ADD CONSTRAINT grupo_membro_grupo_id_fkey FOREIGN KEY (grupo_id) REFERENCES plat.grupo(id) ON DELETE CASCADE;


--
-- Name: grupo_membro grupo_membro_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo_membro
    ADD CONSTRAINT grupo_membro_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: grupo_membro grupo_membro_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo_membro
    ADD CONSTRAINT grupo_membro_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id) ON DELETE CASCADE;


--
-- Name: grupo grupo_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.grupo
    ADD CONSTRAINT grupo_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: importacao importacao_arquivo_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.importacao
    ADD CONSTRAINT importacao_arquivo_id_fkey FOREIGN KEY (arquivo_id) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: importacao importacao_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.importacao
    ADD CONSTRAINT importacao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: importacao importacao_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.importacao
    ADD CONSTRAINT importacao_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id);


--
-- Name: item item_apagado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_apagado_por_fkey FOREIGN KEY (apagado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: item item_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: item item_dono_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_dono_id_fkey FOREIGN KEY (dono_id) REFERENCES plat.usuario(id);


--
-- Name: item_grupo item_grupo_grupo_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_grupo
    ADD CONSTRAINT item_grupo_grupo_id_fkey FOREIGN KEY (grupo_id) REFERENCES plat.grupo(id) ON DELETE CASCADE;


--
-- Name: item_grupo item_grupo_item_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_grupo
    ADD CONSTRAINT item_grupo_item_id_fkey FOREIGN KEY (item_id) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: item item_modificado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_modificado_por_fkey FOREIGN KEY (modificado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: item item_pasta_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_pasta_id_fkey FOREIGN KEY (pasta_id) REFERENCES plat.pasta(id) ON DELETE SET NULL;


--
-- Name: item_relacao item_relacao_destino_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_relacao
    ADD CONSTRAINT item_relacao_destino_fkey FOREIGN KEY (destino) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: item_relacao item_relacao_origem_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_relacao
    ADD CONSTRAINT item_relacao_origem_fkey FOREIGN KEY (origem) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: item_relacao item_relacao_tipo_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_relacao
    ADD CONSTRAINT item_relacao_tipo_fkey FOREIGN KEY (tipo) REFERENCES plat.relacao_tipo(nome);


--
-- Name: item item_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: item item_tipo_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item
    ADD CONSTRAINT item_tipo_fkey FOREIGN KEY (tipo) REFERENCES plat.tipo_item(nome);


--
-- Name: item_versao item_versao_item_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.item_versao
    ADD CONSTRAINT item_versao_item_id_fkey FOREIGN KEY (item_id) REFERENCES plat.item(id) ON DELETE CASCADE;


--
-- Name: job_log job_log_job_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job_log
    ADD CONSTRAINT job_log_job_id_fkey FOREIGN KEY (job_id) REFERENCES plat.job(id) ON DELETE CASCADE;


--
-- Name: job job_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job
    ADD CONSTRAINT job_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: job job_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.job
    ADD CONSTRAINT job_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id);


--
-- Name: papel_personalizado papel_personalizado_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_personalizado
    ADD CONSTRAINT papel_personalizado_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: papel_personalizado papel_personalizado_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_personalizado
    ADD CONSTRAINT papel_personalizado_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: papel_privilegio papel_privilegio_papel_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_privilegio
    ADD CONSTRAINT papel_privilegio_papel_id_fkey FOREIGN KEY (papel_id) REFERENCES plat.papel_personalizado(id) ON DELETE CASCADE;


--
-- Name: papel_privilegio papel_privilegio_privilegio_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.papel_privilegio
    ADD CONSTRAINT papel_privilegio_privilegio_fkey FOREIGN KEY (privilegio) REFERENCES plat.privilegio(nome);


--
-- Name: pasta pasta_dono_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.pasta
    ADD CONSTRAINT pasta_dono_id_fkey FOREIGN KEY (dono_id) REFERENCES plat.usuario(id);


--
-- Name: pasta pasta_pai_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.pasta
    ADD CONSTRAINT pasta_pai_id_fkey FOREIGN KEY (pai_id) REFERENCES plat.pasta(id) ON DELETE RESTRICT;


--
-- Name: pasta pasta_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.pasta
    ADD CONSTRAINT pasta_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: perfil_privilegio perfil_privilegio_privilegio_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.perfil_privilegio
    ADD CONSTRAINT perfil_privilegio_privilegio_fkey FOREIGN KEY (privilegio) REFERENCES plat.privilegio(nome);


--
-- Name: provedor_ldap provedor_ldap_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.provedor_ldap
    ADD CONSTRAINT provedor_ldap_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: provedor_ldap provedor_ldap_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.provedor_ldap
    ADD CONSTRAINT provedor_ldap_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;


--
-- Name: provedor_ldap provedor_ldap_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.provedor_ldap
    ADD CONSTRAINT provedor_ldap_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: raster_colecao raster_colecao_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_colecao
    ADD CONSTRAINT raster_colecao_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id);


--
-- Name: raster_colecao raster_colecao_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_colecao
    ADD CONSTRAINT raster_colecao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: raster_item raster_item_colecao_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_item
    ADD CONSTRAINT raster_item_colecao_fkey FOREIGN KEY (colecao) REFERENCES plat.raster_colecao(colecao) ON DELETE CASCADE;


--
-- Name: raster_item raster_item_criado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_item
    ADD CONSTRAINT raster_item_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES plat.usuario(id);


--
-- Name: raster_item raster_item_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.raster_item
    ADD CONSTRAINT raster_item_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: redefinicao_senha redefinicao_senha_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.redefinicao_senha
    ADD CONSTRAINT redefinicao_senha_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: redefinicao_senha redefinicao_senha_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.redefinicao_senha
    ADD CONSTRAINT redefinicao_senha_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id) ON DELETE CASCADE;


--
-- Name: senha_historico senha_historico_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.senha_historico
    ADD CONSTRAINT senha_historico_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id) ON DELETE CASCADE;


--
-- Name: sessao sessao_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.sessao
    ADD CONSTRAINT sessao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: sessao sessao_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.sessao
    ADD CONSTRAINT sessao_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id) ON DELETE CASCADE;


--
-- Name: token_servico token_servico_renovado_por_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.token_servico
    ADD CONSTRAINT token_servico_renovado_por_fkey FOREIGN KEY (renovado_por) REFERENCES plat.token_servico(id);


--
-- Name: token_servico token_servico_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.token_servico
    ADD CONSTRAINT token_servico_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: token_servico token_servico_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.token_servico
    ADD CONSTRAINT token_servico_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id) ON DELETE CASCADE;


--
-- Name: upload upload_arquivo_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload
    ADD CONSTRAINT upload_arquivo_id_fkey FOREIGN KEY (arquivo_id) REFERENCES plat.item(id);


--
-- Name: upload_parte upload_parte_upload_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload_parte
    ADD CONSTRAINT upload_parte_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES plat.upload(id) ON DELETE CASCADE;


--
-- Name: upload upload_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload
    ADD CONSTRAINT upload_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: upload upload_usuario_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.upload
    ADD CONSTRAINT upload_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES plat.usuario(id);


--
-- Name: usuario usuario_papel_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.usuario
    ADD CONSTRAINT usuario_papel_id_fkey FOREIGN KEY (papel_id) REFERENCES plat.papel_personalizado(id);


--
-- Name: usuario usuario_tenant_id_fkey; Type: FK CONSTRAINT; Schema: plat; Owner: -
--

ALTER TABLE ONLY plat.usuario
    ADD CONSTRAINT usuario_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES plat.tenant(id);


--
-- Name: acervo_assinatura; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.acervo_assinatura ENABLE ROW LEVEL SECURITY;

--
-- Name: agenda; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.agenda ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_conjunto_unidade; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_conjunto_unidade ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_execucao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_execucao ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_fator_bruto; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_fator_bruto ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_modelo; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_modelo ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_modelo_versao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_modelo_versao ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_resultado; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_resultado ENABLE ROW LEVEL SECURITY;

--
-- Name: amc_unidade; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.amc_unidade ENABLE ROW LEVEL SECURITY;

--
-- Name: arquivo; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.arquivo ENABLE ROW LEVEL SECURITY;

--
-- Name: arquivo_bucket; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.arquivo_bucket ENABLE ROW LEVEL SECURITY;

--
-- Name: arquivo_upload; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.arquivo_upload ENABLE ROW LEVEL SECURITY;

--
-- Name: auditoria; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.auditoria ENABLE ROW LEVEL SECURITY;

--
-- Name: categoria; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.categoria ENABLE ROW LEVEL SECURITY;

--
-- Name: compartilhamento_link; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.compartilhamento_link ENABLE ROW LEVEL SECURITY;

--
-- Name: compartilhamento_link_item; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.compartilhamento_link_item ENABLE ROW LEVEL SECURITY;

--
-- Name: conexao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.conexao ENABLE ROW LEVEL SECURITY;

--
-- Name: conexao_saude_historico; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.conexao_saude_historico ENABLE ROW LEVEL SECURITY;

--
-- Name: convite; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.convite ENABLE ROW LEVEL SECURITY;

--
-- Name: evento; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.evento ENABLE ROW LEVEL SECURITY;

--
-- Name: evento_y2026m09; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.evento_y2026m09 ENABLE ROW LEVEL SECURITY;

--
-- Name: evento_y2026m10; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.evento_y2026m10 ENABLE ROW LEVEL SECURITY;

--
-- Name: evento_y2026m11; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.evento_y2026m11 ENABLE ROW LEVEL SECURITY;

--
-- Name: evento_y2026m12; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.evento_y2026m12 ENABLE ROW LEVEL SECURITY;

--
-- Name: favorito; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.favorito ENABLE ROW LEVEL SECURITY;

--
-- Name: grupo; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.grupo ENABLE ROW LEVEL SECURITY;

--
-- Name: grupo_membro; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.grupo_membro ENABLE ROW LEVEL SECURITY;

--
-- Name: importacao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.importacao ENABLE ROW LEVEL SECURITY;

--
-- Name: item; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.item ENABLE ROW LEVEL SECURITY;

--
-- Name: item_grupo; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.item_grupo ENABLE ROW LEVEL SECURITY;

--
-- Name: item_relacao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.item_relacao ENABLE ROW LEVEL SECURITY;

--
-- Name: item_versao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.item_versao ENABLE ROW LEVEL SECURITY;

--
-- Name: job; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.job ENABLE ROW LEVEL SECURITY;

--
-- Name: job_log; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.job_log ENABLE ROW LEVEL SECURITY;

--
-- Name: log_acesso; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.log_acesso ENABLE ROW LEVEL SECURITY;

--
-- Name: log_acesso_y2026m09; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.log_acesso_y2026m09 ENABLE ROW LEVEL SECURITY;

--
-- Name: log_acesso_y2026m10; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.log_acesso_y2026m10 ENABLE ROW LEVEL SECURITY;

--
-- Name: log_acesso_y2026m11; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.log_acesso_y2026m11 ENABLE ROW LEVEL SECURITY;

--
-- Name: log_acesso_y2026m12; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.log_acesso_y2026m12 ENABLE ROW LEVEL SECURITY;

--
-- Name: acervo_assinatura p_acervo_assinatura_apagar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_acervo_assinatura_apagar ON plat.acervo_assinatura FOR DELETE TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: acervo_assinatura p_acervo_assinatura_inserir; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_acervo_assinatura_inserir ON plat.acervo_assinatura FOR INSERT TO plat_app WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: acervo_assinatura p_acervo_assinatura_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_acervo_assinatura_ler ON plat.acervo_assinatura FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: agenda p_agenda; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_agenda ON plat.agenda TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_conjunto_unidade p_amc_conjunto_unidade; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_conjunto_unidade ON plat.amc_conjunto_unidade TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_execucao p_amc_execucao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_execucao ON plat.amc_execucao TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_fator_bruto p_amc_fator_bruto; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_fator_bruto ON plat.amc_fator_bruto TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_modelo p_amc_modelo; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_modelo ON plat.amc_modelo TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_modelo_versao p_amc_modelo_versao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_modelo_versao ON plat.amc_modelo_versao TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_resultado p_amc_resultado; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_resultado ON plat.amc_resultado TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: amc_unidade p_amc_unidade; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_amc_unidade ON plat.amc_unidade TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: arquivo p_arquivo; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_arquivo ON plat.arquivo TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: arquivo_bucket p_arquivo_bucket; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_arquivo_bucket ON plat.arquivo_bucket TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: arquivo_upload p_arquivo_upload; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_arquivo_upload ON plat.arquivo_upload TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: auditoria p_auditoria; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_auditoria ON plat.auditoria FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: categoria p_categoria_escrever; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_categoria_escrever ON plat.categoria TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.tem('conteudo.categorias'::text))) WITH CHECK (((tenant_id = plat.tenant_atual()) AND plat.tem('conteudo.categorias'::text)));


--
-- Name: categoria p_categoria_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_categoria_ler ON plat.categoria FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: conexao p_conexao_alterar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_conexao_alterar ON plat.conexao FOR UPDATE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND ((dono_id = plat.usuario_atual()) OR plat.tem('conteudo.editar_tudo'::text)))) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: conexao p_conexao_apagar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_conexao_apagar ON plat.conexao FOR DELETE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND ((dono_id = plat.usuario_atual()) OR plat.tem('conteudo.editar_tudo'::text))));


--
-- Name: conexao p_conexao_inserir; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_conexao_inserir ON plat.conexao FOR INSERT TO plat_app WITH CHECK (((tenant_id = plat.tenant_atual()) AND (dono_id = plat.usuario_atual()) AND plat.usuario_do_inquilino()));


--
-- Name: conexao p_conexao_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_conexao_ler ON plat.conexao FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: conexao_saude_historico p_conexao_saude_historico_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_conexao_saude_historico_ler ON plat.conexao_saude_historico FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: convite p_convite; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_convite ON plat.convite TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: evento p_evento; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_evento ON plat.evento FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: evento_y2026m09 p_evento_y2026m09; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_evento_y2026m09 ON plat.evento_y2026m09 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: evento_y2026m10 p_evento_y2026m10; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_evento_y2026m10 ON plat.evento_y2026m10 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: evento_y2026m11 p_evento_y2026m11; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_evento_y2026m11 ON plat.evento_y2026m11 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: evento_y2026m12 p_evento_y2026m12; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_evento_y2026m12 ON plat.evento_y2026m12 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: favorito p_favorito; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_favorito ON plat.favorito TO plat_app USING (((tenant_id = plat.tenant_atual()) AND (usuario_id = plat.usuario_atual()))) WITH CHECK (((tenant_id = plat.tenant_atual()) AND (usuario_id = plat.usuario_atual()) AND plat.pode_ler(item_id)));


--
-- Name: grupo p_grupo_alterar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_grupo_alterar ON plat.grupo FOR UPDATE TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: grupo p_grupo_apagar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_grupo_apagar ON plat.grupo FOR DELETE TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: grupo p_grupo_inserir; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_grupo_inserir ON plat.grupo FOR INSERT TO plat_app WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: grupo p_grupo_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_grupo_ler ON plat.grupo FOR SELECT TO plat_app USING (((tenant_id = plat.tenant_atual()) AND (((visibilidade = 'inquilino'::text) AND plat.tem('grupos.ver_inquilino'::text)) OR plat.tem('grupos.gerir_todos'::text) OR (EXISTS ( SELECT 1
   FROM plat.grupo_membro m
  WHERE ((m.grupo_id = grupo.id) AND (m.usuario_id = plat.usuario_atual())))))));


--
-- Name: grupo_membro p_grupo_membro; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_grupo_membro ON plat.grupo_membro TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: importacao p_importacao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_importacao ON plat.importacao TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: item p_item_alterar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_alterar ON plat.item FOR UPDATE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(id))) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: item p_item_apagar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_apagar ON plat.item FOR DELETE TO plat_app USING (false);


--
-- Name: item_grupo p_item_grupo_alterar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_grupo_alterar ON plat.item_grupo FOR UPDATE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(item_id))) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: item_grupo p_item_grupo_apagar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_grupo_apagar ON plat.item_grupo FOR DELETE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(item_id)));


--
-- Name: item_grupo p_item_grupo_inserir; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_grupo_inserir ON plat.item_grupo FOR INSERT TO plat_app WITH CHECK (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(item_id)));


--
-- Name: item_grupo p_item_grupo_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_grupo_ler ON plat.item_grupo FOR SELECT TO plat_app USING (((tenant_id = plat.tenant_atual()) AND (plat.pode_ler(item_id) OR (EXISTS ( SELECT 1
   FROM plat.grupo_membro m
  WHERE ((m.grupo_id = m.grupo_id) AND (m.usuario_id = plat.usuario_atual()) AND (m.estado = 'ativo'::text)))))));


--
-- Name: item p_item_inserir; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_inserir ON plat.item FOR INSERT TO plat_app WITH CHECK (((tenant_id = plat.tenant_atual()) AND (plat.usuario_atual() IS NOT NULL) AND (dono_id = plat.usuario_atual()) AND plat.usuario_do_inquilino() AND plat.tem('conteudo.criar'::text)));


--
-- Name: item p_item_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_ler ON plat.item FOR SELECT TO plat_app USING (((tenant_id = ( SELECT plat.tenant_atual() AS tenant_atual)) AND ((apagado_em IS NULL) OR (( SELECT current_setting('plat.lixeira'::text, true) AS current_setting) = 'on'::text)) AND (((( SELECT plat.usuario_atual() AS usuario_atual) IS NULL) AND ((id)::text IN ( SELECT unnest(string_to_array(current_setting('plat.link_itens'::text, true), ','::text)) AS unnest))) OR ((acesso = 'publico'::text) AND ( SELECT plat.tenant_permite_publico(plat.tenant_atual()) AS tenant_permite_publico)) OR ( SELECT plat.modo_superadmin() AS modo_superadmin) OR (( SELECT plat.usuario_do_inquilino() AS usuario_do_inquilino) AND ((dono_id = ( SELECT plat.usuario_atual() AS usuario_atual)) OR (( SELECT current_setting('plat.transferencia'::text, true) AS current_setting) = 'on'::text) OR ( SELECT plat.tem('conteudo.ver_tudo'::text) AS tem) OR ((acesso = 'inquilino'::text) AND ( SELECT plat.tem('conteudo.ver_inquilino'::text) AS tem)) OR (EXISTS ( SELECT 1
   FROM (plat.item_grupo ig
     JOIN plat.grupo_membro gm ON (((gm.grupo_id = ig.grupo_id) AND (gm.usuario_id = ( SELECT plat.usuario_atual() AS usuario_atual)) AND (gm.estado = 'ativo'::text))))
  WHERE (ig.item_id = item.id))))))));


--
-- Name: item_relacao p_item_relacao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_relacao ON plat.item_relacao TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.pode_ler(origem))) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: item_versao p_item_versao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_item_versao ON plat.item_versao FOR SELECT TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.pode_ler(item_id)));


--
-- Name: job p_job; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_job ON plat.job TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: job_log p_job_log; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_job_log ON plat.job_log TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: compartilhamento_link p_link; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_link ON plat.compartilhamento_link TO plat_app USING (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(item_id))) WITH CHECK (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(item_id)));


--
-- Name: compartilhamento_link_item p_link_item; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_link_item ON plat.compartilhamento_link_item TO plat_app USING (((tenant_id = plat.tenant_atual()) AND (EXISTS ( SELECT 1
   FROM plat.compartilhamento_link k
  WHERE (k.id = compartilhamento_link_item.link_id))))) WITH CHECK (((tenant_id = plat.tenant_atual()) AND plat.pode_editar(item_id)));


--
-- Name: log_acesso p_log_acesso; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_log_acesso ON plat.log_acesso FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: log_acesso_y2026m09 p_log_acesso_y2026m09; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_log_acesso_y2026m09 ON plat.log_acesso_y2026m09 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: log_acesso_y2026m10 p_log_acesso_y2026m10; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_log_acesso_y2026m10 ON plat.log_acesso_y2026m10 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: log_acesso_y2026m11 p_log_acesso_y2026m11; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_log_acesso_y2026m11 ON plat.log_acesso_y2026m11 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: log_acesso_y2026m12 p_log_acesso_y2026m12; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_log_acesso_y2026m12 ON plat.log_acesso_y2026m12 FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: papel_personalizado p_papel_personalizado; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_papel_personalizado ON plat.papel_personalizado TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: papel_privilegio p_papel_privilegio; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_papel_privilegio ON plat.papel_privilegio TO plat_app USING ((EXISTS ( SELECT 1
   FROM plat.papel_personalizado p
  WHERE (p.id = papel_privilegio.papel_id)))) WITH CHECK ((EXISTS ( SELECT 1
   FROM plat.papel_personalizado p
  WHERE (p.id = papel_privilegio.papel_id))));


--
-- Name: pasta p_pasta_alterar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_pasta_alterar ON plat.pasta FOR UPDATE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND ((dono_id = plat.usuario_atual()) OR plat.tem('conteudo.editar_tudo'::text)))) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: pasta p_pasta_apagar; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_pasta_apagar ON plat.pasta FOR DELETE TO plat_app USING (((tenant_id = plat.tenant_atual()) AND ((dono_id = plat.usuario_atual()) OR plat.tem('conteudo.editar_tudo'::text))));


--
-- Name: pasta p_pasta_inserir; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_pasta_inserir ON plat.pasta FOR INSERT TO plat_app WITH CHECK (((tenant_id = plat.tenant_atual()) AND (dono_id = plat.usuario_atual()) AND plat.usuario_do_inquilino()));


--
-- Name: pasta p_pasta_ler; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_pasta_ler ON plat.pasta FOR SELECT TO plat_app USING ((tenant_id = plat.tenant_atual()));


--
-- Name: provedor_ldap p_provedor_ldap; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_provedor_ldap ON plat.provedor_ldap TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: raster_colecao p_raster_colecao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_raster_colecao ON plat.raster_colecao TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: raster_item p_raster_item; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_raster_item ON plat.raster_item TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: redefinicao_senha p_redefinicao_senha; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_redefinicao_senha ON plat.redefinicao_senha TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: senha_historico p_senha_historico; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_senha_historico ON plat.senha_historico TO plat_app USING ((EXISTS ( SELECT 1
   FROM plat.usuario u
  WHERE (u.id = senha_historico.usuario_id)))) WITH CHECK ((EXISTS ( SELECT 1
   FROM plat.usuario u
  WHERE (u.id = senha_historico.usuario_id))));


--
-- Name: sessao p_sessao; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_sessao ON plat.sessao TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: tenant p_tenant; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_tenant ON plat.tenant TO plat_app USING ((id = plat.tenant_atual())) WITH CHECK ((id = plat.tenant_atual()));


--
-- Name: token_servico p_token_servico; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_token_servico ON plat.token_servico TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: upload p_upload; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_upload ON plat.upload TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: upload_parte p_upload_parte; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_upload_parte ON plat.upload_parte TO plat_app USING ((EXISTS ( SELECT 1
   FROM plat.upload u
  WHERE ((u.id = upload_parte.upload_id) AND (u.tenant_id = plat.tenant_atual()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM plat.upload u
  WHERE ((u.id = upload_parte.upload_id) AND (u.tenant_id = plat.tenant_atual())))));


--
-- Name: usuario p_usuario; Type: POLICY; Schema: plat; Owner: -
--

CREATE POLICY p_usuario ON plat.usuario TO plat_app USING ((tenant_id = plat.tenant_atual())) WITH CHECK ((tenant_id = plat.tenant_atual()));


--
-- Name: papel_personalizado; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.papel_personalizado ENABLE ROW LEVEL SECURITY;

--
-- Name: papel_privilegio; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.papel_privilegio ENABLE ROW LEVEL SECURITY;

--
-- Name: pasta; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.pasta ENABLE ROW LEVEL SECURITY;

--
-- Name: provedor_ldap; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.provedor_ldap ENABLE ROW LEVEL SECURITY;

--
-- Name: raster_colecao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.raster_colecao ENABLE ROW LEVEL SECURITY;

--
-- Name: raster_item; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.raster_item ENABLE ROW LEVEL SECURITY;

--
-- Name: redefinicao_pedido; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.redefinicao_pedido ENABLE ROW LEVEL SECURITY;

--
-- Name: redefinicao_senha; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.redefinicao_senha ENABLE ROW LEVEL SECURITY;

--
-- Name: senha_historico; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.senha_historico ENABLE ROW LEVEL SECURITY;

--
-- Name: sessao; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.sessao ENABLE ROW LEVEL SECURITY;

--
-- Name: tenant; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.tenant ENABLE ROW LEVEL SECURITY;

--
-- Name: token_servico; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.token_servico ENABLE ROW LEVEL SECURITY;

--
-- Name: upload; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.upload ENABLE ROW LEVEL SECURITY;

--
-- Name: upload_parte; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.upload_parte ENABLE ROW LEVEL SECURITY;

--
-- Name: usuario; Type: ROW SECURITY; Schema: plat; Owner: -
--

ALTER TABLE plat.usuario ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict 3o8SEWEytSkB4vtaO3j7UB27JcLMb0qcDGtjI0C90pOeLgojX7ZeIpxp3mhSYqU

