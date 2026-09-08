const textoCurto = { type: 'string', maxLength: 200 };
const objetoFechado = (properties = {}, required = []) => ({ type: 'object', additionalProperties: false, properties, required });

const manifestos = [
  {
    nome: 'mapa', versao: '1.0.0', api_widget: 1, modulo: './mapa.js', elemento: 'plat-w-mapa',
    esquema_config: objetoFechado({ rotulo: textoCurto }),
    eventos: ['mapa.selecao', 'mapa.extensao_alterada'], acoes: ['mapa.enquadrar', 'mapa.destacar'],
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
    nome: 'tabela', versao: '1.0.0', api_widget: 1, modulo: './tabela.js', elemento: 'plat-w-tabela',
    esquema_config: objetoFechado({
      colunas: { type: 'array', maxItems: 100, items: objetoFechado({ campo: textoCurto, rotulo: textoCurto }, ['campo', 'rotulo']) },
      linhas: { type: 'array', maxItems: 10000, items: { type: 'object' } },
    }, ['colunas']),
    eventos: ['tabela.linha_selecionada'], acoes: ['tabela.definir', 'tabela.filtrar'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.tabela',
  },
  {
    nome: 'texto', versao: '1.1.0', api_widget: 1, modulo: './texto.js', elemento: 'plat-w-texto',
    esquema_config: objetoFechado({
      texto: { type: 'string', maxLength: 10000 }, nivel: { type: 'integer', minimum: 1, maximum: 6 },
      formato: { type: 'string', enum: ['texto', 'markdown'] },
    }, ['texto']),
    eventos: [], acoes: ['texto.definir', 'texto.feicao'], fontes: { min: 0, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.texto',
  },
  {
    nome: 'botao', versao: '1.1.0', api_widget: 1, modulo: './botao.js', elemento: 'plat-w-botao',
    esquema_config: objetoFechado({
      rotulo: textoCurto, valor: {}, habilitado: { type: 'boolean' },
      acao: objetoFechado({ tipo: { type: 'string', enum: ['evento', 'link', 'pagina'] }, url: { type: 'string', maxLength: 2048 },
                            pagina: textoCurto, nova_aba: { type: 'boolean' } }, ['tipo']),
    }, ['rotulo']),
    eventos: ['botao.acionado', 'botao.pagina'], acoes: ['botao.habilitar'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.botao',
  },
  {
    nome: 'filtro', versao: '1.0.0', api_widget: 1, modulo: './filtro.js', elemento: 'plat-w-filtro',
    esquema_config: objetoFechado({ rotulo: textoCurto, valor: textoCurto }),
    eventos: ['filtro.alterado'], acoes: ['filtro.definir'], fontes: { min: 1, max: 100, tipos: ['camada', 'tabela'] }, i18n: 'widget.filtro',
  },
  // ---- widgets de página e de menu (item L5-01-d): texto/imagem/botão/cartão/incorporar/divisor · menu/controlador/
  // compartilhar/login/idioma/tema — os 12 do "Page elements" + "Menu and toolbar" do Experience Builder
  {
    nome: 'imagem', versao: '1.0.0', api_widget: 1, modulo: './imagem.js', elemento: 'plat-w-imagem',
    esquema_config: objetoFechado({
      url: { type: 'string', maxLength: 2048 }, campo: textoCurto, alternativo: textoCurto, legenda: textoCurto,
      ajuste: { type: 'string', enum: ['cover', 'contain', 'fill', 'none'] }, altura: { type: 'integer', minimum: 16, maximum: 4000 },
    }),
    eventos: ['imagem.acionada'], acoes: ['imagem.definir', 'imagem.feicao'], fontes: { min: 0, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.imagem',
  },
  {
    nome: 'cartao', versao: '1.0.0', api_widget: 1, modulo: './cartao.js', elemento: 'plat-w-cartao',
    esquema_config: objetoFechado({
      titulo: textoCurto, texto: { type: 'string', maxLength: 10000 }, imagem: { type: 'string', maxLength: 2048 },
      imagem_alternativo: textoCurto, link: { type: 'string', maxLength: 2048 }, link_rotulo: textoCurto, pagina: textoCurto,
    }),
    eventos: ['cartao.acionado', 'cartao.pagina'], acoes: ['cartao.feicao'], fontes: { min: 0, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.cartao',
  },
  {
    nome: 'incorporar', versao: '1.0.0', api_widget: 1, modulo: './incorporar.js', elemento: 'plat-w-incorporar',
    esquema_config: objetoFechado({
      url: { type: 'string', maxLength: 2048 }, html: { type: 'string', maxLength: 20000 }, titulo: textoCurto,
      altura: { type: 'integer', minimum: 40, maximum: 4000 },
      dominios_permitidos: { type: 'array', maxItems: 20, items: textoCurto },
      sandbox: { type: 'array', maxItems: 4, items: { type: 'string', enum: ['allow-scripts', 'allow-forms', 'allow-popups', 'allow-presentation'] } },
    }),
    eventos: [], acoes: ['incorporar.definir'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.incorporar',
  },
  {
    nome: 'divisor', versao: '1.0.0', api_widget: 1, modulo: './divisor.js', elemento: 'plat-w-divisor',
    esquema_config: objetoFechado({ estilo: { type: 'string', enum: ['linha', 'tracejado', 'espaco'] }, vertical: { type: 'boolean' } }),
    eventos: [], acoes: [], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.divisor',
  },
  {
    nome: 'menu', versao: '1.0.0', api_widget: 1, modulo: './menu.js', elemento: 'plat-w-menu',
    esquema_config: objetoFechado({
      rotulo: textoCurto, orientacao: { type: 'string', enum: ['horizontal', 'vertical'] },
      itens: { type: 'array', maxItems: 50, items: objetoFechado({ rotulo: textoCurto, pagina: textoCurto, url: { type: 'string', maxLength: 2048 }, valor: {} }, ['rotulo']) },
    }, ['itens']),
    eventos: ['menu.pagina', 'menu.acionado'], acoes: ['menu.definir'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.menu',
  },
  {
    nome: 'controlador', versao: '1.0.0', api_widget: 1, modulo: './controlador.js', elemento: 'plat-w-controlador',
    esquema_config: objetoFechado({
      alvos: { type: 'array', maxItems: 50, items: objetoFechado({ id: textoCurto, rotulo: textoCurto }, ['id']) },
    }, ['alvos']),
    eventos: ['controlador.alternado'], acoes: ['controlador.abrir', 'controlador.fechar'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.controlador',
  },
  {
    nome: 'compartilhar', versao: '1.0.0', api_widget: 1, modulo: './compartilhar.js', elemento: 'plat-w-compartilhar',
    esquema_config: objetoFechado({ url: { type: 'string', maxLength: 2048 }, qr: { type: 'boolean' }, incorporar: { type: 'boolean' } }),
    eventos: [], acoes: [], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.compartilhar',
  },
  {
    nome: 'login', versao: '1.0.0', api_widget: 1, modulo: './login.js', elemento: 'plat-w-login',
    esquema_config: objetoFechado({ rotulo: textoCurto }),
    eventos: ['login.mudou'], acoes: ['login.atualizar'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.login',
  },
  {
    nome: 'idioma', versao: '1.0.0', api_widget: 1, modulo: './idioma.js', elemento: 'plat-w-idioma',
    esquema_config: objetoFechado({ rotulo: textoCurto, idiomas: { type: 'array', maxItems: 10, items: textoCurto } }),
    eventos: ['idioma.mudou'], acoes: ['idioma.definir'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.idioma',
  },
  {
    nome: 'tema', versao: '1.0.0', api_widget: 1, modulo: './tema.js', elemento: 'plat-w-tema',
    esquema_config: objetoFechado({ rotulo: textoCurto }),
    eventos: ['tema.mudou'], acoes: ['tema.definir'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.tema',
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
