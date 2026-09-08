/* plat · coleção — leitora compartilhada do item `colecao` (L5-04-c). Renderiza capa, fichas com navegação
   (um item por vez, botões e setas do teclado, contador) e avisa o que ficou fora. Usada pela página interna
   /colecao (tela.js) e pela anônima /c/<token> (compartilhado.js). Nenhum HTML em string: só h(). */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

/* separa os itens citados pelo corpo em presentes (o leitor conseguiu carregar) e ausentes (ficaram fora do
   link ou sem acesso); `carregados` é Map(id → item) */
export function separar(refs, carregados) {
  const presentes = [];
  const ausentes = [];
  for (const ref of refs || []) {
    const item = carregados.get(ref.item_id);
    if (item) presentes.push({ ref, item });
    else ausentes.push({ item_id: ref.item_id, rotulo: ref.rotulo || '' });
  }
  return { presentes, ausentes };
}

/* ficha de um item presente: rótulo (ou título), tipo e data, resumo; `aoAbrir` opcional recebe o item e
   devolve o href do link "abrir" (a página anônima não passa nada) */
export function fichaDe(entrada, aoAbrir) {
  const { ref, item } = entrada;
  const f = h(
    'article',
    { class: 'colecao-ficha' },
    h('h3', {}, ref.rotulo || item.titulo),
    h('p', { class: 'fraco' }, `${item.tipo || ''}${item.modificado_em ? ' · ' + item.modificado_em.slice(0, 10) : ''}`),
    item.resumo ? h('p', {}, item.resumo) : null,
  );
  if (aoAbrir) f.append(h('p', {}, h('a', { class: 'botao', href: aoAbrir(item) }, t('acao.abrir'))));
  return f;
}

/* monta a leitora em `raiz`: capa, linhas de aviso (uma por item ausente/sem acesso) e a navegação entre as
   fichas presentes. A posição vem do fragmento da URL (#2) e volta para ele a cada troca. */
export function montar(raiz, capa, presentes, avisos, { aoAbrir } = {}) {
  limpar(raiz);
  if (capa && (capa.titulo || capa.midia || capa.subtitulo)) {
    const midia = capa.midia
      ? h('img', { class: 'colecao-midia', src: capa.midia, alt: capa.titulo || '', width: 960, height: 540 })
      : null;
    if (midia) midia.addEventListener('error', () => midia.remove(), { once: true });
    raiz.append(
      h(
        'header',
        { class: 'colecao-capa' },
        midia,
        h('h2', {}, capa.titulo || ''),
        capa.subtitulo ? h('p', { class: 'fraco' }, capa.subtitulo) : null,
      ),
    );
  }
  for (const texto of avisos || []) {
    const a = document.createElement('plat-aviso');
    a.mostrar(texto);
    raiz.append(a);
  }
  if (!presentes.length) {
    raiz.append(h('p', { class: 'fraco' }, t('colecao.vazia')));
    raiz.hidden = false;
    return;
  }
  let i = Math.max(0, Math.min(presentes.length - 1, (parseInt(location.hash.slice(1), 10) || 1) - 1));
  const ficha = h('div', { id: 'colecao-ficha' });
  const contador = h('span', { class: 'fraco', id: 'colecao-contador', 'aria-live': 'polite' });
  const btAnterior = h('button', { type: 'button', class: 'pequeno', id: 'colecao-anterior' }, t('colecao.anterior'));
  const btProximo = h('button', { type: 'button', class: 'pequeno', id: 'colecao-proximo' }, t('colecao.proxima'));
  const ir = (n) => {
    i = Math.max(0, Math.min(presentes.length - 1, n));
    limpar(ficha);
    ficha.append(fichaDe(presentes[i], aoAbrir));
    contador.textContent = t('colecao.contador', { n: i + 1, total: presentes.length });
    btAnterior.disabled = i === 0;
    btProximo.disabled = i === presentes.length - 1;
    history.replaceState(null, '', `#${i + 1}`);
  };
  btAnterior.addEventListener('click', () => ir(i - 1));
  btProximo.addEventListener('click', () => ir(i + 1));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') ir(i - 1);
    else if (e.key === 'ArrowRight') ir(i + 1);
  });
  raiz.append(
    h('nav', { class: 'colecao-nav', 'aria-label': t('colecao.titulo') }, btAnterior, contador, btProximo),
    ficha,
  );
  ir(i);
  raiz.hidden = false;
}
