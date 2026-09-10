/* plat · catálogo — painel do tipo 'camada_vetorial' (tipo_item.modulo_front), usado pelo painel do item
   (item.js) na aba Visão geral (prévia() → resumo + mapa) e na aba Compartilhamento (compartilhar() → URL de
   serviço). Reusa o que a rota do mapa já monta: `GET /api/mapa/camadas/{id}` devolve geometria/campos/
   n_feicoes/tilejson/estilo prontos (app/mapa/rotas.py); a prévia sob sessão não cunha token nenhum — quem
   cunha é a própria rota de tilejson, escopada só àquela camada, 12 h. As URLs da seção Compartilhar (WFS/
   OGC API Features/Esri FeatureServer) são para cliente EXTERNO (QGIS, ArcGIS, um script) e por isso levam
   um token de serviço de verdade (token_servico.js). A seção "Publicar no ArcGIS Online" (item
   L2-08-migracao-agol), no fim da mesma aba, fala com `app/agol/rotas.py`: credencial do inquilino
   (GET/PUT /api/agol/credencial + POST /api/agol/testar) e o estado de publicação por item
   (POST/GET /api/agol/publicacoes) — só aparece o formulário de credencial e o botão Publicar; nunca finge
   que publicou sem a credencial configurada (a API recusa com 422 `agol_nao_configurado`, mostrado aqui tal
   e qual). */
import { h, limpar } from '../../base/dom.js';
import { obter, enviar, alterar, mensagemDe } from '../../base/api.js';
import { botaoCopiar } from '../../base/dom.js';
import { t } from '../../base/i18n.js';
import { dataHora } from '../formato.js';
import { tokenServico, renovarTokenServico } from './token_servico.js';

export const tipo = 'camada_vetorial';

/* mantido pelo contrato de tipo_item.modulo_front (ADR 0004 seção 15.1): abrir este tipo é ir ao mapa, onde
   a camada aparece na árvore de camadas do catálogo. */
export function abrir() { location.assign('/mapa'); }

function campoUrl(valor) {
  const entrada = h('input', { type: 'text', readonly: true, value: valor, class: 'campo-url', 'aria-label': valor });
  const bt = botaoCopiar(valor, entrada, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') });
  return h('div', { class: 'linha-url' }, entrada, bt);
}

function linha(rotulo, valor) {
  return h('div', { class: 'campo-linha' }, h('div', { class: 'rotulo' }, rotulo), h('div', { class: 'valor' }, valor));
}

/* ---------- Visão geral: resumo + prévia no mapa ---------- */
export async function previa(item) {
  const raiz = h('div', { class: 'tipo-previa tipo-camada-vetorial' });
  let ficha;
  try {
    ficha = await obter(`/api/mapa/camadas/${encodeURIComponent(item.id)}`);
  } catch {
    ficha = { status: 0 };
  }
  if (ficha.status !== 200) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.erro_ficha')));
    return raiz;
  }
  const f = ficha.json;
  const campos = h(
    'div', { class: 'tipo-resumo' },
    linha(t('tipo_camada.geometria'), f.geometria),
    linha(t('tipo_camada.srid'), f.srid ?? '—'),
    linha(t('tipo_camada.n_feicoes'), f.n_feicoes === null || f.n_feicoes === undefined ? t('tipo_camada.n_feicoes_desconhecido') : f.n_feicoes.toLocaleString('pt-BR')),
    linha(t('tipo_camada.campos'), t('tipo_camada.campos_n', { n: (f.campos || []).length })),
  );
  raiz.append(campos);
  if (!f.servivel || !f.tilejson) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.sem_previa')));
    return raiz;
  }
  const mapaEl = h('div', { class: 'tipo-mapa', 'aria-label': t('tipo_camada.previa_mapa') });
  raiz.append(mapaEl);
  try {
    const rTj = await obter(f.tilejson);
    if (rTj.status !== 200) throw new Error(rTj.json?.mensagem || 'tilejson');
    montarMapaVetor(mapaEl, rTj.json, f);
  } catch {
    mapaEl.replaceWith(h('p', { class: 'fraco' }, t('tipo_camada.erro_previa')));
  }
  return raiz;
}

function montarMapaVetor(container, tileJson, ficha) {
  if (!window.maplibregl) { container.replaceWith(h('p', { class: 'fraco' }, t('tipo_camada.erro_previa'))); return; }
  const fonteId = `plat-${ficha.id}`;
  const layers = Array.isArray(ficha.estilo) ? ficha.estilo : [];
  const map = new window.maplibregl.Map({
    container,
    style: {
      version: 8,
      sources: { [fonteId]: { type: 'vector', tiles: tileJson.tiles, bounds: tileJson.bounds, minzoom: tileJson.minzoom ?? 0, maxzoom: tileJson.maxzoom ?? 20 } },
      layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#eef1ee' } }, ...layers],
    },
    interactive: true,
    attributionControl: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.on('load', () => {
    const b = tileJson.bounds;
    if (Array.isArray(b) && b.length === 4) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { animate: false, padding: 16 });
  });
}

/* ---------- Compartilhamento: URL de serviço para cliente externo ---------- */
const NOME_TOKEN = (item) => `svc-camada:${item.id}`;
const ESCOPOS_TOKEN = (item) => [`camada:ler:${item.id}`];

function montarUrls(raiz, item, tk) {
  limpar(raiz);
  const origem = location.origin;
  const q = (url) => `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(tk)}`;
  const aviso = h('p', { class: 'fraco' });
  const btRenovar = h('button', { type: 'button', class: 'pequeno' }, t('catalogo.servico_renovar'));
  btRenovar.addEventListener('click', async () => {
    btRenovar.disabled = true;
    try {
      const novo = await renovarTokenServico(item, NOME_TOKEN(item), ESCOPOS_TOKEN(item));
      montarUrls(raiz, item, novo);
      raiz.append(h('p', { class: 'fraco' }, t('catalogo.servico_renovado')));
    } catch (e) {
      aviso.textContent = e.message || t('catalogo.servico_erro_renovar');
      raiz.append(aviso);
    } finally {
      btRenovar.disabled = false;
    }
  });
  raiz.append(
    h('p', { class: 'fraco' }, t('tipo_camada.compartilhar_ajuda')),
    linha('WFS · GetCapabilities', campoUrl(q(`${origem}/wfs/${item.id}?SERVICE=WFS&REQUEST=GetCapabilities`))),
    linha('OGC API Features', campoUrl(q(`${origem}/ogc/features/${item.id}/collections`))),
    linha('Esri FeatureServer', campoUrl(q(`${origem}/rest/services/${item.id}/FeatureServer/0/query?where=1%3D1&f=json`))),
    h('p', {}, btRenovar),
    h('p', {}, h('a', { href: '/mapa', class: 'pequeno' }, t('tipo_camada.abrir_no_mapa'))),
  );
}

export async function compartilhar(item) {
  const raiz = h('div', { class: 'tipo-compartilhar' });
  try {
    const tk = await tokenServico(item, NOME_TOKEN(item), ESCOPOS_TOKEN(item));
    montarUrls(raiz, item, tk);
  } catch (e) {
    raiz.append(h('p', { class: 'erro' }, e.message));
  }
  const agolAlvo = h('div', { class: 'tipo-secao-agol' });
  raiz.append(agolAlvo);
  await montarAgol(agolAlvo, item);
  return raiz;
}

/* ---------- Publicar no ArcGIS Online (item L2-08-migracao-agol) ---------- */
const AGOL_ESTADO_ROTULO = {
  nunca_publicado: 'tipo_camada.agol_estado_nunca_publicado',
  pendente: 'tipo_camada.agol_estado_pendente',
  publicando: 'tipo_camada.agol_estado_publicando',
  publicado: 'tipo_camada.agol_estado_publicado',
  erro: 'tipo_camada.agol_estado_erro',
};
const AGOL_ESTADOS_EM_ANDAMENTO = new Set(['pendente', 'publicando']);

function campoTexto(valor, rotulo, opcoes = {}) {
  return h('input', { type: opcoes.senha ? 'password' : 'text', value: valor || '', placeholder: rotulo, autocomplete: 'off', class: 'campo-agol' });
}

async function montarAgol(raiz, item) {
  limpar(raiz);
  raiz.append(h('h5', {}, t('tipo_camada.agol_titulo')));
  if (!item.dados || item.dados.fonte !== 'hospedada') {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.agol_somente_hospedada')));
    return;
  }

  let cred, pub;
  try {
    [cred, pub] = await Promise.all([
      obter('/api/agol/credencial'),
      obter(`/api/agol/publicacoes/${encodeURIComponent(item.id)}`),
    ]);
  } catch {
    raiz.append(h('p', { class: 'erro' }, t('tipo_camada.agol_erro_generico')));
    return;
  }
  if (cred.status !== 200) { raiz.append(h('p', { class: 'erro' }, mensagemDe(cred))); return; }
  const c = cred.json;

  raiz.append(h('p', { class: 'fraco' }, c.configurado
    ? t('tipo_camada.agol_credencial_configurada', { usuario: c.usuario || '—', portal: c.portal || '' })
    : t('tipo_camada.agol_credencial_ausente')));

  const portalEl = campoTexto(c.portal || 'https://www.arcgis.com', t('tipo_camada.agol_portal'));
  const usuarioEl = campoTexto(c.usuario, t('tipo_camada.agol_usuario'));
  const tipoEl = h('select', { class: 'campo-agol' },
    h('option', { value: 'senha' }, t('tipo_camada.agol_tipo_senha')),
    h('option', { value: 'token' }, t('tipo_camada.agol_tipo_token')));
  tipoEl.value = c.tipo || 'senha';
  const credencialEl = campoTexto('', t('tipo_camada.agol_credencial_campo'), { senha: true });
  const rotuloEl = campoTexto(c.rotulo, t('tipo_camada.agol_rotulo'));
  const avisoCred = h('p', { class: 'fraco' });
  const salvarBt = h('button', { type: 'button', class: 'pequeno' }, t('tipo_camada.agol_salvar_credencial'));
  const testarBt = h('button', { type: 'button', class: 'pequeno' }, t('tipo_camada.agol_testar'));

  salvarBt.addEventListener('click', async () => {
    salvarBt.disabled = true;
    try {
      const corpo = { portal: portalEl.value, usuario: usuarioEl.value, rotulo: rotuloEl.value };
      if (credencialEl.value) { corpo.credencial = credencialEl.value; corpo.tipo = tipoEl.value; }
      const r = await alterar('/api/agol/credencial', corpo);
      avisoCred.className = r.status === 200 ? 'fraco' : 'erro';
      avisoCred.textContent = r.status === 200 ? t('tipo_camada.agol_credencial_salva') : mensagemDe(r);
      if (r.status === 200) { credencialEl.value = ''; await montarAgol(raiz, item); }
    } finally {
      salvarBt.disabled = false;
    }
  });

  testarBt.addEventListener('click', async () => {
    testarBt.disabled = true;
    avisoCred.className = 'fraco';
    avisoCred.textContent = '';
    try {
      const r = await enviar('/api/agol/testar');
      if (r.status !== 200 || !r.json.ok) {
        avisoCred.className = 'erro';
        avisoCred.textContent = r.status === 200 ? r.json.mensagem : mensagemDe(r);
        return;
      }
      avisoCred.className = 'fraco';
      avisoCred.textContent = t('tipo_camada.agol_teste_ok', {
        organizacao: r.json.organizacao || '—',
        creditos: r.json.creditos_disponiveis ?? '—',
      });
    } finally {
      testarBt.disabled = false;
    }
  });

  raiz.append(
    h('div', { class: 'campo-linha' }, portalEl),
    h('div', { class: 'campo-linha' }, usuarioEl, tipoEl),
    h('div', { class: 'campo-linha' }, credencialEl, rotuloEl),
    h('div', { class: 'botoes' }, salvarBt, testarBt),
    avisoCred,
  );

  const estado = pub.status === 200 ? pub.json : { estado: 'nunca_publicado' };
  raiz.append(h('p', {}, t(AGOL_ESTADO_ROTULO[estado.estado] || 'tipo_camada.agol_estado_nunca_publicado')));
  if (estado.servico_url) {
    raiz.append(linha(t('tipo_camada.agol_servico_url'),
      h('a', { href: estado.servico_url, target: '_blank', rel: 'noopener noreferrer' }, t('tipo_camada.agol_abrir_no_agol'))));
  }
  if (estado.n_feicoes !== null && estado.n_feicoes !== undefined) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.agol_n_feicoes', { n: estado.n_feicoes })));
  }
  if (estado.mensagem) raiz.append(h('p', { class: 'erro' }, estado.mensagem));
  if (estado.atualizado_em) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.agol_atualizado_em', { data: dataHora(estado.atualizado_em) })));
  }

  const avisoPub = h('p', { class: 'erro' });
  const publicarBt = h(
    'button',
    { type: 'button', class: 'pequeno primario', disabled: !c.configurado || AGOL_ESTADOS_EM_ANDAMENTO.has(estado.estado) },
    t('tipo_camada.agol_publicar'),
  );
  if (!c.configurado) raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.agol_publicar_desabilitado')));
  publicarBt.addEventListener('click', async () => {
    publicarBt.disabled = true;
    try {
      const r = await enviar('/api/agol/publicacoes', { item_id: item.id });
      if (r.status !== 202) { avisoPub.textContent = mensagemDe(r); raiz.append(avisoPub); return; }
      await montarAgol(raiz, item);
    } finally {
      publicarBt.disabled = false;
    }
  });
  raiz.append(h('div', { class: 'botoes' }, publicarBt));
}
