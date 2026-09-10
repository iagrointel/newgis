/* plat · sistema de referência — entrada da tela /crs (item L2-17-crs-transformacoes).
   Módulos ES sem build; NUNCA ?v= nos imports (regra da casa — duas instâncias do módulo, app morre).
   Lista os CRS do serviço (/api/crs, curada do Brasil primeiro — a ORDEM que a API devolve é preservada
   aqui, tanto na tabela quanto nos dois <select> de origem/destino) e transforma ponto ou bbox por
   /api/crs/transformar, mostrando qual transformação foi usada (grade NTv2 do IBGE, parâmetros sem
   grade, ou projeção direta) — nunca escondida. */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

let saindo = false;
const s = { crs: [] };

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

function linhaTabela(d) {
  return h('tr', { dataset: { epsg: d.epsg, curada: d.curada ? '1' : '0' } },
    h('td', {}, String(d.epsg)),
    h('td', {}, d.nome),
    h('td', {}, d.tipo),
    h('td', { title: d.motivo_curada || '' }, d.area_nome || '—'),
    h('td', {}, d.curada ? h('span', { class: 'marcador ok' }, 'curada') : ''));
}

function opcao(d) {
  return h('option', { value: String(d.epsg) }, `${d.epsg} — ${d.nome}${d.curada ? ' ★' : ''}`);
}

function montarSeletores() {
  const origem = porId('origem');
  const destino = porId('destino');
  limpar(origem);
  limpar(destino);
  // a ORDEM de s.crs é a ordem que a API devolveu (curada primeiro) — nenhum sort aqui, de propósito:
  // é a cláusula "lista curada aparece primeiro nos seletores" (tests/e2e/test_crs.py confere isto no DOM).
  for (const d of s.crs) {
    origem.append(opcao(d));
    destino.append(opcao(d));
  }
  // padrão útil: origem SIRGAS2000 geográfico (4674), destino UTM 22S (31982) — os dois primeiros da curada
  const sirgas = s.crs.find((d) => d.epsg === 4674);
  const utm22s = s.crs.find((d) => d.epsg === 31982);
  if (sirgas) origem.value = '4674';
  if (utm22s) destino.value = '31982';
}

async function carregarLista() {
  aviso('aviso', '');
  const r = await api.obter('/api/crs');
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('aviso', `não foi possível carregar a lista de CRS (${api.mensagemDe(r)})`);
    return;
  }
  s.crs = r.json.itens || [];
  porId('lista-total').textContent = `(${r.json.total}, ${r.json.curados} curados)`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  for (const d of s.crs) corpo.append(linhaTabela(d));
  montarSeletores();
}

function alternarTipo() {
  const bbox = porId('tipo').value === 'bbox';
  for (const id of ['lon', 'lat']) {
    porId(`campos-ponto-${id}`).hidden = bbox;
    porId(id).required = !bbox;
  }
  for (const id of ['xmin', 'ymin', 'xmax', 'ymax']) {
    porId(`campos-bbox-${id}`).hidden = !bbox;
    porId(id).required = bbox;
  }
}

const CACHE_PROJ4 = new Map();

async function proj4Def(epsg) {
  if (CACHE_PROJ4.has(epsg)) return CACHE_PROJ4.get(epsg);
  const resp = await fetch(`/api/crs/${epsg}.proj4`, { credentials: 'same-origin', cache: 'no-store' });
  const texto = resp.ok ? (await resp.text()).trim() : null;
  CACHE_PROJ4.set(epsg, texto);
  return texto;
}

/* prévia em 3857 calculada no PRÓPRIO NAVEGADOR (proj4js, window.proj4 — vendorizado, sem CDN), com as
   MESMAS definições que o backend serve por /api/crs/{epsg}.proj4 (nunca uma definição hardcoded aqui
   que possa divergir). Só para CRS sem grade de datum (o mapa/formulário não pede reprojeção de datum
   legado no navegador — isso fica no backend, que tem a grade NTv2). Falha em silêncio (campo some) se
   o EPSG de destino do resultado for um datum legado ou algo que o proj4js não resolva sozinho. */
async function calcularPrevia3857(destinoEpsg, coordenadas) {
  const alvo = porId('resultado-3857');
  alvo.textContent = '';
  if (!window.proj4 || destinoEpsg === 3857) { alvo.textContent = destinoEpsg === 3857 ? JSON.stringify(coordenadas) : '—'; return; }
  try {
    const defOrigem = await proj4Def(destinoEpsg);
    const def3857 = await proj4Def(3857);
    if (!defOrigem || !def3857) { alvo.textContent = '—'; return; }
    window.proj4.defs(`EPSG:${destinoEpsg}`, defOrigem);
    window.proj4.defs('EPSG:3857', def3857);
    const [x, y] = window.proj4(`EPSG:${destinoEpsg}`, 'EPSG:3857', coordenadas.length === 4
      ? [coordenadas[0], coordenadas[1]] : coordenadas);
    alvo.textContent = `${x.toFixed(3)}, ${y.toFixed(3)}`;
  } catch {
    alvo.textContent = '—';
  }
}

function mostrarResultado(json) {
  porId('resultado').hidden = false;
  porId('resultado-coordenadas').textContent = JSON.stringify(json.coordenadas);
  porId('resultado-transformacao').textContent = json.transformacao_usada
    || (json.transformacoes_usadas || []).join(', ');
  porId('resultado-cobertura').textContent = json.cobertura
    || (json.cobertura_uniforme === false ? 'NÃO uniforme entre os cantos do bbox' : 'uniforme');
  const destino = Number(porId('destino').value);
  calcularPrevia3857(destino, json.coordenadas);
}

async function aoSubmeter(ev) {
  ev.preventDefault();
  aviso('transformar-aviso', '');
  porId('resultado').hidden = true;
  const origem = Number(porId('origem').value);
  const destino = Number(porId('destino').value);
  const tipo = porId('tipo').value;
  const coordenadas = tipo === 'bbox'
    ? [porId('xmin').value, porId('ymin').value, porId('xmax').value, porId('ymax').value].map(Number)
    : [porId('lon').value, porId('lat').value].map(Number);
  const r = await api.enviar('/api/crs/transformar', { origem, destino, tipo, coordenadas });
  if (r.status !== 200) {
    aviso('transformar-aviso', api.mensagemDe(r));
    return;
  }
  mostrarResultado(r.json);
}

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/crs' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Sistema de referência');
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
  } else {
    aviso('aviso', `dados da sessão indisponíveis (GET /api/eu devolveu ${r.status}); a tela segue com a API de CRS`, 'atencao');
  }
  layout(usuario);
  porId('tipo').addEventListener('change', alternarTipo);
  porId('form-transformar').addEventListener('submit', aoSubmeter);
  await carregarLista();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
