/* plat — paleta do CONSTRUTOR DE SITE (item L5-20-sites-paginas-publicas).

   Mesma forma das outras paletas da linha (`paleta.js`, `paleta_paginas.js`): o editor de arrasto do L5-08 não
   sabe o nome de nenhum tipo — lê `aceita_filhos`, `largura_padrao`, `propriedades_padrao` e `esquema`. Quem dá
   SIGNIFICADO a estes tipos é o renderizador do servidor (`app/catalogo/site_render.py`), porque a página de
   site sai pronta do servidor (L5_CONCEITO D24); o navegador só a monta enquanto o autor arrasta.

   Estrutura do documento: `pagina` na raiz, `secao` dentro de página, cartão dentro de seção; `cabecalho`,
   `menu` e `rodape` pertencem ao site inteiro e também ficam na raiz. A mesma regra é conferida no servidor
   (`app/catalogo/site.py::validar_documento`, 422 `site_invalido`) — a paleta orienta, o servidor decide.

   Os nove cartões são os da hipótese do item: texto, imagem, galeria de itens do catálogo com filtro, mapa
   incorporado, app/painel, busca de conteúdo, chamada com botão, estatísticas e conteúdo incorporado. */

const UUID = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$';

export const PALETA_SITE = {
  nome: 'site',
  ordem: [
    'pagina', 'secao',
    'texto', 'imagem', 'galeria', 'mapa', 'aplicativo', 'busca', 'chamada', 'estatisticas', 'incorporado',
    'cabecalho', 'menu', 'rodape',
  ],
  tipos: {
    pagina: {
      rotulo: 'Página',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { titulo: 'Nova página', caminho: 'pagina', ordem: 0, oculta: false, inicial: false },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['titulo', 'caminho'],
        properties: {
          titulo: { type: 'string', title: 'Título', minLength: 1, maxLength: 80 },
          caminho: { type: 'string', title: 'Caminho (URL)', pattern: '^[a-z0-9]([a-z0-9-]{0,58}[a-z0-9])?$' },
          ordem: { type: 'integer', title: 'Ordem no menu', minimum: 0, maximum: 999, default: 0 },
          oculta: { type: 'boolean', title: 'Fora do menu', default: false },
          inicial: { type: 'boolean', title: 'Página inicial', default: false },
        },
      },
    },
    secao: {
      rotulo: 'Seção',
      aceita_filhos: true,
      largura_padrao: 12,
      propriedades_padrao: { rotulo: 'Nova seção', fundo: 'claro' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['rotulo'],
        properties: {
          rotulo: { type: 'string', title: 'Título da seção', minLength: 1, maxLength: 80 },
          fundo: { type: 'string', title: 'Fundo', enum: ['claro', 'escuro'], default: 'claro' },
        },
      },
    },
    cabecalho: {
      rotulo: 'Cabeçalho do site',
      aceita_filhos: false,
      largura_padrao: 12,
      propriedades_padrao: { titulo: '', subtitulo: '', mostrar_logo: true },
      esquema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          titulo: { type: 'string', title: 'Título (vazio = nome da organização)', maxLength: 80 },
          subtitulo: { type: 'string', title: 'Subtítulo', maxLength: 160 },
          mostrar_logo: { type: 'boolean', title: 'Mostrar logotipo', default: true },
        },
      },
    },
    menu: {
      rotulo: 'Menu',
      aceita_filhos: false,
      largura_padrao: 12,
      propriedades_padrao: { rotulo: 'menu do site' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['rotulo'],
        properties: { rotulo: { type: 'string', title: 'Rótulo acessível', minLength: 1, maxLength: 60 } },
      },
    },
    rodape: {
      rotulo: 'Rodapé',
      aceita_filhos: false,
      largura_padrao: 12,
      propriedades_padrao: { texto: '' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        properties: { texto: { type: 'string', title: 'Texto do rodapé', maxLength: 4000 } },
      },
    },
    texto: {
      rotulo: 'Texto',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { titulo: '', texto: 'Escreva aqui.' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['texto'],
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 80 },
          /* linha em branco separa parágrafo; o servidor escapa todo o resto (sem HTML do autor) */
          texto: { type: 'string', title: 'Texto', minLength: 1, maxLength: 4000 },
        },
      },
    },
    imagem: {
      rotulo: 'Imagem',
      aceita_filhos: false,
      largura_padrao: 4,
      propriedades_padrao: { url: '/static/favicon.svg', alternativo: 'Imagem', legenda: '' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['url', 'alternativo'],
        properties: {
          url: { type: 'string', title: 'Endereço (do próprio servidor)', pattern: '^/[A-Za-z0-9._~!$&()*+,;=:@%/?#-]*$', maxLength: 400 },
          alternativo: { type: 'string', title: 'Texto alternativo', minLength: 1, maxLength: 120 },
          legenda: { type: 'string', title: 'Legenda', maxLength: 160 },
        },
      },
    },
    galeria: {
      rotulo: 'Galeria do catálogo',
      aceita_filhos: false,
      largura_padrao: 12,
      propriedades_padrao: { titulo: 'Conteúdo publicado', limite: 12, mostrar_filtro: true },
      esquema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 80 },
          /* vazio = todos os tipos; a lista SÓ restringe — o que entra é o que está compartilhado com todos */
          tipos: { type: 'array', title: 'Tipos de item', maxItems: 20, items: { type: 'string', maxLength: 40 } },
          limite: { type: 'integer', title: 'Quantos itens', minimum: 1, maximum: 60, default: 12 },
          mostrar_filtro: { type: 'boolean', title: 'Mostrar filtro', default: true },
        },
      },
    },
    mapa: {
      rotulo: 'Mapa incorporado',
      aceita_filhos: false,
      largura_padrao: 8,
      propriedades_padrao: { titulo: '', item_id: '', altura: 420 },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['item_id'],
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 80 },
          item_id: { type: 'string', title: 'Item do catálogo (uuid)', pattern: UUID },
          altura: { type: 'integer', title: 'Altura (px)', minimum: 120, maximum: 1200, default: 420 },
        },
      },
    },
    aplicativo: {
      rotulo: 'Aplicativo ou painel',
      aceita_filhos: false,
      largura_padrao: 4,
      propriedades_padrao: { titulo: '', item_id: '' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['item_id'],
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 80 },
          item_id: { type: 'string', title: 'Item do catálogo (uuid)', pattern: UUID },
        },
      },
    },
    busca: {
      rotulo: 'Busca de conteúdo',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { titulo: 'Buscar', rotulo_campo: 'buscar no conteúdo publicado' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 80 },
          rotulo_campo: { type: 'string', title: 'Rótulo do campo', minLength: 1, maxLength: 80 },
        },
      },
    },
    chamada: {
      rotulo: 'Chamada com botão',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { titulo: 'Fale com a equipe', texto: '', rotulo_botao: 'Saber mais', destino: '/' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['rotulo_botao', 'destino'],
        properties: {
          titulo: { type: 'string', title: 'Título', maxLength: 80 },
          texto: { type: 'string', title: 'Texto', maxLength: 4000 },
          rotulo_botao: { type: 'string', title: 'Rótulo do botão', minLength: 1, maxLength: 60 },
          destino: { type: 'string', title: 'Destino (caminho interno ou https)', minLength: 1, maxLength: 400 },
        },
      },
    },
    estatisticas: {
      rotulo: 'Estatísticas',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { titulo: 'Nossos números' },
      esquema: {
        type: 'object',
        additionalProperties: false,
        properties: { titulo: { type: 'string', title: 'Título', maxLength: 80 } },
      },
    },
    incorporado: {
      rotulo: 'Conteúdo incorporado',
      aceita_filhos: false,
      largura_padrao: 6,
      propriedades_padrao: { titulo: 'Conteúdo incorporado', url: 'https://www.openstreetmap.org/export/embed.html', altura: 420 },
      esquema: {
        type: 'object',
        additionalProperties: false,
        required: ['url'],
        properties: {
          titulo: { type: 'string', title: 'Título (vai no quadro, exigido por acessibilidade)', maxLength: 80 },
          url: { type: 'string', title: 'Endereço https', pattern: '^https://', maxLength: 400 },
          altura: { type: 'integer', title: 'Altura (px)', minimum: 120, maximum: 1200, default: 420 },
        },
      },
    },
  },
};
