-- Extensao do documento de estilo raster (item L2-02-f-estilo-raster): parametros_raster ganha
-- bandas (composicao RGB/banda unica), resampling, nodata e esticamento (o metodo que o editor usou
-- para pedir o rescale a /estatisticas.json, item L1-02) -- ver docs/esquemas/estilo-v1-fonte.json.
-- Correcao em arquivo NOVO (regra do brief comum): a migracao 20260907T1148_estilo_modelo.sql ja foi
-- aplicada e nao pode ser editada. Idempotente (UPDATE puro).

UPDATE plat.tipo_item SET esquema = $esquema_estilo${
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "additionalProperties": false,
  "description": "Estilo de camada em duas partes (ADR do item L2-02-a; C2 do L2_CONCEITO): `maplibre` = layers da MapLibre Style Spec v8 puras, validadas pelo pacote oficial no servidor; `plat_construtor` = o que o editor precisa para reabrir o estilo (tipo, campo, método, cortes, rampa, símbolo, rótulos, faixa de escala, transparência).",
  "properties": {
    "corpo": {
      "additionalProperties": false,
      "properties": {
        "maplibre": {
          "additionalProperties": false,
          "description": "subconjunto da MapLibre Style Spec v8: version/layers conferidos aqui, o resto pelo validador oficial (ferramentas/estilo). Layers referenciam a fonte da camada pelo id simbólico `camada` (sem `sources`: a fonte real é ligada na renderização, nunca gravada no documento).",
          "properties": {
            "glyphs": {
              "anyOf": [
                {
                  "maxLength": 300,
                  "pattern": "^/fontes/[a-z0-9][a-z0-9._/{}-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "layers": {
              "description": "layers da Style Spec; teto espelhado de app/limites.py ESTILO_CAMADAS_MAX",
              "items": {
                "type": "object"
              },
              "maxItems": 200,
              "minItems": 1,
              "type": "array"
            },
            "sprite": {
              "anyOf": [
                {
                  "maxLength": 300,
                  "pattern": "^/sprites/[a-z0-9][a-z0-9._/-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "description": "só caminho interno (servido pelo Martin, L2-02-e); URL absoluta externa é recusada aqui e reforçada em app/estilos/validador.py"
            },
            "version": {
              "const": 8
            }
          },
          "required": [
            "version",
            "layers"
          ],
          "type": "object"
        },
        "plat_construtor": {
          "additionalProperties": false,
          "description": "bloco do construtor: o editor reabre o estilo a partir daqui; o bloco maplibre é gerado destes parâmetros.",
          "properties": {
            "agrupamento": {
              "additionalProperties": false,
              "description": "tipo agrupamento: clusteriza pontos por proximidade; degraus por contagem acumulada",
              "properties": {
                "degraus": {
                  "items": {
                    "additionalProperties": false,
                    "properties": {
                      "ate": {
                        "minimum": 0,
                        "type": [
                          "integer",
                          "null"
                        ]
                      },
                      "cor": {
                        "pattern": "^#[0-9a-fA-F]{6}$",
                        "type": "string"
                      },
                      "raio": {
                        "maximum": 100,
                        "minimum": 1,
                        "type": "number"
                      }
                    },
                    "required": [
                      "cor",
                      "raio"
                    ],
                    "type": "object"
                  },
                  "maxItems": 10,
                  "minItems": 1,
                  "type": "array"
                },
                "raio_px": {
                  "maximum": 200,
                  "minimum": 1,
                  "type": "number"
                }
              },
              "required": [
                "raio_px",
                "degraus"
              ],
              "type": "object"
            },
            "calor": {
              "additionalProperties": false,
              "description": "tipo calor: mapa de densidade (heatmap); so faz sentido sobre geometria ponto",
              "properties": {
                "intensidade": {
                  "maximum": 10,
                  "minimum": 0,
                  "type": "number"
                },
                "raio_px": {
                  "maximum": 200,
                  "minimum": 1,
                  "type": "number"
                },
                "rampa": {
                  "items": {
                    "pattern": "^#[0-9a-fA-F]{6}$",
                    "type": "string"
                  },
                  "maxItems": 8,
                  "minItems": 2,
                  "type": "array"
                }
              },
              "required": [
                "intensidade",
                "raio_px"
              ],
              "type": "object"
            },
            "campo": {
              "anyOf": [
                {
                  "maxLength": 63,
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "description": "campo principal do estilo (obrigatório em categoria/classes/proporcional; nulo em unico/raster)"
            },
            "campos": {
              "description": "vocabulário de campos que as expressões MapLibre deste estilo podem ler (o editor grava os campos da camada); referência fora da lista = 422 campo_inexistente",
              "items": {
                "maxLength": 63,
                "type": "string"
              },
              "maxItems": 100,
              "type": "array"
            },
            "categorias": {
              "description": "tipo categoria: cor por valor distinto do campo",
              "items": {
                "additionalProperties": false,
                "properties": {
                  "cor": {
                    "pattern": "^#[0-9a-fA-F]{6}$",
                    "type": "string"
                  },
                  "rotulo": {
                    "maxLength": 250,
                    "type": "string"
                  },
                  "valor": {
                    "type": [
                      "string",
                      "number",
                      "boolean"
                    ]
                  }
                },
                "required": [
                  "valor",
                  "cor"
                ],
                "type": "object"
              },
              "maxItems": 200,
              "type": "array"
            },
            "classes": {
              "description": "tipo classes: faixas [min, max) do campo com cor; a última fecha em max inclusive",
              "items": {
                "additionalProperties": false,
                "properties": {
                  "cor": {
                    "pattern": "^#[0-9a-fA-F]{6}$",
                    "type": "string"
                  },
                  "max": {
                    "type": "number"
                  },
                  "min": {
                    "type": "number"
                  },
                  "rotulo": {
                    "maxLength": 250,
                    "type": "string"
                  }
                },
                "required": [
                  "min",
                  "max",
                  "cor"
                ],
                "type": "object"
              },
              "maxItems": 64,
              "type": "array"
            },
            "cortes": {
              "description": "quebras de classe escolhidas (quando metodo != nenhum)",
              "items": {
                "type": "number"
              },
              "maxItems": 64,
              "type": "array"
            },
            "escala_max": {
              "description": "maior denominador de escala em que o estilo desenha; 0 = sem limite",
              "maximum": 1000000000,
              "minimum": 0,
              "type": "number"
            },
            "escala_min": {
              "description": "menor denominador de escala em que o estilo desenha; 0 = sem limite",
              "maximum": 1000000000,
              "minimum": 0,
              "type": "number"
            },
            "geometria": {
              "description": "família de geometria a que o estilo se aplica",
              "enum": [
                "ponto",
                "linha",
                "poligono",
                "raster"
              ],
              "type": "string"
            },
            "metodo": {
              "description": "método de classificação (só faz sentido em classes/proporcional)",
              "enum": [
                "nenhum",
                "manual",
                "intervalo_igual",
                "quantil",
                "quebras_naturais",
                "desvio_padrao"
              ],
              "type": "string"
            },
            "parametros_raster": {
              "additionalProperties": false,
              "description": "tipo raster: vocabulário de parâmetros de URL do TiTiler (C2 do L2_CONCEITO; L1-02 documenta)",
              "properties": {
                "colormap_name": {
                  "maxLength": 64,
                  "type": "string"
                },
                "expression": {
                  "maxLength": 500,
                  "type": "string"
                },
                "rescale": {
                  "items": {
                    "type": "number"
                  },
                  "maxItems": 2,
                  "minItems": 2,
                  "type": "array"
                },
                "bandas": {
                  "description": "composição de bandas para o ladrilho (1 banda = cinza/rampa; 3 = RGB); índice 1-based",
                  "items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 64
                  },
                  "minItems": 1,
                  "maxItems": 4,
                  "type": "array"
                },
                "resampling": {
                  "description": "reamostragem pedida pelo editor; L1-02 ainda só serve o padrão do rio-tiler (vizinho) — 'bilinear' fica registrado no documento para quando o ladrilho aceitar (ver docs/PARIDADE.md)",
                  "enum": [
                    "vizinho",
                    "bilinear"
                  ],
                  "type": "string"
                },
                "nodata": {
                  "description": "nodata declarado pelo editor para documentação/legenda; o ladrilho usa o nodata do próprio COG (não há parâmetro de sobrescrita no L1-02 hoje)",
                  "type": [
                    "number",
                    "null"
                  ]
                },
                "esticamento": {
                  "additionalProperties": false,
                  "description": "método usado para PROPOR o rescale gravado (a rota /estatisticas.json do L1-02 calcula os números; este bloco só registra qual método o editor usou, para reabrir a mesma escolha)",
                  "properties": {
                    "metodo": {
                      "enum": [
                        "minmax",
                        "percentil_2_98",
                        "desvio_padrao",
                        "nenhum"
                      ],
                      "type": "string"
                    }
                  },
                  "required": [
                    "metodo"
                  ],
                  "type": "object"
                }
              },
              "type": "object"
            },
            "proporcional": {
              "additionalProperties": false,
              "description": "tipo proporcional: raio do simbolo escala linearmente entre raio_min e raio_max conforme o campo numerico, entre valor_min e valor_max observados",
              "properties": {
                "cor": {
                  "pattern": "^#[0-9a-fA-F]{6}$",
                  "type": "string"
                },
                "raio_max": {
                  "maximum": 100,
                  "minimum": 0,
                  "type": "number"
                },
                "raio_min": {
                  "maximum": 100,
                  "minimum": 0,
                  "type": "number"
                },
                "valor_max": {
                  "type": "number"
                },
                "valor_min": {
                  "type": "number"
                }
              },
              "required": [
                "raio_min",
                "raio_max",
                "valor_min",
                "valor_max"
              ],
              "type": "object"
            },
            "rampa": {
              "anyOf": [
                {
                  "maxLength": 64,
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "description": "nome da rampa de cor aplicada (a cor concreta fica em categorias/classes/simbolo)"
            },
            "rotulos": {
              "anyOf": [
                {
                  "additionalProperties": false,
                  "properties": {
                    "campo": {
                      "maxLength": 63,
                      "type": "string"
                    },
                    "cor": {
                      "pattern": "^#[0-9a-fA-F]{6}$",
                      "type": "string"
                    },
                    "tamanho": {
                      "maximum": 72,
                      "minimum": 4,
                      "type": "number"
                    },
                    "visivel": {
                      "type": "boolean"
                    }
                  },
                  "required": [
                    "visivel",
                    "campo"
                  ],
                  "type": "object"
                },
                {
                  "type": "null"
                }
              ]
            },
            "simbolo": {
              "additionalProperties": false,
              "description": "parâmetros do símbolo base (usado por unico e como molde dos demais tipos)",
              "properties": {
                "contorno_cor": {
                  "pattern": "^#[0-9a-fA-F]{6}$",
                  "type": "string"
                },
                "contorno_largura": {
                  "maximum": 40,
                  "minimum": 0,
                  "type": "number"
                },
                "cor": {
                  "pattern": "^#[0-9a-fA-F]{6}$",
                  "type": "string"
                },
                "icone": {
                  "anyOf": [
                    {
                      "maxLength": 64,
                      "pattern": "^[a-z0-9][a-z0-9._-]*$",
                      "type": "string"
                    },
                    {
                      "type": "null"
                    }
                  ]
                },
                "largura": {
                  "maximum": 40,
                  "minimum": 0,
                  "type": "number"
                },
                "opacidade": {
                  "maximum": 1,
                  "minimum": 0,
                  "type": "number"
                },
                "raio": {
                  "maximum": 100,
                  "minimum": 0,
                  "type": "number"
                }
              },
              "type": "object"
            },
            "tipo": {
              "enum": [
                "unico",
                "categoria",
                "classes",
                "proporcional",
                "calor",
                "agrupamento",
                "raster"
              ],
              "type": "string"
            },
            "transparencia": {
              "description": "0 = opaco, 1 = invisível; aplicada sobre a opacidade do símbolo",
              "maximum": 1,
              "minimum": 0,
              "type": "number"
            },
            "versao": {
              "description": "versão do bloco plat_construtor (este documento escreve 1)",
              "minimum": 1,
              "type": "integer"
            }
          },
          "required": [
            "tipo",
            "geometria",
            "versao"
          ],
          "type": "object"
        }
      },
      "required": [
        "maplibre",
        "plat_construtor"
      ],
      "type": "object"
    },
    "esquema_versao": {
      "minimum": 1,
      "type": "integer"
    }
  },
  "required": [
    "esquema_versao",
    "corpo"
  ],
  "title": "documento de estilo do plat (estilo-v1)",
  "type": "object"
}$esquema_estilo$::jsonb
WHERE nome = 'estilo';
