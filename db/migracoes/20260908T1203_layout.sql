-- Item L2-12-b-layouts-elementos-exportacao: tipo de item `layout` (documento de impressão: papel, orientação,
-- margens e elementos posicionados em milímetros — quadro de mapa, legenda, barra de escala, seta de norte,
-- grade, título/texto com expressões, imagem, tabela, data, atribuição). `modelo: true` marca um layout do
-- inquilino que serve de ponto de partida (os modelos padrão vivem em código, app/layout/modelos.py).
-- Sem tabela nova: o layout é um item do catálogo como qualquer outro (RLS, lixeira, compartilhamento herdados).
-- Idempotente (ON CONFLICT no nome). O esquema aqui é o MESMO que app/layout/modelos.py::validar confere antes de
-- compor — a validação de tela sai nomeada por campo e nunca como erro do compositor.
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('layout', 'mapa', 'Layout de impressão',
   'documento de layout: papel A4-A0 ou carta, retrato/paisagem, margens e elementos em milímetros (quadro de mapa '
   'por extensão fixa ou escala 1:N, legenda do estilo, barra de escala, seta de norte verdadeiro/grade, grade de '
   'coordenadas UTM ou geográfica, título e texto com expressões, imagem, tabela de atributos, data, atribuição); '
   'exportado em PDF (texto selecionável), PNG, JPG ou SVG pelo job layout.exportar (item L2-12-b)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["esquema_versao","papel","orientacao","elementos"],
     "properties":{
       "esquema_versao":{"type":"integer","minimum":1},
       "nome":{"type":"string","maxLength":200},
       "papel":{"type":"string","enum":["A4","A3","A2","A1","A0","carta"]},
       "orientacao":{"type":"string","enum":["retrato","paisagem"]},
       "margens_mm":{"type":"object","additionalProperties":false,
         "properties":{"superior":{"type":"number","minimum":0,"maximum":100},"inferior":{"type":"number","minimum":0,"maximum":100},
                       "esquerda":{"type":"number","minimum":0,"maximum":100},"direita":{"type":"number","minimum":0,"maximum":100}}},
       "modelo":{"type":"boolean"},
       "mapa_id":{"type":["string","null"],"pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
       "elementos":{"type":"array","maxItems":200,"items":{"type":"object","additionalProperties":true,"required":["tipo"],
         "properties":{
           "tipo":{"type":"string","enum":["mapa","legenda","escala","norte","grade","titulo","texto","imagem","tabela","data","atribuicao"]},
           "id":{"type":"string","maxLength":64},
           "x":{"type":"number","minimum":0},"y":{"type":"number","minimum":0},
           "w":{"type":"number","minimum":0},"h":{"type":"number","minimum":0}}}}}}'::jsonb,
   1, 'layout', '/static/js/catalogo/tipos/layout.js', '{mapa}', false, 'L2-12')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo, descricao = EXCLUDED.descricao,
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;
