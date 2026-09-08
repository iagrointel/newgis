/* plat — primitivas de arrasto (item L5-08-editor-arrasto), sem uma linha de biblioteca de terceiro.

   Duas mecânicas distintas, cada uma na API do navegador feita para ela:

   1. PALETA -> TELA e TELA -> TELA: HTML5 Drag and Drop (`draggable`, `dragstart`, `dragover`, `drop`). É a
      única que dá arrasto entre elementos distantes com imagem de arrasto do próprio navegador, e é a que o
      playwright desta máquina opera (`page.drag_and_drop`, medido). Carga no `dataTransfer` em dois tipos
      próprios: `application/x-plat-tipo` (widget novo, vindo da paleta) e `application/x-plat-no` (nó que já
      está no documento). O tipo MIME é lido em `dragover` por `dataTransfer.types` — `getData` só devolve
      valor no `drop`, por desenho do padrão.
   2. REDIMENSIONAR: Pointer Events com `setPointerCapture` (D14/L5_CONCEITO): funciona com mouse, caneta e
      TOQUE (o HTML5 DnD não dispara em toque nenhum — é exatamente por isso que toda operação tem alternativa
      de ponteiro único e de teclado, WCAG 2.2 SC 2.5.7).

   Nenhuma função aqui altera documento: todas chamam de volta quem as ligou. */

export const TIPO_NOVO = 'application/x-plat-tipo';
export const TIPO_NO = 'application/x-plat-no';

export function ligarOrigemPaleta(el, tipo) {
  el.draggable = true;
  el.addEventListener('dragstart', (ev) => {
    ev.dataTransfer.setData(TIPO_NOVO, tipo);
    ev.dataTransfer.effectAllowed = 'copy';
  });
}

export function ligarOrigemNo(el, id) {
  el.draggable = true;
  el.addEventListener('dragstart', (ev) => {
    ev.stopPropagation();               // um nó dentro de um contêiner arrasta a si mesmo, não o contêiner
    ev.dataTransfer.setData(TIPO_NO, id);
    ev.dataTransfer.effectAllowed = 'move';
    el.classList.add('arrastando');
  });
  el.addEventListener('dragend', () => el.classList.remove('arrastando'));
}

/* alvo de soltura. `aoSoltar({tipo, id})` recebe o que veio; devolver false marca a soltura como recusada
   (o editor mostra o motivo e o documento não muda). `aceita(carga)` decide se o alvo pisca. */
export function ligarAlvo(el, { aoSoltar, aceita = () => true, classe = 'arrasto-sobre' }) {
  let dentro = 0;
  const carga = (ev) => {
    const t = ev.dataTransfer?.types || [];
    if (t.includes(TIPO_NOVO)) return { tipo: 'novo' };
    if (t.includes(TIPO_NO)) return { tipo: 'no' };
    return null;
  };
  el.addEventListener('dragenter', (ev) => {
    const c = carga(ev);
    if (!c || !aceita(c)) return;
    ev.preventDefault(); ev.stopPropagation();
    dentro += 1; el.classList.add(classe);
  });
  el.addEventListener('dragover', (ev) => {
    const c = carga(ev);
    if (!c || !aceita(c)) return;
    ev.preventDefault(); ev.stopPropagation();
    ev.dataTransfer.dropEffect = c.tipo === 'novo' ? 'copy' : 'move';
  });
  el.addEventListener('dragleave', (ev) => {
    ev.stopPropagation();
    dentro = Math.max(0, dentro - 1);
    if (dentro === 0) el.classList.remove(classe);
  });
  el.addEventListener('drop', (ev) => {
    const dt = ev.dataTransfer;
    const novo = dt.getData(TIPO_NOVO);
    const id = dt.getData(TIPO_NO);
    if (!novo && !id) return;
    ev.preventDefault(); ev.stopPropagation();
    dentro = 0; el.classList.remove(classe);
    aoSoltar(novo ? { tipo: 'novo', valor: novo } : { tipo: 'no', valor: id });
  });
}

/* Redimensionar por arrasto: converte o deslocamento em PIXEL para número de COLUNAS antes de qualquer
   gravação — o documento nunca vê pixel (portão do item). `medirColuna()` devolve a largura de 1 coluna da
   grade em px (largura útil + vão, dividida por 12), medida na hora: a mesma alça funciona em 1440 px e no
   Pixel 7 sem constante escrita à mão. */
export function ligarRedimensionar(alca, { colunas, colunasMax = 12, medirColuna, aoPrever, aoSoltar }) {
  alca.style.touchAction = 'none';
  alca.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0 && ev.pointerType === 'mouse') return;
    ev.preventDefault(); ev.stopPropagation();
    const x0 = ev.clientX;
    const c0 = colunas();
    const larguraColuna = Math.max(1, medirColuna());
    alca.setPointerCapture(ev.pointerId);
    let atual = c0;
    const mover = (e) => {
      const delta = Math.round((e.clientX - x0) / larguraColuna);
      atual = Math.min(colunasMax, Math.max(1, c0 + delta));
      aoPrever?.(atual);
    };
    const soltar = (e) => {
      alca.removeEventListener('pointermove', mover);
      alca.removeEventListener('pointerup', soltar);
      alca.removeEventListener('pointercancel', soltar);
      try { alca.releasePointerCapture(e.pointerId); } catch { /* ponteiro já solto pelo navegador */ }
      aoSoltar(atual);
    };
    alca.addEventListener('pointermove', mover);
    alca.addEventListener('pointerup', soltar);
    alca.addEventListener('pointercancel', soltar);
  });
}
