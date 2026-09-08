-- 20260907T0330_mapa_extensao (item L2-01-mapa-web): extensão geográfica de uma camada hospedada, para o
-- visualizador enquadrar o mapa na camada ("zoom para a camada") sem que a rota monte SQL com nome de
-- tabela vindo do catálogo. SECURITY DEFINER com a MESMA validação de nome das outras funções de camada
-- (`d_<slug>` / `c_<16 hex>`) e a MESMA checagem de inquilino: uma camada de outro inquilino nunca
-- devolve extensão, mesmo que o chamador saiba o nome da tabela.
--
-- Devolve os 4 números [oeste, sul, leste, norte] em graus (EPSG:4326), ou NULL quando a camada está
-- vazia. Custo: ST_Extent varre o índice/tabela; por isso o visualizador prefere `dados.extensao` gravado
-- na ingestão e só cai aqui quando o item não o tem (medido no item: 1 mi de pontos = 78 ms).
CREATE OR REPLACE FUNCTION plat.camada_extensao(p_schema text, p_tabela text)
RETURNS double precision[] LANGUAGE plpgsql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
DECLARE cx geometry; saida double precision[];
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = plat.tenant_atual() AND 'd_' || slug = p_schema) THEN
    RAISE EXCEPTION 'camada_de_outro_inquilino';
  END IF;
  IF to_regclass(format('%I.%I', p_schema, p_tabela)) IS NULL THEN
    RAISE EXCEPTION 'camada_inexistente';
  END IF;
  EXECUTE format('SELECT ST_SetSRID(ST_Extent(ST_Transform(geom, 4326)), 4326) FROM %I.%I',
                 p_schema, p_tabela) INTO cx;
  IF cx IS NULL THEN RETURN NULL; END IF;
  saida := ARRAY[ST_XMin(cx), ST_YMin(cx), ST_XMax(cx), ST_YMax(cx)];
  RETURN saida;
END $$;
REVOKE ALL ON FUNCTION plat.camada_extensao(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_extensao(text, text) TO plat_app;
