/* plat — tela /campo/filas (item L2-07-campo): lista as filas de trabalho do inquilino e cria uma nova a
   partir de uma camada vetorial hospedada do catálogo — o alvo de campo é sempre uma feição de camada do
   catálogo (camada_id + globalid), nunca uma tabela paralela. Porta o conceito de `fila`/`fila_item` do SIG
   de campo que a casa já opera (SIG anterior, web/js/pages.js::painelFilas). */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

await carregar();
const usuario = await exigirSessao({ privilegio: 'campo.coletar' });
if (usuario) iniciar();
pronto();

async function camadasVetoriais() {
  const r = await obter('/api/mapa/camadas');
  if (r.status !== 200) return [];
  return (r.json.camadas || []).filter((c) => c.geometria);
}

async function feicoesDaCamada(camadaId) {
  const r = await obter(`/api/campo/camadas/${camadaId}/globalids?limite=500`);
  return r.status === 200 ? r.json.feicoes || [] : [];
}

async function listarFilas() {
  const r = await obter('/api/campo/filas');
  return r.status === 200 ? r.json.filas || [] : [];
}

function tabelaFilas(filas) {
  if (!filas.length) return h('p', { class: 'vazio' }, t('campo.filas.vazio'));
  return h('div', { class: 'tabela-rolagem' },
    h('table', { class: 'tabela' },
      h('thead', {}, h('tr', {},
        h('th', {}, t('campo.filas.coluna_titulo')),
        h('th', {}, t('campo.filas.coluna_alvos')),
        h('th', {}, t('campo.filas.coluna_visitados')),
        h('th', {}, t('campo.filas.coluna_roteiros')),
        h('th', {}, t('campo.filas.coluna_criada')),
        h('th', {}))),
      h('tbody', {}, ...filas.map((f) => h('tr', {},
        h('td', {}, f.titulo),
        h('td', { class: 'num' }, String(f.n_alvos)),
        h('td', { class: 'num' }, String(f.n_visitados)),
        h('td', { class: 'num' }, String(f.n_roteiros)),
        h('td', {}, formatarData(f.criado_em)),
        h('td', {}, h('a', { href: `/campo/filas/${f.id}` }, t('campo.filas.abrir'))))))));
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/campo/filas' });
  cabecalho(t('campo.filas.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const camadas = await camadasVetoriais();

  const selCamada = h('select', { id: 'camada', 'aria-label': t('campo.filas.camada'), disabled: camadas.length === 0 },
    h('option', { value: '' }, t('campo.filas.escolha_camada')),
    ...camadas.map((c) => h('option', { value: c.id }, c.titulo)));
  const vazioCamada = camadas.length ? null : h('p', { class: 'vazio' }, t('campo.filas.sem_camada'));
  const titulo = h('input', { id: 'titulo-fila', type: 'text', maxlength: '250' });
  const listaFeicoes = h('div', { id: 'lista-feicoes', class: 'lista-selecao' });
  const marcarTodas = h('button', { type: 'button', class: 'pequeno', id: 'marcar-todas' }, t('campo.filas.marcar_todas'));
  const desmarcarTodas = h('button', { type: 'button', class: 'pequeno', id: 'desmarcar-todas' }, t('campo.filas.desmarcar_todas'));
  const botaoCriar = h('button', { id: 'criar-fila', class: 'primario', type: 'button', disabled: true }, t('campo.filas.criar'));

  selCamada.addEventListener('change', async () => {
    limpar(listaFeicoes);
    botaoCriar.disabled = true;
    if (!selCamada.value) return;
    const item = camadas.find((c) => c.id === selCamada.value);
    if (item && !titulo.value) titulo.value = item.titulo;
    listaFeicoes.append(h('p', { class: 'ajuda' }, t('campo.filas.carregando_feicoes')));
    const feicoes = await feicoesDaCamada(selCamada.value);
    limpar(listaFeicoes);
    for (const f of feicoes) {
      const cx = h('input', { type: 'checkbox', value: f.globalid, checked: true });
      listaFeicoes.append(h('label', { class: 'linha-selecao' }, cx, ' ', f.titulo || f.globalid));
    }
    botaoCriar.disabled = feicoes.length === 0;
  });
  marcarTodas.addEventListener('click', () => {
    listaFeicoes.querySelectorAll('input[type=checkbox]').forEach((cx) => { cx.checked = true; });
  });
  desmarcarTodas.addEventListener('click', () => {
    listaFeicoes.querySelectorAll('input[type=checkbox]').forEach((cx) => { cx.checked = false; });
  });

  botaoCriar.addEventListener('click', async () => {
    const globalids = [...listaFeicoes.querySelectorAll('input[type=checkbox]:checked')].map((cx) => cx.value);
    if (!selCamada.value || !globalids.length) return;
    botaoCriar.disabled = true;
    const r = await enviar('/api/campo/filas', {
      titulo: titulo.value || t('campo.filas.nova'), camada_id: selCamada.value, globalids,
    });
    botaoCriar.disabled = false;
    if (r.status !== 201) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    aviso.mostrar(t('campo.filas.criada'), 'ok');
    location.href = `/campo/filas/${r.json.id}`;
  });

  const filas = await listarFilas();
  principal.append(
    h('details', { open: filas.length === 0 },
      h('summary', {}, t('campo.filas.nova')),
      h('p', { class: 'ajuda' }, t('campo.filas.ajuda')),
      h('div', { class: 'formulario' },
        h('label', { for: 'camada' }, t('campo.filas.camada')), selCamada, vazioCamada,
        h('label', { for: 'titulo-fila' }, t('campo.filas.titulo_campo')), titulo,
        h('div', { class: 'linha-botoes' }, marcarTodas, desmarcarTodas),
        listaFeicoes,
        botaoCriar)),
    tabelaFilas(filas),
  );
}
