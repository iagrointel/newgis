-- Vista móvel do documento de construtor (item L5-15-vista-movel-responsivo; depende de L5-05/L5-08).
-- Acrescenta `corpo.vista_movel` ao esquema de grafo de 'app'/'painel' (028_documento_grafo.sql), de 2 para 3:
--   vista_movel.manual   (boolean)  -- true = a lista de corpo.vista_movel.nos MANDA na vista de celular
--                                       (prevalece sobre o reflow automático); false/ausente = reflow puro.
--   vista_movel.nos      (mapa id-de-nó-da-raiz -> {oculto, ordem, largura_colunas}) -- só nós de raiz (D1
--                          deste item: profundidade 1; um contêiner aninhado herda o reflow do pai).
-- Documento sem 'vista_movel' continua válido (chave opcional, como nos/ligacoes já eram na 028); quem grava
-- de novo sem mexer na vista móvel simplesmente não manda a chave. A leitura preenche o padrão
-- {"manual": false, "nos": {}} via app/catalogo/documento.py::_migrar_app_v2_v3/_migrar_painel_v2_v3 (nunca
-- grava de volta sozinha — mesma disciplina da 028).
--
-- esquema_versao só CRESCE (guarda WHERE esquema_versao < 3): reaplicar não regride.

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
          "vista_movel":{"type":"object","additionalProperties":false,
            "properties":{
              "manual":{"type":"boolean"},
              "nos":{"type":"object",
                "additionalProperties":{"type":"object","additionalProperties":false,
                  "properties":{
                    "oculto":{"type":"boolean"},
                    "ordem":{"type":"integer","minimum":0,"maximum":100000},
                    "largura_colunas":{"type":"integer","minimum":1,"maximum":12}
                  }}}
            }}
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
          "vista_movel":{"type":"object","additionalProperties":false,
            "properties":{
              "manual":{"type":"boolean"},
              "nos":{"type":"object",
                "additionalProperties":{"type":"object","additionalProperties":false,
                  "properties":{
                    "oculto":{"type":"boolean"},
                    "ordem":{"type":"integer","minimum":0,"maximum":100000},
                    "largura_colunas":{"type":"integer","minimum":1,"maximum":12}
                  }}}
            }}
        }}
    }}'::jsonb
WHERE nome = 'painel' AND esquema_versao < 3;
