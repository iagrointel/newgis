/* plat — trechos comuns das telas de admin: filtros de lista, seletor de papéis, estado de usuário, erro por campo. */
import { obter } from '../base/api.js';
import { notificar } from '../base/componentes.js';
import { h, limpar, marcador } from '../base/dom.js';
import { tem } from '../base/estado.js';
import { t, formatarData, diasAte } from '../base/i18n.js';

/* <label>rótulo<select|input></label> para a barra de filtros; devolve {el, input} */
export function filtro(rotulo, input) {
  return { el: h('label', {}, rotulo, input), input };
}

export function seletor(nome, opcoes, padrao) {
  const s = h('select', { name: nome });
  for (const o of opcoes) s.append(h('option', { value: o.valor }, o.rotulo));
  if (padrao !== undefined) s.value = String(padrao);
  return s;
}

export const PERFIS = ['admin', 'editor', 'visualizador', 'campo'];
export const opcoesPerfil = () => PERFIS.map((p) => ({ valor: p, rotulo: t(`perfil.${p}`) }));

/* papéis personalizados do inquilino (GET /api/papeis) como opções de select; a primeira é "perfil inteiro" */
export async function opcoesPapel() {
  const r = await obter('/api/papeis');
  const lista = r.status === 200 && Array.isArray(r.json.personalizados) ? r.json.personalizados : [];
  return [{ valor: '', rotulo: t('papel.perfil_inteiro') }, ...lista.map((p) => ({ valor: String(p.id), rotulo: `${p.nome} (${t(`perfil.${p.perfil_minimo}`)})` }))];
}

export function estadoUsuario(u) {
  if (u.ativo === false) return marcador(t('usuario.desabilitado'), 'falha');
  if (u.bloqueado_ate && diasAte(u.bloqueado_ate) !== null && new Date(u.bloqueado_ate) > new Date()) return marcador(t('usuario.bloqueado'), 'atencao');
  return marcador(t('usuario.ativo'), 'ok');
}

export function simNao(v) { return v === undefined || v === null ? '—' : (v ? t('geral.sim') : t('geral.nao')); }

export function dataOuTraco(v) { return v ? formatarData(v) : '—'; }

/* traduz um código de erro da API para texto curto (tabela de recusas do lote, etc.) */
export function textoErro(codigo) {
  const chave = `erro_api.${codigo}`;
  const s = t(chave);
  return s === chave ? codigo : s;
}

/* ---------------------------------------------------------------- UX-06: estados de lista e evento registrado */

/* aplica a resposta de uma lista a <plat-estado> + <plat-tabela>: carregando antes do pedido (chamar com r=null),
   erro/negado pela resposta, vazio quando não há linhas (texto e ação opcionais), senão a tabela à vista */
export function estadoDeLista(estado, tabela, r, { vazio, acoes = [] } = {}) {
  if (!estado) return;
  if (r === null) { estado.carregando(); if (tabela) tabela.hidden = true; return; }
  if (r.status !== 200) { estado.erro(r); if (tabela) { tabela.hidden = true; tabela.linhas = []; } return; }
  const itens = Array.isArray(r.json) ? r.json : (r.json.itens || []);
  if (!itens.length) { estado.vazio(vazio, acoes); if (tabela) tabela.hidden = true; return; }
  estado.limpar();
  if (tabela) tabela.hidden = false;
}

/* portão do item UX-06: toda ação de escrita mostra o evento que ficou registrado. Lê o evento mais recente do
   inquilino (GET /api/eventos, só com org.log_ver); se ele nasceu nos últimos 20 s, mostra tipo, hora e ator com o
   caminho para /admin/log. Sem o privilégio ou sem evento recente, não mostra nada (nunca finge um registro). */
export async function eventoRegistrado(alvo = null) {
  if (!tem('org.log_ver')) return null;
  const desde = new Date(Date.now() - 20000).toISOString();
  const r = await obter(`/api/eventos?limite=1&desde=${encodeURIComponent(desde)}`);
  if (r.status !== 200) return null;
  const e = (r.json.itens || [])[0];
  if (!e) return null;
  const texto = t('admin.evento_registrado', { tipo: e.tipo, quando: formatarData(e.em), ator: e.ator?.login || t('admin.evento_sem_ator') });
  const link = h('a', { href: `/admin/log?aba=eventos&tipo=${encodeURIComponent(e.tipo)}` }, t('admin.evento_ver_log'));
  const n = alvo || document.getElementById('evento-registrado');
  if (n) {
    limpar(n);
    n.append(h('span', { class: 'marcador ok' }, t('admin.evento_marcador')), ' ', texto, ' · ', link);
    n.hidden = false;
  } else {
    notificar(`${texto}`, 'ok');
  }
  return e;
}
