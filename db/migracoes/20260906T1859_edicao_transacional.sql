-- 20260906T1859_edicao_transacional: item L2-03-a-api-edicao-transacional. POST /api/camadas/{id}/edicoes é a
-- única porta de escrita de feição (navegador, PWA, FeatureServer L2-04-d e OGC L2-04-g escrevem por aqui).
-- Sem tabela nova: a transação roda direto contra a tabela de camada `d_<slug>.c_<uuid16>` que
-- plat.camada_preparar (029_ingestao_vetor.sql) já FORCE RLS por tenant_id; concorrência otimista e rastreio
-- usam colunas que já existem lá (versao, criado_por, atualizado_por, criado_em, atualizado_em).
--
-- Bump do esquema de `camada_vetorial` (v2 -> v3), só acrescentando propriedades OPCIONAIS (idempotente e
-- retrocompatível com item já gravado): `edicao.somente_proprias` ("só as próprias feições", ownership como a
-- Esri) e `edicao.geometria_travada`; `regras_campo` (mapa nome-do-campo -> {obrigatorio, somente_leitura,
-- dominio_valores | dominio_min/dominio_max}) é o mecanismo de domínio DESTE item, escopado à própria camada —
-- item L2-10-a-dominios-subtipos (entregue em outra trilha, plat.dominio/plat.dominio_campo compartilhado entre
-- camadas com subtipos) ainda não chegou a esta árvore; quando a trilha for integrada, a validação de domínio
-- desta rota ganha uma segunda fonte (plat.dominio_campo) além de `regras_campo` — não é retrabalho, é adição.
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
       "procedencia":{"type":"object","additionalProperties":true},
       "estatisticas":{"type":"object","additionalProperties":true},
       "importacao":{"type":"object","additionalProperties":true}}}'::jsonb,
   3, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

-- evento de domínio do lote (uma linha por chamada de POST /api/camadas/{id}/edicoes, nunca uma por feição —
-- a contagem vai em propriedades: {"adicionados": n, "atualizados": n, "apagados": n, "modo": "transacao|parcial"})
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/editar', 'lote de edição de feições aplicado (adicionar/atualizar/apagar; L2-03-a)')
ON CONFLICT (nome) DO NOTHING;
