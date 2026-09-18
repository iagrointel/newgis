/* plat — tela /admin/uso (item L0-07-c-cotas-uso): a conta do inquilino contra as cotas em vigor.

   Uma chamada só (GET /api/uso?dias=N) traz três coisas que a tela mostra juntas de propósito: a série
   diária de plat.uso_inquilino (escrita pelo periódico jobs.uso_medir), as cotas do inquilino e os
   contadores VIVOS ("agora"). Sem o "agora" a tela mentiria por até 24 h — antes de o periódico do dia
   rodar, o último ponto é o de ontem —, e sem as cotas o número não diz nada: 4 GB é pouco ou muito
   conforme o teto.

   O gráfico é SVG desenhado aqui, sem biblioteca: a CSP do produto não deixa carregar script de fora, e
   uma linha com eixo não justifica um pacote. */
import { obter, mensagemDe } from '../base/api.js';
import { h } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const DIAS_PADRAO = 30;
const LARGURA = 720;
const ALTURA = 200;
const MARGEM = { esquerda: 64, direita: 12, cima: 12, baixo: 24 };

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.configurar' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/uso' });
  const seletor = h('select', { id: 'dias', 'aria-label': t('uso.janela') },
    ...[7, 30, 90, 365].map((d) => h('option', { value: String(d), selected: d === DIAS_PADRAO ? '' : null },
      t('uso.dias_n').replace('{n}', String(d)))));
  seletor.addEventListener('change', () => carregarSerie(Number(seletor.value)));
  cabecalho(t('uso.titulo'), { botoes: [seletor] });
  montarTabela();
  await carregarSerie(DIAS_PADRAO);
}

function bytesFmt(n) {
  if (n === null || n === undefined) return '';
  const v = Number(n);
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(0)} KB`;
  if (v < 1024 * 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MB`;
  return `${(v / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function montarTabela() {
  const tb = document.getElementById('tabela-serie');
  tb.colunas = [
    { chave: 'dia', titulo: t('uso.dia'), formatar: (v) => formatarData(v) },
    { chave: 'bytes_banco', titulo: t('uso.banco'), classe: 'num', formatar: bytesFmt },
    { chave: 'bytes_bucket', titulo: t('uso.bucket'), classe: 'num', formatar: bytesFmt },
    { chave: 'itens', titulo: t('uso.itens'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'usuarios_ativos_30d', titulo: t('uso.usuarios_ativos'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'jobs', titulo: t('uso.jobs'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'requisicoes', titulo: t('uso.requisicoes'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'bytes_servidos', titulo: t('uso.servidos'), classe: 'num', formatar: bytesFmt },
  ];
  tb.vazio = t('uso.sem_pontos');
}

async function carregarSerie(dias) {
  const aviso = document.getElementById('aviso');
  const r = await obter(`/api/uso?dias=${encodeURIComponent(dias)}`);
  if (r.status !== 200) { aviso.erro = mensagemDe(r); return; }
  aviso.erro = '';
  const dados = r.json;
  const tb = document.getElementById('tabela-serie');
  tb.linhas = dados.pontos;
  document.getElementById('serie-total').textContent = formatarNumero(dados.pontos.length);
  desenharAgora(dados);
  desenharGrafico(dados.pontos, dados.cotas.cota_bytes);
}

function barra(rotulo, valor, teto, formatar) {
  /* Uma linha por cota: rótulo, consumo, teto e uma barra de proporção. Sem teto declarado a barra não
     aparece (não há do que ser "80 %"), e o texto diz "sem teto" em vez de inventar um. */
  const partes = [h('dt', {}, rotulo)];
  if (teto) {
    const fracao = Math.min(1, Number(valor) / Number(teto));
    const estado = fracao >= 0.9 ? 'falha' : (fracao >= 0.75 ? 'aviso' : 'ok');
    partes.push(h('dd', {},
      h('span', { class: 'mono' }, `${formatar(valor)} / ${formatar(teto)}`),
      h('span', { class: 'fraco' }, ` (${(fracao * 100).toFixed(1)} %)`),
      h('div', { class: `barra barra-${estado}`, role: 'img',
        'aria-label': `${(fracao * 100).toFixed(0)} %` },
        h('i', { style: `width:${(fracao * 100).toFixed(1)}%` }))));
  } else {
    partes.push(h('dd', {}, h('span', { class: 'mono' }, formatar(valor)),
      h('span', { class: 'fraco' }, ` · ${t('uso.sem_teto')}`)));
  }
  return partes;
}

function desenharAgora(dados) {
  const a = dados.agora;
  const c = dados.cotas;
  const num = (v) => formatarNumero(v);
  const lista = h('dl', { class: 'cotas' },
    ...barra(t('uso.armazenamento'), a.bytes_total, c.cota_bytes, bytesFmt),
    ...barra(t('uso.itens'), a.itens, c.cota_itens, num),
    ...barra(t('uso.usuarios'), a.usuarios_total, c.cota_usuarios, num),
    ...barra(t('uso.jobs_hoje'), a.jobs_hoje, c.cota_jobs_dia, num));
  const quando = dados.ultimo_medido_em
    ? t('uso.ultima_medicao').replace('{quando}', formatarData(dados.ultimo_medido_em))
    : t('uso.nunca_medido');
  document.getElementById('agora-corpo').replaceChildren(
    lista,
    h('p', { class: 'fraco' }, `${t('uso.lixeira_conta')} · ${quando}`),
  );
}

function svg(nome, atributos, ...filhos) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', nome);
  for (const [k, v] of Object.entries(atributos || {})) if (v !== null) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

function desenharGrafico(pontos, cota) {
  const alvo = document.getElementById('grafico-corpo');
  if (!pontos.length) { alvo.replaceChildren(h('p', { class: 'fraco' }, t('uso.sem_pontos'))); return; }
  const valores = pontos.map((p) => p.bytes_total);
  const teto = Math.max(...valores, cota ? Number(cota) : 0) || 1;
  const largura = LARGURA - MARGEM.esquerda - MARGEM.direita;
  const altura = ALTURA - MARGEM.cima - MARGEM.baixo;
  const x = (i) => MARGEM.esquerda + (pontos.length === 1 ? largura / 2 : (i * largura) / (pontos.length - 1));
  const y = (v) => MARGEM.cima + altura - (v / teto) * altura;
  const caminho = valores.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const filhos = [
    svg('line', { x1: MARGEM.esquerda, y1: MARGEM.cima + altura, x2: LARGURA - MARGEM.direita,
      y2: MARGEM.cima + altura, class: 'eixo' }),
    svg('path', { d: caminho, class: 'serie', fill: 'none' }),
  ];
  if (cota) {
    filhos.push(svg('line', { x1: MARGEM.esquerda, y1: y(Number(cota)), x2: LARGURA - MARGEM.direita,
      y2: y(Number(cota)), class: 'cota' }));
    filhos.push(svg('text', { x: MARGEM.esquerda, y: Math.max(10, y(Number(cota)) - 4), class: 'rotulo' },
      `${t('uso.cota')} ${bytesFmt(cota)}`));
  }
  filhos.push(svg('text', { x: 4, y: MARGEM.cima + 10, class: 'rotulo' }, bytesFmt(teto)));
  filhos.push(svg('text', { x: 4, y: MARGEM.cima + altura, class: 'rotulo' }, '0'));
  const grafico = svg('svg', { viewBox: `0 0 ${LARGURA} ${ALTURA}`, class: 'grafico-uso', role: 'img',
    'aria-label': t('uso.grafico_alt').replace('{n}', String(pontos.length)) }, ...filhos);
  alvo.replaceChildren(grafico);
}
