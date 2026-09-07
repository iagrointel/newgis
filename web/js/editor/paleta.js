/* plat — paleta: catálogo de tipos de nó que o editor sabe pôr na tela (item L5-08-editor-arrasto).

   O editor NÃO conhece nenhum tipo: recebe uma paleta e trabalha com ela. Esta é a paleta de LAYOUT, comum aos
   construtores de app, painel, narrativa, relatório e site — os tipos que existem em todos eles (contêiner,
   texto, imagem, espaço) mais os dois lugares onde os widgets de dado do L5-06/L5-07 vão se encaixar
   (`mapa`, `tabela`), aqui com as propriedades de LAYOUT que o editor grava. Quando o L5-06 publicar o
   manifesto de widget, `criarEditor({paleta})` recebe a paleta montada do manifesto e nada neste editor muda:
   é por isso que o tipo mora em dado (esquema + rótulo + aceita_filhos), nunca em `if (tipo === ...)`.

   `rotulo` é o texto pt-BR usado como valor-padrão do campo "rótulo" do próprio widget (o servidor grava esse
   valor no documento) e como reserva para paletas sem dicionário (o manifesto do L5-06 pode não ter uma).
   `rotulo_chave` é a chave de tradução que `web/js/editor/editor.js::rotuloDoTipo()` prefere quando existe —
   é o que muda com a troca de idioma do construtor (item L5-12-acessibilidade-i18n-construtores); sem ela o
   editor cai em `rotulo` puro, sem quebrar. */

export const PALETA_LAYOUT = {
  nome: 'layout',
  ordem: ['grupo', 'texto', 'imagem', 'mapa', 'tabela'],
  tipos: {
    grupo: {
      rotulo: 'Contêiner',
      rotulo_chave: 'construtor.tipo_grupo',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { rotulo: 'Contêiner', direcao: 'coluna' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['rotulo'],
        properties: {
          rotulo: { type: 'string', title: 'Rótulo', minLength: 1, maxLength: 60 },
          direcao: { type: 'string', title: 'Direção', enum: ['coluna', 'linha'], default: 'coluna' },
        },
      },
    },
    texto: {
      rotulo: 'Texto',
      rotulo_chave: 'construtor.tipo_texto',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { texto: 'Texto novo', nivel: 'corpo' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['texto'],
        properties: {
          texto: { type: 'string', title: 'Texto', minLength: 1, maxLength: 280 },
          nivel: { type: 'string', title: 'Nível', enum: ['corpo', 'titulo', 'legenda'], default: 'corpo' },
        },
      },
    },
    imagem: {
      rotulo: 'Imagem',
      rotulo_chave: 'construtor.tipo_imagem',
      aceita_filhos: false,
      largura_padrao: 4,
      propriedades_padrao: { url: '/static/favicon.svg', alternativo: 'Imagem' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['url', 'alternativo'],
        properties: {
          /* só caminho do próprio servidor: URL de fora vira requisição a terceiro dentro de uma página do
             inquilino (mesma regra do L0-11, arquivo por /api/objetos) */
          url: { type: 'string', title: 'Endereço', pattern: '^/[A-Za-z0-9._~!$&()*+,;=:@%/-]*$', maxLength: 400 },
          alternativo: { type: 'string', title: 'Texto alternativo', minLength: 1, maxLength: 120 },
        },
      },
    },
    mapa: {
      rotulo: 'Mapa',
      rotulo_chave: 'construtor.tipo_mapa',
      aceita_filhos: false,
      largura_padrao: 8,
      propriedades_padrao: { zoom: 10, mostrar_escala: true },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['zoom'],
        properties: {
          zoom: { type: 'integer', title: 'Zoom inicial', minimum: 0, maximum: 22 },
          mostrar_escala: { type: 'boolean', title: 'Mostrar escala', default: true },
        },
      },
    },
    tabela: {
      rotulo: 'Tabela',
      rotulo_chave: 'construtor.tipo_tabela',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { linhas_por_pagina: 25 },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['linhas_por_pagina'],
        properties: {
          linhas_por_pagina: { type: 'integer', title: 'Linhas por página', minimum: 1, maximum: 500 },
        },
      },
    },
  },
};
