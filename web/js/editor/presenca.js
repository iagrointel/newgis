/* plat — presença em documento (item L5-13-edicao-concorrente): quem está com o documento aberto e em que nó.
   Batimento `POST /api/itens/{id}/presenca` a cada `intervaloMs` (5 s) com o nó selecionado; fluxo SSE
   `GET /api/itens/{id}/presenca/eventos` entrega a lista inteira a cada mudança; `sair()` avisa na saída
   (sendBeacon, sobrevive ao fechar a aba). Bloqueio LEVE por nó: quem está num nó que outra aba também está
   recebe aviso, nunca trava (D12). Sem dependência: só fetch/EventSource. */
import { chamar } from '../base/api.js';

export function gerarSessao() {
  const b = crypto.getRandomValues(new Uint8Array(12));
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

export function criarPresenca({ idItem, sessao = gerarSessao(), obterNo = () => null, aoMudar = () => {}, intervaloMs = 5000 }) {
  let timer = null;
  let fonte = null;
  let lista = [];
  let ativo = false;

  async function bater(extra = {}) {
    if (!ativo) return null;
    const r = await chamar('POST', `/api/itens/${idItem}/presenca`, { sessao, no: obterNo() || null, ...extra });
    if (r.status === 200) { lista = r.json.itens || []; aoMudar(lista); }
    return r;
  }

  function ligarFluxo() {
    if (!('EventSource' in window)) return;
    fonte = new EventSource(`/api/itens/${idItem}/presenca/eventos`);
    fonte.addEventListener('presenca', (ev) => {
      try { lista = JSON.parse(ev.data) || []; } catch { return; }
      aoMudar(lista);
    });
    fonte.addEventListener('fim', () => { fonte?.close(); if (ativo) ligarFluxo(); });
  }

  return {
    sessao,
    lista: () => lista,
    outros: () => lista.filter((e) => e.sessao !== sessao),
    /* ids de nó ocupados por OUTRAS abas -> lista de {login, nome} */
    ocupados() {
      const m = new Map();
      for (const e of lista) {
        if (e.sessao === sessao || !e.no) continue;
        if (!m.has(e.no)) m.set(e.no, []);
        m.get(e.no).push(e);
      }
      return m;
    },
    async iniciar() {
      ativo = true;
      ligarFluxo();
      await bater();
      timer = setInterval(() => { bater().catch(() => {}); }, intervaloMs);
    },
    bater,
    sair() {
      ativo = false;
      if (timer) clearInterval(timer);
      fonte?.close();
      const corpo = JSON.stringify({ sessao, no: null, sair: true });
      if (navigator.sendBeacon) {
        navigator.sendBeacon(`/api/itens/${idItem}/presenca`, new Blob([corpo], { type: 'application/json' }));
      } else {
        chamar('POST', `/api/itens/${idItem}/presenca`, { sessao, no: null, sair: true }).catch(() => {});
      }
    },
  };
}
