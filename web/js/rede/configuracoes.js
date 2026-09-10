/* plat — tela /redes/configuracoes (item L4-02-e-configuracoes-de-tracado): a lista das configurações de
   traçado de uma rede (as que vêm com o pacote e as que a equipe salvou) e o FORMULÁRIO que cria uma nova:
   código, nome, tipo de traçado, tipo de resultado, barreiras de condição (atributo, operador, valor) e
   funções sobre atributo (soma, contagem, mínimo, máximo, média). A tela não traça: ela salva o pedido que
   POST /api/rede/{id}/tracar vai executar quando receber `config_id`. */
import { obter, enviar, apagar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const TIPOS = ['conectado', 'subrede', 'montante', 'jusante'];
const RESULTADOS = ['elementos', 'geometria', 'conectividade'];
const OPERADORES = ['=', '<>', '>', '>=', '<', '<=', 'contem', 'comeca_com', 'existe', 'nao_existe'];
const FUNCOES = ['soma', 'contagem', 'minimo', 'maximo', 'media'];

await carregar();
const usuario = await exigirSessao({ privilegio: 'rede.editar' });
if (usuario) iniciar();
pronto();

async function redes() {
  const r = await obter('/api/rede?limite=200');
  return r.status === 200 ? (r.json.itens || []) : [];
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/configuracoes' });
  cabecalho(t('configtracado.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const lista = await redes();

  const selRede = h('select', { id: 'rede', 'aria-label': t('configtracado.rede') },
    h('option', { value: '' }, t('configtracado.escolha')),
    ...lista.map((i) => h('option', { value: i.id }, i.nome)));
  const tabela = h('div', { id: 'configuracoes', class: 'resultado' });
  const formulario = h('form', { id: 'formulario', hidden: true });

  selRede.addEventListener('change', () => { formulario.hidden = !selRede.value; desenhar(); });

  async function desenhar() {
    limpar(tabela);
    if (!selRede.value) return;
    const r = await obter(`/api/rede/${selRede.value}/config_tracado?limite=500`);
    if (r.status !== 200) { aviso.mostrar(t('configtracado.falhou'), 'erro'); return; }
    const itens = r.json.itens || [];
    tabela.dataset.total = String(itens.length);
    if (!itens.length) { tabela.append(h('p', { class: 'ajuda' }, t('configtracado.vazia'))); return; }
    tabela.append(h('table', { class: 'grade' },
      h('thead', {}, h('tr', {},
        h('th', {}, t('configtracado.codigo')), h('th', {}, t('configtracado.nome')),
        h('th', {}, t('configtracado.tipo')), h('th', {}, t('configtracado.origem')),
        h('th', {}, t('configtracado.funcoes')), h('th', {}, t('configtracado.acoes')))),
      h('tbody', {}, ...itens.map((c) => h('tr', { 'data-config': c.id, 'data-codigo': c.codigo },
        h('td', { class: 'codigo' }, c.codigo),
        h('td', {}, c.nome),
        h('td', {}, c.tipo),
        h('td', { class: 'origem' }, c.origem),
        h('td', { class: 'funcoes' },
          String(((c.config || {}).funcoes || []).map((f) => f.codigo).join(', ') || '—')),
        h('td', {}, h('button', {
          type: 'button', class: 'apagar', 'data-apagar': c.id,
          onclick: () => remover(c),
        }, t('configtracado.apagar'))))))));
  }

  async function remover(c) {
    const r = await apagar(`/api/rede/${selRede.value}/config_tracado/${c.id}`);
    if (r.status !== 204) { aviso.mostrar(r.json.mensagem || t('configtracado.falhou'), 'erro'); return; }
    aviso.mostrar(t('configtracado.apagada'), 'ok');
    await desenhar();
  }

  const campoCodigo = h('input', { id: 'codigo', name: 'codigo', required: true, maxlength: '63' });
  const campoNome = h('input', { id: 'nome', name: 'nome', required: true, maxlength: '200' });
  const selTipo = h('select', { id: 'tipo', name: 'tipo' }, ...TIPOS.map((v) => h('option', { value: v }, v)));
  const selResultado = h('select', { id: 'tipo_resultado', name: 'tipo_resultado' },
    ...RESULTADOS.map((v) => h('option', { value: v }, v)));
  const barAtributo = h('input', { id: 'barreira_atributo', maxlength: '63' });
  const barOperador = h('select', { id: 'barreira_operador' },
    ...OPERADORES.map((v) => h('option', { value: v }, v)));
  const barValor = h('input', { id: 'barreira_valor', maxlength: '200' });
  const fnFuncao = h('select', { id: 'funcao', name: 'funcao' },
    h('option', { value: '' }, t('configtracado.sem_funcao')),
    ...FUNCOES.map((v) => h('option', { value: v }, v)));
  const fnAtributo = h('input', { id: 'funcao_atributo', maxlength: '63' });

  formulario.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const config = { tipo_resultado: selResultado.value };
    if (barAtributo.value.trim()) {
      const cond = { atributo: barAtributo.value.trim(), operador: barOperador.value };
      if (!['existe', 'nao_existe'].includes(barOperador.value)) cond.valor = barValor.value;
      config.barreiras_condicao = [cond];
    }
    if (fnFuncao.value) {
      const f = { codigo: fnFuncao.value, nome: fnFuncao.value, funcao: fnFuncao.value };
      if (fnAtributo.value.trim()) f.atributo = fnAtributo.value.trim();
      config.funcoes = [f];
    }
    const r = await enviar(`/api/rede/${selRede.value}/config_tracado`, {
      codigo: campoCodigo.value.trim(), nome: campoNome.value.trim(), tipo: selTipo.value, config,
    });
    if (r.status !== 201) { aviso.mostrar(r.json.mensagem || t('configtracado.falhou'), 'erro'); return; }
    aviso.mostrar(t('configtracado.salva'), 'ok');
    campoCodigo.value = ''; campoNome.value = ''; barAtributo.value = ''; barValor.value = '';
    fnAtributo.value = ''; fnFuncao.value = '';
    await desenhar();
  });

  formulario.append(
    h('h2', {}, t('configtracado.nova')),
    h('p', { class: 'ajuda' }, t('configtracado.ajuda')),
    h('label', { for: 'codigo' }, t('configtracado.codigo')), campoCodigo,
    h('label', { for: 'nome' }, t('configtracado.nome')), campoNome,
    h('label', { for: 'tipo' }, t('configtracado.tipo')), selTipo,
    h('label', { for: 'tipo_resultado' }, t('configtracado.resultado')), selResultado,
    h('fieldset', {},
      h('legend', {}, t('configtracado.barreira')),
      h('label', { for: 'barreira_atributo' }, t('configtracado.atributo')), barAtributo,
      h('label', { for: 'barreira_operador' }, t('configtracado.operador')), barOperador,
      h('label', { for: 'barreira_valor' }, t('configtracado.valor')), barValor),
    h('fieldset', {},
      h('legend', {}, t('configtracado.funcao')),
      h('label', { for: 'funcao' }, t('configtracado.funcao')), fnFuncao,
      h('label', { for: 'funcao_atributo' }, t('configtracado.atributo')), fnAtributo),
    h('button', { type: 'submit', id: 'salvar' }, t('configtracado.salvar')));

  principal.append(h('p', { class: 'ajuda' }, t('configtracado.ajuda')),
    h('label', { for: 'rede' }, t('configtracado.rede')), selRede, tabela, formulario);
}
