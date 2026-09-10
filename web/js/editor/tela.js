/* plat — tela /construtor (itens L5-08-editor-arrasto e L5-09-desfazer-refazer-rascunho): abre um item de
   tipo `app` ou `painel` do catálogo, monta o editor de arrasto sobre o documento do item (L5-05) e grava com
   PATCH /api/itens/{id}.

   A tela é fina de propósito: tudo o que edita documento está em web/js/editor/{documento,editor,arrasto,
   esquema,paleta}.js, que é o que os outros doze construtores da linha vão reusar. Aqui está: sessão,
   carregar, salvar, desfazer/refazer, autosave de rascunho + recuperação local, diferença entre versões e o
   aviso de conflito de versão (409, D12: versão otimista) — sem perda silenciosa nunca (item L5-09); e a edição
   concorrente do item L5-13: `base_versao` no PATCH (o servidor mescla por nó quando os dois lados tocaram nós
   diferentes; 409 com o documento atual e os ids em conflito quando tocaram o mesmo), presença por SSE (quem está
   no documento e em que nó) e bloqueio leve por nó (aviso, não trava).
   Idioma: textos em português literal nesta tela; a passagem para o dicionário é o item
   L5-12-acessibilidade-i18n-construtores, que cobre os construtores todos de uma vez. */
import { obter, chamar, mensagemDe } from '../base/api.js';
import { h, limpar as limparEl } from '../base/dom.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { criarEditor } from './editor.js';
import { PALETA_LAYOUT } from './paleta.js';
import { PALETA_PAGINAS } from './paleta_paginas.js';
import { novoDocumento } from './documento.js';
import { criarHistorico } from './desfazer.js';
import { criarAutosave } from './rascunho.js';
import { compararDocumentos, montarArvoreDiferenca } from './diferenca.js';
import { criarPresenca } from './presenca.js';

const AUTOSAVE_INTERVALO_MS_PADRAO = 20000;
const PRESENCA_INTERVALO_MS_PADRAO = 5000;

/* item `app` ganha a paleta de PÁGINAS E LAYOUT (L5-01-a: página, cabeçalho, menu, janela, ...); os demais
   tipos de construtor continuam com a paleta de layout comum do L5-08, sem página nenhuma dentro deles. */
function paletaDoTipo(tipo) { return tipo === 'app' ? PALETA_PAGINAS : PALETA_LAYOUT; }

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

function documentoDe(item) {
  const dados = item.dados || {};
  if (dados.corpo) return { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } };
  return novoDocumento(item.tipo);
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/construtor' });
  const principal = document.getElementById('principal');
  const parametros = new URLSearchParams(location.search);
  const id = parametros.get('item');
  /* só para o e2e encurtar o ciclo do autosave (item L5-09): em produção o parâmetro nunca chega e vale o
     padrão de 20 s; sem isso um teste precisaria esperar 20 s de verdade para ver o servidor confirmar. */
  const autosaveMs = Number(parametros.get('autosave_ms')) || AUTOSAVE_INTERVALO_MS_PADRAO;
  const presencaMs = Number(parametros.get('presenca_ms')) || PRESENCA_INTERVALO_MS_PADRAO;
  const aviso = document.getElementById('aviso');
  const h1 = document.querySelector('main > h1');

  let item = null;
  let documento = novoDocumento('app');
  if (id) {
    const r = await obter(`/api/itens/${id}`);
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    documento = documentoDe(item);
    h1.textContent = item.titulo;
    document.title = `${item.titulo} · construtor · plat`;
  }

  const historico = criarHistorico();
  let documentoGravado = documento; // último documento confirmado por Salvar OU pelo autosave de rascunho

  const alvo = h('div', { id: 'editor-raiz' });
  const btDesfazer = h('button', { type: 'button', id: 'desfazer', class: 'pequeno', disabled: true }, 'Desfazer');
  const btRefazer = h('button', { type: 'button', id: 'refazer', class: 'pequeno', disabled: true }, 'Refazer');
  const btSalvar = h('button', { type: 'button', id: 'salvar', class: 'primario', disabled: !id }, 'Salvar');
  const btDiferenca = h('button', { type: 'button', id: 'ver-diferenca', class: 'pequeno', disabled: !id }, 'Ver diferença entre versões');
  const estado = h('span', { id: 'estado-salvo', class: 'estado' }, id ? 'sem alterações' : 'sem item: passe ?item=<id>');
  const linkExecutar = documento.tipo === 'app' && id
    ? h('a', { id: 'executar', class: 'pequeno', href: `/executar?item=${id}`, target: '_blank', rel: 'noopener' }, 'Executar')
    : null;
  const areaRecuperacao = h('div', { id: 'area-recuperacao' });
  const areaConflito = h('div', { id: 'area-conflito' });
  const areaDiferenca = h('div', { id: 'area-diferenca' });
  const areaPresenca = h('div', { id: 'presenca', class: 'presenca', 'aria-live': 'polite' });
  const avisoNo = h('div', { id: 'aviso-no-ocupado', class: 'aviso-no-ocupado', hidden: true });
  principal.append(
    areaPresenca,
    avisoNo,
    areaRecuperacao,
    areaConflito,
    h('div', { class: 'linha-ferramentas' }, btDesfazer, btRefazer, btSalvar, btDiferenca, estado, linkExecutar),
    areaDiferenca,
    alvo,
  );

  function dizerEstado(texto, tipo = 'info') { estado.textContent = texto; estado.dataset.tipo = tipo; }
  function atualizarBotoesHistorico() {
    btDesfazer.disabled = !historico.podeDesfazer();
    btRefazer.disabled = !historico.podeRefazer();
  }

  // ---------------------------------------------------------------- autosave de rascunho + localStorage
  let autosave = null;
  if (item) {
    autosave = criarAutosave({
      idItem: item.id,
      obterDocumento: () => editor.documento(),
      obterVersaoBase: () => item.versao_atual,
      intervaloMs: autosaveMs,
      salvarNoServidor: async (doc, versaoBase) => {
        const r = await chamar('PATCH', `/api/itens/${item.id}?rotulo=rascunho`, {
          dados: { tipo: item.tipo, esquema_versao: doc.esquema_versao, corpo: doc.corpo },
          base_versao: versaoBase,
        });
        if (r.status !== 200) return { ok: false, erro: r.json };
        if (r.json.mesclagem) absorverMesclagem(r.json);
        // autosave NUNCA publica: versao_publicada do item não muda aqui (só .../publicar muda) — só o
        // ponteiro local de versao_atual avança, para o próximo autosave/Salvar comparar contra o certo.
        item = { ...item, versao_atual: r.json.versao_atual };
        documentoGravado = doc;
        return { ok: true, versao: r.json.versao_atual };
      },
      aoCiclo: (resultado) => {
        if (resultado?.ok) dizerEstado(`gravado (rascunho automático, versão ${resultado.versao})`, 'rascunho');
        else if (resultado && !resultado.inalterado && !resultado.pulado) dizerEstado('rascunho não sincronizado (rede indisponível); guardado neste navegador', 'erro');
      },
    });

    const local = autosave.recuperar();
    if (local && JSON.stringify(local.documento) !== JSON.stringify(documento)) {
      mostrarRecuperacao(local);
    }
    autosave.iniciar();
    window.addEventListener('beforeunload', () => autosave.parar());
  }

  function mostrarRecuperacao(local) {
    limparEl(areaRecuperacao);
    const quando = new Date(local.salvo_em).toLocaleString('pt-BR');
    const usar = h('button', { type: 'button', class: 'pequeno' }, 'Usar rascunho recuperado');
    const descartar = h('button', { type: 'button', class: 'pequeno' }, 'Descartar e continuar com o servidor');
    usar.addEventListener('click', () => {
      editor.definirDocumento(local.documento);
      historico.limpar();
      atualizarBotoesHistorico();
      dizerEstado('rascunho local restaurado; alterações não gravadas', 'rascunho');
      limparEl(areaRecuperacao);
    });
    descartar.addEventListener('click', () => { autosave?.limparLocal(); limparEl(areaRecuperacao); });
    areaRecuperacao.append(
      h('div', { class: 'conflito-versao', role: 'alert' },
        h('h3', {}, 'rascunho não gravado encontrado neste navegador'),
        h('p', {}, `recuperado do armazenamento local, salvo em ${quando} (a conexão pode ter caído antes do autosave chegar ao servidor)`),
        h('div', { class: 'acoes' }, usar, descartar)),
    );
  }

  // ---------------------------------------------------------------- editor + histórico (desfazer/refazer)
  let documentoAnterior = documento;
  const editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: paletaDoTipo(documento.tipo),
    aoMudar: (novo) => {
      historico.registrar(documentoAnterior, novo);
      documentoAnterior = novo;
      atualizarBotoesHistorico();
      dizerEstado('alterações não gravadas');
      autosave?.registrarLocal(novo);
      setTimeout(() => marcarNosOcupados(), 0);
    },
  });
  atualizarBotoesHistorico();

  btDesfazer.addEventListener('click', () => {
    const novo = historico.desfazer(editor.documento());
    documentoAnterior = novo;
    editor.definirDocumento(novo);
    atualizarBotoesHistorico();
    dizerEstado('desfeito');
    autosave?.registrarLocal(novo);
  });
  btRefazer.addEventListener('click', () => {
    const novo = historico.refazer(editor.documento());
    documentoAnterior = novo;
    editor.definirDocumento(novo);
    atualizarBotoesHistorico();
    dizerEstado('refeito');
    autosave?.registrarLocal(novo);
  });
  document.addEventListener('keydown', (ev) => {
    const mod = ev.ctrlKey || ev.metaKey;
    if (!mod || ev.key.toLowerCase() !== 'z') return;
    ev.preventDefault();
    if (ev.shiftKey) btRefazer.click(); else btDesfazer.click();
  });

  // ---------------------------------------------------------------- presença + bloqueio leve por nó (L5-13)
  let presenca = null;
  if (item) {
    presenca = criarPresenca({
      idItem: item.id,
      intervaloMs: presencaMs,
      obterNo: () => editor.selecionado(),
      aoMudar: desenharPresenca,
    });
    presenca.iniciar().catch(() => {});
    window.addEventListener('pagehide', () => presenca?.sair());
    // seleção muda por clique/teclado dentro do editor: bate na hora (o nó selecionado é parte da presença)
    alvo.addEventListener('click', () => setTimeout(() => { presenca?.bater().catch(() => {}); avisarNoOcupado(); }, 0));
    alvo.addEventListener('keyup', () => setTimeout(avisarNoOcupado, 0));
  }

  function desenharPresenca(lista) {
    limparEl(areaPresenca);
    const outros = lista.filter((e) => e.sessao !== presenca.sessao);
    areaPresenca.dataset.total = String(lista.length);
    areaPresenca.dataset.outros = String(outros.length);
    if (!outros.length) { areaPresenca.append(h('span', { class: 'presenca-vazia' }, 'só você neste documento')); marcarNosOcupados(); return; }
    areaPresenca.append(h('span', { class: 'presenca-titulo' }, `também aqui (${outros.length}): `));
    const ul = h('ul', { class: 'presenca-lista' });
    for (const e of outros) {
      const no = e.no ? (documentoNome(e.no) || e.no.slice(0, 8)) : null;
      ul.append(h('li', { 'data-sessao': e.sessao, 'data-no': e.no || '', 'data-login': e.login },
        h('span', { class: 'presenca-nome' }, e.nome || e.login),
        no ? h('span', { class: 'presenca-no' }, ` no nó ${no}`) : ''));
    }
    areaPresenca.append(ul);
    marcarNosOcupados();
    avisarNoOcupado();
  }

  function documentoNome(idNo) {
    const n = editor.documento().corpo.nos.find((x) => x.id === idNo);
    return n ? `${n.tipo}${n.propriedades?.titulo ? ` "${n.propriedades.titulo}"` : ''}` : null;
  }

  function marcarNosOcupados() {
    const ocupados = presenca?.ocupados() || new Map();
    for (const el of alvo.querySelectorAll('.no-editor[data-no]')) {
      const quem = ocupados.get(el.dataset.no);
      if (quem) { el.dataset.ocupado = quem.map((e) => e.login).join(','); el.title = `em edição por ${quem.map((e) => e.nome || e.login).join(', ')}`; }
      else { delete el.dataset.ocupado; el.removeAttribute('title'); }
    }
  }

  function avisarNoOcupado() {
    const sel = editor.selecionado();
    const quem = sel ? presenca?.ocupados().get(sel) : null;
    if (!quem) { avisoNo.hidden = true; avisoNo.textContent = ''; return; }
    avisoNo.hidden = false;
    avisoNo.textContent = `${quem.map((e) => e.nome || e.login).join(', ')} também está neste nó: quem gravar por último pode ver conflito. Nada trava; combine antes de mudar o mesmo nó.`;
  }

  // ---------------------------------------------------------------- salvar (conflito de versão, D12)
  async function salvar({ forcarVersao = null } = {}) {
    if (!item) return;
    btSalvar.disabled = true;
    const d = editor.documento();
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: item.tipo, esquema_versao: d.esquema_versao, corpo: d.corpo },
      base_versao: forcarVersao ?? item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status === 409) { await mostrarConflito(d, r.json); return; }
    if (r.status !== 200) { dizerEstado('não gravado', 'erro'); aviso.mostrar(mensagemDe(r), 'erro'); return; }
    aviso.limpar?.();
    limparEl(areaConflito);
    if (r.json.mesclagem) {
      absorverMesclagem(r.json);
      const m = r.json.mesclagem;
      dizerEstado(`gravado (versão ${item.versao_atual}; mesclado com a versão ${m.versao_servidor} de outra sessão: ${m.do_servidor.length} nó(s) deles, ${m.do_cliente.length} seu(s))`, 'mesclado');
      return;
    }
    item = r.json;
    documentoGravado = d;
    autosave?.confirmarServidor(d);
    dizerEstado(`gravado (versão ${item.versao_atual})`);
  }

  /* o servidor mesclou nós de outra sessão com os nossos: o documento gravado É o novo estado — entra no
     editor sem passar pelo histórico (não é uma edição nossa), mantendo a seleção. */
  function absorverMesclagem(itemNovo) {
    item = itemNovo;
    const novo = documentoDe(item);
    const sel = editor.selecionado();
    documentoAnterior = novo;
    documentoGravado = novo;
    editor.definirDocumento(novo);
    if (sel && novo.corpo.nos.some((n) => n.id === sel)) editor.selecionar(sel);
    autosave?.confirmarServidor(novo);
  }
  btSalvar.addEventListener('click', () => salvar());

  /* NUNCA perde a edição local silenciosamente (refutação do item): mostra as duas versões (a do servidor,
     que ganhou a corrida, e a diferença contra a base local) e só grava de novo se o usuário escolher. */
  async function mostrarConflito(documentoLocal, erro) {
    dizerEstado('conflito de versão', 'erro');
    const versaoServidor = erro?.detalhe?.versao_atual;
    const conflitos = erro?.detalhe?.conflitos || [];
    limparEl(areaConflito);
    const painel = h('div', { class: 'conflito-versao', role: 'alert', id: 'conflito-versao', 'data-conflitos': conflitos.join(' ') },
      h('h3', {}, conflitos.length ? 'o mesmo nó foi alterado por outra sessão' : 'este item foi editado por outra sessão'),
      h('p', {}, `sua base era a versão ${item.versao_atual}; a versão atual no servidor é ${versaoServidor}. nada foi perdido — escolha o que fazer.`));
    if (conflitos.length) {
      painel.append(h('p', { class: 'conflito-nos' }, `nó(s) em conflito: ${conflitos.length} — os demais seriam mesclados sem problema.`));
    }
    // o documento atual do servidor vem no próprio 409 (L5-13); versão antiga do L5-09 sem ele: busca a versão
    let docServidor = erro?.detalhe?.dados?.corpo
      ? { tipo: item.tipo, esquema_versao: erro.detalhe.dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...erro.detalhe.dados.corpo } }
      : null;
    if (!docServidor && versaoServidor != null) {
      const rServ = await obter(`/api/itens/${item.id}/versoes/${versaoServidor}`);
      if (rServ.status === 200 && rServ.json.corpo?.dados?.corpo) {
        docServidor = { tipo: item.tipo, esquema_versao: rServ.json.corpo.dados.esquema_versao, corpo: rServ.json.corpo.dados.corpo };
      }
    }
    if (docServidor) {
      const comparacao = compararDocumentos(docServidor, documentoLocal);
      painel.append(h('h4', {}, 'diferença entre a versão do servidor e a sua'), montarArvoreDiferenca(h, comparacao, paletaDoTipo(documento.tipo)));
      for (const li of painel.querySelectorAll('.diferenca-arvore li[data-no]')) {
        if (conflitos.includes(li.dataset.no)) li.classList.add('em-conflito');
      }
    }
    const sobrescrever = h('button', { type: 'button', class: 'pequeno' }, conflitos.length ? 'Gravar a minha nos nós em conflito (e mesclar o resto)' : 'Gravar minha versão mesmo assim');
    const recarregar = h('button', { type: 'button', class: 'pequeno' }, 'Descartar a minha e recarregar a do servidor');
    sobrescrever.addEventListener('click', async () => {
      const r = await obter(`/api/itens/${item.id}`);
      if (r.status === 200) { item = r.json; await salvar({ forcarVersao: item.versao_atual }); }
    });
    recarregar.addEventListener('click', async () => {
      const r = await obter(`/api/itens/${item.id}`);
      if (r.status !== 200) return;
      item = r.json;
      const novo = documentoDe(item);
      documentoAnterior = novo;
      documentoGravado = novo;
      editor.definirDocumento(novo);
      historico.limpar();
      atualizarBotoesHistorico();
      autosave?.confirmarServidor(novo);
      limparEl(areaConflito);
      dizerEstado(`recarregado (versão ${item.versao_atual})`);
    });
    painel.append(h('div', { class: 'acoes' }, sobrescrever, recarregar));
    areaConflito.append(painel);
  }

  // ---------------------------------------------------------------- diferença entre duas versões publicadas
  btDiferenca.addEventListener('click', async () => {
    if (!item) return;
    limparEl(areaDiferenca);
    const rLista = await obter(`/api/itens/${item.id}/versoes?limite=100`);
    if (rLista.status !== 200) { aviso.mostrar(mensagemDe(rLista), 'erro'); return; }
    const versoes = rLista.json.itens.map((v) => v.versao).sort((a, b) => a - b);
    if (versoes.length < 2) { areaDiferenca.append(h('p', { class: 'vazio' }, 'menos de duas versões gravadas')); return; }
    const selA = h('select', { id: 'diferenca-de' }, ...versoes.map((v) => h('option', { value: String(v) }, `v${v}`)));
    const selB = h('select', { id: 'diferenca-para' }, ...versoes.map((v) => h('option', { value: String(v) }, `v${v}`)));
    selA.value = String(versoes[0]);
    selB.value = String(versoes[versoes.length - 1]);
    const resultado = h('div', { id: 'diferenca-resultado' });
    const bt = h('button', { type: 'button', class: 'pequeno' }, 'Comparar');
    bt.addEventListener('click', async () => {
      const [ra, rb] = await Promise.all([
        obter(`/api/itens/${item.id}/versoes/${selA.value}`),
        obter(`/api/itens/${item.id}/versoes/${selB.value}`),
      ]);
      if (ra.status !== 200 || rb.status !== 200) return;
      const docA = { tipo: item.tipo, esquema_versao: ra.json.corpo.dados.esquema_versao, corpo: ra.json.corpo.dados.corpo };
      const docB = { tipo: item.tipo, esquema_versao: rb.json.corpo.dados.esquema_versao, corpo: rb.json.corpo.dados.corpo };
      const comparacao = compararDocumentos(docA, docB);
      limparEl(resultado);
      resultado.append(montarArvoreDiferenca(h, comparacao, paletaDoTipo(documento.tipo)));
    });
    areaDiferenca.append(h('div', { class: 'linha-ferramentas' }, h('label', {}, 'de ', selA), h('label', {}, 'para ', selB), bt), resultado);
  });
}
