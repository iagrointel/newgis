/* plat — entrada. Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports
   (duas URLs do mesmo módulo = duas instâncias). Esta tela mostra versão e saúde lidas da API e, quando há
   sessão (marca local plat_sessao gravada no login), a barra lateral, os três passos (Envie · Organize ·
   Compartilhe — o mesmo envio+publicação de /uploads, extraído para js/uploads/nucleo.js), os itens
   publicados mais recentes e uma linha de atalhos para o resto do sistema. Sem a marca não chama /api/eu: a
   página inicial sem sessão não gera 401. */
import { obterJSON, formatarJSON, texto } from './js/core.js';
import { h, limpar } from './js/base/dom.js';
import './js/base/componentes.js';
import { carregar, t } from './js/base/i18n.js';
import { montarLayout, telasVisiveis } from './js/base/layout.js';
import { tem } from './js/base/estado.js';
import { sessaoProvavel, marcarSessao, urlLogin } from './js/auth/sessao.js';
import { listar as listarItens, tipos as tiposItem } from './js/catalogo/api.js';
import { enviarArquivo, publicar, abortar, obterTipos, formatarBytes, extensaoDe } from './js/uploads/nucleo.js';

async function mostrarVersao() {
  const r = await obterJSON('/api/versao');
  texto('versao-numero', r.json.versao);
  texto('versao-git', r.json.git_sha);
  texto('versao-ambiente', r.json.ambiente);
}

/* linha de estado única (pílula) — a porta do produto não é lugar de despejar JSON de saúde; o corpo
   completo continua disponível, só que dentro de <details id="detalhes-tecnicos"> fechado por padrão. */
async function mostrarSaude() {
  const r = await obterJSON('/saude');
  const ok = r.status === 200;
  const pilula = document.getElementById('saude-pilula');
  pilula.textContent = ok ? t('inicio.servico_ok') : t('inicio.servico_indisponivel');
  pilula.className = `estado ${ok ? 'ok' : 'falha'}`;
  document.getElementById('saude-json').textContent = formatarJSON(r.json);
}

function mostrarLinkEntrar() {
  const sec = document.getElementById('entrada');
  const p = document.getElementById('entrada-texto');
  limpar(p);
  p.append(h('a', { class: 'botao primario', href: urlLogin('/') }, t('nav.entrar')));
  sec.hidden = false;
}

function montarPassos() {
  const raiz = document.getElementById('passos');
  limpar(raiz);
  const passo = (n, chaveTitulo, chaveTexto) => h(
    'div', { class: 'passo' },
    h('span', { class: 'n' }, String(n)),
    h('h3', {}, t(chaveTitulo)),
    h('p', {}, t(chaveTexto)),
  );
  raiz.append(
    passo(1, 'inicio.enviar_titulo', 'inicio.enviar_texto'),
    passo(2, 'inicio.organizar_titulo', 'inicio.organizar_texto'),
    passo(3, 'inicio.compartilhar_titulo', 'inicio.compartilhar_texto'),
  );
}

/* zona de arrasto compacta: mesmo enviarArquivo/publicar de /uploads (js/uploads/nucleo.js), sem o seletor
   de tipo — detecta pela extensão e, se não achar, pede para usar /uploads (tela completa com o seletor). */
async function montarEnviar() {
  const raiz = document.getElementById('enviar-area');
  const tipos = await obterTipos();
  const aviso = h('plat-aviso');
  const entrada = h('input', { type: 'file', id: 'inicio-arquivo', class: 'sr-only' });
  const nomeArquivo = h('p', { id: 'inicio-nome' }, t('upload.nenhum_arquivo'));
  const dropzone = h(
    'div', { class: 'upload-dropzone', tabindex: '0', role: 'button', 'aria-label': t('upload.dropzone') },
    h('p', {}, t('upload.dropzone')),
    nomeArquivo,
  );
  let arquivoAtual = null;
  let tipoDeclarado = null;
  const escolher = (arquivo) => {
    arquivoAtual = arquivo;
    tipoDeclarado = tipos.find((tp) => tp.extensoes.includes(extensaoDe(arquivo.name)))?.tipo || null;
    nomeArquivo.textContent = `${arquivo.name} · ${formatarBytes(arquivo.size)}`;
    botaoEnviar.disabled = !tipoDeclarado;
    aviso.limpar();
    if (!tipoDeclarado) aviso.mostrar(t('upload.tipo_desconhecido'), 'atencao');
  };
  dropzone.addEventListener('click', () => entrada.click());
  dropzone.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); entrada.click(); } });
  dropzone.addEventListener('dragover', (ev) => { ev.preventDefault(); dropzone.classList.add('sobre'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('sobre'));
  dropzone.addEventListener('drop', (ev) => { ev.preventDefault(); dropzone.classList.remove('sobre'); if (ev.dataTransfer.files.length) escolher(ev.dataTransfer.files[0]); });
  entrada.addEventListener('change', () => { if (entrada.files[0]) escolher(entrada.files[0]); });

  const barra = h('progress', { max: '100', value: '0', hidden: true });
  const rotuloProgresso = h('p', { hidden: true });
  const botaoEnviar = h('button', { type: 'button', class: 'primario', disabled: true }, t('upload.enviar'));
  const resultado = h('div');
  let uploadEmCurso = null;
  const botaoCancelar = h('button', { type: 'button', class: 'texto', hidden: true }, t('upload.cancelar'));
  botaoCancelar.addEventListener('click', async () => {
    if (!uploadEmCurso) return;
    await abortar(uploadEmCurso);
    aviso.mostrar(t('upload.cancelado'), 'info');
    resetar();
  });
  function resetar() {
    uploadEmCurso = null;
    barra.hidden = true;
    rotuloProgresso.hidden = true;
    botaoCancelar.hidden = true;
    botaoEnviar.disabled = !arquivoAtual || !tipoDeclarado;
  }
  botaoEnviar.addEventListener('click', async () => {
    if (!arquivoAtual || !tipoDeclarado) return;
    aviso.limpar();
    limpar(resultado);
    botaoEnviar.disabled = true;
    botaoCancelar.hidden = false;
    barra.hidden = false;
    rotuloProgresso.hidden = false;
    barra.value = 0;
    let arquivoId = null;
    try {
      const concluido = await enviarArquivo(arquivoAtual, tipoDeclarado, {
        aoIniciar: (id) => { uploadEmCurso = id; },
        aoProgredir: (feitas, total) => { barra.value = Math.round((feitas / total) * 100); rotuloProgresso.textContent = t('upload.parte_de', { n: feitas, total }); },
      });
      arquivoId = concluido.arquivo_id;
      uploadEmCurso = null;
      botaoCancelar.hidden = true;
      aviso.ok(t('upload.concluido'));
      const { itemId, publicado } = await publicar(arquivoId, tipoDeclarado, arquivoAtual.name, {
        aoStatus: (msg) => { rotuloProgresso.textContent = msg; },
        aoProgredir: (pct) => { barra.value = pct; },
      });
      if (!publicado) resultado.append(h('p', { class: 'upload-ok' }, t('upload.formato_sem_publicacao')));
      location.assign(`/conteudo/${itemId}`);
    } catch (e) {
      aviso.erro(e.message || t('upload.erro_generico'));
      if (arquivoId) resultado.append(h('p', {}, h('a', { href: `/conteudo/${arquivoId}` }, t('upload.abrir_arquivo'))));
      resetar();
    }
  });

  raiz.append(aviso, entrada, dropzone, h('div', { class: 'botoes' }, botaoEnviar, botaoCancelar), barra, rotuloProgresso, resultado);
}

async function montarRecentes() {
  const raiz = document.getElementById('recentes-lista');
  limpar(raiz);
  let rotulos = {};
  try { rotulos = Object.fromEntries((await tiposItem()).map((tp) => [tp.nome, tp.rotulo])); } catch { /* segue sem rótulo bonito */ }
  try {
    const r = await listarItens({ tipo: ['camada_vetorial', 'raster'], ordenar: 'criado_em', limite: 6 });
    const itens = r.itens || [];
    if (!itens.length) { raiz.append(h('p', { class: 'fraco' }, t('inicio.recentes_vazio'))); return; }
    const lista = h('div', { class: 'lista-recentes' });
    for (const it of itens) {
      lista.append(h('a', { href: `/conteudo/${it.id}` }, h('span', {}, it.titulo), h('span', { class: 'tipo' }, rotulos[it.tipo] || it.tipo)));
    }
    raiz.append(lista);
  } catch (e) {
    raiz.append(h('p', { class: 'fraco' }, `${t('inicio.recentes_erro')} ${e.status === 401 ? '' : (e.message || '')}`.trim()));
  }
}

function montarAtalhos(usuario) {
  const raiz = document.getElementById('atalhos');
  limpar(raiz);
  for (const tela of telasVisiveis(usuario)) {
    if (tela.caminho === '/') continue;
    raiz.append(h('a', { href: tela.caminho }, t(tela.chave)));
  }
}

async function mostrarEntrada() {
  if (!sessaoProvavel()) { mostrarLinkEntrar(); return; }
  const r = await obterJSON('/api/eu');
  if (r.status !== 200) { marcarSessao(false); mostrarLinkEntrar(); return; }
  const usuario = r.json;
  montarLayout({ usuario, ativo: '/' });
  const sec = document.getElementById('entrada');
  document.getElementById('entrada-texto').textContent = t('inicio.ola', { nome: usuario.nome || usuario.login, inquilino: usuario.inquilino?.nome || '' });
  document.getElementById('conteudo-logado').hidden = false;
  montarPassos();
  montarAtalhos(usuario);
  sec.hidden = false;
  if (tem('conteudo.criar', usuario)) { await montarEnviar(); } else { document.getElementById('enviar-cartao').hidden = true; }
  await montarRecentes();
}

await carregar();
await Promise.all([mostrarVersao(), mostrarSaude(), mostrarEntrada()]);
document.body.dataset.pronto = '1';
