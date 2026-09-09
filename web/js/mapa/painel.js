/* plat · mapa — painel "Camadas" e "Legenda" (item L2-01-mapa-web).

   A lista tem ordem (arrastar-e-soltar E dois botões por linha, para quem usa teclado ou leitor de tela
   — arrastar sozinho não é acessível e não se testa de forma estável), ligar/desligar, opacidade e
   enquadrar. A legenda NÃO é escrita aqui: cada entrada vem de `ficha.legenda`, que o servidor gera da
   mesma lista de classes que gerou o estilo (app/mapa/simbologia.py). O painel só desenha o que veio. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

function amostraDeLegenda(entrada) {
  const cor = entrada.cor;
  const span = h('span', { class: `legenda-amostra legenda-${entrada.forma}` });
  span.style.setProperty('--cor', cor);
  return span;
}

export class Painel {
  constructor(catalogo, { raizCamadas, raizLegenda, aoEnquadrar, aoErro }) {
    this.catalogo = catalogo;
    this.raizCamadas = raizCamadas;
    this.raizLegenda = raizLegenda;
    this.aoEnquadrar = aoEnquadrar;
    this.aoErro = aoErro || (() => {});
    this.arrastando = null;
    catalogo.aoMudar(() => this.desenhar());
  }

  desenhar() {
    this.desenharCamadas();
    this.desenharLegenda();
  }

  desenharCamadas() {
    const raiz = this.raizCamadas;
    limpar(raiz);
    const cat = this.catalogo;
    const ordenadas = [
      ...cat.ativas.map((id) => cat.ficha(id)).filter(Boolean),
      ...cat.disponiveis.filter((f) => !cat.ativas.includes(f.id)),
    ];
    for (const f of ordenadas) {
      const ativa = cat.ativas.includes(f.id);
      const li = h('li', {
        class: `camada-linha${ativa ? ' ativa' : ''}`,
        dataset: { camada: f.id },
        draggable: ativa ? 'true' : 'false',
      });
      const caixa = h('input', {
        type: 'checkbox', checked: ativa, id: `chk-${f.id}`,
        'aria-label': `${t('mapa.mostrar_camada')} ${f.titulo}`,
        onchange: async () => {
          try { await cat.alternar(f.id); } catch (e) { this.aoErro(e); this.desenhar(); }
        },
      });
      const titulo = h('label', { class: 'camada-titulo', for: `chk-${f.id}`, title: f.titulo }, f.titulo);
      const conta = h('span', { class: 'camada-conta' },
        f.n_feicoes === null || f.n_feicoes === undefined ? '' : `${f.n_feicoes.toLocaleString('pt-BR')}`);
      const cabecalho = h('div', { class: 'camada-cabecalho' }, caixa, titulo, conta);
      li.append(cabecalho);
      if (ativa) {
        const i = cat.ativas.indexOf(f.id);
        const faixa = h('input', {
          type: 'range', min: '0', max: '100', step: '1', class: 'camada-opacidade',
          value: String(Math.round((cat.opacidade.get(f.id) ?? 1) * 100)),
          'aria-label': `${t('mapa.opacidade')} ${f.titulo}`,
          oninput: (ev) => cat.definirOpacidade(f.id, Number(ev.target.value) / 100),
        });
        const subir = h('button', {
          type: 'button', class: 'botao-mini', disabled: i === 0,
          'aria-label': `${t('mapa.subir')} ${f.titulo}`, dataset: { acao: 'subir' },
          onclick: () => cat.mover(f.id, -1),
        }, '▲');
        const descer = h('button', {
          type: 'button', class: 'botao-mini', disabled: i === cat.ativas.length - 1,
          'aria-label': `${t('mapa.descer')} ${f.titulo}`, dataset: { acao: 'descer' },
          onclick: () => cat.mover(f.id, 1),
        }, '▼');
        const enquadrar = h('button', {
          type: 'button', class: 'botao-mini', 'aria-label': `${t('mapa.enquadrar')} ${f.titulo}`,
          dataset: { acao: 'enquadrar' }, onclick: () => this.aoEnquadrar(f.id),
        }, '⤢');
        li.append(h('div', { class: 'camada-controles' }, subir, descer, enquadrar, faixa));
      }
      this._arrastavel(li, f.id);
      raiz.append(li);
    }
  }

  _arrastavel(li, id) {
    li.addEventListener('dragstart', (ev) => {
      this.arrastando = id;
      ev.dataTransfer.effectAllowed = 'move';
      try { ev.dataTransfer.setData('text/plain', id); } catch { /* alguns navegadores recusam em teste */ }
    });
    li.addEventListener('dragover', (ev) => { ev.preventDefault(); li.classList.add('alvo'); });
    li.addEventListener('dragleave', () => li.classList.remove('alvo'));
    li.addEventListener('drop', (ev) => {
      ev.preventDefault();
      li.classList.remove('alvo');
      const origem = this.arrastando || ev.dataTransfer.getData('text/plain');
      this.arrastando = null;
      if (!origem || origem === id) return;
      const ativas = [...this.catalogo.ativas];
      if (!ativas.includes(origem) || !ativas.includes(id)) return;
      ativas.splice(ativas.indexOf(origem), 1);
      ativas.splice(ativas.indexOf(id), 0, origem);
      this.catalogo.reordenar(ativas);
    });
  }

  desenharLegenda() {
    const raiz = this.raizLegenda;
    limpar(raiz);
    const cat = this.catalogo;
    if (!cat.ativas.length) {
      raiz.append(h('p', { class: 'vazio' }, t('mapa.legenda_vazia')));
      return;
    }
    for (const id of cat.ativas) {
      const f = cat.ficha(id);
      if (!f) continue;
      const bloco = h('div', { class: 'legenda-bloco', dataset: { camada: id } },
        h('h3', {}, f.titulo));
      const ul = h('ul', { class: 'legenda-lista' });
      for (const entrada of f.legenda || []) {
        ul.append(h('li', {}, amostraDeLegenda(entrada), h('span', {}, entrada.rotulo)));
      }
      bloco.append(ul);
      raiz.append(bloco);
    }
  }
}
