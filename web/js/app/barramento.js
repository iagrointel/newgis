/* plat — barramento de mensagens do app (item L5-07; L5_CONCEITO D5): gatilho {origem, evento} -> ações
   [{alvo, acao, parametros, relacao}]. EventTarget nativo, sem biblioteca. Uma "volta" é o processamento de um
   gatilho de fora (clique no mapa, filtro digitado): as ações que ela dispara podem gerar novos gatilhos, mas
   cada mensagem roda NO MÁXIMO uma vez por volta — A filtra B e B filtra A não recursa: a segunda passagem por
   A é cortada e o barramento emite `aviso` {tipo: 'ciclo_cortado'} (refutação do item). Latência
   gatilho->ação é medida por gatilho (performance.now) e fica em `medidas` para o teste ler o p95.

   Relação entre fontes (regra dos Dashboards): mesma_fonte = os ids/filtro passam direto; atributo = os valores
   do campo_origem dos registros de origem (selecionados quando o gatilho é seleção, filtrados quando é filtro)
   viram `in` no campo_alvo; espacial = envelope dos registros de origem vira `s_intersects` no alvo. */
import * as modelo from './modelo.js';
import { envelope, predicado } from './cql2.js';

const relogio = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

export class Barramento extends EventTarget {
  constructor(corpo, { vistas, widgets = new Map() }) {
    super();
    this.corpo = corpo;
    this.vistas = vistas;
    this.widgets = widgets;
    this.mensagens = (corpo.mensagens || []).map((m) => ({ ...m }));
    this.medidas = [];
    this.avisos = [];
    this.#volta = null;
    for (const v of vistas.values()) {
      for (const ev of ['filtro_mudou', 'selecao_mudou', 'vista_mudou', 'dado_adicionado', 'registros_carregados']) {
        v.addEventListener(ev, (e) => {
          this.disparar(v.id, ev, e.detail);
          // o mesmo evento vale para o WIDGET que causou a mudança (gatilho "seleção mudou" no mapa, como no
          // Experience Builder): `detail.origem` é o noId que chamou definirSelecao/definirFiltro
          const causador = e.detail?.origem;
          if (causador && causador !== v.id && this.widgets.has(causador)) this.disparar(causador, ev, e.detail);
        });
      }
    }
  }

  #volta;

  registrarWidget(id, widget) { this.widgets.set(id, widget); }

  /* ponto de entrada de todo gatilho (widget ou vista) */
  disparar(origem, evento, detalhe = {}) {
    const raiz = this.#volta === null;
    if (raiz) this.#volta = { mensagens: new Set(), inicio: relogio(), origem, evento };
    const t0 = relogio();
    let disparadas = 0;
    try {
      for (const m of this.mensagens) {
        if (m.gatilho?.origem !== origem || m.gatilho?.evento !== evento) continue;
        if (this.#volta.mensagens.has(m.id)) {
          this.#aviso('ciclo_cortado', `mensagem ${m.id} (${origem}/${evento}) já rodou nesta volta; recursão cortada`, { mensagem: m.id, origem, evento });
          continue;
        }
        this.#volta.mensagens.add(m.id);
        for (const a of m.acoes || []) this.#executar(m, a, origem, detalhe);
        disparadas += 1;
      }
    } finally {
      const ms = relogio() - t0;
      if (disparadas) this.medidas.push({ origem, evento, mensagens: disparadas, ms });
      if (raiz) this.#volta = null;
    }
    return disparadas;
  }

  #aviso(tipo, mensagem, detalhe) {
    const aviso = { tipo, mensagem, ...detalhe };
    this.avisos.push(aviso);
    this.dispatchEvent(new CustomEvent('aviso', { detail: aviso }));
  }

  #vistaDe(id) {
    if (this.vistas.has(id)) return this.vistas.get(id);
    const w = this.widgets.get(id);
    const vid = w?.configuracao?.vista;
    return vid ? this.vistas.get(vid) || null : null;
  }

  #registrosDeOrigem(origem, evento, detalhe, acao = null) {
    const v = this.#vistaDe(origem);
    if (!v) return [];
    let regs;
    if (evento === 'selecao_mudou' || evento === 'clique') {
      const ids = detalhe?.ids || (detalhe?.id !== undefined ? [detalhe.id] : null);
      if (ids) { const s = new Set(ids); regs = v.registros().filter((f) => s.has(f.id)); } else regs = v.selecionados();
    } else regs = v.registros();
    // item L5-01-e: `parametros.condicao` (CQL2) restringe os registros de origem que a ação leva em conta
    const cond = acao?.parametros?.condicao;
    if (cond !== undefined && cond !== null) regs = regs.filter((f) => avaliarSeguro(cond, f));
    return regs;
  }

  /* traduz a relação para o alvo: devolve {ids} (mesma fonte) ou {filtro} (atributo/espacial) */
  #traduzir(acao, origem, evento, detalhe) {
    const rel = acao.relacao || { tipo: 'mesma_fonte' };
    const vo = this.#vistaDe(origem); const va = this.#vistaDe(acao.alvo);
    const mesma = vo && va && vo.fonte.id === va.fonte.id;
    if (rel.tipo === 'mesma_fonte' || (!rel.tipo && mesma)) {
      if (!mesma) { this.#aviso('relacao_invalida', 'ação de dado entre fontes diferentes sem relação declarada; ignorada', { origem, alvo: acao.alvo }); return null; }
      if (evento === 'selecao_mudou' || evento === 'clique') return { ids: this.#registrosDeOrigem(origem, evento, detalhe, acao).map((f) => f.id) };
      // filtro vindo de um widget (caixa de filtro, gráfico) chega em detalhe.filtro; de uma vista, é o filtro dela
      const cond = acao.parametros?.condicao;
      const comCondicao = (f) => (cond ? (f ? { op: 'and', args: [f, cond] } : cond) : f);
      if (detalhe && detalhe.filtro !== undefined && !this.vistas.has(origem)) return { filtro: comCondicao(detalhe.filtro), ids: null };
      return { filtro: comCondicao(vo.filtro), ids: null };
    }
    let regs = this.#registrosDeOrigem(origem, evento, detalhe, acao);
    if (detalhe && detalhe.filtro !== undefined && !this.vistas.has(origem) && vo) {
      // filtro digitado num widget de outra fonte: aplica na origem em memória e leva os valores casados
      regs = vo.fonte.feicoes.filter((f) => avaliarSeguro(detalhe.filtro, f));
    }
    if (rel.tipo === 'atributo') {
      const valores = [...new Set(regs.map((f) => f.propriedades?.[rel.campo_origem]).filter((x) => x !== null && x !== undefined))];
      if (!valores.length) return { filtro: { op: 'in', args: [{ property: rel.campo_alvo }, []] } };
      return { filtro: { op: 'in', args: [{ property: rel.campo_alvo }, valores.slice(0, 10000)] } };
    }
    if (rel.tipo === 'espacial') {
      let env = null;
      for (const f of regs) { const e = envelope(f.geometria); if (!e) continue; env = env ? [Math.min(env[0], e[0]), Math.min(env[1], e[1]), Math.max(env[2], e[2]), Math.max(env[3], e[3])] : e; }
      if (!env) return { filtro: { op: 'in', args: [{ property: '__id' }, []] } };
      const caixa = { type: 'Polygon', coordinates: [[[env[0], env[1]], [env[2], env[1]], [env[2], env[3]], [env[0], env[3]], [env[0], env[1]]]] };
      return { filtro: { op: 's_intersects', args: [{ property: 'geometria' }, caixa] } };
    }
    return null;
  }

  #executar(m, acao, origem, detalhe) {
    const alvoVista = this.#vistaDe(acao.alvo);
    const alvoWidget = this.widgets.get(acao.alvo);
    if (modelo.ACOES_DADO.includes(acao.acao)) {
      if (!alvoVista) { this.#aviso('alvo_sem_vista', `ação ${acao.acao} em alvo sem vista: ${acao.alvo}`, { alvo: acao.alvo }); return; }
      if (acao.acao === 'limpar_filtro') { alvoVista.limparFiltro(origem); return; }
      if (acao.acao === 'limpar_selecao') { alvoVista.limparSelecao(origem); return; }
      const t = this.#traduzir(acao, origem, m.gatilho.evento, detalhe);
      if (!t) return;
      if (acao.acao === 'filtrar') {
        if (t.filtro !== undefined && t.ids === undefined) alvoVista.definirFiltro(t.filtro, origem);
        else if (t.ids) alvoVista.definirFiltro(t.ids.length ? { op: 'in', args: [{ property: '__id' }, t.ids] } : { op: 'in', args: [{ property: '__id' }, []] }, origem);
        else alvoVista.definirFiltro(t.filtro, origem);
      } else if (acao.acao === 'selecionar') {
        if (t.ids) alvoVista.definirSelecao(t.ids, origem);
        else if (t.filtro) {
          const ids = alvoVista.fonte.feicoes.filter((f) => avaliarSeguro(t.filtro, f)).map((f) => f.id);
          alvoVista.definirSelecao(ids, origem);
        }
      }
      return;
    }
    if (!alvoWidget || typeof alvoWidget.executar !== 'function') { this.#aviso('alvo_sem_widget', `ação ${acao.acao} em alvo que não é widget: ${acao.alvo}`, { alvo: acao.alvo }); return; }
    const vistaOrigem = this.#vistaDe(origem);
    const regs = vistaOrigem ? this.#registrosDeOrigem(origem, m.gatilho.evento, detalhe, acao) : [];
    // ação de widget com condição: só dispara se algum registro de origem a satisfaz (item L5-01-e)
    const cond = acao.parametros?.condicao;
    if (vistaOrigem && cond !== undefined && cond !== null && !regs.length) return;
    try { alvoWidget.executar(acao.acao, { ...(acao.parametros || {}), origem, registros: regs, detalhe }); }
    catch (e) { this.#aviso('acao_falhou', `${acao.acao} em ${acao.alvo}: ${e.message}`, { alvo: acao.alvo }); }
  }

  p95() {
    const xs = this.medidas.map((m) => m.ms).sort((a, b) => a - b);
    if (!xs.length) return null;
    return xs[Math.min(xs.length - 1, Math.ceil(xs.length * 0.95) - 1)];
  }
}

function avaliarSeguro(filtro, feicao) { try { return predicado(filtro)(feicao); } catch { return false; } }
