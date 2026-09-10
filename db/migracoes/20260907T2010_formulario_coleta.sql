-- Formulário de coleta por XLSForm (item L2-07-b-formulario-de-coleta-xlsform).
-- Reaproveita plat.item por inteiro (compartilhamento, lixeira, RLS, versões): o documento de formulário é um
-- item do tipo `formulario`; a camada de destino e as camadas filhas de repetição são `camada_vetorial` comuns,
-- ligadas por plat.item_relacao. Nenhuma tabela nova.
-- Idempotente (mesmo UPSERT do ADR 0004 seção 3: o esquema só troca se a versão nova for maior).

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                           tem_dado_fisico, linha_dona) VALUES
  ('formulario', 'formulario', 'Formulário de coleta',
   'documento de formulário (campos, regras de relevância/restrição/cálculo como AST da linguagem própria, listas de escolha) que grava respostas na camada de destino',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["versao","nome","titulo","campos","listas"],
     "properties":{
       "versao":{"type":"integer","minimum":1},
       "nome":{"type":"string","maxLength":250},
       "titulo":{"type":"string","maxLength":250},
       "versao_formulario":{"type":"string","maxLength":100},
       "idiomas":{"type":"array","items":{"type":"string"},"maxItems":50},
       "idioma_padrao":{"type":"string","maxLength":100},
       "campos":{"type":"array","items":{"type":"object","required":["nome","tipo"]},"maxItems":500},
       "listas":{"type":"object"},
       "camada_destino":{"type":["string","null"],"format":"uuid"},
       "camadas_filhas":{"type":"object","additionalProperties":{"type":"string","format":"uuid"}},
       "ordem_calculo":{"type":"array","items":{"type":"string"}},
       "avisos":{"type":"array","items":{"type":"object"}},
       "tem_geometria":{"type":"boolean"}}}'::jsonb,
   1, 'formulario', '/static/js/coleta/tela.js', '{/coleta}', false, 'L2-07-b')
ON CONFLICT (nome) DO UPDATE SET
  descricao      = EXCLUDED.descricao,
  esquema        = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

INSERT INTO plat.relacao_tipo VALUES
  ('formulario_de_camada', 'formulário grava respostas na camada',          '{formulario}', '{camada}', false, false),
  ('repeticao_de_camada',  'camada filha de repetição do formulário da camada pai', '{camada}', '{camada}', false, false)
ON CONFLICT (nome) DO NOTHING;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('formularios/importar',  'XLSForm importado como item formulario (L2-07-b)'),
  ('formularios/responder', 'resposta de formulário gravada como feição (L2-07-b)')
ON CONFLICT (nome) DO NOTHING;
