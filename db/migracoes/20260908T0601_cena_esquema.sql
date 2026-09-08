-- 20260908T0601_cena_esquema (item L2-09-b-cena-extrusao-slides): o tipo `cena` deixa de ter o envelope
-- vazio da migração 011 e passa a ter o esquema próprio do documento de cena — câmera, terreno, iluminação,
-- atmosfera, camadas com extrusão por atributo e slides (vistas salvas). Continua sendo o MESMO mecanismo
-- genérico do L0-03 (plat.item.dados + plat.tipo_item.esquema + plat.item_versao): nenhuma tabela nova.
--
-- `esquema_versao` continua 1 de propósito: o envelope antigo aceitava qualquer `corpo`, e todo `corpo`
-- que existia até aqui ({} nas bancadas de teste) continua válido — nenhum documento gravado fica fora do
-- esquema novo, logo não há migração de leitura a fazer (app/catalogo/documento.py). Campo nenhum é
-- obrigatório dentro de `corpo`; quem abre a cena aplica o padrão do visualizador ao que faltar.
--
-- O que o JSON Schema NÃO expressa e por isso mora em app/cena/documento.py: id de camada/slide repetido,
-- slide que cita camada inexistente, e extrusão sem altura (nem campo, nem valor fixo).
-- Idempotente: UPDATE sobre a linha semeada em 011_catalogo.sql.

UPDATE plat.tipo_item SET
  descricao = 'documento de cena 3D (câmera, terreno, extrusão por atributo, slides)',
  esquema = $esq${
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object", "additionalProperties": false,
  "required": ["esquema_versao", "corpo"],
  "properties": {
    "esquema_versao": {"type": "integer", "minimum": 1},
    "corpo": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "camera": {"$ref": "#/$defs/camera"},
        "terreno": {
          "type": "object", "additionalProperties": false,
          "properties": {
            "ligado": {"type": "boolean"},
            "url": {"type": "string", "maxLength": 2048},
            "codificacao": {"type": "string", "enum": ["terrain-rgb", "terrarium"]},
            "tamanho_tile": {"type": "integer", "enum": [256, 512]},
            "zoom_maximo": {"type": "integer", "minimum": 0, "maximum": 22},
            "exagero": {"type": "number", "minimum": 0, "maximum": 8}
          }
        },
        "iluminacao": {
          "type": "object", "additionalProperties": false,
          "properties": {
            "modo": {"type": "string", "enum": ["data_hora", "fixa"]},
            "instante": {"type": "string", "format": "date-time", "maxLength": 40},
            "azimute": {"type": "number", "minimum": 0, "maximum": 360},
            "elevacao": {"type": "number", "minimum": -90, "maximum": 90},
            "intensidade": {"type": "number", "minimum": 0, "maximum": 1},
            "cor": {"$ref": "#/$defs/cor"}
          }
        },
        "atmosfera": {
          "type": "object", "additionalProperties": false,
          "properties": {
            "ceu": {"type": "boolean"},
            "cor_horizonte": {"$ref": "#/$defs/cor"},
            "nevoa": {
              "type": "object", "additionalProperties": false,
              "properties": {
                "ligada": {"type": "boolean"},
                "inicio": {"type": "number", "minimum": 0, "maximum": 1},
                "fim": {"type": "number", "minimum": 0, "maximum": 1},
                "cor": {"$ref": "#/$defs/cor"}
              }
            }
          }
        },
        "camadas": {
          "type": "array", "maxItems": 200,
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["id", "camada_id"],
            "properties": {
              "id": {"$ref": "#/$defs/ulid"},
              "camada_id": {"$ref": "#/$defs/uuid"},
              "titulo": {"type": "string", "maxLength": 300},
              "visivel": {"type": "boolean"},
              "desenho": {"type": "string", "enum": ["extrusao", "icone", "linha_elevada"]},
              "opacidade": {"type": "number", "minimum": 0, "maximum": 1},
              "cor": {"$ref": "#/$defs/cor"},
              "cor_por_campo": {
                "type": "object", "additionalProperties": false,
                "required": ["campo", "paradas"],
                "properties": {
                  "campo": {"$ref": "#/$defs/campo"},
                  "paradas": {
                    "type": "array", "minItems": 1, "maxItems": 30,
                    "items": {
                      "type": "object", "additionalProperties": false,
                      "required": ["valor", "cor"],
                      "properties": {"valor": {"type": "number"}, "cor": {"$ref": "#/$defs/cor"}}
                    }
                  }
                }
              },
              "extrusao": {
                "type": "object", "additionalProperties": false,
                "properties": {
                  "campo_altura": {"$ref": "#/$defs/campo"},
                  "altura_fixa": {"type": "number", "minimum": 0, "maximum": 10000},
                  "campo_base": {"$ref": "#/$defs/campo"},
                  "base_fixa": {"type": "number", "minimum": 0, "maximum": 10000},
                  "escala": {"type": "number", "minimum": 0, "maximum": 1000},
                  "gradiente_vertical": {"type": "boolean"}
                }
              },
              "icone": {
                "type": "object", "additionalProperties": false,
                "properties": {
                  "campo_altura": {"$ref": "#/$defs/campo"},
                  "altura_fixa": {"type": "number", "minimum": 0, "maximum": 10000},
                  "tamanho": {"type": "number", "minimum": 0.1, "maximum": 20}
                }
              },
              "linha": {
                "type": "object", "additionalProperties": false,
                "properties": {
                  "campo_altura": {"$ref": "#/$defs/campo"},
                  "altura_fixa": {"type": "number", "minimum": 0, "maximum": 10000},
                  "largura": {"type": "number", "minimum": 0.1, "maximum": 60}
                }
              }
            }
          }
        },
        "slides": {
          "type": "array", "maxItems": 100,
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["id", "nome", "camera"],
            "properties": {
              "id": {"$ref": "#/$defs/ulid"},
              "nome": {"type": "string", "minLength": 1, "maxLength": 200},
              "camera": {"$ref": "#/$defs/camera"},
              "camadas_visiveis": {"type": "array", "maxItems": 200, "items": {"$ref": "#/$defs/ulid"}},
              "instante": {"type": "string", "format": "date-time", "maxLength": 40},
              "exagero": {"type": "number", "minimum": 0, "maximum": 8},
              "miniatura": {"type": "string", "maxLength": 200000, "pattern": "^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$"}
            }
          }
        }
      }
    }
  },
  "$defs": {
    "cor": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
    "uuid": {"type": "string", "format": "uuid", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
    "ulid": {"type": "string", "pattern": "^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
    "campo": {"type": "string", "minLength": 1, "maxLength": 63, "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
    "camera": {
      "type": "object", "additionalProperties": false,
      "required": ["centro"],
      "properties": {
        "centro": {"type": "array", "minItems": 2, "maxItems": 2,
                   "prefixItems": [{"type": "number", "minimum": -180, "maximum": 180},
                                   {"type": "number", "minimum": -85.05, "maximum": 85.05}],
                   "items": {"type": "number"}},
        "zoom": {"type": "number", "minimum": 0, "maximum": 24},
        "inclinacao": {"type": "number", "minimum": 0, "maximum": 85},
        "rotacao": {"type": "number", "minimum": 0, "maximum": 360}
      }
    }
  }
}$esq$::jsonb
WHERE nome = 'cena';
