/* plat · catálogo — tela /modelos (item L5-37-pacotes-modelos-entre-inquilinos): galeria de modelos e
   importação de pacote. A tela faz três coisas e nada além disso:
   1. lista os modelos que o inquilino enxerga (os dele e os de escopo `plataforma`);
   2. recebe um pacote — escolhido na galeria ou solto/aberto do disco — e mostra a ANÁLISE de
      `POST /api/pacotes/verificar`: documentos que vêm, fontes que faltam mapear e, para cada fonte já
      mapeada, a diferença de esquema campo a campo;
   3. importa (`POST /api/pacotes/importar`) quando a análise diz `pronto`.
   O mapeamento é um <select> por fonte, preenchido com as camadas do inquilino de destino
   (GET /api/itens?tipo=...): é o "camada X do pacote → camada Y do destino" do item. O zip vai em base64
   dentro de JSON, como a miniatura, porque o CSRF sob cookie exige application/json. */
import { obter, enviar, apagar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const TIPOS_FONTE = ['camada_vetorial', 'vista_de_camada', 'raster', 'rede', 'arquivo'];

await carregar();
const usuario = await exigirSessao({ privilegio: 'conteudo.criar' });
if (usuario) iniciar();
pronto();

let pacoteAtual = null; // { modelo_id } ou { conteudo: base64 }
let mapeamento = {};

function avisar(texto, tipo = 'erro') {
  const aviso = document.getElementById('aviso');
  if (aviso) { aviso.setAttribute('tipo', tipo); aviso.textContent = texto; }
}

async function base64De(arquivo) {
  const bytes = new Uint8Array(await arquivo.arrayBuffer());
  let bruto = '';
  for (const b of bytes) bruto += String.fromCharCode(b);
  return btoa(bruto);
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/modelos' });
  cabecalho(t('modelos.titulo'));
  const entrada = h('input', { type: 'file', accept: '.zip,application/zip', id: 'pacote-arquivo' });
  entrada.addEventListener('change', async () => {
    if (!entrada.files.length) return;
    pacoteAtual = { conteudo: await base64De(entrada.files[0]) };
    mapeamento = {};
    await verificar();
  });
  document.getElementById('galeria').append(h('p', {}, h('label', {}, t('modelos.do_disco'), entrada)));
  await listar();
}

async function listar() {
  const lista = document.getElementById('lista');
  limpar(lista);
  const r = await obter('/api/modelos');
  if (r.status !== 200) { avisar(mensagemDe(r)); return; }
  if (!r.json.length) { lista.append(h('p', {}, t('modelos.vazio'))); return; }
  const tabela = h('table', { class: 'tabela' },
    h('thead', {}, h('tr', {},
      h('th', {}, t('modelos.nome')), h('th', {}, t('modelos.escopo')),
      h('th', {}, t('modelos.conteudo')), h('th', {}, ''))));
  const corpo = h('tbody');
  for (const m of r.json) {
    const usar = h('button', { type: 'button', class: 'pequeno' }, t('modelos.usar'));
    usar.addEventListener('click', async () => { pacoteAtual = { modelo_id: m.id }; mapeamento = {}; await verificar(); });
    const acoes = [usar, h('a', { class: 'pequeno', href: `/api/modelos/${m.id}/pacote` }, t('modelos.baixar'))];
    if (m.do_inquilino) {
      const bt = h('button', { type: 'button', class: 'pequeno' }, t('modelos.apagar'));
      bt.addEventListener('click', async () => {
        const r2 = await apagar(`/api/modelos/${m.id}`);
        if (r2.status !== 204) avisar(mensagemDe(r2)); else await listar();
      });
      acoes.push(bt);
    }
    corpo.append(h('tr', {},
      h('td', {}, m.nome, h('small', {}, m.descricao || '')),
      h('td', {}, t(`modelos.escopo_${m.escopo}`)),
      h('td', {}, `${m.documentos} · ${m.fontes}`),
      h('td', {}, ...acoes)));
  }
  tabela.append(corpo);
  lista.append(tabela);
}

async function camadasDoDestino() {
  const r = await obter(`/api/itens?${TIPOS_FONTE.map((x) => `tipo=${x}`).join('&')}&limite=200`);
  return r.status === 200 ? (r.json.itens || []) : [];
}

async function verificar() {
  const secao = document.getElementById('importar');
  secao.hidden = false;
  avisar('', 'informacao');
  const r = await enviar('/api/pacotes/verificar', { ...pacoteAtual, mapeamento });
  if (r.status !== 200) { avisar(mensagemDe(r)); return; }
  await desenharAnalise(r.json);
}

async function desenharAnalise(a) {
  const alvo = document.getElementById('analise');
  limpar(alvo);
  const candidatas = await camadasDoDestino();
  alvo.append(h('p', {}, `${a.titulo_raiz || ''} · ${a.documentos.length} ${t('modelos.documentos')}`));
  alvo.append(h('p', {}, h('code', {}, a.sha256_conteudo || '')));
  for (const f of a.fontes) {
    const sel = h('select', { 'aria-label': f.titulo || f.id },
      h('option', { value: '' }, t('modelos.escolher')),
      ...candidatas.map((c) => h('option', { value: c.id, selected: mapeamento[f.id] === c.id ? '' : undefined },
        `${c.titulo} (${c.tipo})`)));
    sel.addEventListener('change', async () => {
      if (sel.value) mapeamento[f.id] = sel.value; else delete mapeamento[f.id];
      await verificar();
    });
    const linha = h('div', { class: 'fonte' },
      h('strong', {}, f.titulo || f.id),
      h('span', {}, ` ${f.tipo} · ${f.campos} ${t('modelos.campos')} `), sel);
    if (f.diferencas && f.diferencas.length) {
      const ul = h('ul', { class: 'diferencas' });
      for (const d of f.diferencas) {
        ul.append(h('li', { class: d.bloqueia ? 'bloqueia' : '' },
          `${d.campo}: ${t(`modelos.regra_${d.regra}`)} (${t('modelos.esperado')} ${d.esperado ?? '—'}, ${t('modelos.encontrado')} ${d.encontrado ?? '—'})`));
      }
      linha.append(ul);
    }
    alvo.append(linha);
  }
  const bt = h('button', { type: 'button', disabled: a.pronto ? undefined : '' }, t('modelos.importar'));
  bt.addEventListener('click', async () => {
    const r = await enviar('/api/pacotes/importar', { ...pacoteAtual, mapeamento });
    if (r.status !== 201) { avisar(mensagemDe(r)); return; }
    avisar(t('modelos.importado'), 'sucesso');
    location.href = `/conteudo/${r.json.raiz}`;
  });
  alvo.append(bt);
}
