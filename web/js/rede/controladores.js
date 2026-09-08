/* plat — tela /redes/controladores (item L4-04-a-controladores-e-tiers): a tabela de subredes da rede
   escolhida (tier, controladores, estado limpa/suja, resumo) e a FICHA de um controlador — qual dispositivo,
   qual terminal, em que tier, de que subrede, e o nó que ele ocupa na topologia corrente. A ficha traz as
   duas ações do ciclo de vida: atualizar a subrede (ela volta a limpa) e remover o controlador.
   Item L4-04-b: a tabela ganha o comprimento da linha agregada da subrede, o link de exportação e o botão
   que enfileira a atualização em LOTE das subredes sujas (é job: a resposta traz o identificador do
   trabalho, e quem acompanha é a tela de Trabalhos). */
import { obter, enviar, apagar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

await carregar();
const usuario = await exigirSessao({ privilegio: 'rede.editar' });
if (usuario) iniciar();
pronto();

async function redes() {
  const r = await obter('/api/rede?limite=200');
  return r.status === 200 ? (r.json.itens || []) : [];
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/controladores' });
  cabecalho(t('controladores.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const lista = await redes();

  const selRede = h('select', { id: 'rede', 'aria-label': t('controladores.rede') },
    h('option', { value: '' }, t('controladores.escolha')),
    ...lista.map((i) => h('option', { value: i.id }, i.nome)));
  const tabela = h('div', { id: 'subredes', class: 'resultado' });
  const ficha = h('div', { id: 'ficha', class: 'resultado', hidden: true });

  selRede.addEventListener('change', () => { ficha.hidden = true; desenharSubredes(); });

  async function desenharSubredes() {
    limpar(tabela);
    ficha.hidden = true;
    if (!selRede.value) return;
    const r = await obter(`/api/rede/${selRede.value}/subredes?limite=500`);
    if (r.status !== 200) { aviso.mostrar(t('controladores.falhou'), 'erro'); return; }
    const itens = r.json.itens || [];
    tabela.dataset.total = String(itens.length);
    if (!itens.length) { tabela.append(h('p', { class: 'ajuda' }, t('controladores.sem_subrede'))); return; }
    const corpo = h('tbody', {}, ...itens.map((s) => h('tr', { 'data-subrede': s.id },
      h('td', {}, s.nome),
      h('td', {}, `${s.tier_nome} (${s.tier_tipo})`),
      h('td', { class: `estado-${s.estado}` }, s.estado),
      h('td', {}, String((s.resumo && s.resumo.elementos) ?? '—')),
      h('td', { class: 'comprimento' },
        s.resumo && s.resumo.comprimento_m !== undefined
          ? String(s.resumo.comprimento_m) : t('controladores.sem_comprimento')),
      h('td', {}, ...s.controladores.map((c) => h('button', {
        type: 'button', class: 'controlador', 'data-controlador': c.id,
        onclick: () => desenharFicha(c.id),
      }, c.nome))),
      h('td', {}, h('a', {
        class: 'exportar', 'data-subrede-nome': s.nome,
        href: `/api/rede/${selRede.value}/subrede/${encodeURIComponent(s.nome)}/exportar?tier=${s.tier}`,
      }, t('controladores.exportar'))))));
    tabela.append(h('table', { class: 'grade' },
      h('thead', {}, h('tr', {},
        h('th', {}, t('controladores.subrede')), h('th', {}, t('controladores.tier')),
        h('th', {}, t('controladores.estado')), h('th', {}, t('controladores.elementos')),
        h('th', {}, t('controladores.comprimento')),
        h('th', {}, t('controladores.controladores')), h('th', {}, t('controladores.exportar')))),
      corpo));
  }

  async function desenharFicha(id) {
    const r = await obter(`/api/rede/${selRede.value}/controlador/${id}`);
    if (r.status !== 200) { aviso.mostrar(t('controladores.falhou'), 'erro'); return; }
    const c = r.json;
    limpar(ficha);
    ficha.dataset.controladorId = c.id;
    const atualizar = h('button', { id: 'atualizar-subrede', type: 'button', class: 'primario' },
      t('controladores.atualizar'));
    atualizar.addEventListener('click', async () => {
      const a = await enviar(`/api/rede/${selRede.value}/subredes/${c.subrede_id}/atualizar`, {});
      if (a.status !== 200) { aviso.mostrar((a.json && a.json.mensagem) || t('controladores.falhou'), 'erro'); return; }
      aviso.mostrar(t('controladores.atualizada'), 'ok');
      await desenharSubredes();
    });
    const remover = h('button', { id: 'remover-controlador', type: 'button' }, t('controladores.remover'));
    remover.addEventListener('click', async () => {
      const d = await apagar(`/api/rede/${selRede.value}/controlador/${c.id}`);
      if (d.status !== 204) { aviso.mostrar(t('controladores.falhou'), 'erro'); return; }
      aviso.mostrar(t('controladores.removido'), 'ok');
      await desenharSubredes();
    });
    ficha.append(
      h('h2', { id: 'f-nome' }, c.nome),
      h('dl', {},
        h('dt', {}, t('controladores.subrede')), h('dd', { id: 'f-subrede' }, c.subrede),
        h('dt', {}, t('controladores.tier')), h('dd', { id: 'f-tier' }, `${c.tier_nome} (${c.tier_tipo})`),
        h('dt', {}, t('controladores.tipo')), h('dd', { id: 'f-tipo' }, c.tipo_nome || t('controladores.sem_dispositivo')),
        h('dt', {}, t('controladores.terminal')), h('dd', { id: 'f-terminal' }, c.terminal === null ? '—' : String(c.terminal)),
        h('dt', {}, t('controladores.papel')), h('dd', { id: 'f-papel' }, c.papel),
        h('dt', {}, t('controladores.origem')), h('dd', { id: 'f-origem' }, c.origem),
        h('dt', {}, t('controladores.no')), h('dd', { id: 'f-no' }, c.no_id || t('controladores.sem_no'))),
      h('div', { class: 'acoes' }, atualizar, remover));
    ficha.hidden = false;
  }

  const lote = h('button', { id: 'atualizar-sujas', type: 'button' }, t('controladores.atualizar_sujas'));
  lote.addEventListener('click', async () => {
    if (!selRede.value) return;
    const r = await enviar(`/api/rede/${selRede.value}/subredes/atualizar`, {});
    if (r.status !== 202) { aviso.mostrar((r.json && r.json.mensagem) || t('controladores.falhou'), 'erro'); return; }
    aviso.mostrar(t('controladores.lote_enfileirado').replace('{job}', r.json.job_id), 'ok');
  });

  principal.append(
    h('p', { class: 'ajuda' }, t('controladores.ajuda')),
    h('div', { class: 'formulario' }, h('label', { for: 'rede' }, t('controladores.rede')), selRede),
    h('div', { class: 'acoes' }, lote),
    tabela, ficha);
}
