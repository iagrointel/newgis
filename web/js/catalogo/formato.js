/* plat · catálogo — formatação e limites da tela (ADR 0004 seção 14): bytes, elipse, datas relativas, rótulos de acesso,
   status e origem por i18n. Puro (sem rede); DOM só em ícone de texto. Os limites são os mesmos da API; a tela
   valida antes de enviar e mostra a mensagem da API quando ela decide diferente. */
import { t, formatarData, formatarNumero } from '../base/i18n.js';

export const LIMITES = {
  titulo: 250, resumo: 2048, descricao: 65536, creditos: 2048, termos: 65536,
  tags: 50, tag: 128, categorias: 20, pastaNome: 128, pastaProfundidade: 5,
  miniaturaBytes: 10 * 1024 * 1024, linkDias: 365, lote: 100, pagina: 50, buscaQ: 1000, buscaTermos: 200,
  uploadBytes: 2 * 1024 * 1024 * 1024,
};

export function bytes(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const v = Number(n);
  if (v < 1024) return `${formatarNumero(v)} B`;
  const u = ['kB', 'MB', 'GB', 'TB'];
  let x = v / 1024; let i = 0;
  while (x >= 1024 && i < u.length - 1) { x /= 1024; i += 1; }
  return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: x < 10 ? 1 : 0 }).format(x)} ${u[i]}`;
}

/* corta em n caracteres com reticência; título de 2.048 caracteres não estoura a linha (refutação do L0-03-f) */
export function elipse(s, n = 120) {
  const v = s === null || s === undefined ? '' : String(s);
  return v.length > n ? `${v.slice(0, n - 1).trimEnd()}…` : v;
}

/* "há 2 h" · "ontem" · "05/09/2026" — relativo até 7 dias, depois data curta */
export function quando(iso, agora = Date.now()) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const s = Math.round((agora - d.getTime()) / 1000);
  if (s < 60) return t('catalogo.agora');
  if (s < 3600) return t('catalogo.ha_min', { n: Math.round(s / 60) });
  if (s < 86400) return t('catalogo.ha_h', { n: Math.round(s / 3600) });
  if (s < 7 * 86400) return t('catalogo.ha_d', { n: Math.round(s / 86400) });
  return formatarData(iso, true);
}

export function dataHora(iso) { return iso ? formatarData(iso) : '—'; }

export function rotuloAcesso(item) {
  if (!item) return '';
  if (item.acesso === 'publico') return t('catalogo.acesso_publico');
  if (item.acesso === 'inquilino') return item.compartilhado_com_grupos ? t('catalogo.acesso_inquilino_grupos', { n: item.compartilhado_com_grupos }) : t('catalogo.acesso_inquilino');
  if (item.compartilhado_com_grupos) return t('catalogo.acesso_grupos', { n: item.compartilhado_com_grupos });
  return t('catalogo.acesso_privado');
}

export function rotuloStatus(status) {
  if (status === 'autoritativo') return t('catalogo.status_autoritativo');
  if (status === 'obsoleto') return t('catalogo.status_obsoleto');
  return t('catalogo.status_nenhum');
}

export function rotuloOrigem(origem) { return origem === 'referenciado' ? t('catalogo.origem_referenciado') : t('catalogo.origem_hospedado'); }

export function nomeDono(d) { return d ? (d.nome || d.login || String(d.id)) : '—'; }

/* tags "a, b, c" -> ['a','b','c'] sem vazios, sem duplicata, no limite */
export function tagsDeTexto(texto) {
  const vistas = new Set();
  const out = [];
  for (const parte of String(texto || '').split(/[,\n]/)) {
    const v = parte.trim().replace(/\s+/g, ' ');
    if (!v || vistas.has(v.toLowerCase())) continue;
    vistas.add(v.toLowerCase());
    out.push(v.slice(0, LIMITES.tag));
    if (out.length >= LIMITES.tags) break;
  }
  return out;
}

/* extent [xmin, ymin, xmax, ymax] -> texto; null -> '—' */
export function textoExtent(e) {
  if (!Array.isArray(e) || e.length !== 4) return '—';
  return e.map((v) => Number(v).toFixed(4)).join(', ');
}

/* erros de validação local dos campos de metadado; devolve {campo: mensagem} */
export function validarMetadado(v) {
  const erros = {};
  const titulo = (v.titulo ?? '').trim();
  if ('titulo' in v && (!titulo || titulo.length > LIMITES.titulo)) erros.titulo = t('catalogo.erro_titulo', { max: LIMITES.titulo });
  if ((v.resumo || '').length > LIMITES.resumo) erros.resumo = t('catalogo.erro_tamanho', { max: LIMITES.resumo });
  if ((v.descricao || '').length > LIMITES.descricao) erros.descricao = t('catalogo.erro_tamanho', { max: LIMITES.descricao });
  if ((v.creditos || '').length > LIMITES.creditos) erros.creditos = t('catalogo.erro_tamanho', { max: LIMITES.creditos });
  if ((v.termos_de_uso || '').length > LIMITES.termos) erros.termos_de_uso = t('catalogo.erro_tamanho', { max: LIMITES.termos });
  if (Array.isArray(v.tags)) {
    if (v.tags.length > LIMITES.tags) erros.tags = t('catalogo.erro_tags', { max: LIMITES.tags });
    else if (v.tags.some((x) => x.length > LIMITES.tag || /[,\n\r\t]/.test(x))) erros.tags = t('catalogo.erro_tag', { max: LIMITES.tag });
  }
  if (v.url && !/^https?:\/\/\S+$/.test(v.url)) erros.url = t('catalogo.erro_url');
  return erros;
}

/* extent de texto "xmin, ymin, xmax, ymax" -> array ou {erro} */
export function extentDeTexto(texto) {
  const partes = String(texto || '').split(/[,\s]+/).filter(Boolean).map(Number);
  if (partes.length !== 4 || partes.some((n) => Number.isNaN(n))) return { erro: t('catalogo.erro_extent') };
  const [a, b, c, d] = partes;
  if (a < -180 || c > 180 || b < -90 || d > 90 || a >= c || b >= d) return { erro: t('catalogo.erro_extent') };
  return { extent: partes };
}

/* tipo declarado do upload (ADR 0005 seção 3.3) pela extensão do nome; null = não aceito */
export function tipoDeclaradoDoNome(nome) {
  const n = String(nome || '').toLowerCase();
  const ext = n.includes('.') ? n.slice(n.lastIndexOf('.') + 1) : '';
  const mapa = {
    zip: 'zip', gpkg: 'gpkg', geojson: 'geojson', json: 'geojson', geojsonl: 'geojsonseq', ndjson: 'geojsonseq', jsonl: 'geojsonseq',
    kml: 'kml', kmz: 'kmz', csv: 'csv', txt: 'txt', tsv: 'tsv', psv: 'csv', xlsx: 'xlsx', xls: 'xls', ods: 'ods',
    gpx: 'gpx', dxf: 'dxf', dwg: 'dwg', fgb: 'fgb', gml: 'gml', xml: 'gml', parquet: 'parquet',
  };
  return mapa[ext] || null;
}

export const TIPOS_UPLOAD = ['shapefile.zip', 'gdb.zip', 'tab.zip', 'mif.zip', 'zip', 'gpkg', 'geojson', 'geojsonseq', 'kml', 'kmz', 'csv', 'txt', 'tsv', 'xlsx', 'xls', 'ods', 'gpx', 'dxf', 'dwg', 'fgb', 'gml', 'parquet'];
