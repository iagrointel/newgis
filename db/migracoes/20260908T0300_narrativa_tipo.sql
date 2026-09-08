-- 20260908T0300_narrativa_tipo: tipo de item `narrativa` (item L5-04-a-blocos-de-conteudo), o construtor de
-- narrativa por blocos do L5 (D2 do L5_CONCEITO lista `narrativa` no envelope; faltava a linha em plat.tipo_item).
-- Mesmo envelope de documento do app/painel v2 (028_documento_grafo.sql): `corpo.nos` é a LISTA de blocos em
-- ordem de leitura, cada bloco com id ULID imutável, `tipo` (capa, texto, imagem, video, audio, mapa, tabela,
-- botao, separador, incorporar, aplicativo) e `propriedades` validadas campo a campo pela paleta
-- (web/js/editor/paleta_narrativa.js) e, ao publicar, por app/catalogo/narrativa.py (texto alternativo
-- obrigatório em imagem — a regra que o esquema não expressa). `ligacoes` fica vazio na v1 (blocos não se ligam).
-- Família própria `narrativa`: entra em FAMILIAS_GRAFO (validação de ULID/ligações no servidor) e em
-- FAMILIAS_PUBLICAVEIS do L5-14 (publica em /p/<inquilino>/<slug>).
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                           tem_dado_fisico, linha_dona)
SELECT 'narrativa', 'narrativa', 'Narrativa', 'narrativa por blocos (texto, mídia, mapa com vista salva; envelope L5)',
  '{"$schema":"https://json-schema.org/draft/2020-12/schema",
    "title":"Documento de construtor — narrativa",
    "type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
    "properties":{
      "tipo":{"const":"narrativa"},
      "esquema_versao":{"type":"integer","minimum":1},
      "corpo":{"type":"object","additionalProperties":false,
        "properties":{
          "nos":{"type":"array","maxItems":2000,
            "items":{"type":"object","required":["id","tipo"],
              "properties":{
                "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "tipo":{"type":"string","enum":["capa","texto","imagem","video","audio","mapa","tabela","botao","separador","incorporar","aplicativo"]},
                "pai":{"type":["string","null"]},
                "largura_colunas":{"type":"integer","minimum":1,"maximum":12},
                "propriedades":{"type":"object"}
              }}},
          "ligacoes":{"type":"array","maxItems":0}
        }}
    }}'::jsonb,
  1, 'narrativa', '/static/js/catalogo/tipos/narrativa.js', '{narrativa}', false, 'L5-04'
WHERE NOT EXISTS (SELECT 1 FROM plat.tipo_item WHERE nome = 'narrativa');

-- relações que a narrativa cita (app/catalogo/relacoes.py::_narrativa): o mapa do bloco `mapa` e o app/painel
-- do bloco `aplicativo` — é por elas que `camadas_citadas` (L5-14) chega às camadas do token da publicação
INSERT INTO plat.relacao_tipo
SELECT * FROM (VALUES
  ('mapa_de_narrativa', 'narrativa usa mapa',        ARRAY['narrativa'], ARRAY['mapa'],        false, false),
  ('app_de_narrativa',  'narrativa incorpora app/painel', ARRAY['narrativa'], ARRAY['app','painel'], false, false)
) AS v(nome, descricao, origens, destinos, a, b)
WHERE NOT EXISTS (SELECT 1 FROM plat.relacao_tipo rt WHERE rt.nome = v.nome);
