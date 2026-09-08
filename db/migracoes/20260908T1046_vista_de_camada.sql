-- 20260908T1046_vista_de_camada: item L5-32-vistas-de-camada (linha L5 builder). Idempotente, sem BEGIN/COMMIT.
--
-- O tipo de item `vista_de_camada` JÁ existia reservado em 011_catalogo.sql (esquema v1: camada_id, filtro,
-- campos_ocultos, extent), junto com o tipo de relação `vista_de_camada` (origem camada -> destino camada,
-- apaga_junto = true). Este item entrega a coisa: a vista deixa de ser um registro descritivo e passa a ser uma
-- VIEW PostgreSQL de verdade em `d_<slug>`, servida pelos mesmos protocolos da camada-mãe.
--
-- Esquema v2, acrescentando o que a VIEW precisa para ser servida sem nenhum caminho novo de leitura:
--   schema/tabela/srid/geometria/fonte  - os mesmos campos de `camada_vetorial`, porque `tabela` aqui é o nome
--                                         da VIEW; é isso que faz `rotas_query`, `rotas_servico`, OGC e WFS
--                                         servirem a vista sem saber que ela é uma vista. Ficam OPCIONAIS no
--                                         esquema (só `camada_id` é obrigatório, como na v1) para não invalidar
--                                         item já gravado; quem serve o dado exige `tabela` e devolve 404
--                                         quando ela falta, em vez de tratar item incompleto como camada.
--   filtro                              - texto no dialeto `where` do FeatureServer, compilado por
--                                         `app.consulta.where_ast` (lista branca de coluna, valor parametrizado)
--                                         e CONGELADO dentro da definição da VIEW. Não existe caminho em que o
--                                         cliente reescreva esse filtro: `where=1=1` só se soma a ele.
--   campos_ocultos                      - colunas que a VIEW não seleciona. Campo que não está na view não
--                                         existe para `information_schema.columns`, logo não existe para
--                                         `outFields=*` nem para a lista branca do `where`.
--   somente_leitura                     - recusa de escrita na porta única (`app.edicao.servico`), 403.
--   estilo/popup                        - configuração própria da vista, separada da camada-mãe.
--
-- Isolamento: a VIEW é criada com `security_invoker = true`, então a política de RLS da tabela-mãe
-- (`tenant_id = plat.tenant_atual()`, FORCE, posta por `plat.camada_preparar`) é avaliada com o papel e o
-- contexto de quem consulta, nunca com os do dono da view. Compartilhar a vista publicamente muda
-- `plat.item.acesso` DA VISTA; a camada-mãe continua com o acesso dela, e `plat.tenant_publico_itens` olha o
-- item pedido, não o item de onde ele deriva.

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('vista_de_camada', 'camada', 'Vista de camada', 'vista derivada de uma camada primária (filtro, campos, extent)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["camada_id"],
     "properties":{
       "camada_id":{"type":"string","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
       "schema":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "tabela":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "geometria":{"type":"string","enum":["Point","MultiPoint","LineString","MultiLineString","Polygon","MultiPolygon","Geometry","nenhuma"]},
       "srid":{"type":"integer","minimum":1,"maximum":999999},
       "fonte":{"type":"string","enum":["hospedada","referenciada"]},
       "filtro":{"type":["string","null"],"maxLength":4000},
       "campos_ocultos":{"type":"array","maxItems":500,"items":{"type":"string","maxLength":63}},
       "somente_leitura":{"type":"boolean"},
       "extent":{"type":["array","null"],"minItems":4,"maxItems":4,"items":{"type":"number"}},
       "campos":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":false,"required":["nome","tipo"],
                 "properties":{"nome":{"type":"string","maxLength":63},"tipo":{"type":"string","maxLength":64},"alias":{"type":"string","maxLength":200}}}},
       "edicao":{"type":"object","additionalProperties":false,"properties":{
           "habilitada":{"type":"boolean"},
           "somente_proprias":{"type":"boolean"},
           "geometria_travada":{"type":"boolean"}}},
       "estilo":{"type":["object","null"],"additionalProperties":true},
       "popup":{"type":["object","null"],"additionalProperties":true},
       "procedencia":{"type":"object","additionalProperties":true}}}'::jsonb,
   2, 'vista', '/static/js/catalogo/tipos/vista_de_camada.js', '{mapa,tabela}', true, 'L5-32')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  linha_dona = EXCLUDED.linha_dona;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/criar_vista', 'vista de camada criada (view PostgreSQL com filtro e campos ocultos, L5-32)'),
  ('camadas/alterar_vista', 'definição de vista de camada alterada e view recriada (L5-32)')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- dívida trazida junto (correção em arquivo
-- novo, nunca editando migração já aplicada): duas funções do histórico de feição e da origem de edição
-- nasceram com EXECUTE para PUBLIC. `tests/api/catalogo/test_eventos_e_seguranca.py` exige que nenhuma função
-- do schema `plat` fique aberta a PUBLIC. As duas são chamadas por GATILHO (que corre com os direitos do dono
-- da tabela) e de dentro de outras funções do mesmo dono, então fechá-las não tira privilégio de ninguém.
DO $$
BEGIN
  IF to_regprocedure('plat.feicao_historico_registrar()') IS NOT NULL THEN
    EXECUTE 'REVOKE EXECUTE ON FUNCTION plat.feicao_historico_registrar() FROM PUBLIC';
  END IF;
  IF to_regprocedure('plat.origem_atual()') IS NOT NULL THEN
    EXECUTE 'REVOKE EXECUTE ON FUNCTION plat.origem_atual() FROM PUBLIC';
    EXECUTE 'GRANT EXECUTE ON FUNCTION plat.origem_atual() TO plat_app';
  END IF;
END $$;
