/* plat · painel — INTERAÇÃO do painel (item L2-06-c): a ponte entre os ELEMENTOS do painel
 * (`web/js/paineis/elementos.js`) e o BARRAMENTO de mensagens do L5-07 (`web/js/app/barramento.js`) —
 * um só barramento, não dois. Nada aqui traduz mensagem: quem traduz gatilho→ação, com corte de ciclo
 * em uma volta e medida de latência, é o barramento do L5-07 inteiro. Este módulo só adapta os dois
 * lados:
 *
 *  - VistaElemento (sem DOM, testável em node): cada elemento COM fonte do painel vira uma "vista" na
 *    interface que o barramento espera — `fonte.id`, `registros()`, `selecionados()`, `filtro`,
 *    `definirFiltro/limparFiltro/definirSelecao/limparSelecao` — e embala as linhas que o servidor
 *    devolveu na forma {id, propriedades, geometria} das feições do L5-07. O filtro que o barramento
 *    entrega (CQL2-JSON) é o MESMO que vai por pedido ao servidor (`app/paineis/dados.py`), que o
 *    executa em SQL — filtrar é sempre do lado do dado, nunca em cópia no navegador.
 *  - widgetDoElemento / ligarInteracoes (com DOM): cada elemento vira também um "widget" do barramento
 *    (as ações de widget do L5-07: zoom, pan, piscar, popup, seguir, abrir, fechar, definir_parametro)
 *    e liga os cliques que viram GATILHO: mudança de seletor → filtro_mudou, clique em barra do
 *    gráfico / linha de lista / ponto do mapa → selecao_mudou, botão de extensão → extensao_mudou.
 *
 * Os ids de gatilho/ação nas mensagens do corpo são ids de ELEMENTO do painel; as vistas ficam sob
 * `v:<id do elemento>` e o barramento resolve widget → vista por `configuracao.vista`. */
import { validar as validarCql2 } from '../app/cql2.js';
import { TIPOS_COM_FONTE } from './elementos.js';

/** Linhas de um resultado do servidor (`app/paineis/dados.py`) na forma de feição do L5-07. O id é
 * a POSIÇÃO na resposta (linha de painel não tem chave estável — o que atravessa recarga é o FILTRO,
 * que é CQL2 e vai na URL), e a geometria vem das colunas __lon/__lat do pedido de mapa. */
export function embrulharResultado(resultado) {
  if (!resultado || typeof resultado !== 'object') return [];
  if (resultado.tipo === 'linhas') {
    return (resultado.linhas || []).map((linha, i) => ({
      id: String(i), propriedades: linha, geometria: pontoDe(linha),
    }));
  }
  if (resultado.tipo === 'serie') {
    const campo = resultado.chave || 'categoria';
    return (resultado.chaves || []).map((chave, i) => ({ id: String(chave), propriedades: { [campo]: chave } }));
  }
  if (resultado.tipo === 'categorias') {
    return (resultado.linhas || []).map((linha, i) => ({
      id: String(linha.categoria ?? i), propriedades: linha,
    }));
  }
  if (resultado.tipo === 'feicao') {
    return resultado.valores ? [{ id: '0', propriedades: resultado.valores, geometria: pontoDe(resultado.valores) }] : [];
  }
  return [];  // numero e demais: não carrega feição
}

function pontoDe(linha) {
  const lon = Number(linha && linha.__lon); const lat = Number(linha && linha.__lat);
  return Number.isFinite(lon) && Number.isFinite(lat)
    ? { type: 'Point', coordinates: [lon, lat] } : undefined;
}

/* ---------------------------------------------------------------- vista (sem DOM) */
export class VistaElemento extends EventTarget {
  constructor(elemento, fonte) {
    super();
    this.id = `v:${elemento.id}`;
    this.elementoId = elemento.id;
    this.fonte = { id: fonte ? fonte.id : null, campos: fonte ? fonte.campos : [], feicoes: [] };
    this.filtroDinamico = null;
    this.selecao = new Set();
  }

  get filtro() { return this.filtroDinamico; }

  registros() { return this.fonte.feicoes; }

  selecionados() { return this.fonte.feicoes.filter((f) => this.selecao.has(f.id)); }

  /* o barramento chama com o CQL2 traduzido da relação; filtro inválido NÃO substitui o anterior
   * (aviso no próprio objeto, nunca exceção dentro de uma ação do barramento) */
  definirFiltro(filtro, origem) {
    if (filtro) {
      try { validarCql2(filtro); } catch (e) {
        this.dispatchEvent(new CustomEvent('aviso', { detail: { tipo: 'filtro_invalido', erro: e.message, origem } }));
        return;
      }
    }
    this.filtroDinamico = filtro && Object.keys(filtro).length ? filtro : null;
    this.dispatchEvent(new CustomEvent('filtro_mudou', { detail: { filtro: this.filtroDinamico, origem } }));
    this.dispatchEvent(new CustomEvent('vista_mudou', { detail: { origem } }));
  }

  limparFiltro(origem) { this.definirFiltro(null, origem); }

  definirSelecao(ids, origem) {
    this.selecao = new Set((Array.isArray(ids) ? ids : []).slice(0, 10000));
    this.dispatchEvent(new CustomEvent('selecao_mudou', { detail: { ids: [...this.selecao], origem } }));
    this.dispatchEvent(new CustomEvent('vista_mudou', { detail: { origem } }));
  }

  limparSelecao(origem) { this.definirSelecao([], origem); }

  /* render.js chama a cada resposta do servidor: as feições da última carga são o que as relações
   * leem (valores de campo para `atributo`, envelope para `espacial`) */
  carregar(resultado) { this.fonte.feicoes = embrulharResultado(resultado); }
}

/* ---------------------------------------------------------------- widget (com DOM) */
function envelopeDeFeicoes(feicoes) {
  let caixa = null;
  for (const f of feicoes || []) {
    const g = f && f.geometria;
    const lon = g && g.type === 'Point' ? g.coordinates[0] : NaN;
    const lat = g && g.type === 'Point' ? g.coordinates[1] : NaN;
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    caixa = caixa
      ? [Math.min(caixa[0], lon), Math.min(caixa[1], lat), Math.max(caixa[2], lon), Math.max(caixa[3], lat)]
      : [lon, lat, lon, lat];
  }
  return caixa;
}

/** As ações de widget do L5-07 sobre um elemento do painel. O estado que elas mudam vive em
 * `ctx.estado(el.id)` (o mesmo estado de execução de ordenação/paginação), e o efeito aparece no
 * repintar — `ctx.repintar(el.id)` — não em mutação direta do DOM, que a próxima carga desfaria. */
export function executarAcaoWidget(el, estado, acao, p = {}) {
  const registros = Array.isArray(p.registros) ? p.registros : [];
  if (acao === 'zoom' || acao === 'seguir') {
    const caixa = envelopeDeFeicoes(registros);
    if (caixa) {
      const dx = (caixa[2] - caixa[0]) * 0.06 || 0.01; const dy = (caixa[3] - caixa[1]) * 0.06 || 0.01;
      estado.caixa = [caixa[0] - dx, caixa[1] - dy, caixa[2] + dx, caixa[3] + dy];
    }
    estado.piscar = acao === 'seguir' ? registros : estado.piscar;
    if (acao === 'seguir' && registros.length) estado.popup = registros[0];
    return true;
  }
  if (acao === 'pan') {
    if (!estado.caixa) return false;
    const dx = Number(p.dx) || 0; const dy = Number(p.dy) || 0;
    if (p.lon !== undefined && p.lat !== undefined) {
      const largura = (estado.caixa[2] - estado.caixa[0]) / 2;
      const altura = (estado.caixa[3] - estado.caixa[1]) / 2;
      const lon = Number(p.lon); const lat = Number(p.lat);
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        estado.caixa = [lon - largura, lat - altura, lon + largura, lat + altura];
        return true;
      }
    }
    estado.caixa = [estado.caixa[0] + dx, estado.caixa[1] + dy, estado.caixa[2] + dx, estado.caixa[3] + dy];
    return true;
  }
  if (acao === 'piscar') { estado.piscar = registros; return true; }
  if (acao === 'popup') { estado.popup = registros[0] || null; return true; }
  if (acao === 'abrir' || acao === 'fechar') return false;  // painel não tem caixa dobrável ainda
  if (acao === 'definir_parametro') {
    estado.parametros = { ...(estado.parametros || {}), [p.nome]: p.valor };
    return true;
  }
  return false;
}

/* ---------------------------------------------------------------- ligação do painel */
/** Registra cada elemento COM fonte como widget do barramento (as ações de widget do L5-07 chegam aqui e
 * mudam o `ctx.estado(el.id)` — zoom/pan/piscar/popup aparecem no repintar do mapa, ver `elementos.js`).
 * A configuração `{vista: 'v:'+id}` é o que faz o barramento resolver o widget na vista certa quando o
 * alvo da ação é um elemento do painel. Os GATILHOS não passam por aqui: cliques de barra/linha/ponto e a
 * mudança de seletor chamam `ctx.definirSelecaoElemento`/`ctx.definirFiltroElemento` (render.js), que
 * mudam a vista — o barramento intercepta o evento da vista e o re-dispara como gatilho do widget
 * causador (linhas do construtor do Barramento). */
export function ligarInteracoes(container, { elementos, ctx, barramento }) {
  void container;  // a ligação é no barramento; o container só documenta o escopo do painel
  for (const el of elementos) {
    if (!TIPOS_COM_FONTE.has(el.tipo)) continue;
    barramento.registrarWidget(el.id, {
      configuracao: { vista: `v:${el.id}` },
      executar(acao, parametros) {
        const ok = executarAcaoWidget(el, ctx.estado(el.id, {}), acao, parametros || {});
        ctx.repintar(el.id);
        return ok;
      },
    });
  }
}
