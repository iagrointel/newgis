/* plat — tela /redes/continuidade (item L4-10-continuidade-dec-fec): o PAINEL da continuidade.

   A ANEEL apura DEC e FEC por CONJUNTO de unidades consumidoras; a BDGD traz o campo CONJ nos elementos
   da rede. A tela mostra, para cada conjunto que a rede declara, a série de 2020 a 2025: o valor apurado
   do ano, o limite daquele ano e a comparação entre os dois. Uma segunda tabela leva o mesmo número ao
   alimentador, ponderado pelas unidades consumidoras.

   ⛔ A comparação com o limite tem duas frases e só duas: "dentro do limite" e "acima do limite
   regulatório", sempre com o valor e o limite ao lado. Nenhum texto desta tela classifica infração —
   isso é do processo da agência, não desta leitura. Ano sem apurado aparece como "sem dado", com célula
   vazia: uma linha caindo até zero seria continuidade perfeita, o contrário do que o dado diz.

   Módulo ES sem build; cache resolvido por no-store no nginx: NUNCA ?v= nos imports. */
import { obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const ANO_DE = 2020;
const ANO_ATE = 2025;
const ACIMA = 'acima do limite regulatório';
const SEM_DADO = 'sem dado';

await carregar();
const usuario = await exigirSessao();
if (usuario) iniciar();
pronto();

async function redes() {
  const r = await obter('/api/rede?limite=200');
  return r.status === 200 ? (r.json.itens || []) : [];
}

function numero(v) {
  return v === null || v === undefined ? '' : String(v);
}

function classeDaSituacao(situacao) {
  if (situacao === ACIMA) return 'acima';
  if (situacao === SEM_DADO) return 'sem-dado';
  return 'dentro';
}

function tabelaSerie(painel, indicador) {
  const cabeca = h('tr', {}, h('th', { scope: 'col' }, t('continuidade.conjunto')),
    ...painel.anos.map((a) => h('th', { scope: 'col' }, String(a))),
    h('th', { scope: 'col' }, t('continuidade.anos_acima')));
  const corpo = painel.itens.map((item) => {
    const serie = item.series[indicador];
    return h('tr', { 'data-conjunto': String(item.conjunto_id) },
      h('th', { scope: 'row' },
        `${item.conjunto_id}${item.conjunto_nome ? ` — ${item.conjunto_nome}` : ''}`),
      ...painel.anos.map((ano, i) => {
        const situacao = serie.situacao[i];
        const apurado = serie.apurado[i];
        const limite = serie.limite[i];
        return h('td', {
          class: `continuidade-celula ${classeDaSituacao(situacao)}`,
          'data-situacao': situacao,
          'data-ano': String(ano),
          title: `${t('continuidade.apurado')}: ${numero(apurado)} · ${t('continuidade.limite')}: `
            + `${numero(limite)} · ${situacao}`,
        }, apurado === null ? t('continuidade.sem_dado') : `${apurado} / ${numero(limite)}`);
      }),
      h('td', {}, String(item.anos_acima_do_limite[indicador])));
  });
  return h('table', { class: 'tabela', id: `serie-${indicador.toLowerCase()}` },
    h('caption', {}, `${indicador} — ${painel.unidades[indicador]}`),
    h('thead', {}, cabeca), h('tbody', {}, ...corpo));
}

function tabelaAlimentadores(dados) {
  if (!dados.itens.length) return h('p', { class: 'ajuda' }, t('continuidade.sem_alimentador'));
  return h('table', { class: 'tabela', id: 'alimentadores' },
    h('caption', {}, `${t('continuidade.alimentadores')} — ${dados.ano}`),
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, t('continuidade.alimentador')),
      h('th', { scope: 'col' }, 'DEC'), h('th', { scope: 'col' }, 'FEC'),
      h('th', { scope: 'col' }, t('continuidade.uc')),
      h('th', { scope: 'col' }, t('continuidade.uc_sem_dado')))),
    h('tbody', {}, ...dados.itens.map((it) => h('tr', { 'data-alimentador': it.alimentador },
      h('th', { scope: 'row' }, it.alimentador),
      ...['DEC', 'FEC'].map((ind) => h('td', {
        class: `continuidade-celula ${classeDaSituacao(it.indicadores[ind].situacao)}`,
        'data-situacao': it.indicadores[ind].situacao,
      }, it.indicadores[ind].apurado_ponderado === null ? t('continuidade.sem_dado')
        : `${it.indicadores[ind].apurado_ponderado} / `
          + `${numero(it.indicadores[ind].limite_ponderado)}`)),
      h('td', {}, String(it.n_uc)),
      h('td', {}, String(it.indicadores.DEC.uc_sem_dado))))));
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/continuidade' });
  cabecalho(t('continuidade.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const lista = await redes();

  const selRede = h('select', { id: 'rede', 'aria-label': t('continuidade.rede') },
    h('option', { value: '' }, t('continuidade.escolha')),
    ...lista.map((i) => h('option', { value: i.id }, i.nome)));
  const saida = h('div', { id: 'painel', class: 'resultado' });
  const nota = h('p', { class: 'ajuda', id: 'base-normativa' }, '');

  async function desenhar() {
    limpar(saida);
    nota.textContent = '';
    if (!selRede.value) return;
    const r = await obter(
      `/api/rede/${selRede.value}/continuidade/painel?ano_de=${ANO_DE}&ano_ate=${ANO_ATE}`);
    if (r.status !== 200) { aviso.mostrar(t('continuidade.falhou'), 'erro'); return; }
    const painel = r.json;
    saida.dataset.total = String(painel.total);
    if (!painel.total) { saida.append(h('p', { class: 'ajuda' }, t('continuidade.vazio'))); return; }
    nota.textContent = painel.limite_base_normativa;
    saida.append(tabelaSerie(painel, 'DEC'), tabelaSerie(painel, 'FEC'));
    const a = await obter(`/api/rede/${selRede.value}/continuidade/alimentadores?ano=${ANO_ATE}`);
    if (a.status === 200) saida.append(tabelaAlimentadores(a.json));
  }

  selRede.addEventListener('change', desenhar);
  principal.append(h('p', { class: 'ajuda' }, t('continuidade.ajuda')),
    h('label', { for: 'rede' }, t('continuidade.rede')), selRede, saida, nota);
}
