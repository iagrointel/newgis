/* plat · AMC — item L3-01-f-explicacao: entrada da tela /amc/explicacao/<execucao_id>/<unidade_id>.
   "por que esta unidade tem nota N": busca GET /api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao,
   monta a tabela fator → valor bruto → transformação → favorabilidade → peso → contribuição e o resumo (soma,
   veto, cobertura). Item L3-15-metadado-fator: cada linha abre a FICHA do fator no '?' (fonte e versão, unidade,
   direção, base, proxy com teto de peso, classe e âncora do peso, "o que não sustenta") e a página traz o cartão
   "proxies e âncoras" com as duas listas do relatório. Sem `?v=` no import (no-store no nginx resolve o cache). */
import { obter } from '../base/api.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { irParaLogin, marcarSessao } from '../auth/sessao.js';
import { h, limpar } from '../base/dom.js';

const ROTA = /^\/amc\/explicacao\/([^/]+)\/([^/]+)\/?$/;

function idsDaUrl() {
  const m = ROTA.exec(location.pathname);
  return m ? { execucaoId: decodeURIComponent(m[1]), unidadeId: decodeURIComponent(m[2]) } : null;
}

function numero(v, casas = 2) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(casas) : '—';
}

function montarResumo(exp) {
  const dl = document.getElementById('resumo-lista');
  limpar(dl);
  const linha = (rotulo, valor) => dl.append(h('dt', {}, rotulo), h('dd', {}, valor));
  linha('combinador', `${exp.combinador} — ${exp.combinador_descricao}`);
  linha('pesos', exp.aviso_pesos);
  linha('favorabilidade recalculada', numero(exp.favorabilidade_recalculada));
  linha('favorabilidade gravada', numero(exp.favorabilidade_gravada));
  linha('diferença (recalculada − gravada)', numero(exp.delta, 4));
  linha('cobertura', `${numero(exp.cobertura_recalculada * 100, 1)}% (gravada: ${numero((exp.cobertura_gravada ?? NaN) * 100, 1)}%)`);
  linha('vetado', exp.vetado ? `sim — ${exp.motivo_veto || 'sem motivo registrado'}` : 'não');
}

/* item L3-15: ficha do fator no '?'. `details` nativo — sem janela flutuante, sem biblioteca, e o conteúdo
   continua na página quando alguém imprime ou usa leitor de tela. */
function fichaDoFator(f) {
  const m = f.metadado || {};
  const dl = h('dl');
  const linha = (rotulo, valor) => { if (valor) dl.append(h('dt', {}, rotulo), h('dd', {}, valor)); };
  linha('critério', m.criterio);
  linha('fonte', m.fonte);
  linha('versão da fonte', m.versao_fonte || 'não declarada');
  linha('unidade', m.unidade);
  linha('direção', m.direcao === 'maior_melhor' ? 'maior é melhor' : 'menor é melhor');
  linha('base do fator', m.base ? `${m.base} — ${m.base_descricao}` : 'não declarada');
  linha('classe do peso', m.classe_peso ? `${m.classe_peso} — ${m.classe_peso_descricao}` : 'não declarada');
  linha('âncora do peso', m.ancora_peso ? `${m.ancora_peso} — ${m.ancora_peso_descricao}` : 'não declarada');
  if (m.proxy) {
    linha('proxy', m.proxy_descricao || 'declarado sem descrição');
    linha('teto de peso do proxy', `${numero(m.proxy_teto_peso * 100, 1)}% do peso do modelo`
      + (typeof m.fatia_do_peso === 'number' ? ` (hoje ${numero(m.fatia_do_peso * 100, 1)}%)` : ''));
  }
  linha('não sustenta', m.nao_sustenta);
  return h('details', { class: 'ficha' },
    h('summary', { title: `ficha do fator ${f.nome || f.fator_id}` }, '?'), dl);
}

function montarTabela(exp) {
  const corpo = document.getElementById('tabela-corpo');
  limpar(corpo);
  for (const f of exp.fatores) {
    const tr = h('tr', f.presente === false ? {} : {});
    if (exp.vetado) tr.setAttribute('data-vetado', '1');
    const proxy = f.metadado && f.metadado.proxy
      ? h('abbr', { class: 'marca-proxy', title: 'a camada mede grandeza diferente do gatilho' }, 'proxy')
      : null;
    tr.append(
      h('td', {}, fichaDoFator(f)),
      h('td', {}, `${f.nome} (${f.fator_id})`, proxy),
      h('td', {}, f.fonte || '—'),
      h('td', {}, numero(f.valor_bruto, 3)),
      h('td', {}, f.unidade_medida || '—'),
      h('td', {}, f.transformacao_tipo),
      h('td', {}, numero(f.favorabilidade_fator)),
      h('td', {}, numero(f.peso, 3)),
      h('td', {}, f.presente ? 'sim' : 'não'),
      h('td', {}, numero(f.contribuicao)),
      h('td', { class: 'observacao' }, f.observacao || (f.presente ? '' : 'ausente na extração')),
    );
    corpo.append(tr);
  }
}

/* item L3-15: o cartão "proxies e âncoras" do relatório. Um fator que mede grandeza diferente do gatilho e um
   peso escolhido, e não medido, ficam nomeados na página — não só dentro do '?'. */
function montarMetadado(exp) {
  const m = exp.metadado || {};
  document.getElementById('aviso-proxy').textContent = m.aviso_proxy || '';
  const proxies = document.getElementById('proxies-lista');
  limpar(proxies);
  for (const p of m.proxies || []) {
    proxies.append(h('li', {}, `${p.nome} (${p.fator_id}): ${p.descricao || 'sem descrição'} — teto `
      + `${numero(p.teto_peso * 100, 1)}% do peso do modelo, hoje ${numero(p.fatia_do_peso * 100, 1)}%.`));
  }
  document.getElementById('aviso-ancora').textContent = m.aviso_ancora || '';
  const ancoras = document.getElementById('ancoras-lista');
  limpar(ancoras);
  const a = m.ancoras || {};
  const rotulos = [['medida', 'peso ancorado em medida externa'], ['escolhida', 'peso escolhido por quem decide'],
                   ['nao_declarada', 'âncora não declarada']];
  for (const [chave, rotulo] of rotulos) {
    const ids = a[chave] || [];
    if (ids.length) ancoras.append(h('li', {}, `${rotulo}: ${ids.join(', ')}`));
  }
  const sem = m.fatores_sem_versao_de_fonte || [];
  document.getElementById('sem-versao').textContent = sem.length
    ? `fatores sem versão de fonte declarada: ${sem.join(', ')}.`
    : 'todos os fatores declaram a versão da fonte.';
}

function montarObservacoes(exp) {
  const secao = document.getElementById('observacoes-cartao');
  const lista = document.getElementById('observacoes-lista');
  limpar(lista);
  const obs = [...exp.observacoes];
  if (!exp.contribuicoes_aditivas) {
    obs.push('a soma das contribuições exibidas não é comparável à favorabilidade porque este combinador é fuzzy.');
  }
  secao.hidden = obs.length === 0;
  for (const o of obs) lista.append(h('li', {}, o));
}

async function principal() {
  const ids = idsDaUrl();
  const aviso = document.getElementById('aviso');
  const r = await obter('/api/eu');
  if (r.status === 401) {
    irParaLogin();
    return;
  }
  const usuario = r.status === 200 ? r.json : null;
  marcarSessao(!!usuario);
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/amc/explicacao' });

  if (!ids) {
    aviso.erro('URL inválida: use /amc/explicacao/<execucao_id>/<unidade_id>.');
    pronto();
    return;
  }

  const resp = await obter(`/api/amc/execucoes/${encodeURIComponent(ids.execucaoId)}/unidades/${encodeURIComponent(ids.unidadeId)}/explicacao`);
  if (resp.status !== 200) {
    aviso.erro((resp.json && resp.json.mensagem) || `não foi possível carregar a explicação (${resp.status})`);
    pronto();
    return;
  }
  montarResumo(resp.json);
  montarTabela(resp.json);
  montarMetadado(resp.json);
  montarObservacoes(resp.json);
  pronto();
}

principal();
