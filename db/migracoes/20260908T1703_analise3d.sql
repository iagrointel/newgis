-- 20260908T1703_analise3d: análise 3D sobre terreno e extrusões (item L2-09-d-analise-3d-visibilidade, linha L2).
--
-- Hipótese do item: as análises 3D do Scene Viewer (linha de visada, viewshed, perfil de elevação e sombra
-- projetada) têm implementação computável no servidor, com resultado reproduzível e proveniência declarada;
-- cada resultado pode ser guardado como item do catálogo (tipo `analise_3d`) com parâmetro, resultado e
-- procedência dentro do `dados`.
--
-- Esta migração NÃO cria tabela de resultado: o resultado da análise vive como ITEM do catálogo quando o
-- usuário pede (`salvar_item`), com o mesmo RLS e o mesmo ciclo de vida de qualquer item. O que o item cria:
--   * o tipo de item `analise_3d` (familia `documento`, sem dado físico), com JSON Schema que EXIGE os
--     quatro blocos `analise`, `parametros`, `resultado` e `procedencia` — item de análise sem procedência
--     não existe;
--   * os quatro eventos de domínio, um por rota de análise.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- ---------------------------------------------------------------- tipo_item analise_3d: esquema v1
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('analise_3d', 'documento', 'Análise 3D', 'resultado de análise 3D (visada, viewshed, perfil ou sombra) com procedência',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["analise","parametros","resultado","procedencia"],
     "properties":{
       "analise":{"type":"string","enum":["visada","viewshed","perfil","sombra"]},
       "parametros":{"type":"object","additionalProperties":true},
       "resultado":{"type":"object","additionalProperties":true},
       "procedencia":{"type":"object","additionalProperties":true}}}'::jsonb,
   1, 'analise', '/static/js/analise3d/painel.js', '{analise3d}', false, 'L2-09-d')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

-- ---------------------------------------------------------------- eventos novos (um por rota de análise)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('analise3d/visada', 'linha de visada entre observador e alvo amostrada no terreno (visível, ponto de obstrução)'),
  ('analise3d/viewshed', 'bacia visual calculada com gdal_viewshed (células visíveis, comando, sha de entrada e saída)'),
  ('analise3d/perfil', 'perfil de elevação ao longo de uma linha (ganho, perda, declividade máxima)'),
  ('analise3d/sombra', 'sombra projetada de sólidos por data e hora (posição solar, comprimento, polígono)')
ON CONFLICT (nome) DO NOTHING;
