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

/* ------------------------------------------------------------------------------------------------------------
   arrasto por TOQUE (item L5-15-vista-movel-responsivo): o HTML5 DnD acima nunca dispara em toque (comprovado
   pelo L5-08 — por isso aquele item só deu alternativa de toque SEM gesto, botão "Adicionar" e menu "mover
   para"). Este item pede o gesto de verdade em tablet, então aqui vai um SEGUNDO caminho, por Pointer Events
   (a mesma API que já resolve o redimensionar por toque logo abaixo), registrado ao LADO do HTML5 DnD — o
   mouse continua usando dragstart/drop; só pointerType 'touch' entra nesta rota. Um LIMIAR de 8 px antes de
   assumir o gesto (`LIMIAR_TOQUE_PX`) é o que deixa um toque simples continuar sendo toque (seleciona,
   dispara o `click` normal) e só um toque que ANDA vira arrasto — sem isso, tocar para selecionar um nó já
   dispararia uma captura de ponteiro e quebraria o toque simples. */

const LIMIAR_TOQUE_PX = 8;
const ALVOS = new Map(); // Element (alvo de soltura) -> {aoSoltar, aceita, classe}

function alvoTatilEm(x, y) {
  const el = document.elementFromPoint(x, y);
  const alvoEl = el?.closest?.('[data-alvo-arrasto="1"]');
  if (!alvoEl || !ALVOS.has(alvoEl)) return null;
  return { el: alvoEl, ...ALVOS.get(alvoEl) };
}

function iniciarArrastoTatil(origemEl, carga) {
  const fantasma = origemEl.cloneNode(true);
  fantasma.classList.add('arrasto-fantasma');
  fantasma.removeAttribute('id');
  fantasma.style.position = 'fixed';
  fantasma.style.left = '0'; fantasma.style.top = '0';
  fantasma.style.width = `${origemEl.offsetWidth}px`;
  fantasma.style.pointerEvents = 'none';
  fantasma.style.zIndex = '9999';
  document.body.append(fantasma);
  origemEl.classList.add('arrastando');
  let ultimoAlvo = null;
  const mover = (x, y) => {
    fantasma.style.transform = `translate(${x - origemEl.offsetWidth / 2}px, ${y - 12}px)`;
    const alvo = alvoTatilEm(x, y);
    if (ultimoAlvo && ultimoAlvo.el !== alvo?.el) ultimoAlvo.el.classList.remove(ultimoAlvo.classe);
    if (alvo && alvo.el !== ultimoAlvo?.el && alvo.aceita(carga)) alvo.el.classList.add(alvo.classe);
    ultimoAlvo = alvo && alvo.aceita(carga) ? alvo : null;
  };
  const aoMover = (ev) => { ev.preventDefault(); mover(ev.clientX, ev.clientY); };
  const encerrar = () => {
    document.removeEventListener('pointermove', aoMover);
    document.removeEventListener('pointerup', aoSoltar);
    document.removeEventListener('pointercancel', aoCancelar);
    fantasma.remove();
    origemEl.classList.remove('arrastando');
    if (ultimoAlvo) ultimoAlvo.el.classList.remove(ultimoAlvo.classe);
  };
  const aoSoltar = () => { const alvo = ultimoAlvo; encerrar(); if (alvo) alvo.aoSoltar(carga); };
  const aoCancelar = () => encerrar();
  document.addEventListener('pointermove', aoMover);
  document.addEventListener('pointerup', aoSoltar);
  document.addEventListener('pointercancel', aoCancelar);
  return mover;
}

/* liga a origem de um arrasto por toque num elemento já `draggable` (HTML5, para mouse). `obterCarga()`
   devolve `{tipo:'novo', valor:<tipo>}` ou `{tipo:'no', valor:<id>}` — quem chama decide. */
function ligarOrigemToque(el, obterCarga) {
  el.style.touchAction = 'none'; // sem isso o navegador rouba o gesto para rolar a página antes do limiar
  let inicio = null;
  const aoDescer = (ev) => {
    if (ev.pointerType !== 'touch') return;
    inicio = { x: ev.clientX, y: ev.clientY, id: ev.pointerId };
    document.addEventListener('pointermove', aoAndar);
    document.addEventListener('pointerup', aoSoltarSemMover);
    document.addEventListener('pointercancel', aoSoltarSemMover);
  };
  const aoAndar = (ev) => {
    if (!inicio || ev.pointerId !== inicio.id) return;
    const dx = ev.clientX - inicio.x; const dy = ev.clientY - inicio.y;
    if (Math.hypot(dx, dy) < LIMIAR_TOQUE_PX) return;
    document.removeEventListener('pointermove', aoAndar);
    document.removeEventListener('pointerup', aoSoltarSemMover);
    document.removeEventListener('pointercancel', aoSoltarSemMover);
    const mover = iniciarArrastoTatil(el, obterCarga());
    mover(ev.clientX, ev.clientY);
    inicio = null;
  };
  const aoSoltarSemMover = () => {
    document.removeEventListener('pointermove', aoAndar);
    document.removeEventListener('pointerup', aoSoltarSemMover);
    document.removeEventListener('pointercancel', aoSoltarSemMover);
    inicio = null; // ficou abaixo do limiar: solta como toque simples, o `click` do navegador segue seu curso
  };
  el.addEventListener('pointerdown', aoDescer);
}

export function ligarOrigemPaleta(el, tipo) {
  el.draggable = true;
  el.addEventListener('dragstart', (ev) => {
    ev.dataTransfer.setData(TIPO_NOVO, tipo);
    ev.dataTransfer.effectAllowed = 'copy';
  });
  ligarOrigemToque(el, () => ({ tipo: 'novo', valor: tipo }));
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

/* toque no NÓ: só a partir do cabeçalho (`elCabecalho`), nunca do nó inteiro — o corpo do nó continua livre
   para rolagem vertical da tela e para o toque simples de seleção (click), e a alça de largura (mais abaixo)
   continua com o seu próprio Pointer Events sem disputar o mesmo elemento. */
export function ligarOrigemNoToque(elCabecalho, id) {
  ligarOrigemToque(elCabecalho, () => ({ tipo: 'no', valor: id }));
}

/* alvo de soltura. `aoSoltar({tipo, id})` recebe o que veio; devolver false marca a soltura como recusada
   (o editor mostra o motivo e o documento não muda). `aceita(carga)` decide se o alvo pisca. */
export function ligarAlvo(el, { aoSoltar, aceita = () => true, classe = 'arrasto-sobre' }) {
  let dentro = 0;
  el.dataset.alvoArrasto = '1';
  ALVOS.set(el, { aoSoltar, aceita, classe });
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
