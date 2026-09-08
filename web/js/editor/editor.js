/* plat — editor de arrasto: primitiva COMPARTILHADA dos construtores da linha L5 (item L5-08-editor-arrasto).

   Monta quatro regiões sobre um documento (`web/js/editor/documento.js`) e uma paleta
   (`web/js/editor/paleta.js` ou, quando o L5-06 publicar, o manifesto de widget):

     paleta  — cada tipo é ao mesmo tempo origem de arrasto E um botão "adicionar" (alternativa de ponteiro
               único e de teclado exigida pela WCAG 2.2 SC 2.5.7, L5_CONCEITO D14);
     tela    — grade de 12 colunas; largura de nó é `largura_colunas`, nunca pixel; soltar sobre um nó insere
               ANTES dele, soltar dentro de um contêiner insere no fim dele, soltar no fundo insere na raiz;
     estrutura — a árvore, que reflete o aninhamento e é o caminho de teclado completo (mover, aninhar,
               desaninhar, largura, remover), mais o menu "mover para" para quem só tem toque;
     propriedades — gerado do JSON Schema do tipo; valor fora do esquema é RECUSADO (o documento não muda) e a
               mensagem fica ao lado do campo.

   Regra de redesenho (achado de outro item, 07/09): o tratador de mudança de propriedade NUNCA redesenha o
   painel inteiro — isso apagaria a própria mensagem que acabou de escrever. Mudança de propriedade repinta só
   o nó na tela e o rótulo na árvore. */

import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import * as doc from './documento.js';
import { validarValor, valorDoControle, conferirSuportado } from './esquema.js';
import { ligarOrigemPaleta, ligarOrigemNo, ligarAlvo, ligarRedimensionar } from './arrasto.js';

const VAO_PADRAO = 8; // px; casa com --e2 usado no gap da grade em web/estilo/editor.css

export function criarEditor({ raiz, documento = doc.novoDocumento('app'), paleta, aoMudar = null }) {
  for (const [tipo, def] of Object.entries(paleta.tipos)) {
    const fora = conferirSuportado(def.esquema);
    if (fora.length) throw new Error(`esquema do tipo ${tipo} usa palavra não suportada pelo painel: ${fora.join(', ')}`);
  }

  let documentoAtual = documento;
  let selecionado = null;

  const elPaleta = h('section', { class: 'editor-paleta', 'aria-label': t('construtor.paleta') }, h('h2', {}, t('construtor.paleta')));
  const elTela = h('div', { class: 'editor-tela', id: 'tela', role: 'group', 'aria-label': t('construtor.tela') });
  const elEstrutura = h('div', { class: 'editor-arvore', id: 'estrutura', role: 'tree', 'aria-label': t('construtor.estrutura') });
  const elProps = h('div', { class: 'editor-props', id: 'propriedades' });
  const elMensagem = h('p', { class: 'editor-mensagem', id: 'editor-mensagem', role: 'status', 'aria-live': 'polite' }, '');

  limpar(raiz).append(
    h('div', { class: 'editor' },
      elPaleta,
      h('section', { class: 'editor-centro', 'aria-label': t('construtor.tela_documento') }, elMensagem, elTela),
      h('aside', { class: 'editor-lado' },
        h('section', { 'aria-label': t('construtor.estrutura') }, h('h2', {}, t('construtor.estrutura')), elEstrutura),
        h('section', { 'aria-label': t('construtor.propriedades') }, h('h2', {}, t('construtor.propriedades')), elProps))));

  function dizer(texto, tipo = 'ok') {
    elMensagem.textContent = texto;
    elMensagem.dataset.tipo = tipo;
  }

  function aplicar(novo, mensagem) {
    documentoAtual = novo;
    desenharTela();
    desenharEstrutura();
    desenharPropriedades();
    if (mensagem) dizer(mensagem);
    aoMudar?.(documentoAtual);
  }

  function tentar(fn, mensagem) {
    try {
      const novo = fn();
      aplicar(novo, mensagem);
      return true;
    } catch (e) {
      if (e instanceof doc.ErroEdicao) { dizer(e.message, 'erro'); return false; }
      throw e;
    }
  }

  /* ---------------------------------------------------------------- comandos (um só caminho para mouse,
     toque e teclado: o botão da paleta, a tecla e a soltura chamam EXATAMENTE estas quatro funções) */
  const api = {
    documento: () => documentoAtual,
    definirDocumento(d) { selecionado = null; aplicar(d); },
    selecionar(id) { selecionado = id; desenharTela(); desenharEstrutura(); desenharPropriedades(); },
    selecionado: () => selecionado,
    adicionar(tipo, { pai = null, antes = null, selecionar = true } = {}) {
      let idNovo = null;
      const ok = tentar(() => {
        const r = doc.inserir(documentoAtual, paleta, { tipo, pai, antes });
        idNovo = r.id;
        return r.documento;
      }, t('construtor.adicionado', { rotulo: paleta.tipos[tipo]?.rotulo || tipo }));
      if (ok && selecionar) api.selecionar(idNovo);
      return ok ? idNovo : null;
    },
    mover(id, { pai = null, antes = null } = {}) {
      return tentar(() => doc.mover(documentoAtual, paleta, id, { pai, antes }), t('construtor.movido'));
    },
    largura(id, colunas) {
      const c = Math.min(doc.COLUNAS, Math.max(1, Math.round(colunas)));
      return tentar(() => doc.redimensionar(documentoAtual, id, c), t('construtor.largura_definida', { n: c, total: doc.COLUNAS }));
    },
    remover(id) {
      if (selecionado === id) selecionado = null;
      return tentar(() => doc.remover(documentoAtual, id), t('construtor.removido'));
    },
  };

  /* ---------------------------------------------------------------- tela */
  function medirColunaDe(elemento) {
    const grade = elemento.parentElement;
    const vao = parseFloat(getComputedStyle(grade).columnGap) || VAO_PADRAO;
    return (grade.clientWidth + vao) / doc.COLUNAS;
  }

  function alvoDeSoltura(carga, { pai = null, antes = null }) {
    if (carga.tipo === 'novo') api.adicionar(carga.valor, { pai, antes });
    else api.mover(carga.valor, { pai, antes });
  }

  function desenharNo(no) {
    const def = paleta.tipos[no.tipo] || { rotulo: no.tipo };
    const el = h('div', {
      class: `no-editor tipo-${no.tipo}${selecionado === no.id ? ' selecionado' : ''}`,
      dataset: { no: no.id, tipo: no.tipo, colunas: String(no.largura_colunas) },
      tabindex: '0',
      role: 'group',
      'aria-label': t('construtor.no_rotulo', { rotulo: def.rotulo, n: no.largura_colunas, total: doc.COLUNAS }),
    });
    el.style.gridColumn = `span ${no.largura_colunas}`;
    el.addEventListener('click', (ev) => { ev.stopPropagation(); api.selecionar(no.id); });
    ligarOrigemNo(el, no.id);
    /* soltar SOBRE um nó = entrar antes dele, no mesmo pai (regra única, sem zona de meio pixel) */
    ligarAlvo(el, {
      aoSoltar: (carga) => {
        if (carga.tipo === 'no' && carga.valor === no.id) { dizer(t('construtor.sobre_si_mesmo'), 'erro'); return; }
        alvoDeSoltura(carga, { pai: no.pai ?? null, antes: no.id });
      },
    });

    const titulo = h('span', { class: 'no-titulo' }, def.rotulo);
    const resumo = h('span', { class: 'no-resumo', dataset: { resumo: no.id } }, resumoDe(no));
    el.append(h('header', { class: 'no-cabecalho' }, titulo, resumo));

    if (def.aceita_filhos) {
      const dentro = h('div', { class: 'no-filhos', dataset: { filhosDe: no.id }, role: 'group', 'aria-label': t('construtor.dentro_de', { rotulo: def.rotulo }) });
      for (const f of doc.filhos(documentoAtual, no.id)) dentro.append(desenharNo(f));
      if (!dentro.childElementCount) dentro.append(h('p', { class: 'vazio' }, t('construtor.conteiner_vazio')));
      ligarAlvo(dentro, { aoSoltar: (carga) => alvoDeSoltura(carga, { pai: no.id, antes: null }) });
      el.append(dentro);
    }

    const alca = h('button', {
      type: 'button', class: 'alca-largura', dataset: { alca: no.id },
      'aria-label': t('construtor.alca_largura', { rotulo: def.rotulo, n: no.largura_colunas }),
    });
    alca.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowRight') { ev.preventDefault(); api.largura(no.id, no.largura_colunas + 1); }
      if (ev.key === 'ArrowLeft') { ev.preventDefault(); api.largura(no.id, no.largura_colunas - 1); }
    });
    alca.addEventListener('click', (ev) => ev.stopPropagation());
    ligarRedimensionar(alca, {
      colunas: () => no.largura_colunas,
      medirColuna: () => medirColunaDe(el),
      aoPrever: (c) => { el.style.gridColumn = `span ${c}`; },
      aoSoltar: (c) => api.largura(no.id, c),
    });
    el.append(alca);
    return el;
  }

  function resumoDe(no) {
    const p = no.propriedades || {};
    return String(p.rotulo ?? p.texto ?? p.alternativo ?? p.zoom ?? p.linhas_por_pagina ?? '');
  }

  function desenharTela() {
    limpar(elTela);
    for (const n of doc.filhos(documentoAtual, null)) elTela.append(desenharNo(n));
    if (!elTela.childElementCount) elTela.append(h('p', { class: 'vazio', id: 'tela-vazia' }, t('construtor.tela_vazia')));
  }
  ligarAlvo(elTela, { aoSoltar: (carga) => alvoDeSoltura(carga, { pai: null, antes: null }) });
  elTela.addEventListener('click', () => api.selecionar(null));

  /* ---------------------------------------------------------------- paleta */
  function desenharPaleta() {
    const ul = h('ul', { class: 'lista-paleta' });
    for (const tipo of paleta.ordem) {
      const def = paleta.tipos[tipo];
      const arrastavel = h('span', { class: 'paleta-item', dataset: { paleta: tipo } }, def.rotulo);
      ligarOrigemPaleta(arrastavel, tipo);
      const bt = h('button', { type: 'button', class: 'pequeno', dataset: { adicionar: tipo } }, t('construtor.adicionar'));
      bt.addEventListener('click', () => {
        /* alternativa sem arrasto: entra dentro do contêiner selecionado, senão no fim da raiz */
        const sel = selecionado ? doc.acharNo(documentoAtual, selecionado) : null;
        const pai = sel && paleta.tipos[sel.tipo]?.aceita_filhos ? sel.id : (sel?.pai ?? null);
        api.adicionar(tipo, { pai });
      });
      ul.append(h('li', {}, arrastavel, bt));
    }
    limpar(elPaleta).append(h('h2', {}, t('construtor.paleta')), ul);
  }

  /* ---------------------------------------------------------------- estrutura (árvore) */
  function irmaos(no) { return doc.filhos(documentoAtual, no.pai ?? null); }

  function porTeclado(ev, no) {
    const lista = irmaos(no);
    const i = lista.findIndex((x) => x.id === no.id);
    if (ev.altKey && ev.key === 'ArrowUp' && i > 0) { ev.preventDefault(); api.mover(no.id, { pai: no.pai ?? null, antes: lista[i - 1].id }); }
    else if (ev.altKey && ev.key === 'ArrowDown' && i < lista.length - 1) {
      ev.preventDefault();
      const depois = lista[i + 2];
      api.mover(no.id, { pai: no.pai ?? null, antes: depois ? depois.id : null });
    } else if (ev.altKey && ev.key === 'ArrowRight' && i > 0) {
      ev.preventDefault(); api.mover(no.id, { pai: lista[i - 1].id, antes: null });
    } else if (ev.altKey && ev.key === 'ArrowLeft' && no.pai) {
      ev.preventDefault();
      const pai = doc.acharNo(documentoAtual, no.pai);
      api.mover(no.id, { pai: pai.pai ?? null, antes: null });
    } else if (ev.shiftKey && ev.key === 'ArrowRight') { ev.preventDefault(); api.largura(no.id, no.largura_colunas + 1); }
    else if (ev.shiftKey && ev.key === 'ArrowLeft') { ev.preventDefault(); api.largura(no.id, no.largura_colunas - 1); }
    else if (ev.key === 'Delete') { ev.preventDefault(); api.remover(no.id); }
    else return;
    const foco = elEstrutura.querySelector(`[data-arvore="${no.id}"]`);
    foco?.focus();
  }

  function menuMoverPara(no) {
    /* alternativa de PONTEIRO ÚNICO (toque): escolher o destino numa lista e apertar Mover — nenhum gesto. */
    const opcoes = [h('option', { value: '' }, t('construtor.raiz'))];
    for (const { no: outro, nivel } of doc.emProfundidade(documentoAtual)) {
      if (!paleta.tipos[outro.tipo]?.aceita_filhos) continue;
      if (outro.id === no.id || doc.ehDescendente(documentoAtual, outro.id, no.id)) continue;
      opcoes.push(h('option', { value: outro.id }, `${'— '.repeat(nivel)}${paleta.tipos[outro.tipo].rotulo}: ${resumoDe(outro)}`));
    }
    const sel = h('select', { dataset: { moverPara: no.id }, 'aria-label': t('construtor.mover_para') }, ...opcoes);
    sel.value = no.pai ?? '';
    const bt = h('button', { type: 'button', class: 'pequeno', dataset: { mover: no.id } }, t('construtor.mover'));
    bt.addEventListener('click', () => api.mover(no.id, { pai: sel.value || null, antes: null }));
    return [sel, bt];
  }

  function desenharEstrutura() {
    limpar(elEstrutura);
    const linhas = doc.emProfundidade(documentoAtual);
    if (!linhas.length) { elEstrutura.append(h('p', { class: 'vazio' }, t('construtor.documento_vazio'))); return; }
    for (const { no, nivel } of linhas) {
      const def = paleta.tipos[no.tipo] || { rotulo: no.tipo };
      const bt = h('button', {
        type: 'button', class: `arvore-item${selecionado === no.id ? ' selecionado' : ''}`,
        dataset: { arvore: no.id, nivel: String(nivel), pai: no.pai ?? '' },
      },
        h('span', { class: 'arvore-rotulo' }, `${def.rotulo}`),
        h('span', { class: 'arvore-resumo', dataset: { arvoreResumo: no.id } }, resumoDe(no)),
        h('span', { class: 'arvore-colunas', dataset: { arvoreColunas: no.id } }, `${no.largura_colunas}/${doc.COLUNAS}`));
      bt.style.paddingLeft = `${nivel * 16 + 8}px`;
      bt.addEventListener('click', () => api.selecionar(no.id));
      bt.addEventListener('keydown', (ev) => porTeclado(ev, no));
      const acoes = h('div', { class: 'arvore-acoes' },
        ...menuMoverPara(no),
        botao('−', t('construtor.diminuir_largura', { rotulo: def.rotulo }), () => api.largura(no.id, no.largura_colunas - 1), { larguraMenos: no.id }),
        botao('+', t('construtor.aumentar_largura', { rotulo: def.rotulo }), () => api.largura(no.id, no.largura_colunas + 1), { larguraMais: no.id }),
        botao(t('construtor.remover'), t('construtor.remover_rotulo', { rotulo: def.rotulo }), () => api.remover(no.id), { remover: no.id }));
      /* a linha é o treeitem (filho direto do role=tree, como a ARIA exige); o botão dentro dela é o que recebe foco */
      elEstrutura.append(h('div', {
        class: 'arvore-linha', dataset: { linha: no.id }, role: 'treeitem',
        'aria-level': String(nivel + 1), 'aria-selected': selecionado === no.id ? 'true' : 'false',
      }, bt, acoes));
    }
  }

  function botao(texto, rotulo, aoClicar, dataset) {
    const b = h('button', { type: 'button', class: 'pequeno', 'aria-label': rotulo, dataset }, texto);
    b.addEventListener('click', aoClicar);
    return b;
  }

  /* ---------------------------------------------------------------- propriedades (gerado do JSON Schema) */
  function desenharPropriedades() {
    limpar(elProps);
    const no = selecionado ? doc.acharNo(documentoAtual, selecionado) : null;
    if (!no) { elProps.append(h('p', { class: 'vazio' }, t('construtor.selecione'))); return; }
    const def = paleta.tipos[no.tipo];
    elProps.append(h('p', { class: 'props-tipo' }, def.rotulo));

    const largura = h('input', {
      type: 'number', min: '1', max: String(doc.COLUNAS), step: '1', id: 'prop-largura', value: String(no.largura_colunas),
    });
    largura.addEventListener('change', () => {
      const v = Number(largura.value);
      if (!Number.isInteger(v) || v < 1 || v > doc.COLUNAS) { dizer(t('construtor.largura_invalida', { total: doc.COLUNAS }), 'erro'); largura.value = String(no.largura_colunas); return; }
      api.largura(no.id, v);
    });
    elProps.append(h('label', { class: 'campo' }, h('span', {}, t('construtor.largura_campo', { total: doc.COLUNAS })), largura));

    for (const [nome, esq] of Object.entries(def.esquema.properties || {})) {
      elProps.append(campoDeEsquema(no, nome, esq, (def.esquema.required || []).includes(nome)));
    }
  }

  function campoDeEsquema(no, nome, esq, obrigatorio) {
    const valorAtual = (no.propriedades || {})[nome];
    const erro = h('span', { class: 'campo-erro', dataset: { erro: nome }, role: 'alert' }, '');
    let controle;
    if (esq.enum) {
      controle = h('select', { dataset: { prop: nome } }, ...esq.enum.map((v) => h('option', { value: String(v) }, String(v))));
      controle.value = String(valorAtual ?? esq.default ?? esq.enum[0]);
    } else if (esq.type === 'boolean') {
      controle = h('input', { type: 'checkbox', dataset: { prop: nome } });
      controle.checked = !!valorAtual;
    } else {
      controle = h('input', {
        type: esq.type === 'integer' || esq.type === 'number' ? 'number' : 'text',
        dataset: { prop: nome }, value: valorAtual === undefined || valorAtual === null ? '' : String(valorAtual),
      });
      if (esq.minimum !== undefined) controle.min = String(esq.minimum);
      if (esq.maximum !== undefined) controle.max = String(esq.maximum);
      if (esq.type === 'integer') controle.step = '1';
    }
    controle.addEventListener('change', () => {
      const bruto = controle.type === 'checkbox' ? controle.checked : controle.value;
      const conv = valorDoControle(esq, bruto);
      const valor = conv.valor;
      const problemas = conv.ok
        ? [
          ...(obrigatorio && (valor === undefined || valor === '') ? [{ erro: t('form.obrigatorio') }] : []),
          ...validarValor(esq, valor, nome),
        ]
        : [{ erro: t('construtor.tipo_invalido', { tipo: esq.type }) }];
      if (problemas.length) {
        /* RECUSA: o documento não muda, o valor volta ao que era e a mensagem fica no campo. Nada aqui
           redesenha o painel — redesenhar apagaria esta mensagem no mesmo instante em que ela aparece. */
        erro.textContent = problemas[0].erro;
        controle.setAttribute('aria-invalid', 'true');
        dizer(`${esq.title || nome}: ${problemas[0].erro}`, 'erro');
        return;
      }
      erro.textContent = '';
      controle.removeAttribute('aria-invalid');
      documentoAtual = doc.definirPropriedade(documentoAtual, no.id, nome, valor);
      no.propriedades = { ...no.propriedades, [nome]: valor };
      const noAtualizado = doc.acharNo(documentoAtual, no.id);
      const naTela = elTela.querySelector(`[data-resumo="${no.id}"]`);
      if (naTela) naTela.textContent = resumoDe(noAtualizado);
      const naArvore = elEstrutura.querySelector(`[data-arvore-resumo="${no.id}"]`);
      if (naArvore) naArvore.textContent = resumoDe(noAtualizado);
      dizer(t('construtor.propriedade_gravada', { campo: esq.title || nome }));
      aoMudar?.(documentoAtual);
    });
    return h('label', { class: 'campo' },
      h('span', {}, `${esq.title || nome}${obrigatorio ? ' *' : ''}`), controle, erro);
  }

  desenharPaleta();
  aplicar(documentoAtual);
  return api;
}
