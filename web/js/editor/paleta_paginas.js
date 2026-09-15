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
          texto: { type: 'string', title: 'Texto', minLength: 1, maxLength: 280 },
          nivel: { type: 'string', title: 'Nível', enum: ['corpo', 'titulo', 'legenda'], default: 'corpo' },
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

    // ---------------------------------------------------------------- widgets de página (item
    // L5-01-d-widgets-pagina-menu): as propriedades usam o MESMO vocabulário do `esquema_config` do manifesto
    // em `widgets/registro.js` (mesmos nomes de campo), para o dia em que o executor montar estes tipos pelo
    // motor (`widgets/motor.js`) sem tradução nenhuma — hoje o executor ainda desenha estes nós pela caixa
    // genérica `exec-desconhecido` (ver `TIPOS_WIDGET_PAGINA` em `executor/executor.js`); só o CONSTRUTOR
    // (arrasto + edição de propriedades) está completo para eles nesta entrega.
    botao: {
      rotulo: 'Botão', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: { rotulo: 'Botão', habilitado: true, acao: { tipo: 'evento' } },
      esquema: {
        type: 'object', additionalProperties: false, required: ['rotulo'],
        properties: {
          rotulo: { type: 'string', title: 'Rótulo', minLength: 1, maxLength: 200 },
          habilitado: { type: 'boolean', title: 'Habilitado', default: true },
          valor: {},
          acao: {
            type: 'object', additionalProperties: false, required: ['tipo'],
            properties: {
              tipo: { type: 'string', title: 'Tipo de ação', enum: ['evento', 'link', 'pagina'], default: 'evento' },
              url: { type: 'string', title: 'Endereço do link', maxLength: 2000 },
              nova_aba: { type: 'boolean', title: 'Abrir em nova aba', default: false },
              pagina: { type: 'string', title: 'Caminho da página', maxLength: 80 },
            },
          },
        },
      },
    },
    cartao: {
      rotulo: 'Cartão', aceita_filhos: false, largura_padrao: 4,
      propriedades_padrao: { titulo: 'Novo cartão', texto: '' },
      esquema: {
        type: 'object', additionalProperties: false, required: ['titulo'],
        properties: {
          titulo: { type: 'string', title: 'Título', minLength: 1, maxLength: 200 },
          texto: { type: 'string', title: 'Texto (Markdown)', maxLength: 5000, default: '' },
          imagem: { type: 'string', title: 'Endereço da imagem', maxLength: 2000 },
          imagem_alternativo: { type: 'string', title: 'Texto alternativo da imagem', maxLength: 200 },
          link: { type: 'string', title: 'Endereço do link', maxLength: 2000 },
          link_rotulo: { type: 'string', title: 'Rótulo do link/botão', maxLength: 200 },
          pagina: { type: 'string', title: 'Caminho da página', maxLength: 80 },
        },
      },
    },
    incorporar: {
      rotulo: 'Incorporar', aceita_filhos: false, largura_padrao: 6,
      propriedades_padrao: { titulo: 'Conteúdo incorporado', altura: 320, dominios_permitidos: [], sandbox: ['allow-scripts'] },
      esquema: {
        type: 'object', additionalProperties: false, required: [],
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 200 },
          url: { type: 'string', title: 'Endereço (https, só domínio permitido)', maxLength: 2000 },
          html: { type: 'string', title: 'HTML (sanitizado)', maxLength: 20000 },
          altura: { type: 'integer', title: 'Altura (px)', minimum: 60, maximum: 2000, default: 320 },
          dominios_permitidos: { type: 'array', title: 'Domínios permitidos', maxItems: 20, items: { type: 'string', maxLength: 200 } },
          // enum estrito de propósito (diferente do esquema_config do motor, mais permissivo): aqui é um
          // SELETOR na tela de propriedades, então `allow-same-origin` nem aparece como opção; lá é a
          // validação de um documento já gravado, que não pode travar por um token velho/desconhecido —
          // quem filtra de verdade na hora de montar é `seguro.js::sandboxDe`.
          sandbox: {
            type: 'array', title: 'Sandbox', maxItems: 4,
            items: { type: 'string', enum: ['allow-scripts', 'allow-forms', 'allow-popups', 'allow-presentation'] },
          },
        },
      },
    },
    divisor: {
      rotulo: 'Divisor', aceita_filhos: false, largura_padrao: 12,
      propriedades_padrao: { estilo: 'linha', vertical: false },
      esquema: {
        type: 'object', additionalProperties: false, required: ['estilo'],
        properties: {
          estilo: { type: 'string', title: 'Estilo', enum: ['linha', 'tracejado', 'pontilhado'], default: 'linha' },
          vertical: { type: 'boolean', title: 'Vertical', default: false },
        },
      },
    },
    // chave `menu_widget` (não `menu`): o tipo `menu` já existe acima como NAVEGAÇÃO ENTRE PÁGINAS do
    // documento inteiro (gerado da lista de páginas, sem `itens` configurável); este é o widget genérico de
    // menu do motor (`widgets/menu.js`, manifesto `menu` em `widgets/registro.js`), com itens escolhidos à
    // mão (página OU link) — mesma raiz que colidiu para `texto`/`imagem`/`mapa`/`tabela` acima, resolvida
    // aqui com um nome de tipo diferente em vez de reescrever a navegação existente.
    menu_widget: {
      rotulo: 'Menu (widget)', aceita_filhos: false, largura_padrao: 12,
      propriedades_padrao: { orientacao: 'horizontal', itens: [] },
      esquema: {
        type: 'object', additionalProperties: false, required: ['orientacao'],
        properties: {
          orientacao: { type: 'string', title: 'Orientação', enum: ['horizontal', 'vertical'], default: 'horizontal' },
          rotulo: { type: 'string', title: 'Rótulo (acessibilidade)', maxLength: 200 },
          itens: {
            type: 'array', title: 'Itens', maxItems: 30,
            items: {
              type: 'object', additionalProperties: false,
              properties: {
                rotulo: { type: 'string', maxLength: 200 }, pagina: { type: 'string', maxLength: 80 },
                url: { type: 'string', maxLength: 2000 }, valor: {},
              },
            },
          },
        },
      },
    },
    controlador: {
      rotulo: 'Controlador', aceita_filhos: false, largura_padrao: 6,
      propriedades_padrao: { alvos: [] },
      esquema: {
        type: 'object', additionalProperties: false, required: [],
        properties: {
          alvos: {
            type: 'array', title: 'Alvos (id do nó na mesma página)', maxItems: 50,
            items: { type: 'object', additionalProperties: false, required: ['id'], properties: { id: { type: 'string', maxLength: 26 }, rotulo: { type: 'string', maxLength: 200 } } },
          },
        },
      },
    },
    compartilhar: {
      rotulo: 'Compartilhar', aceita_filhos: false, largura_padrao: 6,
      propriedades_padrao: { qr: true, incorporar: true },
      esquema: {
        type: 'object', additionalProperties: false, required: [],
        properties: {
          url: { type: 'string', title: 'Endereço (padrão: a própria página)', maxLength: 2000 },
          qr: { type: 'boolean', title: 'Mostrar QR', default: true },
          incorporar: { type: 'boolean', title: 'Mostrar trecho de incorporação', default: true },
        },
      },
    },
    login: {
      rotulo: 'Login', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: {},
      esquema: { type: 'object', additionalProperties: false, required: [], properties: {} },
    },
    idioma: {
      rotulo: 'Idioma', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: { idiomas: ['pt-BR'] },
      esquema: {
        type: 'object', additionalProperties: false, required: [],
        properties: {
          idiomas: { type: 'array', title: 'Idiomas oferecidos', maxItems: 5, items: { type: 'string', enum: ['pt-BR', 'en', 'es'] } },
          rotulo: { type: 'string', title: 'Rótulo', maxLength: 200 },
        },
      },
    },
    tema: {
      rotulo: 'Tema', aceita_filhos: false, largura_padrao: 3,
      propriedades_padrao: {},
      esquema: {
        type: 'object', additionalProperties: false, required: [],
        properties: { rotulo: { type: 'string', title: 'Rótulo', maxLength: 200 } },
      },
    },
  },
};
