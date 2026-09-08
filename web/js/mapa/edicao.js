/* plat · mapa — edição de feições (item L2-03-edicao), sobre o visualizador do L2-01-mapa-web e a API
   transacional do L2-03-a (`POST /api/camadas/{id}/edicoes`, única porta de escrita).

   O que este módulo cobre: criar (ponto/linha/polígono), mover e editar vértice (arrastar), apagar,
   formulário de atributos com domínio/obrigatório (espelho no navegador do que o servidor já aplica —
   ver `app/edicao/servico.py::validar_atributos`), anexos, desfazer/refazer, aderência a vértice
   próximo, edição em lote (um atributo em N feições selecionadas) e histórico/restauração.

   Geometria de trabalho nunca vem do tile (MVT é recortado/generalizado por zoom — conceito C3): toda
   seleção busca a feição EXATA em `GET /api/camadas/{id}/feicoes/{globalid}` antes de desenhar vértice
   ou preencher o formulário. Depois de qualquer escrita bem-sucedida, a camada é religada
   (`catalogo.desligar`+`catalogo.ligar`) para que o TileJSON cunhe um token novo — é isso que evita o
   tile antigo em cache do navegador (o próprio Martin devolve `Cache-Control: private, max-age=60`).

   Achado da casa citado no brief: o tratador de mudança de uma aba de painel nunca deve disparar o
   redesenho INTEIRO por cima da própria mensagem de sucesso — por isso a mensagem de resultado vive na
   área de edição, nunca dentro do que `painel.desenhar()` já limpa/recria a cada `catalogo.aoMudar`. */
import { apagar as apagarHttp, enviar, obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

const FONTE_RASCUNHO = 'plat-edicao-rascunho';
const FONTE_VERTICES = 'plat-edicao-vertices';
const TOLERANCIA_ADERIR_PX = 12;

function vazio() { return { type: 'FeatureCollection', features: [] }; }

function coordenadasDe(geometria) {
  if (!geometria) return [];
  if (geometria.type === 'Point') return [geometria.coordinates];
  if (geometria.type === 'LineString') return geometria.coordinates;
  if (geometria.type === 'Polygon') return geometria.coordinates[0].slice(0, -1);
  return [];
}

function reconstruirGeometria(tipo, coords) {
  if (tipo === 'Point') return { type: 'Point', coordinates: coords[0] };
  if (tipo === 'LineString') return { type: 'LineString', coordinates: coords };
  if (tipo === 'Polygon') return { type: 'Polygon', coordinates: [[...coords, coords[0]]] };
  return null;
}

function familiaDeGeometria(tipo) {
  if (!tipo) return 'ponto';
  if (tipo.includes('Point')) return 'ponto';
  if (tipo.includes('LineString')) return 'linha';
  if (tipo.includes('Polygon')) return 'poligono';
  return 'ponto';
}

export class Edicao {
  constructor(map, maplibregl, catalogo, { raiz, aoErro }) {
    this.map = map;
    this.maplibregl = maplibregl;
    this.catalogo = catalogo;
    this.raiz = raiz;
    this.aoErro = aoErro || (() => {});
    this.camadaId = null;
    this.modo = 'nenhum'; // nenhum | selecionar | adicionar_ponto | adicionar_linha | adicionar_poligono | dividir
    this.aderir = true;
    this.rascunho = [];
    this.selecionadas = new Map(); // id -> {versao, atributos, geometria}
    this.arrastando = null;
    this.pilha = []; this.indicePilha = -1; // desfazer/refazer (adicionar/atualizar; ver README do item)
    // shift+arrastar é "caixa de zoom" por padrão no MapLibre — some com o shift+clique de seleção
    // múltipla desta tela (achado do e2e: com boxZoom ligado, o evento 'click' nunca dispara sob shift)
    map.boxZoom.disable();
    this._instalarFontesECamadas();
    this._instalarEventosDeDesenho();
    this._montarUI();
  }

  // ---------------------------------------------------------------- infraestrutura no mapa
  _instalarFontesECamadas() {
    const map = this.map;
    if (map.getSource(FONTE_RASCUNHO)) return; // idempotente: troca de mapa-base (setStyle) apaga tudo e
    // o mesmo botão que re-liga as camadas do catálogo também tem de re-chamar isto (ver mapa.js)
    map.addSource(FONTE_RASCUNHO, { type: 'geojson', data: vazio() });
    map.addLayer({ id: 'plat-edicao-rascunho-linha', type: 'line', source: FONTE_RASCUNHO,
      filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': '#2b7fd9', 'line-width': 2, 'line-dasharray': [2, 1] } });
    map.addLayer({ id: 'plat-edicao-rascunho-poligono', type: 'fill', source: FONTE_RASCUNHO,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#2b7fd9', 'fill-opacity': 0.15 } });
    map.addSource(FONTE_VERTICES, { type: 'geojson', data: vazio() });
    map.addLayer({ id: 'plat-edicao-vertices', type: 'circle', source: FONTE_VERTICES,
      paint: { 'circle-radius': 6, 'circle-color': '#d9822b', 'circle-stroke-color': '#fff',
        'circle-stroke-width': 2 } });
  }

  _rascunhoRedesenhar() {
    const feats = [];
    if (this.rascunho.length === 1) feats.push({ type: 'Feature', geometry: { type: 'Point', coordinates: this.rascunho[0] }, properties: {} });
    if (this.rascunho.length >= 2) {
      feats.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: this.rascunho }, properties: {} });
      if (this.modo === 'adicionar_poligono' && this.rascunho.length >= 3) {
        feats.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [[...this.rascunho, this.rascunho[0]]] }, properties: {} });
      }
    }
    this.map.getSource(FONTE_RASCUNHO).setData({ type: 'FeatureCollection', features: feats });
  }

  _verticesRedesenhar() {
    const feats = [];
    for (const [id, sel] of this.selecionadas) {
      const coords = coordenadasDe(sel.geometria);
      coords.forEach((c, i) => feats.push({ type: 'Feature', geometry: { type: 'Point', coordinates: c },
        properties: { id, indice: i } }));
    }
    this.map.getSource(FONTE_VERTICES).setData({ type: 'FeatureCollection', features: feats });
  }

  _aderirSe(lngLat, pixel) {
    if (!this.aderir) return lngLat;
    const camadas = this.catalogo.ativas.flatMap((id) => this.catalogo.idsDeEstilo(id)).filter((idc) => this.map.getLayer(idc));
    const janela = [[pixel.x - TOLERANCIA_ADERIR_PX, pixel.y - TOLERANCIA_ADERIR_PX],
      [pixel.x + TOLERANCIA_ADERIR_PX, pixel.y + TOLERANCIA_ADERIR_PX]];
    const proximos = this.map.queryRenderedFeatures(janela, { layers: [...camadas, 'plat-edicao-vertices'] });
    let melhor = null; let melhorDist = Infinity;
    for (const f of proximos) {
      for (const c of coordenadasDe(f.geometry)) {
        const p = this.map.project(c);
        const d = Math.hypot(p.x - pixel.x, p.y - pixel.y);
        if (d < melhorDist) { melhorDist = d; melhor = c; }
      }
    }
    return (melhor && melhorDist <= TOLERANCIA_ADERIR_PX) ? { lng: melhor[0], lat: melhor[1] } : lngLat;
  }

  // ---------------------------------------------------------------- clique/arraste no mapa
  _instalarEventosDeDesenho() {
    const map = this.map;
    map.on('click', (ev) => {
      if (this.modo === 'nenhum') return;
      const pt = this._aderirSe(ev.lngLat, ev.point);
      if (this.modo === 'adicionar_ponto') {
        this.rascunho = [[pt.lng, pt.lat]];
        this._rascunhoRedesenhar();
        this._abrirFormularioNovo();
        return;
      }
      if (this.modo === 'adicionar_linha' || this.modo === 'adicionar_poligono') {
        this.rascunho.push([pt.lng, pt.lat]);
        this._rascunhoRedesenhar();
        return;
      }
      if (this.modo === 'dividir') {
        this._dividirNoPonto([pt.lng, pt.lat]);
        return;
      }
      if (this.modo === 'selecionar') {
        ev.originalEvent.stopImmediatePropagation(); // não abre o popup de leitura por cima
        this._selecionarNoClique(ev);
      }
    });
    map.on('mousedown', 'plat-edicao-vertices', (ev) => {
      if (this.modo !== 'selecionar') return;
      ev.preventDefault();
      const f = ev.features[0];
      this.arrastando = { id: f.properties.id, indice: f.properties.indice };
      map.dragPan.disable();
      map.getCanvas().style.cursor = 'grabbing';
    });
    map.on('mousemove', (ev) => {
      if (!this.arrastando) return;
      const pt = this._aderirSe(ev.lngLat, ev.point);
      const sel = this.selecionadas.get(this.arrastando.id);
      const coords = coordenadasDe(sel.geometria);
      coords[this.arrastando.indice] = [pt.lng, pt.lat];
      sel.geometria = reconstruirGeometria(sel.geometria.type, coords);
      this._verticesRedesenhar();
    });
    map.on('mouseup', async () => {
      if (!this.arrastando) return;
      const id = this.arrastando.id;
      this.arrastando = null;
      map.dragPan.enable();
      map.getCanvas().style.cursor = '';
      await this._salvarGeometria(id);
    });
  }

  async _selecionarNoClique(ev) {
    const camadas = this.camadaId ? this.catalogo.idsDeEstilo(this.camadaId) : [];
    const feicoes = this.map.queryRenderedFeatures(ev.point, { layers: camadas.filter((idc) => this.map.getLayer(idc)) });
    if (!feicoes.length) return;
    // a função de tile (L2-01-b) exclui só geom/tenant_id/criado_por/atualizado_por — globalid vai junto
    const globalid = (feicoes[0].properties || {}).globalid;
    if (!globalid) { this.aoErro(t('erro.carregar')); return; }
    await this.selecionar(String(globalid), ev.originalEvent && ev.originalEvent.shiftKey);
  }

  // ---------------------------------------------------------------- API pública (também usada pelo e2e)
  async selecionar(globalid, acumular) {
    const r = await obter(`/api/mapa/camadas/${this.camadaId}`); // garante ficha (campos/regras) atual
    if (r.status !== 200) { this.aoErro(t('erro.carregar')); return; }
    const rf = await obter(`/api/camadas/${this.camadaId}/feicoes/${globalid}`);
    if (rf.status !== 200) { this.aoErro(t('erro.carregar')); return; }
    if (!acumular) this.selecionadas.clear();
    this.selecionadas.set(globalid, rf.json);
    this._verticesRedesenhar();
    await this._desenharPainelSelecao();
    return rf.json;
  }

  limparSelecao() {
    this.selecionadas.clear();
    this._verticesRedesenhar();
    this._desenharPainelSelecao();
  }

  async apagarSelecionada(globalid) {
    const sel = this.selecionadas.get(globalid);
    if (!sel) return;
    const r = await enviar(`/api/camadas/${this.camadaId}/edicoes`,
      { adicionar: [], atualizar: [], apagar: [{ id: globalid, versao: sel.versao }] });
    if (r.status !== 200) { this._mostrarErro(r); return; }
    this.selecionadas.delete(globalid);
    this._verticesRedesenhar();
    await this._religar();
    this._mensagem(t('mapa.edicao_salvo'));
    this._desenharPainelSelecao();
  }

  async _salvarGeometria(globalid) {
    const sel = this.selecionadas.get(globalid);
    const r = await enviar(`/api/camadas/${this.camadaId}/edicoes`,
      { adicionar: [], atualizar: [{ id: globalid, versao: sel.versao, geometria: sel.geometria }], apagar: [] });
    if (r.status === 200) {
      sel.versao = r.json.atualizar[0].versao;
      await this._religar();
      this._mensagem(t('mapa.edicao_salvo'));
    } else if (r.json && r.json.erro === 'conflito_versao') {
      // modo "transacao" (padrão): um item em conflito reprova a chamada inteira com 409 — o corpo é o
      // ErroAPI, não o EdicoesSaida por item (esse formato só existe em modo "parcial", que esta tela
      // não usa). A mensagem de conflito mora em #edicao-saida, perto do formulário, não no aviso global.
      this._mensagem(t('mapa.edicao_conflito'));
    } else {
      this._mostrarErro(r);
    }
  }

  async _religar() {
    const id = this.camadaId;
    if (!id) return;
    this.catalogo.desligar(id);
    try { await this.catalogo.ligar(id); } catch { /* sem tile por enquanto: segue */ }
  }

  _mostrarErro(r) {
    const j = (r.json) || {};
    this.aoErro(j.mensagem || t('erro.carregar'));
  }

  _mensagem(txt) {
    if (this.saida) this.saida.textContent = txt;
  }

  // ---------------------------------------------------------------- dividir/unir
  async _dividirNoPonto(ponto) {
    const [id] = this.selecionadas.keys();
    const sel = id && this.selecionadas.get(id);
    if (!sel) { this._mensagem(t('mapa.edicao_sem_selecao')); return; }
    const r = await enviar(`/api/camadas/${this.camadaId}/feicoes/dividir`, { id, versao: sel.versao, ponto });
    if (r.status !== 200) { this._mostrarErro(r); return; }
    this.selecionadas.clear();
    this._verticesRedesenhar();
    this.modo = 'nenhum';
    await this._religar();
    this._mensagem(t('mapa.edicao_salvo'));
    this._desenharPainelSelecao();
  }

  async unirSelecionadas() {
    const ids = [...this.selecionadas.keys()];
    if (ids.length < 2) return;
    const versoes = {};
    for (const [id, sel] of this.selecionadas) versoes[id] = sel.versao;
    const r = await enviar(`/api/camadas/${this.camadaId}/feicoes/unir`, { ids, versoes });
    if (r.status !== 200) { this._mostrarErro(r); return; }
    this.selecionadas.clear();
    this._verticesRedesenhar();
    await this._religar();
    this._mensagem(t('mapa.edicao_salvo'));
    this._desenharPainelSelecao();
  }

  // ---------------------------------------------------------------- formulário de atributos
  _camposDaCamada() {
    const f = this.catalogo.ficha(this.camadaId);
    return (f && f.campos) || [];
  }

  _regrasDaCamada() {
    const f = this.catalogo.ficha(this.camadaId);
    return (f && f.regras_campo) || {};
  }

  _validarCampo(campo, valor, regra) {
    if ((regra || {}).obrigatorio && (valor === '' || valor === null || valor === undefined)) {
      return t('mapa.edicao_campo_obrigatorio');
    }
    if (valor !== '' && valor !== null && (regra || {}).dominio_valores && !regra.dominio_valores.includes(valor)) {
      return t('mapa.edicao_campo_fora_do_dominio');
    }
    return null;
  }

  _campoInput(campo, regra, valorAtual, aoMudar) {
    const nome = campo.nome;
    if (regra && Array.isArray(regra.dominio_valores)) {
      const sel = h('select', { name: nome, onchange: (ev) => aoMudar(nome, ev.target.value) },
        h('option', { value: '' }, '—'),
        ...regra.dominio_valores.map((v) => h('option', { value: v, selected: v === valorAtual }, String(v))));
      return sel;
    }
    const tipo = campo.tipo === 'boolean' ? 'checkbox'
      : (campo.tipo === 'integer' || campo.tipo === 'bigint' || campo.tipo === 'double precision') ? 'number' : 'text';
    return h('input', {
      name: nome, type: tipo,
      value: tipo !== 'checkbox' ? (valorAtual ?? '') : undefined,
      checked: tipo === 'checkbox' ? !!valorAtual : undefined,
      onchange: (ev) => aoMudar(nome, tipo === 'checkbox' ? ev.target.checked
        : (tipo === 'number' ? (ev.target.value === '' ? null : Number(ev.target.value)) : ev.target.value)),
    });
  }

  _montarFormulario({ atributosIniciais, aoSubmeter, rotuloBotao, permitirLote }) {
    const campos = this._camposDaCamada();
    const regras = this._regrasDaCamada();
    const valores = { ...atributosIniciais };
    const erros = h('ul', { class: 'edicao-erros' });
    const form = h('form', { class: 'edicao-form' });
    let ultimoCampoMudado = null;
    for (const campo of campos) {
      const regra = regras[campo.nome];
      if ((regra || {}).somente_leitura) continue;
      const linha = h('div', { class: 'campo' },
        h('label', {}, campo.nome, (regra || {}).obrigatorio ? ' *' : ''),
        this._campoInput(campo, regra, valores[campo.nome], (nome, v) => { valores[nome] = v; ultimoCampoMudado = nome; }));
      form.append(linha);
    }
    const botoes = h('div', { class: 'linha' },
      h('button', { type: 'submit', class: 'botao' }, rotuloBotao));
    if (permitirLote && this.selecionadas.size > 1) {
      botoes.append(h('button', {
        type: 'button', class: 'botao secundario',
        onclick: () => this._aplicarEmLote(ultimoCampoMudado, valores[ultimoCampoMudado]),
      }, t('mapa.edicao_lote_aplicar', { n: this.selecionadas.size })));
    }
    form.append(erros, botoes);
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      limpar(erros);
      let ok = true;
      for (const campo of campos) {
        const msg = this._validarCampo(campo, valores[campo.nome], regras[campo.nome]);
        if (msg) { erros.append(h('li', {}, `${campo.nome}: ${msg}`)); ok = false; }
      }
      if (!ok) return;
      await aoSubmeter(valores);
    });
    return form;
  }

  _abrirFormularioNovo() {
    const tipo = this.catalogo.ficha(this.camadaId).geometria;
    const form = this._montarFormulario({
      atributosIniciais: {},
      rotuloBotao: t('mapa.edicao_salvar'),
      aoSubmeter: async (valores) => {
        const geometria = reconstruirGeometria(tipo, this.rascunho);
        const r = await enviar(`/api/camadas/${this.camadaId}/edicoes`,
          { adicionar: [{ atributos: valores, geometria }], atualizar: [], apagar: [] });
        if (r.status === 200 && r.json.adicionar[0].sucesso) {
          this.rascunho = [];
          this._rascunhoRedesenhar();
          await this._religar();
          this._mensagem(t('mapa.edicao_salvo'));
          this.painelDinamico && limpar(this.painelDinamico);
        } else {
          this._mostrarErro(r.status === 200 ? { json: r.json.adicionar[0] } : r);
        }
      },
    });
    if (this.painelDinamico) { limpar(this.painelDinamico); this.painelDinamico.append(form); }
  }

  async _aplicarEmLote(campo, valor) {
    if (!campo) return;
    const atualizar = [...this.selecionadas.entries()].map(([id, sel]) => ({
      id, versao: sel.versao, atributos: { [campo]: valor },
    }));
    const r = await enviar(`/api/camadas/${this.camadaId}/edicoes`, { adicionar: [], atualizar, apagar: [] });
    if (r.status !== 200) { this._mostrarErro(r); return; }
    for (const res of r.json.atualizar) {
      if (res.sucesso && this.selecionadas.has(res.id)) this.selecionadas.get(res.id).versao = res.versao;
    }
    await this._religar();
    this._mensagem(t('mapa.edicao_salvo'));
  }

  // ---------------------------------------------------------------- histórico
  async _historicoPainel(globalid) {
    const r = await obter(`/api/camadas/${this.camadaId}/feicoes/${globalid}/historico`);
    const raiz = h('div', { class: 'bloco' }, h('h3', {}, t('mapa.edicao_historico')));
    const lista = h('ul', { class: 'edicao-historico' });
    const entradas = (r.status === 200 && r.json) || [];
    if (!entradas.length) lista.append(h('li', {}, t('mapa.edicao_historico_vazio')));
    for (const e of entradas) {
      lista.append(h('li', {}, `${e.operacao} · ${new Date(e.momento).toLocaleString('pt-BR')} `,
        h('button', {
          type: 'button', class: 'botao secundario pequeno',
          onclick: async () => {
            const rr = await enviar(`/api/camadas/${this.camadaId}/feicoes/${globalid}/historico/${e.id}/restaurar`);
            if (rr.status !== 200) { this._mostrarErro(rr); return; }
            await this.selecionar(globalid, false);
            await this._religar();
            this._mensagem(t('mapa.edicao_historico_restaurado'));
          },
        }, t('mapa.edicao_historico_restaurar'))));
    }
    raiz.append(lista);
    return raiz;
  }

  // ---------------------------------------------------------------- anexos
  async _anexosPainel(globalid) {
    const raiz = h('div', { class: 'bloco' }, h('h3', {}, t('mapa.edicao_anexos')));
    const lista = h('ul', { class: 'edicao-anexos' });
    const redesenharLista = async () => {
      limpar(lista);
      const r = await obter(`/api/camadas/${this.camadaId}/feicoes/${globalid}/anexos`);
      const entradas = (r.status === 200 && r.json) || [];
      if (!entradas.length) lista.append(h('li', {}, t('mapa.edicao_anexos_vazio')));
      for (const a of entradas) {
        lista.append(h('li', {},
          h('a', { href: `/api/camadas/${this.camadaId}/feicoes/${globalid}/anexos/${a.id}`, target: '_blank', rel: 'noopener' }, a.nome),
          ` (${Math.round(a.bytes / 1024)} kB) `,
          h('button', {
            type: 'button', class: 'botao secundario pequeno',
            onclick: async () => {
              await apagarHttp(`/api/camadas/${this.camadaId}/feicoes/${globalid}/anexos/${a.id}`);
              await redesenharLista();
            },
          }, t('mapa.edicao_anexos_apagar'))));
      }
    };
    await redesenharLista();
    const arquivo = h('input', { type: 'file' });
    const enviarBtn = h('button', { type: 'button', class: 'botao' }, t('mapa.edicao_anexos_enviar'));
    enviarBtn.addEventListener('click', async () => {
      const f = arquivo.files && arquivo.files[0];
      if (!f) return;
      const conteudo = await new Promise((resolve, reject) => {
        const leitor = new FileReader();
        leitor.onload = () => resolve(String(leitor.result).split(',')[1] || '');
        leitor.onerror = reject;
        leitor.readAsDataURL(f);
      });
      const r = await enviar(`/api/camadas/${this.camadaId}/feicoes/${globalid}/anexos`,
        { nome: f.name, content_type: f.type || 'application/octet-stream', conteudo });
      if (r.status !== 201) { this._mostrarErro(r); return; }
      arquivo.value = '';
      await redesenharLista();
    });
    raiz.append(lista, h('div', { class: 'linha' }, arquivo, enviarBtn));
    return raiz;
  }

  async _desenharPainelSelecao() {
    if (!this.painelDinamico) return;
    if (this._loteAtualizar) this._loteAtualizar();
    limpar(this.painelDinamico);
    if (!this.selecionadas.size) {
      this.painelDinamico.append(h('p', { class: 'saida' }, t('mapa.edicao_sem_selecao')));
      return;
    }
    if (this.selecionadas.size > 1) {
      this.painelDinamico.append(h('p', {}, t('mapa.edicao_selecionadas', { n: this.selecionadas.size })));
    }
    const [primeiroId, primeiraSel] = [...this.selecionadas.entries()][0];
    const form = this._montarFormulario({
      atributosIniciais: primeiraSel.atributos,
      rotuloBotao: t('mapa.edicao_salvar'),
      permitirLote: true,
      aoSubmeter: async (valores) => {
        const r = await enviar(`/api/camadas/${this.camadaId}/edicoes`,
          { adicionar: [], atualizar: [{ id: primeiroId, versao: primeiraSel.versao, atributos: valores }], apagar: [] });
        if (r.status === 200) {
          primeiraSel.versao = r.json.atualizar[0].versao;
          primeiraSel.atributos = { ...primeiraSel.atributos, ...valores };
          await this._religar();
          await this._desenharPainelSelecao(); // histórico/anexos ficam desatualizados senão (achado do e2e)
          this._mensagem(t('mapa.edicao_salvo'));
        } else if (r.json && r.json.erro === 'conflito_versao') {
          // ver nota equivalente em _salvarGeometria: modo "transacao" devolve 409 com o corpo do ErroAPI
          this._mensagem(t('mapa.edicao_conflito'));
        } else {
          this._mostrarErro(r);
        }
      },
    });
    this.painelDinamico.append(form);
    if (this.selecionadas.size === 1) {
      this.painelDinamico.append(await this._historicoPainel(primeiroId));
      this.painelDinamico.append(await this._anexosPainel(primeiroId));
    }
  }

  // ---------------------------------------------------------------- edição em lote (item L2-03-f)
  /* `POST /api/camadas/{id}/lote`: calcular campo por expressão, atribuir valor, apagar e corrigir geometria sobre
     as selecionadas, todas ou uma expressão `onde`; pré-visualização (10 linhas antes/depois) antes de aplicar;
     acima de 5.000 feições a API devolve 202 com o job — o painel acompanha o progresso e permite cancelar. */
  _montarLote() {
    const caixa = h('section', { id: 'edicao-lote', class: 'edicao-lote', 'aria-labelledby': 'edicao-lote-titulo' });
    const op = h('select', { id: 'lote-operacao' },
      ...[['calcular', 'mapa.lote_calcular'], ['atribuir', 'mapa.lote_atribuir'], ['apagar', 'mapa.lote_apagar'],
        ['corrigir_geometria', 'mapa.lote_corrigir']].map(([v, k]) => h('option', { value: v }, t(k))));
    const campo = h('select', { id: 'lote-campo' });
    const expressao = h('textarea', { id: 'lote-expressao', rows: '2', spellcheck: 'false',
      title: t('mapa.lote_expressao_exemplo') });
    const valor = h('input', { id: 'lote-valor', type: 'text' });
    const onde = h('input', { id: 'lote-onde', type: 'text', title: t('mapa.lote_onde_exemplo'),
      'aria-label': t('mapa.lote_onde') });
    const radio = (v, rotulo) => h('label', { class: 'lote-radio' },
      h('input', { type: 'radio', name: 'lote-selecao', value: v, checked: v === 'todas' }), h('span', {}, rotulo));
    const rSel = radio('selecionadas', '');
    const ajuda = h('small', { id: 'lote-ajuda', class: 'ajuda' });
    const linhaCampo = h('div', { class: 'campo' }, h('label', { for: 'lote-campo' }, t('mapa.lote_campo')), campo);
    const linhaExpr = h('div', { class: 'campo' }, h('label', { for: 'lote-expressao' }, t('mapa.lote_expressao')),
      expressao, ajuda);
    const linhaValor = h('div', { class: 'campo' }, h('label', { for: 'lote-valor' }, t('mapa.lote_valor')), valor);
    const saida = h('div', { id: 'lote-resultado', 'aria-live': 'polite' });
    const erro = h('p', { id: 'lote-erro', class: 'edicao-erros', role: 'alert', hidden: true });
    const btPrevia = h('button', { type: 'button', class: 'botao secundario', id: 'lote-previa' }, t('mapa.lote_previa'));
    const btAplicar = h('button', { type: 'button', class: 'botao', id: 'lote-aplicar' }, t('mapa.lote_aplicar'));
    const btCancelar = h('button', { type: 'button', class: 'botao secundario', id: 'lote-cancelar', hidden: true },
      t('mapa.lote_cancelar'));
    const atualizarCampos = () => {
      limpar(campo);
      const regras = this._regrasDaCamada();
      for (const c of this._camposDaCamada()) {
        if ((regras[c.nome] || {}).somente_leitura) continue;
        campo.append(h('option', { value: c.nome }, `${c.nome} (${c.tipo})`));
      }
      const nomes = this._camposDaCamada().map((c) => `$${c.nome}`);
      ajuda.textContent = t('mapa.lote_expressao_ajuda', {
        campos: nomes.join(' '), derivados: '$area_m2 $comprimento_m $perimetro_m $x $y' });
    };
    const atualizarVisibilidade = () => {
      const o = op.value;
      linhaCampo.hidden = !(o === 'calcular' || o === 'atribuir');
      linhaExpr.hidden = o !== 'calcular';
      linhaValor.hidden = o !== 'atribuir';
      rSel.firstChild.disabled = !this.selecionadas.size;
      rSel.lastChild.textContent = t('mapa.lote_selecionadas', { n: this.selecionadas.size });
      if (!this.selecionadas.size && rSel.firstChild.checked) caixa.querySelector('input[value="todas"]').checked = true;
    };
    op.addEventListener('change', atualizarVisibilidade);
    this._loteAtualizar = () => { atualizarCampos(); atualizarVisibilidade(); };
    const corpo = () => {
      const sel = caixa.querySelector('input[name="lote-selecao"]:checked').value;
      const selecao = sel === 'selecionadas' ? { ids: [...this.selecionadas.keys()] }
        : sel === 'onde' ? { onde: onde.value } : { todas: true };
      const c = { operacao: op.value, selecao };
      if (op.value === 'calcular') { c.campo = campo.value; c.expressao = expressao.value; }
      if (op.value === 'atribuir') {
        c.campo = campo.value;
        const tipo = (this._camposDaCamada().find((x) => x.nome === campo.value) || {}).tipo;
        const v = valor.value;
        c.valor = v === '' ? null : tipo === 'boolean' ? (v === 'true' || v === 'verdadeiro' || v === '1')
          : (tipo === 'integer' || tipo === 'bigint' || tipo === 'double precision') ? Number(v) : v;
      }
      return c;
    };
    const mostrarErro = (r) => {
      const j = r.json || {};
      // erro NOMEADO da API (422/403/409): código + mensagem, nunca o número cru
      erro.textContent = j.erro ? `${j.erro}: ${j.mensagem}` : (j.mensagem || t('erro.carregar'));
      erro.hidden = false;
    };
    const desenharPrevia = (j) => {
      limpar(saida);
      const linhas = j.previa || [];
      saida.append(h('p', { class: 'ajuda' }, t('mapa.lote_previa_total', { n: linhas.length, total: j.total })
        + (j.traducao ? ` · ${t('mapa.lote_traducao_' + j.traducao)}` : '')));
      if (!linhas.length) return;
      const fmt = (v) => (v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
      saida.append(h('table', { class: 'lote-tabela' },
        h('thead', {}, h('tr', {}, h('th', {}, 'id'), h('th', {}, t('mapa.lote_antes')), h('th', {}, t('mapa.lote_depois')))),
        h('tbody', {}, ...linhas.map((l) => h('tr', { class: l.erro ? 'erro' : '' },
          h('td', { class: 'mono' }, l.id.slice(0, 8)), h('td', {}, fmt(l.antes)),
          h('td', {}, l.erro ? `${l.erro}: ${l.mensagem}` : fmt(l.depois)))))));
    };
    const resumo = (j) => t('mapa.lote_resultado', { alteradas: j.alteradas || 0, apagadas: j.apagadas || 0,
      criadas: j.criadas || 0, corrigidas: j.corrigidas || 0, falhas: j.falhas_total || 0 });
    let jobAtual = null;
    const acompanhar = async (jobId) => {
      jobAtual = jobId;
      btCancelar.hidden = false;
      limpar(saida);
      const linha = h('p', { id: 'lote-job' }, t('mapa.lote_job', { pct: 0 }), ' ',
        h('a', { href: `/tarefas/${jobId}` }, t('mapa.lote_job_ver')));
      saida.append(linha);
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        const r = await obter(`/api/jobs/${jobId}`);
        if (r.status !== 200) { mostrarErro(r); break; }
        const j = r.json;
        linha.firstChild.textContent = t('mapa.lote_job', { pct: j.progresso || 0 });
        if (['concluido', 'falhou', 'cancelado'].includes(j.estado)) {
          linha.firstChild.textContent = j.estado === 'concluido' ? resumo(j.resultado || {})
            : t('mapa.lote_job_' + j.estado, { erro: j.erro || '' });
          if (j.estado === 'concluido') await this._religar();
          break;
        }
      }
      btCancelar.hidden = true;
      jobAtual = null;
    };
    btCancelar.addEventListener('click', async () => { if (jobAtual) await enviar(`/api/jobs/${jobAtual}/cancelar`, {}); });
    btPrevia.addEventListener('click', async () => {
      erro.hidden = true;
      const r = await enviar(`/api/camadas/${this.camadaId}/lote`, { ...corpo(), previa: true });
      if (r.status !== 200) { mostrarErro(r); return; }
      desenharPrevia(r.json);
    });
    btAplicar.addEventListener('click', async () => {
      erro.hidden = true;
      const c = corpo();
      if (c.operacao === 'apagar' && !window.confirm(t('mapa.lote_confirmar_apagar'))) return;
      btAplicar.disabled = true;
      const r = await enviar(`/api/camadas/${this.camadaId}/lote`, c);
      btAplicar.disabled = false;
      if (r.status === 202) { await acompanhar(r.json.job_id); return; }
      if (r.status !== 200) { mostrarErro(r); return; }
      limpar(saida);
      saida.append(h('p', { id: 'lote-ok' }, resumo(r.json)
        + (r.json.traducao ? ` · ${t('mapa.lote_traducao_' + r.json.traducao)}` : '')));
      await this._religar();
      this._mensagem(t('mapa.edicao_salvo'));
      if (c.operacao === 'apagar') this.limparSelecao();
    });
    caixa.append(
      h('h3', { id: 'edicao-lote-titulo' }, t('mapa.lote')),
      h('div', { class: 'campo' }, h('label', { for: 'lote-operacao' }, t('mapa.lote_operacao')), op),
      linhaCampo, linhaExpr, linhaValor,
      h('fieldset', { class: 'lote-selecao' }, h('legend', {}, t('mapa.lote_selecao')),
        rSel, radio('todas', t('mapa.lote_todas')), radio('onde', t('mapa.lote_onde')), onde),
      h('div', { class: 'linha' }, btPrevia, btAplicar, btCancelar),
      erro, saida,
    );
    this._loteAtualizar();
    return caixa;
  }

  // ---------------------------------------------------------------- barra de ferramentas
  _montarUI() {
    const raiz = this.raiz;
    const seletor = h('select', { id: 'edicao-camada' });
    const modoBotoes = {};
    const definirModo = (m) => {
      this.modo = this.modo === m ? 'nenhum' : m;
      this.rascunho = [];
      this._rascunhoRedesenhar();
      for (const [k, b] of Object.entries(modoBotoes)) b.setAttribute('aria-pressed', k === this.modo ? 'true' : 'false');
    };
    for (const [chave, rotulo] of [
      ['adicionar_ponto', 'mapa.edicao_ponto'], ['adicionar_linha', 'mapa.edicao_linha'],
      ['adicionar_poligono', 'mapa.edicao_poligono'], ['selecionar', 'mapa.edicao_selecionar'],
    ]) {
      const b = h('button', { type: 'button', class: 'botao', 'aria-pressed': 'false', onclick: () => definirModo(chave) }, t(rotulo));
      modoBotoes[chave] = b;
    }
    const concluir = h('button', {
      type: 'button', class: 'botao',
      onclick: () => {
        if ((this.modo === 'adicionar_linha' && this.rascunho.length >= 2)
          || (this.modo === 'adicionar_poligono' && this.rascunho.length >= 3)) this._abrirFormularioNovo();
      },
    }, t('mapa.edicao_concluir'));
    const dividirBtn = h('button', { type: 'button', class: 'botao', 'aria-pressed': 'false',
      onclick: () => definirModo('dividir') }, t('mapa.edicao_dividir'));
    modoBotoes.dividir = dividirBtn;
    const unirBtn = h('button', { type: 'button', class: 'botao', onclick: () => this.unirSelecionadas() }, t('mapa.edicao_unir'));
    const apagarBtn = h('button', {
      type: 'button', class: 'botao secundario',
      onclick: () => { const [id] = this.selecionadas.keys(); if (id) this.apagarSelecionada(id); },
    }, t('mapa.edicao_apagar'));
    const aderirCk = h('input', { type: 'checkbox', id: 'edicao-aderir', checked: true,
      onchange: (ev) => { this.aderir = ev.target.checked; } });

    this.saida = h('p', { class: 'saida', id: 'edicao-saida', 'aria-live': 'polite' });
    this.painelDinamico = h('div', { id: 'edicao-dinamico' });
    const lote = this._montarLote();

    seletor.addEventListener('change', () => {
      this.camadaId = seletor.value || null;
      this.selecionadas.clear();
      this._verticesRedesenhar();
      this._desenharPainelSelecao();
      this._loteAtualizar();
    });
    this.catalogo.aoMudar(() => this._redesenharSeletor(seletor));
    this._redesenharSeletor(seletor);

    limpar(raiz);
    raiz.append(
      h('h2', {}, t('mapa.edicao')),
      h('label', { class: 'rotulo', for: 'edicao-camada' }, t('mapa.edicao_camada')), seletor,
      h('div', { class: 'linha' }, ...Object.values(modoBotoes).filter((b) => b !== dividirBtn), concluir),
      h('div', { class: 'linha' }, dividirBtn, unirBtn, apagarBtn),
      h('div', { class: 'linha' }, aderirCk, h('label', { for: 'edicao-aderir' }, t('mapa.edicao_aderir'))),
      this.saida,
      this.painelDinamico,
      lote,
    );
    this._desenharPainelSelecao();
  }

  _redesenharSeletor(seletor) {
    const atual = seletor.value;
    limpar(seletor);
    const editaveis = this.catalogo.disponiveis.filter((f) => f.editavel);
    if (!editaveis.length) {
      seletor.append(h('option', { value: '' }, t('mapa.edicao_camada_nenhuma')));
      seletor.disabled = true;
      return;
    }
    seletor.disabled = false;
    seletor.append(h('option', { value: '' }, '—'));
    for (const f of editaveis) seletor.append(h('option', { value: f.id, selected: f.id === atual }, f.titulo));
    if (!this.camadaId && editaveis.length === 1) { seletor.value = editaveis[0].id; this.camadaId = editaveis[0].id; }
  }
}

export { familiaDeGeometria };
