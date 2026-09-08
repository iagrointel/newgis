/* plat — tela /uploads (itens L0-04-a-upload-arquivo e UX-05; ADR 0005 seção 3): upload retomável em partes de
   16 MiB com FILA de arquivos, progresso por PARTE com bytes acumulados, velocidade e estimativa de tempo, cancelar
   por arquivo ou tudo (AbortController), tentar de novo o que falhou. O arquivo nunca é lido inteiro na memória:
   cada parte é um Blob.slice que o navegador transmite por streaming; a tela pinta no máximo uma vez por quadro
   (requestAnimationFrame), o que mantém o fio principal livre em arquivos de gigabytes (refutação do item: "upload
   de 2 GB mostra progresso sem travar a tela" — a suíte e2e mede as tarefas longas do fio principal).
   Por que não progresso por byte: só XMLHttpRequest expõe upload.onprogress, e um XHR na mesma origem SEMPRE leva o
   cookie de sessão junto (withCredentials só vale entre origens); com cookie + Authorization a API responde 400
   autenticacao_ambigua (regra deliberada de app/auth/sessao.py). fetch com credentials:'omit' é o único caminho que
   omite o cookie, e fetch não expõe progresso de envio. Fica registrado no handoff para o dono da autenticação.
   A sessão (cookie) só assina `POST /api/uploads` (JSON, CSRF-seguro); o envio das partes, a conclusão e o aborto
   exigem um TOKEN de serviço — a própria tela troca a sessão por um token de escopo restrito (`POST /api/tokens`,
   uma vez por carregamento de página) e usa esse token só em memória, nunca localStorage.
   Estados explícitos por <plat-estado>: carregando (tipos aceitos), erro (com tentar de novo), negado (sem
   conteudo.criar, por exigirSessao). Cada erro da API aparece nomeado na linha do arquivo, nunca um status cru. */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { aoTraduzir, carregar, formatarNumero, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const NOME_TOKEN = 'plat-uploads-tela';
const UNIDADES = ['B', 'KB', 'MB', 'GB', 'TB'];
const ESTADOS_FINAIS = new Set(['concluido', 'falhou', 'cancelado']);

await carregar();
const usuario = await exigirSessao({ privilegio: 'conteudo.criar' });
if (usuario) await iniciar();
pronto();

let tokenServico = null;

async function token() {
  if (tokenServico) return tokenServico;
  const r = await enviar('/api/tokens', { nome: NOME_TOKEN, escopos: ['admin:inquilino'], validade_dias: 1 });
  if (r.status !== 201) throw new Error(r.json.mensagem || t('upload.erro_preparar'));
  tokenServico = r.json.token;
  return tokenServico;
}

export function formatarBytes(n) {
  if (n === null || n === undefined) return '—';
  let v = n, i = 0;
  while (v >= 1024 && i < UNIDADES.length - 1) { v /= 1024; i += 1; }
  return `${formatarNumero(Number(v.toFixed(i === 0 ? 0 : 1)))} ${UNIDADES[i]}`;
}

function formatarSegundos(s) {
  if (!Number.isFinite(s) || s < 0) return '—';
  if (s < 60) return t('upload.segundos', { n: Math.ceil(s) });
  return t('upload.minutos', { n: Math.ceil(s / 60) });
}

function extensaoDe(nome) {
  const i = nome.lastIndexOf('.');
  return i >= 0 ? nome.slice(i).toLowerCase() : '';
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/uploads' });
  cabecalho(t('upload.titulo'));
  await montarTela();
}

/* ---------- tela ---------- */

async function montarTela() {
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const estado = document.getElementById('upload-estado');

  estado.carregando(t('upload.carregando_tipos'));
  const rTipos = await obter('/api/uploads/tipos');
  if (rTipos.status !== 200) {
    estado.erro(rTipos);
    estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') location.reload(); }, { once: true });
    return;
  }
  estado.limpar();
  const tipos = Array.isArray(rTipos.json) ? rTipos.json : [];
  const tipoDaExtensao = (nome) => tipos.find((tp) => tp.extensoes.includes(extensaoDe(nome)))?.tipo || null;

  const selecao = h(
    'select', { id: 'upload-tipo' },
    h('option', { value: '' }, t('upload.tipo_detectar')),
    ...tipos.map((tp) => h('option', { value: tp.tipo }, `${tp.rotulo} (${tp.extensoes.join(', ')})`)),
  );

  const entrada = h('input', { type: 'file', id: 'upload-arquivo', class: 'sr-only', multiple: true, 'aria-label': t('upload.escolher_arquivos') });
  const nomeArquivo = h('p', { id: 'upload-nome' }, t('upload.nenhum_arquivo'));
  const dropzone = h(
    'div', { id: 'upload-dropzone', class: 'upload-dropzone', tabindex: '0', role: 'button', 'aria-label': t('upload.dropzone') },
    h('p', {}, t('upload.dropzone')),
    h('p', { class: 'ajuda' }, t('upload.dropzone_ajuda', { tamanho: '2 GiB', parte: '16 MiB' })),
    nomeArquivo,
  );
  dropzone.addEventListener('click', () => entrada.click());
  dropzone.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); entrada.click(); } });
  dropzone.addEventListener('dragover', (ev) => { ev.preventDefault(); dropzone.classList.add('sobre'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('sobre'));
  dropzone.addEventListener('drop', (ev) => {
    ev.preventDefault();
    dropzone.classList.remove('sobre');
    if (ev.dataTransfer.files.length) acrescentar([...ev.dataTransfer.files]);
  });
  entrada.addEventListener('change', () => { acrescentar([...entrada.files]); entrada.value = ''; });

  const barra = h('progress', { id: 'upload-progresso', max: '100', value: '0', hidden: true, 'aria-labelledby': 'upload-rotulo-progresso' });
  const rotuloProgresso = h('p', { id: 'upload-rotulo-progresso', hidden: true, 'aria-live': 'polite' });
  const botaoEnviar = h('button', { type: 'button', class: 'primario', id: 'upload-enviar' }, t('upload.enviar'));
  const botaoCancelar = h('button', { type: 'button', class: 'texto', id: 'upload-cancelar', hidden: true }, t('upload.cancelar_tudo'));
  const botaoLimpar = h('button', { type: 'button', class: 'texto', id: 'upload-limpar', hidden: true }, t('upload.limpar_fila'));
  const resultado = h('div', { id: 'upload-resultado', 'aria-live': 'polite' });
  const fila = h('ol', { id: 'upload-fila', class: 'upload-fila vazio', 'aria-label': t('upload.fila'), hidden: true });

  /* ---- fila ---- */
  const itens = []; // {id, arquivo, tipo, estado, enviados, uploadId, aborto, erro, li, ...}
  let seq = 0;
  let enviando = false;
  let cancelarTudo = false;

  function acrescentar(arquivos) {
    aviso.limpar();
    for (const f of arquivos) {
      const it = { id: `f${++seq}`, arquivo: f, tipo: tipoDaExtensao(f.name), estado: 'na_fila', enviados: 0, uploadId: null, aborto: null, erro: null, partes: 0, parteAtual: 0 };
      it.li = linhaFila(it);
      itens.push(it);
      fila.append(it.li);
    }
    marcarFilaVazia();
    if (arquivos.length === 1 && itens.filter((i) => !ESTADOS_FINAIS.has(i.estado)).length === 1) {
      // um arquivo só: a caixa mostra o nome e o tipo detectado vai para o seletor (comportamento do item L0-04-a)
      const it = itens[itens.length - 1];
      nomeArquivo.textContent = `${it.arquivo.name} · ${formatarBytes(it.arquivo.size)}`;
      if (it.tipo) selecao.value = it.tipo;
    } else {
      atualizarResumo();
    }
    botaoLimpar.hidden = false;
    atualizarLinhas();
  }

  /* estado vazio explícito da fila: sem arquivo, a lista some e a área de soltar é o convite */
  function marcarFilaVazia() { fila.classList.toggle('vazio', itens.length === 0); fila.hidden = itens.length === 0; }

  function atualizarResumo() {
    const pendentes = itens.filter((i) => !ESTADOS_FINAIS.has(i.estado));
    if (!pendentes.length) { nomeArquivo.textContent = t('upload.nenhum_arquivo'); return; }
    const total = pendentes.reduce((a, i) => a + i.arquivo.size, 0);
    nomeArquivo.textContent = pendentes.length === 1
      ? `${pendentes[0].arquivo.name} · ${formatarBytes(pendentes[0].arquivo.size)}`
      : t('upload.n_arquivos', { n: pendentes.length, total: formatarBytes(total) });
  }

  function rotuloEstado(it) {
    switch (it.estado) {
      case 'na_fila': return t('upload.est_na_fila');
      case 'enviando': return t('upload.parte_de', { n: it.parteAtual, total: it.partes });
      case 'concluindo': return t('upload.est_concluindo');
      case 'concluido': return t('upload.est_concluido');
      case 'falhou': return it.erro || t('upload.erro_generico');
      case 'cancelado': return t('upload.cancelado');
      default: return '';
    }
  }

  function linhaFila(it) {
    const barraItem = h('progress', { class: 'barra', max: '100', value: '0', 'aria-label': t('upload.progresso_de', { nome: it.arquivo.name }) });
    const estadoItem = h('span', { class: 'estado-arquivo' }, rotuloEstado(it));
    const tipoItem = h('span', { class: 'tipo-arquivo mono' }, it.tipo || t('upload.tipo_por_definir'));
    const btCancelar = h('button', { type: 'button', class: 'pequeno perigo acao-cancelar' }, t('upload.cancelar'));
    btCancelar.addEventListener('click', () => cancelarItem(it));
    const btRepetir = h('button', { type: 'button', class: 'pequeno acao-repetir', hidden: true }, t('upload.tentar_de_novo'));
    btRepetir.addEventListener('click', () => { it.estado = 'na_fila'; it.enviados = 0; it.erro = null; it.uploadId = null; atualizarLinhas(); atualizarResumo(); processar(); });
    const btRemover = h('button', { type: 'button', class: 'pequeno texto acao-remover' }, t('upload.remover'));
    btRemover.addEventListener('click', () => { if (it.estado === 'enviando' || it.estado === 'concluindo') return; itens.splice(itens.indexOf(it), 1); it.li.remove(); atualizarResumo(); botaoLimpar.hidden = !itens.length; marcarFilaVazia(); });
    const li = h('li', { class: 'upload-item', dataset: { estado: it.estado, id: it.id } },
      h('div', { class: 'upload-item-topo' },
        h('span', { class: 'nome-arquivo' }, it.arquivo.name),
        h('span', { class: 'tamanho mono' }, formatarBytes(it.arquivo.size)),
        tipoItem,
        h('span', { class: 'marcador info estado-marcador' }, t('upload.est_na_fila'))),
      barraItem,
      h('div', { class: 'upload-item-rodape' }, estadoItem, h('div', { class: 'acoes-linha' }, btCancelar, btRepetir, btRemover)));
    it.el = { barraItem, estadoItem, tipoItem, btCancelar, btRepetir, btRemover, marcador: li.querySelector('.estado-marcador') };
    return li;
  }

  const MARCADOR = { na_fila: ['info', 'upload.est_na_fila'], enviando: ['info', 'upload.est_enviando'], concluindo: ['info', 'upload.est_concluindo'], concluido: ['ok', 'upload.est_concluido'], falhou: ['falha', 'upload.est_falhou'], cancelado: ['atencao', 'upload.cancelado'] };

  function atualizarLinhas() {
    for (const it of itens) {
      it.li.dataset.estado = it.estado;
      const pct = it.arquivo.size ? Math.min(100, Math.round((it.enviados / it.arquivo.size) * 100)) : (it.estado === 'concluido' ? 100 : 0);
      it.el.barraItem.value = it.estado === 'concluido' ? 100 : pct;
      it.el.estadoItem.textContent = rotuloEstado(it);
      it.el.estadoItem.classList.toggle('falha', it.estado === 'falhou');
      it.el.tipoItem.textContent = it.tipo || (selecao.value || t('upload.tipo_por_definir'));
      const [classe, chave] = MARCADOR[it.estado] || MARCADOR.na_fila;
      it.el.marcador.className = `marcador ${classe} estado-marcador`;
      it.el.marcador.textContent = t(chave);
      it.el.btCancelar.hidden = ESTADOS_FINAIS.has(it.estado);
      it.el.btRepetir.hidden = !(it.estado === 'falhou' || it.estado === 'cancelado');
      it.el.btRemover.hidden = it.estado === 'enviando' || it.estado === 'concluindo';
    }
  }

  /* ---- progresso global (arquivo em curso) pintado no máximo uma vez por quadro ---- */
  let quadro = null;
  let atual = null;
  let inicioEnvio = 0;
  function pintarProgresso() {
    quadro = null;
    if (!atual) return;
    const it = atual;
    const pct = it.arquivo.size ? Math.min(100, Math.floor((it.enviados / it.arquivo.size) * 100)) : 0;
    barra.value = pct;
    const decorrido = (performance.now() - inicioEnvio) / 1000;
    const velocidade = decorrido > 0 ? it.enviados / decorrido : 0;
    const restante = velocidade > 0 ? (it.arquivo.size - it.enviados) / velocidade : NaN;
    rotuloProgresso.textContent = `${t('upload.parte_de', { n: it.parteAtual, total: it.partes })} · ${formatarBytes(it.enviados)} / ${formatarBytes(it.arquivo.size)} · ${formatarBytes(velocidade)}/s · ${t('upload.restam', { tempo: formatarSegundos(restante) })}`;
    it.el.barraItem.value = pct;
    it.el.estadoItem.textContent = `${t('upload.parte_de', { n: it.parteAtual, total: it.partes })} · ${pct} %`;
  }
  const pedirPintura = () => { if (quadro === null) quadro = requestAnimationFrame(pintarProgresso); };

  /* ---- ações ---- */
  async function cancelarItem(it) {
    if (it.estado === 'enviando' || it.estado === 'concluindo') {
      it.cancelado = true;
      if (it.aborto) it.aborto.abort();
      return; // quem está enviando fecha a linha ao ver `cancelado`
    }
    it.estado = 'cancelado';
    atualizarLinhas();
    atualizarResumo();
  }

  async function abortarNoServidor(uploadId) {
    if (!uploadId) return;
    try {
      await fetch(`/api/uploads/${uploadId}`, { method: 'DELETE', credentials: 'omit', headers: { authorization: `Bearer ${await token()}` } });
    } catch { /* melhor esforço: o periódico de 24h limpa se isto falhar */ }
  }

  botaoCancelar.addEventListener('click', () => {
    cancelarTudo = true;
    for (const it of itens) if (it.estado === 'na_fila') it.estado = 'cancelado';
    if (atual) cancelarItem(atual);
    atualizarLinhas();
    aviso.mostrar(t('upload.cancelado'), 'info');
  });

  botaoLimpar.addEventListener('click', () => {
    for (const it of itens.slice()) {
      if (ESTADOS_FINAIS.has(it.estado)) { itens.splice(itens.indexOf(it), 1); it.li.remove(); }
    }
    botaoLimpar.hidden = !itens.length;
    atualizarResumo();
    marcarFilaVazia();
  });

  botaoEnviar.addEventListener('click', () => {
    const prontos = itens.filter((i) => i.estado === 'na_fila');
    if (!prontos.length) { aviso.erro(t('upload.escolha_um_arquivo')); return; }
    aviso.limpar();
    processar();
  });

  function terminarFila() {
    enviando = false;
    atual = null;
    barra.hidden = true;
    rotuloProgresso.hidden = true;
    botaoCancelar.hidden = true;
    botaoEnviar.disabled = false;
    cancelarTudo = false;
    atualizarResumo();
    const feitos = itens.filter((i) => i.estado === 'concluido').length;
    const falhas = itens.filter((i) => i.estado === 'falhou').length;
    if (feitos && !falhas) aviso.ok(feitos === 1 ? t('upload.concluido') : t('upload.concluidos', { n: feitos }));
    else if (feitos && falhas) aviso.mostrar(t('upload.parcial', { ok: feitos, falhas }), 'atencao');
    else if (falhas) aviso.erro(falhas === 1 ? (itens.find((i) => i.estado === 'falhou').erro || t('upload.erro_generico')) : t('upload.falharam', { n: falhas }));
  }

  async function processar() {
    if (enviando) return;
    enviando = true;
    botaoEnviar.disabled = true;
    barra.hidden = false;
    rotuloProgresso.hidden = false;
    botaoCancelar.hidden = false;
    limpar(resultado);
    for (;;) {
      const it = itens.find((i) => i.estado === 'na_fila');
      if (!it || cancelarTudo) break;
      atual = it;
      inicioEnvio = performance.now();
      barra.value = 0;
      it.estado = 'enviando';
      it.tipo = it.tipo || selecao.value || null;
      atualizarLinhas();
      if (!it.tipo) {
        it.estado = 'falhou';
        it.erro = t('upload.tipo_desconhecido');
        atualizarLinhas();
        continue;
      }
      try {
        const fim = await enviarArquivo(it, {
          aoIniciar: (id, partes) => { it.uploadId = id; it.partes = partes; it.parteAtual = 1; pedirPintura(); },
          aoProgredir: (bytes, parte) => { it.enviados = bytes; it.parteAtual = parte; pedirPintura(); },
        });
        it.estado = 'concluido';
        it.enviados = it.arquivo.size;
        barra.value = 100;
        rotuloProgresso.textContent = `${t('upload.parte_de', { n: it.partes, total: it.partes })} · ${formatarBytes(it.arquivo.size)} · 100 %`;
        const p = h('p', { class: 'upload-ok' }, `${it.arquivo.name}: ${t('upload.arquivo_pronto')}`);
        if (fim && fim.arquivo_id) p.append(' ', h('a', { href: `/conteudo/${encodeURIComponent(fim.arquivo_id)}` }, t('upload.abrir_item')));
        resultado.append(p);
      } catch (e) {
        if (it.cancelado) {
          it.estado = 'cancelado';
          it.cancelado = false;
          await abortarNoServidor(it.uploadId);
        } else {
          it.estado = 'falhou';
          it.erro = e.message || t('upload.erro_generico');
          await abortarNoServidor(it.uploadId);
        }
      }
      atualizarLinhas();
    }
    terminarFila();
  }

  /* ---- envio de um arquivo: POST inicia, PUT por parte (XHR com progresso de byte), POST conclui ---- */
  async function enviarArquivo(it, { aoIniciar, aoProgredir }) {
    const tk = await token();
    const arquivo = it.arquivo;
    const rIniciar = await enviar('/api/uploads', { nome: arquivo.name, bytes: arquivo.size, tipo_declarado: it.tipo });
    if (rIniciar.status !== 201) throw new Error(mensagemDe(rIniciar) || t('upload.erro_iniciar'));
    const { id, parte_bytes: parteBytes, partes } = rIniciar.json;
    aoIniciar(id, partes);
    for (let n = 1; n <= partes; n += 1) {
      if (it.cancelado) throw new Error(t('upload.cancelado'));
      const inicio = (n - 1) * parteBytes;
      const pedaco = arquivo.slice(inicio, inicio + parteBytes);
      aoProgredir(inicio, n);
      await enviarParte(it, tk, id, n, pedaco);
      aoProgredir(inicio + pedaco.size, n);
    }
    it.estado = 'concluindo';
    atualizarLinhas();
    const respConcluir = await fetch(`/api/uploads/${id}/concluir`, {
      method: 'POST', credentials: 'omit',
      headers: { authorization: `Bearer ${tk}`, 'content-type': 'application/json' }, body: '{}',
    });
    if (!respConcluir.ok) {
      const corpo = await respConcluir.json().catch(() => ({}));
      throw new Error(corpo.mensagem || t('upload.erro_concluir'));
    }
    return respConcluir.json();
  }

  /* PUT da parte por fetch com credentials:'omit' (só o token de serviço; ver o cabeçalho do arquivo) e
     AbortController para cancelar no meio; erro da API nomeado com a parte e a mensagem do servidor */
  async function enviarParte(it, tk, id, n, pedaco) {
    const aborto = new AbortController();
    it.aborto = aborto;
    let resp;
    try {
      resp = await fetch(`/api/uploads/${id}/partes/${n}`, {
        method: 'PUT', credentials: 'omit', signal: aborto.signal,
        headers: { authorization: `Bearer ${tk}`, 'content-type': 'application/octet-stream' }, body: pedaco,
      });
    } catch (e) {
      it.aborto = null;
      if (e && e.name === 'AbortError') throw new Error(t('upload.cancelado'));
      throw new Error(t('upload.erro_rede_parte', { n }));
    }
    it.aborto = null;
    if (resp.ok) return;
    const corpo = await resp.json().catch(() => ({}));
    throw new Error(corpo.mensagem ? `${t('upload.erro_parte', { n })}: ${corpo.mensagem}` : t('upload.erro_parte', { n }));
  }

  const area = h(
    'div', { class: 'upload-area' },
    h('div', { class: 'campo' }, h('label', { for: 'upload-tipo' }, t('upload.tipo')), selecao, h('span', { class: 'ajuda' }, t('upload.tipo_ajuda'))),
    entrada,
    dropzone,
    h('div', { class: 'botoes' }, botaoEnviar, botaoCancelar, botaoLimpar),
    barra,
    rotuloProgresso,
    fila,
    resultado,
  );
  principal.append(area);
  selecao.addEventListener('change', atualizarLinhas);
  aoTraduzir(() => atualizarLinhas());

  // exposto só para a suíte e2e medir (nunca para a aplicação): quantos arquivos há na fila e em que estado
  window.plat = window.plat || {};
  window.plat.uploads = { fila: () => itens.map((i) => ({ nome: i.arquivo.name, estado: i.estado, enviados: i.enviados, partes: i.partes })) };
}
