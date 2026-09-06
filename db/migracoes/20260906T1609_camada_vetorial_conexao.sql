-- Item L6-02-c-wfs-ogcapi (ADR 0018): a camada COPIADA de um WFS 2.0 / OGC API - Features precisa guardar, na
-- própria ficha, de onde ela veio e o que a cópia apurou — protocolo, URL, coleção, CRS declarado × gravado,
-- o total que o serviço declarou, quantas foram copiadas, se parou no limite e se o serviço ignorou a
-- paginação. O esquema v2 de `camada_vetorial` (migração 029) é `additionalProperties: false` e não tinha
-- onde pôr isso; enfiar em `procedencia` misturaria o vocabulário de proveniência (que o metadado ISO 19139
-- lê) com o relatório da cópia. Daí a propriedade nova `conexao`, e só ela: nada mais do esquema muda.
--
-- Idempotente e sem renumerar nada: o INSERT ... ON CONFLICT DO UPDATE só sobe a versão do esquema (a mesma
-- guarda da 029, que nunca REBAIXA um esquema já mais novo).

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front,
                           abre_em, tem_dado_fisico, linha_dona) VALUES
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
       "edicao":{"type":"object","additionalProperties":false,"properties":{"habilitada":{"type":"boolean"}}},
       "procedencia":{"type":"object","additionalProperties":true},
       "estatisticas":{"type":"object","additionalProperties":true},
       "conexao":{"type":"object","additionalProperties":true},
       "importacao":{"type":"object","additionalProperties":true}}}'::jsonb,
   3, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);
