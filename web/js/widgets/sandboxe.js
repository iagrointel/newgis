/* plat — hospedeiro de widget externo em SANDBOX (L5-36). Na página, <plat-widget-sandboxe> é um PlatWidget
   comum (recebe configuração, responde a ações, emite no barramento de verdade); por dentro é um <iframe
   sandbox="allow-scripts"> SEM allow-same-origin, com o código do widget em linha e origem opaca:
   document.cookie lança SecurityError, fetch para a API sai sem credenciais (401) e o CSP embutido
   (connect-src 'none') não deixa rede nenhuma. Ponte nos dois sentidos: para dentro vão
   {plat:'anfitriao', tipo:'acao'}; para fora, {plat:'widget', nome, detalhe} vira emitir no barramento —
   nome fora de manifesto.eventos é descartado (o pacote só fala o que declarou). */
import { PlatWidget, definir } from './base.js';
import { REGISTRO } from './registro.js';

/* texto de módulo já baixado e conferido por nome — o carregador (externos.js) preenche; quem corre no
   iframe é ESTE texto, nunca uma segunda descarga (o que foi verificado é o que executa) */
export const modulosVerificados = new Map();

const jsonSeguro = (valor) => JSON.stringify(valor ?? null)
  .replace(/</g, '\\u003c')
  .replace(/[\u2028\u2029]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);

/* o código do parceiro não pode fechar a tag de script da cola antes da hora: `</script` em código JS só
   aparece dentro de string/template/regex, e em todos esses contextos `<\/script` (e `<\!--`) vale o MESMO
   texto que o original */
const semQuebraDeScript = (texto) => texto.replaceAll('</script', '<\\/script').replaceAll('<!--', '<\\!--');

/* CSP do iframe: script inline (a cola e o módulo em linha) e nada mais — sem conexão, sem base, sem
   formulário; a widget recebe dados por mensagem, não por rede */
const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'";

export function srcdocDe(manifesto, texto, configuracao) {
  return `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>html,body{margin:0;height:100%}#raiz{height:100%;font:14px/1.45 system-ui,sans-serif;padding:8px;box-sizing:border-box}</style>
</head><body><div id="raiz"></div>
<script type="module">
const CONFIGURACAO = Object.freeze(${jsonSeguro(configuracao)});
window.plat = {
  configuracao: CONFIGURACAO,
  widget: null,
  emitir(nome, detalhe = {}) { parent.postMessage({ plat: 'widget', nome, detalhe }, '*'); },
  registrar(widget) {
    window.plat.widget = widget;
    const raiz = document.getElementById('raiz');
    if (widget && typeof widget.montar === 'function') widget.montar(raiz);
  },
};
window.addEventListener('message', (e) => {
  const m = e.data;
  if (!m || m.plat !== 'anfitriao') return;
  const widget = window.plat.widget;
  if (m.tipo === 'acao' && widget && typeof widget.acao === 'function') widget.acao(m.acao, m.detalhe ?? {});
});
</script>
<script type="module">
${semQuebraDeScript(texto)}
</script>
</body></html>`;
}

class PlatWidgetSandboxe extends PlatWidget {
  #iframe = null;
  #ouvir = (e) => this.#mensagem(e);

  renderizar() {
    const nome = this.dataset.tipo;
    const manifesto = REGISTRO.get(nome);
    const texto = modulosVerificados.get(nome);
    if (!manifesto?.sandbox) return; // hospedeiro só montado para pacote em sandbox (o motor decide isso)
    if (texto === undefined) {
      const erro = document.createElement('section');
      erro.className = 'plat-widget-erro'; erro.setAttribute('role', 'alert');
      erro.textContent = `Widget “${nome}”: código não conferido (sha256), nada corre`;
      this.replaceChildren(erro);
      return;
    }
    const moldura = document.createElement('iframe');
    moldura.setAttribute('sandbox', 'allow-scripts'); // SEM allow-same-origin: origem opaca
    moldura.className = 'plat-widget-sandboxe';
    moldura.setAttribute('title', manifesto.nome);
    moldura.style.cssText = 'width:100%;height:100%;border:0;display:block';
    // a origem do código que corre aqui fica no próprio elemento (auditoria sem abrir o banco)
    moldura.setAttribute('data-widget-origem',
      `widget externo ${manifesto.nome} ${manifesto.versao} (sandbox, sha256 ${manifesto.sha256.slice(0, 12)}…)`);
    moldura.srcdoc = srcdocDe(manifesto, texto, this.configuracao);
    this.replaceChildren(moldura);
    this.#iframe = moldura;
  }

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener('message', this.#ouvir);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener('message', this.#ouvir);
    this.#iframe = null;
  }

  #mensagem(e) {
    if (!this.#iframe || e.source !== this.#iframe.contentWindow) return;
    const m = e.data;
    if (!m || m.plat !== 'widget') return;
    const manifesto = REGISTRO.get(this.dataset.tipo);
    if (manifesto?.eventos?.includes(m.nome)) this.emitir(m.nome, m.detalhe ?? {});
  }

  /* ações chegam pelo mesmo portão do motor (manifesto.acoes); dentro do sandbox é quem responde — o
     comportamento padrão do hospedeiro (piscar, abrir, fechar) continua valendo, e ação que só existe
     lá dentro não derruba a página */
  executar(acao, detalhe = {}) {
    this.#iframe?.contentWindow?.postMessage({ plat: 'anfitriao', tipo: 'acao', acao, detalhe }, '*');
    try { super.executar(acao, detalhe); } catch { /* ação definida só dentro do sandbox */ }
  }
}

definir('plat-widget-sandboxe', PlatWidgetSandboxe);
