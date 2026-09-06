/* plat · mapa — painel de camadas do mapa (item L2-01-a-documento-mapa): lista ordenada, arrasta-e-solta para
   reordenar, caixa de visibilidade e botão de salvar. Regra do dono: arrasta-e-solta em tudo — e, junto,
   teclado (Alt+seta) e dois botões, porque arrastar não é acessível sozinho e porque o teste precisa de um
   caminho determinístico quando o navegador não entrega evento de arrasto.

   O painel não desenha camada nenhuma no canvas: nesta máquina não há servidor de tiles (o item L2-01-b
   instala o Martin), e o próprio servidor diz isso em `camada.tiles.pronto`. Em vez de fingir um desenho, a
   linha da camada mostra o selo "sem tiles" com o motivo que veio da API. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

const ARRASTANDO = 'arrastando';

export function montarPainel({ raiz, camadas, aoReordenar, aoAlternarVisivel }) {
  const lista = h('ul', { class: 'camadas-lista', id: 'camadas-lista', role: 'list' });
  let arrastado = null;

  const ids = () => [...lista.querySelectorAll('li')].map((li) => li.dataset.id);

  const mover = (li, delta) => {
    const irmaos = [...lista.querySelectorAll('li')];
    const i = irmaos.indexOf(li);
    const j = i + delta;
    if (j < 0 || j >= irmaos.length) return;
    if (delta < 0) lista.insertBefore(li, irmaos[j]);
    else lista.insertBefore(irmaos[j], li);
    aoReordenar(ids());
    li.querySelector('.camada-pega').focus();
  };

  for (const c of camadas) {
    const pega = h(
      'button',
      {
        type: 'button',
        class: 'camada-pega',
        title: t('mapa.camadas_mover_ajuda'),
        'aria-label': `${t('mapa.camadas_mover')}: ${c.titulo}`,
      },
      '⠿',
    );
    const caixa = h('input', { type: 'checkbox', class: 'camada-visivel', checked: c.visivel !== false });
    caixa.addEventListener('change', () => aoAlternarVisivel(c.id, caixa.checked));
    const selo = c.tiles && c.tiles.pronto === false
      ? h('span', { class: 'camada-selo', title: c.tiles.motivo || '' }, t('mapa.camada_sem_tiles'))
      : null;
    const li = h(
      'li',
      { class: 'camada-linha', draggable: 'true', dataset: { id: c.id, ref: c.ref } },
      pega,
      h('label', { class: 'camada-rotulo' }, caixa, h('span', { class: 'camada-titulo' }, c.titulo)),
      h('span', { class: 'camada-tipo' }, c.tipo),
      selo,
      h('span', { class: 'camada-botoes' },
        h('button', { type: 'button', class: 'pequeno camada-subir', 'aria-label': t('mapa.camadas_subir'), onclick: () => mover(li, -1) }, '↑'),
        h('button', { type: 'button', class: 'pequeno camada-descer', 'aria-label': t('mapa.camadas_descer'), onclick: () => mover(li, +1) }, '↓')),
    );
    pega.addEventListener('keydown', (ev) => {
      if (!ev.altKey) return;
      if (ev.key === 'ArrowUp') { ev.preventDefault(); mover(li, -1); }
      if (ev.key === 'ArrowDown') { ev.preventDefault(); mover(li, +1); }
    });
    li.addEventListener('dragstart', (ev) => {
      arrastado = li;
      li.classList.add(ARRASTANDO);
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('text/plain', c.id);
    });
    li.addEventListener('dragend', () => { li.classList.remove(ARRASTANDO); arrastado = null; });
    li.addEventListener('dragover', (ev) => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'move';
      const alvo = li;
      if (!arrastado || arrastado === alvo) return;
      const caixaAlvo = alvo.getBoundingClientRect();
      const meio = caixaAlvo.top + caixaAlvo.height / 2;
      if (ev.clientY < meio) lista.insertBefore(arrastado, alvo);
      else lista.insertBefore(arrastado, alvo.nextSibling);
    });
    li.addEventListener('drop', (ev) => { ev.preventDefault(); aoReordenar(ids()); });
    lista.append(li);
  }
  limpar(raiz);
  raiz.append(lista);
  return { ids };
}
