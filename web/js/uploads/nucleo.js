/* plat · uploads — núcleo do envio retomável + publicação automática (ADR 0005 seção 3), compartilhado pela
   tela /uploads (enviar.js) e pela zona de arrasto da tela inicial (app.js): mesmo upload em partes, mesma
   troca sessão→token, mesma decisão de publicar como raster (geotiff/jp2, `POST /api/imagens/ingestoes`) ou
   como camada vetorial (shapefile.zip/gpkg/geojson/csv, `POST /api/importacoes` → confirmar → carregar) ou,
   para os formatos que a ingestão ainda não lê, deixar como item 'arquivo' mesmo — nunca uma promessa sem data. */
import { obter, enviar, alterar } from '../base/api.js';
import { h } from '../base/dom.js';
import { t } from '../base/i18n.js';
import '../base/componentes.js';

const NOME_TOKEN = 'plat-uploads-tela';
/* app/ingestao/formatos.py FORMATOS: únicos formatos vetoriais com ingestão automática nesta passagem.
   app/uploads/tipos.py TIPOS: geotiff/jp2 são os dois tipos raster aceitos no upload. */
export const FORMATOS_VETOR = new Set(['shapefile.zip', 'gpkg', 'geojson', 'csv']);
export const TIPOS_RASTER = new Set(['geotiff', 'jp2']);
/* item L1-03-modelo3d: .ifc/.xkt viram job modelo3d.converter (POST /api/modelo3d/ingestoes); foto360 (.jpg
   equirretangular) não precisa de job — cria o item direto (POST /api/foto360, síncrono). */
export const TIPOS_MODELO3D = new Set(['ifc', 'xkt']);
export const TIPOS_FOTO360 = new Set(['foto360']);
const POLL_MS = 1500;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

let tokenServico = null;

async function token() {
  if (tokenServico) return tokenServico;
  const r = await enviar('/api/tokens', { nome: NOME_TOKEN, escopos: ['admin:inquilino'], validade_dias: 1 });
  if (r.status !== 201) throw new Error(r.json.mensagem || 'não foi possível preparar o envio');
  tokenServico = r.json.token;
  return tokenServico;
}

export function formatarBytes(n) {
  if (n === null || n === undefined) return '—';
  const unidades = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n, i = 0;
  while (v >= 1024 && i < unidades.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${unidades[i]}`;
}

export function extensaoDe(nome) {
  const i = nome.lastIndexOf('.');
  return i >= 0 ? nome.slice(i).toLowerCase() : '';
}

export async function obterTipos() {
  const r = await obter('/api/uploads/tipos');
  return r.status === 200 ? r.json : [];
}

export async function abortar(uploadId) {
  try {
    await fetch(`/api/uploads/${uploadId}`, { method: 'DELETE', credentials: 'omit', headers: { authorization: `Bearer ${await token()}` } });
  } catch { /* melhor esforço: o periódico de 24h limpa se isto falhar */ }
}

export async function enviarArquivo(arquivo, tipoDeclarado, { aoIniciar, aoProgredir }) {
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

/* ---------- publicação automática (raster/vetor) ---------- */

async function esperarJob(jobId, aoProgredir) {
  const t0 = Date.now();
  for (;;) {
    const r = await obter(`/api/jobs/${jobId}`);
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || t('upload.publicar_erro'));
    const job = r.json;
    aoProgredir(job);
    if (job.estado === 'concluido') return job;
    if (job.estado === 'erro' || job.estado === 'falhou') throw new Error(job.erro || t('upload.job_falhou', { erro: job.mensagem || job.estado }));
    if (job.estado === 'cancelado') throw new Error(t('upload.job_cancelado'));
    if (Date.now() - t0 > POLL_TIMEOUT_MS) throw new Error(t('upload.job_falhou', { erro: 'tempo esgotado' }));
    await new Promise((res) => { setTimeout(res, POLL_MS); });
  }
}

/* pergunta mínima na tela: só cobre os campos que app/ingestao/rotas.py::confirmar sabe responder (crs,
   codificacao) além de geometria (já respondida sozinha, sempre a 1ª opção da proposta). Qualquer outra
   pergunta pendente é reportada, nunca inventada. */
async function perguntarMinimo(pendentes, proposta) {
  const conhecidas = pendentes.filter((p) => p === 'crs' || p === 'codificacao');
  const desconhecidas = pendentes.filter((p) => p !== 'crs' && p !== 'codificacao');
  const avisoDesconhecidas = desconhecidas.length ? h('p', { class: 'fraco' }, t('upload.pergunta_desconhecida', { perguntas: desconhecidas.join(', ') })) : null;
  const d = document.body.appendChild(h('plat-dialogo', { id: 'upload-pergunta' }));
  if (!conhecidas.length) {
    await d.abrir({ titulo: t('upload.pergunta_titulo'), corpo: avisoDesconhecidas, botoes: [{ id: 'ok', rotulo: t('acao.fechar') }] });
    d.remove();
    return null;
  }
  const f = h('plat-formulario');
  const campos = [];
  if (conhecidas.includes('crs')) {
    campos.push({ nome: 'srid', rotulo: t('upload.pergunta_srid'), tipo: 'texto', obrigatorio: true,
      padrao: String((proposta.crs && proposta.crs.sugerido && proposta.crs.sugerido.srid) || 4326) });
  }
  if (conhecidas.includes('codificacao')) {
    const opcoes = (proposta.codificacao && proposta.codificacao.opcoes) || ['utf-8', 'latin1', 'windows-1252'];
    campos.push({ nome: 'codificacao', rotulo: t('upload.pergunta_codificacao'), tipo: 'select',
      opcoes: opcoes.map((v) => ({ valor: v, rotulo: v })) });
  }
  f.campos = campos;
  f.botoes = [{ id: 'ok', rotulo: t('upload.pergunta_confirmar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  let valores = null;
  f.addEventListener('enviar', (e) => { valores = e.detail.valores; d.fechar('ok'); });
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') d.fechar(null); });
  const r = await d.abrir({ titulo: t('upload.pergunta_titulo'), corpo: h('div', {}, avisoDesconhecidas, f) });
  d.remove();
  if (r !== 'ok' || !valores) return null;
  const respostas = {};
  if ('srid' in valores) respostas.crs = { srid: Number(valores.srid) };
  if ('codificacao' in valores) respostas.codificacao = { valor: valores.codificacao };
  return respostas;
}

async function publicarVetor(arquivoId, formato, { aoStatus, aoProgredir }) {
  const etapaInspecionando = t('upload.publicando_vetor', { etapa: t('upload.etapa_inspecionando') });
  const etapaCarregando = t('upload.publicando_vetor', { etapa: t('upload.etapa_carregando') });
  aoStatus(etapaInspecionando);
  aoProgredir(0);
  const rImp = await enviar('/api/importacoes', { arquivo_id: arquivoId, formato });
  if (rImp.status !== 202) throw new Error((rImp.json && rImp.json.mensagem) || t('upload.publicar_erro'));
  const { importacao_id: importacaoId, job_id: jobInspecao } = rImp.json;
  await esperarJob(jobInspecao, (j) => { aoProgredir(j.progresso ?? 0); aoStatus(`${etapaInspecionando} ${j.progresso ?? 0}%`); });

  const rGet = await obter(`/api/importacoes/${importacaoId}`);
  if (rGet.status !== 200) throw new Error((rGet.json && rGet.json.mensagem) || t('upload.publicar_erro'));
  const importacao = rGet.json;
  if (importacao.estado !== 'proposta') throw new Error(importacao.erro || t('upload.publicar_erro'));
  const proposta = importacao.proposta || {};

  const corpo = {};
  if (proposta.geometria && Array.isArray(proposta.geometria.opcoes) && proposta.geometria.opcoes.length) {
    corpo.geometria = { escolhida: proposta.geometria.escolhida || proposta.geometria.opcoes[0] };
  }
  let rConf = await alterar(`/api/importacoes/${importacaoId}/confirmar`, corpo);
  if (rConf.status === 422 && rConf.json && rConf.json.erro === 'perguntas_pendentes') {
    const pendentes = (rConf.json.detalhe && rConf.json.detalhe.perguntas) || [];
    const respostas = await perguntarMinimo(pendentes, proposta);
    if (!respostas) throw new Error(t('upload.publicacao_cancelada'));
    rConf = await alterar(`/api/importacoes/${importacaoId}/confirmar`, { ...corpo, ...respostas });
  }
  if (rConf.status !== 202) throw new Error((rConf.json && rConf.json.mensagem) || t('upload.publicar_erro'));

  aoStatus(etapaCarregando);
  aoProgredir(0);
  await esperarJob(rConf.json.job_id, (j) => { aoProgredir(j.progresso ?? 0); aoStatus(`${etapaCarregando} ${j.progresso ?? 0}%`); });
  return importacao.item_id;
}

/* Publica o item recém-enviado conforme o tipo declarado e devolve {itemId, publicado}. `publicado` é falso
   quando o formato ainda não tem publicação automática — o item 'arquivo' existe de qualquer forma (o
   `concluir` do upload sempre cria um), então `itemId` nunca falta. `aoStatus`/`aoProgredir` são opcionais. */
export async function publicar(arquivoId, tipoDeclarado, nomeArquivo, { aoStatus = () => {}, aoProgredir = () => {} } = {}) {
  if (TIPOS_RASTER.has(tipoDeclarado)) {
    aoStatus(t('upload.publicando_raster'));
    aoProgredir(0);
    const r = await enviar('/api/imagens/ingestoes', { arquivo_id: arquivoId, titulo: nomeArquivo });
    if (r.status !== 202) throw new Error((r.json && r.json.mensagem) || t('upload.publicar_erro'));
    const job = await esperarJob(r.json.job_id, (j) => { aoProgredir(j.progresso ?? 0); aoStatus(`${t('upload.publicando_raster')} ${j.progresso ?? 0}%`); });
    const itemId = job.resultado && job.resultado.item_id;
    if (!itemId) throw new Error(t('upload.publicar_erro'));
    return { itemId, publicado: true };
  }
  if (FORMATOS_VETOR.has(tipoDeclarado)) {
    const itemId = await publicarVetor(arquivoId, tipoDeclarado, { aoStatus, aoProgredir });
    return { itemId, publicado: true };
  }
  if (TIPOS_MODELO3D.has(tipoDeclarado)) {
    aoStatus(t('upload.publicando_modelo3d'));
    aoProgredir(0);
    const r = await enviar('/api/modelo3d/ingestoes', { arquivo_id: arquivoId, titulo: nomeArquivo });
    if (r.status !== 202) throw new Error((r.json && r.json.mensagem) || t('upload.publicar_erro'));
    const job = await esperarJob(r.json.job_id, (j) => { aoProgredir(j.progresso ?? 0); aoStatus(`${t('upload.publicando_modelo3d')} ${j.progresso ?? 0}%`); });
    const itemId = job.resultado && job.resultado.item_id;
    if (!itemId) throw new Error(t('upload.publicar_erro'));
    return { itemId, publicado: true };
  }
  if (TIPOS_FOTO360.has(tipoDeclarado)) {
    aoStatus(t('upload.publicando_foto360'));
    aoProgredir(0);
    const r = await enviar('/api/foto360', { arquivo_id: arquivoId, titulo: nomeArquivo });
    if (r.status !== 201) throw new Error((r.json && r.json.mensagem) || t('upload.publicar_erro'));
    aoProgredir(100);
    return { itemId: r.json.item_id, publicado: true };
  }
  return { itemId: arquivoId, publicado: false };
}
