/* plat — validação de propriedade contra JSON Schema no navegador e geração do painel de propriedades
   (item L5-08-editor-arrasto; L5_CONCEITO D2 regra 2: "JSON Schema por tipo e por versão ... servido em
   /api/esquemas/ para o editor gerar painéis de propriedades").

   Por que um validador próprio e não Ajv: o painel só precisa do SUBCONJUNTO que descreve a propriedade de um
   widget (tipo, obrigatório, enum, faixa, tamanho, padrão de texto) e o servidor continua sendo a autoridade —
   `tipos.validar` + `documento.validar_grafo` recusam no PATCH o que passar aqui. Ajv são 120 kB para repetir no
   cliente uma decisão que o servidor toma de novo. O que este módulo NÃO faz (declarado, não escondido):
   `$ref`, `allOf/anyOf/oneOf`, `if/then`, `additionalProperties` de esquema, `format` semântico. Um esquema que
   use qualquer um deles é REPROVADO por `conferirSuportado` — nunca aceito em silêncio. */

const TIPOS_JS = {
  string: (v) => typeof v === 'string',
  number: (v) => typeof v === 'number' && Number.isFinite(v),
  integer: (v) => typeof v === 'number' && Number.isInteger(v),
  boolean: (v) => typeof v === 'boolean',
  object: (v) => v !== null && typeof v === 'object' && !Array.isArray(v),
  array: (v) => Array.isArray(v),
  null: (v) => v === null,
};

const PALAVRAS_SUPORTADAS = new Set([
  'type', 'title', 'description', 'enum', 'const', 'default', 'required', 'properties',
  'minimum', 'maximum', 'minLength', 'maxLength', 'pattern', 'items', 'minItems', 'maxItems',
  'additionalProperties', '$schema', 'multiploDe',
]);

export function conferirSuportado(esquema, caminho = '') {
  const fora = [];
  const anda = (e, c) => {
    if (!e || typeof e !== 'object') return;
    for (const k of Object.keys(e)) {
      if (!PALAVRAS_SUPORTADAS.has(k)) fora.push(`${c || '.'}${k}`);
      if (k === 'additionalProperties' && typeof e[k] === 'object') fora.push(`${c}additionalProperties(esquema)`);
    }
    for (const [nome, sub] of Object.entries(e.properties || {})) anda(sub, `${c}${nome}.`);
    if (e.items) anda(e.items, `${c}items.`);
  };
  anda(esquema, caminho);
  return fora;
}

/* devolve [] quando o valor serve, ou [{campo, erro, regra}] — mesmo formato de erro do servidor. */
export function validarValor(esquema, valor, campo = '') {
  const erros = [];
  const e = esquema || {};
  if (valor === undefined) return erros;
  const tipos = Array.isArray(e.type) ? e.type : (e.type ? [e.type] : []);
  if (tipos.length && !tipos.some((t) => TIPOS_JS[t]?.(valor))) {
    erros.push({ campo, erro: `valor precisa ser do tipo ${tipos.join(' ou ')}`, regra: 'type' });
    return erros;
  }
  if (e.enum && !e.enum.some((v) => v === valor)) {
    erros.push({ campo, erro: `valor fora da lista: ${e.enum.join(', ')}`, regra: 'enum' });
  }
  if (e.const !== undefined && valor !== e.const) erros.push({ campo, erro: `valor tem de ser ${e.const}`, regra: 'const' });
  if (typeof valor === 'number') {
    if (e.minimum !== undefined && valor < e.minimum) erros.push({ campo, erro: `mínimo ${e.minimum}`, regra: 'minimum' });
    if (e.maximum !== undefined && valor > e.maximum) erros.push({ campo, erro: `máximo ${e.maximum}`, regra: 'maximum' });
  }
  if (typeof valor === 'string') {
    if (e.minLength !== undefined && valor.length < e.minLength) erros.push({ campo, erro: `mínimo de ${e.minLength} caracteres`, regra: 'minLength' });
    if (e.maxLength !== undefined && valor.length > e.maxLength) erros.push({ campo, erro: `máximo de ${e.maxLength} caracteres`, regra: 'maxLength' });
    if (e.pattern && !new RegExp(e.pattern).test(valor)) erros.push({ campo, erro: 'formato não aceito', regra: 'pattern' });
  }
  if (Array.isArray(valor)) {
    if (e.minItems !== undefined && valor.length < e.minItems) erros.push({ campo, erro: `mínimo de ${e.minItems} itens`, regra: 'minItems' });
    if (e.maxItems !== undefined && valor.length > e.maxItems) erros.push({ campo, erro: `máximo de ${e.maxItems} itens`, regra: 'maxItems' });
    if (e.items) valor.forEach((v, i) => erros.push(...validarValor(e.items, v, `${campo}.${i}`)));
  }
  if (TIPOS_JS.object(valor) && e.properties) {
    for (const nome of e.required || []) {
      if (valor[nome] === undefined) erros.push({ campo: campo ? `${campo}.${nome}` : nome, erro: 'campo obrigatório', regra: 'required' });
    }
    for (const [nome, sub] of Object.entries(e.properties)) {
      erros.push(...validarValor(sub, valor[nome], campo ? `${campo}.${nome}` : nome));
    }
    if (e.additionalProperties === false) {
      for (const nome of Object.keys(valor)) {
        if (!(nome in e.properties)) erros.push({ campo: campo ? `${campo}.${nome}` : nome, erro: 'campo fora do esquema', regra: 'additionalProperties' });
      }
    }
  }
  return erros;
}

/* converte o texto digitado no controle para o tipo do esquema; devolve {ok, valor} — texto que não vira
   número é erro de esquema (type), não um NaN silencioso. */
export function valorDoControle(esquema, bruto) {
  const t = Array.isArray(esquema.type) ? esquema.type[0] : esquema.type;
  if (t === 'number' || t === 'integer') {
    if (bruto === '' || bruto === null) return { ok: true, valor: undefined };
    const n = Number(bruto);
    if (!Number.isFinite(n)) return { ok: false, valor: bruto };
    return { ok: true, valor: t === 'integer' && !Number.isInteger(n) ? n : n };
  }
  if (t === 'boolean') return { ok: true, valor: !!bruto };
  if (bruto === '' ) return { ok: true, valor: '' };
  return { ok: true, valor: String(bruto) };
}
