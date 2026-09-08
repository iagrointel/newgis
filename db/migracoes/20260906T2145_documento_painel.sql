-- Documento de painel (item L2-06-a-modelo-painel-fontes; ADR docs/adr/20260906T2145-documento-de-painel.md):
-- o tipo `painel` sai do grafo genérico v2 (corpo nos/ligações, item L5-05) e ganha o modelo de painel como
-- esquema_versao 3: grade responsiva, elementos com posição e tamanho, fontes de dado como VISTAS (camada por
-- `ref` uuid + filtro CQL2-JSON + campos + ordenação + intervalo de atualização), filtros globais, parâmetros
-- de URL e tema claro/escuro. `nos`/`ligacoes`/`mapa_id`/`mapas` continuam aceitos (v2), opcionais — documento
-- antigo migra NA LEITURA (app/catalogo/documento.py::_migrar_painel_v2_v3), nada se perde.
-- O arquivo publicado é docs/esquemas/painel-v3.json (gerado deste esquema por docs/gerar_esquemas.py). O
-- portão do item cita docs/esquemas/painel-v1.json: v1 (011_catalogo.sql, corpo livre) e v2 (028_documento_
-- grafo.sql, grafo) já existem como registro HISTÓRICO e o gerador nunca reescreve versão morta — a cláusula
-- é cumprida pelo esquema vigente publicado em docs/esquemas, com a versão que a sequência exige (v3).
-- Acrescenta o tipo de relação `fonte_de_painel` (painel -> camada), a função SECURITY DEFINER que resolve os
-- metadados das camadas de UM painel para o contexto anônimo de link (a camada não entra em link_itens; o que
-- se expõe é só o metadado das camadas que o painel compartilhado já referencia, do MESMO inquilino) e a
-- função de semente do painel de exemplo da demo (mesmas guardas de plat.jobs_semear_demo, migração 014).
-- Idempotente; sem BEGIN/COMMIT.

UPDATE plat.tipo_item SET esquema = $esquema_painel${
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "additionalProperties": false,
  "properties": {
    "corpo": {
      "additionalProperties": false,
      "properties": {
        "elementos": {
          "description": "o que a tela desenha; posição e tamanho na grade (x, y em células, origem no canto superior esquerdo)",
          "items": {
            "additionalProperties": false,
            "properties": {
              "altura": {
                "description": "altura em linhas da grade",
                "maximum": 60,
                "minimum": 1,
                "type": "integer"
              },
              "fonte": {
                "anyOf": [
                  {
                    "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "description": "id de uma entrada de corpo.fontes; obrigatória para todo tipo exceto texto"
              },
              "id": {
                "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                "type": "string"
              },
              "largura": {
                "description": "largura em colunas da grade",
                "maximum": 24,
                "minimum": 1,
                "type": "integer"
              },
              "opcoes": {
                "additionalProperties": true,
                "description": "forma por tipo, validada campo a campo em app/paineis/documento.py (o que depende dos campos da camada não cabe em JSON Schema)",
                "type": "object"
              },
              "tipo": {
                "enum": [
                  "texto",
                  "indicador",
                  "grafico",
                  "tabela"
                ],
                "type": "string"
              },
              "titulo": {
                "maxLength": 120,
                "type": "string"
              },
              "x": {
                "description": "coluna inicial (0 = primeira)",
                "maximum": 23,
                "minimum": 0,
                "type": "integer"
              },
              "y": {
                "description": "linha inicial (0 = primeira)",
                "maximum": 1000,
                "minimum": 0,
                "type": "integer"
              }
            },
            "required": [
              "id",
              "tipo",
              "x",
              "y",
              "largura",
              "altura"
            ],
            "type": "object"
          },
          "maxItems": 200,
          "type": "array"
        },
        "filtros": {
          "description": "filtros globais: um controle na barra do painel; a condição entra em TODA fonte que tem o campo",
          "items": {
            "additionalProperties": false,
            "properties": {
              "campo": {
                "maxLength": 63,
                "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                "type": "string"
              },
              "id": {
                "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                "type": "string"
              },
              "tipo": {
                "enum": [
                  "categoria",
                  "numero",
                  "data"
                ],
                "type": "string"
              },
              "titulo": {
                "maxLength": 80,
                "type": "string"
              }
            },
            "required": [
              "id",
              "campo",
              "tipo"
            ],
            "type": "object"
          },
          "maxItems": 10,
          "type": "array"
        },
        "fontes": {
          "description": "fontes de dado do painel: o objeto VISTA (camada por ref + filtro CQL2-JSON + campos + ordenação) — a mesma forma que o L5-07 registra como fonte e o L2-01-h executa",
          "items": {
            "additionalProperties": false,
            "properties": {
              "atualizacao_s": {
                "default": 0,
                "description": "intervalo de reconsulta em segundos; 0 = só na abertura e sob ação do usuário",
                "maximum": 86400,
                "minimum": 0,
                "type": "integer"
              },
              "camada": {
                "additionalProperties": false,
                "properties": {
                  "ref": {
                    "description": "uuid do item de camada do catálogo, nunca URL",
                    "format": "uuid",
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    "type": "string"
                  }
                },
                "required": [
                  "ref"
                ],
                "type": "object"
              },
              "campos": {
                "description": "campos da camada que a fonte expõe aos elementos (lista branca — nunca SELECT *)",
                "items": {
                  "maxLength": 63,
                  "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                  "type": "string"
                },
                "maxItems": 50,
                "minItems": 1,
                "type": "array"
              },
              "filtro": {
                "description": "CQL2-JSON fixo da vista; executado pelo subconjunto seguro de app/paineis/cql2.py (o L2-01-h amplia a gramática)",
                "type": "object"
              },
              "id": {
                "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                "type": "string"
              },
              "limite": {
                "default": 200,
                "description": "máximo de linhas devolvidas por consulta",
                "maximum": 1000,
                "minimum": 1,
                "type": "integer"
              },
              "nome": {
                "maxLength": 80,
                "type": "string"
              },
              "ordenacao": {
                "items": {
                  "additionalProperties": false,
                  "properties": {
                    "campo": {
                      "maxLength": 63,
                      "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                      "type": "string"
                    },
                    "direcao": {
                      "enum": [
                        "asc",
                        "desc"
                      ],
                      "type": "string"
                    }
                  },
                  "required": [
                    "campo"
                  ],
                  "type": "object"
                },
                "maxItems": 4,
                "type": "array"
              }
            },
            "required": [
              "id",
              "camada",
              "campos"
            ],
            "type": "object"
          },
          "maxItems": 50,
          "type": "array"
        },
        "grade": {
          "additionalProperties": false,
          "properties": {
            "colunas": {
              "default": 12,
              "maximum": 24,
              "minimum": 1,
              "type": "integer"
            },
            "linha_px": {
              "default": 36,
              "description": "altura de uma linha da grade em pixels; em tela estreita (<= 640 px) a grade colapsa para uma coluna e os elementos empilham na ordem do documento",
              "maximum": 200,
              "minimum": 8,
              "type": "integer"
            }
          },
          "type": "object"
        },
        "ligacoes": {
          "items": {
            "properties": {
              "alvo": {
                "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                "type": "string"
              },
              "origem": {
                "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                "type": "string"
              },
              "tipo": {
                "maxLength": 60,
                "type": "string"
              }
            },
            "required": [
              "origem",
              "alvo"
            ],
            "type": "object"
          },
          "maxItems": 4000,
          "type": "array"
        },
        "mapa_id": {
          "format": "uuid",
          "type": "string"
        },
        "mapas": {
          "items": {
            "format": "uuid",
            "type": "string"
          },
          "type": "array"
        },
        "nos": {
          "items": {
            "properties": {
              "id": {
                "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$",
                "type": "string"
              },
              "tipo": {
                "maxLength": 60,
                "minLength": 1,
                "type": "string"
              }
            },
            "required": [
              "id",
              "tipo"
            ],
            "type": "object"
          },
          "maxItems": 2000,
          "type": "array"
        },
        "parametros_url": {
          "description": "parâmetros que a URL do painel aceita (?nome=valor) e que viram condição nas fontes que têm o campo; o L5-18 amplia os tipos",
          "items": {
            "additionalProperties": false,
            "properties": {
              "campo": {
                "description": "campo das fontes; no tipo geometria é a coluna de geometria (em geral geom) e o valor é o,s,l,n em EPSG:4326",
                "maxLength": 63,
                "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                "type": "string"
              },
              "nome": {
                "pattern": "^[a-z][a-z0-9_]{0,30}$",
                "type": "string"
              },
              "obrigatorio": {
                "default": false,
                "type": "boolean"
              },
              "tipo": {
                "enum": [
                  "categoria",
                  "numero",
                  "data",
                  "feicao",
                  "geometria"
                ],
                "type": "string"
              }
            },
            "required": [
              "nome",
              "campo",
              "tipo"
            ],
            "type": "object"
          },
          "maxItems": 20,
          "type": "array"
        },
        "tema": {
          "additionalProperties": false,
          "description": "claro/escuro até o L5-10 (temas e marca) existir; aí este objeto ganha referência ao tema",
          "properties": {
            "modo": {
              "enum": [
                "claro",
                "escuro"
              ],
              "type": "string"
            }
          },
          "type": "object"
        },
        "semente": {
          "description": "marca interna de idempotência de uma semente de demonstração (ex.: plat.painel_exemplo_semear); documento de autor nunca grava este campo",
          "maxLength": 60,
          "type": "string"
        }
      },
      "type": "object"
    },
    "esquema_versao": {
      "minimum": 1,
      "type": "integer"
    },
    "tipo": {
      "const": "painel"
    }
  },
  "required": [
    "tipo",
    "esquema_versao",
    "corpo"
  ],
  "type": "object"
}$esquema_painel$::jsonb,
    esquema_versao = 3
WHERE nome = 'painel';

-- relação painel -> camada de dado (é dela que sai o 409 ao apagar camada usada como fonte de painel)
INSERT INTO plat.relacao_tipo(nome, descricao, origem_familias, destino_familias, arrasta_dono, apaga_junto)
VALUES ('fonte_de_painel', 'painel usa camada como fonte de dado', '{painel}', '{camada,raster}', false, false)
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- metadado das camadas de UM painel (contexto
-- anônimo de link): a leitura anônima (/c/<token>) vê o item do painel por link_itens, mas NÃO as camadas que
-- ele referencia — e o endpoint de dados precisa da lista branca de campos e do nome da tabela para montar a
-- consulta com segurança. Esta função devolve só o metadado das camadas que o próprio documento do painel
-- referencia, do MESMO inquilino do contexto, nunca por id pedido pelo cliente. Sem ela a alternativa seria
-- obrigar quem compartilha a incluir cada camada no link (vazamento por esquecimento) ou ler plat.item fora da
-- RLS (vazamento por construção).
CREATE OR REPLACE FUNCTION plat.painel_camadas_resolver(p_painel uuid)
RETURNS TABLE(id uuid, tipo text, titulo text, dados jsonb)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'plat', 'public'
AS $func$
BEGIN
  RETURN QUERY
  SELECT i.id, i.tipo, i.titulo, i.dados
  FROM plat.item p
  JOIN plat.item i
    ON i.tenant_id = p.tenant_id
   AND i.apagado_em IS NULL
  WHERE p.id = p_painel
    AND p.tipo = 'painel'
    AND p.apagado_em IS NULL
    AND p.tenant_id = plat.tenant_atual()
    AND i.id::text IN (
      SELECT f->'camada'->>'ref'
      FROM jsonb_array_elements(coalesce(p.dados->'corpo'->'fontes', '[]'::jsonb)) f
    );
END
$func$;
REVOKE EXECUTE ON FUNCTION plat.painel_camadas_resolver(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.painel_camadas_resolver(uuid) TO plat_app;

-- ---------------------------------------------------------------- painel de exemplo da demo (mesmas quatro
-- guardas de plat.jobs_semear_demo, migração 014: interruptor de ambiente, inquilino de demonstração, teto e
-- marca). Cria UMA camada de ocorrências sintéticas (dado de demonstração, declarado no título e em
-- procedencia) com a tabela física em d_<slug> e UM painel de 6 elementos sobre 2 fontes. Idempotente pela
-- marca dados->>'semente' = 'painel_exemplo': rodado duas vezes devolve os ids já criados.
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
  ELSE
    SELECT i.dados->>'tabela' INTO tabela FROM plat.item i WHERE i.id = c_id;
  END IF;

  -- o painel de exemplo: 6 elementos sobre 2 fontes (a segunda lê a MESMA camada com filtro fixo — prova de
  -- que a tela agrupa a consulta por fonte, não por elemento), filtro global de categoria e parâmetro de URL
  IF p_id IS NULL THEN
    p_id := gen_random_uuid();
    corpo := jsonb_build_object(
      'semente', 'painel_exemplo',
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
