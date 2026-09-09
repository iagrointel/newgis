-- 20260909T0045 (item L2-06-c-acoes-seletores-filtros-cruzados): o documento de painel ganha INTERAÇÃO —
-- o array `corpo.mensagens` (gatilho {origem, evento} -> ações [{alvo, acao, parametros, relacao}], o
-- MESMO modelo do barramento do L5-07, ids de elemento no lugar de nó/vista) e o 13º tipo de elemento,
-- `seletor` (categoria com valores da fonte ou lista fixa, número/intervalo, data com presets, feição).
-- A semântica das mensagens é validada em código (app/paineis/interacoes.py), que é onde se olha a lista
-- inteira de elementos e de campos de fonte; aqui o esquema só ganha a FORMA. Sem mudança de
-- `esquema_versao`: documento antigo continua válido palavra por palavra.
-- A semente do painel de exemplo (plat.painel_exemplo_semear) é reescrita: os 6 elementos originais
-- ganham 3 companheiros (seletor de categoria, mapa, lista) e 3 mensagens — e o painel JÁ INSTALADO na
-- base de demonstração é ATUALIZADO no lugar (mesma marca de semente, corpo novo), para o e2e da trilha
-- e a demo não ficarem com o painel velho sem interação. Idempotente; sem BEGIN/COMMIT.

UPDATE plat.tipo_item
SET esquema = jsonb_set(
      esquema,
      '{properties,corpo,properties,elementos,items,properties,tipo,enum}',
      '["texto","indicador","grafico","tabela","serial","pizza","lista","mapa","detalhes","texto_rico","legenda","cabecalho","seletor"]'::jsonb,
      false)
WHERE nome = 'painel'
  AND esquema #> '{properties,corpo,properties,elementos,items,properties,tipo,enum}' IS NOT NULL;

-- a FORMA de uma mensagem (a semântica — origem/alvo existirem, relação declarada entre fontes
-- diferentes — é do validador em código; JSON Schema não olha a lista)
UPDATE plat.tipo_item
SET esquema = jsonb_set(
      esquema,
      '{properties,corpo,properties,mensagens}',
      $mensagens${
  "description": "interação do painel (item L2-06-c): gatilho {origem, evento} de um elemento e as ações que dispara em outros — o mesmo modelo do barramento do L5-07, com ids de ELEMENTO do painel; a regra de relação entre fontes diferentes é validada em app/paineis/interacoes.py",
  "items": {
    "additionalProperties": false,
    "properties": {
      "acoes": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "acao": {
              "enum": [
                "filtrar",
                "selecionar",
                "limpar_filtro",
                "limpar_selecao",
                "zoom",
                "pan",
                "piscar",
                "popup",
                "abrir",
                "fechar",
                "definir_parametro"
              ],
              "type": "string"
            },
            "alvo": {
              "description": "id do elemento que recebe a ação",
              "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
              "type": "string"
            },
            "parametros": {
              "description": "parâmetros da ação de widget (ex.: definir_parametro exige nome)",
              "type": "object"
            },
            "relacao": {
              "additionalProperties": false,
              "description": "como o dado da origem chega ao alvo: atributo (valores de campo_origem viram IN em campo_alvo) ou espacial (envelope da origem vira s_intersects no alvo); obrigatória entre fontes diferentes e em gatilho de seleção",
              "properties": {
                "campo_alvo": {
                  "maxLength": 63,
                  "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                  "type": "string"
                },
                "campo_origem": {
                  "maxLength": 63,
                  "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                  "type": "string"
                },
                "operador": {
                  "enum": [
                    "=",
                    "in"
                  ],
                  "type": "string"
                },
                "tipo": {
                  "enum": [
                    "mesma_fonte",
                    "atributo",
                    "espacial"
                  ],
                  "type": "string"
                }
              },
              "required": [
                "tipo"
              ],
              "type": "object"
            }
          },
          "required": [
            "alvo",
            "acao"
          ],
          "type": "object"
        },
        "maxItems": 20,
        "minItems": 1,
        "type": "array"
      },
      "descricao": {
        "maxLength": 200,
        "type": "string"
      },
      "gatilho": {
        "additionalProperties": false,
        "properties": {
          "evento": {
            "description": "os 8 eventos do Experience Builder que o barramento do L5-07 já atende",
            "enum": [
              "clique",
              "dado_adicionado",
              "filtro_mudou",
              "extensao_mudou",
              "localizacao",
              "registros_carregados",
              "selecao_mudou",
              "vista_mudou"
            ],
            "type": "string"
          },
          "origem": {
            "description": "id do elemento de onde o gatilho parte",
            "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
            "type": "string"
          }
        },
        "required": [
          "origem",
          "evento"
        ],
        "type": "object"
      },
      "id": {
        "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
        "type": "string"
      }
    },
    "required": [
      "id",
      "gatilho",
      "acoes"
    ],
    "type": "object"
  },
  "maxItems": 500,
  "type": "array"
}$mensagens$::jsonb,
      true)
WHERE nome = 'painel';

DO $$
DECLARE tipos jsonb; mensagens jsonb;
BEGIN
  SELECT esquema #> '{properties,corpo,properties,elementos,items,properties,tipo,enum}',
         esquema #> '{properties,corpo,properties,mensagens}'
    INTO tipos, mensagens FROM plat.tipo_item WHERE nome = 'painel';
  IF tipos IS NULL OR jsonb_array_length(tipos) <> 13 THEN
    RAISE EXCEPTION 'esquema do painel nao ganhou os 13 tipos de elemento: %', tipos;
  END IF;
  IF mensagens IS NULL OR mensagens->>'type' <> 'array' THEN
    RAISE EXCEPTION 'esquema do painel nao ganhou corpo.mensagens';
  END IF;
END $$;

-- ---------------------------------------------------------------- semente do painel de exemplo, versão 2:
-- mesmos 6 elementos + seletor de categoria + mapa + lista, e 3 mensagens (seletor -> todo mundo; barra
-- do gráfico -> lista; linha da lista -> zoom no mapa). O painel já instalado com a marca antiga é
-- ATUALIZADO no lugar.
CREATE OR REPLACE FUNCTION plat.painel_exemplo_semear(p_slug text DEFAULT 'demo')
RETURNS TABLE(camada_id uuid, painel_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'plat', 'public'
AS $func$
DECLARE
  t_id int; t_slug text; t_admin int; schema_d text; tabela text;
  c_id uuid; p_id uuid; n_linhas int; corpo_novo jsonb; marca text;
  f1 text := '01JPA1NEKEXEMPK0F0NTE0000A';
  f2 text := '01JPA1NEKEXEMPK0F0NTE0000B';
  e text[] := ARRAY['01JPA1NEKEXEMPK0EKEM00000A','01JPA1NEKEXEMPK0EKEM00000B','01JPA1NEKEXEMPK0EKEM00000C',
                    '01JPA1NEKEXEMPK0EKEM00000D','01JPA1NEKEXEMPK0EKEM00000E','01JPA1NEKEXEMPK0EKEM00000F',
                    '01JPA1NEKEXEMPK0EKEM00000G','01JPA1NEKEXEMPK0EKEM00000H','01JPA1NEKEXEMPK0EKEM00000J'];
  m text[] := ARRAY['01JPA1NEKEXEMPK0EKEM00000K','01JPA1NEKEXEMPK0EKEM00000M','01JPA1NEKEXEMPK0EKEM00000P'];
  fg text := '01JPA1NEKEXEMPK0F1KTR0000A';
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

  -- idempotência: a camada pela marca antiga (continua a mesma), o painel pela v2
  SELECT i.id INTO c_id FROM plat.item i
  WHERE i.tenant_id = t_id AND i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
    AND i.dados->>'semente' = 'painel_exemplo' LIMIT 1;
  SELECT i.id, i.dados->'corpo'->>'semente' INTO p_id, marca FROM plat.item i
  WHERE i.tenant_id = t_id AND i.tipo = 'painel' AND i.apagado_em IS NULL
    AND i.dados->'corpo'->>'semente' LIKE 'painel_exemplo%' LIMIT 1;
  IF c_id IS NOT NULL AND p_id IS NOT NULL AND marca = 'painel_exemplo_v2' THEN
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

  -- corpo v2: os 6 elementos originais + seletor (e7) + mapa (e8) + lista (e9) + 2 mensagens
  corpo_novo := jsonb_build_object(
    'semente', 'painel_exemplo_v2',
    'grade', jsonb_build_object('colunas', 12, 'linha_px', 36),
    'tema', jsonb_build_object('modo', 'claro'),
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
        'opcoes', jsonb_build_object('texto', 'Painel de exemplo do documento de painel (itens L2-06-a a L2-06-c). Dado sintético de demonstração: 120 ocorrências geradas por generate_series, sem descrever lugar nem pessoa.')),
      jsonb_build_object('id', e[7], 'tipo', 'seletor', 'titulo', 'filtrar por categoria', 'fonte', f1, 'x', 0, 'y', 2, 'largura', 3, 'altura', 2,
        'opcoes', jsonb_build_object('modo', 'categoria', 'campo', 'categoria', 'rotulo', 'categoria')),
      jsonb_build_object('id', e[2], 'tipo', 'indicador', 'titulo', 'ocorrências', 'fonte', f1, 'x', 3, 'y', 2, 'largura', 3, 'altura', 3,
        'opcoes', jsonb_build_object('agregacao', 'contagem')),
      jsonb_build_object('id', e[3], 'tipo', 'indicador', 'titulo', 'soma do valor', 'fonte', f1, 'x', 6, 'y', 2, 'largura', 3, 'altura', 3,
        'opcoes', jsonb_build_object('agregacao', 'soma', 'campo', 'valor')),
      jsonb_build_object('id', e[6], 'tipo', 'indicador', 'titulo', 'ocorrências de água', 'fonte', f2, 'x', 9, 'y', 2, 'largura', 3, 'altura', 3,
        'opcoes', jsonb_build_object('agregacao', 'contagem')),
      jsonb_build_object('id', e[4], 'tipo', 'grafico', 'titulo', 'valor por categoria', 'fonte', f1, 'x', 0, 'y', 5, 'largura', 6, 'altura', 6,
        'opcoes', jsonb_build_object('grafico', 'barras', 'campo_rotulo', 'categoria', 'agregacao', 'soma', 'campo', 'valor', 'max_categorias', 8)),
      jsonb_build_object('id', e[5], 'tipo', 'tabela', 'titulo', 'últimas ocorrências', 'fonte', f1, 'x', 6, 'y', 5, 'largura', 6, 'altura', 5,
        'opcoes', jsonb_build_object('campos', jsonb_build_array('categoria','valor','registrado_em'), 'max_linhas', 8)),
      jsonb_build_object('id', e[8], 'tipo', 'mapa', 'titulo', 'ocorrências no mapa', 'fonte', f1, 'x', 6, 'y', 10, 'largura', 6, 'altura', 6,
        'opcoes', jsonb_build_object('campos', jsonb_build_array('categoria','valor'), 'max_pontos', 200)),
      jsonb_build_object('id', e[9], 'tipo', 'lista', 'titulo', 'lista de ocorrências', 'fonte', f1, 'x', 0, 'y', 11, 'largura', 6, 'altura', 5,
        'opcoes', jsonb_build_object('campos', jsonb_build_array('categoria','valor','descricao'), 'modelo_titulo', '{descricao}', 'por_pagina', 10))),
    'mensagens', jsonb_build_array(
      jsonb_build_object('id', m[1],
        'descricao', 'o seletor de categoria filtra os elementos da mesma fonte e o indicador da fonte de água (relação por atributo)',
        'gatilho', jsonb_build_object('origem', e[7], 'evento', 'filtro_mudou'),
        'acoes', jsonb_build_array(
          jsonb_build_object('alvo', e[2], 'acao', 'filtrar'),
          jsonb_build_object('alvo', e[4], 'acao', 'filtrar'),
          jsonb_build_object('alvo', e[5], 'acao', 'filtrar'),
          jsonb_build_object('alvo', e[8], 'acao', 'filtrar'),
          jsonb_build_object('alvo', e[9], 'acao', 'filtrar'),
          jsonb_build_object('alvo', e[6], 'acao', 'filtrar',
            'relacao', jsonb_build_object('tipo', 'atributo', 'campo_origem', 'categoria', 'campo_alvo', 'categoria', 'operador', 'in')))),
      jsonb_build_object('id', m[2],
        'descricao', 'clicar numa barra do gráfico filtra a lista pela categoria da barra (relação por atributo)',
        'gatilho', jsonb_build_object('origem', e[4], 'evento', 'selecao_mudou'),
        'acoes', jsonb_build_array(
          jsonb_build_object('alvo', e[9], 'acao', 'filtrar',
            'relacao', jsonb_build_object('tipo', 'atributo', 'campo_origem', 'categoria', 'campo_alvo', 'categoria', 'operador', 'in')))),
      jsonb_build_object('id', m[3],
        'descricao', 'clicar numa linha da lista aproxima o mapa na ocorrência da linha (ação de widget: zoom)',
        'gatilho', jsonb_build_object('origem', e[9], 'evento', 'selecao_mudou'),
        'acoes', jsonb_build_array(
          jsonb_build_object('alvo', e[8], 'acao', 'zoom')))));

  IF p_id IS NULL THEN
    INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, dono_id, dados, criado_por, modificado_por)
    VALUES (gen_random_uuid(), t_id, 'painel', 'Painel de exemplo',
            'Painel instalado pela semente de demonstração (plat.painel_exemplo_semear): grade de 12 colunas, 9 elementos, 2 fontes sobre a camada de ocorrências sintéticas, seletor e mensagens de interação.',
            t_admin,
            jsonb_build_object('tipo', 'painel', 'esquema_versao', 3, 'corpo', corpo_novo),
            t_admin, t_admin)
    RETURNING id INTO p_id;
  ELSE
    UPDATE plat.item i SET dados = jsonb_build_object('tipo', 'painel', 'esquema_versao', 3, 'corpo', corpo_novo)
      WHERE i.id = p_id;
  END IF;

  INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id, posicao)
  VALUES (p_id, c_id, 'fonte_de_painel', t_id, 0)
  ON CONFLICT DO NOTHING;

  RETURN QUERY SELECT c_id, p_id;
END
$func$;
REVOKE EXECUTE ON FUNCTION plat.painel_exemplo_semear(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.painel_exemplo_semear(text) TO plat_app;
