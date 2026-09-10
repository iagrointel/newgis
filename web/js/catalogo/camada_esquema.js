/* plat — tela /construtor-camada (item L5-31-construtor-de-camada-esquema): monta a lista de campos de uma
   camada vazia por arrasto (paleta de tipos -> lista) ou por clique (mesma paleta, alternativa de teclado —
   as duas produzem exatamente o mesmo objeto de campo, sem biblioteca de drag-and-drop: só Drag and Drop API
   nativa do HTML5, o mesmo princípio de "0 byte" do editor de arrasto do L5-08). Ao criar, mostra os campos
   de volta no formato `fields` que a API devolve (GET /api/camadas/{id}/campos) — é a prova visual de que
   alias e domínio já estão lá, sem reconfigurar nada. */
import { enviar, mensagemDe, obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import '../base/componentes.js';
import { carregar } from '../base/i18n.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

await carregar();

const TIPOS = [
  { tipo: 'text', rotulo: 'Texto' },
  { tipo: 'integer', rotulo: 'Número inteiro' },
  { tipo: 'bigint', rotulo: 'Número inteiro longo' },
  { tipo: 'double precision', rotulo: 'Número decimal' },
  { tipo: 'boolean', rotulo: 'Verdadeiro/falso' },
  { tipo: 'date', rotulo: 'Data' },
  { tipo: 'time', rotulo: 'Hora' },
  { tipo: 'timestamp with time zone', rotulo: 'Data e hora' },
];
const ROTULO_DE = Object.fromEntries(TIPOS.map((t) => [t.tipo, t.rotulo]));

let campos = []; // {id, tipo, nome, alias, tamanho, obrigatorio, padrao, dominioTexto, indice}
let proximoId = 1;

const usuario = await exigirSessao({ privilegio: 'conteudo.publicar_camada' });
if (usuario) iniciar();
pronto();

function iniciar() {
  montarLayout({ usuario, ativo: '/construtor-camada' });
  cabecalho('Construtor de camada');
  montarPaleta();
  renderizarCampos();
  document.getElementById('criar-camada').addEventListener('click', criar);
}

function montarPaleta() {
  const paleta = document.getElementById('paleta');
  for (const { tipo, rotulo } of TIPOS) {
    const chip = h('li', {}, h('button', {
      type: 'button',
      class: 'chip-tipo',
      draggable: 'true',
      dataset: { tipo },
      title: `arraste até a lista de campos, ou clique para adicionar um campo do tipo ${rotulo.toLowerCase()}`,
      onclick: () => adicionarCampo(tipo),
      ondragstart: (e) => e.dataTransfer.setData('text/plain', tipo),
    }, rotulo));
    paleta.append(chip);
  }
  const zona = document.getElementById('zona-campos');
  zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('sobre-arraste'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('sobre-arraste'));
  zona.addEventListener('drop', (e) => {
    e.preventDefault();
    zona.classList.remove('sobre-arraste');
    const tipo = e.dataTransfer.getData('text/plain');
    if (ROTULO_DE[tipo]) adicionarCampo(tipo);
  });
}

function adicionarCampo(tipo) {
  campos.push({
    id: proximoId++, tipo, nome: '', alias: '', tamanho: '', obrigatorio: false, padrao: '',
    dominioTexto: '', indice: false,
  });
  renderizarCampos();
  const ultima = document.querySelector('#zona-campos .campo-linha:last-child input[data-campo="nome"]');
  if (ultima) ultima.focus();
}

function removerCampo(id) {
  campos = campos.filter((c) => c.id !== id);
  renderizarCampos();
}

function renderizarCampos() {
  const zona = document.getElementById('zona-campos');
  limpar(zona);
  document.getElementById('zona-vazia').hidden = campos.length > 0;
  for (const c of campos) zona.append(linhaCampo(c));
}

function linhaCampo(c) {
  const atualizar = (chave, valor) => { c[chave] = valor; };
  return h('li', { class: 'campo-linha' },
    h('span', { class: 'campo-tipo-rotulo' }, ROTULO_DE[c.tipo] || c.tipo),
    h('label', {}, 'nome',
      h('input', {
        type: 'text', required: true, maxLength: 250, value: c.nome, dataset: { campo: 'nome' },
        oninput: (e) => atualizar('nome', e.target.value),
      })),
    h('label', {}, 'alias (rótulo de tela)',
      h('input', {
        type: 'text', maxLength: 250, value: c.alias,
        oninput: (e) => atualizar('alias', e.target.value),
      })),
    c.tipo === 'text'
      ? h('label', {}, 'tamanho',
          h('input', {
            type: 'number', min: 1, max: 10000, value: c.tamanho,
            oninput: (e) => atualizar('tamanho', e.target.value),
          }))
      : h('span'),
    h('label', {}, 'valor padrão',
      h('input', {
        type: 'text', maxLength: 2000, value: c.padrao,
        oninput: (e) => atualizar('padrao', e.target.value),
      })),
    h('label', {}, 'domínio (código:rótulo, código:rótulo)',
      h('input', {
        type: 'text', value: c.dominioTexto, placeholder: 'ex.: 1:Ativo, 2:Inativo',
        oninput: (e) => atualizar('dominioTexto', e.target.value),
      })),
    h('label', {},
      h('input', {
        type: 'checkbox', checked: c.obrigatorio,
        onchange: (e) => atualizar('obrigatorio', e.target.checked),
      }), ' obrigatório'),
    h('label', {},
      h('input', {
        type: 'checkbox', checked: c.indice,
        onchange: (e) => atualizar('indice', e.target.checked),
      }), ' índice'),
    h('button', {
      type: 'button', class: 'remover-campo', onclick: () => removerCampo(c.id),
    }, 'remover'),
  );
}

function dominioDe(texto) {
  const partes = (texto || '').split(',').map((p) => p.trim()).filter(Boolean);
  if (!partes.length) return null;
  return partes.map((p) => {
    const [codigo, ...resto] = p.split(':');
    return { codigo: codigo.trim(), rotulo: (resto.join(':').trim() || codigo.trim()) };
  });
}

function corpoCriacao() {
  return {
    titulo: document.getElementById('camada-titulo').value.trim(),
    geometria: document.getElementById('camada-geometria').value,
    srid: Number(document.getElementById('camada-srid').value),
    campos: campos.map((c) => ({
      nome: c.nome,
      tipo: c.tipo,
      tamanho: c.tamanho ? Number(c.tamanho) : null,
      alias: c.alias || null,
      obrigatorio: c.obrigatorio,
      padrao: c.padrao || null,
      dominio: dominioDe(c.dominioTexto),
      indice: c.indice,
    })),
  };
}

async function criar() {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const titulo = document.getElementById('camada-titulo').value.trim();
  if (!titulo) { aviso.erro('dê um título para a camada'); return; }
  if (!campos.length) { aviso.erro('adicione ao menos um campo'); return; }
  if (campos.some((c) => !c.nome.trim())) { aviso.erro('todo campo precisa de um nome'); return; }

  const botao = document.getElementById('criar-camada');
  botao.disabled = true;
  try {
    const r = await enviar('/api/camadas/esquema', corpoCriacao());
    if (r.status !== 201) { aviso.erro(mensagemDe(r)); return; }
    aviso.ok(`camada criada: ${r.json.campos} campo(s)` + (r.json.avisos.length
      ? ` (${r.json.avisos.length} nome(s) normalizado(s) automaticamente)` : ''));
    await mostrarResultado(r.json.item_id);
  } finally {
    botao.disabled = false;
  }
}

async function mostrarResultado(itemId) {
  const r = await obter(`/api/camadas/${itemId}/campos`);
  if (r.status !== 200) return;
  const cartao = document.getElementById('resultado-cartao');
  const corpo = document.getElementById('resultado-corpo');
  limpar(corpo);
  document.getElementById('resultado-resumo').textContent =
    `${r.json.fields.length} campo(s) já disponíveis no formato FeatureServer (id ${itemId}).`;
  for (const f of r.json.fields) {
    corpo.append(h('tr', {},
      h('td', {}, h('code', {}, f.name)),
      h('td', {}, f.alias),
      h('td', {}, f.sqlType),
      h('td', {}, f.nullable ? 'não' : 'sim'),
      h('td', {}, f.domain ? f.domain.codedValues.map((v) => `${v.codigo}: ${v.rotulo}`).join('; ') : '—'),
    ));
  }
  cartao.hidden = false;
}
