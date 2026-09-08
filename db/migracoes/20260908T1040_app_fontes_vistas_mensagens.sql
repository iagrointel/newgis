-- app_fontes_vistas_mensagens: item L5-07-fontes-vistas-mensagens (L5_CONCEITO D4 e D5). O documento `app` passa
-- ao esquema 3: `corpo` ganha `fontes` (item do catálogo/caminho/embutida + campos tipados), `vistas` (fonte +
-- filtro CQL2-JSON + seleção + ordenação + campos) e `mensagens` (gatilho -> ações com relação). O JSON Schema
-- só confere a FORMA; a regra de relação entre fontes (tipos casam, espacial exige geometria) e os ciclos ficam em
-- app/app_modelo/validar.py, chamado por app/catalogo/documento.py junto com validar_grafo. Documento v2 é
-- migrado na leitura (as três listas vazias); esquema_versao só cresce.
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
          "fontes":{"type":"array","maxItems":50,
            "items":{"type":"object","required":["id","origem","campos"],
              "properties":{
                "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "nome":{"type":"string","maxLength":120},
                "origem":{"type":"object","required":["tipo"],
                  "properties":{"tipo":{"type":"string","enum":["item","url","embutida"]},
                    "item_id":{"type":"string","maxLength":64},"url":{"type":"string","maxLength":2000},
                    "feicoes":{"type":"array","maxItems":20000}}},
                "campos":{"type":"array","maxItems":500,
                  "items":{"type":"object","required":["nome","tipo"],
                    "properties":{"nome":{"type":"string","minLength":1,"maxLength":120},
                      "tipo":{"type":"string","enum":["texto","inteiro","decimal","booleano","data","data_hora","geometria"]},
                      "rotulo":{"type":"string","maxLength":120}}}}
              }}},
          "vistas":{"type":"array","maxItems":200,
            "items":{"type":"object","required":["id","fonte"],
              "properties":{
                "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "nome":{"type":"string","maxLength":120},
                "fonte":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "filtro":{"type":["object","null"]},
                "selecao":{"type":"array","maxItems":10000},
                "ordenacao":{"type":"array","maxItems":10,"items":{"type":"object","required":["campo"],
                  "properties":{"campo":{"type":"string","maxLength":120},"direcao":{"type":"string","enum":["asc","desc"]}}}},
                "campos":{"type":["array","null"],"maxItems":500,"items":{"type":"string","maxLength":120}}
              }}},
          "mensagens":{"type":"array","maxItems":500,
            "items":{"type":"object","required":["id","gatilho","acoes"],
              "properties":{
                "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
                "gatilho":{"type":"object","required":["origem","evento"],
                  "properties":{"origem":{"type":"string","maxLength":26},
                    "evento":{"type":"string","enum":["clique","dado_adicionado","filtro_mudou","extensao_mudou","localizacao","registros_carregados","selecao_mudou","vista_mudou"]}}},
                "acoes":{"type":"array","minItems":1,"maxItems":20,
                  "items":{"type":"object","required":["alvo","acao"],
                    "properties":{"alvo":{"type":"string","maxLength":26},
                      "acao":{"type":"string","enum":["filtrar","selecionar","limpar_filtro","limpar_selecao","zoom","pan","piscar","popup","abrir","fechar","definir_parametro"]},
                      "parametros":{"type":"object"},
                      "relacao":{"type":["object","null"],
                        "properties":{"tipo":{"type":"string","enum":["mesma_fonte","atributo","espacial"]},
                          "campo_origem":{"type":"string","maxLength":120},"campo_alvo":{"type":"string","maxLength":120},
                          "operador":{"type":"string","enum":["=","in"]}}}}}}
              }}},
          "mapas":{"type":"array","items":{"type":"string","format":"uuid"}},
          "mapa_id":{"type":"string","format":"uuid"}
        }}
    }}'::jsonb
WHERE nome = 'app' AND esquema_versao < 3;
