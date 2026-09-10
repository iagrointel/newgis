/* plat — tela /uploads (item L0-04-a-upload-arquivo; ADR 0005 seção 3): upload retomável em partes de 16 MiB,
   com barra de progresso, cota do inquilino e recusa por tipo x conteúdo. A troca sessão→token e o envio em
   si vivem em uploads/nucleo.js (compartilhado com a zona de arrasto da tela inicial, app.js). Depois que o
   arquivo chega, esta tela publica sozinha: raster (geotiff, jp2) vira imagem; os formatos vetoriais que a
   ingestão já lê (shapefile.zip, gpkg, geojson, csv) viram camada vetorial; os demais tipos aceitos no upload
   (kml, kmz, gpx, xlsx, dxf, dwg, gdb.zip, parquet, fgb, gml, zip) ainda não têm publicação automática nesta
   instalação — o arquivo fica como item 'arquivo' mesmo, e é para lá que a tela leva. */
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { enviarArquivo, publicar, abortar, obterTipos, formatarBytes, extensaoDe } from './nucleo.js';

await carregar();
const usuario = await exigirSessao({ privilegio: 'conteudo.criar' });
if (usuario) iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/uploads' });
  cabecalho(t('upload.titulo'));
  await montarTela();
}

async function montarTela() {
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const tipos = await obterTipos();

  const selecao = h(
    'select', { id: 'upload-tipo' },
    h('option', { value: '' }, t('upload.tipo_detectar')),
    ...tipos.map((tp) => h('option', { value: tp.tipo }, `${tp.rotulo} (${tp.extensoes.join(', ')})`)),
  );

  const entrada = h('input', { type: 'file', id: 'upload-arquivo', class: 'sr-only' });
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
    await abortar(uploadEmCurso);
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
    let arquivoId = null;
    try {
      const concluido = await enviarArquivo(arquivoAtual, tipoDeclarado, {
        aoIniciar: (id) => { uploadEmCurso = id; },
        aoProgredir: (feitas, total) => {
          barra.value = Math.round((feitas / total) * 100);
          rotuloProgresso.textContent = t('upload.parte_de', { n: feitas, total });
        },
      });
      arquivoId = concluido.arquivo_id;
      uploadEmCurso = null;
      botaoCancelar.hidden = true;
      aviso.ok(t('upload.concluido'));
      const { itemId, publicado } = await publicar(arquivoId, tipoDeclarado, arquivoAtual.name, {
        aoStatus: (msg) => { rotuloProgresso.textContent = msg; },
        aoProgredir: (pct) => { barra.value = pct; },
      });
      if (publicado) {
        aviso.ok(t('upload.publicado_ir'));
      } else {
        resultado.append(h('p', { class: 'upload-ok' }, t('upload.formato_sem_publicacao')));
      }
      location.assign(`/conteudo/${itemId}`);
    } catch (e) {
      aviso.erro(e.message || t('upload.erro_generico'));
      if (arquivoId) resultado.append(h('p', {}, h('a', { href: `/conteudo/${arquivoId}` }, t('upload.abrir_arquivo'))));
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
