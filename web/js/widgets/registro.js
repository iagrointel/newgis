const textoCurto = { type: 'string', maxLength: 200 };
const objetoFechado = (properties = {}, required = []) => ({ type: 'object', additionalProperties: false, properties, required });

const manifestos = [
  {
    nome: 'mapa', versao: '1.0.0', api_widget: 1, modulo: './mapa.js', elemento: 'plat-mapa',
    esquema_config: objetoFechado({ rotulo: textoCurto }),
    eventos: ['mapa.selecao', 'mapa.extensao_alterada'], acoes: ['mapa.enquadrar', 'mapa.destacar'],
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
    nome: 'tabela', versao: '1.0.0', api_widget: 1, modulo: './tabela.js', elemento: 'plat-tabela',
    esquema_config: objetoFechado({
      colunas: { type: 'array', maxItems: 100, items: objetoFechado({ campo: textoCurto, rotulo: textoCurto }, ['campo', 'rotulo']) },
      linhas: { type: 'array', maxItems: 10000, items: { type: 'object' } },
    }, ['colunas']),
    eventos: ['tabela.linha_selecionada'], acoes: ['tabela.definir', 'tabela.filtrar'],
    fontes: { min: 1, max: 1, tipos: ['camada', 'tabela'] }, i18n: 'widget.tabela',
  },
  {
    nome: 'texto', versao: '1.0.0', api_widget: 1, modulo: './texto.js', elemento: 'plat-texto',
    esquema_config: objetoFechado({ texto: { type: 'string', maxLength: 10000 }, nivel: { type: 'integer', minimum: 1, maximum: 6 } }, ['texto']),
    eventos: [], acoes: ['texto.definir'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.texto',
  },
  {
    nome: 'botao', versao: '1.0.0', api_widget: 1, modulo: './botao.js', elemento: 'plat-botao',
    esquema_config: objetoFechado({ rotulo: textoCurto, valor: {}, habilitado: { type: 'boolean' } }, ['rotulo']),
    eventos: ['botao.acionado'], acoes: ['botao.habilitar'], fontes: { min: 0, max: 0, tipos: [] }, i18n: 'widget.botao',
  },
  {
    nome: 'filtro', versao: '1.0.0', api_widget: 1, modulo: './filtro.js', elemento: 'plat-filtro',
    esquema_config: objetoFechado({ rotulo: textoCurto, placeholder: textoCurto, valor: textoCurto }),
    eventos: ['filtro.alterado'], acoes: ['filtro.definir'], fontes: { min: 1, max: 100, tipos: ['camada', 'tabela'] }, i18n: 'widget.filtro',
  },
];

const CAMPOS_MANIFESTO = ['nome', 'versao', 'api_widget', 'modulo', 'elemento', 'esquema_config', 'eventos', 'acoes', 'fontes', 'i18n'];

function falha(caminho, mensagem) { throw new Error(`${caminho}: ${mensagem}`); }

export function validarEsquema(valor, esquema, caminho = 'configuracao') {
  if (!esquema || Object.keys(esquema).length === 0) return;
  const tipo = Array.isArray(valor) ? 'array' : (valor === null ? 'null' : typeof valor);
  if (esquema.type && tipo !== esquema.type) falha(caminho, `esperado ${esquema.type}, recebido ${tipo}`);
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
