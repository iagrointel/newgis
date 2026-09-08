/* plat · mapa — bloco "Exportar" (item L2-01-l).

   Três coisas saem daqui, todas do que já está na tela:

   * ARQUIVO DE DADO — camada ativa, formato, CRS e recorte (camada inteira ou só as feições da vista
     atual). É um job no servidor (`POST /api/exportacoes`), então a tela pergunta o estado até ficar
     pronto e mostra o link, com a validade em dias que o próprio servidor informa. Não há download
     "direto": um GeoPackage de camada grande passa de 1 GB e o navegador não é o lugar de montá-lo.
   * ESTILO — MapLibre (JSON) ou SLD 1.0.0, o mesmo que o servidor gera da simbologia da camada.
   * CÓPIA DE FEIÇÃO — GeoJSON ou WKT na área de transferência, lido da tabela (a geometria do tile vem
     recortada na borda, ver `app/mapa/exportar.py`).

   O que a tela mostra ANTES de exportar: a "perda declarada" que o servidor devolve — DXF não leva
   atributo, shapefile trunca nome de campo em 10 caracteres, GeoJSON grava sempre em EPSG:4326. É a
   diferença entre o usuário escolher um formato e descobrir a perda depois de abrir o arquivo. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { chamar, obter } from '../base/api.js';

const ESPERA_MS = 700;

/* corpo CRU (zip do pacote) sob o cookie da sessão: o cliente comum js/base/api.js só fala JSON */
function enviarBruto(metodo, url, corpo, tipo) {
  return fetch(url, { method: metodo, body: corpo, credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': tipo, Accept: 'application/json' } });
}

export async function listarFormatos() {
  const r = await obter('/api/exportacoes/formatos');
  if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao listar formatos');
  return r.json;
}

export function copiarTexto(texto) {
  /* `navigator.clipboard` só existe em contexto seguro; o retorno para textarea+execCommand é o que
     mantém a cópia funcionando em http de rede interna, que é onde esta plataforma costuma rodar. */
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texto);
  const area = document.createElement('textarea');
  area.value = texto;
  area.setAttribute('readonly', '');
  area.style.cssText = 'position:absolute;left:-9999px';
  document.body.append(area);
  area.select();
  const ok = document.execCommand('copy');
  area.remove();
  return ok ? Promise.resolve() : Promise.reject(new Error('cópia recusada pelo navegador'));
}

export async function copiarFeicao(camadaId, fid, formato) {
  const r = await obter(`/api/mapa/camadas/${camadaId}/feicoes/${fid}?formato=${formato}`);
  if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao ler a feição');
  await copiarTexto(r.json.texto);
  return r.json.texto.length;
}

export async function esperarExportacao(id, aoProgresso) {
  for (;;) {
    const r = await obter(`/api/exportacoes/${id}`);
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao consultar a exportação');
    const e = r.json;
    if (aoProgresso) aoProgresso(e.estado);
    if (['pronta', 'falhou', 'cancelada', 'expirada'].includes(e.estado)) return e;
    await new Promise((r2) => setTimeout(r2, ESPERA_MS));
  }
}

export class PainelExportar {
  constructor(catalogo, map, { raiz, aoErro }) {
    this.catalogo = catalogo;
    this.map = map;
    this.raiz = raiz;
    this.aoErro = aoErro || (() => {});
    this.formatos = [];
    this.validadeDias = null;
  }

  async iniciar() {
    const r = await listarFormatos();
    this.formatos = r.formatos.filter((f) => f.nome !== 'pacote');
    this.validadeDias = r.validade_dias;
    this.catalogo.aoMudar(() => this.desenhar());
    this.desenhar();
  }

  formatoAtual() {
    const nome = this.raiz.querySelector('#exp-formato')?.value;
    return this.formatos.find((f) => f.nome === nome) || null;
  }

  desenhar() {
    const raiz = this.raiz;
    const camadaAnterior = raiz.querySelector('#exp-camada')?.value;
    const formatoAnterior = raiz.querySelector('#exp-formato')?.value;
    limpar(raiz);
    const ativas = this.catalogo.ativas.map((id) => this.catalogo.ficha(id)).filter(Boolean);
    if (!ativas.length) {
      raiz.append(h('p', { class: 'saida', id: 'exp-vazio' }, t('mapa.exportar_sem_camada')));
      this.desenharImportacao();
      return;
    }
    const camada = h('select', { id: 'exp-camada', 'aria-label': t('mapa.exportar_camada') },
      ...ativas.map((f) => h('option', { value: f.id }, f.titulo)));
    if (camadaAnterior && ativas.some((f) => f.id === camadaAnterior)) camada.value = camadaAnterior;
    const formato = h('select', { id: 'exp-formato', 'aria-label': t('mapa.exportar_formato'),
      onchange: () => this.mostrarPerda() },
    ...this.formatos.map((f) => h('option', { value: f.nome }, f.rotulo)));
    if (formatoAnterior) formato.value = formatoAnterior;
    // rótulo visível em vez de texto de dica dentro do campo: dica dentro do campo some ao digitar
    const crs = h('input', { id: 'exp-crs', type: 'number', min: '1', max: '999999',
      'aria-label': t('mapa.exportar_crs') });
    const crsRotulo = h('label', { class: 'rotulo', for: 'exp-crs' }, 'EPSG');
    const soVista = h('input', { type: 'checkbox', id: 'exp-so-vista' });
    const botao = h('button', { type: 'button', class: 'botao', id: 'btn-exportar',
      onclick: () => this.exportar() }, t('mapa.exportar'));
    raiz.append(
      h('div', { class: 'linha' }, camada),
      h('div', { class: 'linha' }, formato, crsRotulo, crs),
      h('div', { class: 'linha' },
        h('label', { class: 'rotulo', for: 'exp-so-vista' }, soVista, t('mapa.exportar_so_vista'))),
      h('div', { class: 'linha' }, botao,
        h('button', { type: 'button', class: 'botao secundario', id: 'btn-estilo-maplibre',
          onclick: () => this.baixarEstilo('maplibre') }, 'MapLibre'),
        h('button', { type: 'button', class: 'botao secundario', id: 'btn-estilo-sld',
          onclick: () => this.baixarEstilo('sld') }, 'SLD')),
      h('p', { class: 'saida', id: 'exp-perda', 'aria-live': 'polite' }),
      h('p', { class: 'saida', id: 'exp-saida', 'aria-live': 'polite' }),
    );
    this.mostrarPerda();
    this.desenharImportacao();
  }

  /* importação de pacote de mapa (UX-23): o zip que outro inquilino exportou volta como mapa + camadas novas
     (POST /api/mapa/pacotes/importar, corpo = zip cru). O bloco existe mesmo sem camada ativa — importar é o
     que traz a primeira camada. */
  desenharImportacao() {
    const raiz = this.raiz;
    if (raiz.querySelector('#imp-bloco')) return;
    const entrada = h('input', { type: 'file', id: 'imp-arquivo', accept: '.zip,application/zip' });
    const botao = h('button', { type: 'button', class: 'botao', id: 'btn-importar-pacote', disabled: true,
      onclick: () => this.importarPacote() }, t('mapa.pacote_importar'));
    entrada.addEventListener('change', () => { botao.disabled = !entrada.files.length; });
    const estado = h('plat-estado', { id: 'imp-estado' });
    estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.importarPacote(); });
    raiz.append(h('section', { class: 'exp-importar', id: 'imp-bloco', 'aria-labelledby': 'imp-titulo' },
      h('h3', { id: 'imp-titulo' }, t('mapa.pacote_titulo')),
      h('p', { class: 'ajuda' }, t('mapa.pacote_ajuda')),
      h('div', { class: 'linha' }, h('label', { class: 'rotulo', for: 'imp-arquivo' }, t('mapa.pacote_arquivo')), entrada),
      h('div', { class: 'linha' }, botao),
      estado,
      h('p', { class: 'saida', id: 'imp-saida', 'aria-live': 'polite' })));
    // o painel é redesenhado a cada mudança do catálogo (inclusive a recarga depois de importar): o resumo da
    // última importação é reposto para não sumir debaixo do usuário
    if (this.ultimaImportacao) this.mostrarImportacao(this.ultimaImportacao);
  }

  mostrarImportacao(json) {
    const saida = this.raiz.querySelector('#imp-saida');
    if (!saida) return;
    const camadas = (json && json.camadas) || [];
    limpar(saida).append(t('mapa.pacote_importado', { n: camadas.length, titulo: (json && json.titulo) || '' }), ' ',
      h('a', { href: `/mapa?mapa=${encodeURIComponent(json.mapa_id)}`, id: 'imp-abrir' }, t('mapa.pacote_abrir')));
  }

  async importarPacote() {
    const entrada = this.raiz.querySelector('#imp-arquivo');
    const estado = this.raiz.querySelector('#imp-estado');
    const saida = this.raiz.querySelector('#imp-saida');
    const botao = this.raiz.querySelector('#btn-importar-pacote');
    const arquivo = entrada && entrada.files && entrada.files[0];
    limpar(saida);
    if (!arquivo) { estado.erro(t('mapa.pacote_sem_arquivo'), []); return; }
    if (!/\.zip$/i.test(arquivo.name)) { estado.erro(t('mapa.pacote_nao_zip', { nome: arquivo.name }), []); return; }
    estado.carregando(t('mapa.pacote_enviando', { mb: (arquivo.size / (1024 * 1024)).toFixed(1) }));
    botao.disabled = true;
    let resp; let json = null;
    try {
      resp = await enviarBruto('POST', '/api/mapa/pacotes/importar', arquivo, 'application/zip');
      try { json = await resp.json(); } catch { json = null; }
    } catch (e) {
      botao.disabled = false;
      estado.erro({ status: 0, json: { mensagem: (e && e.message) || String(e) } }, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }]);
      return;
    }
    botao.disabled = false;
    if (resp.status !== 201) {
      const r = { status: resp.status, json: json || {} };
      estado.mostrar({ tipo: resp.status === 403 ? 'negado' : 'erro', texto: this.textoErroPacote(r),
        acoes: resp.status >= 500 ? [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] : [], ref: r.json.req_id });
      return;
    }
    estado.limpar();
    entrada.value = '';
    botao.disabled = true;
    this.ultimaImportacao = json;
    this.mostrarImportacao(json);
    try { await this.catalogo.carregar(); } catch (e) { this.aoErro(e); }
  }

  textoErroPacote(r) {
    const j = r.json || {};
    const base = (j.mensagem) || `${t('erro.carregar')} (${r.status})`;
    if (r.status === 413) return t('mapa.pacote_grande', { mensagem: base });
    if (j.erro === 'pacote_invalido' || j.erro === 'pacote_vazio') return t('mapa.pacote_invalido', { mensagem: base });
    if (j.erro === 'pacote_camada_invalida') return t('mapa.pacote_camada_invalida', { mensagem: base });
    return base;
  }

  mostrarPerda() {
    const f = this.formatoAtual();
    const alvo = this.raiz.querySelector('#exp-perda');
    if (!f || !alvo) return;
    const avisos = [];
    if (!f.guarda_atributos) avisos.push(t('mapa.exportar_sem_atributo', { formato: f.rotulo }));
    if (!f.guarda_geometria) avisos.push(t('mapa.exportar_sem_geometria', { formato: f.rotulo }));
    if (f.crs_saida === '4326' || f.crs_saida === '3857') {
      avisos.push(t('mapa.exportar_crs_fixo', { formato: f.rotulo, epsg: f.crs_saida }));
    }
    alvo.textContent = avisos.join(' · ');
    const crs = this.raiz.querySelector('#exp-crs');
    if (crs) crs.disabled = f.crs_saida !== 'livre';
  }

  async baixarEstilo(formato) {
    const id = this.raiz.querySelector('#exp-camada').value;
    const url = `/api/mapa/camadas/${id}/estilo?formato=${formato}`;
    if (formato === 'sld') { window.open(url, '_blank', 'noopener'); return; }
    const r = await obter(url);
    if (r.status !== 200) { this.aoErro(new Error((r.json && r.json.mensagem) || 'falha')); return; }
    const blob = new Blob([JSON.stringify(r.json, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `estilo-${id}.json`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 30000);
  }

  corpoDoPedido() {
    const id = this.raiz.querySelector('#exp-camada').value;
    const formato = this.raiz.querySelector('#exp-formato').value;
    const crs = this.raiz.querySelector('#exp-crs');
    const corpo = { item_id: id, formato };
    if (crs && !crs.disabled && crs.value) corpo.srid_saida = Number(crs.value);
    if (this.raiz.querySelector('#exp-so-vista').checked) {
      const b = this.map.getBounds();
      corpo.bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    }
    return corpo;
  }

  async exportar() {
    const saida = this.raiz.querySelector('#exp-saida');
    const botao = this.raiz.querySelector('#btn-exportar');
    botao.disabled = true;
    limpar(saida);
    saida.textContent = t('mapa.exportar_pedindo');
    try {
      const r = await chamar('POST', '/api/exportacoes', this.corpoDoPedido());
      if (r.status !== 202) throw new Error((r.json && r.json.mensagem) || 'falha ao pedir a exportação');
      const final = await esperarExportacao(r.json.exportacao_id,
        (estado) => { saida.textContent = t('mapa.exportar_estado', { estado }); });
      limpar(saida);
      if (final.estado !== 'pronta') {
        saida.textContent = t('mapa.exportar_falhou', { erro: final.erro || final.estado });
        return;
      }
      saida.append(
        h('a', { href: final.link, download: '', id: 'exp-link' },
          t('mapa.exportar_baixar', { feicoes: (final.feicoes ?? 0).toLocaleString('pt-BR') })),
        h('span', {}, ` · ${t('mapa.exportar_validade', { dias: final.validade_dias })}`),
      );
    } catch (e) {
      saida.textContent = (e && e.message) || String(e);
      this.aoErro(e);
    } finally {
      botao.disabled = false;
    }
  }
}
