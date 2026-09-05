/* plat · catálogo — transferência de dono com pré-checagem (ADR 0004 seção 10): busca o novo dono em
   /api/usuarios?q=, pede o plano com simular:true, mostra por item o que arrasta e o que falha (com a solução
   "adicionar aos grupos"), e só executa quando o plano está limpo ou o usuário aceita o parcial. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import * as api from './api.js';
import { elipse } from './formato.js';

function dialogo() { return document.getElementById('painel-transferir') || document.body.appendChild(h('plat-dialogo', { id: 'painel-transferir' })); }

export async function abrirTransferencia(ids, { aoTerminar = () => {} } = {}) {
  const d = dialogo();
  const corpo = h('div', { class: 'transferir' });
  const aviso = h('plat-aviso');
  const busca = h('plat-busca', { rotulo: t('catalogo.transferir_buscar'), atraso: '300' });
  const resultados = h('ul', { class: 'lista-relacoes', id: 'transferir-resultados' });
  const planoArea = h('div', { class: 'dependencias', id: 'transferir-plano' });
  const opAdicionar = h('input', { type: 'checkbox', id: 'transferir-adicionar' });
  const opPastas = h('select', { id: 'transferir-pastas' }, h('option', { value: 'manter' }, t('catalogo.transferir_pastas_manter')), h('option', { value: 'unica' }, t('catalogo.transferir_pastas_unica')));
  let novoDono = null;
  let plano = null;
  const executarBt = h('button', { type: 'button', class: 'primario', id: 'transferir-executar', disabled: true }, t('catalogo.transferir_executar'));
  const parcialBt = h('button', { type: 'button', id: 'transferir-parcial', hidden: true }, t('catalogo.transferir_parcial'));

  async function simular() {
    if (!novoDono) return;
    limpar(planoArea);
    planoArea.append(h('p', { class: 'fraco' }, t('catalogo.carregando')));
    try {
      plano = await api.transferir({ ids, novo_dono_id: novoDono.id, simular: true, pastas: opPastas.value, adicionar_aos_grupos: opAdicionar.checked });
    } catch (e) { limpar(planoArea); aviso.erro(e.message); plano = null; executarBt.disabled = true; parcialBt.hidden = true; return; }
    aviso.limpar();
    mostrarPlano();
  }

  function mostrarPlano() {
    limpar(planoArea);
    const linhas = plano.plano || [];
    const tab = h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, t('catalogo.col_titulo')), h('th', {}, t('catalogo.transferir_arrasta')), h('th', {}, t('catalogo.transferir_falhas')))));
    const tb = h('tbody');
    for (const l of linhas) {
      const falhas = (l.falhas || []).map((f) => h('div', {}, t(`catalogo.falha_${f.codigo}`) === `catalogo.falha_${f.codigo}` ? f.codigo : t(`catalogo.falha_${f.codigo}`), f.grupo ? ` (${f.grupo.nome})` : '', f.solucao === 'adicionar_aos_grupos' ? h('span', { class: 'fraco' }, ` · ${t('catalogo.transferir_solucao_grupos')}`) : null));
      tb.append(h('tr', {}, h('td', {}, elipse(l.titulo, 60)), h('td', {}, (l.arrasta || []).length ? t('catalogo.transferir_n_dependentes', { n: l.arrasta.length }) : '—'), h('td', {}, falhas.length ? falhas : h('span', { class: 'marcador ok' }, t('catalogo.ok')))));
    }
    tab.append(tb);
    planoArea.append(h('p', {}, t('catalogo.transferir_resumo', { total: plano.total ?? linhas.length, falhas: plano.com_falha ?? 0, dono: plano.novo_dono?.login || novoDono.login })), tab);
    const comFalha = (plano.com_falha ?? 0) > 0;
    executarBt.disabled = comFalha;
    parcialBt.hidden = !comFalha || (plano.total ?? linhas.length) <= (plano.com_falha ?? 0);
  }

  busca.addEventListener('buscar', async (e) => {
    limpar(resultados);
    if (!e.detail.q) return;
    try {
      const r = await api.usuariosBuscar(e.detail.q);
      for (const u of r.itens || []) {
        const b = h('button', { type: 'button', class: 'pequeno' }, t('catalogo.escolher'));
        b.addEventListener('click', () => { novoDono = u; limpar(resultados); resultados.append(h('li', {}, h('strong', {}, u.login), ' ', u.nome || '', u.ativo === false ? h('span', { class: 'marcador falha' }, t('usuario.desabilitado')) : null)); simular(); });
        resultados.append(h('li', {}, h('span', {}, u.login, ' ', h('span', { class: 'fraco' }, u.nome || '')), b));
      }
      if (!(r.itens || []).length) resultados.append(h('li', { class: 'oculto' }, t('grupo.ninguem_encontrado')));
    } catch (err) { aviso.erro(err.message); }
  });
  opAdicionar.addEventListener('change', simular);
  opPastas.addEventListener('change', simular);

  async function executar(forcarParcial) {
    executarBt.disabled = true; parcialBt.disabled = true;
    try {
      const r = await api.transferir({ ids, novo_dono_id: novoDono.id, simular: false, pastas: opPastas.value, adicionar_aos_grupos: opAdicionar.checked, ...(forcarParcial ? { forcar_parcial: true } : {}) });
      d.fechar('ok');
      document.getElementById('aviso')?.ok(t('catalogo.transferidos', { n: r.transferidos ?? 0, dono: novoDono.login }));
      aoTerminar(r);
    } catch (e) { aviso.erro(e.message); executarBt.disabled = false; parcialBt.disabled = false; }
  }
  executarBt.addEventListener('click', () => executar(false));
  parcialBt.addEventListener('click', () => executar(true));

  corpo.append(aviso, h('p', {}, t('catalogo.transferir_texto', { n: ids.length })), busca, resultados,
    h('div', { class: 'form compacto' }, h('div', { class: 'campo caixa' }, opAdicionar, h('label', { for: 'transferir-adicionar' }, t('catalogo.transferir_adicionar_grupos'))),
      h('div', { class: 'campo' }, h('label', { for: 'transferir-pastas' }, t('catalogo.transferir_pastas')), opPastas)),
    planoArea, h('div', { class: 'botoes' }, executarBt, parcialBt));
  await d.abrir({ titulo: t('catalogo.transferir_dono'), corpo, botoes: [{ id: 'cancelar', rotulo: t('acao.cancelar') }] });
}
