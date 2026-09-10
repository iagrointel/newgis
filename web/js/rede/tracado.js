/* plat — tela /redes/tracado (item L4-02-f-resultados-e-exportacao): traça, mostra o resultado como TABELA
   com as agregações ao lado (por tipo de ativo e por nível de tensão) e dá ao resultado as quatro saídas do
   portão do item — selecionar (a seleção vira a entrada das outras ações), salvar como camada (item de
   catálogo com procedência), exportar (CSV, GeoJSON ou GeoPackage) e o histórico dos últimos traçados, cada
   um com repetir. A tela não traça sozinha: ela monta o pedido e chama POST /api/rede/{id}/tracar. */
import { obter, enviar, chamar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const TIPOS = ['conectado', 'subrede', 'montante', 'jusante', 'lacos', 'isolados'];
const FORMATOS = ['csv', 'geojson', 'gpkg'];

await carregar();
const usuario = await exigirSessao();
if (usuario) iniciar();
pronto();

async function redes() {
  const r = await obter('/api/rede?limite=200');
  return r.status === 200 ? (r.json.itens || []) : [];
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/tracado' });
  cabecalho(t('tracadoresultado.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const lista = await redes();
  let ultimoPedido = null;   // o pedido do traçado que está na tela
  let selecionados = [];     // ids de feição marcados por "selecionar"

  const selRede = h('select', { id: 'rede', 'aria-label': t('tracadoresultado.rede') },
    h('option', { value: '' }, t('tracadoresultado.escolha')),
    ...lista.map((i) => h('option', { value: i.id }, i.nome)));
  const selTipo = h('select', { id: 'tipo' }, ...TIPOS.map((v) => h('option', { value: v }, v)));
  const campoFeicao = h('input', { id: 'feicao', maxlength: '36' });
  const campoTerminal = h('input', { id: 'terminal', type: 'number', min: '1', max: '8' });
  const selFormato = h('select', { id: 'formato' }, ...FORMATOS.map((v) => h('option', { value: v }, v)));
  const campoTitulo = h('input', { id: 'titulo', maxlength: '250' });

  const tabela = h('div', { id: 'resultado', class: 'resultado' });
  const painel = h('aside', { id: 'agregacoes', class: 'resultado' });
  const situacao = h('p', { id: 'situacao', class: 'ajuda' });
  const historico = h('div', { id: 'historico', class: 'resultado' });

  const btTracar = h('button', { type: 'button', id: 'tracar', onclick: () => tracar() }, t('tracadoresultado.tracar'));
  const btSelecionar = h('button', { type: 'button', id: 'selecionar', disabled: true, onclick: () => selecionar() },
    t('tracadoresultado.selecionar'));
  const btCamada = h('button', { type: 'button', id: 'camada', disabled: true, onclick: () => salvarCamada() },
    t('tracadoresultado.salvar_camada'));
  const btExportar = h('button', { type: 'button', id: 'exportar', disabled: true, onclick: () => exportar() },
    t('tracadoresultado.exportar'));

  function pedido() {
    const p = { tipo: selTipo.value, pontos_partida: [] };
    if (campoFeicao.value.trim()) {
      const ponto = { feicao_id: campoFeicao.value.trim() };
      if (campoTerminal.value) ponto.terminal = Number(campoTerminal.value);
      p.pontos_partida.push(ponto);
    }
    return p;
  }

  function desenharResultado(json) {
    limpar(tabela); limpar(painel);
    selecionados = [];
    const elementos = json.elementos || [];
    tabela.dataset.total = String(json.contagem ?? elementos.length);
    tabela.dataset.selecionados = '0';
    tabela.append(h('table', { class: 'grade' },
      h('thead', {}, h('tr', {},
        h('th', {}, t('tracadoresultado.col_id')), h('th', {}, t('tracadoresultado.col_tipo')),
        h('th', {}, t('tracadoresultado.col_grupo')), h('th', {}, t('tracadoresultado.col_terminal')))),
      h('tbody', {}, ...elementos.map((e) => h('tr', { 'data-feicao': e.feicao_id },
        h('td', { class: 'ident' }, e.feicao_id),
        h('td', {}, e.tipo_chave || '—'),
        h('td', {}, e.grupo || '—'),
        h('td', {}, e.terminal === null || e.terminal === undefined ? '—' : String(e.terminal)))))));
    const ag = json.agregacoes || { por_tipo: [], por_nivel: [] };
    painel.append(
      h('h2', {}, t('tracadoresultado.por_tipo')),
      h('table', { class: 'grade', id: 'por_tipo' }, h('tbody', {}, ...(ag.por_tipo || []).map((x) =>
        h('tr', { 'data-tipo': x.tipo || 'sem_tipo' },
          h('td', {}, x.tipo_nome || x.tipo || '—'), h('td', { class: 'contagem' }, String(x.contagem)))))),
      h('h2', {}, t('tracadoresultado.por_nivel')),
      h('table', { class: 'grade', id: 'por_nivel' }, h('tbody', {}, ...(ag.por_nivel || []).map((x) =>
        h('tr', { 'data-nivel': x.nivel || 'sem_nivel' },
          h('td', {}, x.nivel_nome || x.nivel || t('tracadoresultado.sem_nivel')),
          h('td', { class: 'contagem' }, String(x.contagem)))))));
    for (const bt of [btSelecionar, btCamada, btExportar]) bt.disabled = elementos.length === 0;
  }

  async function tracar() {
    if (!selRede.value) { aviso.mostrar(t('tracadoresultado.escolha'), 'erro'); return; }
    ultimoPedido = pedido();
    const r = await enviar(`/api/rede/${selRede.value}/tracar`, ultimoPedido);
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    desenharResultado(r.json);
    situacao.textContent = t('tracadoresultado.tracado_pronto');
    await desenharHistorico();
  }

  function selecionar() {
    selecionados = [...tabela.querySelectorAll('tbody tr')].map((tr) => {
      tr.setAttribute('aria-selected', 'true');
      tr.classList.add('selecionada');
      return tr.dataset.feicao;
    });
    tabela.dataset.selecionados = String(selecionados.length);
    situacao.textContent = `${selecionados.length} ${t('tracadoresultado.selecionados')}`;
  }

  async function salvarCamada() {
    if (!ultimoPedido) return;
    const titulo = campoTitulo.value.trim() || t('tracadoresultado.titulo_camada');
    const r = await enviar(`/api/rede/${selRede.value}/tracar/camada`, { ...ultimoPedido, titulo });
    if (r.status !== 201) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    situacao.dataset.item = r.json.item_id;
    situacao.textContent = `${t('tracadoresultado.camada_salva')} (${r.json.contagem})`;
    aviso.mostrar(t('tracadoresultado.camada_salva'), 'ok');
  }

  async function exportar() {
    if (!ultimoPedido) return;
    const formato = selFormato.value;
    const resp = await fetch(`/api/rede/${selRede.value}/tracar/exportar?formato=${formato}`, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ultimoPedido),
    });
    if (!resp.ok) { aviso.mostrar(mensagemDe({ status: resp.status, json: await resp.json().catch(() => ({})) }), 'erro'); return; }
    const bruto = await resp.blob();
    const url = URL.createObjectURL(bruto);
    const alvo = h('a', { href: url, download: `tracado.${formato}` });
    document.body.append(alvo); alvo.click(); alvo.remove();
    URL.revokeObjectURL(url);
    situacao.dataset.bytes = String(bruto.size);
    situacao.dataset.formato = formato;
    situacao.textContent = `${t('tracadoresultado.exportado')} ${formato} (${resp.headers.get('X-Plat-Contagem') || '?'})`;
  }

  async function desenharHistorico() {
    limpar(historico);
    if (!selRede.value) return;
    const r = await obter(`/api/rede/${selRede.value}/tracados`);
    if (r.status !== 200) return;
    const itens = r.json.itens || [];
    historico.dataset.total = String(itens.length);
    historico.append(h('table', { class: 'grade' }, h('tbody', {}, ...itens.map((x) =>
      h('tr', { 'data-execucao': x.id },
        h('td', {}, x.tipo),
        h('td', { class: 'contagem' }, x.contagem === null ? '—' : String(x.contagem)),
        h('td', {}, x.criado_em || ''),
        h('td', {}, h('button', {
          type: 'button', class: 'repetir', 'data-repetir': x.id, onclick: () => repetir(x.id),
        }, t('tracadoresultado.repetir'))))))));
  }

  async function repetir(execucaoId) {
    const r = await chamar('POST', `/api/rede/${selRede.value}/tracados/${execucaoId}/repetir`, {});
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    ultimoPedido = null;
    desenharResultado(r.json);
    situacao.dataset.repetido = execucaoId;
    situacao.textContent = `${t('tracadoresultado.repetido')} (${r.json.contagem})`;
    await desenharHistorico();
  }

  selRede.addEventListener('change', () => { limpar(tabela); limpar(painel); desenharHistorico(); });

  principal.append(
    h('p', { class: 'ajuda' }, t('tracadoresultado.ajuda')),
    h('label', { for: 'rede' }, t('tracadoresultado.rede')), selRede,
    h('label', { for: 'tipo' }, t('tracadoresultado.tipo')), selTipo,
    h('label', { for: 'feicao' }, t('tracadoresultado.feicao')), campoFeicao,
    h('label', { for: 'terminal' }, t('tracadoresultado.terminal')), campoTerminal,
    btTracar,
    h('fieldset', {}, h('legend', {}, t('tracadoresultado.acoes')),
      btSelecionar,
      h('label', { for: 'titulo' }, t('tracadoresultado.titulo_camada')), campoTitulo, btCamada,
      h('label', { for: 'formato' }, t('tracadoresultado.formato')), selFormato, btExportar),
    situacao, tabela, painel,
    h('h2', {}, t('tracadoresultado.historico')), historico);
}
