-- Temas de marca (item L5-10-temas-marca). Nada de tabela nova: o tema do inquilino vive em
-- plat.tenant.config -> chave 'tema' (mesma coluna jsonb que o L0-07-a e o L0-02 já usam; gravada só por
-- PUT /api/org/tema, app/rotas_temas.py) e o tema por documento vive em corpo.tema dos tipos app/painel.
-- Esta migração só: (1) substitui o esquema v2 de 'app' e 'painel' (028_documento_grafo.sql) pelo v3,
-- que aceita a chave OPCIONAL corpo.tema — {"id": <padrão|inquilino>} ou {"definicao": {tokens}}; a
-- validação PROFUNDA dos tokens (formato de cor, lista fechada de fontes, medida, sombra) é do
-- app/temas.py::validar_referencia_de_documento, chamada por documento.validar_grafo, porque JSON Schema
-- não expressa a lista fechada de fontes sem duplicar o vocabulário em dois lugares; (2) registra o
-- vocabulário de evento do tema do inquilino. Idempotente; sem BEGIN/COMMIT; esquema_versao só cresce.
-- A migração de DADO antigo (v2 -> v3) não muda corpo nenhum: tema ausente continua ausente (documento sem
-- tema renderiza com o padrão) — app/catalogo/documento.py::_MIGRACOES só sobe o número na leitura.

UPDATE plat.tipo_item SET esquema_versao = 3, esquema =
  '{"$schema":"https://json-schema.org/draft/2020-12/schema",
    "title":"Documento de construtor — aplicativo",
    "type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
    "properties":{
      "tipo":{"const":"app"},
      "esquema_versao":{"type":"integer","minimum":1},
      "corpo":{"type":"object","additionalProperties":false,
        "properties":{
          "nos":{"type":"array","maxItems":2000,
            "items":{"type":"object","required":["id","tipo"],
              "properties":{
                "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "tipo":{"type":"string","minLength":1,"maxLength":60}
              }}},
          "ligacoes":{"type":"array","maxItems":4000,
            "items":{"type":"object","required":["origem","alvo"],
              "properties":{
                "origem":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "alvo":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "tipo":{"type":"string","maxLength":60}
              }}},
          "mapas":{"type":"array","items":{"type":"string","format":"uuid"}},
          "mapa_id":{"type":"string","format":"uuid"},
          "tema":{"oneOf":[
            {"type":"object","additionalProperties":false,"required":["id"],
             "properties":{"id":{"type":"string","minLength":1,"maxLength":60}}},
            {"type":"object","additionalProperties":false,"required":["definicao"],
             "properties":{"definicao":{"type":"object"}}}
          ]}
        }}
    }}'::jsonb
WHERE nome = 'app' AND esquema_versao < 3;

UPDATE plat.tipo_item SET esquema_versao = 3, esquema =
  '{"$schema":"https://json-schema.org/draft/2020-12/schema",
    "title":"Documento de construtor — painel",
    "type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
    "properties":{
      "tipo":{"const":"painel"},
      "esquema_versao":{"type":"integer","minimum":1},
      "corpo":{"type":"object","additionalProperties":false,
        "properties":{
          "nos":{"type":"array","maxItems":2000,
            "items":{"type":"object","required":["id","tipo"],
              "properties":{
                "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "tipo":{"type":"string","minLength":1,"maxLength":60}
              }}},
          "ligacoes":{"type":"array","maxItems":4000,
            "items":{"type":"object","required":["origem","alvo"],
              "properties":{
                "origem":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "alvo":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "tipo":{"type":"string","maxLength":60}
              }}},
          "mapas":{"type":"array","items":{"type":"string","format":"uuid"}},
          "mapa_id":{"type":"string","format":"uuid"},
          "tema":{"oneOf":[
            {"type":"object","additionalProperties":false,"required":["id"],
             "properties":{"id":{"type":"string","minLength":1,"maxLength":60}}},
            {"type":"object","additionalProperties":false,"required":["definicao"],
             "properties":{"definicao":{"type":"object"}}}
          ]}
        }}
    }}'::jsonb
WHERE nome = 'painel' AND esquema_versao < 3;

-- vocabulário novo de evento (append à tabela existente da 003; ON CONFLICT preserva reaplicação)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/tema_gravar', 'tema do inquilino gravado ou removido (PUT /api/org/tema; marca própria do inquilino)')
ON CONFLICT (nome) DO NOTHING;
