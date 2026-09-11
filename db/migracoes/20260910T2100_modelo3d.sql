-- L1-03-modelo3d (10/09/2026): visualizador de modelo 3D (IFC/BIM convertido para .xkt) e foto 360 — a casa
-- já opera os dois dentro de um SIG de cliente (xeokit-convert + pannellum), isto é o mesmo módulo portado
-- para a plataforma. Dois tipos de item novos (`plat.tipo_item`) e os eventos que `app/modelo3d/*.py`
-- registra (`plat.evento_tipo`) — sem isso a rota dá 500 por chave estrangeira, MESMO defeito real do
-- L1-02 hoje cedo (ver 20260910T0245_imagens_evento_tipo.sql). Idempotente. Sem BEGIN/COMMIT.

-- família nova: nenhuma das 11 existentes (011_catalogo.sql) descreve um modelo 3D/foto 360 — não é camada,
-- não é raster (serving completamente diferente), não é documento genérico (tem visualizador dedicado).
-- Alarga o CHECK em vez de forçar um encaixe falso numa família existente (nome do constraint conferido na
-- trilha, 10/09/2026: é o padrão do Postgres para CHECK de coluna sem nome explícito, tipo_item_familia_check
-- — nenhuma outra migração o havia tocado até aqui).
ALTER TABLE plat.tipo_item DROP CONSTRAINT IF EXISTS tipo_item_familia_check;
ALTER TABLE plat.tipo_item ADD CONSTRAINT tipo_item_familia_check
  -- (união de ramos) a lista deste ramo não tinha site, narrativa, que outro ramo já semeou na tabela,
  -- e a restrição nascia violada. A forma da escrita original foi preservada.
  CHECK (familia = ANY (ARRAY['camada', 'raster', 'mapa', 'app', 'painel', 'formulario', 'fluxo', 'rede', 'arquivo', 'ferramenta', 'documento', 'modelo3d', 'site', 'narrativa']));

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('modelo3d', 'modelo3d', 'Modelo 3D', 'modelo BIM/IFC convertido para .xkt (visualizador xeokit)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["xkt_chave","origem"],
     "properties":{
       "xkt_chave":{"type":"string"},
       "origem":{"type":"string","enum":["ifc_convertido","xkt_enviado","amostra_gabarito"]},
       "ifc_chave":{"type":["string","null"]},
       "bytes_xkt":{"type":["integer","null"],"minimum":0},
       "conversao":{"type":["object","null"],"additionalProperties":true},
       "schema_ifc":{"type":["string","null"]},
       "projeto":{"type":["string","null"]},
       "pavimentos":{"type":"array","maxItems":200,"items":{"type":"string"}},
       "ambientes":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":true}},
       "n_ambientes":{"type":["integer","null"],"minimum":0},
       "n_elementos":{"type":["integer","null"],"minimum":0}}}'::jsonb,
   1, 'modelo3d', '/static/js/catalogo/tipos/modelo3d.js', '{modelo3d}', true, 'L1-03')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('foto360', 'modelo3d', 'Foto 360', 'foto equirretangular para o visualizador panorâmico (pannellum)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["imagem_chave"],
     "properties":{
       "imagem_chave":{"type":"string"},
       "origem":{"type":"string","enum":["enviada","amostra"]}}}'::jsonb,
   1, 'foto360', '/static/js/catalogo/tipos/foto360.js', '{foto360}', true, 'L1-03')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('modelo3d/ingestar', 'modelo 3D (L1-03): job modelo3d.converter criado a partir de um arquivo .ifc/.xkt'),
  ('foto360/criar', 'foto 360 (L1-03): item foto360 criado a partir de um arquivo .jpg enviado')
ON CONFLICT (nome) DO NOTHING;
