// Perfis de uso da linguagem de expressão no NAVEGADOR (item L5-11-expressoes-no-navegador).
// Espelho exato de app/expressao/perfis.py: mesmos nomes de perfil, mesmos tipos de retorno
// aceitos, mesmos orçamentos e mesmos códigos de erro. O perfil não muda a semântica da
// linguagem — só o contrato de saída e o orçamento —, e é por isso que a MESMA expressão no
// popup e no cálculo de formulário devolve o MESMO valor.
// Sem rede: este módulo não usa fetch, XMLHttpRequest, window, document nem import dinâmico
// (tests/unit/test_expressao_perfis.py varre o arquivo e reprova se aparecer qualquer um).
import { analisar, avaliar, ErroExpressao, LIMITE_MS_CLIENTE, MAX_PASSOS_PADRAO } from './avaliador.js';

export const LIMITE_MS_SERVIDOR = 500; // o mesmo valor de LIMITE_MS_SERVIDOR em avaliador_py.py
export const CAMPOS_RESERVADOS = ['feicao', 'geometria'];

const ESCALAR = ['texto', 'numero', 'booleano', 'nulo'];
const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const possui = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

export const PERFIS = {
  popup: {
    tipos: ESCALAR, limite_ms: LIMITE_MS_CLIENTE, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'linha de conteúdo da janela de feição, avaliada no navegador a cada clique',
  },
  rotulo: {
    tipos: ['texto', 'numero', 'nulo'], limite_ms: LIMITE_MS_CLIENTE, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'texto desenhado sobre a feição no mapa, avaliado no navegador a cada quadro',
  },
  calculo_formulario: {
    tipos: ESCALAR, limite_ms: LIMITE_MS_SERVIDOR, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'valor calculado de um campo do formulário de edição, conferido também no servidor',
  },
  visibilidade: {
    tipos: ['booleano', 'nulo'], limite_ms: LIMITE_MS_CLIENTE, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'mostra ou esconde um campo/elemento; nulo é "não sei" e o chamador trata como escondido',
  },
  restricao: {
    tipos: ['booleano', 'nulo'], limite_ms: LIMITE_MS_SERVIDOR, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'verdadeiro = a feição pode ser gravada; falso ou nulo = a gravação é recusada',
  },
  indicador_painel: {
    tipos: ['numero', 'nulo'], limite_ms: LIMITE_MS_SERVIDOR, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'número exibido num indicador de painel',
  },
  titulo_dinamico: {
    tipos: ['texto', 'numero', 'nulo'], limite_ms: LIMITE_MS_CLIENTE, limite_passos: MAX_PASSOS_PADRAO,
    descricao: 'título de janela, aba ou painel montado a partir da feição',
  },
};

export function tipoDoValor(valor) {
  if (valor === null || valor === undefined) return 'nulo';
  if (typeof valor === 'boolean') return 'booleano';
  if (typeof valor === 'number' && !Number.isNaN(valor)) return 'numero';
  if (typeof valor === 'string') return 'texto';
  if (Array.isArray(valor)) return 'lista';
  if (typeof valor === 'object') return 'dicionario';
  return 'desconhecido';
}

export function descricaoDoPerfil(nome) {
  if (typeof nome !== 'string' || !possui(PERFIS, nome)) {
    throw new ErroExpressao('perfil_desconhecido', `perfil desconhecido: ${nome}`, { perfil: nome });
  }
  return PERFIS[nome];
}

function feicaoNormalizada(feicao) {
  if (feicao === null || feicao === undefined) return { atributos: {}, geometria: null };
  if (typeof feicao !== 'object' || Array.isArray(feicao)) {
    throw new ErroExpressao('feicao_invalida', 'feição tem de ser um dicionário', {});
  }
  let atributos = possui(feicao, 'atributos') ? feicao.atributos : {};
  if (atributos === null || atributos === undefined) atributos = {};
  if (typeof atributos !== 'object' || Array.isArray(atributos)) {
    throw new ErroExpressao('feicao_invalida', 'atributos da feição têm de ser um dicionário de nomes', {});
  }
  const geometria = possui(feicao, 'geometria') ? feicao.geometria : null;
  if (geometria !== null && geometria !== undefined && (typeof geometria !== 'object' || Array.isArray(geometria))) {
    throw new ErroExpressao('feicao_invalida', 'geometria da feição tem de ser um dicionário GeoJSON', {});
  }
  const copia = {};
  for (const k of Object.keys(atributos)) copia[k] = atributos[k];
  return { atributos: copia, geometria: geometria === undefined ? null : geometria };
}

export function contextoDaFeicao(feicao) {
  const normalizada = feicaoNormalizada(feicao);
  const contexto = {};
  for (const nome of Object.keys(normalizada.atributos)) {
    if (CAMPOS_RESERVADOS.includes(nome) || !IDENT.test(nome)) continue; // só por Atributo($feicao, '<nome>')
    contexto[nome] = normalizada.atributos[nome];
  }
  contexto.feicao = normalizada;
  contexto.geometria = normalizada.geometria;
  return contexto;
}

export function avaliarPerfil(perfil, expressao, feicao = null, opcoes = {}) {
  const descricao = descricaoDoPerfil(perfil);
  const valor = avaliar(analisar(expressao), contextoDaFeicao(feicao), {
    limitePassos: opcoes.limitePassos === undefined ? descricao.limite_passos : opcoes.limitePassos,
    limiteMs: opcoes.limiteMs === undefined ? descricao.limite_ms : opcoes.limiteMs,
  });
  const tipo = tipoDoValor(valor);
  if (!descricao.tipos.includes(tipo)) {
    throw new ErroExpressao(
      'tipo_de_retorno_invalido',
      `perfil ${perfil} espera ${descricao.tipos.join('/')}, a expressão devolveu ${tipo}`,
      { perfil, tipo },
    );
  }
  return valor;
}
