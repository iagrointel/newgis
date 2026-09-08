/* plat — painel "Dados e mensagens" do construtor (item L5-07): edita `corpo.fontes`, `corpo.vistas` e
   `corpo.mensagens` do documento aberto em /construtor, sem tocar nos nós (o editor de arrasto cuida deles).
   Fonte: item do catálogo (o painel lê o item e deduz os campos de uma amostra) ou caminho do servidor.
   Vista: fonte + filtro em CQL2-text (convertido para JSON ao salvar). Mensagem: gatilho (origem: vista ou
   widget; evento) + uma ação (alvo, ação, relação). Toda mudança passa por `validarModelo`: ERRO bloqueia a
   gravação e aparece ao lado (é aqui que "sem relação é recusado no construtor com mensagem"); AVISO (ciclo)
   aparece e deixa salvar. O painel devolve o corpo pelo `aoMudar`, e o construtor grava tudo junto. */
import { h, limpar } from '../base/dom.js';
import * as modelo from './modelo.js';
import * as cql2 from './cql2.js';
import { Fonte, deduzirCampos } from './fontes.js';

export function montarPainelDados({ raiz, colecoes, nosAtuais = () => [], aoMudar }) {
  /* `colecoes` = {fontes, vistas, mensagens} (vive aqui; o construtor junta ao corpo na gravação); os nós vêm do
     editor de arrasto a cada consulta (`nosAtuais`), porque o editor troca o objeto do documento a cada edição */
  modelo.garantirColecoes(colecoes);
  const corpo = new Proxy(colecoes, { get: (alvo, chave) => (chave === 'nos' ? nosAtuais() : alvo[chave]), set: (alvo, chave, valor) => { alvo[chave] = valor; return true; } });
  const aviso = h('plat-aviso', { id: 'dados-aviso' });
  const listaErros = h('ul', { id: 'dados-erros', class: 'dados-erros' });
  const secFontes = h('section', { class: 'cartao', id: 'sec-fontes' }, h('h2', {}, 'Fontes'));
  const secVistas = h('section', { class: 'cartao', id: 'sec-vistas' }, h('h2', {}, 'Vistas'));
  const secMsgs = h('section', { class: 'cartao', id: 'sec-mensagens' }, h('h2', {}, 'Mensagens (gatilho → ação)'));
  raiz.append(aviso, listaErros, secFontes, secVistas, secMsgs);

  const estado = { erros: [], avisos: [] };
  function validar() {
    const r = modelo.validarModelo({ nos: nosAtuais(), fontes: corpo.fontes, vistas: corpo.vistas, mensagens: corpo.mensagens });
    estado.erros = r.erros; estado.avisos = r.avisos;
    limpar(listaErros);
    for (const e of r.erros) listaErros.append(h('li', { class: 'erro', dataset: { regra: e.regra, campo: e.campo } }, `${e.campo}: ${e.erro}`));
    for (const a of r.avisos) listaErros.append(h('li', { class: 'aviso', dataset: { regra: a.regra } }, a.aviso));
    raiz.dataset.erros = String(r.erros.length);
    raiz.dataset.avisos = String(r.avisos.length);
    return r;
  }
  function mudou() { validar(); aoMudar?.({ colecoes, erros: estado.erros, avisos: estado.avisos }); }

  const nomeDe = (id) => corpo.fontes.find((f) => f.id === id)?.nome || corpo.vistas.find((v) => v.id === id)?.nome
    || (corpo.nos || []).find((n) => n.id === id) && `${(corpo.nos || []).find((n) => n.id === id).tipo} ${id.slice(-4)}` || id;

  /* ---------------------------------------------------------------- fontes */
  function desenharFontes() {
    limpar(secFontes);
    secFontes.append(h('h2', {}, 'Fontes'));
    const ul = h('ul', { class: 'lista-dados', id: 'lista-fontes' });
    for (const f of corpo.fontes) {
      const li = h('li', { dataset: { fonte: f.id } },
        h('strong', {}, f.nome || f.id), ' ', h('span', { class: 'fraco' }, `${f.origem?.tipo}${f.origem?.item_id ? ' ' + f.origem.item_id : ''} · ${(f.campos || []).length} campo(s)`),
        ' ', botao('Remover', () => { corpo.fontes = corpo.fontes.filter((x) => x !== f); corpo.vistas = corpo.vistas.filter((v) => v.fonte !== f.id); desenharTudo(); mudou(); }, 'perigo'));
      ul.append(li);
    }
    const form = h('form', { class: 'form linha', id: 'form-fonte', novalidate: true });
    const nome = h('input', { type: 'text', name: 'nome', required: true, maxlength: 120 });
    const tipo = h('select', { name: 'tipo' }, h('option', { value: 'item' }, 'item do catálogo'), h('option', { value: 'url' }, 'caminho do servidor'));
    const ref = h('input', { type: 'text', name: 'referencia', required: true, maxlength: 400, spellcheck: 'false' });
    const bt = h('button', { type: 'submit', class: 'pequeno', id: 'fonte-adicionar' }, 'Adicionar fonte');
    form.append(campo('nome', nome), campo('origem', tipo), campo('item (id) ou caminho', ref), bt);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const origem = tipo.value === 'item' ? { tipo: 'item', item_id: ref.value.trim() } : { tipo: 'url', url: ref.value.trim() };
      const f = { id: modelo.gerarUlid(), nome: nome.value.trim(), origem, campos: [] };
      bt.disabled = true;
      try {
        const fonte = new Fonte(f);
        await fonte.carregar();
        f.campos = deduzirCampos(fonte.feicoes);
        aviso.mostrar?.(`fonte ${f.nome}: ${fonte.feicoes.length} feição(ões), ${f.campos.length} campo(s) lidos`, 'ok');
      } catch (erro) {
        aviso.mostrar?.(`fonte ${f.nome}: não foi possível ler agora (${erro.message}); os campos ficam vazios até a leitura funcionar`, 'atencao');
      }
      bt.disabled = false;
      corpo.fontes.push(f);
      desenharTudo(); mudou();
    });
    secFontes.append(ul, form);
  }

  /* ---------------------------------------------------------------- vistas */
  function desenharVistas() {
    limpar(secVistas);
    secVistas.append(h('h2', {}, 'Vistas'));
    const ul = h('ul', { class: 'lista-dados', id: 'lista-vistas' });
    for (const v of corpo.vistas) {
      ul.append(h('li', { dataset: { vista: v.id } },
        h('strong', {}, v.nome || v.id), ' ', h('span', { class: 'fraco' }, `fonte ${nomeDe(v.fonte)}${v.filtro ? ' · filtro ' + JSON.stringify(v.filtro) : ''}`),
        ' ', botao('Remover', () => { corpo.vistas = corpo.vistas.filter((x) => x !== v); desenharTudo(); mudou(); }, 'perigo')));
    }
    const form = h('form', { class: 'form linha', id: 'form-vista', novalidate: true });
    const nome = h('input', { type: 'text', name: 'nome', required: true, maxlength: 120 });
    const fonte = h('select', { name: 'fonte' }, ...corpo.fontes.map((f) => h('option', { value: f.id }, f.nome || f.id)));
    const filtro = h('input', { type: 'text', name: 'filtro', maxlength: 4000, spellcheck: 'false' });
    const bt = h('button', { type: 'submit', class: 'pequeno', id: 'vista-adicionar', disabled: !corpo.fontes.length }, 'Adicionar vista');
    form.append(campo('nome', nome), campo('fonte', fonte), campo('filtro (CQL2, opcional)', filtro), bt);
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      let f = null;
      try { f = cql2.normalizar(filtro.value.trim() || null); }
      catch (erro) { aviso.mostrar?.(`filtro inválido: ${erro.message}`, 'erro'); return; }
      corpo.vistas.push({ id: modelo.gerarUlid(), nome: nome.value.trim(), fonte: fonte.value, filtro: f, selecao: [], ordenacao: [], campos: null });
      desenharTudo(); mudou();
    });
    secVistas.append(ul, form);
  }

  /* ---------------------------------------------------------------- mensagens */
  function desenharMensagens() {
    limpar(secMsgs);
    secMsgs.append(h('h2', {}, 'Mensagens (gatilho → ação)'));
    const ul = h('ul', { class: 'lista-dados', id: 'lista-mensagens' });
    for (const m of corpo.mensagens) {
      const a = m.acoes[0] || {};
      ul.append(h('li', { dataset: { mensagem: m.id } },
        h('span', {}, `${nomeDe(m.gatilho.origem)} · ${m.gatilho.evento} → ${a.acao} em ${nomeDe(a.alvo)}${a.relacao?.tipo ? ` (${a.relacao.tipo}${a.relacao.campo_origem ? ` ${a.relacao.campo_origem}=${a.relacao.campo_alvo}` : ''})` : ''}`),
        ' ', botao('Remover', () => { corpo.mensagens = corpo.mensagens.filter((x) => x !== m); desenharTudo(); mudou(); }, 'perigo')));
    }
    const alvos = [...corpo.vistas.map((v) => ({ id: v.id, rotulo: `vista ${v.nome || v.id}` })),
      ...(corpo.nos || []).map((n) => ({ id: n.id, rotulo: `widget ${n.tipo} ${n.id.slice(-4)}` }))];
    const form = h('form', { class: 'form linha', id: 'form-mensagem', novalidate: true });
    const origem = h('select', { name: 'origem' }, ...alvos.map((x) => h('option', { value: x.id }, x.rotulo)));
    const evento = h('select', { name: 'evento' }, ...modelo.EVENTOS.map((ev) => h('option', { value: ev }, ev)));
    const alvo = h('select', { name: 'alvo' }, ...alvos.map((x) => h('option', { value: x.id }, x.rotulo)));
    const acao = h('select', { name: 'acao' }, ...modelo.ACOES.map((ac) => h('option', { value: ac }, ac)));
    const relacao = h('select', { name: 'relacao' }, h('option', { value: '' }, '(sem relação / mesma fonte)'), h('option', { value: 'atributo' }, 'por atributo'), h('option', { value: 'espacial' }, 'espacial'));
    const campoOrigem = h('input', { type: 'text', name: 'campo_origem', maxlength: 120, spellcheck: 'false' });
    const campoAlvo = h('input', { type: 'text', name: 'campo_alvo', maxlength: 120, spellcheck: 'false' });
    const bt = h('button', { type: 'submit', class: 'pequeno', id: 'mensagem-adicionar', disabled: !alvos.length }, 'Adicionar mensagem');
    const erroForm = h('p', { class: 'erro-form', id: 'mensagem-erro', role: 'alert', hidden: true });
    form.append(campo('origem', origem), campo('evento', evento), campo('alvo', alvo), campo('ação', acao), campo('relação', relacao), campo('campo de origem', campoOrigem), campo('campo do alvo', campoAlvo), bt, erroForm);
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const rel = relacao.value ? { tipo: relacao.value, ...(relacao.value === 'atributo' ? { campo_origem: campoOrigem.value.trim(), campo_alvo: campoAlvo.value.trim(), operador: 'in' } : {}) } : null;
      const m = { id: modelo.gerarUlid(), gatilho: { origem: origem.value, evento: evento.value }, acoes: [{ alvo: alvo.value, acao: acao.value, parametros: {}, relacao: rel }] };
      // recusa ANTES de entrar no documento: a mensagem fica no formulário, nomeando a regra
      const prova = modelo.validarModelo({ nos: nosAtuais(), fontes: corpo.fontes, vistas: corpo.vistas, mensagens: [...corpo.mensagens, m] });
      const proprios = prova.erros.filter((x) => x.campo.startsWith(`corpo.mensagens.${corpo.mensagens.length}`));
      if (proprios.length) { erroForm.hidden = false; erroForm.textContent = proprios.map((x) => x.erro).join('; '); erroForm.dataset.regra = proprios[0].regra; return; }
      erroForm.hidden = true;
      corpo.mensagens.push(m);
      desenharTudo(); mudou();
    });
    secMsgs.append(ul, form);
  }

  function desenharTudo() { desenharFontes(); desenharVistas(); desenharMensagens(); validar(); }
  desenharTudo();
  return { validar, colecoes: () => colecoes, redesenhar: desenharTudo, erros: () => estado.erros };
}

function campo(rotulo, input) { return h('label', { class: 'campo' }, h('span', {}, rotulo), input); }
function botao(rotulo, aoClicar, classe = '') {
  const b = h('button', { type: 'button', class: `pequeno ${classe}`.trim() }, rotulo);
  b.addEventListener('click', aoClicar);
  return b;
}
