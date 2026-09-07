/* plat — seção "Exportar meu inquilino" da tela /admin/organizacao (item L0-06-d-exportar-inquilino).

   Três coisas na tela, nessa ordem: o tamanho ESTIMADO do pacote (GET /api/inquilino/exportar/estimativa,
   antes de qualquer clique), o botão que pede (POST /api/inquilino/exportar) e a lista das exportações deste
   inquilino com estado, tamanho e link de download. Enquanto uma está pendente ou gerando, a lista se
   reconsulta a cada 2 s — a mesma cadência da tela de tarefas, e o relógio para sozinho quando não há mais
   nada em curso ou quando a seção sai da página.

   A cota é de uma execução por dia: quando ela já foi gasta, o botão fica desativado com a razão escrita ao
   lado, em vez de deixar o admin clicar para receber 429. O 429 continua tratado, porque duas abas abertas
   podem clicar no mesmo segundo. */
import { obter, enviar, apagar, mensagemDe } from '../base/api.js';
import { t } from '../base/i18n.js';
import { h, limpar } from '../base/dom.js';
import { tem } from '../base/estado.js';

const EM_CURSO = new Set(['pendente', 'gerando']);
const INTERVALO_MS = 2000;
let relogio = null;

export async function montarExportacao(aviso, usuario) {
  /* a tela inteira exige `org.configurar`; ESTA seção exige `org.exportar`, que é outro privilégio (o pacote
     leva o dado de todos os membros). Quem configura mas não exporta simplesmente não vê a seção — melhor
     que mostrar um cartão que só sabe responder "sem permissão". */
  if (!tem('org.exportar', usuario)) {
    document.getElementById('exportar-inquilino')?.remove();
    return;
  }
  document.getElementById('exp-pedir').addEventListener('click', () => pedir(aviso));
  await Promise.all([montarEstimativa(), montarLista(aviso)]);
}

function formatarBytes(n) {
  if (n === null || n === undefined) return '—';
  if (n < 1024) return `${n} B`;
  const unidades = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < unidades.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${unidades[i]}`;
}

async function montarEstimativa() {
  const alvo = document.getElementById('exp-estimativa');
  const botao = document.getElementById('exp-pedir');
  const r = await obter('/api/inquilino/exportar/estimativa');
  if (r.status !== 200) { alvo.textContent = mensagemDe(r); return; }
  const e = r.json;
  alvo.textContent = t('orgexp.estimativa', {
    tamanho: formatarBytes(e.bytes), itens: e.n_itens, camadas: e.n_camadas, arquivos: e.n_arquivos,
  });
  botao.disabled = !e.disponivel;
  const cota = document.getElementById('exp-cota');
  cota.hidden = e.disponivel;
  cota.textContent = e.disponivel ? '' : t('orgexp.cota_gasta', { maximo: e.maximo_por_dia });
}

async function pedir(aviso) {
  const botao = document.getElementById('exp-pedir');
  aviso.limpar();
  botao.disabled = true;
  const r = await enviar('/api/inquilino/exportar', {});
  if (r.status !== 202) {
    aviso.erro(mensagemDe(r));
    if (r.status !== 429) botao.disabled = false;
    return;
  }
  aviso.ok(t('orgexp.pedida', { tamanho: formatarBytes(r.json.estimativa_bytes) }));
  await montarLista(aviso);
  await montarEstimativa();
}

async function montarLista(aviso) {
  const alvo = document.getElementById('exp-lista');
  if (!alvo || !alvo.isConnected) { pararRelogio(); return; }
  const r = await obter('/api/inquilino/exportacoes?limite=10');
  if (r.status !== 200) { alvo.textContent = mensagemDe(r); return; }
  limpar(alvo);
  const itens = r.json.itens;
  if (!itens.length) {
    alvo.append(h('p', { class: 'fraco', id: 'exp-vazio' }, t('orgexp.vazio')));
    pararRelogio();
    return;
  }
  const tabela = h('plat-tabela', { id: 'exp-tabela', legenda: t('orgexp.titulo') });
  tabela.colunas = [
    { chave: 'criado_em', titulo: t('orgexp.quando'), formatar: (v) => new Date(v).toLocaleString('pt-BR') },
    { chave: 'estado', titulo: t('orgexp.estado'), formatar: (v) => t(`orgexp.estado_${v}`) },
    { chave: 'n_camadas', titulo: t('orgexp.camadas'), formatar: (v) => (v === null ? '—' : String(v)) },
    { chave: 'n_arquivos', titulo: t('orgexp.arquivos'), formatar: (v) => (v === null ? '—' : String(v)) },
    { chave: 'bytes', titulo: t('orgexp.tamanho'), formatar: formatarBytes },
    {
      chave: 'link',
      titulo: t('orgexp.pacote'),
      formatar: (v, linha) => (v
        ? h('a', { href: v, download: 'inquilino_exportado.zip', class: 'exp-baixar' }, t('orgexp.baixar'))
        : (linha.erro || '—')),
    },
  ];
  tabela.linhas = itens;
  tabela.acoes = (linha) => (linha.estado === 'expirada' || linha.estado === 'cancelada' || linha.estado === 'falhou'
    ? []
    : [{ id: 'apagar', rotulo: t('orgexp.apagar'), classe: 'perigo' }]);
  tabela.addEventListener('acao', async (ev) => {
    const r2 = await apagar(`/api/inquilino/exportacoes/${ev.detail.linha.id}`);
    if (r2.status !== 204) { aviso.erro(mensagemDe(r2)); return; }
    await montarLista(aviso);
  });
  alvo.append(tabela);
  if (itens.some((i) => EM_CURSO.has(i.estado))) ligarRelogio(aviso); else pararRelogio();
}

function ligarRelogio(aviso) {
  if (relogio) return;
  relogio = setInterval(() => { montarLista(aviso); }, INTERVALO_MS);
}

function pararRelogio() {
  if (!relogio) return;
  clearInterval(relogio);
  relogio = null;
}
