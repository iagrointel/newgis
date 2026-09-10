/* plat — tela /camadas/{id}/dominios (item L2-10-a-dominios-subtipos).

   Três painéis, e os três leem a MESMA resposta de GET /api/camadas/{id}/dominios:
   1. Campos e domínios: o que cada campo tem ligado, e em qual subtipo.
   2. Nova feição: o formulário de atributos. Campo com domínio codificado vira lista de escolha que MOSTRA a
      descrição e GRAVA o código; campo com domínio de intervalo vira número com mínimo e máximo; o campo de
      subtipo vira lista que, ao mudar, refaz os campos dependentes e aplica os valores padrão do subtipo.
   3. Feições da camada: a tabela, com o mesmo rótulo do formulário (descrição, não código).

   A validação de verdade é do banco: o formulário evita o erro comum, não o substitui. Um 422 vindo da API
   é mostrado ao lado do campo que ela nomear em `detalhe.campo`. */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { dominioDoCampo, opcoes, rotulo, rotuloSubtipo } from './valores.js';

const PARAMS = new URLSearchParams(location.search);
const FID_NA_URL = PARAMS.get('fid');

const ITEM_ID = location.pathname.split('/')[2] || '';

await carregar();
const usuario = await exigirSessao();
if (usuario) iniciar();
pronto();

let dados = null;         // {item_id, campos, ligacoes, subtipo}
let relacionamentos = [];  // classes de relacionamento que ESTA camada enxerga (item L2-10-b)

function aviso(texto, tipo = 'erro') {
  const el = document.getElementById('aviso');
  if (el) { el.setAttribute('tipo', tipo); el.textContent = texto || ''; }
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/conteudo' });
  cabecalho(t('dominios.titulo'));
  await recarregar();
}

async function recarregar() {
  const r = await obter(`/api/camadas/${ITEM_ID}/dominios`);
  if (r.status !== 200) { aviso(mensagemDe(r)); return; }
  dados = r.json;
  const rr = await obter(`/api/camadas/${ITEM_ID}/relacionamentos`);
  relacionamentos = rr.status === 200 ? rr.json.itens : [];
  montarLigacoes();
  montarFormulario();
  await montarTabela();
}

function subtipoAtual() {
  const campo = dados.subtipo && dados.subtipo.campo;
  if (!campo) return null;
  const el = document.getElementById(`campo-${campo}`);
  return el && el.value !== '' ? el.value : null;
}

/* ------------------------------------------------------------------ painel 1: campos e domínios */
function montarLigacoes() {
  const alvo = limpar(document.getElementById('ligacoes-corpo'));
  const tabela = h('table', { class: 'lista', id: 'tabela-ligacoes' },
    h('thead', {}, h('tr', {},
      h('th', {}, t('dominios.campo')), h('th', {}, t('dominios.tipo_do_campo')),
      h('th', {}, t('dominios.dominio')), h('th', {}, t('dominios.subtipo')))));
  const corpo = h('tbody');
  for (const campo of dados.campos) {
    const linhas = dados.ligacoes.filter((l) => l.campo === campo.nome);
    if (linhas.length === 0) {
      corpo.append(h('tr', { dataset: { campo: campo.nome } },
        h('td', {}, campo.nome), h('td', {}, campo.tipo),
        h('td', { class: 'vazio' }, t('dominios.sem_dominio')), h('td', {}, '—')));
      continue;
    }
    for (const l of linhas) {
      corpo.append(h('tr', { dataset: { campo: campo.nome, subtipo: String(l.subtipo_codigo ?? '') } },
        h('td', {}, campo.nome), h('td', {}, campo.tipo),
        h('td', {}, h('span', { class: 'dominio-nome' }, l.dominio_nome),
          ' ', h('small', {}, l.tipo === 'codificado' ? `${l.valores.length} ${t('dominios.valores')}`
            : `${l.valores.min} – ${l.valores.max}`)),
        h('td', {}, l.subtipo_codigo === null ? t('dominios.padrao') : String(l.subtipo_codigo))));
    }
  }
  tabela.append(corpo);
  alvo.append(tabela);
  if (dados.subtipo) {
    alvo.append(h('p', { class: 'nota', id: 'nota-subtipo' },
      `${t('dominios.campo_de_subtipo')}: ${dados.subtipo.campo}`));
  }
}

/* ------------------------------------------------------------------ painel 2: formulário de feição */
function campoDeAtributo(campo, subtipo) {
  const d = dominioDoCampo(dados.ligacoes, campo.nome, subtipo);
  const id = `campo-${campo.nome}`;
  if (d && d.tipo === 'codificado') {
    const sel = h('select', { id, name: campo.nome, dataset: { dominio: d.dominio_nome } },
      h('option', { value: '' }, t('dominios.escolha')));
    for (const o of opcoes(d)) sel.append(h('option', { value: o.codigo }, o.descricao));
    return sel;
  }
  if (d && d.tipo === 'intervalo') {
    return h('input', { id, name: campo.nome, type: 'number', step: 'any',
      min: d.valores.min, max: d.valores.max, dataset: { dominio: d.dominio_nome } });
  }
  const numerico = ['integer', 'bigint', 'smallint', 'double precision', 'real', 'numeric'].includes(campo.tipo);
  return h('input', { id, name: campo.nome, type: numerico ? 'number' : 'text', step: 'any' });
}

function montarFormulario() {
  const form = limpar(document.getElementById('feicao-form'));
  const campoSub = dados.subtipo && dados.subtipo.campo;
  if (campoSub) {
    const sel = h('select', { id: `campo-${campoSub}`, name: campoSub },
      h('option', { value: '' }, t('dominios.escolha')));
    for (const v of dados.subtipo.valores) sel.append(h('option', { value: String(v.codigo) }, v.nome));
    sel.addEventListener('change', () => { aplicarSubtipo(); });
    form.append(h('p', { class: 'campo' }, h('label', { for: `campo-${campoSub}` }, campoSub), sel));
  }
  for (const campo of dados.campos) {
    if (campo.nome === campoSub) continue;
    form.append(h('p', { class: 'campo', dataset: { campo: campo.nome } },
      h('label', { for: `campo-${campo.nome}` }, campo.nome),
      campoDeAtributo(campo, subtipoAtual()),
      h('span', { class: 'erro-campo', id: `erro-${campo.nome}` })));
  }
  const botao = h('button', { type: 'submit', id: 'gravar' }, t('dominios.gravar'));
  form.append(h('p', {}, botao));
  form.addEventListener('submit', gravar);
}

/* trocar o subtipo troca os campos dependentes (novo domínio) e aplica os valores padrão declarados */
function aplicarSubtipo() {
  const sub = subtipoAtual();
  const campoSub = dados.subtipo.campo;
  for (const campo of dados.campos) {
    if (campo.nome === campoSub) continue;
    const p = document.querySelector(`#feicao-form .campo[data-campo="${campo.nome}"]`);
    if (!p) continue;
    const antigo = document.getElementById(`campo-${campo.nome}`);
    const novo = campoDeAtributo(campo, sub);
    p.replaceChild(novo, antigo);
  }
  const escolhido = (dados.subtipo.valores || []).find((v) => String(v.codigo) === String(sub));
  for (const [campo, valor] of Object.entries((escolhido && escolhido.padroes) || {})) {
    const el = document.getElementById(`campo-${campo}`);
    if (el) el.value = valor === null || valor === undefined ? '' : String(valor);
  }
}

async function gravar(ev) {
  ev.preventDefault();
  aviso('');
  for (const el of document.querySelectorAll('.erro-campo')) el.textContent = '';
  const atributos = {};
  for (const campo of dados.campos) {
    const el = document.getElementById(`campo-${campo.nome}`);
    if (!el || el.value === '') continue;
    const numerico = ['integer', 'bigint', 'smallint', 'double precision', 'real', 'numeric'].includes(campo.tipo);
    atributos[campo.nome] = numerico ? Number(el.value) : el.value;
  }
  const r = await enviar(`/api/camadas/${ITEM_ID}/feicoes`, { atributos });
  if (r.status !== 201) {
    const campo = r.json && r.json.detalhe && r.json.detalhe.campo;
    const alvo = campo && document.getElementById(`erro-${campo}`);
    if (alvo) alvo.textContent = mensagemDe(r); else aviso(mensagemDe(r));
    return;
  }
  aviso(`${t('dominios.gravada')} #${r.json.fid}`, 'ok');
  await montarTabela();
}

/* ------------------------------------------------------------------ painel 3: tabela de feições */
async function montarTabela() {
  const alvo = limpar(document.getElementById('tabela-corpo'));
  const r = await obter(`/api/camadas/${ITEM_ID}/feicoes?limite=20`);
  if (r.status !== 200) { alvo.append(h('p', { class: 'vazio' }, mensagemDe(r))); return; }
  const campoSub = dados.subtipo && dados.subtipo.campo;
  const cabecalhos = [h('th', {}, 'fid'), ...dados.campos.map((c) => h('th', {}, c.nome))];
  if (relacionamentos.length > 0) cabecalhos.push(h('th', {}, t('dominios.relacionados')));
  const tabela = h('table', { class: 'lista', id: 'tabela-feicoes' },
    h('thead', {}, h('tr', {}, ...cabecalhos)));
  const corpo = h('tbody');
  for (const f of r.json.itens) {
    const sub = campoSub ? f[campoSub] : null;
    const celulas = [h('td', {}, String(f.fid)),
      ...dados.campos.map((c) => h('td', { title: f[c.nome] === null ? '' : String(f[c.nome]) },
        c.nome === campoSub ? rotuloSubtipo(dados.subtipo, f[c.nome])
          : rotulo(dados.ligacoes, c.nome, f[c.nome], sub)))];
    if (relacionamentos.length > 0) {
      const botao = h('button', { type: 'button', class: 'link', dataset: { fid: String(f.fid) } },
        t('dominios.relacionados'));
      botao.addEventListener('click', () => abrirRelacionados(f.fid));
      celulas.push(h('td', {}, botao));
    }
    corpo.append(h('tr', { dataset: { fid: String(f.fid) } }, ...celulas));
  }
  tabela.append(corpo);
  alvo.append(tabela);
  // navegação vinda do popup de outra camada (?fid=N): destaca e centraliza a linha, se estiver na página
  if (FID_NA_URL) {
    const linha = alvo.querySelector(`tr[data-fid="${CSS.escape(FID_NA_URL)}"]`);
    if (linha) { linha.classList.add('destaque'); linha.scrollIntoView({ block: 'center' }); }
  }
}

/* ------------------------------------------------------------------ popup de relacionados (item L2-10-b) */
async function abrirRelacionados(fid) {
  const dlg = document.getElementById('popup-relacionados');
  const corpo = h('div', { class: 'relacionados-corpo' });
  const secoes = [];
  for (const rel of relacionamentos) {
    const r = await obter(`/api/camadas/${ITEM_ID}/relacionados/${encodeURIComponent(rel.nome)}?fids=${fid}`);
    const registros = r.status === 200 ? (r.json.grupos[String(fid)] || []) : [];
    const lista = registros.length === 0
      ? h('p', { class: 'vazio' }, t('dominios.sem_relacionados'))
      : h('ul', {}, ...registros.map((reg) => h('li', {},
          h('a', { href: `/camadas/${rel.alvo_item_id}/dominios?fid=${reg.fid}` },
            `#${reg.fid}`, ' ', h('small', {}, `(${t('dominios.ver_registro')})`)))));
    secoes.push(h('section', { class: 'relacionado-secao', dataset: { rel: rel.nome } },
      h('h3', {}, `${rel.nome} (${registros.length})`), lista));
  }
  corpo.append(...(secoes.length ? secoes : [h('p', { class: 'vazio' }, t('dominios.sem_relacionados'))]));
  await dlg.abrir({
    titulo: `${t('dominios.relacionados_titulo')} · #${fid}`, corpo,
    botoes: [{ id: 'fechar', rotulo: t('dialogo.fechar'), classe: 'primario' }],
  });
}
