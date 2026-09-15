/* plat — registro de widgets (item L5-06-motor-widgets; ampliado pelo L5-07-fontes-vistas-mensagens, pelo
   L5-01-c-widgets-dado: tabela 2, gráfico 2, filtro 2, lista, consulta, seleção, info-feicao, adicionar-dado;
   e pelo L5-01-d-widgets-pagina-menu: imagem, cartão, incorporar, divisor, menu (widget), controlador,
   compartilhar, login, idioma, tema — mais texto/botão, que já existiam aqui e ganharam os campos que
   faltavam (`formato`/`acao`) e o elemento correto (`plat-w-<nome>`, o que `web/js/widgets/base.js::definir`
   registra de verdade; ver PARIDADE.md). Varredura de 15/09 (item F2-widgets-3): o mesmo bug do `texto`/
   `botao` (elemento inventado, nunca definido) estava em MAIS TRÊS manifestos mais antigos —
   `mapa` ('plat-mapa'), `legenda` ('plat-legenda') e `filtro` ('plat-filtro') — todos com módulo próprio
   que na verdade registra `plat-w-<nome>`; corrigidos aqui e cobertos por
   `test_widgets_registro_elementos.py`, que reprova QUALQUER divergência futura entre `elemento` e o
   `definir(...)` real do módulo, não só os nomes de um item específico.
   Cada manifesto declara os EVENTOS que emite e as AÇÕES que aceita no vocabulário do barramento
   (L5_CONCEITO D5): eventos clique | dado_adicionado | filtro_mudou | extensao_mudou | localizacao |
   registros_carregados | selecao_mudou | vista_mudou; ações de dado filtrar | selecionar | limpar_filtro |
   limpar_selecao (resolvidas na VISTA do widget) e de widget zoom | pan | piscar | popup | abrir | fechar |
   definir_parametro (chamadas no elemento). `configuracao.vista` liga o widget a uma vista do documento.
   ⚠ os widgets de página (`texto`/`imagem`/`botão`/`cartão`/... de `../widgets/*.js`, base `PlatWidget` de
   `base.js`) são catálogo independente dos tipos HOMÔNIMOS de `editor/paleta_paginas.js` (que o EXECUTOR
   desenha direto, sem passar pelo motor — ver o comentário de `TIPOS_WIDGET_PAGINA` em
   `executor/executor.js`): `texto`/`imagem` ficam aqui por completude do registro (outros construtores os
   usam), mas a paleta de páginas continua com o esquema PRÓPRIO dela para esses dois nomes. */
const textoCurto = { type: 'string', maxLength: 200 };
const ulid = { type: 'string', maxLength: 26 };
const objetoFechado = (properties = {}, required = []) => ({ type: 'object', additionalProperties: false, properties, required });

export const EVENTOS_BARRAMENTO = Object.freeze(['clique', 'dado_adicionado', 'filtro_mudou', 'extensao_mudou', 'localizacao', 'registros_carregados', 'selecao_mudou', 'vista_mudou']);
export const ACOES_DADO = Object.freeze(['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao']);
export const ACOES_WIDGET = Object.freeze(['zoom', 'pan', 'piscar', 'popup', 'abrir', 'fechar', 'definir_parametro']);

const manifestos = [
  {
    nome: 'mapa', versao: '1.1.0', api_widget: 1, modulo: './mapa.js', elemento: 'plat-w-mapa',
    esquema_config: objetoFechado({ rotulo: textoCurto, vista: ulid, campo_rotulo: textoCurto, altura: { type: 'integer', minimum: 120, maximum: 2000 } }),
    eventos: ['clique', 'selecao_mudou', 'extensao_mudou', 'registros_carregados', 'mapa.selecao', 'mapa.extensao_alterada'],
    acoes: [...ACOES_DADO, 'zoom', 'pan', 'piscar', 'popup', 'mapa.enquadrar', 'mapa.destacar'],
    fontes: { min: 0, max: 100, tipos: ['mapa', 'camada'] }, i18n: 'widget.mapa',
  },
  {
    nome: 'legenda', versao: '1.0.0', api_widget: 1, modulo: './legenda.js', elemento: 'plat-w-legenda',
    esquema_config: objetoFechado({
      titulo: textoCurto,
      itens: { type: 'array', maxItems: 500, items: objetoFechado({ rotulo: textoCurto, cor: textoCurto, valor: {} }, ['rotulo']) },
    }),
    eventos: ['legenda.item_acionado'], acoes: ['legenda.definir'],
    fontes: { min: 0, max: 1, tipos: ['mapa'] }, i18n: 'widget.legenda',
  },
  {
    nome: 'tabela', versao: '2.0.0', api_widget: 1, modulo: './tabela.js', elemento: 'plat-tabela',
    esquema_config: objetoFechado({
      vista: ulid,
      colunas: { type: 'array', maxItems: 100, items: objetoFechado({ campo: textoCurto, rotulo: textoCurto }, ['campo', 'rotulo']) },
      linhas: { type: 'array', maxItems: 10000, items: { type: 'object' } },
      linhas_por_pagina: { type: 'integer', minimum: 5, maximum: 1000 },
      exportar: { type: 'boolean' },
    }),
    eventos: ['clique', 'selecao_mudou', 'registros_carregados', 'tabela.linha_selecionada', 'tabela.exportada'],
    acoes: [...ACOES_DADO, 'piscar', 'tabela.definir', 'tabela.filtrar', 'tabela.ordenar', 'tabela.pagina'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.tabela',
  },
  {
    nome: 'grafico', versao: '2.0.0', api_widget: 1, modulo: './grafico.js', elemento: 'plat-grafico',
    esquema_config: objetoFechado({
      vista: ulid, titulo: textoCurto, tipo: { type: 'string', enum: ['barra', 'linha', 'pizza', 'dispersao', 'histograma'] },
      campo: textoCurto, agregacao: { type: 'string', enum: ['contagem', 'soma', 'media', 'minimo', 'maximo'] },
      campo_valor: textoCurto, campo_y: textoCurto, maximo_barras: { type: 'integer', minimum: 1, maximum: 200 },
      faixas: { type: 'integer', minimum: 2, maximum: 100 }, amostra: { type: 'integer', minimum: 10, maximum: 5000 },
      altura: { type: 'integer', minimum: 80, maximum: 2000 },
    }, ['campo']),
    eventos: ['clique', 'selecao_mudou', 'filtro_mudou', 'registros_carregados', 'grafico.desenhado'],
    acoes: [...ACOES_DADO, 'piscar', 'grafico.definir'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.grafico',
  },
  {
    nome: 'lista', versao: '1.0.0', api_widget: 1, modulo: './lista.js', elemento: 'plat-lista',
    esquema_config: objetoFechado({ vista: ulid, modelo: { type: 'string', maxLength: 2000 }, linhas_por_pagina: { type: 'integer', minimum: 1, maximum: 500 } }),
    eventos: ['clique', 'selecao_mudou', 'lista.item_selecionado'], acoes: [...ACOES_DADO, 'piscar', 'lista.pagina'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.lista',
  },
  {
    nome: 'consulta', versao: '1.0.0', api_widget: 1, modulo: './consulta_dado.js', elemento: 'plat-consulta',
    esquema_config: objetoFechado({ vista: ulid, rotulo: textoCurto, campos: { type: 'array', maxItems: 100, items: textoCurto }, espacial: { type: 'boolean' } }),
    eventos: ['filtro_mudou', 'consulta.executada'], acoes: ['limpar_filtro', 'consulta.executar', 'definir_parametro'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.consulta',
  },
  {
    nome: 'selecao', versao: '1.0.0', api_widget: 1, modulo: './selecao.js', elemento: 'plat-selecao',
    esquema_config: objetoFechado({ vista: ulid, campo: textoCurto }),
    eventos: ['selecao_mudou', 'selecao.alterada'], acoes: ['selecionar', 'limpar_selecao', 'selecao.por_atributo', 'selecao.tudo', 'selecao.inverter'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.selecao',
  },
  {
    nome: 'info-feicao', versao: '1.0.0', api_widget: 1, modulo: './info_feicao.js', elemento: 'plat-info-feicao',
    esquema_config: objetoFechado({ vista: ulid, modelo: { type: 'string', maxLength: 2000 }, campos: { type: 'array', maxItems: 100, items: textoCurto }, vazio: textoCurto }),
    eventos: ['info.mostrada'], acoes: ['piscar', 'info.mostrar', 'abrir', 'fechar'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.info-feicao',
  },
  {
    nome: 'adicionar-dado', versao: '1.0.0', api_widget: 1, modulo: './adicionar_dado.js', elemento: 'plat-adicionar-dado',
    esquema_config: objetoFechado({ vista: ulid, rotulo: textoCurto, aceitar_url: { type: 'boolean' } }),
    eventos: ['dado_adicionado', 'adicionar.carregado', 'adicionar.erro'], acoes: ['adicionar.carregar'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.adicionar-dado',
  },
  {
    // item L5-01-d: `formato: 'markdown'` (Markdown mínimo + DOMPurify, seguro.js/base.js::fragmentoSeguro) e
    // `texto.feicao` (liga a {campo} da feição selecionada) faltavam aqui; elemento real é `plat-w-texto`.
    nome: 'texto', versao: '1.1.0', api_widget: 1, modulo: './texto.js', elemento: 'plat-w-texto',
    esquema_config: objetoFechado({
      texto: { type: 'string', maxLength: 10000 }, nivel: { type: 'integer', minimum: 1, maximum: 6 },
      formato: { type: 'string', enum: ['markdown'] },
    }, ['texto']),
    eventos: [], acoes: ['texto.definir', 'texto.feicao', 'definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.texto',
  },
  {
    // item L5-01-d: imagem por endereço ou por {campo} da feição selecionada (imagem.js); elemento `plat-w-imagem`.
    nome: 'imagem', versao: '1.0.0', api_widget: 1, modulo: './imagem.js', elemento: 'plat-w-imagem',
    esquema_config: objetoFechado({
      url: { type: 'string', maxLength: 2000 }, campo: textoCurto, alternativo: textoCurto,
      legenda: { type: 'string', maxLength: 200 },
      ajuste: { type: 'string', enum: ['cobrir', 'conter', 'preencher', 'nenhum'] },
      altura: { type: 'integer', minimum: 20, maximum: 4000 },
    }),
    eventos: ['imagem.acionada'], acoes: ['imagem.definir', 'imagem.feicao', 'definir_parametro'],
    fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.imagem',
  },
  {
    // item L5-01-d: `acao` faltava aqui (botao.js lê `c.acao.tipo` evento|link|pagina) — sem isto todo botão de
    // link/página do documento era recusado por "campo desconhecido"; elemento real é `plat-w-botao`.
    nome: 'botao', versao: '1.1.0', api_widget: 1, modulo: './botao.js', elemento: 'plat-w-botao',
    esquema_config: objetoFechado({
      rotulo: textoCurto, valor: {}, habilitado: { type: 'boolean' },
      acao: objetoFechado({
        tipo: { type: 'string', enum: ['evento', 'link', 'pagina'] },
        url: { type: 'string', maxLength: 2000 }, nova_aba: { type: 'boolean' }, pagina: textoCurto,
      }),
    }, ['rotulo']),
    eventos: ['clique', 'botao.acionado', 'botao.pagina'], acoes: ['botao.habilitar', 'abrir', 'fechar', 'definir_parametro'],
    fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.botao',
  },
  {
    // item L5-01-d: cartão com imagem, título, corpo em Markdown ({campo} da feição) e link ou troca de página.
    nome: 'cartao', versao: '1.0.0', api_widget: 1, modulo: './cartao.js', elemento: 'plat-w-cartao',
    esquema_config: objetoFechado({
      titulo: { type: 'string', maxLength: 200 }, texto: { type: 'string', maxLength: 5000 },
      imagem: { type: 'string', maxLength: 2000 }, imagem_alternativo: textoCurto,
      link: { type: 'string', maxLength: 2000 }, link_rotulo: textoCurto, pagina: textoCurto,
    }),
    eventos: ['cartao.acionado', 'cartao.pagina'], acoes: ['cartao.feicao', 'definir_parametro'],
    fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.cartao',
  },
  {
    // item L5-01-d: incorporar por URL (só domínio da lista, sandbox nunca com allow-same-origin) ou HTML
    // sanitizado em `srcdoc` (sandbox vazio) — ver seguro.js::hostPermitido/sandboxDe.
    nome: 'incorporar', versao: '1.0.0', api_widget: 1, modulo: './incorporar.js', elemento: 'plat-w-incorporar',
    esquema_config: objetoFechado({
      titulo: textoCurto, altura: { type: 'integer', minimum: 60, maximum: 2000 },
      html: { type: 'string', maxLength: 20000 }, url: { type: 'string', maxLength: 2000 },
      dominios_permitidos: { type: 'array', maxItems: 20, items: textoCurto },
      // sem enum de propósito: `seguro.js::sandboxDe` já filtra para a lista permitida (nunca `allow-same-
      // origin`) na hora de montar o iframe — o esquema só barra estrutura errada, não repete a filtragem
      // de segurança, que é do widget (documento antigo com token descontinuado continua carregando).
      sandbox: { type: 'array', maxItems: 6, items: { type: 'string', maxLength: 40 } },
    }),
    eventos: [], acoes: ['incorporar.definir', 'definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.incorporar',
  },
  {
    // item L5-01-d: divisor (`<hr>`) — sem dado, sem ação além das genéricas do widget.
    nome: 'divisor', versao: '1.0.0', api_widget: 1, modulo: './divisor.js', elemento: 'plat-w-divisor',
    esquema_config: objetoFechado({
      estilo: { type: 'string', enum: ['linha', 'tracejado', 'pontilhado'] }, vertical: { type: 'boolean' },
    }),
    eventos: [], acoes: ['definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.divisor',
  },
  {
    // item L5-01-d: menu de widget (itens com página OU link) — nome próprio no registro (`menu`) por já ser
    // o do módulo/i18n; a paleta de páginas usa a chave `menu_widget` para nunca colidir com o tipo `menu` de
    // navegação entre páginas (root, esquema diferente, desenhado por `executor.js::desenharMenu`).
    nome: 'menu', versao: '1.0.0', api_widget: 1, modulo: './menu.js', elemento: 'plat-w-menu',
    esquema_config: objetoFechado({
      orientacao: { type: 'string', enum: ['horizontal', 'vertical'] }, rotulo: textoCurto,
      itens: {
        type: 'array', maxItems: 30,
        items: objetoFechado({ rotulo: textoCurto, pagina: textoCurto, url: { type: 'string', maxLength: 2000 }, valor: {} }),
      },
    }),
    eventos: ['menu.pagina', 'menu.acionado'], acoes: ['menu.definir', 'definir_parametro'],
    fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.menu',
  },
  {
    // item L5-01-d: controlador — um botão por nó-alvo da própria página (abre/fecha por `data-no-id`).
    nome: 'controlador', versao: '1.0.0', api_widget: 1, modulo: './controlador.js', elemento: 'plat-w-controlador',
    esquema_config: objetoFechado({
      alvos: { type: 'array', maxItems: 50, items: objetoFechado({ id: ulid, rotulo: textoCurto }, ['id']) },
    }),
    eventos: ['controlador.alternado'], acoes: ['controlador.abrir', 'controlador.fechar', 'definir_parametro'],
    fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.controlador',
  },
  {
    // item L5-01-d: compartilhar — link da página, QR (`GET /api/qr.svg`, sem serviço externo) e trecho de embed.
    nome: 'compartilhar', versao: '1.0.0', api_widget: 1, modulo: './compartilhar.js', elemento: 'plat-w-compartilhar',
    esquema_config: objetoFechado({ url: { type: 'string', maxLength: 2000 }, qr: { type: 'boolean' }, incorporar: { type: 'boolean' } }),
    eventos: [], acoes: ['definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.compartilhar',
  },
  {
    // item L5-01-d: login — quem está autenticado (`GET /api/eu`) com botão sair, ou link para `/entrar`.
    nome: 'login', versao: '1.0.0', api_widget: 1, modulo: './login.js', elemento: 'plat-w-login',
    esquema_config: objetoFechado({}),
    eventos: ['login.mudou'], acoes: ['login.atualizar', 'definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.login',
  },
  {
    // item L5-01-d: idioma — seletor entre os idiomas que o documento lista (web/js/i18n/*.json).
    nome: 'idioma', versao: '1.0.0', api_widget: 1, modulo: './idioma.js', elemento: 'plat-w-idioma',
    esquema_config: objetoFechado({
      idiomas: { type: 'array', maxItems: 5, items: { type: 'string', enum: ['pt-BR', 'en', 'es'] } }, rotulo: textoCurto,
    }),
    eventos: ['idioma.mudou'], acoes: ['idioma.definir', 'definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.idioma',
  },
  {
    // item L5-01-d: tema — sistema/claro/escuro, `data-theme` no `<html>` (tokens.css); lembra em localStorage.
    nome: 'tema', versao: '1.0.0', api_widget: 1, modulo: './tema.js', elemento: 'plat-w-tema',
    esquema_config: objetoFechado({ rotulo: textoCurto }),
    eventos: ['tema.mudou'], acoes: ['tema.definir', 'definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.tema',
  },
  {
    nome: 'filtro', versao: '2.0.0', api_widget: 1, modulo: './filtro.js', elemento: 'plat-w-filtro',
    esquema_config: objetoFechado({
      rotulo: textoCurto, valor: textoCurto, vista: ulid, campo: textoCurto,
      modo: { type: 'string', enum: ['texto', 'valores', 'intervalo', 'data'] }, multiplo: { type: 'boolean' },
      maximo_valores: { type: 'integer', minimum: 1, maximum: 5000 },
    }),
    eventos: ['filtro_mudou', 'filtro.alterado'], acoes: ['filtro.definir', 'limpar_filtro', 'definir_parametro'],
    fontes: { min: 1, max: 100, tipos: ['camada', 'tabela'] }, i18n: 'widget.filtro',
  },
];

const CAMPOS_MANIFESTO = ['nome', 'versao', 'api_widget', 'modulo', 'elemento', 'esquema_config', 'eventos', 'acoes', 'fontes', 'i18n'];

function falha(caminho, mensagem) { throw new Error(`${caminho}: ${mensagem}`); }

export function validarEsquema(valor, esquema, caminho = 'configuracao') {
  if (!esquema || Object.keys(esquema).length === 0) return;
  const tipo = Array.isArray(valor) ? 'array' : (valor === null ? 'null' : typeof valor);
  // JSON Schema: `integer` é um `number` sem parte fracionária (typeof não distingue os dois)
  const tipoEsperado = esquema.type === 'integer' ? 'number' : esquema.type;
  if (tipoEsperado && tipo !== tipoEsperado) falha(caminho, `esperado ${esquema.type}, recebido ${tipo}`);
  if (tipo === 'string' && esquema.maxLength !== undefined && valor.length > esquema.maxLength) falha(caminho, `máximo ${esquema.maxLength} caracteres`);
  if (tipo === 'string' && esquema.enum && !esquema.enum.includes(valor)) falha(caminho, `valor fora de ${esquema.enum.join('|')}`);
  if ((tipo === 'number' || tipo === 'integer') && esquema.minimum !== undefined && valor < esquema.minimum) falha(caminho, `mínimo ${esquema.minimum}`);
  if ((tipo === 'number' || tipo === 'integer') && esquema.maximum !== undefined && valor > esquema.maximum) falha(caminho, `máximo ${esquema.maximum}`);
  if (esquema.type === 'integer' && !Number.isInteger(valor)) falha(caminho, 'esperado inteiro');
  if (tipo === 'array') {
    if (esquema.maxItems !== undefined && valor.length > esquema.maxItems) falha(caminho, `máximo ${esquema.maxItems} itens`);
    valor.forEach((item, indice) => validarEsquema(item, esquema.items || {}, `${caminho}.${indice}`));
  }
  if (tipo === 'object') {
    for (const campo of esquema.required || []) if (!(campo in valor)) falha(`${caminho}.${campo}`, 'campo obrigatório');
    if (esquema.additionalProperties === false) {
      for (const campo of Object.keys(valor)) if (!(campo in (esquema.properties || {}))) falha(`${caminho}.${campo}`, 'campo desconhecido');
    }
    for (const [campo, subesquema] of Object.entries(esquema.properties || {})) {
      if (campo in valor) validarEsquema(valor[campo], subesquema, `${caminho}.${campo}`);
    }
  }
}

export function validarManifesto(manifesto) {
  for (const campo of CAMPOS_MANIFESTO) if (!(campo in manifesto)) falha(`manifesto.${campo}`, 'campo obrigatório');
  if (!/^[a-z][a-z0-9-]*$/.test(manifesto.nome)) falha('manifesto.nome', 'nome inválido');
  if (!/^plat-[a-z][a-z0-9-]*$/.test(manifesto.elemento)) falha('manifesto.elemento', 'Custom Element inválido');
  if (!/^\d+\.\d+\.\d+$/.test(manifesto.versao)) falha('manifesto.versao', 'semver inválido');
  if (manifesto.api_widget !== 1) falha('manifesto.api_widget', 'versão de API incompatível');
  // L5-36: além do relativo de fábrica ('./texto.js'), o manifesto de widget EXTERNO aponta o caminho
  // absoluto same-origin servido pela API ('/api/widgets/externos/<nome>/modulo.js') — nunca URL de outra
  // origem: código de terceiro só corre vindo do próprio servidor e com o sha256 conferido.
  if ((!manifesto.modulo.startsWith('./') && !manifesto.modulo.startsWith('/')) || !manifesto.modulo.endsWith('.js'))
    falha('manifesto.modulo', 'módulo inválido (relativo ./algo.js ou caminho same-origin /algo.js)');
  if (!Array.isArray(manifesto.eventos) || !Array.isArray(manifesto.acoes)) falha('manifesto', 'eventos e ações precisam ser listas');
  if (!Number.isInteger(manifesto.fontes.min) || !Number.isInteger(manifesto.fontes.max)
      || manifesto.fontes.min < 0 || manifesto.fontes.max < manifesto.fontes.min) falha('manifesto.fontes', 'limites inválidos');
  validarEsquema({}, { type: 'object' }, 'manifesto.esquema_config');
  return manifesto;
}

export const REGISTRO = new Map(manifestos.map((manifesto) => [validarManifesto(manifesto).nome, Object.freeze(manifesto)]));

export function obterManifesto(nome) { return REGISTRO.get(nome) || null; }
