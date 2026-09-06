-- Documento de construtor (item L5-05-documento-versoes; ADR 0011; laco/decomposicao/L5_CONCEITO.md D2/D3).
-- Reaproveita por inteiro plat.item/plat.item_versao/plat.tipo_item de 011_catalogo.sql: não cria tabela nova,
-- só substitui o esquema TRIVIAL de 'app' e 'painel' (corpo:{}, sem forma) pelo esquema de GRAFO (corpo.nos com
-- id ULID por nó; corpo.ligacoes referenciando nós existentes — a unicidade de id e a referência pendente são
-- responsabilidade de app/catalogo/documento.py::validar_grafo, porque JSON Schema puro não expressa "compare a
-- lista inteira"). `nos`/`ligacoes` são OPCIONAIS no esquema (documento sem nó nenhum continua válido: `corpo:{}`
-- dos 1.573 itens 'app' e 1.571 'painel' já semeados em demo/demo2 passa nas duas versões) — o que muda é que,
-- QUANDO `nos` existe, cada nó precisa de ULID único e toda `ligacao` precisa apontar para um nó que existe.
-- `mapas`/`mapa_id` continuam declarados (não são deste item: são o contrato já entregue e testado de
-- app/catalogo/relacoes.py::_app, item L0-03-i — quebrar esse campo quebraria "usado-por" de app/painel→mapa).
--
-- A migração de esquema de verdade (documento antigo → novo) vive em app/catalogo/documento.py::migrar_para_leitura,
-- aplicada NA LEITURA (GET /api/itens/{id}), nunca gravada de volta no banco por esta migração nem por nenhum job.
--
-- esquema_versao só CRESCE (guarda WHERE esquema_versao < 2): rodar esta migração duas vezes não regride nem
-- reaplica; se algum dia um item novo já estiver em v2 por outra via, o UPDATE simplesmente não acha linha.

UPDATE plat.tipo_item SET esquema_versao = 2, esquema =
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
          "mapa_id":{"type":"string","format":"uuid"}
        }}
    }}'::jsonb
WHERE nome = 'app' AND esquema_versao < 2;

UPDATE plat.tipo_item SET esquema_versao = 2, esquema =
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
          "mapa_id":{"type":"string","format":"uuid"}
        }}
    }}'::jsonb
WHERE nome = 'painel' AND esquema_versao < 2;

-- vocabulário novo de evento: GET /api/itens/{id} registra quando devolve o documento já migrado para o
-- esquema vigente (app/catalogo/documento.py::migrar_para_leitura, nunca grava de volta no banco).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('itens/esquema_migrado', 'leitura devolveu dados migrados para o esquema_versao vigente do tipo (não gravado)')
ON CONFLICT (nome) DO NOTHING;
