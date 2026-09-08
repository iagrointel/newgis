/* plat · análise — entrada da tela /analise (item L2-05-a-catalogo-ferramentas-gpserver).
   Módulos ES sem build; NUNCA ?v= nos imports (regra da casa). O formulário é gerado do manifesto de cada
   ferramenta (GET /api/ferramentas): GPFeatureRecordSetLayer vira seleção de camada do catálogo, GPLinearUnit vira
   número + unidade, GPBoolean caixa, GPDouble/GPLong número, GPString texto ou lista fechada, GPDate data.
   O envio vai a POST /api/ferramentas/{nome}/executar: 200 = rodou em processo; 202 = job, acompanhado por
   GET /api/jobs/{id} até o estado final. O resultado é um link para a ficha do item (com a proveniência). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

const UNIDADES = [
  { valor: 'esriMeters', rotulo: 'metros' }, { valor: 'esriKilometers', rotulo: 'quilômetros' },
  { valor: 'esriFeet', rotulo: 'pés' }, { valor: 'esriMiles', rotulo: 'milhas' },
];
let saindo = false;
const s = { ferramentas: [], camadas: [], rasters: [], atual: null };

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(id, texto, tipo = 'erro') {
  const n = document.getElementById(id);
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

/* um parâmetro do manifesto → um ou dois campos do <plat-formulario> */
function camposDe(p) {
  const base = { nome: p.nome, rotulo: p.rotulo, obrigatorio: p.obrigatorio && p.padrao === null, ajuda: p.descricao || '' };
  const tipo = p.tipo.startsWith('GPMultiValue:') ? p.tipo.slice('GPMultiValue:'.length) : p.tipo;
  switch (tipo) {
    case 'GPFeatureRecordSetLayer':
      return [{ ...base, tipo: 'select', opcoes: s.camadas.map((c) => ({ valor: c.id, rotulo: c.titulo })) }];
    /* item raster do inquilino; quando o parâmetro é de valor múltiplo, a tela escolhe UM e o envio o
       embrulha em lista (escolher vários numa só execução ainda é pela API). */
    case 'GPRasterDataLayer':
      return [{ ...base, tipo: 'select', opcoes: s.rasters.map((c) => ({ valor: c.id, rotulo: c.titulo })) }];
    case 'GPLinearUnit':
      return [
        { ...base, tipo: 'numero', padrao: p.padrao ? p.padrao.distance : 0, atributos: { min: 0, step: 'any' } },
        { nome: `${p.nome}__unidade`, rotulo: `${p.rotulo} (unidade)`, tipo: 'select', opcoes: UNIDADES, padrao: p.padrao ? p.padrao.units : 'esriMeters' },
      ];
    case 'GPBoolean':
      return [{ ...base, tipo: 'caixa', padrao: !!p.padrao, obrigatorio: false }];
    case 'GPDouble': case 'GPLong':
      return [{ ...base, tipo: 'numero', padrao: p.padrao ?? '', atributos: { min: p.minimo ?? undefined, max: p.maximo ?? undefined, step: tipo === 'GPLong' ? 1 : 'any' } }];
    case 'GPDate':
      return [{ ...base, tipo: 'texto', padrao: p.padrao ?? '', atributos: { type: 'date' } }];
    default:
      if (p.opcoes && p.opcoes.length) return [{ ...base, tipo: 'select', opcoes: p.opcoes.map((o) => ({ valor: o, rotulo: o })), padrao: p.padrao ?? p.opcoes[0] }];
      return [{ ...base, tipo: p.tipo.startsWith('GPMultiValue') ? 'lista' : 'texto', padrao: p.padrao ?? '' }];
  }
}

/* valores do formulário → parâmetros no vocabulário GP */
function parametrosDe(valores) {
  const saida = {};
  for (const p of s.atual.parametros.filter((x) => x.direcao === 'entrada')) {
    const v = valores[p.nome];
    if (p.tipo === 'GPLinearUnit') { saida[p.nome] = { distance: Number(v ?? 0), units: valores[`${p.nome}__unidade`] || 'esriMeters' }; continue; }
    if (v === '' || v === null || v === undefined) continue;
    saida[p.nome] = p.tipo === 'GPMultiValue:GPRasterDataLayer' && !Array.isArray(v) ? [v] : v;
  }
  return saida;
}

function montarFormulario() {
  const f = porId('formulario');
  const entradas = s.atual.parametros.filter((p) => p.direcao === 'entrada');
  f.campos = [
    ...entradas.flatMap(camposDe),
    { nome: 'titulo', rotulo: 'título do resultado', tipo: 'texto', obrigatorio: false, ajuda: 'em branco = nome da ferramenta e da entrada' },
  ];
  f.botoes = [{ id: 'executar', rotulo: 'executar', tipo: 'submit' }];
  porId('ferramenta-descricao').textContent = `${s.atual.descricao || ''} (v${s.atual.versao}; GPServer: ${s.atual.gpserver})`;
}

function estado(texto, pct) {
  porId('execucao').hidden = false;
  porId('execucao-estado').textContent = texto;
  if (pct !== undefined) porId('execucao-progresso').value = pct;
}

function resultado(itemId, feicoes, sha256, comoRodou) {
  const r = porId('execucao-resultado');
  limpar(r);
  r.append('resultado: ', h('a', { id: 'resultado-link', href: `/conteudo/${itemId}` }, itemId),
    ` · ${feicoes ?? '?'} feições · sha256 ${String(sha256 || '').slice(0, 16)} · ${comoRodou}`);
  r.dataset.itemId = itemId;
}

async function acompanhar(jobId) {
  for (;;) {
    const r = await api.obter(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (r.status !== 200) { aviso('execucao-aviso', `não foi possível ler o job: ${api.mensagemDe(r)}`); return; }
    const j = r.json;
    estado(`job ${jobId}: ${j.estado} — ${j.mensagem || ''}`, j.progresso);
    if (j.estado === 'concluido') { resultado(j.resultado.item_id, j.resultado.feicoes, j.resultado.sha256, `job ${jobId}`); return; }
    if (j.estado === 'falhou' || j.estado === 'cancelado') { aviso('execucao-aviso', `job ${j.estado}: ${j.erro || ''}`); return; }
    await new Promise((res) => setTimeout(res, 700));
  }
}

async function executar(valores) {
  const f = porId('formulario');
  aviso('execucao-aviso', '');
  f.ocupado = true;
  try {
    const corpo = { parametros: parametrosDe(valores), titulo: valores.titulo || null };
    estado('enviando…', 0);
    const r = await api.enviar(`/api/ferramentas/${encodeURIComponent(s.atual.nome)}/executar`, corpo);
    if (r.status === 200) { estado('concluído em processo', 100); resultado(r.json.item_id, r.json.feicoes, r.json.sha256, 'em processo'); return; }
    if (r.status === 202) { await acompanhar(r.json.job_id); return; }
    if (r.status === 422 && Array.isArray(r.json && r.json.detalhe)) {
      for (const d of r.json.detalhe) f.erro(d.campo, d.mensagem);
    }
    aviso('execucao-aviso', api.mensagemDe(r));
  } finally {
    f.ocupado = false;
  }
}

async function carregar() {
  const [rf, rc, rr] = await Promise.all([
    api.obter('/api/ferramentas'),
    api.obter('/api/itens?tipo=camada_vetorial&limite=200'),
    api.obter('/api/itens?tipo=raster&limite=200'),
  ]);
  if (rf.status !== 200) { aviso('aviso', `não foi possível listar as ferramentas: ${api.mensagemDe(rf)}`); return; }
  s.ferramentas = rf.json;
  s.camadas = rc.status === 200 ? (rc.json.itens || []) : [];
  s.rasters = rr.status === 200 ? (rr.json.itens || []) : [];
  const sel = porId('ferramenta');
  limpar(sel);
  for (const f of s.ferramentas) sel.append(h('option', { value: f.nome }, f.titulo));
  sel.addEventListener('change', () => { s.atual = s.ferramentas.find((f) => f.nome === sel.value); montarFormulario(); });
  s.atual = s.ferramentas[0] || null;
  if (s.atual) montarFormulario();
  porId('formulario').addEventListener('enviar', (e) => { executar(e.detail.valores); });
}

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/analise' });
  cabecalho('Análise');
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { saindo = true; irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
    const destino = caminhoPendencia(usuario.pendencias);
    if (destino) { saindo = true; location.replace(destino); return; }
  }
  layout(usuario);
  await carregar();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
