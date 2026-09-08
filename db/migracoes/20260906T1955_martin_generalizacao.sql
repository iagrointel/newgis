-- 20260906T1955_martin_generalizacao: item L2-01-b-martin-tiles-vetoriais. Substitui o corpo da função de
-- tile gerada por plat.camada_tile_garantir (20260906T1546_leitor_tiles) por uma versão com generalização
-- por zoom e limite de feições marcado — o contrato de contexto por token e a checagem de inquilino
-- continuam IDÊNTICOS (mesma assinatura, mesma RLS). Idempotente (CREATE OR REPLACE); reaplica a função de
-- tile de toda camada já publicada no catálogo deste ambiente, do mesmo jeito que a migração anterior fez.
--
-- Duas cláusulas do portão deste item:
--   1. "generalização por zoom declarada (ST_SimplifyPreserveTopology com tolerância = resolução do tile/2
--      para z < 12)": tolerância = (largura do envelope do tile em EPSG:3857) / 4096 / 2, isto é, meio
--      "pixel" de tile na resolução daquele zoom — abaixo de z12 (onde a densidade de vértices por pixel de
--      tela é maior que a útil) e ZERO a partir de z12 (a malha já é fina o bastante).
--   2. "limite de 10.000 feições por tile com marcação 'truncado'": a subconsulta pega no máximo 10.000
--      linhas (ORDER BY fid, determinístico) e toda feição do tile carrega um atributo booleano `_truncado`
--      dizendo se o total de feições que caem no tile passava de 10.000 — like Martin's próprio
--      `max_feature_count` (deploy/martin.yaml) corta de novo se, por algum motivo, a função não cortar
--      (defesa em profundidade), mas só a função sabe dizer SE cortou.
--
-- ST_Subdivide de polígono com mais de 4.096 vértices (a outra cláusula de generalização do item) NÃO está
-- aqui: nenhuma camada de teste desta trilha tem polígono nesse tamanho, e subdividir multiplica linhas por
-- feição (a marcação de truncado teria de ser recalculada por peça, não por feição-fonte) — fronteira aberta,
-- registrada no handoff deste item, não neste comentário de migração.
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

-- retroativo: reaplica a função de tile (agora com generalização) em toda camada já publicada, do mesmo
-- jeito que a 20260906T1546 fez na primeira vez.
DO $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT i.id, i.dados->>'schema' AS esquema, i.dados->>'tabela' AS tabela
           FROM plat.item i
           WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
             AND coalesce(i.dados->>'fonte', 'hospedada') = 'hospedada'
             AND i.dados->>'schema' ~ '^d_[a-z0-9_]{1,60}$' AND i.dados->>'tabela' ~ '^c_[0-9a-f]{16}$' LOOP
    CONTINUE WHEN to_regclass(format('%I.%I', r.esquema, r.tabela)) IS NULL;
    PERFORM plat.camada_tile_garantir(r.esquema, r.tabela, r.id);
    n := n + 1;
  END LOOP;
  RAISE NOTICE 'funções de tile regeneradas (generalização por zoom) para % camada(s) do catálogo', n;
END $$;
