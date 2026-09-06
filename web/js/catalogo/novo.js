/* plat · catálogo — "Novo item" (ADR 0004 seção 15.1): Arquivo (upload retomável do ADR 0005 seção 3: partes de
   parte_bytes em octet-stream, concluir cria o item 'arquivo'), Conexão por URL, Mapa em branco, Pasta e "Outro
   tipo" (título + tipo + formulário gerado do JSON Schema). Todos criam de verdade e abrem o item criado. */
import { h, limpar } from '../base/dom.js';
import { icone } from '../base/icones.js';
import { t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import { pedir } from '../base/componentes.js';
import * as api from './api.js';
import { ctx, tipoDe } from './contexto.js';
import { bytes, tipoDeclaradoDoNome, TIPOS_UPLOAD, LIMITES } from './formato.js';
import { camposDoEsquema, dadosDosValores, aplicarErros, errosDoServidor, dadosIniciais } from './item_dados.js';
import { criar as criarPasta } from './pastas.js';

let aoCriado = () => {};
const el = (id) => document.getElementById(id);

export function botaoNovo({ criado, rotas = new Set() }) {
  aoCriado = criado;
  const wrap = h('div', { class: 'menu-mais novo-menu' });
  const b = h('button', { type: 'button', class: 'primario', id: 'novo-item', 'aria-haspopup': 'true', 'aria-expanded': 'false' }, t('catalogo.novo_item'), icone('chevron_baixo', { tamanho: 14 }));
  const ul = h('ul', { role: 'menu', hidden: true });
  const op = (id, rotulo, fn) => { const bt = h('button', { type: 'button', role: 'menuitem', id: `novo-${id}` }, rotulo); bt.addEventListener('click', () => { fechar(); fn(); }); ul.append(h('li', {}, bt)); };
  if (rotas.has('/api/uploads')) op('arquivo', t('catalogo.novo_arquivo'), novoArquivo);
  op('conexao', t('catalogo.novo_conexao'), novaConexao);
  op('mapa', t('catalogo.novo_mapa'), novoMapa);
  op('outro', t('catalogo.novo_outro'), novoOutro);
  op('pasta', t('catalogo.pasta_nova'), () => criarPasta(ctx.ler('pastaId')));
  const fechar = () => { ul.hidden = true; b.setAttribute('aria-expanded', 'false'); };
  b.addEventListener('click', () => { ul.hidden = !ul.hidden; b.setAttribute('aria-expanded', String(!ul.hidden)); if (!ul.hidden) ul.querySelector('button')?.focus(); });
  document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) fechar(); });
  wrap.addEventListener('keydown', (e) => { if (e.key === 'Escape') { fechar(); b.focus(); } });
  wrap.append(b, ul);
  return wrap;
}

function pastaAtual() { return ctx.ler('pastaId') || undefined; }

async function criarItem(corpo, form) {
  try {
    const item = await api.criar({ ...corpo, ...(pastaAtual() ? { pasta_id: pastaAtual() } : {}) });
    el('aviso').ok(t('catalogo.item_criado', { titulo: item.titulo }));
    aoCriado(item);
    return item;
  } catch (e) {
    if (form) {
      if (e.codigo === 'dados_invalidos') aplicarErros(form, errosDoServidor(e.detalhe));
      else form.mensagem(e.message, 'erro');
    } else el('aviso').erro(e.message);
    return null;
  }
}

async function novaConexao() {
  const tipo = tipoDe('conexao');
  const protocolos = tipo?.esquema?.properties?.protocolo?.enum || ['wms', 'wfs', 'wmts', 'ogc_api', 'esri_rest', 'postgres_fdw', 's3', 'http'];
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'titulo', rotulo: t('catalogo.col_titulo'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: LIMITES.titulo } },
    { nome: 'url', rotulo: 'URL', tipo: 'texto', obrigatorio: true, atributos: { maxlength: 2048, title: 'https://' } },
    { nome: 'protocolo', rotulo: t('catalogo.protocolo'), tipo: 'select', opcoes: protocolos.map((p) => ({ valor: p, rotulo: p })) },
  ];
  f.botoes = [{ id: 'ok', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    if (!/^https?:\/\/\S+$/.test(v.url)) { f.erro('url', t('catalogo.erro_url')); return; }
    f.ocupado = true;
    const item = await criarItem({ tipo: 'conexao', titulo: v.titulo, url: v.url, origem: 'referenciado', dados: { protocolo: v.protocolo, url: v.url } }, f);
    f.ocupado = false;
    if (item) document.getElementById('painel-novo')?.fechar('ok');
  });
  abrirForm(t('catalogo.novo_conexao'), f);
}

async function novoMapa() {
  const f = h('plat-formulario');
  f.campos = [{ nome: 'titulo', rotulo: t('catalogo.col_titulo'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: LIMITES.titulo } }, { nome: 'resumo', rotulo: t('catalogo.resumo'), tipo: 'area', linhas: 2, atributos: { maxlength: LIMITES.resumo } }];
  f.botoes = [{ id: 'ok', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    f.ocupado = true;
    const item = await criarItem({ tipo: 'mapa', titulo: v.titulo, resumo: v.resumo || undefined, dados: { esquema_versao: 1, corpo: {} } }, f);
    f.ocupado = false;
    if (item) document.getElementById('painel-novo')?.fechar('ok');
  });
  abrirForm(t('catalogo.novo_mapa'), f);
}

async function novoOutro() {
  const tipos = (ctx.ler('tipos') || []).filter((x) => x.nome !== 'arquivo');
  const f = h('plat-formulario');
  let tipo = tipos[0] || null;
  const montar = () => {
    const dados = tipo ? dadosIniciais(tipo.esquema) : {};
    f.campos = [
      { nome: 'tipo', rotulo: t('catalogo.col_tipo'), tipo: 'select', obrigatorio: true, padrao: tipo?.nome || '', opcoes: tipos.map((x) => ({ valor: x.nome, rotulo: x.rotulo })), ajuda: tipo?.descricao || '' },
      { nome: 'titulo', rotulo: t('catalogo.col_titulo'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: LIMITES.titulo } },
      { nome: 'resumo', rotulo: t('catalogo.resumo'), tipo: 'area', linhas: 2, atributos: { maxlength: LIMITES.resumo } },
      ...(tipo ? camposDoEsquema(tipo.esquema, dados).map((c) => ({ ...c, nome: `dados.${c.nome}` })) : []),
    ];
    f.botoes = [{ id: 'ok', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
    f.campo('tipo')?.addEventListener('change', (e) => { tipo = tipoDe(e.target.value); montar(); });
  };
  montar();
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    const camposDados = camposDoEsquema(tipo.esquema, {}).map((c) => ({ ...c }));
    const valoresDados = {};
    for (const c of camposDados) valoresDados[c.nome] = v[`dados.${c.nome}`];
    const { dados, erros } = dadosDosValores(camposDados, valoresDados, tipo.esquema);
    if (Object.keys(erros).length) { for (const [k, m] of Object.entries(erros)) f.erro(f.campo(`dados.${k.split('.')[0]}`) ? `dados.${k.split('.')[0]}` : '$', m); return; }
    f.ocupado = true;
    const item = await criarItem({ tipo: tipo.nome, titulo: v.titulo, resumo: v.resumo || undefined, dados }, f);
    f.ocupado = false;
    if (item) document.getElementById('painel-novo')?.fechar('ok');
  });
  abrirForm(t('catalogo.novo_outro'), f);
}

function abrirForm(titulo, f) {
  const d = document.getElementById('painel-novo') || document.body.appendChild(h('plat-dialogo', { id: 'painel-novo' }));
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') d.fechar(null); });
  d.abrir({ titulo, corpo: f });
}

/* ---------- upload de arquivo (ADR 0005 seção 3) ---------- */
async function sha256Hex(blob) {
  if (!crypto?.subtle || blob.size > 256 * 1024 * 1024) return null; // acima disso o servidor confere sozinho
  const buf = await blob.arrayBuffer();
  const hash = await crypto.subtle.digest('SHA-256', buf);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function novoArquivo() {
  const d = document.getElementById('painel-novo') || document.body.appendChild(h('plat-dialogo', { id: 'painel-novo' }));
  const corpo = h('div', { class: 'arquivo-escolha' });
  const aviso = h('plat-aviso', { id: 'upload-aviso' });
  const entrada = h('input', { type: 'file', id: 'upload-arquivo', 'aria-label': t('catalogo.novo_arquivo') });
  const tipoSel = h('select', { id: 'upload-tipo', 'aria-label': t('catalogo.tipo_declarado') }, ...TIPOS_UPLOAD.map((x) => h('option', { value: x }, x)));
  const info = h('p', { class: 'info' }, t('catalogo.upload_texto', { max: bytes(LIMITES.uploadBytes) }));
  const barra = h('div', { class: 'progresso', hidden: true, role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': '0' }, h('span', { style: 'width:0%' }));
  const estado = h('p', { class: 'info', id: 'upload-estado' });
  const enviar = h('button', { type: 'button', class: 'primario', id: 'upload-enviar', disabled: true }, t('catalogo.enviar'));
  entrada.addEventListener('change', () => {
    const f = entrada.files?.[0];
    enviar.disabled = !f;
    if (!f) return;
    const tp = tipoDeclaradoDoNome(f.name);
    if (tp) tipoSel.value = tp;
    estado.textContent = `${f.name} · ${bytes(f.size)}`;
    if (f.size > LIMITES.uploadBytes) { aviso.erro(t('catalogo.upload_grande', { max: bytes(LIMITES.uploadBytes) })); enviar.disabled = true; } else aviso.limpar();
  });
  enviar.addEventListener('click', async () => {
    const f = entrada.files?.[0];
    if (!f) return;
    enviar.disabled = true; entrada.disabled = true; tipoSel.disabled = true;
    barra.hidden = false;
    let up = null;
    try {
      estado.textContent = t('catalogo.upload_preparando');
      const sha = await sha256Hex(f);
      up = await api.uploadIniciar({ nome: f.name, bytes: f.size, tipo_declarado: tipoSel.value, ...(sha ? { sha256: sha } : {}) });
      const tam = up.parte_bytes || 16777216;
      const partes = up.partes || Math.max(1, Math.ceil(f.size / tam));
      for (let n = 1; n <= partes; n += 1) {
        const ini = (n - 1) * tam;
        const blob = f.slice(ini, Math.min(f.size, ini + tam));
        let tentativa = 0;
        for (;;) {
          try { await api.uploadParte(up.id, n, blob); break; } catch (e) { tentativa += 1; if (tentativa >= 3 || e.status === 401 || (e.status >= 400 && e.status < 500 && e.status !== 429)) throw e; }
        }
        const pct = Math.round((n / partes) * 100);
        barra.firstChild.style.width = `${pct}%`; barra.setAttribute('aria-valuenow', String(pct));
        estado.textContent = t('catalogo.upload_parte', { n, total: partes });
      }
      estado.textContent = t('catalogo.upload_concluindo');
      const r = await api.uploadConcluir(up.id);
      const itemId = r.item_id;
      const item = itemId ? await api.obter(itemId) : null;
      el('aviso').ok(t('catalogo.arquivo_enviado', { nome: f.name }));
      d.fechar('ok');
      if (item) aoCriado(item);
    } catch (e) {
      aviso.erro(e.codigo === 'conteudo_nao_corresponde' || e.codigo === 'tipo_desconhecido' ? e.message : `${t('catalogo.upload_falhou')}: ${e.message}`);
      if (up && up.id) { try { await api.uploadAbortar(up.id); } catch { /* aborto falhou: o periódico expira em 24 h */ } }
      enviar.disabled = false; entrada.disabled = false; tipoSel.disabled = false; barra.hidden = true;
    }
  });
  corpo.append(aviso, info, entrada, h('label', {}, t('catalogo.tipo_declarado'), ' ', tipoSel), estado, barra, h('div', { class: 'botoes' }, enviar));
  if (!tem('conteudo.criar')) { limpar(corpo); corpo.append(h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('erro.sem_permissao', { privilegio: 'conteudo.criar' }))); }
  await d.abrir({ titulo: t('catalogo.novo_arquivo'), corpo, botoes: [{ id: 'cancelar', rotulo: t('acao.cancelar') }] });
}
