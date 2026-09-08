import { PlatWidget, definir } from './base.js';
import { botaoCopiar } from '../base/dom.js';

export const contrato = Object.freeze({ eventos: [], acoes: [] });

/* compartilhar: link da página atual (copiar), QR gerado NA PLATAFORMA (GET /api/qr.svg, sem serviço externo) e
   trecho de incorporação (<iframe>) — o que o "Share" do Experience Builder oferece */
class PlatCompartilhar extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const url = c.url || location.href;
    const raiz = document.createElement('div'); raiz.className = 'plat-compartilhar';
    const campo = document.createElement('input'); campo.type = 'text'; campo.readOnly = true; campo.value = url; campo.setAttribute('aria-label', 'link');
    raiz.append(campo, botaoCopiar(() => url, campo));
    if (c.qr !== false) {
      const img = document.createElement('img');
      img.alt = 'QR do link'; img.className = 'plat-qr';
      img.src = `/api/qr.svg?texto=${encodeURIComponent(url)}`;
      raiz.append(img);
    }
    if (c.incorporar !== false) {
      const trecho = document.createElement('textarea'); trecho.readOnly = true; trecho.rows = 2;
      trecho.setAttribute('aria-label', 'código de incorporação');
      trecho.value = `<iframe src="${url.replace(/"/g, '%22')}" width="100%" height="480" sandbox="allow-scripts allow-same-origin"></iframe>`;
      raiz.append(trecho, botaoCopiar(() => trecho.value, trecho));
    }
    this.replaceChildren(raiz);
  }
}

definir('plat-compartilhar', PlatCompartilhar);
