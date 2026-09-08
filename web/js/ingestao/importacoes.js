/* plat — tela /importacoes (item UX-16-ingestao-sem-tela): as três rotas de escrita do grupo `ingestao` ganham
   controle — `POST /api/importacoes` ("nova importação": item de arquivo já enviado + formato; dispara a inspeção e
   a tela acompanha até a proposta), `PUT /api/importacoes/{id}/confirmar` (proposta editada: título, CRS,
   codificação, geometria, campos e validade — só o que a proposta deixa mudar; dispara a carga) e
   `DELETE /api/importacoes/{id}` (proposta/falhou/cancelada/expirada). Estados do sistema de design (UX-01):
   <plat-estado> da lista (carregando, vazio com "nova importação", erro com "tentar de novo", negado), do fluxo
   (inspecionando/carregando com o job, falhou nomeado) e do formulário; o erro da API aparece NOMEADO no campo
   (formato_nao_suportado / conteudo_nao_corresponde → formato; item_inexistente → arquivo; srid_inexistente → CRS;
   tipo_nao_permitido / campo_desconhecido → campo; perguntas_pendentes → lista das perguntas; 409 estado_invalido e
   403 negado no controle) — nunca "422" cru, nunca tela quebrada (refutação do item). */
import { obter, enviar, alterar, apagar, mensagemDe } from '../base/api.js';
import { h, limpar, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { confirmar, notificar } from '../base/componentes.js';
import { tem } from '../base/estado.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const el = (id) => document.getElementById(id);
const PRIVILEGIO = 'conteudo.publicar_camada';
const FINAIS_INSPECAO = new Set(['proposta', 'falhou', 'cancelada', 'expirada']);
const FINAIS_CARGA = new Set(['concluida', 'falhou', 'cancelada', 'expirada']);
const APAGAVEIS = new Set(['proposta', 'falhou', 'cancelada', 'expirada']);
const CODIFICACOES = ['UTF-8', 'ISO-8859-1', 'WINDOWS-1252'];
const MARCADOR = { inspecionando: 'info', proposta: 'atencao', confirmada: 'info', carregando: 'info', concluida: 'ok',
  falhou: 'falha', cancelada: 'falha', expirada: 'falha' };
let itens = [];
let formatos = [];
let acompanhando = null;

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/importacoes' });
  cabecalho(t('importacoes.titulo'));
  montarTabela();
  el('nova').addEventListener('click', abrirNova);
  el('recarregar').addEventListener('click', () => carregarLista());
  el('lista-estado').addEventListener('acao', (e) => {
    if (e.detail.id === 'tentar') carregarLista();
    if (e.detail.id === 'nova') abrirNova();
  });
  el('fluxo-estado').addEventListener('acao', (e) => {
    if (e.detail.id === 'fechar') el('fluxo-estado').limpar();
    if (e.detail.id === 'tentar' && acompanhando) acompanhar(acompanhando.id, acompanhando.finais);
  });
  if (!tem(PRIVILEGIO)) {
    el('nova').hidden = true;
  }
  await carregarLista();
}

/* ------------------------------------------------------------------ lista */
function rotuloEstado(estado) {
  const chave = `importacoes.estado_${estado}`;
  const s = t(chave);
  return s === chave ? estado : s;
}

function montarTabela() {
  const tab = el('tabela');
  tab.colunas = [
    // o título confirmado vale mais que o proposto (é o que a camada recebe)
    { chave: 'proposta', titulo: t('importacoes.col_titulo'),
      formatar: (p, imp) => (imp.confirmacao && imp.confirmacao.titulo) || (p && p.titulo) || '—' },
    { chave: 'formato', titulo: t('importacoes.col_formato'), classe: 'mono' },
    { chave: 'estado', titulo: t('campo.estado'), formatar: (v) => marcador(rotuloEstado(v), MARCADOR[v] || 'info') },
    { chave: 'proposta', titulo: t('importacoes.col_feicoes'), classe: 'num',
      formatar: (p) => (p && typeof p.feicoes === 'number' && p.feicoes >= 0 ? formatarNumero(p.feicoes) : '—') },
    { chave: 'criado_em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'erro', titulo: t('importacoes.col_erro'), formatar: (v) => v || '' },
  ];
  tab.acoes = (imp) => {
    const a = [];
    if (imp.estado === 'proposta') a.push({ id: 'confirmar', rotulo: t('importacoes.confirmar'), classe: 'primario' });
    if (imp.estado === 'concluida') a.push({ id: 'camada', rotulo: t('importacoes.ver_camada') });
    const job = imp.estado === 'inspecionando' ? imp.job_inspecao : (imp.estado === 'carregando' || imp.estado === 'confirmada') ? imp.job_carga : null;
    if (job) a.push({ id: 'tarefa', rotulo: t('importacoes.ver_tarefa') });
    if (APAGAVEIS.has(imp.estado)) a.push({ id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' });
    return a;
  };
  tab.vazio = t('importacoes.vazio');
  tab.addEventListener('acao', (e) => acao(e.detail.id, e.detail.linha));
}

async function carregarLista() {
  const estado = el('lista-estado');
  const tab = el('tabela');
  tab.hidden = true;
  estado.carregando(t('importacoes.carregando'));
  const r = await obter('/api/importacoes?limite=200');
  if (r.status === 401) { location.href = '/entrar?proximo=/importacoes'; return; }
  if (r.status >= 400 || r.status === 0) {
    estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]);
    return;
  }
  itens = r.json.itens || [];
  el('contagem').textContent = t('importacoes.contagem', { n: itens.length });
  if (!itens.length) {
    estado.mostrar({ tipo: 'vazio', titulo: t('importacoes.vazio_titulo'), texto: t('importacoes.vazio'),
      acoes: tem(PRIVILEGIO) ? [{ id: 'nova', rotulo: t('importacoes.nova'), classe: 'primario' }] : [] });
    return;
  }
  estado.limpar();
  tab.linhas = itens;
  tab.hidden = false;
}

async function acao(id, imp) {
  if (id === 'confirmar') return abrirConfirmar(imp);
  if (id === 'camada') { location.href = `/conteudo/${encodeURIComponent(imp.item_id)}`; return null; }
  if (id === 'tarefa') { location.href = `/tarefas/${encodeURIComponent(imp.job_inspecao || imp.job_carga)}`; return null; }
  if (id === 'apagar') return apagarImportacao(imp);
  return null;
}

/* ------------------------------------------------------------------ acompanhar um job (inspeção ou carga) */
async function acompanhar(importacaoId, finais) {
  const estado = el('fluxo-estado');
  acompanhando = { id: importacaoId, finais };
  const inicio = Date.now();
  for (;;) {
    const r = await obter(`/api/importacoes/${encodeURIComponent(importacaoId)}`);
    if (r.status !== 200) { estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }]); return null; }
    const imp = r.json;
    if (finais.has(imp.estado)) {
      acompanhando = null;
      if (imp.estado === 'falhou') {
        estado.mostrar({ tipo: 'erro', titulo: t('importacoes.falhou_titulo'), texto: imp.erro || t('importacoes.falhou'),
          acoes: [{ id: 'fechar', rotulo: t('acao.fechar') }] });
      } else {
        estado.limpar();
      }
      await carregarLista();
      return imp;
    }
    estado.carregando(t(imp.estado === 'inspecionando' ? 'importacoes.inspecionando' : 'importacoes.carregando_camada'));
    if (Date.now() - inicio > 180000) {
      estado.mostrar({ tipo: 'erro', titulo: t('importacoes.demorando_titulo'), texto: t('importacoes.demorando'),
        acoes: [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
      return null;
    }
    await new Promise((res) => setTimeout(res, 1000));
  }
}

/* ------------------------------------------------------------------ nova importação */
function campoErro(form, nome, texto) {
  const alvo = form.querySelector(`[data-campo="${nome}"]`);
  if (!alvo) return false;
  let e = alvo.querySelector('.erro-campo');
  if (!e) { e = h('span', { class: 'erro-campo', role: 'alert' }); alvo.append(e); }
  e.textContent = texto;
  const controle = alvo.querySelector('input, select, textarea');
  if (controle) { controle.setAttribute('aria-invalid', 'true'); controle.focus(); }
  return true;
}

function limparErros(form) {
  for (const e of form.querySelectorAll('.erro-campo')) e.remove();
  for (const c of form.querySelectorAll('[aria-invalid]')) c.removeAttribute('aria-invalid');
}

async function abrirNova() {
  const painel = el('painel');
  if (!tem(PRIVILEGIO)) {
    const estado = h('plat-estado', { id: 'nova-estado' });
    painel.abrir({ titulo: t('importacoes.nova'), corpo: estado, botoes: [{ id: 'fechar', rotulo: t('acao.fechar') }] });
    estado.negado(t('importacoes.negado', { privilegio: PRIVILEGIO }));
    return;
  }
  const estado = h('plat-estado', { id: 'nova-estado' });
  const form = h('form', { class: 'importacao-form', id: 'form-nova' });
  const selArquivo = h('select', { name: 'arquivo_id', id: 'nova-arquivo', required: true });
  const selFormato = h('select', { name: 'formato', id: 'nova-formato', required: true });
  form.append(
    h('label', { class: 'campo', dataset: { campo: 'arquivo_id' } }, h('span', {}, t('importacoes.campo_arquivo')), selArquivo,
      h('small', { class: 'fraco' }, t('importacoes.campo_arquivo_ajuda'))),
    h('label', { class: 'campo', dataset: { campo: 'formato' } }, h('span', {}, t('importacoes.campo_formato')), selFormato),
    estado,
  );
  painel.abrir({ titulo: t('importacoes.nova'), corpo: form, botoes: [] });
  estado.carregando(t('importacoes.carregando_arquivos'));
  const [rArq, rFmt] = await Promise.all([obter('/api/itens?tipo=arquivo&limite=100'), obter('/api/importacoes/formatos')]);
  if (rArq.status >= 400 || rFmt.status >= 400) { estado.erro(rArq.status >= 400 ? rArq : rFmt); return; }
  formatos = rFmt.json || [];
  const arquivos = (rArq.json && rArq.json.itens) || [];
  if (!arquivos.length) {
    estado.mostrar({ tipo: 'vazio', titulo: t('importacoes.sem_arquivos_titulo'), texto: t('importacoes.sem_arquivos'),
      acoes: [{ id: 'enviar', rotulo: t('importacoes.ir_enviar'), classe: 'primario' }] });
    estado.addEventListener('acao', (e) => { if (e.detail.id === 'enviar') location.href = '/uploads'; });
    return;
  }
  estado.limpar();
  selArquivo.append(h('option', { value: '' }, t('importacoes.escolha')));
  for (const a of arquivos) selArquivo.append(h('option', { value: a.id }, a.titulo));
  selFormato.append(h('option', { value: '' }, t('importacoes.escolha')));
  for (const f of formatos) selFormato.append(h('option', { value: f.tipo }, `${f.rotulo} (${f.extensoes.join(', ')})`));
  // sugestão de formato pela extensão do arquivo escolhido
  selArquivo.addEventListener('change', () => {
    const nome = selArquivo.options[selArquivo.selectedIndex].textContent.toLowerCase();
    const f = formatos.find((x) => x.extensoes.some((ext) => nome.endsWith(ext)));
    if (f && !selFormato.value) selFormato.value = f.tipo;
  });
  const botoes = h('div', { class: 'botoes' },
    h('button', { type: 'submit', class: 'primario', id: 'nova-enviar' }, t('importacoes.inspecionar')),
    h('button', { type: 'button', onclick: () => painel.fechar(null) }, t('acao.cancelar')));
  form.append(botoes);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    limparErros(form);
    if (!selArquivo.value) { campoErro(form, 'arquivo_id', t('importacoes.campo_obrigatorio')); return; }
    if (!selFormato.value) { campoErro(form, 'formato', t('importacoes.campo_obrigatorio')); return; }
    el('nova-enviar').disabled = true;
    estado.carregando(t('importacoes.enviando'));
    const r = await enviar('/api/importacoes', { arquivo_id: selArquivo.value, formato: selFormato.value });
    el('nova-enviar').disabled = false;
    if (r.status === 202) {
      painel.fechar('ok');
      notificar(t('importacoes.criada'), { tipo: 'ok' });
      const imp = await acompanhar(r.json.importacao_id, FINAIS_INSPECAO);
      if (imp && imp.estado === 'proposta') abrirConfirmar(imp);
      return;
    }
    const j = r.json || {};
    if (r.status === 403) { estado.negado(j.mensagem); return; }
    estado.limpar();
    const campo = { formato_nao_suportado: 'formato', conteudo_nao_corresponde: 'formato', item_inexistente: 'arquivo_id',
      objeto_inexistente: 'arquivo_id' }[j.erro];
    if (campo) { campoErro(form, campo, `${j.erro}: ${j.mensagem}`); return; }
    estado.mostrar({ tipo: 'erro', titulo: t('importacoes.erro_criar'), texto: j.erro ? `${j.erro}: ${j.mensagem}` : mensagemDe(r),
      ref: j.req_id, acoes: [] });
  });
  selArquivo.focus();
}

/* ------------------------------------------------------------------ confirmar a proposta */
async function abrirConfirmar(imp) {
  const painel = el('painel');
  const r = await obter(`/api/importacoes/${encodeURIComponent(imp.id)}`);
  if (r.status !== 200) { el('aviso').erro(mensagemDe(r)); return; }
  imp = r.json;
  const p = imp.proposta || {};
  const perguntas = new Set(p.perguntas || []);
  const estado = h('plat-estado', { id: 'confirmar-estado' });
  const form = h('form', { class: 'importacao-form', id: 'form-confirmar' });
  const linha = (nome, rotulo, controle, ajuda) => h('label', { class: 'campo', dataset: { campo: nome } },
    h('span', {}, rotulo), controle, ...(ajuda ? [h('small', { class: 'fraco' }, ajuda)] : []));
  const titulo = h('input', { name: 'titulo', type: 'text', value: p.titulo || '', maxlength: '250', required: true });
  form.append(
    h('dl', { class: 'importacao-resumo' },
      h('div', {}, h('dt', {}, t('importacoes.col_formato')), h('dd', {}, `${p.formato || imp.formato} · ${p.camada_origem || ''}`)),
      h('div', {}, h('dt', {}, t('importacoes.col_feicoes')), h('dd', {}, p.feicoes >= 0 ? formatarNumero(p.feicoes) : '—')),
      ...(p.validade ? [h('div', {}, h('dt', {}, t('importacoes.validade')), h('dd', {},
        t('importacoes.validade_resumo', { amostra: p.validade.amostra, invalidas: p.validade.invalidas })))] : [])),
    linha('titulo', t('importacoes.campo_titulo'), titulo),
  );
  // Node.append(null) escreve o texto "null": os opcionais entram só quando existem
  if ((p.avisos || []).length) {
    form.insertBefore(h('ul', { class: 'importacao-avisos', id: 'confirmar-avisos' }, ...p.avisos.map((a) => h('li', {}, a))),
      form.querySelector('[data-campo="titulo"]'));
  }
  let srid = null, codificacao = null, geometria = null, validade = null;
  if (perguntas.has('crs') || (p.crs && p.crs.srid === null)) {
    srid = h('input', { name: 'srid', type: 'number', min: '1', value: (p.crs && (p.crs.srid || p.crs.sugestao)) || '', required: true });
    form.append(linha('crs', t('importacoes.campo_srid'), srid, t('importacoes.campo_srid_ajuda', { sugestao: (p.crs && p.crs.sugestao) || '—' })));
  } else if (p.crs && p.crs.srid) {
    form.append(h('p', { class: 'fraco' }, t('importacoes.crs_detectado', { srid: p.crs.srid, origem: p.crs.origem })));
  }
  if (perguntas.has('codificacao')) {
    codificacao = h('select', { name: 'codificacao' }, ...CODIFICACOES.map((c) => h('option', { value: c, selected: c === ((p.codificacao || {}).sugestao || 'UTF-8') }, c)));
    form.append(linha('codificacao', t('importacoes.campo_codificacao'), codificacao));
  }
  const opcoesGeom = (p.geometria && p.geometria.opcoes) || [];
  if (perguntas.has('geometria') || opcoesGeom.length > 1) {
    geometria = h('select', { name: 'geometria' }, ...opcoesGeom.map((g) => h('option', { value: g, selected: g === (p.geometria || {}).escolhida }, g)));
    form.append(linha('geometria', t('importacoes.campo_geometria'), geometria));
  }
  if (p.validade && p.validade.invalidas > 0) {
    validade = h('select', { name: 'validade' }, ...['corrigir', 'descartar', 'recusar'].map((a) => h('option', { value: a }, t(`importacoes.validade_${a}`))));
    form.append(linha('validade', t('importacoes.campo_validade'), validade, t('importacoes.campo_validade_ajuda')));
  }
  const campos = p.campos || [];
  const tabela = h('table', { class: 'importacao-campos', id: 'confirmar-campos' },
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, t('importacoes.campo_importar')), h('th', { scope: 'col' }, t('campo.nome')),
      h('th', { scope: 'col' }, t('importacoes.campo_origem')), h('th', { scope: 'col' }, t('importacoes.campo_tipo')))),
    h('tbody', {}, ...campos.map((c) => h('tr', { dataset: { campo: c.nome } },
      h('td', {}, h('input', { type: 'checkbox', name: `importar:${c.nome}`, checked: true, 'aria-label': t('importacoes.campo_importar_nome', { nome: c.nome }) })),
      h('td', { class: 'mono' }, c.nome),
      h('td', {}, c.origem || c.nome, ...((c.avisos || []).length ? [h('small', { class: 'fraco' }, ` · ${c.avisos.join('; ')}`)] : [])),
      h('td', {}, h('select', { name: `tipo:${c.nome}`, 'aria-label': t('importacoes.campo_tipo_nome', { nome: c.nome }) },
        ...(c.opcoes_tipo || [c.tipo]).map((o) => h('option', { value: o, selected: o === c.tipo }, o))))))));
  form.append(h('div', { class: 'campo', dataset: { campo: 'campos' } }, h('span', {}, t('importacoes.campos', { n: campos.length })), tabela), estado,
    h('div', { class: 'botoes' },
      h('button', { type: 'submit', class: 'primario', id: 'confirmar-enviar' }, t('importacoes.confirmar_carregar')),
      h('button', { type: 'button', onclick: () => painel.fechar(null) }, t('acao.cancelar'))));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    limparErros(form);
    const corpo = { titulo: titulo.value.trim() || undefined };
    if (srid) corpo.crs = { srid: Number(srid.value) };
    if (codificacao) corpo.codificacao = { valor: codificacao.value };
    if (geometria) corpo.geometria = { escolhida: geometria.value };
    if (validade) corpo.validade = { acao: validade.value };
    corpo.campos = campos.map((c) => ({ nome: c.nome, tipo: form.querySelector(`[name="tipo:${c.nome}"]`).value,
      importar: form.querySelector(`[name="importar:${c.nome}"]`).checked }));
    el('confirmar-enviar').disabled = true;
    estado.carregando(t('importacoes.enviando'));
    const r2 = await alterar(`/api/importacoes/${encodeURIComponent(imp.id)}/confirmar`, corpo);
    el('confirmar-enviar').disabled = false;
    if (r2.status === 202) {
      painel.fechar('ok');
      notificar(t('importacoes.confirmada'), { tipo: 'ok' });
      const fim = await acompanhar(imp.id, FINAIS_CARGA);
      if (fim && fim.estado === 'concluida') notificar(t('importacoes.concluida'), { tipo: 'ok' });
      return;
    }
    const j = r2.json || {};
    if (r2.status === 403) { estado.negado(j.mensagem); return; }
    estado.limpar();
    if (j.erro === 'perguntas_pendentes') {
      estado.mostrar({ tipo: 'erro', titulo: t('importacoes.perguntas_titulo'),
        texto: t('importacoes.perguntas_pendentes', { lista: ((j.detalhe && j.detalhe.perguntas) || []).join(', ') }), acoes: [] });
      return;
    }
    const campo = { srid_inexistente: 'crs', geometria_nao_permitida: 'geometria', tipo_nao_permitido: 'campos',
      campo_desconhecido: 'campos', validacao: 'validade' }[j.erro];
    if (campo && campoErro(form, campo, `${j.erro}: ${j.mensagem}`)) return;
    if (r2.status === 409) {
      estado.mostrar({ tipo: 'erro', titulo: t('importacoes.erro_confirmar'), texto: `${j.erro}: ${j.mensagem}`, acoes: [] });
      return;
    }
    estado.mostrar({ tipo: 'erro', titulo: t('importacoes.erro_confirmar'), texto: j.erro ? `${j.erro}: ${j.mensagem}` : mensagemDe(r2),
      ref: j.req_id, acoes: [] });
  });
  painel.abrir({ titulo: t('importacoes.confirmar_titulo', { titulo: p.titulo || '' }), corpo: form, botoes: [] });
  titulo.focus();
}

/* ------------------------------------------------------------------ apagar */
async function apagarImportacao(imp) {
  const nome = (imp.proposta && imp.proposta.titulo) || imp.formato;
  const ok = await confirmar(t('importacoes.apagar_titulo'), t('importacoes.apagar_texto', { nome }), { ok: t('acao.apagar'), perigo: true });
  if (!ok) return;
  const r = await apagar(`/api/importacoes/${encodeURIComponent(imp.id)}`);
  if (r.status === 204) {
    notificar(t('importacoes.apagada'), { tipo: 'ok' });
    await carregarLista();
    return;
  }
  const j = r.json || {};
  if (r.status === 403) { el('fluxo-estado').negado(j.mensagem); return; }
  if (r.status === 409 || r.status === 404) {
    el('fluxo-estado').mostrar({ tipo: 'erro', titulo: t('importacoes.erro_apagar'), texto: `${j.erro}: ${j.mensagem}`,
      acoes: [{ id: 'fechar', rotulo: t('acao.fechar') }] });
    return;
  }
  el('fluxo-estado').erro(r, [{ id: 'fechar', rotulo: t('acao.fechar') }]);
}
