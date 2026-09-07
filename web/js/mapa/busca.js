/* plat · mapa — pesquisa de endereço e de coordenada (itens L2-01-mapa-web e L2-01-f).

   Uma caixa só, dois comportamentos, decididos pelo TEXTO digitado:
   * parece coordenada -> vai direto para o ponto, sem chamar servidor nenhum;
   * qualquer outra coisa -> sugestões do geocodificador da casa (`GET /api/sugerir`, CNEFE 2022) e,
     ao escolher, `POST /api/geocodificar` para o ponto.

   Formatos de coordenada aceitos (ordem sempre LATITUDE, LONGITUDE quando os dois são decimais, como
   se escreve num mapa; a ordem invertida é detectada quando o primeiro número não cabe em latitude):
     -23.4935, -46.5930      |     -23,4935 -46,5930      |     −23,55 −46,63 (sinal de menos tipográfico)
     23°29'36"S 46°35'34"W   |     23°33′S 46°38′W (minutos sem segundos, aspas tipográficas)
     333.000 7.394.000 EPSG:31983   (projetado: x y + EPSG explícito; ponto de milhar aceito; UTM só com zona
     explícita pelo EPSG — nunca adivinhada)
   Sem adivinhação silenciosa: o que não casa com um destes formatos é tratado como endereço. */
import { obter, consulta } from '../base/api.js';
import { crsDe, paraLonLat } from './crs.js';

const NUM = String.raw`[-−]?\d{1,3}(?:[.,]\d+)?`;
const DECIMAL = new RegExp(String.raw`^\s*(${NUM})\s*[,;\s]\s*(${NUM})\s*$`);
const GMS = /(\d{1,3})\s*[°º]\s*(\d{1,2}(?:[.,]\d+)?)?\s*['′’]?\s*(\d{1,2}(?:[.,]\d+)?)?\s*["″”]?\s*([NSEWOnsewo])/g;
/* x y EPSG:NNNN — os números podem ter ponto de milhar (333.000) ou casas decimais (333000,50); a distinção é
   pelo grupo de 3 dígitos após o ponto: "333.000" é milhar, "333.5" é decimal */
const PROJETADO = /^\s*([-−]?[\d.]+(?:,\d+)?)\s+([-−]?[\d.]+(?:,\d+)?)\s+(?:EPSG:|SRID[:=]?)?\s*(\d{4,5})\s*$/i;

function numero(s) {
  return Number(String(s).replace('−', '-').replace(',', '.'));
}

function numeroProjetado(s) {
  const t = String(s).replace('−', '-');
  const [inteiro, decimal] = t.split(',');
  const semMilhar = /^-?\d{1,3}(\.\d{3})+$/.test(inteiro) ? inteiro.replace(/\./g, '') : inteiro;
  return Number(decimal !== undefined ? `${semMilhar}.${decimal}` : semMilhar);
}

export function interpretarCoordenada(texto) {
  if (typeof texto !== 'string' || texto.length > 200) return null;
  const proj = PROJETADO.exec(texto);
  if (proj) {
    const srid = Number(proj[3]);
    if (!crsDe(srid) || crsDe(srid).unidade === 'grau') return null; // só CRS projetado da lista curada
    const x = numeroProjetado(proj[1]);
    const y = numeroProjetado(proj[2]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    let lonlat;
    try { lonlat = paraLonLat(x, y, srid); } catch { return null; }
    const [lon, lat] = lonlat;
    if (!Number.isFinite(lon) || !Number.isFinite(lat) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
    return { lat, lon, formato: 'projetado', srid };
  }
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
  // GET, não POST: geocodificar é leitura, e a porta de escrita sob cookie exige a checagem de origem
  // (ADR 0002 seção 5.3), que recusa quando a URL pública configurada não é a do navegador.
  const r = await obter(`/api/geocodificar${consulta({ endereco: texto, max_locations: 1 })}`);
  if (r.status !== 200) return null;
  const lista = r.json.candidatos || r.json.candidates || [];
  if (!lista.length) return null;
  const c = lista[0];
  const lon = c.lon ?? (c.location && c.location.x);
  const lat = c.lat ?? (c.location && c.location.y);
  if (typeof lon !== 'number' || typeof lat !== 'number') return null;
  return { lat, lon, rotulo: c.endereco || c.address || texto, escore: c.escore ?? c.score ?? null };
}
