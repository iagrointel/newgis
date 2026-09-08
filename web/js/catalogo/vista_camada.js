/* plat — tela /vista-de-camada (item L5-32-vistas-de-camada): monta a definição de uma vista de camada
   (filtro, campos ocultos, só leitura) e a cria. Arrastar um campo até a área "ocultos" é a mesma Drag and
   Drop API nativa do HTML5 usada no construtor de camada do L5-31 (sem biblioteca); clicar no campo faz o
   mesmo, para quem não usa mouse. Depois de criada, a tela mostra o que a vista PUBLICA — lido da própria
   vista (GET /api/vistas/{id}), não da camada-mãe: se um campo oculto aparecesse aqui, apareceria na
   consulta também. */
import { enviar, mensagemDe, obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import '../base/componentes.js';
import { carregar } from '../base/i18n.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

await carregar();

let camadas = [];
let campos = []; // {nome, tipo, oculto}

const usuario = await exigirSessao({ privilegio: 'conteudo.publicar_camada' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/vista-de-camada' });
  cabecalho('Vista de camada');
  ligarZonas();
  document.getElementById('criar-vista').addEventListener('click', criar);
  document.getElementById('vista-camada').addEventListener('change', carregarCampos);
  await carregarCamadas();
}

async function carregarCamadas() {
  const r = await obter('/api/itens?tipo=camada_vetorial&limite=200');
  if (r.status !== 200) { document.getElementById('aviso').erro(mensagemDe(r)); return; }
  camadas = r.json.itens || r.json.resultados || [];
  const select = document.getElementById('vista-camada');
  limpar(select);
  for (const c of camadas) select.append(h('option', { value: c.id }, c.titulo));
  if (camadas.length) await carregarCampos();
}

async function carregarCampos() {
  const id = document.getElementById('vista-camada').value;
  if (!id) return;
  const r = await obter(`/api/camadas/${id}/campos`);
  if (r.status !== 200) { document.getElementById('aviso').erro(mensagemDe(r)); return; }
  campos = r.json.fields.map((f) => ({ nome: f.name, tipo: f.sqlType, oculto: false }));
  renderizar();
}

function ligarZonas() {
  for (const [id, oculto] of [['zona-visiveis', false], ['zona-ocultos', true]]) {
    const zona = document.getElementById(id);
    zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('sobre-arraste'); });
    zona.addEventListener('dragleave', () => zona.classList.remove('sobre-arraste'));
    zona.addEventListener('drop', (e) => {
      e.preventDefault();
      zona.classList.remove('sobre-arraste');
      mover(e.dataTransfer.getData('text/plain'), oculto);
    });
  }
}

function mover(nome, oculto) {
  const campo = campos.find((c) => c.nome === nome);
  if (!campo) return;
  campo.oculto = oculto;
  renderizar();
}

function renderizar() {
  const visiveis = document.getElementById('zona-visiveis');
  const ocultos = document.getElementById('zona-ocultos');
  limpar(visiveis);
  limpar(ocultos);
  for (const campo of campos) {
    const destino = campo.oculto ? ocultos : visiveis;
    destino.append(h('li', { class: 'campo-linha' }, h('button', {
      type: 'button',
      class: 'chip-tipo',
      draggable: 'true',
      dataset: { campo: campo.nome, oculto: String(campo.oculto) },
      title: campo.oculto ? 'clique para publicar este campo de novo' : 'clique para ocultar este campo',
      onclick: () => mover(campo.nome, !campo.oculto),
      ondragstart: (e) => e.dataTransfer.setData('text/plain', campo.nome),
    }, `${campo.nome} (${campo.tipo})`)));
  }
  document.getElementById('ocultos-vazio').hidden = campos.some((c) => c.oculto);
}

async function criar() {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const camadaId = document.getElementById('vista-camada').value;
  const titulo = document.getElementById('vista-titulo').value.trim();
  if (!camadaId) { aviso.erro('escolha a camada-mãe'); return; }
  if (!titulo) { aviso.erro('dê um título para a vista'); return; }

  const botao = document.getElementById('criar-vista');
  botao.disabled = true;
  try {
    const r = await enviar(`/api/camadas/${camadaId}/vistas`, {
      titulo,
      filtro: document.getElementById('vista-filtro').value.trim() || null,
      campos_ocultos: campos.filter((c) => c.oculto).map((c) => c.nome),
      somente_leitura: document.getElementById('vista-somente-leitura').checked,
    });
    if (r.status !== 201) { aviso.erro(mensagemDe(r)); return; }
    aviso.ok(`vista criada: ${r.json.campos_ocultos.length} campo(s) oculto(s)`);
    await mostrarResultado(r.json.item_id);
  } finally {
    botao.disabled = false;
  }
}

async function mostrarResultado(itemId) {
  const r = await obter(`/api/vistas/${itemId}`);
  if (r.status !== 200) return;
  const corpo = document.getElementById('resultado-corpo');
  limpar(corpo);
  for (const campo of r.json.campos) {
    corpo.append(h('tr', {}, h('td', {}, h('code', {}, campo.nome)), h('td', {}, campo.tipo)));
  }
  document.getElementById('resultado-resumo').textContent =
    `${r.json.campos.length} campo(s) publicados, ${r.json.campos_ocultos.length} oculto(s)`
    + (r.json.filtro ? `, filtro ${r.json.filtro}` : '')
    + (r.json.somente_leitura ? ', somente leitura' : ', editável');
  document.getElementById('resultado-servico').textContent =
    `serviço: /rest/services/${itemId}/FeatureServer/0`;
  document.getElementById('resultado-cartao').hidden = false;
}
