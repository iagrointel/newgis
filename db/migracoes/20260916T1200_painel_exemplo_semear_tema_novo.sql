-- 20260916T1200_painel_exemplo_semear_tema_novo: `plat.painel_exemplo_semear` (20260906T2145_documento_painel.sql)
-- grava `corpo.tema = {"modo": "claro"}` no painel de exemplo — o formato PLACEHOLDER pré-L5-10 (mesma forma
-- que a conserto 20260916T0934_conserto_fusao_app_painel_tema_fontes.sql já tinha achado morta no esquema de
-- 'app'/'painel'). Como a função grava direto por SQL (SECURITY DEFINER, nunca passa pelo JSON Schema da API),
-- o item semeado nasceu e ficou anos-luz fora do esquema atual sem ninguém notar — só aparece quando algum
-- teste RELÊ o documento e tenta GRAVAR de volta (PUT), porque aí sim o esquema novo (`corpo.tema` oneOf
-- {"id"}/{"definicao"}, 20260916T0934) entra em jogo e recusa o `{"modo": "claro"}` antigo.
--
-- MEDIDO 16/09/2026 (tests/api/paineis/test_painel_dados.py::
-- test_painel_de_a_nao_vaza_dado_de_b_mesmo_com_documento_adulterado, achado ao conferir regressão do
-- conserto de app/painel desta mesma rodada do laço f2fixcatalogo).
--
-- Conserto: (1) a função passa a nascer SEM `tema` (chave opcional; um painel de demonstração não precisa de
-- tema para provar fontes/elementos) — função idempotente por design (`IF c_id IS NOT NULL AND p_id IS NOT
-- NULL THEN RETURN`), então só recriar a função não alcança o item JÁ semeado em nenhuma trilha; (2) por isso
-- este arquivo também tira `tema` de todo painel já semeado por ela (identificado por
-- `dados->'corpo'->>'semente' = 'painel_exemplo'`), em qualquer inquilino. Idempotente; sem BEGIN/COMMIT.

CREATE OR REPLACE FUNCTION plat.painel_exemplo_semear(p_slug text DEFAULT 'demo')
RETURNS TABLE(camada_id uuid, painel_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'plat', 'public'
AS $func$
DECLARE
  t_id int; t_slug text; t_admin int; schema_d text; tabela text;
  c_id uuid; p_id uuid; n_linhas int;
  f1 text := '01JPA1NEKEXEMPK0F0NTE0000A';
  f2 text := '01JPA1NEKEXEMPK0F0NTE0000B';
  e text[] := ARRAY['01JPA1NEKEXEMPK0EKEM00000A','01JPA1NEKEXEMPK0EKEM00000B','01JPA1NEKEXEMPK0EKEM00000C',
                    '01JPA1NEKEXEMPK0EKEM00000D','01JPA1NEKEXEMPK0EKEM00000E','01JPA1NEKEXEMPK0EKEM00000F'];
  fg text := '01JPA1NEKEXEMPK0F1KTR0000A';
  corpo jsonb;
BEGIN
  -- guarda 1: interruptor (dev ou semear_demo); guarda 2: só inquilino de demonstração
  IF NOT (plat.ambiente_atual() = 'dev' OR plat.semente_demo_habilitada()) THEN
    RAISE EXCEPTION 'semente_desligada';
  END IF;
  IF p_slug NOT IN ('demo', 'demo2') AND p_slug NOT LIKE 'zt-%%' THEN
    RAISE EXCEPTION 'inquilino_nao_e_demonstracao';
  END IF;
  SELECT t.id, t.slug INTO t_id, t_slug FROM plat.tenant t WHERE t.slug = p_slug AND t.ativo;
  IF t_id IS NULL THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  PERFORM set_config('plat.tenant_id', t_id::text, true);
  SELECT u.id INTO t_admin FROM plat.usuario u
  WHERE u.tenant_id = t_id AND u.ativo ORDER BY u.id LIMIT 1;

  -- idempotência: devolve o que já existe
  SELECT i.id INTO c_id FROM plat.item i
  WHERE i.tenant_id = t_id AND i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
    AND i.dados->>'semente' = 'painel_exemplo' LIMIT 1;
  SELECT i.id INTO p_id FROM plat.item i
  WHERE i.tenant_id = t_id AND i.tipo = 'painel' AND i.apagado_em IS NULL
    AND i.dados->'corpo'->>'semente' = 'painel_exemplo' LIMIT 1;
  IF c_id IS NOT NULL AND p_id IS NOT NULL THEN
    RETURN QUERY SELECT c_id, p_id; RETURN;
  END IF;

  schema_d := 'd_' || t_slug;
  PERFORM plat.camada_schema_garantir(t_slug);

  -- camada física: ocorrências sintéticas de demonstração (categoria, valor, data, ponto)
  IF c_id IS NULL THEN
    c_id := gen_random_uuid();
    tabela := 'c_' || replace(c_id::text, '-', '')::text;
    tabela := substr(tabela, 1, 18);
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', schema_d, tabela);
    EXECUTE format(
      'CREATE TABLE %I.%I (fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, geom geometry(Point,4326), '
      'categoria text NOT NULL, valor numeric NOT NULL, registrado_em timestamptz NOT NULL, '
      'descricao text NOT NULL DEFAULT '''')', schema_d, tabela);
    -- 120 linhas determinísticas: 4 categorias, valores e dias derivados da série (sem random: reexecutável)
    EXECUTE format(
      'INSERT INTO %I.%I (geom, categoria, valor, registrado_em, descricao) '
      'SELECT ST_SetSRID(ST_MakePoint(-46.53 - (g %% 11) * 0.01, -23.45 - (g %% 7) * 0.01), 4326), '
      '       (ARRAY[''agua'',''energia'',''via'',''limpeza''])[1 + (g %% 4)], '
      '       round(((g * 37) %% 900 + 10)::numeric, 2), '
      '       timestamptz ''2026-06-01 00:00+00'' + ((g %% 90) || '' days'')::interval, '
      '       ''ocorrencia '' || g '
      'FROM generate_series(1, 120) g', schema_d, tabela);
    EXECUTE format('SELECT plat.camada_preparar(%L, %L, %s, %L, %s)', schema_d, tabela, 4326, 'Point', t_admin);
    EXECUTE format('ANALYZE %I.%I', schema_d, tabela);

    INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, dono_id, dados, criado_por, modificado_por)
    VALUES (c_id, t_id, 'camada_vetorial', 'Ocorrências de demonstração do painel',
            'Dado sintético e determinístico (generate_series), criado por plat.painel_exemplo_semear para o painel de exemplo. Não descreve lugar nem pessoa.',
            t_admin,
            jsonb_build_object(
              'schema', schema_d, 'tabela', tabela, 'geometria', 'Point', 'srid', 4326,
              'campos', jsonb_build_array(
                jsonb_build_object('nome', 'categoria', 'tipo', 'text', 'alias', 'categoria'),
                jsonb_build_object('nome', 'valor', 'tipo', 'numeric', 'alias', 'valor'),
                jsonb_build_object('nome', 'registrado_em', 'tipo', 'timestamptz', 'alias', 'registrado em'),
                jsonb_build_object('nome', 'descricao', 'tipo', 'text', 'alias', 'descrição')),
              'fonte', 'hospedada', 'semente', 'painel_exemplo',
              'procedencia', jsonb_build_object('origem', 'sintetico', 'detalhe', 'generate_series(1,120) em plat.painel_exemplo_semear')),
            t_admin, t_admin);
    -- a camada semeada é publicada como qualquer outra: função de tile garantida na criação
    -- (a invariância do leitor — toda camada do catálogo com t_<tabela> em pg_proc — vale para a semente)
    PERFORM plat.camada_tile_garantir(schema_d, tabela, c_id);
  ELSE
    SELECT i.dados->>'tabela' INTO tabela FROM plat.item i WHERE i.id = c_id;
  END IF;

  -- o painel de exemplo: 6 elementos sobre 2 fontes (a segunda lê a MESMA camada com filtro fixo — prova de
  -- que a tela agrupa a consulta por fonte, não por elemento), filtro global de categoria e parâmetro de URL.
  -- Sem `tema` (chave opcional, item L5-10): a demonstração não precisa dele, e gravar o placeholder antigo
  -- {"modo":"claro"} só criava um documento que nunca revalidaria contra o esquema atual (achado 16/09).
  IF p_id IS NULL THEN
    p_id := gen_random_uuid();
    corpo := jsonb_build_object(
      'semente', 'painel_exemplo',
      'grade', jsonb_build_object('colunas', 12, 'linha_px', 36),
      'fontes', jsonb_build_array(
        jsonb_build_object('id', f1, 'nome', 'ocorrências', 'camada', jsonb_build_object('ref', c_id),
          'campos', jsonb_build_array('categoria','valor','registrado_em','descricao'),
          'ordenacao', jsonb_build_array(jsonb_build_object('campo','registrado_em','direcao','desc')),
          'limite', 200, 'atualizacao_s', 0),
        jsonb_build_object('id', f2, 'nome', 'ocorrências de água', 'camada', jsonb_build_object('ref', c_id),
          'campos', jsonb_build_array('categoria','valor','registrado_em'),
          'filtro', jsonb_build_object('op','=','args', jsonb_build_array(jsonb_build_object('property','categoria'),'agua')),
          'limite', 100, 'atualizacao_s', 0)),
      'filtros', jsonb_build_array(
        jsonb_build_object('id', fg, 'titulo', 'categoria', 'campo', 'categoria', 'tipo', 'categoria')),
      'parametros_url', jsonb_build_array(
        jsonb_build_object('nome', 'cat', 'campo', 'categoria', 'tipo', 'categoria')),
      'elementos', jsonb_build_array(
        jsonb_build_object('id', e[1], 'tipo', 'texto', 'titulo', '', 'x', 0, 'y', 0, 'largura', 12, 'altura', 2,
          'opcoes', jsonb_build_object('texto', 'Painel de exemplo do documento de painel (item L2-06-a). Dado sintético de demonstração: 120 ocorrências geradas por generate_series, sem descrever lugar nem pessoa.')),
        jsonb_build_object('id', e[2], 'tipo', 'indicador', 'titulo', 'ocorrências', 'fonte', f1, 'x', 0, 'y', 2, 'largura', 3, 'altura', 3,
          'opcoes', jsonb_build_object('agregacao', 'contagem')),
        jsonb_build_object('id', e[3], 'tipo', 'indicador', 'titulo', 'soma do valor', 'fonte', f1, 'x', 3, 'y', 2, 'largura', 3, 'altura', 3,
          'opcoes', jsonb_build_object('agregacao', 'soma', 'campo', 'valor')),
        jsonb_build_object('id', e[4], 'tipo', 'grafico', 'titulo', 'valor por categoria', 'fonte', f1, 'x', 6, 'y', 2, 'largura', 6, 'altura', 6,
          'opcoes', jsonb_build_object('grafico', 'barras', 'campo_rotulo', 'categoria', 'agregacao', 'soma', 'campo', 'valor', 'max_categorias', 8)),
        jsonb_build_object('id', e[5], 'tipo', 'tabela', 'titulo', 'últimas ocorrências', 'fonte', f1, 'x', 0, 'y', 5, 'largura', 6, 'altura', 6,
          'opcoes', jsonb_build_object('campos', jsonb_build_array('categoria','valor','registrado_em'), 'max_linhas', 8)),
        jsonb_build_object('id', e[6], 'tipo', 'indicador', 'titulo', 'ocorrências de água', 'fonte', f2, 'x', 6, 'y', 8, 'largura', 6, 'altura', 3,
          'opcoes', jsonb_build_object('agregacao', 'contagem'))));
    INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, dono_id, dados, criado_por, modificado_por)
    VALUES (p_id, t_id, 'painel', 'Painel de exemplo',
            'Painel instalado pela semente de demonstração (plat.painel_exemplo_semear): grade de 12 colunas, 6 elementos, 2 fontes sobre a camada de ocorrências sintéticas.',
            t_admin,
            jsonb_build_object('tipo', 'painel', 'esquema_versao', 3, 'corpo', corpo),
            t_admin, t_admin);
    INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id, posicao)
    VALUES (p_id, c_id, 'fonte_de_painel', t_id, 0)
    ON CONFLICT DO NOTHING;
  END IF;

  RETURN QUERY SELECT c_id, p_id;
END
$func$;
REVOKE EXECUTE ON FUNCTION plat.painel_exemplo_semear(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.painel_exemplo_semear(text) TO plat_app;

-- conserto retroativo: painel já semeado em QUALQUER inquilino, com o tema placeholder antigo
UPDATE plat.item
SET dados = jsonb_set(dados, '{corpo}', (dados->'corpo') - 'tema')
WHERE tipo = 'painel'
  AND dados->'corpo'->>'semente' = 'painel_exemplo'
  AND dados->'corpo'->'tema' = '{"modo": "claro"}'::jsonb;
