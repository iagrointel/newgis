/* plat — tela /uploads (item L0-04-a-upload-arquivo; ADR 0005 seção 3): upload retomável em partes de 16 MiB,
   com barra de progresso, cota do inquilino e recusa por tipo x conteúdo. A sessão (cookie) só assina
   `POST /api/uploads` (JSON, CSRF-seguro); o envio das partes e a conclusão exigem um TOKEN de serviço — a
   própria tela troca a sessão por um token de escopo restrito (`POST /api/tokens`, uma vez por carregamento de
   página, igual ao que `app.rotas_arquivos`/`app.uploads.rotas` documentam no backend) e usa esse token só em
   memória, nunca localStorage: um recarregamento de página pede um token novo. */
import { obter, enviar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const NOME_TOKEN = 'plat-uploads-tela';

await carregar();
const usuario = await exigirSessao({ privilegio: 'conteudo.criar' });
if (usuario) iniciar();
pronto();

let tokenServico = null;

async function token() {
  if (tokenServico) return tokenServico;
  const r = await enviar('/api/tokens', { nome: NOME_TOKEN, escopos: ['admin:inquilino'], validade_dias: 1 });
  if (r.status !== 201) throw new Error(r.json.mensagem || 'não foi possível preparar o envio');
  tokenServico = r.json.token;
  return tokenServico;
}

function formatarBytes(n) {
  if (n === null || n === undefined) return '—';
  const unidades = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n, i = 0;
  while (v >= 1024 && i < unidades.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${unidades[i]}`;
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

async function montarTela() {
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');

  const rTipos = await obter('/api/uploads/tipos');
  const tipos = rTipos.status === 200 ? rTipos.json : [];

  const selecao = h(
    'select', { id: 'upload-tipo' },
    h('option', { value: '' }, t('upload.tipo_detectar')),
    ...tipos.map((tp) => h('option', { value: tp.tipo }, `${tp.rotulo} (${tp.extensoes.join(', ')})`)),
  );

  const entrada = h('input', { type: 'file', id: 'upload-arquivo', class: 'sr-only', 'aria-label': t('upload.escolher') });
  const nomeArquivo = h('p', { id: 'upload-nome' }, t('upload.nenhum_arquivo'));
  const dropzone = h(
    'div', { id: 'upload-dropzone', class: 'upload-dropzone', tabindex: '0', role: 'button',
             'aria-label': t('upload.dropzone') },
    h('p', {}, t('upload.dropzone')),
    nomeArquivo,
  );
  dropzone.addEventListener('click', () => entrada.click());
  dropzone.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); entrada.click(); } });
  dropzone.addEventListener('dragover', (ev) => { ev.preventDefault(); dropzone.classList.add('sobre'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('sobre'));
  dropzone.addEventListener('drop', (ev) => {
    ev.preventDefault();
    dropzone.classList.remove('sobre');
    if (ev.dataTransfer.files.length) { entrada.files = ev.dataTransfer.files; arquivoEscolhido(); }
  });

  let arquivoAtual = null;
  function arquivoEscolhido() {
    arquivoAtual = entrada.files[0] || null;
    if (arquivoAtual) {
      nomeArquivo.textContent = `${arquivoAtual.name} · ${formatarBytes(arquivoAtual.size)}`;
      const ext = extensaoDe(arquivoAtual.name);
      const achado = tipos.find((tp) => tp.extensoes.includes(ext));
      if (achado) selecao.value = achado.tipo;
    } else {
      nomeArquivo.textContent = t('upload.nenhum_arquivo');
    }
  }
  entrada.addEventListener('change', arquivoEscolhido);

  const barra = h('progress', { id: 'upload-progresso', max: '100', value: '0', hidden: true });
  const rotuloProgresso = h('p', { id: 'upload-rotulo-progresso', hidden: true });
  const botaoEnviar = h('button', { type: 'button', class: 'primario', id: 'upload-enviar' }, t('upload.enviar'));
  const botaoCancelar = h('button', { type: 'button', class: 'texto', id: 'upload-cancelar', hidden: true }, t('upload.cancelar'));
  const resultado = h('div', { id: 'upload-resultado' });

  let uploadEmCurso = null;
  botaoCancelar.addEventListener('click', async () => {
    if (!uploadEmCurso) return;
    try {
      await fetch(`/api/uploads/${uploadEmCurso}`, { method: 'DELETE', credentials: 'omit', headers: { authorization: `Bearer ${await token()}` } });
    } catch { /* melhor esforço: o periódico de 24h limpa se isto falhar */ }
    aviso.mostrar(t('upload.cancelado'), 'info');
    resetar();
  });

  function resetar() {
    uploadEmCurso = null;
    barra.hidden = true;
    rotuloProgresso.hidden = true;
    botaoCancelar.hidden = true;
    botaoEnviar.disabled = false;
  }

  botaoEnviar.addEventListener('click', async () => {
    if (!arquivoAtual) { aviso.erro(t('upload.escolha_um_arquivo')); return; }
    const tipoDeclarado = selecao.value || tipos.find((tp) => tp.extensoes.includes(extensaoDe(arquivoAtual.name)))?.tipo;
    if (!tipoDeclarado) { aviso.erro(t('upload.tipo_desconhecido')); return; }
    aviso.limpar();
    limpar(resultado);
    botaoEnviar.disabled = true;
    barra.hidden = false;
    rotuloProgresso.hidden = false;
    botaoCancelar.hidden = false;
    barra.value = 0;
    try {
      await enviarArquivo(arquivoAtual, tipoDeclarado, {
        aoIniciar: (id) => { uploadEmCurso = id; },
        aoProgredir: (feitas, total) => {
          barra.value = Math.round((feitas / total) * 100);
          rotuloProgresso.textContent = t('upload.parte_de', { n: feitas, total });
        },
      });
      aviso.ok(t('upload.concluido'));
      resultado.append(h('p', { class: 'upload-ok' }, t('upload.arquivo_pronto')));
    } catch (e) {
      aviso.erro(e.message || t('upload.erro_generico'));
    } finally {
      resetar();
    }
  });

  const area = h(
    'div', { class: 'upload-area' },
    h('div', { class: 'campo' }, h('label', { for: 'upload-tipo' }, t('upload.tipo')), selecao),
    entrada,
    dropzone,
    h('div', { class: 'botoes' }, botaoEnviar, botaoCancelar),
    barra,
    rotuloProgresso,
    resultado,
  );
  principal.append(area);
}

async function enviarArquivo(arquivo, tipoDeclarado, { aoIniciar, aoProgredir }) {
  const tk = await token();
  const rIniciar = await enviar('/api/uploads', { nome: arquivo.name, bytes: arquivo.size, tipo_declarado: tipoDeclarado });
  if (rIniciar.status !== 201) throw new Error(rIniciar.json.mensagem || t('upload.erro_iniciar'));
  const { id, parte_bytes: parteBytes, partes } = rIniciar.json;
  aoIniciar(id);

  for (let n = 1; n <= partes; n += 1) {
    const inicio = (n - 1) * parteBytes;
    const pedaco = arquivo.slice(inicio, inicio + parteBytes);
    const resp = await fetch(`/api/uploads/${id}/partes/${n}`, {
      method: 'PUT',
      credentials: 'omit',
      headers: { authorization: `Bearer ${tk}`, 'content-type': 'application/octet-stream' },
      body: pedaco,
    });
    if (!resp.ok) {
      const corpo = await resp.json().catch(() => ({}));
      throw new Error(corpo.mensagem || t('upload.erro_parte', { n }));
    }
    aoProgredir(n, partes);
  }

  const respConcluir = await fetch(`/api/uploads/${id}/concluir`, {
    method: 'POST',
    credentials: 'omit',
    headers: { authorization: `Bearer ${tk}`, 'content-type': 'application/json' },
    body: '{}',
  });
  if (!respConcluir.ok) {
    const corpo = await respConcluir.json().catch(() => ({}));
    throw new Error(corpo.mensagem || t('upload.erro_concluir'));
  }
  return respConcluir.json();
}
