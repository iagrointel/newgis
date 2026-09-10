/* plat — RÉGUA (item L0-14-identidade-visual): o traço que só este produto tem. Todo número que a tela mostra
   carrega a sua procedência: de que rota veio, em que instante, e (quando há) o comando que o gerou — a mesma
   regra da casa "número em documento sai de script, com o comando que o gerou", agora na interface.

   regua(valor, {origem, em, comando, unidade}) -> <span class="regua" tabindex="0" data-procedencia="...">
   Sem `origem`, usa a última chamada à API registrada por web/js/base/api.js (chamada mais recente da tela).
   A etiqueta aparece em hover/foco (CSS em base.css); para leitor de tela o mesmo texto vai em aria-label
   (o textContent do elemento continua sendo só o valor, para nada que leia a tela mudar).
   reguaTela(main) monta a linha de procedência da tela: as últimas chamadas à API com rota, status, hora e ms. */
import { h, limpar } from './dom.js';
import { chamadas, ultimaChamada, aoChamar } from './api.js';

const fmtHora = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC' });

export function horaUtc(iso) {
  const d = iso ? new Date(iso) : new Date();
  return Number.isNaN(d.getTime()) ? String(iso) : `${fmtHora.format(d)} UTC`;
}

export function textoProcedencia({ origem, em, comando, status, ms } = {}) {
  const linhas = [];
  if (origem) linhas.push(`origem  ${origem}${status ? ` -> ${status}` : ''}${ms !== undefined && ms !== null ? ` · ${ms} ms` : ''}`);
  linhas.push(`instante ${horaUtc(em)}`);
  if (comando) linhas.push(`comando ${comando}`);
  return linhas.join('\n');
}

/* origem padrão: a última chamada à API (GET) feita pela tela */
function origemPadrao() {
  const u = ultimaChamada();
  if (!u) return {};
  return { origem: `${u.metodo} ${u.caminho}`, em: u.em, status: u.status, ms: u.ms };
}

export function regua(valor, opcoes = {}) {
  const dados = { ...origemPadrao(), ...opcoes };
  const texto = textoProcedencia(dados);
  const v = valor === undefined || valor === null ? '' : String(valor);
  const el = h('span', { class: `regua${opcoes.classe ? ` ${opcoes.classe}` : ''}`, tabindex: '0', 'data-procedencia': texto,
    'aria-label': `${v}${opcoes.unidade ? ` ${opcoes.unidade}` : ''}; procedência: ${texto.replace(/\n/g, '; ')}` },
    v, opcoes.unidade ? h('span', { class: 'fraco' }, ` ${opcoes.unidade}`) : null);
  return el;
}

/* transforma um elemento existente (dd, span) em régua, mantendo o texto */
export function marcarRegua(el, opcoes = {}) {
  const dados = { ...origemPadrao(), ...opcoes };
  const texto = textoProcedencia(dados);
  el.classList.add('regua');
  el.setAttribute('tabindex', '0');
  el.dataset.procedencia = texto;
  el.setAttribute('aria-label', `${(el.textContent || '').trim()}; procedência: ${texto.replace(/\n/g, '; ')}`);
  return el;
}

/* linha de procedência da tela: últimas chamadas à API (rota, status, hora UTC, ms). Atualiza sozinha. */
export function reguaTela(alvo, { maximo = 5 } = {}) {
  if (!alvo) return null;
  let caixa = alvo.querySelector(':scope > .regua-tela');
  if (!caixa) {
    caixa = h('footer', { class: 'regua-tela', 'aria-label': 'procedência dos dados desta tela' });
    alvo.append(caixa);
  }
  const render = () => {
    limpar(caixa);
    caixa.append(h('span', { class: 'rotulo' }, 'régua'));
    const lista = chamadas().slice(-maximo).reverse();
    if (!lista.length) { caixa.append(h('span', { class: 'vazio' }, 'nenhuma chamada à API ainda')); return; }
    const ol = h('ol');
    for (const c of lista) {
      ol.append(h('li', {},
        h('span', {}, `${c.metodo} ${c.caminho}`),
        h('span', { class: c.status >= 400 || c.status === 0 ? 'st-erro' : 'st-ok' }, String(c.status || 'rede')),
        h('span', {}, horaUtc(c.em)),
        h('span', {}, `${c.ms} ms`)));
    }
    caixa.append(ol);
  };
  render();
  aoChamar(render);
  return caixa;
}
