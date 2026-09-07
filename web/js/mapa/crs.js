/* plat · mapa — sistemas de referência do visualizador (item L2-01-f-navegacao-medicao-coordenadas).

   Lista curada brasileira (a mesma do L2-17: SIRGAS 2000 geográfico, UTM SIRGAS 21S-25S, Policônica, Web
   Mercator, WGS 84) com as definições PROJ COPIADAS de `spatial_ref_sys` do PostGIS desta instalação
   (tests/unit/test_navegacao_mapa.py confere texto a texto: divergiu = teste reprova). A conversão roda no
   navegador com o proj4js vendorizado (web/vendor/proj4-2.22.0.js, global `proj4`); no node os testes injetam
   a mesma biblioteca por `usarProj4`. Sem proj4 disponível, `converter` lança — nunca devolve coordenada errada
   em silêncio. */

export const CRS = [
  { srid: 4326, nome: 'WGS 84 (graus)', unidade: 'grau', proj: '+proj=longlat +datum=WGS84 +no_defs' },
  { srid: 4674, nome: 'SIRGAS 2000 (graus)', unidade: 'grau', proj: '+proj=longlat +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +no_defs' },
  { srid: 31981, nome: 'SIRGAS 2000 / UTM 21S', unidade: 'm', proj: '+proj=utm +zone=21 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs' },
  { srid: 31982, nome: 'SIRGAS 2000 / UTM 22S', unidade: 'm', proj: '+proj=utm +zone=22 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs' },
  { srid: 31983, nome: 'SIRGAS 2000 / UTM 23S', unidade: 'm', proj: '+proj=utm +zone=23 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs' },
  { srid: 31984, nome: 'SIRGAS 2000 / UTM 24S', unidade: 'm', proj: '+proj=utm +zone=24 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs' },
  { srid: 31985, nome: 'SIRGAS 2000 / UTM 25S', unidade: 'm', proj: '+proj=utm +zone=25 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs' },
  { srid: 5880, nome: 'SIRGAS 2000 / Policônica', unidade: 'm', proj: '+proj=poly +lat_0=0 +lon_0=-54 +x_0=5000000 +y_0=10000000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs' },
  { srid: 3857, nome: 'Web Mercator', unidade: 'm', proj: '+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs' },
];

let _proj4 = null;
export function usarProj4(p) { _proj4 = p; }
function proj4() {
  const p = _proj4 || globalThis.proj4;
  if (!p) throw new Error('proj4 ausente: inclua /static/vendor/proj4-2.22.0.js antes do módulo');
  for (const c of CRS) if (!p.defs(`EPSG:${c.srid}`)) p.defs(`EPSG:${c.srid}`, c.proj);
  return p;
}

export function crsDe(srid) { return CRS.find((c) => c.srid === Number(srid)) || null; }

/* lon/lat (4326) -> [x, y] no CRS pedido */
export function converter(lon, lat, srid) {
  const c = crsDe(srid);
  if (!c) throw new Error(`CRS fora da lista curada: ${srid}`);
  if (c.srid === 4326) return [lon, lat];
  return proj4()('EPSG:4326', `EPSG:${c.srid}`, [lon, lat]);
}

/* [x, y] no CRS pedido -> lon/lat (4326) */
export function paraLonLat(x, y, srid) {
  const c = crsDe(srid);
  if (!c) throw new Error(`CRS fora da lista curada: ${srid}`);
  if (c.srid === 4326) return [x, y];
  return proj4()(`EPSG:${c.srid}`, 'EPSG:4326', [x, y]);
}

/* projeção azimutal equivalente (LAEA) centrada no ponto dado, sobre o GRS80: área exata no elipsoide para o
   cálculo de área da medição (medicao.js) — a projeção equivalente preserva área por definição */
export function laeaLocal(lon0, lat0) {
  const p = proj4();
  const nome = `PLAT_LAEA_${lon0.toFixed(6)}_${lat0.toFixed(6)}`;
  if (!p.defs(nome)) p.defs(nome, `+proj=laea +lat_0=${lat0} +lon_0=${lon0} +x_0=0 +y_0=0 +ellps=GRS80 +units=m +no_defs`);
  return (lon, lat) => p('EPSG:4326', nome, [lon, lat]);
}

/* ---- formatação ---- */
function gms(valor, eixo) {
  const abs = Math.abs(valor);
  const g = Math.floor(abs);
  const mTotal = (abs - g) * 60;
  const m = Math.floor(mTotal);
  const s = ((mTotal - m) * 60).toFixed(2);
  const hemi = eixo === 'lat' ? (valor < 0 ? 'S' : 'N') : (valor < 0 ? 'W' : 'E');
  return `${g}°${String(m).padStart(2, '0')}′${String(s).padStart(5, '0')}″${hemi}`;
}

export function formatarCoordenada(lon, lat, srid, { formato = 'decimal' } = {}) {
  const c = crsDe(srid) || CRS[0];
  if (c.unidade === 'grau') {
    if (formato === 'gms') return `${gms(lat, 'lat')} ${gms(lon, 'lon')}`;
    return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  }
  const [x, y] = converter(lon, lat, c.srid);
  const f = (v) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${f(x)} ${f(y)} m`;
}
