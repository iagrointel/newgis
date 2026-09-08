import { PlatWidget, definir } from './base.js';
import { hostPermitido, sandboxDe } from './seguro.js';

export const contrato = Object.freeze({ eventos: [], acoes: ['incorporar.definir'] });

/* incorporar: iframe SEMPRE com sandbox; por URL só https e só domínio da lista `dominios_permitidos`; por HTML
   (`html`) o conteúdo passa pelo DOMPurify e entra como srcdoc num iframe sem scripts (sandbox vazio). */
class PlatIncorporar extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('sandbox', '');
    iframe.setAttribute('referrerpolicy', 'no-referrer');
    iframe.title = c.titulo || 'conteúdo incorporado';
    iframe.style.height = `${c.altura || 320}px`;
    if (c.html) {
      const limpo = document.createElement('div'); limpo.append(this.fragmentoSeguro(c.html));
      iframe.srcdoc = limpo.innerHTML; // sandbox vazio: nem scripts, nem mesma origem
      this.replaceChildren(iframe);
      return;
    }
    if (!c.url) { this.erro('sem url nem html'); return; }
    if (!hostPermitido(c.url, c.dominios_permitidos)) { this.erro(`domínio fora da lista permitida: ${c.url}`); return; }
    iframe.setAttribute('sandbox', sandboxDe(c.sandbox || ['allow-scripts']));
    iframe.src = c.url;
    this.replaceChildren(iframe);
  }

  acao_incorporar_definir(detalhe) { this.configuracao = { ...this.configuracao, url: String(detalhe.url || '') }; }
}

definir('plat-w-incorporar', PlatIncorporar);
