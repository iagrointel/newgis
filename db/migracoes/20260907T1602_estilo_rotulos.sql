-- Estende o esquema do tipo `estilo` com o vocabulario completo de rotulos (item
-- L2-02-d-rotulos): classes com filtro/faixa de escala, texto por campo ou por expressao da
-- linguagem do L2-10-c, fonte/tamanho/cor/halo, ancora e deslocamento (ponto), rotulo ao longo da
-- linha com repeticao, posicao no poligono, varias linhas, maiusculas, unidade, prioridade e
-- permitir_sobreposicao. Substitui o bloco simples {visivel, campo, cor, tamanho} da migracao
-- 20260907T1148_estilo_modelo.sql (nenhum estilo gravado ainda por nenhum construtor: mesmo
-- raciocinio das migracoes anteriores da familia, apertar o esquema nao migra conteudo).
-- Idempotente (UPDATE com o esquema completo).

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
                    "classes": {
                      "description": "1+ classes de rótulo; a 1ª sem filtro (ou a única) é a classe padrão; várias classes = 1 layer MapLibre por classe, na mesma ordem (prioridade decide colisão, não a ordem dos layers)",
                      "items": {
                        "additionalProperties": false,
                        "properties": {
                          "ancora": {
                            "description": "âncora do símbolo (ponto); ignorada em linha/polígono",
                            "enum": [
                              "center",
                              "left",
                              "right",
                              "top",
                              "bottom",
                              "top-left",
                              "top-right",
                              "bottom-left",
                              "bottom-right"
                            ]
                          },
                          "ao_longo_da_linha": {
                            "description": "geometria linha: rótulo segue a linha (symbol-placement=line) em vez de um ponto único",
                            "type": "boolean"
                          },
                          "cor": {
                            "pattern": "^#[0-9a-fA-F]{6}$",
                            "type": "string"
                          },
                          "deslocamento": {
                            "description": "[x, y] em 'em' (tamanho da fonte); ponto/polígono",
                            "items": {
                              "type": "number"
                            },
                            "maxItems": 2,
                            "minItems": 2,
                            "type": "array"
                          },
                          "escala_max": {
                            "maximum": 1000000000,
                            "minimum": 0,
                            "type": "number"
                          },
                          "escala_min": {
                            "description": "maior denominador de escala em que a classe desenha (0 = sem limite); mesma convenção de plat_construtor.escala_min",
                            "maximum": 1000000000,
                            "minimum": 0,
                            "type": "number"
                          },
                          "filtro": {
                            "anyOf": [
                              {
                                "additionalProperties": false,
                                "properties": {
                                  "campo": {
                                    "maxLength": 63,
                                    "type": "string"
                                  },
                                  "operador": {
                                    "enum": [
                                      "==",
                                      "!=",
                                      "<",
                                      "<=",
                                      ">",
                                      ">="
                                    ]
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
                                  "campo",
                                  "operador",
                                  "valor"
                                ],
                                "type": "object"
                              },
                              {
                                "type": "null"
                              }
                            ],
                            "description": "condição simples que decide se esta classe de rótulo se aplica à feição; nulo = aplica-se a todas (classe padrão)"
                          },
                          "fonte": {
                            "description": "pilha de glifos pelo nome publicado no catálogo do Martin (item L2-02-e); padrão ['Noto Sans Regular']",
                            "items": {
                              "maxLength": 80,
                              "type": "string"
                            },
                            "maxItems": 2,
                            "minItems": 1,
                            "type": "array"
                          },
                          "halo_cor": {
                            "anyOf": [
                              {
                                "pattern": "^#[0-9a-fA-F]{6}$",
                                "type": "string"
                              },
                              {
                                "type": "null"
                              }
                            ]
                          },
                          "halo_largura": {
                            "maximum": 10,
                            "minimum": 0,
                            "type": "number"
                          },
                          "maiusculas": {
                            "description": "text-transform: uppercase",
                            "type": "boolean"
                          },
                          "nome": {
                            "description": "identifica a classe na legenda/editor; não entra no desenho",
                            "maxLength": 120,
                            "type": "string"
                          },
                          "permitir_sobreposicao": {
                            "description": "text-allow-overlap: ignora o índice de colisão para esta classe",
                            "type": "boolean"
                          },
                          "posicao_poligono": {
                            "description": "centro geométrico (pode cair fora de polígono côncavo) ou ponto interior garantido",
                            "enum": [
                              "centro",
                              "ponto_interior"
                            ]
                          },
                          "prioridade": {
                            "description": "número MENOR = mais importante (convenção do editor); compilado para symbol-sort-key NEGADO, porque o MapLibre real faz o sort-key MAIOR vencer a colisão (medido em tests/e2e/test_rotulos_render.py::test_prioridade_classe_a_vence_b_em_colisao)",
                            "maximum": 1000,
                            "minimum": 0,
                            "type": "integer"
                          },
                          "repetir_px": {
                            "anyOf": [
                              {
                                "maximum": 2000,
                                "minimum": 20,
                                "type": "number"
                              },
                              {
                                "type": "null"
                              }
                            ],
                            "description": "distância de repetição do rótulo ao longo da linha (symbol-spacing); nulo = um rótulo só"
                          },
                          "tamanho": {
                            "maximum": 72,
                            "minimum": 4,
                            "type": "number"
                          },
                          "tamanho_max": {
                            "anyOf": [
                              {
                                "maximum": 72,
                                "minimum": 4,
                                "type": "number"
                              },
                              {
                                "type": "null"
                              }
                            ]
                          },
                          "tamanho_zoom_max": {
                            "anyOf": [
                              {
                                "maximum": 24,
                                "minimum": 0,
                                "type": "number"
                              },
                              {
                                "type": "null"
                              }
                            ]
                          },
                          "tamanho_zoom_min": {
                            "anyOf": [
                              {
                                "maximum": 24,
                                "minimum": 0,
                                "type": "number"
                              },
                              {
                                "type": "null"
                              }
                            ],
                            "description": "zoom onde `tamanho` vale; com `tamanho_zoom_max`/`tamanho_max` forma uma interpolação linear de tamanho por zoom"
                          },
                          "texto": {
                            "additionalProperties": false,
                            "description": "fonte do texto do rótulo: exatamente um de `campo` (leitura direta) ou `expressao` (linguagem do item L2-10-c; compilada para MapLibre quando possível, senão pré-calculada no servidor — app/estilos/rotulos_servidor.py)",
                            "properties": {
                              "campo": {
                                "anyOf": [
                                  {
                                    "maxLength": 63,
                                    "type": "string"
                                  },
                                  {
                                    "type": "null"
                                  }
                                ]
                              },
                              "expressao": {
                                "anyOf": [
                                  {
                                    "maxLength": 500,
                                    "type": "string"
                                  },
                                  {
                                    "type": "null"
                                  }
                                ]
                              }
                            },
                            "type": "object"
                          },
                          "unidade": {
                            "anyOf": [
                              {
                                "maxLength": 20,
                                "type": "string"
                              },
                              {
                                "type": "null"
                              }
                            ],
                            "description": "sufixo concatenado ao texto (ex. 'ha', 'km'); nunca aplicado à coluna do servidor sem passar pela mesma expressão"
                          },
                          "varias_linhas_largura_max": {
                            "anyOf": [
                              {
                                "maximum": 40,
                                "minimum": 1,
                                "type": "number"
                              },
                              {
                                "type": "null"
                              }
                            ],
                            "description": "text-max-width em 'em'; nulo = uma linha só (largura 0 nativa do MapLibre)"
                          }
                        },
                        "required": [
                          "texto"
                        ],
                        "type": "object"
                      },
                      "maxItems": 20,
                      "minItems": 1,
                      "type": "array"
                    },
                    "visivel": {
                      "type": "boolean"
                    }
                  },
                  "required": [
                    "visivel",
                    "classes"
                  ],
                  "type": "object"
                },
                {
                  "type": "null"
                }
              ],
              "description": "rótulos da camada (item L2-02-d-rotulos); null ou ausente = sem rótulo"
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
