/* plat — registro de widgets (item L5-06-motor-widgets; ampliado pelo L5-07-fontes-vistas-mensagens e pelo
   L5-01-c-widgets-dado: tabela 2, gráfico 2, filtro 2, lista, consulta, seleção, info-feicao, adicionar-dado).
   Cada manifesto declara os EVENTOS que emite e as AÇÕES que aceita no vocabulário do barramento
   (L5_CONCEITO D5): eventos clique | dado_adicionado | filtro_mudou | extensao_mudou | localizacao |
   registros_carregados | selecao_mudou | vista_mudou; ações de dado filtrar | selecionar | limpar_filtro |
   limpar_selecao (resolvidas na VISTA do widget) e de widget zoom | pan | piscar | popup | abrir | fechar |
   definir_parametro (chamadas no elemento). `configuracao.vista` liga o widget a uma vista do documento. */
const textoCurto = { type: 'string', maxLength: 200 };
const ulid = { type: 'string', maxLength: 26 };
const objetoFechado = (properties = {}, required = []) => ({ type: 'object', additionalProperties: false, properties, required });

export const EVENTOS_BARRAMENTO = Object.freeze(['clique', 'dado_adicionado', 'filtro_mudou', 'extensao_mudou', 'localizacao', 'registros_carregados', 'selecao_mudou', 'vista_mudou']);
export const ACOES_DADO = Object.freeze(['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao']);
export const ACOES_WIDGET = Object.freeze(['zoom', 'pan', 'piscar', 'popup', 'abrir', 'fechar', 'definir_parametro']);

const manifestos = [
  {
    nome: 'mapa', versao: '1.1.0', api_widget: 1, modulo: './mapa.js', elemento: 'plat-mapa',
    esquema_config: objetoFechado({ rotulo: textoCurto, vista: ulid, campo_rotulo: textoCurto, altura: { type: 'integer', minimum: 120, maximum: 2000 } }),
    eventos: ['clique', 'selecao_mudou', 'extensao_mudou', 'registros_carregados', 'mapa.selecao', 'mapa.extensao_alterada'],
    acoes: [...ACOES_DADO, 'zoom', 'pan', 'piscar', 'popup', 'mapa.enquadrar', 'mapa.destacar'],
    fontes: { min: 0, max: 100, tipos: ['mapa', 'camada'] }, i18n: 'widget.mapa',
  },
  {
    nome: 'legenda', versao: '1.0.0', api_widget: 1, modulo: './legenda.js', elemento: 'plat-legenda',
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
    nome: 'texto', versao: '1.0.0', api_widget: 1, modulo: './texto.js', elemento: 'plat-texto',
    esquema_config: objetoFechado({ texto: { type: 'string', maxLength: 10000 }, nivel: { type: 'integer', minimum: 1, maximum: 6 } }, ['texto']),
    eventos: [], acoes: ['texto.definir', 'definir_parametro'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.texto',
  },
  {
    nome: 'botao', versao: '1.0.0', api_widget: 1, modulo: './botao.js', elemento: 'plat-botao',
    esquema_config: objetoFechado({ rotulo: textoCurto, valor: {}, habilitado: { type: 'boolean' } }, ['rotulo']),
    eventos: ['clique', 'botao.acionado'], acoes: ['botao.habilitar', 'abrir', 'fechar'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.botao',
  },
  {
    nome: 'filtro', versao: '2.0.0', api_widget: 1, modulo: './filtro.js', elemento: 'plat-filtro',
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
  if (!manifesto.modulo.startsWith('./') || !manifesto.modulo.endsWith('.js')) falha('manifesto.modulo', 'módulo relativo inválido');
  if (!Array.isArray(manifesto.eventos) || !Array.isArray(manifesto.acoes)) falha('manifesto', 'eventos e ações precisam ser listas');
  if (!Number.isInteger(manifesto.fontes.min) || !Number.isInteger(manifesto.fontes.max)
      || manifesto.fontes.min < 0 || manifesto.fontes.max < manifesto.fontes.min) falha('manifesto.fontes', 'limites inválidos');
  validarEsquema({}, { type: 'object' }, 'manifesto.esquema_config');
  return manifesto;
}

export const REGISTRO = new Map(manifestos.map((manifesto) => [validarManifesto(manifesto).nome, Object.freeze(manifesto)]));

export function obterManifesto(nome) { return REGISTRO.get(nome) || null; }
