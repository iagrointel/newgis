/* plat · reportar — botão "reportar problema" presente em TODA tela com layout (item L7-13-a-chamados).
   Abre o formulário com CAPTURA AUTOMÁTICA e CONTEXTO AUTOMÁTICO:
   - captura: quadro real do canvas do mapa (window.platMapa, registrado por web/js/mapa/mapa.js; o quadro só
     é capturável dentro de um evento 'render' do MapLibre). Tela sem mapa não inventa captura — vai sem, e a
     estrutura do DOM segue como texto.
   - contexto: tela (caminho), versão (GET /api/versao, consultada uma vez), navegador (user agent), idioma,
     req_id das últimas 20 requisições (anel de web/js/base/api.js) e estrutura enxuta do DOM visível
     (tag + texto curto de títulos/botões — NUNCA valor de campo de formulário, para não anexar dado de
     inquilino ao chamado).
   Também monta o BANNER de resposta do suporte (GET /api/chamados/banner) no início da barra lateral. */
import { enviar, obter, reqIdsRecentes } from '../base/api.js';
import '../base/componentes.js';
import { h } from '../base/dom.js';
import { idiomaAtual, t } from '../base/i18n.js';

let versaoCache = null;

export function capturarDom() {
  const seletor = 'main h1, main h2, main button, aside a[aria-current], .marcador, [role="alert"]';
  const estrutura = [];
  document.querySelectorAll(seletor).forEach((e) => {
    if (estrutura.length >= 60) return;
    const texto = (e.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
    if (!texto) return;
    estrutura.push({ tag: e.tagName.toLowerCase(), texto });
  });
  return estrutura;
}

export function capturarMapa() {
  const mapa = window.platMapa;
  if (!mapa || !mapa.getCanvas) return Promise.resolve(null);
  return new Promise((res) => {
    const teto = setTimeout(() => res(null), 2000);
    mapa.once('render', () => {
      clearTimeout(teto);
      try {
        res(mapa.getCanvas().toDataURL('image/png'));
      } catch {
        res(null);
      }
    });
    mapa.triggerRepaint();
  });
}

async function contexto() {
  if (versaoCache === null) {
    const r = await obter('/api/versao');
    versaoCache = r.status === 200 && r.json.versao ? String(r.json.versao) : '';
  }
  return {
    tela: location.pathname,
    versao: versaoCache,
    navegador: navigator.userAgent,
    idioma: idiomaAtual(),
    req_ids: reqIdsRecentes(),
    dom: capturarDom(),
  };
}

function campo(rotulo, entrada) {
  return h('label', { class: 'campo' }, h('span', {}, rotulo), entrada);
}

function formularioAoAbrir(dialogo) {
  const titulo = h('input', { id: 'chamado-titulo', maxlength: '200', required: 'required' });
  const descricao = h('textarea', { id: 'chamado-descricao', rows: '5', maxlength: '20000' });
  const severidade = h('select', { id: 'chamado-severidade' },
    ...['baixa', 'media', 'alta', 'critica'].map((s) => h('option', { value: s }, t(`chamado.sev.${s}`))));
  severidade.value = 'media';
  const captura = h('input', { type: 'checkbox', id: 'chamado-captura', checked: 'checked' });
  const form = h('form', { class: 'formulario' },
    campo(t('chamado.titulo'), titulo),
    campo(t('chamado.descricao'), descricao),
    campo(t('chamado.severidade'), severidade),
    h('label', { class: 'campo-linha' }, captura, ' ', t('chamado.incluir_captura')),
    h('p', { class: 'ajuda' }, t('chamado.captura_ajuda')));
  const enviarBt = h('button', { type: 'submit', class: 'primario' }, t('chamado.enviar'));
  form.append(enviarBt);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    enviarBt.disabled = true;
    const corpo = {
      titulo: titulo.value.trim(),
      descricao: descricao.value.trim(),
      severidade: severidade.value,
      contexto: await contexto(),
    };
    if (captura.checked) corpo.captura = await capturarMapa();
    const r = await enviar('/api/chamados', corpo);
    if (r.status !== 201) {
      enviarBt.disabled = false;
      form.querySelector('.ajuda').textContent = `${t('chamado.erro_abrir')}: ${r.json.mensagem || r.status}`;
      return;
    }
    dialogo.fechar('ok');
  }, { once: true });
  return form;
}

export async function abrirReporte() {
  const dialogo = document.createElement('plat-dialogo');
  document.body.append(dialogo);
  const form = formularioAoAbrir(dialogo);
  await dialogo.abrir({ titulo: t('chamado.reportar'), corpo: form });
  dialogo.remove();
}

/* banner: chamados do cliente com resposta nova ou resolvidos desde a última leitura */
export async function montarBanner() {
  const caixa = document.getElementById('banner-chamados');
  if (!caixa) return;
  const r = await obter('/api/chamados/banner');
  if (r.status !== 200 || !Array.isArray(r.json) || !r.json.length) return;
  const primeiro = r.json[0];
  const a = h('a', { href: '/chamados', id: 'banner-chamados-link' },
    t('chamado.banner.' + primeiro.motivo, { numero: primeiro.numero }));
  caixa.append(a);
  caixa.hidden = false;
}

/* chamado por montarLayout (web/js/base/layout.js): botão na barra lateral + banner */
export function montar(usuario) {
  const aside = document.getElementById('lateral');
  if (!aside) return;
  if (!usuario) return;
  const banner = h('div', { id: 'banner-chamados', class: 'banner-chamados', hidden: 'hidden' });
  const botao = h('button', { type: 'button', class: 'pequeno', id: 'reportar' }, t('chamado.reportar'));
  botao.addEventListener('click', () => abrirReporte());
  aside.append(banner, botao);
  montarBanner();
}
