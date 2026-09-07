/* plat · AMC — item L3-01-f-explicacao: entrada da tela /amc/explicacao/<execucao_id>/<unidade_id>.
   "por que esta unidade tem nota N": busca GET /api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao,
   monta a tabela fator → valor bruto → transformação → favorabilidade → peso → contribuição e o resumo (soma,
   veto, cobertura). Sem `?v=` no import (no-store no nginx resolve o cache). */
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

function montarTabela(exp) {
  const corpo = document.getElementById('tabela-corpo');
  limpar(corpo);
  for (const f of exp.fatores) {
    const tr = h('tr', f.presente === false ? {} : {});
    if (exp.vetado) tr.setAttribute('data-vetado', '1');
    tr.append(
      h('td', {}, `${f.nome} (${f.fator_id})`),
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
  montarObservacoes(resp.json);
  pronto();
}

principal();
