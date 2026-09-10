-- plat · catálogo — tipo_item.esquema ganha `servico`: link de serviço externo ESTÁVEL por item (problema
-- medido no painel de compartilhamento: web/js/catalogo/tipos/token_servico.js cunhava um token novo do
-- MESMO nome a cada carregamento de página, revogando o anterior — a URL WMTS/WFS que o usuário colou no
-- QGIS ontem parava de funcionar hoje). Agora o token é cunhado uma vez e o VALOR fica guardado no próprio
-- item (`dados.servico.token`); reabrir o painel relê, nunca cunha de novo; só o botão "renovar" troca.
-- camada_vetorial: esquema v2 -> v3 (acrescenta `servico`, mesma forma dos demais campos livres do tipo).
-- raster: esquema v1 -> v2 (acrescenta `servico`; era o único dos dois tipos sem nenhum campo livre).
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
       "edicao":{"type":"object","additionalProperties":false,"properties":{"habilitada":{"type":"boolean"}}},
       "procedencia":{"type":"object","additionalProperties":true},
       "estatisticas":{"type":"object","additionalProperties":true},
       "importacao":{"type":"object","additionalProperties":true},
       "servico":{"type":"object","additionalProperties":false,"properties":{
         "token_id":{"type":"integer"},"nome":{"type":"string","maxLength":200},
         "token":{"type":"string","maxLength":500},"criado_em":{"type":"string"}}}}}'::jsonb,
   3, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04'),
  ('raster', 'raster', 'Imagem', 'imagem ou coleção raster (pgstac + objeto)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["colecao","stac_id","perfil","origem","srid_nativo"],
     "properties":{"colecao":{"type":"string"},"stac_id":{"type":"string"},"perfil":{"type":"string","enum":["visual","cientifico","referencia"]},
       "origem":{"type":"string","enum":["copiado","referenciado"]},"srid_nativo":{"type":"integer"},
       "bandas":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["nome"],
                 "properties":{"nome":{"type":"string"},"nome_comum":{"type":"string"}}}},
       "servico":{"type":"object","additionalProperties":false,"properties":{
         "token_id":{"type":"integer"},"nome":{"type":"string","maxLength":200},
         "token":{"type":"string","maxLength":500},"criado_em":{"type":"string"}}}}}'::jsonb,
   2, 'raster', '/static/js/catalogo/tipos/raster.js', '{mapa}', true, 'L1-01')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);
