/* plat — tela /versoes (item L2-13-a): ramos de versão de uma camada, reconciliação e resolução de
   conflito com DIFF LADO A LADO.

   Por que uma tela própria e não um painel dentro do mapa: reconciliar é uma operação sobre a camada
   inteira, com uma lista que pode ter dezenas de feições e três valores por campo. Numa gaveta do mapa
   isso vira rolagem; aqui a comparação cabe na tela e cada linha mostra base, ramo e padrão lado a
   lado, na mesma ordem em todas as feições. A edição da geometria continua no mapa: aqui só se DECIDE.

   O diff é montado do que a API já devolve em `detalhe.atributos[campo] = {base, ramo, padrao,
   mudou_no_ramo, mudou_no_padrao}` — a tela não recalcula diferença nenhuma, para não haver duas
   respostas possíveis para "o que mudou". */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

await carregar();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario });
  await iniciar();
}
pronto();

const aviso = () => document.getElementById('aviso');
const selCamada = () => document.getElementById('versoes-camada');
const selRamo = () => document.getElementById('versoes-ramo');
const alvo = () => document.getElementById('conflitos');
const resumo = () => document.getElementById('versoes-resumo');

function falhar(resp) {
  aviso().setAttribute('tipo', 'erro');
  aviso().textContent = mensagemDe(resp);
}

function informar(texto) {
  aviso().setAttribute('tipo', 'informacao');
  aviso().textContent = texto;
}

async function iniciar() {
  const r = await obter('/api/mapa/camadas');
  const camadas = r.status === 200 ? (r.json.camadas || []) : [];
  const opcoes = camadas.map((c) => h('option', { value: c.id }, c.titulo || c.id));
  limpar(selCamada());
  selCamada().append(...opcoes);
  const pedida = new URLSearchParams(location.search).get('camada');
  if (pedida) selCamada().value = pedida;
  selCamada().addEventListener('change', carregarRamos);
  selRamo().addEventListener('change', () => mostrarConflitos([]));
  document.getElementById('btn-reconciliar').addEventListener('click', reconciliar);
  document.getElementById('btn-publicar').addEventListener('click', publicar);
  await carregarRamos();
}

async function carregarRamos() {
  limpar(selRamo());
  limpar(alvo());
  resumo().textContent = '';
  const camada = selCamada().value;
  if (!camada) return;
  const r = await obter(`/api/camadas/${camada}/versoes`);
  if (r.status !== 200) {
    selRamo().disabled = true;
    return falhar(r);
  }
  selRamo().disabled = false;
  selRamo().append(...r.json.map((v) => h('option', { value: v.nome }, `${v.nome} (${v.acesso})`)));
  if (!r.json.length) informar(t('versoes.sem_ramo'));
}

async function reconciliar() {
  const camada = selCamada().value;
  const ramo = selRamo().value;
  if (!camada || !ramo) return;
  const r = await enviar(`/api/camadas/${camada}/versoes/${encodeURIComponent(ramo)}/reconciliar`, {});
  if (r.status !== 200) return falhar(r);
  resumo().textContent = t('versoes.resumo')
    .replace('{conflitos}', String(r.json.conflitos.length))
    .replace('{pendentes}', String(r.json.pendentes));
  mostrarConflitos(r.json.conflitos);
}

async function publicar() {
  const camada = selCamada().value;
  const ramo = selRamo().value;
  if (!camada || !ramo) return;
  const r = await enviar(`/api/camadas/${camada}/versoes/${encodeURIComponent(ramo)}/publicar`, {});
  if (r.status !== 200) return falhar(r);
  informar(t('versoes.publicado'));
  limpar(alvo());
  await carregarRamos();
}

function texto(valor) {
  if (valor === null || valor === undefined) return '—';
  return String(valor);
}

function linhaDiff(campo, valores) {
  return h(
    'tr', { class: 'diff-linha', 'data-campo': campo },
    h('th', { scope: 'row' }, campo),
    h('td', { class: 'valor-base' }, texto(valores.base)),
    h('td', { class: `valor-ramo${valores.mudou_no_ramo ? ' mudou' : ''}` }, texto(valores.ramo)),
    h('td', { class: `valor-padrao${valores.mudou_no_padrao ? ' mudou' : ''}` }, texto(valores.padrao)),
  );
}

function blocoGeometria(geometria) {
  if (!geometria) return null;
  return h(
    'tr', { class: 'diff-linha', 'data-campo': 'geometria' },
    h('th', { scope: 'row' }, t('versoes.geometria')),
    h('td', { class: 'valor-base' }, geometria.base ? t('versoes.geometria_ha') : '—'),
    h('td', { class: `valor-ramo${geometria.mudou_no_ramo ? ' mudou' : ''}` },
      geometria.mudou_no_ramo ? t('versoes.geometria_mudou') : t('versoes.geometria_igual')),
    h('td', { class: `valor-padrao${geometria.mudou_no_padrao ? ' mudou' : ''}` },
      geometria.mudou_no_padrao ? t('versoes.geometria_mudou') : t('versoes.geometria_igual')),
  );
}

function mostrarConflitos(conflitos) {
  limpar(alvo());
  if (!conflitos.length) {
    alvo().append(h('p', {}, t('versoes.sem_conflito')));
    return;
  }
  for (const c of conflitos) alvo().append(cartaoConflito(c));
}

function cartaoConflito(conflito) {
  const atributos = conflito.detalhe.atributos || {};
  const campos = Object.keys(atributos);
  const corpo = h('tbody', {}, ...campos.map((campo) => linhaDiff(campo, atributos[campo])));
  const linhaGeom = blocoGeometria(conflito.detalhe.geometria);
  if (linhaGeom) corpo.append(linhaGeom);

  const manual = h('div', { class: 'manual', hidden: true });
  for (const campo of campos) {
    const entrada = h('input', { type: 'text', id: `manual-${conflito.globalid}-${campo}`,
                                 'data-campo': campo, value: texto(atributos[campo].ramo) });
    manual.append(h('label', { for: entrada.id }, campo), entrada);
  }

  const nome = `decisao-${conflito.globalid}`;
  const radios = ['ramo', 'padrao', 'manual'].map((valor) => {
    const input = h('input', { type: 'radio', name: nome, value: valor, id: `${nome}-${valor}` });
    input.addEventListener('change', () => { manual.hidden = valor !== 'manual'; });
    return h('span', {}, input, h('label', { for: input.id }, t(`versoes.decisao_${valor}`)));
  });

  const aplicar = h('button', { type: 'button', class: 'aplicar' }, t('versoes.aplicar'));
  aplicar.addEventListener('click', () => resolver(conflito, nome, manual, aplicar));

  return h(
    'article', { class: 'conflito', 'data-globalid': conflito.globalid, 'data-tipo': conflito.tipo },
    h('h2', {}, `${t('versoes.feicao')} ${conflito.globalid} · ${conflito.tipo}`),
    h('table', { class: 'diff' },
      h('thead', {}, h('tr', {},
        h('th', { scope: 'col' }, t('versoes.campo')),
        h('th', { scope: 'col' }, t('versoes.base')),
        h('th', { scope: 'col' }, t('versoes.ramo_coluna')),
        h('th', { scope: 'col' }, t('versoes.padrao_coluna')))),
      corpo),
    h('div', { class: 'decisao' }, ...radios, aplicar),
    manual,
  );
}

async function resolver(conflito, nomeRadio, manual, botao) {
  const escolhido = document.querySelector(`input[name="${nomeRadio}"]:checked`);
  if (!escolhido) return informar(t('versoes.escolha'));
  const corpo = { decisao: escolhido.value };
  if (escolhido.value === 'manual') {
    corpo.atributos = {};
    for (const entrada of manual.querySelectorAll('input[data-campo]')) {
      const bruto = entrada.value;
      const numero = Number(bruto);
      corpo.atributos[entrada.dataset.campo] =
        bruto.trim() !== '' && !Number.isNaN(numero) ? numero : bruto;
    }
  }
  const camada = selCamada().value;
  const ramo = selRamo().value;
  const url = `/api/camadas/${camada}/versoes/${encodeURIComponent(ramo)}`
            + `/conflitos/${conflito.globalid}/resolver`;
  const r = await enviar(url, corpo);
  if (r.status !== 200) return falhar(r);
  botao.closest('.conflito').dataset.resolvido = escolhido.value;
  botao.disabled = true;
  informar(t('versoes.resolvido'));
}
