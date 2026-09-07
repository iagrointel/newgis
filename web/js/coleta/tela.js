// Tela do formulário de coleta (item L2-07-b): /coleta?formulario=<id>. Desenha os controles a partir do
// documento (texto, inteiro, decimal, data, hora, data-hora, select_one com busca, select_multiple em caixas,
// grupos recolhíveis, repetições), reage à relevância/cascata/cálculo pelo Motor, guarda rascunho a cada
// mudança (localStorage, por formulário) e envia para /api/formularios/{id}/respostas.
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { Motor, folhas } from './motor.js';

const CHAVE_RASCUNHO = (id) => `plat_coleta_rascunho_${id}`;
const TIPO_INPUT = { texto: 'text', inteiro: 'number', decimal: 'number', data: 'date', hora: 'time', data_hora: 'datetime-local', oculto: 'hidden', fora: 'text' };

function guardarRascunho(id, motor) {
  try { localStorage.setItem(CHAVE_RASCUNHO(id), motor.serializar()); } catch { /* sem armazenamento: segue sem rascunho */ }
}
function lerRascunho(id) {
  try { return localStorage.getItem(CHAVE_RASCUNHO(id)); } catch { return null; }
}
function apagarRascunho(id) {
  try { localStorage.removeItem(CHAVE_RASCUNHO(id)); } catch { /* idem */ }
}

class Tela {
  constructor(id, doc, form, aviso) {
    this.id = id;
    this.doc = doc;
    this.form = form;
    this.aviso = aviso;
    this.motor = new Motor(doc);
    this.inicio = new Date().toISOString();
    this.erros = [];
  }

  montar() {
    limpar(this.form);
    if ((this.doc.idiomas || []).length > 1) this.form.append(this._idiomas());
    for (const no of this.doc.campos) this.form.append(this._no(no, [], null, null, null));
    const botao = h('button', { type: 'submit', class: 'botao primario', id: 'enviar' }, 'Enviar');
    const estado = h('span', { id: 'estado-rascunho', class: 'saida', 'aria-live': 'polite' }, '');
    this.form.append(h('div', { class: 'coleta-rodape' }, botao, estado));
    this.atualizar();
  }

  _idiomas() {
    const sel = h('select', { id: 'idioma', 'aria-label': 'idioma' }, ...this.doc.idiomas.map((i) => h('option', { value: i, selected: i === this.motor.idioma ? '' : null }, i)));
    sel.addEventListener('change', () => { this.motor.idioma = sel.value; this.montar(); });
    return h('div', { class: 'coleta-idiomas' }, h('label', { for: 'idioma' }, 'Idioma'), sel);
  }

  _no(no, pais, linha, repeticao, indice) {
    if (no.tipo === 'grupo') {
      const det = h('details', { class: 'coleta-grupo', open: '', 'data-campo': no.nome }, h('summary', {}, this.motor.rotulo(no)));
      const filhos = h('div', { class: 'coleta-filhos' });
      for (const f of no.filhos || []) filhos.append(this._no(f, [...pais, no], linha, repeticao, indice));
      det.append(filhos);
      det.dataset.pais = JSON.stringify(pais.map((p) => p.nome));
      return det;
    }
    if (no.tipo === 'repeticao') return this._repeticao(no, pais);
    return this._campo(no, pais, linha, repeticao, indice);
  }

  _repeticao(no, pais) {
    const caixa = h('section', { class: 'coleta-repeticao', 'data-campo': no.nome, 'aria-label': this.motor.rotulo(no) }, h('h2', {}, this.motor.rotulo(no)));
    const linhas = h('div', { class: 'coleta-linhas' });
    const desenharLinhas = () => {
      limpar(linhas);
      (this.motor.repeticoes[no.nome] || []).forEach((l, i) => {
        const bloco = h('div', { class: 'coleta-linha', 'data-indice': String(i) });
        const remover = h('button', { type: 'button', class: 'botao', 'data-remover': String(i) }, 'Remover');
        remover.addEventListener('click', () => { this.motor.removerLinha(no.nome, i); this.montar(); this._guardar(); });
        bloco.append(h('div', { class: 'coleta-linha-cabecalho' }, h('strong', {}, `${this.motor.rotulo(no)} ${i + 1}`), remover));
        for (const f of no.filhos || []) bloco.append(this._no(f, [], l, no.nome, i));
        linhas.append(bloco);
      });
    };
    desenharLinhas();
    const adicionar = h('button', { type: 'button', class: 'botao', 'data-adicionar': no.nome }, `Adicionar ${this.motor.rotulo(no).toLowerCase()}`);
    adicionar.addEventListener('click', () => { this.motor.adicionarLinha(no.nome); this.montar(); this._guardar(); });
    caixa.append(linhas, adicionar);
    return caixa;
  }

  _valorAtual(no, linha) { return linha ? linha[no.nome] : this.motor.valores[no.nome]; }

  _campo(no, pais, linha, repeticao, indice) {
    const idc = repeticao ? `c-${repeticao}-${indice}-${no.nome}` : `c-${no.nome}`;
    const caixa = h('div', { class: 'coleta-campo', 'data-campo': no.nome, 'data-tipo': no.tipo });
    if (repeticao) { caixa.dataset.repeticao = repeticao; caixa.dataset.indice = String(indice); }
    caixa._no = no; caixa._pais = pais; caixa._linha = linha;
    if (no.tipo === 'nota') {
      caixa.classList.add('coleta-nota');
      caixa.append(h('p', { id: idc }, ''));
      return caixa;
    }
    if (no.tipo === 'calculo' || no.tipo === 'meta') { caixa.hidden = true; return caixa; }
    const rotulo = h('label', { for: idc }, this.motor.rotulo(no) + (no.obrigatorio ? ' *' : ''));
    caixa.append(rotulo);
    const dica = (no.dica || {})[this.motor.idioma] ?? Object.values(no.dica || {})[0];
    if (dica) caixa.append(h('div', { class: 'dica' }, dica));
    const valor = this._valorAtual(no, linha);
    const mudou = (v) => { this.motor.definir(no.nome, v, { repeticao, indice }); this.atualizar(); this._guardar(); };
    if (no.tipo === 'select_one') {
      const busca = h('input', { type: 'search', class: 'coleta-busca', placeholder: 'buscar…', 'aria-label': `buscar ${this.motor.rotulo(no)}`, id: `${idc}-busca` });
      const sel = h('select', { id: idc, name: no.nome });
      caixa._select = sel; caixa._busca = busca;
      sel.addEventListener('change', () => mudou(sel.value || null));
      busca.addEventListener('input', () => this._opcoes(caixa));
      caixa.append(busca, sel);
    } else if (no.tipo === 'select_multiple') {
      const caixas = h('div', { class: 'coleta-caixas', id: idc, role: 'group' });
      caixa._caixas = caixas;
      caixa.append(caixas);
    } else {
      const input = h('input', { type: TIPO_INPUT[no.tipo] || 'text', id: idc, name: no.nome, value: valor ?? '' });
      if (no.tipo === 'decimal') input.step = 'any';
      if (no.tipo === 'inteiro') input.step = '1';
      if (no.somente_leitura) input.readOnly = true;
      input.addEventListener('change', () => mudou(input.value === '' ? null : (no.tipo === 'inteiro' || no.tipo === 'decimal' ? Number(input.value) : input.value)));
      input.addEventListener('input', () => { if (no.tipo === 'texto') mudou(input.value || null); });
      caixa.append(input);
    }
    caixa.append(h('div', { class: 'erro', id: `${idc}-erro`, 'aria-live': 'polite' }, ''));
    return caixa;
  }

  _opcoes(caixa) {
    const no = caixa._no;
    const linha = caixa._linha;
    const atual = this._valorAtual(no, linha);
    const opcoes = this.motor.opcoes(no, { linha });
    if (caixa._select) {
      const filtro = (caixa._busca.value || '').toLowerCase();
      const sel = caixa._select;
      limpar(sel);
      sel.append(h('option', { value: '' }, '—'));
      for (const o of opcoes) {
        const rot = this.motor.rotuloOpcao(o);
        if (filtro && !rot.toLowerCase().includes(filtro) && String(o.nome) !== atual) continue;
        sel.append(h('option', { value: String(o.nome), selected: String(o.nome) === String(atual ?? '') ? '' : null }, rot));
      }
      if (atual && !opcoes.some((o) => String(o.nome) === String(atual))) {
        // a cascata mudou acima: a escolha antiga deixou de existir e some do estado também
        this.motor.definir(no.nome, null, { repeticao: caixa.dataset.repeticao || null, indice: Number(caixa.dataset.indice || 0) });
        sel.value = '';
      }
    } else if (caixa._caixas) {
      const escolhidos = new Set(String(atual || '').split(' ').filter(Boolean));
      limpar(caixa._caixas);
      for (const o of opcoes) {
        const cb = h('input', { type: 'checkbox', value: String(o.nome), checked: escolhidos.has(String(o.nome)) ? '' : null });
        cb.addEventListener('change', () => {
          const marcados = [...caixa._caixas.querySelectorAll('input:checked')].map((x) => x.value);
          this.motor.definir(no.nome, marcados.length ? marcados.join(' ') : null, { repeticao: caixa.dataset.repeticao || null, indice: Number(caixa.dataset.indice || 0) });
          this.atualizar(); this._guardar();
        });
        caixa._caixas.append(h('label', {}, cb, this.motor.rotuloOpcao(o)));
      }
    }
  }

  // relevância, cascata, cálculos exibidos em notas e erros já mostrados
  atualizar() {
    for (const caixa of this.form.querySelectorAll('.coleta-campo')) {
      const no = caixa._no;
      const rel = this.motor.relevante(no, { linha: caixa._linha, pais: caixa._pais });
      caixa.hidden = !rel || no.tipo === 'calculo' || no.tipo === 'meta';
      if (!rel) continue;
      if (no.tipo === 'nota') {
        const texto = this.motor.rotulo(no).replace(/\$\{([\w-]+)\}/g, (_m, n) => {
          const v = caixa._linha && n in caixa._linha ? caixa._linha[n] : this.motor.valores[n];
          return v === null || v === undefined ? '' : String(v);
        });
        caixa.querySelector('p').textContent = texto;
      } else if (no.tipo === 'select_one' || no.tipo === 'select_multiple') this._opcoes(caixa);
    }
    for (const det of this.form.querySelectorAll('.coleta-grupo')) {
      const nome = det.dataset.campo;
      const no = [...this.form.querySelectorAll('.coleta-grupo')].length ? this._noPorNome(nome) : null;
      if (no) det.hidden = !this.motor.relevante(no, { pais: [] });
    }
  }

  _noPorNome(nome) {
    const busca = (lista) => { for (const c of lista) { if (c.nome === nome) return c; if (c.filhos) { const f = busca(c.filhos); if (f) return f; } } return null; };
    return busca(this.doc.campos);
  }

  _guardar() { guardarRascunho(this.id, this.motor); const e = this.form.querySelector('#estado-rascunho'); if (e) e.textContent = 'rascunho guardado'; }

  mostrarErros(erros) {
    for (const el of this.form.querySelectorAll('.coleta-campo.com-erro')) { el.classList.remove('com-erro'); const e = el.querySelector('.erro'); if (e) e.textContent = ''; }
    for (const erro of erros) {
      const seletor = erro.repeticao ? `.coleta-campo[data-campo="${erro.campo}"][data-repeticao="${erro.repeticao}"][data-indice="${erro.indice}"]` : `.coleta-campo[data-campo="${erro.campo}"]:not([data-repeticao])`;
      const caixa = this.form.querySelector(seletor);
      if (!caixa) continue;
      caixa.classList.add('com-erro');
      const e = caixa.querySelector('.erro');
      if (e) e.textContent = erro.mensagem || erro.erro;
    }
    if (erros.length) { this.aviso.mostrar?.(`${erros.length} campo(s) com erro`, 'erro'); const primeiro = this.form.querySelector('.coleta-campo.com-erro input, .coleta-campo.com-erro select'); primeiro?.focus(); }
  }

  async enviar() {
    const erros = this.motor.validar();
    this.mostrarErros(erros);
    if (erros.length) return false;
    const corpo = this.motor.resposta({ inicio: this.inicio, dispositivo: navigator.userAgent.slice(0, 200) });
    const r = await enviar(`/api/formularios/${this.id}/respostas`, corpo);
    if (r.status === 201) {
      apagarRascunho(this.id);
      this.aviso.mostrar?.(`Resposta gravada (feição ${r.json.feicao.id.slice(0, 8)})`, 'ok');
      this.form.dataset.enviado = r.json.feicao.id;
      return true;
    }
    if (r.status === 422 && Array.isArray(r.json.detalhe)) this.mostrarErros(r.json.detalhe);
    else this.aviso.mostrar?.(mensagemDe(r), 'erro');
    return false;
  }
}

async function iniciar() {
  await carregar();
  const usuario = await exigirSessao();
  if (!usuario) return;
  montarLayout({ usuario });
  const aviso = document.getElementById('aviso');
  const form = document.getElementById('formulario');
  const id = new URLSearchParams(location.search).get('formulario');
  if (!id) { cabecalho('Coleta'); aviso.mostrar?.('informe ?formulario=<id>', 'erro'); pronto(); return; }
  const r = await obter(`/api/formularios/${id}`);
  if (r.status !== 200) { cabecalho('Coleta'); aviso.mostrar?.(mensagemDe(r), 'erro'); pronto(); return; }
  const doc = r.json.documento;
  cabecalho(r.json.titulo);
  const tela = new Tela(id, doc, form, aviso);
  const rascunho = lerRascunho(id);
  if (rascunho && tela.motor.restaurar(rascunho)) { form.dataset.rascunho = '1'; }
  tela.montar();
  form.addEventListener('submit', async (ev) => { ev.preventDefault(); const botao = form.querySelector('#enviar'); botao.disabled = true; try { await tela.enviar(); } finally { botao.disabled = false; } });
  window.plat_coleta = tela;
  pronto();
  void t;
}

iniciar();
