/* plat — trechos comuns das telas de admin: filtros de lista, seletor de papéis, estado de usuário, erro por campo. */
import { obter } from '../base/api.js';
import { h, marcador } from '../base/dom.js';
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
