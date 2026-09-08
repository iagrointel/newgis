-- L5-04-c-temas-capa-colecao: tipo `colecao` (familia documento) e relação `item_de_colecao`.
-- A coleção agrupa itens de qualquer família numa página leitora (/colecao) com capa, metadados de
-- compartilhamento (título/resumo/miniatura para as marcas abertas `og:` da página /c/<token>) e
-- navegação. A relação segue o mesmo formato das outras do vocabulário (011): origem = coleção,
-- destino = o item agrupado; quem valida existência e inquilino é `relacoes.sincronizar` + o gatilho
-- `plat.tg_item_relacao`, quem deriva as dependências do compartilhamento é `plat.item_criado_a_partir_de`.
-- Idempotente (ON CONFLICT), padrão do 011; `esquema_versao` 1.

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front,
                           abre_em, tem_dado_fisico, linha_dona) VALUES
  ('colecao', 'documento', 'Coleção', 'página que agrupa itens com capa, navegação e metadados de compartilhamento',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["tipo","esquema_versao","corpo"],
     "properties":{
       "tipo":{"const":"colecao"},
       "esquema_versao":{"type":"integer","minimum":1},
       "corpo":{
         "type":"object","additionalProperties":false,
         "required":["capa","itens"],
         "properties":{
           "capa":{"type":"object","additionalProperties":false,"required":["titulo"],
             "properties":{"titulo":{"type":"string","minLength":1,"maxLength":200},
                           "subtitulo":{"type":"string","maxLength":300},
                           "midia":{"type":"string","maxLength":2048}}},
           "metadados":{"type":"object","additionalProperties":false,
             "properties":{"titulo":{"type":"string","maxLength":200},
                           "resumo":{"type":"string","maxLength":500},
                           "miniatura":{"type":"string","maxLength":2048}}},
           "itens":{"type":"array","maxItems":100,"items":{
             "type":"object","additionalProperties":false,"required":["item_id"],
             "properties":{"item_id":{"type":"string","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
                           "rotulo":{"type":"string","maxLength":200}}}},
           "tema":{"type":"object"}}}}}'::jsonb,
   1, 'colecao', '/static/js/catalogo/tipos/colecao.js', '{/colecao}', false, 'L5-04-c')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo, descricao = EXCLUDED.descricao,
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;

INSERT INTO plat.relacao_tipo VALUES
  ('item_de_colecao', 'coleção agrupa item (ordem em posicao)', '{documento}',
   '{camada,raster,mapa,app,painel,formulario,fluxo,rede,arquivo,ferramenta,documento}', false, false)
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao, origem_familias = EXCLUDED.origem_familias,
  destino_familias = EXCLUDED.destino_familias, arrasta_dono = EXCLUDED.arrasta_dono, apaga_junto = EXCLUDED.apaga_junto;
