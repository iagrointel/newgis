/* plat — pré-visualização por dispositivo do construtor (item L5-15-vista-movel-responsivo): iframe de MESMA
   ORIGEM (precedente Puck) que carrega web/visualizar.html e recebe o documento em edição por `postMessage`
   — nunca por navegação/recarregamento, para refletir uma alteração que ainda não foi salva. Três larguras
   fixas (não são o viewport real do navegador — são o CONTAINER do iframe; o CSS responsivo do visualizador
   reage do mesmo jeito que reagiria numa tela real dessa largura, porque a media query olha o viewport do
   PRÓPRIO documento do iframe, que é a largura do iframe): celular 375, tablet 768, desktop 1440. */
import { h, limpar } from '../base/dom.js';

export const DISPOSITIVOS = [
  { chave: 'celular', rotulo: 'Celular', largura: 375, altura: 640 },
  { chave: 'tablet', rotulo: 'Tablet', largura: 768, altura: 1024 },
  { chave: 'desktop', rotulo: 'Desktop', largura: 1440, altura: 900 },
];

export function montarPreVisualizacao({ raiz, obterDocumento }) {
  const iframe = h('iframe', { id: 'pre-visualizacao-quadro', title: 'Pré-visualização do dispositivo', src: '/visualizar?preview=1' });
  const moldura = h('div', { class: 'pre-visualizacao-moldura' }, iframe);
  const botoes = DISPOSITIVOS.map((d) => {
    const b = h('button', { type: 'button', class: 'pequeno', dataset: { dispositivo: d.chave }, 'aria-pressed': 'false' }, d.rotulo);
    b.addEventListener('click', () => aplicarDispositivo(d));
    return b;
  });

  function aplicarDispositivo(d) {
    moldura.style.width = `${d.largura}px`;
    iframe.style.width = `${d.largura}px`;
    iframe.style.height = `${d.altura}px`;
    for (const b of botoes) {
      const ativo = b.dataset.dispositivo === d.chave;
      b.classList.toggle('ativo', ativo);
      b.setAttribute('aria-pressed', String(ativo));
    }
    enviar();
  }

  function enviar() {
    iframe.contentWindow?.postMessage({ tipo: 'plat-documento-preview', documento: obterDocumento() }, location.origin);
  }

  iframe.addEventListener('load', enviar);
  limpar(raiz).append(
    h('div', { class: 'pre-visualizacao-botoes', role: 'group', 'aria-label': 'Dispositivo de pré-visualização' }, ...botoes),
    moldura,
  );
  aplicarDispositivo(DISPOSITIVOS[0]);
  return { atualizar: enviar };
}
