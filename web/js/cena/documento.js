/* plat · cena — o documento de cena (item L2-09-b-cena-extrusao-slides).

   A cena é um item do catálogo do tipo `cena`: lê e grava por /api/itens/{id}, com versão e hash como
   qualquer outro documento (L0-03/L5-05). Este módulo só cuida da FORMA do corpo — o padrão de cada
   campo que o documento não trouxer, o id de camada/slide (ULID, mesmo formato do servidor) e o
   recorte do que vai para o servidor (nada além do que o esquema do tipo aceita). */
import { obter, alterar } from '../base/api.js';

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/* ULID: 48 bits de tempo em ms + 80 bits aleatórios, Crockford base32 — o MESMO formato que
   app/catalogo/documento.py gera no servidor (os dois lados concordam no formato, não no código). */
export function gerarUlid() {
  const bytes = new Uint8Array(10);
  crypto.getRandomValues(bytes);
  let ts = BigInt(Date.now()) & ((1n << 48n) - 1n);
  let valor = ts << 80n;
  for (const b of bytes) valor = (valor << 8n) | BigInt(b);
  const saida = [];
  for (let i = 0; i < 26; i += 1) { saida.push(CROCKFORD[Number(valor & 31n)]); valor >>= 5n; }
  return saida.reverse().join('');
}

export const PADRAO = Object.freeze({
  camera: { centro: [-46.593018, -23.493476], zoom: 15, inclinacao: 60, rotacao: 0 },
  terreno: { ligado: false, url: '', codificacao: 'terrain-rgb', tamanho_tile: 256, zoom_maximo: 14, exagero: 1 },
  iluminacao: { modo: 'data_hora', instante: '2026-06-21T12:00:00-03:00', intensidade: 0.35, cor: '#ffffff' },
  atmosfera: { ceu: true, cor_horizonte: '#a8c6dd', nevoa: { ligada: true, inicio: 0.7, fim: 1, cor: '#c9d6de' } },
  camadas: [],
  slides: [],
});

function juntar(padrao, valor) {
  if (!valor || typeof valor !== 'object' || Array.isArray(valor)) return valor ?? padrao;
  const saida = { ...padrao };
  for (const [k, v] of Object.entries(valor)) {
    saida[k] = (padrao[k] && typeof padrao[k] === 'object' && !Array.isArray(padrao[k])) ? juntar(padrao[k], v) : v;
  }
  return saida;
}

/* corpo do documento com o padrão do visualizador no que faltar (o esquema do tipo não obriga campo
   nenhum dentro de `corpo`: documento vazio é documento válido, e abre na cena padrão). */
export function comPadrao(corpo) {
  const c = corpo && typeof corpo === 'object' ? corpo : {};
  return {
    camera: juntar(PADRAO.camera, c.camera),
    terreno: juntar(PADRAO.terreno, c.terreno),
    iluminacao: juntar(PADRAO.iluminacao, c.iluminacao),
    atmosfera: juntar(PADRAO.atmosfera, c.atmosfera),
    camadas: Array.isArray(c.camadas) ? c.camadas.map((x) => ({ ...x })) : [],
    slides: Array.isArray(c.slides) ? c.slides.map((x) => ({ ...x })) : [],
  };
}

/* o corpo que vai ao servidor: sem `url` de terreno vazia (o esquema aceita string, mas gravar ''
   guarda uma configuração que não existe) e sem chave nenhuma fora do esquema do tipo. */
export function paraGravar(corpo) {
  const c = comPadrao(corpo);
  const terreno = { ...c.terreno };
  if (!terreno.url) delete terreno.url;
  return { camera: c.camera, terreno, iluminacao: c.iluminacao, atmosfera: c.atmosfera,
    camadas: c.camadas, slides: c.slides };
}

export class Documento {
  constructor(item) {
    this.item = item;                       // ficha do item vinda de /api/itens/{id}
    this.corpo = comPadrao((item.dados || {}).corpo);
    this.versao = item.versao_atual ?? null;
  }

  static async carregar(id) {
    const r = await obter(`/api/itens/${id}`);
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao abrir a cena');
    if (r.json.tipo !== 'cena') throw new Error(`o item não é uma cena: ${r.json.tipo}`);
    return new Documento(r.json);
  }

  camada(id) { return this.corpo.camadas.find((c) => c.id === id) || null; }
  slide(id) { return this.corpo.slides.find((s) => s.id === id) || null; }

  async gravar() {
    const dados = { esquema_versao: (this.item.dados || {}).esquema_versao || 1, corpo: paraGravar(this.corpo) };
    const r = await alterar(`/api/itens/${this.item.id}`, { dados, versao_atual: this.versao });
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao gravar a cena');
    this.item = r.json;
    this.versao = r.json.versao_atual ?? this.versao;
    return r.json;
  }
}
