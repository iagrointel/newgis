/* plat — painel "Ações" de cada widget no construtor (item L5-01-e-acoes-configuraveis, como o painel
   "Actions" do Experience Builder): com um widget selecionado, o construtor lista as mensagens em que ele é a
   ORIGEM (gatilho → alvo → ação → parâmetros) e oferece um formulário guiado — o gatilho vem dos eventos que o
   TIPO do widget emite (contrato do registro), o alvo é qualquer widget ou vista do documento, a ação é só o que
   o alvo ACEITA, e os parâmetros são a relação (campo de origem/alvo por atributo, ou espacial) e uma condição
   CQL2 sobre os registros de origem. Cada tentativa passa por `validarModelo` ANTES de entrar no documento: a
   regra reprovada aparece nomeada (`gatilho_repetido`, `alvo_incompativel`, `evento_incompativel`,
   `relacao_ausente`, `relacao_tipos`, `campo_inexistente`, `cql2`) — campo renomeado na fonte vira referência
   quebrada listada aqui, com a mensagem inteira marcada. As coleções são as mesmas do painel "Dados e
   mensagens" (L5-07); os dois painéis leem e escrevem `corpo.mensagens`. */
import { h, limpar } from '../base/dom.js';
import * as modelo from './modelo.js';
import * as cql2 from './cql2.js';

export function montarPainelAcoes({ raiz, no, colecoes, nosAtuais = () => [], aoMudar }) {
  modelo.garantirColecoes(colecoes);
  const corpoAtual = () => ({ nos: nosAtuais(), fontes: colecoes.fontes, vistas: colecoes.vistas, mensagens: colecoes.mensagens });
  const idx = () => modelo.indices(corpoAtual());
  const nomeDe = (id) => {
    const v = colecoes.vistas.find((x) => x.id === id); if (v) return `vista ${v.nome || id}`;
    const n = nosAtuais().find((x) => x.id === id); if (n) return `${n.tipo} ${id.slice(-4)}`;
    return id;
  };
  const caixa = h('section', { class: 'painel-acoes', id: 'painel-acoes', dataset: { no: no.id } }, h('h3', {}, 'Ações'));
  raiz.append(caixa);

  function desenhar() {
    limpar(caixa);
    caixa.append(h('h3', {}, 'Ações'));
    const corpo = corpoAtual();
    const validacao = modelo.validarModelo(corpo);
    const minhas = corpo.mensagens.map((m, i) => ({ m, i })).filter(({ m }) => m.gatilho?.origem === no.id);
    const ul = h('ul', { class: 'lista-dados', id: 'lista-acoes' });
    for (const { m, i } of minhas) {
      const errosDaMensagem = validacao.erros.filter((e) => e.campo.startsWith(`corpo.mensagens.${i}`));
      for (const [j, a] of (m.acoes || []).entries()) {
        const errosDaAcao = errosDaMensagem.filter((e) => e.campo.startsWith(`corpo.mensagens.${i}.acoes.${j}`) || !e.campo.includes('.acoes.'));
        const rel = a.relacao?.tipo ? ` · ${a.relacao.tipo}${a.relacao.campo_origem ? ` ${a.relacao.campo_origem} → ${a.relacao.campo_alvo}` : ''}` : '';
        const cond = a.parametros?.condicao ? ` · se ${cql2.texto ? cql2.texto(a.parametros.condicao) : JSON.stringify(a.parametros.condicao)}` : '';
        const li = h('li', { dataset: { mensagem: m.id, acao: String(j), quebrada: errosDaAcao.length ? '1' : '0' } },
          h('span', {}, `${m.gatilho.evento} → ${a.acao} em ${nomeDe(a.alvo)}${rel}${cond}`),
          ' ', botao('Remover', () => {
            m.acoes = m.acoes.filter((x) => x !== a);
            if (!m.acoes.length) colecoes.mensagens = colecoes.mensagens.filter((x) => x !== m);
            desenhar(); aoMudar?.();
          }, 'perigo'));
        if (errosDaAcao.length) li.append(h('p', { class: 'erro-form', role: 'alert', dataset: { regra: errosDaAcao[0].regra } }, `referência quebrada: ${errosDaAcao.map((e) => e.erro).join('; ')}`));
        ul.append(li);
      }
    }
    if (!minhas.length) ul.append(h('li', { class: 'fraco' }, 'nenhuma ação configurada para este widget'));
    caixa.append(ul);

    /* ------------------------------------------------------------ formulário guiado */
    const ix = idx();
    const eventos = modelo.eventosDe(corpo, no.id, ix);
    const alvos = [...corpo.vistas.map((v) => ({ id: v.id, rotulo: `vista ${v.nome || v.id}` })),
      ...corpo.nos.filter((n) => n.id !== no.id && modelo.CONTRATOS[n.tipo]).map((n) => ({ id: n.id, rotulo: `widget ${n.tipo} ${n.id.slice(-4)}` }))];
    const form = h('form', { class: 'form linha', id: 'form-acao', novalidate: true });
    const evento = h('select', { name: 'evento', id: 'acao-evento' }, ...eventos.map((e) => h('option', { value: e }, e)));
    const alvo = h('select', { name: 'alvo', id: 'acao-alvo' }, ...alvos.map((x) => h('option', { value: x.id }, x.rotulo)));
    const acao = h('select', { name: 'acao', id: 'acao-acao' });
    const relacao = h('select', { name: 'relacao', id: 'acao-relacao' });
    const campoOrigem = h('select', { name: 'campo_origem', id: 'acao-campo-origem' });
    const campoAlvo = h('select', { name: 'campo_alvo', id: 'acao-campo-alvo' });
    const condicao = h('input', { type: 'text', name: 'condicao', id: 'acao-condicao', maxlength: 4000, spellcheck: 'false' });
    const erroForm = h('p', { class: 'erro-form', id: 'acao-erro', role: 'alert', hidden: true });
    const bt = h('button', { type: 'submit', class: 'pequeno', id: 'acao-adicionar', disabled: !alvos.length || !eventos.length }, 'Adicionar ação');
    const fonteDe = (id) => modelo.fonteDe(corpo, id, ix);
    const preencherCampos = (sel, fonte) => { limpar(sel); for (const c of (fonte?.campos || []).filter((x) => x.tipo !== 'geometria')) sel.append(h('option', { value: c.nome }, `${c.nome} (${c.tipo})`)); };
    function aoTrocarAlvo() {
      limpar(acao);
      for (const a of modelo.acoesDe(corpo, alvo.value, ix)) acao.append(h('option', { value: a }, a));
      const fo = fonteDe(no.id); const fa = fonteDe(alvo.value);
      limpar(relacao);
      if (fo && fa && fo.id === fa.id) relacao.append(h('option', { value: 'mesma_fonte' }, 'mesma fonte'));
      else if (fo && fa) {
        relacao.append(h('option', { value: 'atributo' }, 'por atributo (campo de relação)'));
        if (fo.campos.some((c) => c.tipo === 'geometria') && fa.campos.some((c) => c.tipo === 'geometria')) relacao.append(h('option', { value: 'espacial' }, 'espacial (interseção)'));
      } else relacao.append(h('option', { value: '' }, '(sem dado)'));
      preencherCampos(campoOrigem, fo); preencherCampos(campoAlvo, fa);
      aoTrocarRelacao();
    }
    function aoTrocarRelacao() {
      const porAtributo = relacao.value === 'atributo';
      campoOrigem.closest('label').hidden = !porAtributo; campoAlvo.closest('label').hidden = !porAtributo;
    }
    alvo.addEventListener('change', aoTrocarAlvo);
    relacao.addEventListener('change', aoTrocarRelacao);
    form.append(campo('gatilho (evento deste widget)', evento), campo('alvo', alvo), campo('ação', acao), campo('relação', relacao),
      campo('campo de origem', campoOrigem), campo('campo do alvo', campoAlvo), campo('condição (CQL2, opcional)', condicao), bt, erroForm);
    if (alvos.length) aoTrocarAlvo();
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const dado = modelo.ACOES_DADO.includes(acao.value);
      let rel = null;
      if (dado && relacao.value) {
        rel = { tipo: relacao.value };
        if (relacao.value === 'atributo') Object.assign(rel, { campo_origem: campoOrigem.value, campo_alvo: campoAlvo.value, operador: 'in' });
      }
      const parametros = {};
      if (condicao.value.trim()) {
        try { parametros.condicao = cql2.normalizar(condicao.value.trim()); }
        catch (erro) { erroForm.hidden = false; erroForm.textContent = `condição inválida: ${erro.message}`; erroForm.dataset.regra = 'cql2'; return; }
      }
      const nova = { alvo: alvo.value, acao: acao.value, parametros, ...(rel ? { relacao: rel } : {}) };
      // a mesma origem + evento entra na MESMA mensagem (uma mensagem = um gatilho, N ações), como no EXB
      const existente = corpo.mensagens.find((m) => m.gatilho?.origem === no.id && m.gatilho?.evento === evento.value);
      const candidatas = existente
        ? corpo.mensagens.map((m) => (m === existente ? { ...m, acoes: [...m.acoes, nova] } : m))
        : [...corpo.mensagens, { id: modelo.gerarUlid(), gatilho: { origem: no.id, evento: evento.value }, acoes: [nova] }];
      const prova = modelo.validarModelo({ ...corpo, mensagens: candidatas });
      const i = existente ? corpo.mensagens.indexOf(existente) : corpo.mensagens.length;
      const j = existente ? existente.acoes.length : 0;
      const proprios = prova.erros.filter((x) => x.campo.startsWith(`corpo.mensagens.${i}.acoes.${j}`) || x.campo === `corpo.mensagens.${i}.gatilho.evento`);
      if (proprios.length) { erroForm.hidden = false; erroForm.textContent = proprios.map((x) => x.erro).join('; '); erroForm.dataset.regra = proprios[0].regra; return; }
      erroForm.hidden = true;
      if (existente) existente.acoes.push(nova);
      else colecoes.mensagens.push(candidatas[candidatas.length - 1]);
      desenhar(); aoMudar?.();
    });
    caixa.append(form);
  }
  desenhar();
  return { redesenhar: desenhar };
}

function campo(rotulo, input) { return h('label', { class: 'campo' }, h('span', {}, rotulo), input); }
function botao(rotulo, aoClicar, classe = '') {
  const b = h('button', { type: 'button', class: `pequeno ${classe}`.trim() }, rotulo);
  b.addEventListener('click', aoClicar);
  return b;
}
