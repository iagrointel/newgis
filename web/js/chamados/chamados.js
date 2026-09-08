/* plat · chamados — tela /chamados do cliente (item L7-13-a-chamados): lista os chamados do inquilino com o
   tempo de primeira resposta MEDIDO e o SLA declarado por severidade ao lado, abre o detalhe (conversa,
   contexto automático, anexos) e permite comentar, anexar e fechar. A abertura com captura fica no botão
   "reportar" presente em toda tela (web/js/chamados/reportar.js). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, formatarData, t } from '../base/i18n.js';
import { loja } from '../base/estado.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

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
  return h('tr', {},
    h('td', {}, `#${c.numero}`),
    h('td', {}, c.titulo),
    h('td', {}, t(`chamado.sev.${c.severidade}`)),
    h('td', {}, h('span', { class: `marcador ${ESTADO_CLASSE[c.estado] || 'info'}` }, t(`chamado.estado.${c.estado}`))),
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
  const r = await api.obter(`/api/chamados/${encodeURIComponent(id)}`);
  if (r.status !== 200) {
    aviso('lista-aviso', `${t('chamado.erro_carregar')}: ${api.mensagemDe(r)}`);
    return;
  }
  const c = r.json;
  const conversa = h('div', { class: 'conversa' }, ...c.comentarios_lista.map(comentarioEl));
  if (!c.comentarios_lista.length) conversa.append(h('p', { class: 'ajuda' }, t('chamado.sem_comentarios')));

  const contextoEl = h('details', {}, h('summary', {}, t('chamado.contexto')),
    h('pre', {}, JSON.stringify({
      tela: c.contexto.tela, versao: c.contexto.versao, idioma: c.contexto.idioma,
      req_ids: c.contexto.req_ids,
    }, null, 1)));

  const anexosEl = h('ul', { class: 'anexos' });
  for (const a of c.anexos) {
    const li = h('li', {}, `${a.nome} (${a.tipo}, ${a.bytes} bytes) `);
    const bt = h('button', { type: 'button', class: 'pequeno' }, t('chamado.baixar'));
    bt.addEventListener('click', async () => {
      const resp = await fetch(`/api/chamados/${encodeURIComponent(c.id)}/anexos/${a.id}`, { credentials: 'same-origin' });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
    li.append(bt);
    anexosEl.append(li);
  }

  const texto = h('textarea', { id: 'chamado-novo-comentario', rows: '3', maxlength: '10000' });
  const btComentar = h('button', { type: 'button' }, t('chamado.comentar'));
  btComentar.addEventListener('click', async () => {
    if (!texto.value.trim()) return;
    btComentar.disabled = true;
    const r2 = await api.enviar(`/api/chamados/${encodeURIComponent(c.id)}/comentarios`, { texto: texto.value.trim() });
    btComentar.disabled = false;
    if (r2.status !== 201) {
      aviso('lista-aviso', `${t('chamado.erro_comentar')}: ${api.mensagemDe(r2)}`);
      return;
    }
    dialogo.fechar('ok');
    abrirDetalhe(c.id);
  });

  const btFechar = h('button', { type: 'button', class: 'perigo' }, t('chamado.fechar'));
  btFechar.addEventListener('click', async () => {
    btFechar.disabled = true;
    const r2 = await api.enviar(`/api/chamados/${encodeURIComponent(c.id)}/fechar`, {});
    btFechar.disabled = false;
    if (r2.status !== 200) {
      aviso('lista-aviso', `${t('chamado.erro_fechar')}: ${api.mensagemDe(r2)}`);
      return;
    }
    dialogo.fechar('ok');
    await carregar();
  });

  const SUFIXO_TIPO = { png: 'png', jpg: 'jpeg', jpeg: 'jpeg', geojson: 'geojson', json: 'geojson',
    csv: 'csv', txt: 'csv', kml: 'kml', kmz: 'kmz', gpx: 'gpx', dxf: 'dxf', zip: 'zip', xlsx: 'xlsx' };
  const btAnexo = h('input', { type: 'file', id: 'chamado-novo-anexo' });
  btAnexo.addEventListener('change', async () => {
    const arquivo = btAnexo.files[0];
    if (!arquivo) return;
    const sufixo = arquivo.name.split('.').pop().toLowerCase();
    const tipo = SUFIXO_TIPO[sufixo];
    if (!tipo) {
      aviso('lista-aviso', `${t('chamado.erro_anexar')}: ${t('chamado.tipo_nao_aceito')}`);
      return;
    }
    const buffer = await arquivo.arrayBuffer();
    let bin = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
    const r2 = await api.enviar(`/api/chamados/${encodeURIComponent(c.id)}/anexos`,
      { nome: arquivo.name, tipo, conteudo: btoa(bin) });
    if (r2.status !== 201) {
      aviso('lista-aviso', `${t('chamado.erro_anexar')}: ${api.mensagemDe(r2)}`);
      return;
    }
    aviso('lista-aviso', t('chamado.anexo_ok'), 'ok');
  });

  const corpo = h('div', {},
    h('p', {}, h('strong', {}, `#${c.numero} — ${c.titulo}`)),
    h('p', {}, c.descricao),
    h('p', {}, `${t('chamado.severidade')}: ${t(`chamado.sev.${c.severidade}`)} · `,
      celulaResposta(c)),
    anexosEl,
    h('h3', {}, t('chamado.conversa')), conversa,
    h('label', { class: 'campo' }, h('span', {}, t('chamado.novo_comentario')), texto),
    h('div', { class: 'dialogo-botoes' }, btComentar, btFechar, btAnexo),
    contextoEl);

  const dialogo = document.getElementById('dialogo');
  await dialogo.abrir({ titulo: t('chamado.detalhe', { numero: c.numero }), corpo,
    botoes: [{ id: 'fechar', rotulo: t('dialogo.fechar') }] });
}

async function carregar() {
  aviso('lista-aviso', '');
  const r = await api.obter('/api/chamados');
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('lista-aviso', `${t('chamado.erro_carregar')}: ${api.mensagemDe(r)}`);
    return;
  }
  porId('lista-total').textContent = `(${r.json.length})`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  if (!r.json.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '7', class: 'ajuda' }, t('chamado.vazio'))));
    return;
  }
  for (const c of r.json) corpo.append(linha(c));
}

function layout(usuario) {
  montarLayout({ usuario, ativo: '/chamados' });
  cabecalho(t('nav.chamados'));
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
  layout(usuario);
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
