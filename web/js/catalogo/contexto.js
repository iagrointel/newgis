/* plat · catálogo — estado da tela Conteúdo (loja da base, js/base/estado.js). Um só lugar para aba, vista, busca,
   ordenação, pasta, filtros laterais, itens carregados, cursor e seleção; os módulos assinam por chave. */
import { criarLoja } from '../base/estado.js';
import { LIMITES } from './formato.js';

export const FILTROS_VAZIOS = () => ({
  tipo: [], familia: [], dono_id: [], tags: [], categoria: [], status: [], acesso: [], origem: '',
  criado_de: '', criado_ate: '', modificado_de: '', modificado_ate: '', bbox: '',
  licenca: [], procedencia_min: '',   // item L0-09-a: licença registrada e pontuação mínima de procedência
});

export const ctx = criarLoja({
  usuario: null,
  tipos: [],                      // GET /api/tipos-item
  aba: 'meus',                    // meus | favoritos | grupos | inquilino | lixeira
  vista: 'tabela',                // tabela | lista | grade
  q: '',
  ordenar: '',                    // '' = padrão (relevância com q; modificado_em:desc sem q)
  pastaId: null,
  grupoId: null,
  filtros: FILTROS_VAZIOS(),
  itens: [],
  total: 0,
  cursor: null,
  aproximado: false,
  carregando: false,
  selecionados: [],
  itemAberto: null,
});

export function tipoDe(nome) { return (ctx.ler('tipos') || []).find((x) => x.nome === nome) || null; }

export function rotuloTipo(nome) { const x = tipoDe(nome); return x ? x.rotulo : (nome || ''); }

/* parâmetros de GET /api/itens para o estado atual (sem cursor; quem pagina acrescenta) */
export function parametrosLista() {
  const e = ctx.obter();
  const p = { limite: LIMITES.pagina };
  if (e.aba === 'meus') p.meus = 'true';
  else if (e.aba === 'favoritos') p.favoritos = 'true';
  else if (e.aba === 'grupos') { if (e.grupoId) p.grupo_id = e.grupoId; }
  else if (e.aba === 'inquilino') p.acesso = ['inquilino', 'publico'];
  if (e.pastaId) p.pasta_id = e.pastaId;
  if (e.q) p.q = e.q;
  if (e.ordenar) { const [campo, direcao] = e.ordenar.split(':'); p.ordenar = campo; if (direcao) p.direcao = direcao; }
  const f = e.filtros;
  for (const k of ['tipo', 'familia', 'dono_id', 'tags', 'categoria', 'status', 'licenca']) if (f[k].length) p[k] = f[k];
  if (f.acesso.length && e.aba !== 'inquilino') p.acesso = f.acesso;
  for (const k of ['origem', 'criado_de', 'criado_ate', 'modificado_de', 'modificado_ate', 'bbox', 'procedencia_min']) if (f[k]) p[k] = f[k];
  return p;
}

export function filtrosAtivos() {
  const f = ctx.ler('filtros');
  return Object.entries(f).filter(([, v]) => (Array.isArray(v) ? v.length : v)).length;
}

export function definirFiltro(chave, valor) {
  ctx.definir({ filtros: { ...ctx.ler('filtros'), [chave]: valor } });
}

export function alternarFiltro(chave, valor) {
  const atual = ctx.ler('filtros')[chave] || [];
  const s = String(valor);
  definirFiltro(chave, atual.map(String).includes(s) ? atual.filter((x) => String(x) !== s) : [...atual, valor]);
}

export function limparFiltros() { ctx.definir({ filtros: FILTROS_VAZIOS() }); }

/* preferência de vista guardada no navegador (falha silenciosa: privado, bloqueado) */
export function lerVistaGuardada() { try { return localStorage.getItem('plat_conteudo_vista') || ''; } catch { return ''; } }
export function guardarVista(v) { try { localStorage.setItem('plat_conteudo_vista', v); } catch { /* sem armazenamento: segue */ } }

export function selecionado(id) { return ctx.ler('selecionados').includes(id); }
export function alternarSelecao(id, forcar) {
  const s = ctx.ler('selecionados');
  const tem = s.includes(id);
  const querer = forcar === undefined ? !tem : !!forcar;
  if (querer && !tem) { if (s.length >= LIMITES.lote) return false; ctx.definir({ selecionados: [...s, id] }); }
  else if (!querer && tem) ctx.definir({ selecionados: s.filter((x) => x !== id) });
  return true;
}
export function limparSelecao() { if (ctx.ler('selecionados').length) ctx.definir({ selecionados: [] }); }

/* substitui/insere um item na lista carregada (depois de editar no painel) */
export function atualizarItemNaLista(item) {
  const itens = ctx.ler('itens');
  const i = itens.findIndex((x) => x.id === item.id);
  if (i < 0) return;
  const novos = itens.slice();
  novos[i] = { ...itens[i], ...item };
  ctx.definir({ itens: novos });
}

export function removerItemDaLista(id) {
  const itens = ctx.ler('itens');
  if (!itens.some((x) => x.id === id)) return;
  ctx.definir({ itens: itens.filter((x) => x.id !== id), total: Math.max(0, ctx.ler('total') - 1), selecionados: ctx.ler('selecionados').filter((x) => x !== id) });
}
