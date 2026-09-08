/* plat · atualização viva (item L2-06-d-atualizacao-viva-sse). Uma assinatura por TELA, nunca uma por
   elemento: o chamador entrega a lista de camadas que lhe interessa e uma função `aoMudar(camadas)`; este
   módulo abre UM EventSource em /api/eventos/camadas e chama de volta no máximo uma vez por janela de
   coalescência, com o conjunto de camadas que mudaram na janela.

   Por que coalescer aqui e não no servidor: o servidor já reduz N linhas a um evento por comando (o gatilho
   é FOR EACH STATEMENT), mas uma sincronização legítima pode emitir muitos comandos seguidos. Sem a janela,
   mil comandos em um segundo viram mil consultas do navegador — que é exatamente o que a refutação do item
   procura. Com a janela de ATRASO_MS, a rajada vira uma consulta.

   Reconexão: o navegador reabre o EventSource sozinho e reenvia o último `id:` recebido no cabeçalho
   Last-Event-ID; o servidor devolve o que passou dentro da janela de retenção. Não há reimplementação de
   reconexão aqui de propósito — a do próprio EventSource é a que o padrão define.

   Fallback: se o fluxo não abrir (proxy sem suporte, PLAT_SSE_LIGADO=false → 503, rede sem SSE), a
   assinatura se declara indisponível chamando `aoIndisponivel()` uma única vez; quem chamou volta ao
   intervalo de atualização configurado em cada fonte. A tela nunca fica sem atualizar por causa disso. */

export const ATRASO_MS = 1000;

/**
 * @param {string[]} camadas ids das camadas a assinar (o servidor recusa acima do teto declarado)
 * @param {(camadasMudadas: Set<string>) => void} aoMudar chamado no máximo uma vez por janela
 * @param {{aoIndisponivel?: () => void, atrasoMs?: number, criarFonte?: (url: string) => EventSource}} opcoes
 * @returns {{fechar: () => void, disponivel: () => boolean}}
 */
export function assinarCamadas(camadas, aoMudar, opcoes = {}) {
  const unicas = [...new Set((camadas || []).filter(Boolean))];
  const atraso = opcoes.atrasoMs ?? ATRASO_MS;
  const criarFonte = opcoes.criarFonte || ((url) => new EventSource(url));
  let fonte = null;
  let temporizador = null;
  let pendentes = new Set();
  let indisponivelAvisado = false;
  let vivo = false;
  let fechado = false;

  if (!unicas.length || typeof EventSource === 'undefined') {
    if (opcoes.aoIndisponivel) opcoes.aoIndisponivel();
    return { fechar() {}, disponivel: () => false };
  }

  function despachar() {
    temporizador = null;
    if (!pendentes.size) return;
    const lote = pendentes;
    pendentes = new Set();
    try {
      aoMudar(lote);
    } catch (e) {
      // uma falha ao redesenhar não pode derrubar a assinatura: o próximo evento tenta de novo
      console.error('atualização viva: falha ao aplicar mudança', e);
    }
  }

  function acumular(camadaId) {
    pendentes.add(camadaId);
    if (temporizador === null) temporizador = setTimeout(despachar, atraso);
  }

  const url = `/api/eventos/camadas?camadas=${unicas.map(encodeURIComponent).join(',')}`;
  fonte = criarFonte(url);

  fonte.addEventListener('pronto', () => { vivo = true; });
  fonte.addEventListener('camada', (ev) => {
    let dados;
    try {
      dados = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (dados && dados.camada) acumular(dados.camada);
  });
  fonte.addEventListener('error', () => {
    // EventSource fecha em erro definitivo (readyState 2) e reabre sozinho nos transitórios (0/1).
    if (fechado || vivo) return;
    if (!indisponivelAvisado) {
      indisponivelAvisado = true;
      if (opcoes.aoIndisponivel) opcoes.aoIndisponivel();
    }
  });

  return {
    fechar() {
      fechado = true;
      if (temporizador !== null) clearTimeout(temporizador);
      temporizador = null;
      if (fonte) fonte.close();
    },
    disponivel: () => vivo,
  };
}

/** "atualizado às hh:mm:ss" no fuso do navegador; o cabeçalho do painel usa isto a cada refetch. */
export function horaCurta(data = new Date()) {
  return data.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
