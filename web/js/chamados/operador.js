/* plat · painel do operador — tela /admin/chamados, só superadmin (item L7-13-a-chamados). Fila de chamados de
   todos os inquilinos (GET /api/plataforma/chamados), leitura, resposta, mudança de estado e download de anexos.
   Tudo passa pelas funções SECURITY DEFINER que provam o superadmin pelo hash da sessão — esta tela não recebe
   chave de objeto nenhuma: o download vem da rota da API. A guarda aqui é de superfície (o servidor recusa
   quem não é superadmin em toda rota); quem não é superadmin vê "sem permissão". */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, formatarData, t } from '../base/i18n.js';
import { loja } from '../base/estado.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao, semPermissao } from '../auth/sessao.js';

/* espelho do mapa de transições de app/chamados/rotas.py (o servidor continua sendo quem valida) */
const TRANSICOES = {
  aberto: ['em_analise', 'aguardando_cliente', 'resolvido'],
  em_analise: ['aguardando_cliente', 'resolvido'],
  aguardando_cliente: ['em_analise', 'resolvido'],
  resolvido: ['fechado', 'em_analise'],
  fechado: [],
};
const ESTADO_CLASSE = { aberto: 'info', em_analise: 'atencao', aguardando_cliente: 'atencao',
  resolvido: 'ok', fechado: '' };
let saindo = false;

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

function celulaResposta(c) {
  if (c.primeira_resposta_horas === null || c.primeira_resposta_horas === undefined) {
    return h('span', { class: 'ajuda' }, t('chamado.sem_resposta', { horas: c.sla_primeira_resposta_horas }));
  }
  const dentro = c.sla_dentro === true ? 'ok' : 'falha';
  return h('span', {},
    `${t('chamado.respondeu_em', { horas: c.primeira_resposta_horas })} `,
    h('span', { class: `marcador ${dentro}`, title: t('chamado.sla_title', { horas: c.sla_primeira_resposta_horas }) },
      c.sla_dentro === true ? t('chamado.sla_dentro') : t('chamado.sla_fora')));
}

function linha(c) {
  const btVer = h('button', { type: 'button', class: 'pequeno' }, t('chamado.ver'));
  btVer.addEventListener('click', () => abrirDetalhe(c.id));
  return h('tr', { 'data-chamado': c.id },
    h('td', {}, c.tenant_slug),
    h('td', {}, `#${c.numero}`),
    h('td', {}, c.titulo),
    h('td', {}, t(`chamado.sev.${c.severidade}`)),
    h('td', {}, h('span', { class: `marcador ${ESTADO_CLASSE[c.estado] || 'info'}` }, t(`chamado.estado.${c.estado}`))),
    h('td', {}, c.aberto_por || ''),
    h('td', {}, celulaResposta(c)),
    h('td', {}, formatarData(c.aberto_em)),
    h('td', {}, btVer));
}

function comentarioEl(k) {
  return h('div', { class: `comentario origem-${k.origem}` },
    h('p', {}, k.texto),
    h('p', { class: 'ajuda' }, `${k.autor} · ${formatarData(k.criado_em)} · ${t(`chamado.origem.${k.origem}`)}`));
}

async function abrirDetalhe(id) {
  const r = await api.obter(`/api/plataforma/chamados/${encodeURIComponent(id)}`);
  if (r.status !== 200) {
    aviso('lista-aviso', `${t('chamado.erro_carregar')}: ${api.mensagemDe(r)}`);
    return;
  }
  const c = r.json;
  const conversa = h('div', { class: 'conversa' }, ...c.comentarios_lista.map(comentarioEl));
  if (!c.comentarios_lista.length) conversa.append(h('p', { class: 'ajuda' }, t('chamado.sem_comentarios')));

  const anexosEl = h('ul', { class: 'anexos' });
  for (const a of c.anexos) {
    const li = h('li', {}, `${a.nome} (${a.tipo}, ${a.bytes} bytes) `);
    const bt = h('button', { type: 'button', class: 'pequeno' }, t('chamado.baixar'));
    bt.addEventListener('click', () => {
      window.open(`/api/plataforma/chamados/${encodeURIComponent(c.id)}/anexos/${a.id}`, '_blank');
    });
    li.append(bt);
    anexosEl.append(li);
  }

  const resposta = h('textarea', { id: 'chamado-resposta', rows: '4', maxlength: '10000' });
  const btResponder = h('button', { type: 'button', class: 'primario' }, t('chamado.responder'));
  btResponder.addEventListener('click', async () => {
    if (!resposta.value.trim()) return;
    btResponder.disabled = true;
    const r2 = await api.enviar(`/api/plataforma/chamados/${encodeURIComponent(c.id)}/comentarios`,
      { texto: resposta.value.trim() });
    btResponder.disabled = false;
    if (r2.status !== 201) {
      aviso('lista-aviso', `${t('chamado.erro_responder')}: ${api.mensagemDe(r2)}`);
      return;
    }
    dialogo.fechar('ok');
    await carregar();
    abrirDetalhe(id);
  });

  /* mudança de estado: só os destinos válidos a partir do estado atual (espelho local; o servidor valida de novo) */
  const destinos = TRANSICOES[c.estado] || [];
  const btEstado = h('button', { type: 'button', class: destinos.includes('fechado') ? 'perigo' : '' },
    t('chamado.mudar_estado'));
  const selEstado = h('select', { id: 'chamado-novo-estado' },
    ...destinos.map((e) => h('option', { value: e }, t(`chamado.estado.${e}`))));
  if (destinos.length) {
    btEstado.addEventListener('click', async () => {
      if (!selEstado.value) return;
      btEstado.disabled = true;
      const r2 = await api.enviar(`/api/plataforma/chamados/${encodeURIComponent(c.id)}/estado`,
        { estado: selEstado.value });
      btEstado.disabled = false;
      if (r2.status !== 200) {
        aviso('lista-aviso', `${t('chamado.erro_estado')}: ${api.mensagemDe(r2)}`);
        return;
      }
      dialogo.fechar('ok');
      await carregar();
      abrirDetalhe(id);
    });
  } else {
    btEstado.disabled = true;
  }

  const contextoEl = h('details', {}, h('summary', {}, t('chamado.contexto')),
    h('pre', {}, JSON.stringify({
      inquilino: c.tenant_slug, tela: c.contexto.tela, versao: c.contexto.versao,
      idioma: c.contexto.idioma, req_ids: c.contexto.req_ids,
    }, null, 1)));

  const corpo = h('div', {},
    h('p', {}, h('strong', {}, `${c.tenant_slug} · #${c.numero} — ${c.titulo}`)),
    h('p', {}, c.descricao),
    h('p', {},
      `${t('chamado.aberto_por')}: ${c.aberto_por || ''} (${c.aberto_por_email || ''}) · `,
      `${t('chamado.severidade')}: ${t(`chamado.sev.${c.severidade}`)} · `,
      celulaResposta(c)),
    anexosEl,
    h('h3', {}, t('chamado.conversa')), conversa,
    h('label', { class: 'campo' }, h('span', {}, t('chamado.resposta_nova')), resposta),
    h('div', { class: 'dialogo-botoes' }, btResponder,
      h('span', { class: 'campo-linha' }, selEstado, btEstado)),
    contextoEl);

  const dialogo = document.getElementById('dialogo');
  await dialogo.abrir({ titulo: t('chamado.detalhe', { numero: c.numero }), corpo,
    botoes: [{ id: 'fechar', rotulo: t('dialogo.fechar') }] });
}

async function carregar() {
  aviso('lista-aviso', '');
  const estado = porId('filtro-estado').value || null;
  const r = await api.obter(`/api/plataforma/chamados${estado ? `?estado=${encodeURIComponent(estado)}` : ''}`);
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('lista-aviso', `${t('chamado.erro_carregar')}: ${api.mensagemDe(r)}`);
    return;
  }
  porId('lista-total').textContent = `(${r.json.length})`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  if (!r.json.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '9', class: 'ajuda' }, t('chamado.vazio'))));
    return;
  }
  for (const c of r.json) corpo.append(linha(c));
}

function layout(usuario) {
  montarLayout({ usuario, ativo: '/admin/chamados' });
  cabecalho(t('nav.chamados_operador'));
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { saindo = true; irParaLogin(); return; }
  const usuario = r.json;
  marcarSessao(true);
  if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
  loja.definir({ usuario });
  const destino = caminhoPendencia(usuario.pendencias);
  if (destino) { saindo = true; location.replace(destino); return; }
  if (usuario.superadmin !== true) { semPermissao('superadmin'); return; }
  layout(usuario);
  porId('filtro-estado').addEventListener('change', () => carregar());
  porId('recarregar').addEventListener('click', () => carregar());
  await carregar();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
