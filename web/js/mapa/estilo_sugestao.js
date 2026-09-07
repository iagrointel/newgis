/* plat · mapa — sugestões do editor de simbologia (item L2-02-c-editor-simbologia-vetor). Funções PURAS, sem DOM:
   rodam no navegador (estilo_editor.js) e no node (tests/unit/test_estilo_sugestao.py), para a regra das
   categorias ("as 200 primeiras entram, o resto vira 'outros'") e a montagem das classes a partir dos cortes do
   servidor (L2-02-b) terem UMA implementação testada. As cores vêm do ColorBrewer vendorizado
   (web/vendor/colorbrewer-1.7.0.js, Apache-2.0) — `esquemas` é o objeto `colorbrewer` injetado. */

export const CATEGORIAS_MAX = 200;
export const COR_OUTROS = '#9a9a9a';

function hex(n) { return Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0'); }
function rgb(cor) { return [1, 3, 5].map((i) => parseInt(cor.slice(i, i + 2), 16)); }

/* n cores da rampa nomeada; o ColorBrewer publica de 3 a 9 (ou 12) passos, fora disso interpola em RGB entre os
   passos do maior conjunto disponível. `invertida` devolve a ordem contrária. */
export function cores(esquemas, nome, n, invertida = false) {
  const esquema = esquemas && esquemas[nome];
  if (!esquema) throw new Error(`rampa desconhecida: ${nome}`);
  const passos = Object.keys(esquema).map(Number).filter((k) => !Number.isNaN(k)).sort((a, b) => a - b);
  let lista;
  if (esquema[n]) lista = esquema[n].slice();
  else if (n < passos[0]) lista = esquema[passos[0]].slice(0, n);
  else {
    const base = esquema[passos[passos.length - 1]];
    lista = [];
    for (let i = 0; i < n; i += 1) {
      const t = n === 1 ? 0 : (i / (n - 1)) * (base.length - 1);
      const a = rgb(base[Math.floor(t)]); const b = rgb(base[Math.min(base.length - 1, Math.ceil(t))]);
      const f = t - Math.floor(t);
      lista.push(`#${hex(a[0] + (b[0] - a[0]) * f)}${hex(a[1] + (b[1] - a[1]) * f)}${hex(a[2] + (b[2] - a[2]) * f)}`);
    }
  }
  return invertida ? lista.reverse() : lista;
}

/* resposta de GET /api/camadas/{id}/classes?campo=<categórico> → categorias do construtor.
   `valores` vem ordenado por contagem (os mais frequentes primeiro); só os CATEGORIAS_MAX primeiros viram
   categoria, o resto é representado por `outros` (o `case` do estilo dá a eles a cor de outros). */
export function sugerirCategorias(resposta, paleta, limite = CATEGORIAS_MAX) {
  const valores = (resposta && resposta.valores) || [];
  const total = Number.isInteger(resposta && resposta.total_distintos) ? resposta.total_distintos : valores.length;
  const usados = valores.slice(0, limite);
  const categorias = usados.map((v, i) => {
    const valor = typeof v === 'object' && v !== null && 'valor' in v ? v.valor : v;
    return { valor, rotulo: String(valor), cor: paleta[i % paleta.length] };
  });
  const sobram = total - usados.length;
  const outros = sobram > 0 ? { cor: COR_OUTROS, rotulo: `outros (${sobram} valores)`, visivel: true } : null;
  return { categorias, outros, total_distintos: total, agrupados_em_outros: Math.max(0, sobram) };
}

/* cortes do L2-02-b (limites das faixas: [c0, c1, ..., cn], n faixas) → classes [min, max) do construtor.
   `tamanhos` opcional = [t_min, t_max] para classes de TAMANHO (interpolação linear por faixa). */
export function sugerirClasses(cortes, paleta, tamanhos = null) {
  const c = (cortes || []).map(Number);
  if (c.length < 2) return [];
  const n = c.length - 1;
  const classes = [];
  for (let i = 0; i < n; i += 1) {
    const cls = { min: c[i], max: c[i + 1], cor: paleta[i % paleta.length] };
    if (tamanhos) cls.tamanho = n === 1 ? tamanhos[0] : tamanhos[0] + ((tamanhos[1] - tamanhos[0]) * i) / (n - 1);
    classes.push(cls);
  }
  return classes;
}

/* chaves que só o editor usa (estado do formulário); nunca vão ao documento, cujo esquema é fechado */
export const CHAVES_EDITOR = ['n_classes', 'classes_de_tamanho', 'tamanho_min', 'tamanho_max', 'cortes_manuais', 'total_distintos'];

/* o mesmo objeto que o servidor recebe; garante `campos` (vocabulário), tira as chaves do editor e as nulas */
export function normalizar(pc, camposDaCamada) {
  const saida = {};
  for (const [k, v] of Object.entries(pc)) {
    if (CHAVES_EDITOR.includes(k)) continue;
    if (v !== undefined && v !== null && !(Array.isArray(v) && v.length === 0 && k !== 'classes' && k !== 'categorias')) saida[k] = v;
  }
  if (camposDaCamada && camposDaCamada.length) saida.campos = camposDaCamada.slice(0, 100);
  return saida;
}
