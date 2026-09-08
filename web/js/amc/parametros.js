/* plat · AMC — item L3-01-g-tela-motor: quais campos cada transformação pede, para o formulário de fator ser
   um formulário de verdade e não uma caixa de JSON cru. A lista espelha os parâmetros lidos por
   `app/amc/transformacoes.py` (item L3-01-d) — quando um tipo ganhar parâmetro novo lá, ele entra aqui.
   `abaixo`/`acima` são comuns a todos e ficam fora desta tabela (a tela os oferece à parte). */

export const CAMPOS = {
  categoria: [{ nome: 'notas', tipo: 'pares', rotulo: 'nota por categoria (codigo:nota)' },
              { nome: 'outros', tipo: 'numero', rotulo: 'nota das demais categorias', opcional: true }],
  faixas: [{ nome: 'quebras', tipo: 'lista', rotulo: 'quebras (valores crescentes)' },
           { nome: 'notas', tipo: 'lista', rotulo: 'notas (uma a mais que as quebras)' }],
  linear: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
           { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' },
           { nome: 'direcao', tipo: 'escolha', rotulo: 'direção', opcoes: ['crescente', 'decrescente'] }],
  linear_simetrica: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
                     { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' }],
  degraus: [{ nome: 'bandas', tipo: 'bandas', rotulo: 'bandas (ate:nota, uma por linha)' }],
  exponencial: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
                { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' },
                { nome: 'deslocamento', tipo: 'numero', rotulo: 'deslocamento', opcional: true },
                { nome: 'base', tipo: 'numero', rotulo: 'base', opcional: true }],
  logaritmo: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
              { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' },
              { nome: 'deslocamento', tipo: 'numero', rotulo: 'deslocamento', opcional: true },
              { nome: 'fator', tipo: 'numero', rotulo: 'fator', opcional: true }],
  potencia: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
             { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' },
             { nome: 'deslocamento', tipo: 'numero', rotulo: 'deslocamento', opcional: true },
             { nome: 'expoente', tipo: 'numero', rotulo: 'expoente', opcional: true }],
  crescimento_logistico: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
                          { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' },
                          { nome: 'y_intercepto_percentual', tipo: 'numero',
                            rotulo: 'intercepto em y (%)', opcional: true }],
  decaimento_logistico: [{ nome: 'minimo', tipo: 'numero', rotulo: 'mínimo' },
                         { nome: 'maximo', tipo: 'numero', rotulo: 'máximo' },
                         { nome: 'y_intercepto_percentual', tipo: 'numero',
                           rotulo: 'intercepto em y (%)', opcional: true }],
  gaussiana: [{ nome: 'midpoint', tipo: 'numero', rotulo: 'ponto médio' },
              { nome: 'spread', tipo: 'numero', rotulo: 'espalhamento' }],
  proxima: [{ nome: 'midpoint', tipo: 'numero', rotulo: 'ponto médio' },
            { nome: 'spread', tipo: 'numero', rotulo: 'espalhamento' }],
  grande: [{ nome: 'midpoint', tipo: 'numero', rotulo: 'ponto médio' },
           { nome: 'spread', tipo: 'numero', rotulo: 'espalhamento' }],
  pequena: [{ nome: 'midpoint', tipo: 'numero', rotulo: 'ponto médio' },
            { nome: 'spread', tipo: 'numero', rotulo: 'espalhamento' }],
  ms_grande: [{ nome: 'multiplicador_media', tipo: 'numero', rotulo: 'multiplicador da média' },
              { nome: 'multiplicador_desvio', tipo: 'numero', rotulo: 'multiplicador do desvio' }],
  ms_pequena: [{ nome: 'multiplicador_media', tipo: 'numero', rotulo: 'multiplicador da média' },
               { nome: 'multiplicador_desvio', tipo: 'numero', rotulo: 'multiplicador do desvio' }],
};

export const TIPOS = Object.keys(CAMPOS);

/* extratores do esquema amc_modelo.v1 agrupados pela geometria da camada, que é como o usuário pensa */
export const EXTRATORES = {
  raster: ['raster_media', 'raster_minimo', 'raster_maximo', 'raster_mediana', 'raster_percentil',
           'raster_moda', 'raster_fracao_classe'],
  poligono: ['poligono_fracao_area', 'poligono_area', 'poligono_contagem', 'poligono_atributo_ponderado'],
  linha: ['linha_comprimento', 'linha_distancia_mais_proxima'],
  ponto: ['ponto_contagem_raio', 'ponto_densidade_kernel', 'ponto_distancia_mais_proximo',
          'ponto_atributo_mais_proximo'],
  pronto: ['valor_pronto'],
};

/** texto do formulário → valor do parâmetro, por tipo de campo; devolve undefined quando vazio e opcional. */
export function lerCampo(campo, texto) {
  const cru = (texto ?? '').trim();
  if (cru === '') {
    if (campo.opcional) return undefined;
    throw new Error(`o campo "${campo.rotulo}" é obrigatório`);
  }
  if (campo.tipo === 'numero') {
    const n = Number(cru);
    if (!Number.isFinite(n)) throw new Error(`"${campo.rotulo}" não é um número: ${cru}`);
    return n;
  }
  if (campo.tipo === 'escolha') return cru;
  if (campo.tipo === 'lista') {
    const lista = cru.split(',').map((x) => Number(x.trim()));
    if (lista.some((n) => !Number.isFinite(n))) throw new Error(`"${campo.rotulo}" tem valor que não é número`);
    return lista;
  }
  if (campo.tipo === 'pares') {
    const notas = {};
    for (const linha of cru.split(/[\n,]/)) {
      const l = linha.trim();
      if (!l) continue;
      const [k, v] = l.split(':');
      const n = Number((v ?? '').trim());
      if (!k || !Number.isFinite(n)) throw new Error(`"${campo.rotulo}": esperado codigo:nota, veio ${l}`);
      notas[k.trim()] = n;
    }
    return notas;
  }
  if (campo.tipo === 'bandas') {
    const bandas = [];
    for (const linha of cru.split(/[\n,]/)) {
      const l = linha.trim();
      if (!l) continue;
      const [a, n] = l.split(':');
      const ate = Number((a ?? '').trim());
      const nota = Number((n ?? '').trim());
      if (!Number.isFinite(ate) || !Number.isFinite(nota)) {
        throw new Error(`"${campo.rotulo}": esperado ate:nota, veio ${l}`);
      }
      bandas.push({ ate, nota });
    }
    if (!bandas.length) throw new Error(`"${campo.rotulo}" está vazio`);
    return bandas;
  }
  return cru;
}
