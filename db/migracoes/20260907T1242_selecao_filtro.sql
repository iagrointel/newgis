-- 20260907T1242_selecao_filtro: item L2-01-h-selecao-filtros.
--
-- Acrescenta o tipo de item `selecao` (família `camada`, já permitida pelo CHECK de `plat.tipo_item`
-- desde 011_catalogo.sql — nenhuma migração de esquema de tabela é necessária, só uma linha nova):
-- uma seleção salva é `{camada_id, ids (lista de fid), criterio, contagem}`, para reuso em análise,
-- exportação e edição em lote (hipótese do item). Não tem tabela física própria (`tem_dado_fisico =
-- false`): os fids apontam para linhas que já existem na tabela hospedada da camada.
--
-- O filtro PERSISTENTE (que grava "no documento", oposto da seleção efêmera) reaproveita o tipo
-- `vista_de_camada` que a ADR 0004 já declarou para exatamente isto (`dados.filtro`, mesmo objeto
-- CQL2-JSON deste item) — nenhuma mudança de esquema também aí. O documento de mapa (L2-01-a) que
-- guardaria a vista dentro do corpo do mapa é um item irmão em outro ramo, ainda não juntado nesta
-- árvore; enquanto isso, a vista salva sozinha (item do catálogo, `camada_id` explícito) já cobre a
-- hipótese "filtro persistente ... para reuso", e passa a ser reaproveitada por quem juntar o documento
-- de mapa depois (a mesma decisão que a ADR 0004 já tomou, não uma nova).
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona) VALUES
  ('selecao', 'camada', 'Seleção',
   'lista de feições selecionadas de uma camada (clique, retângulo, polígono, laço, filtro por atributo '
   'ou seleção espacial), salva para reuso em análise, exportação e edição em lote (item L2-01-h)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["camada_id","ids"],
     "properties":{
       "camada_id":{"type":"string","format":"uuid","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
       "ids":{"type":"array","maxItems":200000,"items":{"type":["integer","string"]}},
       "criterio":{"type":"object","additionalProperties":true,
         "properties":{"modo":{"type":"string","enum":["clique","retangulo","poligono","laco","filtro","espacial"]}}},
       "contagem":{"type":"integer","minimum":0}}}'::jsonb,
   1, 'selecao', '/static/js/catalogo/tipos/selecao.js', '{mapa}', false, 'L2-01-h')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo, descricao = EXCLUDED.descricao,
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;

INSERT INTO plat.relacao_tipo VALUES
  ('selecao_de_camada', 'seleção salva referencia a camada de origem', '{camada}', '{camada}', true, true)
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao, origem_familias = EXCLUDED.origem_familias,
  destino_familias = EXCLUDED.destino_familias, arrasta_dono = EXCLUDED.arrasta_dono, apaga_junto = EXCLUDED.apaga_junto;
