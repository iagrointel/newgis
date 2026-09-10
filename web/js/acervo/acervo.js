/* plat · acervo — entrada da tela /acervo (item L6-01-h-frescor-verificacao).
   Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports (duas URLs do mesmo
   módulo = duas instâncias, a tela morre — regra da casa).

   Mostra as camadas do registro do acervo (`plat.acervo_camada`, item L6-01-a) com o estado de VERIFICAÇÃO
   calculado por `plat.v_acervo_camada_frescor`: quem está com "verificação vencida" e por quê, a última
   contagem exata, a variação contra a verificação anterior e o histórico das 12 verificações que o job
   mantém por camada. Nenhum número é calculado aqui: tudo vem da API, que lê a view. */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma, formatarData } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';
import { AVISO_VENCIDA, selo } from './frescor.js';

let saindo = false;
const s = { camadas: [], usuario: null };

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(id, texto, tipo = 'erro') {
  const n = document.getElementById(id);
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

function numero(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('pt-BR');
}

function celulaContagem(c) {
  if (c.contagem_estado === 'contado') return h('span', {}, numero(c.linhas_exatas));
  if (c.contagem_estado === 'nao_contado_no_prazo') {
    return h('span', { class: 'marcador atencao', title: 'COUNT(*) não terminou no prazo de 25 s' },
      'não contado no prazo');
  }
  if (c.contagem_estado === 'erro') return h('span', { class: 'marcador falha' }, 'erro na contagem');
  return h('span', { class: 'ajuda' }, 'ainda não contada');
}

function celulaVariacao(c) {
  if (c.variacao_pct === null || c.variacao_pct === undefined) {
    return h('span', { class: 'ajuda', title: 'sem as duas contagens não há variação' }, '—');
  }
  const texto = `${c.variacao_pct > 0 ? '+' : ''}${c.variacao_pct.toFixed(2).replace('.', ',')} %`;
  return h('span', { class: c.mudanca_relevante ? 'marcador atencao' : '' }, texto);
}

async function verHistorico(c) {
  const dialogo = porId('dialogo');
  const r = await api.obter(`/api/acervo/camadas/${c.acervo_camada_id.split('/').map(encodeURIComponent).join('/')}/verificacoes`);
  if (r.status !== 200) {
    aviso('camadas-aviso', `não foi possível ler o histórico de ${c.acervo_camada_id}: ${api.mensagemDe(r)}`);
    return;
  }
  const itens = r.json.verificacoes || [];
  const corpo = h('div', {},
    h('p', {}, `${c.schema_nome}.${c.tabela} — ${itens.length} verificação(ões) no histórico (o job mantém as 12 mais recentes)`),
    itens.length
      ? h('table', { class: 'tabela' },
          h('thead', {}, h('tr', {}, h('th', {}, 'quando'), h('th', {}, 'contagem'), h('th', {}, 'linhas'),
            h('th', {}, 'variação'), h('th', {}, 'hash'))),
          h('tbody', {}, ...itens.map((v) => h('tr', {},
            h('td', {}, formatarData(v.verificada_em)),
            h('td', {}, v.contagem_estado),
            h('td', {}, v.linhas_exatas === null || v.linhas_exatas === undefined ? '—' : numero(v.linhas_exatas)),
            h('td', {}, v.variacao_pct === null || v.variacao_pct === undefined
              ? '—' : `${v.variacao_pct.toFixed(2).replace('.', ',')} %`),
            h('td', {}, v.hash_estado)))))
      : h('p', { class: 'ajuda' }, 'nenhuma verificação registrada ainda para esta camada'));
  dialogo.abrir({ titulo: 'histórico de verificação', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
}

function linhaCamada(c) {
  const btHistorico = h('button', { type: 'button', class: 'pequeno' }, 'histórico');
  btHistorico.addEventListener('click', () => verHistorico(c));
  return h('tr', { 'data-camada': c.acervo_camada_id, 'data-vencida': c.verificacao_vencida ? '1' : '0' },
    h('td', {}, h('code', {}, `${c.schema_nome}.${c.tabela}`)),
    h('td', {}, c.fonte_nome || c.fonte_id),
    h('td', {}, selo(c, h)),
    h('td', {}, celulaContagem(c)),
    h('td', {}, celulaVariacao(c)),
    h('td', {}, c.verificada_em ? formatarData(c.verificada_em) : h('span', { class: 'ajuda' }, 'nunca')),
    h('td', {}, btHistorico));
}

async function carregarCamadas() {
  aviso('camadas-aviso', '');
  const filtro = porId('filtro-vencida').value;
  const busca = filtro === '' ? '' : `?vencida=${filtro}`;
  const r = await api.obter(`/api/acervo/camadas${busca}`);
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('camadas-aviso', `não foi possível carregar as camadas do acervo (${api.mensagemDe(r)})`);
    return;
  }
  s.camadas = r.json.itens || [];
  porId('camadas-total').textContent = `(${r.json.total})`;
  porId('camadas-vencidas').textContent = r.json.vencidas
    ? `${r.json.vencidas} de ${r.json.total} com ${AVISO_VENCIDA}`
    : `nenhuma camada com ${AVISO_VENCIDA} neste recorte`;
  const corpo = porId('camadas-corpo');
  limpar(corpo);
  if (!s.camadas.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '7', class: 'ajuda' },
      'nenhuma camada neste recorte — o registro é montado por scripts/acervo_sync.py')));
    return;
  }
  for (const c of s.camadas) corpo.append(linhaCamada(c));
}

async function carregarMudancas() {
  aviso('mudancas-aviso', '');
  const r = await api.obter('/api/acervo/frescor/mudancas');
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('mudancas-aviso', `não foi possível carregar o relatório de mudanças (${api.mensagemDe(r)})`);
    return;
  }
  const itens = r.json.itens || [];
  porId('mudancas-total').textContent = `(${r.json.total})`;
  const corpo = porId('mudancas-corpo');
  limpar(corpo);
  if (!itens.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '5', class: 'ajuda' },
      'nenhuma contagem variou mais de 5 % desde a verificação anterior')));
    return;
  }
  for (const m of itens) {
    corpo.append(h('tr', { 'data-camada': m.acervo_camada_id },
      h('td', {}, h('code', {}, `${m.schema_nome}.${m.tabela}`)),
      h('td', {}, numero(m.linhas_anteriores)),
      h('td', {}, numero(m.linhas_exatas)),
      h('td', {}, h('span', { class: 'marcador atencao' },
        `${m.variacao_pct > 0 ? '+' : ''}${m.variacao_pct.toFixed(2).replace('.', ',')} %`)),
      h('td', {}, formatarData(m.verificada_em))));
  }
}

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/acervo' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Acervo');
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { saindo = true; irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
    const destino = caminhoPendencia(usuario.pendencias);
    if (destino) { saindo = true; location.replace(destino); return; }
  } else {
    aviso('aviso', `dados da sessão indisponíveis (GET /api/eu devolveu ${r.status}); a tela segue com a API do acervo`, 'atencao');
  }
  s.usuario = usuario;
  layout(usuario);
  porId('filtro-vencida').addEventListener('change', () => carregarCamadas());
  await carregarCamadas();
  await carregarMudancas();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
