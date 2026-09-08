// Combinação do motor multicritério no navegador. Segunda implementação da MESMA conta que
// app/amc/combinacao.py faz no servidor: os dois são comparados vetor a vetor em
// tests/unit/test_amc_combinacao_equivalencia.py, com diferença absoluta máxima aceita de 0,5.
//
// O fator ausente é NULL (null ou NaN), nunca zero. Os pesos são escolhidos pelo usuário por projeto:
// não são medidos, calculados nem otimizados aqui. Todo resultado carrega a frase em `avisoPesos`.

export const AVISO_PESOS = 'pesos escolhidos pelo usuário, não medidos';

export const COMBINADORES = {
  soma_ponderada: 'soma ponderada normalizada Σ w·f / Σ w sobre os fatores com dado (padrão)',
  percentual: 'soma com pesos em porcentagem que fecham 100, arredondada ao inteiro (paridade '
    + 'com o Weighted Overlay; perde precisão, não é a recomendação da casa)',
  media_geometrica: 'média geométrica ponderada exp(Σ w·ln f / Σ w); um fator em zero anula a nota',
  minimo: 'mínimo dos fatores com dado (E fuzzy); ignora os pesos por definição',
  maximo: 'máximo dos fatores com dado (OU fuzzy); ignora os pesos por definição',
  produto: 'produto fuzzy Π f, na escala 0-1; ignora os pesos por definição',
  soma_fuzzy: 'soma fuzzy 1 − Π(1 − f), na escala 0-1; ignora os pesos por definição',
  gama: 'gama fuzzy (soma fuzzy)^γ · (produto)^(1−γ); ignora os pesos por definição',
};
// Tradução do vocabulário do documento do modelo (docs/esquemas/amc_modelo.v1.json, item L3-01-a) para o
// vocabulário desta função — as duas trilhas nomearam a mesma escolha de forma diferente. Gêmeo em JavaScript
// dos dicionários MAPA_COMBINADOR/MAPA_POLITICA de app/amc/explicacao.py; quem escrever mais um nome de
// combinador tem de escrever nos dois lugares, e tests/unit/test_amc_combinacao_equivalencia.py cobra.
export const MAPA_COMBINADOR = {
  soma_ponderada_normalizada: 'soma_ponderada',
  percentual: 'percentual',
  media_geometrica: 'media_geometrica',
  minimo: 'minimo',
  maximo: 'maximo',
  produto: 'produto',
  soma_fuzzy: 'soma_fuzzy',
  gama: 'gama',
};
export const MAPA_POLITICA = {
  excluir_fator: 'excluir',
  unidade_nula: 'nulo',
  nota_pessimista: 'pessimista',
};
export const SEM_PESO = ['minimo', 'maximo', 'produto', 'soma_fuzzy', 'gama'];
export const POLITICAS_AUSENTE = {
  excluir: 'o fator sai da conta naquela unidade e a cobertura cai (padrão)',
  nulo: 'a unidade inteira fica sem nota quando falta qualquer fator',
  pessimista: 'o fator ausente recebe a nota 0, declarada como estimativa pessimista',
};
const ESCALA_MAX = 100;
const TOLERANCIA_PERCENTUAL = 1e-6;

export class ErroCombinacao extends Error {
  constructor(codigo, mensagem, detalhe = null) {
    super(mensagem);
    this.codigo = codigo;
    this.mensagem = mensagem;
    this.detalhe = detalhe;
  }
}

function ausente(v) { return v === null || v === undefined || Number.isNaN(v); }

function validaPesos(pesos, nFatores, combinador) {
  if (!Array.isArray(pesos) || pesos.length !== nFatores) {
    throw new ErroCombinacao('pesos_incompativeis',
      `são ${nFatores} fatores e ${Array.isArray(pesos) ? pesos.length : '?'} pesos; um peso por fator`);
  }
  let soma = 0;
  for (const p of pesos) {
    if (!Number.isFinite(p)) throw new ErroCombinacao('peso_nao_finito', 'peso ausente, infinito ou NaN não é aceito');
    if (p < 0) throw new ErroCombinacao('peso_negativo', 'peso negativo não é aceito; o peso é multiplicador ≥ 0');
    soma += p;
  }
  if (soma <= 0) throw new ErroCombinacao('soma_de_pesos_zero', 'a soma dos pesos é zero; não há como normalizar');
  if (combinador === 'percentual' && Math.abs(soma - 100) > TOLERANCIA_PERCENTUAL) {
    throw new ErroCombinacao('percentual_nao_soma_100',
      `no modo percentual os pesos têm de somar 100; somaram ${soma.toFixed(6)}`, { soma });
  }
  return soma;
}

function validaIds(ids, nFatores) {
  if (!ids) return null;
  if (ids.length !== nFatores) {
    throw new ErroCombinacao('ids_incompativeis', `são ${nFatores} fatores e ${ids.length} identificadores`);
  }
  const vistos = new Set(); const repetidos = new Set();
  for (const i of ids) { if (vistos.has(i)) repetidos.add(i); vistos.add(i); }
  if (repetidos.size) {
    throw new ErroCombinacao('fator_duplicado',
      `o mesmo fator aparece mais de uma vez no modelo: ${[...repetidos].sort().join(', ')}`,
      { repetidos: [...repetidos].sort() });
  }
  return ids;
}

/** Combina a matriz `fatores` (unidade × fator, escala 0-100, null = sem dado). */
export function combinar(fatores, pesos, opcoes = {}) {
  const {
    combinador = 'soma_ponderada', politicaAusente = 'excluir', gama = 0.5,
    fracaoVetada = null, motivoVeto = null, idsFatores = null,
  } = opcoes;
  if (!(combinador in COMBINADORES)) {
    throw new ErroCombinacao('combinador_desconhecido', `combinador desconhecido: ${combinador}`,
      { aceitos: Object.keys(COMBINADORES).sort() });
  }
  if (!(politicaAusente in POLITICAS_AUSENTE)) {
    throw new ErroCombinacao('politica_ausente_desconhecida',
      `política de dado ausente desconhecida: ${politicaAusente}`, { aceitas: Object.keys(POLITICAS_AUSENTE).sort() });
  }
  if (!Array.isArray(fatores) || (fatores.length && !Array.isArray(fatores[0]))) {
    throw new ErroCombinacao('matriz_invalida', 'a matriz de fatores precisa ter duas dimensões (unidade × fator)');
  }
  const nUnidades = fatores.length;
  const nFatores = nUnidades ? fatores[0].length : (Array.isArray(pesos) ? pesos.length : 0);
  if (!nFatores) throw new ErroCombinacao('sem_fatores', 'o modelo não tem nenhum fator');
  validaIds(idsFatores, nFatores);
  const somaPesosTotal = validaPesos(pesos, nFatores, combinador);
  if (!Number.isFinite(gama) || gama < 0 || gama > 1) {
    throw new ErroCombinacao('gama_fora_da_faixa', 'o parâmetro gama tem de estar entre 0 e 1');
  }
  let veto = null;
  if (fracaoVetada !== null) {
    if (!Array.isArray(fracaoVetada) || fracaoVetada.length !== nUnidades) {
      throw new ErroCombinacao('fracao_vetada_incompativel', 'uma fração vetada por unidade de análise');
    }
    for (const f of fracaoVetada) {
      if (!Number.isFinite(f) || f < 0 || f > 1) {
        throw new ErroCombinacao('fracao_vetada_invalida', 'a fração vetada tem de estar entre 0 e 1');
      }
    }
    veto = fracaoVetada;
  }

  const fav = new Array(nUnidades).fill(null);
  const vetado = new Array(nUnidades).fill(false);
  const cobertura = new Array(nUnidades).fill(0);
  const motivo = new Array(nUnidades).fill(null);
  let semNota = 0; let zeradas = 0;

  for (let i = 0; i < nUnidades; i += 1) {
    const linha = fatores[i];
    if (linha.length !== nFatores) {
      throw new ErroCombinacao('matriz_invalida', `a unidade ${i} tem ${linha.length} fatores, não ${nFatores}`);
    }
    const completa = linha.every((v) => !ausente(v));
    let somaPesoPresente = 0; let acumulado = 0; let logAcumulado = 0;
    let temZero = false; let minimo = Infinity; let maximo = -Infinity;
    let produto = 1; let complemento = 1; let algum = false;
    for (let j = 0; j < nFatores; j += 1) {
      let v = linha[j];
      let presente = !ausente(v);
      if (!presente && politicaAusente === 'pessimista') { v = 0; presente = true; }
      if (presente && politicaAusente === 'nulo' && !completa) presente = false;
      if (!presente) continue;
      if (!Number.isFinite(v)) throw new ErroCombinacao('valor_nao_finito', 'fator infinito não é aceito; ausência de dado é NULL');
      if (v < 0 || v > ESCALA_MAX) {
        throw new ErroCombinacao('valor_fora_da_escala',
          `fator fora da escala 0-100 na unidade ${i}, fator ${j}: ${v}`, { unidade: i, fator: j, valor: v });
      }
      algum = true;
      const w = pesos[j];
      somaPesoPresente += w;
      acumulado += w * v;
      if (v <= 0) temZero = true; else logAcumulado += w * Math.log(v);
      if (v < minimo) minimo = v;
      if (v > maximo) maximo = v;
      produto *= v / ESCALA_MAX;
      complemento *= 1 - v / ESCALA_MAX;
    }
    cobertura[i] = somaPesoPresente / somaPesosTotal;
    if (veto && veto[i] >= 1) {
      vetado[i] = true; zeradas += 1;
      motivo[i] = (motivoVeto && motivoVeto[i]) || 'unidade inteiramente coberta por restrição declarada no modelo';
    }
    // unidade sem nenhum dado continua sem nota mesmo quando vetada: veto marca, não inventa número
    if (!algum) { semNota += 1; continue; }
    let nota;
    if (combinador === 'soma_ponderada') nota = acumulado / somaPesoPresente;
    else if (combinador === 'percentual') nota = Math.round(acumulado / somaPesoPresente);
    else if (combinador === 'media_geometrica') nota = temZero ? 0 : Math.exp(logAcumulado / somaPesoPresente);
    else if (combinador === 'minimo') nota = minimo;
    else if (combinador === 'maximo') nota = maximo;
    else if (combinador === 'produto') nota = produto * ESCALA_MAX;
    else if (combinador === 'soma_fuzzy') nota = (1 - complemento) * ESCALA_MAX;
    else nota = ((1 - complemento) ** gama) * (produto ** (1 - gama)) * ESCALA_MAX;
    if (veto) {
      nota = veto[i] >= 1 ? 0 : nota * (1 - veto[i]);
    }
    fav[i] = nota;
  }

  const observacoes = [];
  if (zeradas) observacoes.push(`${zeradas} de ${nUnidades} unidades zeradas por restrição, não por peso`);
  if (SEM_PESO.includes(combinador)) {
    observacoes.push(`o combinador ${combinador} não usa peso por definição matemática; `
      + 'os pesos escolhidos pelo usuário não entram nesta conta');
  }
  if (combinador === 'percentual') {
    observacoes.push('modo de paridade com o Weighted Overlay: a nota é arredondada ao inteiro e perde precisão');
  }
  if (semNota) observacoes.push(`${semNota} de ${nUnidades} unidades ficaram sem nota por falta de dado`);

  return {
    avisoPesos: AVISO_PESOS,
    aviso_pesos: AVISO_PESOS,
    combinador,
    descricaoCombinador: COMBINADORES[combinador],
    politicaAusente,
    pesosNormalizados: pesos.map((p) => p / somaPesosTotal),
    observacoes,
    fav,
    vetado,
    cobertura,
    motivo,
  };
}
