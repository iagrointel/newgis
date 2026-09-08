-- 20260908T0715_regras_atributo: regras de atributo por camada (item L2-10-d-regras-de-atributo; L2_CONCEITO C5:
-- regra de expressão fica na API, no caminho único de escrita do L2-03-a). Esquema v4 de camada_vetorial acrescenta
-- `regras` (cálculo/restrição/validação), `campos_virtuais` (só leitura, avaliados na leitura) e `validacao` (o que
-- o job camadas.validar gravou: tabela e_<hex16> de erros, item da camada de erros, contagens). Tabela de erros
-- preparada por plat.tabela_erros_preparar (RLS por inquilino, como plat.camada_preparar). Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('camada_vetorial', 'camada', 'Camada vetorial', 'camada vetorial hospedada ou referenciada (tabela PostGIS)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["schema","tabela","geometria","srid","campos","fonte"],
     "properties":{
       "schema":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "tabela":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "geometria":{"type":"string","enum":["Point","MultiPoint","LineString","MultiLineString","Polygon","MultiPolygon","Geometry","nenhuma"]},
       "srid":{"type":"integer","minimum":1,"maximum":999999},
       "campos":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":false,"required":["nome","tipo"],
                 "properties":{"nome":{"type":"string","maxLength":63},"tipo":{"type":"string","maxLength":64},"alias":{"type":"string","maxLength":200}}}},
       "fonte":{"type":"string","enum":["hospedada","referenciada"]},
       "edicao":{"type":"object","additionalProperties":false,"properties":{
           "habilitada":{"type":"boolean"},
           "somente_proprias":{"type":"boolean"},
           "geometria_travada":{"type":"boolean"}}},
       "regras_campo":{"type":"object","maxProperties":500,"additionalProperties":{
           "type":"object","additionalProperties":false,"properties":{
             "obrigatorio":{"type":"boolean"},
             "somente_leitura":{"type":"boolean"},
             "dominio_valores":{"type":"array","maxItems":1000,"items":{"type":["string","number","boolean","null"]}},
             "dominio_min":{"type":"number"},
             "dominio_max":{"type":"number"}}}},
       "regras":{"type":"array","maxItems":100,"items":{"type":"object","additionalProperties":false,
           "required":["id","tipo","expressao"],
           "properties":{
             "id":{"type":"string","pattern":"^[a-z][a-z0-9_]{0,62}$"},
             "nome":{"type":"string","maxLength":200},
             "tipo":{"type":"string","enum":["calculo","restricao","validacao"]},
             "campo":{"type":"string","maxLength":63},
             "expressao":{"type":"string","maxLength":4000},
             "gatilhos":{"type":"array","maxItems":500,"items":{"type":"string","maxLength":63}},
             "eventos":{"type":"array","maxItems":2,"items":{"type":"string","enum":["inserir","atualizar"]}},
             "ordem":{"type":"integer","minimum":0,"maximum":100000},
             "habilitada":{"type":"boolean"},
             "mensagem":{"type":"string","maxLength":500},
             "codigo":{"type":"string","pattern":"^[a-z][a-z0-9_]{0,62}$"},
             "excluir_em_massa":{"type":"boolean"}}}},
       "campos_virtuais":{"type":"array","maxItems":50,"items":{"type":"object","additionalProperties":false,
           "required":["nome","expressao"],
           "properties":{
             "nome":{"type":"string","pattern":"^[a-z][a-z0-9_]{0,62}$"},
             "alias":{"type":"string","maxLength":200},
             "expressao":{"type":"string","maxLength":4000}}}},
       "validacao":{"type":"object","additionalProperties":true},
       "procedencia":{"type":"object","additionalProperties":true},
       "estatisticas":{"type":"object","additionalProperties":true},
       "importacao":{"type":"object","additionalProperties":true}}}'::jsonb,
   4, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/regras_definir', 'regras de atributo e campos virtuais de uma camada definidos (L2-10-d)'),
  ('camadas/validar', 'job camadas.validar avaliou as regras de validação de uma camada e gravou a camada de erros (L2-10-d)')
ON CONFLICT (nome) DO NOTHING;

-- tabela de erros de validação e_<hex16> ao lado da camada, no schema do inquilino: mesma RLS por tenant_id das
-- tabelas c_* (plat.camada_preparar), colunas fixas; a camada de erros é um item camada_vetorial que aponta para ela.
CREATE OR REPLACE FUNCTION plat.tabela_erros_preparar(p_schema text, p_tabela text, p_srid int, p_tipo text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; nome_curto text; tipo_geom text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^e_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND 'd_' || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  IF p_tipo IS NULL OR p_tipo = 'nenhuma' THEN tipo_geom := 'Geometry'; ELSE tipo_geom := p_tipo; END IF;
  nome_curto := substr(p_tabela, 3);
  EXECUTE format(
    'CREATE TABLE IF NOT EXISTS %1$I.%2$I ('
    '  fid            serial PRIMARY KEY, '
    '  feicao_fid     int NOT NULL, '
    '  feicao_globalid uuid, '
    '  regra          text NOT NULL, '
    '  codigo         text NOT NULL, '
    '  mensagem       text NOT NULL, '
    '  em             timestamptz NOT NULL DEFAULT now(), '
    '  geom           geometry(%4$s, %3$s), '
    '  tenant_id      int NOT NULL DEFAULT %5$L)',
    p_schema, p_tabela, p_srid, tipo_geom, t_atual
  );
  EXECUTE format('CREATE INDEX IF NOT EXISTS e_%2$s_geom_gix ON %1$I.%3$I USING gist (geom)', p_schema, nome_curto, p_tabela);
  EXECUTE format('CREATE INDEX IF NOT EXISTS e_%2$s_feicao_ix ON %1$I.%3$I (feicao_fid)', p_schema, nome_curto, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I ENABLE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I FORCE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('DROP POLICY IF EXISTS p_e_%2$s ON %1$I.%3$I', p_schema, nome_curto, p_tabela);
  EXECUTE format(
    'CREATE POLICY p_e_%2$s ON %1$I.%3$I FOR ALL TO plat_app, plat_leitor, plat_worker '
    'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
    p_schema, nome_curto, p_tabela
  );
  EXECUTE format('GRANT SELECT, INSERT, DELETE ON %1$I.%2$I TO plat_app, plat_worker', p_schema, p_tabela);
  EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %1$I.%2$I_fid_seq TO plat_app, plat_worker', p_schema, p_tabela);
  EXECUTE format('GRANT SELECT ON %1$I.%2$I TO plat_leitor', p_schema, p_tabela);
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, p_tabela, 'plat erros de validação (L2-10-d)');
END $$;
REVOKE EXECUTE ON FUNCTION plat.tabela_erros_preparar(text, text, int, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tabela_erros_preparar(text, text, int, text) TO plat_app, plat_worker;
