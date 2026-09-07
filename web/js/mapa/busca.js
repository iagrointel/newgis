/* plat · mapa — pesquisa de endereço e de coordenada (item L2-01-mapa-web).

   Uma caixa só, dois comportamentos, decididos pelo TEXTO digitado:
   * parece coordenada -> vai direto para o ponto, sem chamar servidor nenhum;
   * qualquer outra coisa -> sugestões do geocodificador da casa (`GET /api/sugerir`, CNEFE 2022) e,
     ao escolher, `POST /api/geocodificar` para o ponto.

   Formatos de coordenada aceitos (ordem sempre LATITUDE, LONGITUDE quando os dois são decimais, como
   se escreve num mapa; a ordem invertida é detectada quando o primeiro número não cabe em latitude):
     -23.4935, -46.5930      |     -23,4935 -46,5930      |     23°29'36"S 46°35'34"W
   Sem adivinhação silenciosa: o que não casa com um destes formatos é tratado como endereço. */
import { obter, enviar } from '../base/api.js';

const DECIMAL = /^\s*(-?\d{1,3}(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:[.,]\d+)?)\s*$/;
const GMS = /(\d{1,3})\s*[°º]\s*(\d{1,2})?\s*['′]?\s*(\d{1,2}(?:[.,]\d+)?)?\s*["″]?\s*([NSEWOnsewo])/g;

function numero(s) { return Number(String(s).replace(',', '.')); }

export function interpretarCoordenada(texto) {
  const m = DECIMAL.exec(texto);
  if (m) {
    let a = numero(m[1]);
    let b = numero(m[2]);
    // quando o primeiro número não cabe em latitude e o segundo cabe, o usuário digitou lon,lat
    if (Math.abs(a) > 90 && Math.abs(b) <= 90) { const t = a; a = b; b = t; }
    if (Math.abs(a) <= 90 && Math.abs(b) <= 180) return { lat: a, lon: b, formato: 'decimal' };
    return null;
  }
  const partes = [...texto.matchAll(GMS)];
  if (partes.length === 2) {
    const valores = partes.map((p) => {
      const g = numero(p[1]) + (p[2] ? numero(p[2]) / 60 : 0) + (p[3] ? numero(p[3]) / 3600 : 0);
      const hemi = p[4].toUpperCase();
      return { valor: 'SWO'.includes(hemi) ? -g : g, eixo: 'NS'.includes(hemi) ? 'lat' : 'lon' };
    });
    const lat = valores.find((v) => v.eixo === 'lat');
    const lon = valores.find((v) => v.eixo === 'lon');
    if (lat && lon && Math.abs(lat.valor) <= 90 && Math.abs(lon.valor) <= 180) {
      return { lat: lat.valor, lon: lon.valor, formato: 'gms' };
    }
  }
  return null;
}

export async function sugerir(texto) {
  if (!texto || texto.trim().length < 2) return [];
  const r = await obter(`/api/sugerir?q=${encodeURIComponent(texto)}&limite=8`);
  if (r.status !== 200) return [];
  return (r.json.sugestoes || []).map((s) => (typeof s === 'string' ? { texto: s } : s));
}

export async function geocodificar(texto) {
  const r = await enviar('/api/geocodificar', { endereco: texto, max_locations: 1 });
  if (r.status !== 200) return null;
  const lista = r.json.candidatos || r.json.candidates || [];
  if (!lista.length) return null;
  const c = lista[0];
  const lon = c.lon ?? (c.location && c.location.x);
  const lat = c.lat ?? (c.location && c.location.y);
  if (typeof lon !== 'number' || typeof lat !== 'number') return null;
  return { lat, lon, rotulo: c.endereco || c.address || texto, escore: c.escore ?? c.score ?? null };
}
