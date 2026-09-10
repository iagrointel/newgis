/* plat — paleta de PÁGINAS E LAYOUT DO APP (item L5-01-a-layout-paginas).

   Superconjunto da PALETA_LAYOUT (grupo/texto/imagem/mapa/tabela, item L5-08) mais os tipos que fazem um
   documento `app` virar um APLICATIVO DE VÁRIAS PÁGINAS navegável: página (raiz do documento), cabeçalho,
   rodapé, menu, e os widgets de layout do Experience Builder que a hipótese enumera — linha, coluna, grade,
   acordeão, painel fixo, painel lateral e janela (que cobre tanto "modal" quanto "ancorada" da Esri, que na
   ferramenta deles não é um WIDGET e sim um tipo de PÁGINA à parte — ver PARIDADE.md).

   O editor (`web/js/editor/editor.js`) continua sem saber o nome de nenhum tipo: só lê `aceita_filhos`,
   `largura_padrao`, `propriedades_padrao` e `esquema`. Quem interpreta o SIGNIFICADO de `pagina`, `cabecalho`,
   `menu` etc. é o executor (`web/js/executor/executor.js`), na hora de renderizar o app de verdade.

   Convenção desta linha (documentada, não imposta pelas primitivas genéricas de `documento.js` — que são
   compartilhadas por doze construtores e não sabem o que é uma "página"): nós de tipo `pagina` só fazem
   sentido na RAIZ do documento (pai=null); os demais tipos entram dentro de uma página (ou dentro de outro
   contêiner de layout dentro dela). O editor genérico não bloqueia outra montagem — quem prova a montagem
   certa é o e2e do portão deste item. */

export const COLUNAS_GRADE_PADRAO = 3;

export const PALETA_PAGINAS = {
  nome: 'paginas',
  ordem: [
    'pagina', 'cabecalho', 'rodape', 'menu',
    'linha', 'coluna', 'grade', 'acordeao', 'painel_fixo', 'painel_lateral', 'janela',
    'secao_vistas', 'vista',
    'grupo', 'texto', 'imagem', 'mapa', 'tabela',
    'botao', 'cartao', 'incorporar', 'divisor', 'menu_widget', 'controlador', 'compartilhar', 'login', 'idioma', 'tema',
  ],
  tipos: {
    // ---------------------------------------------------------------- página (raiz do documento)
    pagina: {
      rotulo: 'Página',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { titulo: 'Nova página', caminho: 'pagina', tipo_pagina: 'rolavel', ordem: 0, oculta: false, inicial: false },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['titulo', 'caminho', 'tipo_pagina'],
        properties: {
          titulo: { type: 'string', title: 'Título', minLength: 1, maxLength: 80 },
          /* segmento de URL da página (usado em /executar?item=<id>&pagina=<caminho>): letra minúscula,
             dígito e hífen, para nunca precisar de escape na querystring nem no href do menu. */
          caminho: { type: 'string', title: 'Caminho (URL)', pattern: '^[a-z0-9]([a-z0-9-]{0,58}[a-z0-9])?$' },
          tipo_pagina: { type: 'string', title: 'Tipo de página', enum: ['tela_cheia', 'rolavel'], default: 'rolavel' },
          ordem: { type: 'integer', title: 'Ordem no menu', minimum: 0, maximum: 999, default: 0 },
          oculta: { type: 'boolean', title: 'Oculta do menu', default: false },
          inicial: { type: 'boolean', title: 'Página inicial', default: false },
        },
      },
    },
    cabecalho: {
      rotulo: 'Cabeçalho',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { fixo: true },
      esquema: {
        type: 'object', additionalProperties: false, required: ['fixo'],
        properties: { fixo: { type: 'boolean', title: 'Fixo ao rolar', default: true } },
      },
    },
    rodape: {
      rotulo: 'Rodapé',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { texto: '' },
      esquema: {
        type: 'object', additionalProperties: false, required: [],
        properties: { texto: { type: 'string', title: 'Texto', maxLength: 280, default: '' } },
      },
    },
    /* nav entre páginas do MESMO documento — não lê filho nenhum: a lista de links vem da lista de nós
       `pagina` da raiz do documento inteiro, ordenada por `ordem`, sem as `oculta` (o executor monta). */
    menu: {
      rotulo: 'Menu',
      aceita_filhos: false,
      largura_padrao: 12,
      propriedades_padrao: { estilo: 'horizontal' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['estilo'],
        properties: { estilo: { type: 'string', title: 'Estilo', enum: ['horizontal', 'vertical'], default: 'horizontal' } },
      },
    },

    // ---------------------------------------------------------------- os widgets de layout (paridade EXB)
    linha: {
      rotulo: 'Linha',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { alinhar: 'inicio' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['alinhar'],
        properties: { alinhar: { type: 'string', title: 'Alinhamento', enum: ['inicio', 'centro', 'fim', 'espacado'], default: 'inicio' } },
      },
    },
    coluna: {
      rotulo: 'Coluna',
      aceita_filhos: true,
      largura_padrao: 6,
      propriedades_padrao: { alinhar: 'inicio' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['alinhar'],
        properties: { alinhar: { type: 'string', title: 'Alinhamento', enum: ['inicio', 'centro', 'fim', 'espacado'], default: 'inicio' } },
      },
    },
    grade: {
      rotulo: 'Grade',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { colunas: COLUNAS_GRADE_PADRAO },
      esquema: {
        type: 'object', additionalProperties: false, required: ['colunas'],
        properties: { colunas: { type: 'integer', title: 'Colunas da grade', minimum: 1, maximum: 12, default: COLUNAS_GRADE_PADRAO } },
      },
    },
    acordeao: {
      rotulo: 'Acordeão',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { multiplo_aberto: false },
      esquema: {
        type: 'object', additionalProperties: false, required: ['multiplo_aberto'],
        properties: { multiplo_aberto: { type: 'boolean', title: 'Vários painéis abertos ao mesmo tempo', default: false } },
      },
    },
    painel_fixo: {
      rotulo: 'Painel fixo',
      aceita_filhos: true,
      largura_padrao: 4,
      propriedades_padrao: { posicao: 'superior-direita' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['posicao'],
        properties: {
          posicao: {
            type: 'string', title: 'Posição', default: 'superior-direita',
            enum: ['superior-direita', 'superior-esquerda', 'inferior-direita', 'inferior-esquerda'],
          },
        },
      },
    },
    painel_lateral: {
      rotulo: 'Painel lateral',
      aceita_filhos: true,
      largura_padrao: 4,
      propriedades_padrao: { lado: 'esquerda', recolhivel: true, aberto_inicial: true },
      esquema: {
        type: 'object', additionalProperties: false, required: ['lado', 'recolhivel'],
        properties: {
          lado: { type: 'string', title: 'Lado', enum: ['esquerda', 'direita'], default: 'esquerda' },
          recolhivel: { type: 'boolean', title: 'Recolhível', default: true },
          aberto_inicial: { type: 'boolean', title: 'Aberto ao abrir a página', default: true },
        },
      },
    },
    /* cobre os dois modos da Esri ao mesmo tempo (Window: pop-up modal centralizado; ancorada perto do que a
       abriu) porque a distinção deles é de POSICIONAMENTO, não de comportamento — ver PARIDADE.md. */
    janela: {
      rotulo: 'Janela',
      aceita_filhos: true,
      largura_padrao: 6,
      propriedades_padrao: { modo: 'modal', rotulo_botao: 'Abrir' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['modo', 'rotulo_botao'],
        properties: {
          modo: { type: 'string', title: 'Modo', enum: ['modal', 'ancorada'], default: 'modal' },
          rotulo_botao: { type: 'string', title: 'Rótulo do botão', minLength: 1, maxLength: 40, default: 'Abrir' },
        },
      },
    },

    // ---------------------------------------------------------------- seção com vistas (abas)
    secao_vistas: {
      rotulo: 'Seção com vistas',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: {},
      esquema: { type: 'object', additionalProperties: false, required: [], properties: {} },
    },
    vista: {
      rotulo: 'Vista',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { rotulo: 'Vista' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['rotulo'],
        properties: { rotulo: { type: 'string', title: 'Rótulo da aba', minLength: 1, maxLength: 40 } },
      },
    },

    // ---------------------------------------------------------------- conteúdo (item L5-08, reusado)
    grupo: {
      rotulo: 'Contêiner', aceita_filhos: true, largura_padrao: 12,
      propriedades_padrao: { rotulo: 'Contêiner', direcao: 'coluna' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['rotulo'],
        properties: {
          rotulo: { type: 'string', title: 'Rótulo', minLength: 1, maxLength: 60 },
          direcao: { type: 'string', title: 'Direção', enum: ['coluna', 'linha'], default: 'coluna' },
        },
      },
    },
    texto: {
      rotulo: 'Texto', aceita_filhos: false, largura_padrao: 6,
      propriedades_padrao: { texto: 'Texto novo', nivel: 'corpo' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['texto'],
        properties: {
          texto: { type: 'string', title: 'Texto', minLength: 1, maxLength: 10000 },
          nivel: { type: 'string', title: 'Nível', enum: ['corpo', 'titulo', 'legenda'], default: 'corpo' },
          formato: { type: 'string', title: 'Formato', enum: ['texto', 'markdown'], default: 'texto' },
        },
      },
    },
    imagem: {
      rotulo: 'Imagem', aceita_filhos: false, largura_padrao: 4,
      propriedades_padrao: { url: '/static/favicon.svg', alternativo: 'Imagem' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['url', 'alternativo'],
        properties: {
          url: { type: 'string', title: 'Endereço', pattern: '^/[A-Za-z0-9._~!$&()*+,;=:@%/-]*$', maxLength: 400 },
          alternativo: { type: 'string', title: 'Texto alternativo', minLength: 1, maxLength: 120 },
        },
      },
    },
    mapa: {
      rotulo: 'Mapa', aceita_filhos: false, largura_padrao: 8,
      propriedades_padrao: { zoom: 10, mostrar_escala: true },
      esquema: {
        type: 'object', additionalProperties: false, required: ['zoom'],
        properties: {
          zoom: { type: 'integer', title: 'Zoom inicial', minimum: 0, maximum: 22 },
          mostrar_escala: { type: 'boolean', title: 'Mostrar escala', default: true },
        },
      },
    },
    tabela: {
      rotulo: 'Tabela', aceita_filhos: false, largura_padrao: 6,
      propriedades_padrao: { linhas_por_pagina: 25 },
      esquema: {
        type: 'object', additionalProperties: false, required: ['linhas_por_pagina'],
        properties: { linhas_por_pagina: { type: 'integer', title: 'Linhas por página', minimum: 1, maximum: 500 } },
      },
    },

    // ---------------------------------------------------------------- widgets de página e de menu (item L5-01-d):
    // desenhados pelo motor de widgets (web/js/widgets/<tipo>.js); `menu_widget` é o menu configurável (itens com
    // página ou link), diferente de `menu`, que é a navegação automática entre páginas do documento.
    botao: {
      rotulo: 'Botão', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: { rotulo: 'Abrir', acao: { tipo: 'pagina', pagina: 'pagina' } },
      esquema: {
        type: 'object', additionalProperties: false, required: ['rotulo', 'acao'],
        properties: {
          rotulo: { type: 'string', title: 'Rótulo', minLength: 1, maxLength: 200 },
          acao: {
            type: 'object', additionalProperties: false, required: ['tipo'],
            properties: {
              tipo: { type: 'string', title: 'Ação', enum: ['pagina', 'link', 'evento'], default: 'pagina' },
              pagina: { type: 'string', title: 'Página (caminho)', maxLength: 200 },
              url: { type: 'string', title: 'Endereço do link', maxLength: 2048 },
              nova_aba: { type: 'boolean', title: 'Abrir em nova aba', default: false },
            },
          },
        },
      },
    },
    cartao: {
      rotulo: 'Cartão', aceita_filhos: false, largura_padrao: 4,
      propriedades_padrao: { titulo: 'Cartão', texto: 'Texto do cartão' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['titulo'],
        properties: {
          titulo: { type: 'string', title: 'Título', minLength: 1, maxLength: 200 },
          texto: { type: 'string', title: 'Texto (markdown; {campo} da feição)', maxLength: 10000 },
          imagem: { type: 'string', title: 'Imagem (endereço)', maxLength: 2048 },
          imagem_alternativo: { type: 'string', title: 'Texto alternativo da imagem', maxLength: 200 },
          link: { type: 'string', title: 'Link', maxLength: 2048 },
          pagina: { type: 'string', title: 'Página (caminho)', maxLength: 200 },
          link_rotulo: { type: 'string', title: 'Rótulo do link', maxLength: 200 },
        },
      },
    },
    incorporar: {
      rotulo: 'Incorporar', aceita_filhos: false, largura_padrao: 6,
      propriedades_padrao: { url: '', titulo: 'conteúdo incorporado', altura: 320, dominios_permitidos: [] },
      esquema: {
        type: 'object', additionalProperties: false, required: ['titulo'],
        properties: {
          url: { type: 'string', title: 'Endereço (https, domínio da lista)', maxLength: 2048 },
          html: { type: 'string', title: 'HTML (sanitizado, sem script)', maxLength: 20000 },
          titulo: { type: 'string', title: 'Título acessível', minLength: 1, maxLength: 200 },
          altura: { type: 'integer', title: 'Altura (px)', minimum: 40, maximum: 4000, default: 320 },
          dominios_permitidos: { type: 'array', title: 'Domínios permitidos', maxItems: 20, items: { type: 'string', maxLength: 200 } },
        },
      },
    },
    divisor: {
      rotulo: 'Divisor', aceita_filhos: false, largura_padrao: 12,
      propriedades_padrao: { estilo: 'linha' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['estilo'],
        properties: {
          estilo: { type: 'string', title: 'Estilo', enum: ['linha', 'tracejado', 'espaco'], default: 'linha' },
          vertical: { type: 'boolean', title: 'Vertical', default: false },
        },
      },
    },
    menu_widget: {
      rotulo: 'Menu (itens)', aceita_filhos: false, largura_padrao: 12,
      propriedades_padrao: { orientacao: 'horizontal', itens: [] },
      esquema: {
        type: 'object', additionalProperties: false, required: ['itens'],
        properties: {
          rotulo: { type: 'string', title: 'Rótulo acessível', maxLength: 200 },
          orientacao: { type: 'string', title: 'Orientação', enum: ['horizontal', 'vertical'], default: 'horizontal' },
          itens: {
            type: 'array', title: 'Itens', maxItems: 50,
            items: {
              type: 'object', additionalProperties: false, required: ['rotulo'],
              properties: {
                rotulo: { type: 'string', maxLength: 200 }, pagina: { type: 'string', maxLength: 200 },
                url: { type: 'string', maxLength: 2048 },
              },
            },
          },
        },
      },
    },
    controlador: {
      rotulo: 'Controlador de widgets', aceita_filhos: false, largura_padrao: 12,
      propriedades_padrao: { alvos: [] },
      esquema: {
        type: 'object', additionalProperties: false, required: ['alvos'],
        properties: {
          alvos: {
            type: 'array', title: 'Widgets controlados (id do nó)', maxItems: 50,
            items: { type: 'object', additionalProperties: false, required: ['id'],
                     properties: { id: { type: 'string', maxLength: 200 }, rotulo: { type: 'string', maxLength: 200 } } },
          },
        },
      },
    },
    compartilhar: {
      rotulo: 'Compartilhar', aceita_filhos: false, largura_padrao: 4,
      propriedades_padrao: { qr: true, incorporar: true },
      esquema: {
        type: 'object', additionalProperties: false,
        properties: {
          url: { type: 'string', title: 'Endereço (vazio = página atual)', maxLength: 2048 },
          qr: { type: 'boolean', title: 'Mostrar QR', default: true },
          incorporar: { type: 'boolean', title: 'Mostrar código de incorporação', default: true },
        },
      },
    },
    login: {
      rotulo: 'Login', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: {},
      esquema: { type: 'object', additionalProperties: false, properties: { rotulo: { type: 'string', title: 'Rótulo', maxLength: 200 } } },
    },
    idioma: {
      rotulo: 'Seletor de idioma', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: { idiomas: ['pt-BR'] },
      esquema: {
        type: 'object', additionalProperties: false, required: ['idiomas'],
        properties: {
          rotulo: { type: 'string', title: 'Rótulo', maxLength: 200 },
          idiomas: { type: 'array', title: 'Idiomas', maxItems: 10, items: { type: 'string', maxLength: 10 } },
        },
      },
    },
    tema: {
      rotulo: 'Seletor de tema', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: {},
      esquema: { type: 'object', additionalProperties: false, properties: { rotulo: { type: 'string', title: 'Rótulo', maxLength: 200 } } },
    },
  },
};
