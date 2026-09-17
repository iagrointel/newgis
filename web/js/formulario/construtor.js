/* plat — tela /camadas/{id}/formulario (item L5-03-form-builder): construtor arrasta-e-solta do formulário
   de atributos de uma camada. Paleta = atributos REAIS da camada (`GET /api/camadas/{id}/campos` — o campo
   do desenho tem de casar com um destes, portão cláusula 2); tela = grupos com os campos já colocados,
   cada um com um painel de propriedade curto (rótulo, obrigatório, domínio, condicional, cálculo — as
   duas últimas em expressão da linguagem de `web/js/expressao/avaliador.js`, MESMA que valida no servidor).
   Arrasto por HTML5 Drag and Drop (`web/js/editor/arrasto.js`, item L5-08-editor-arrasto — reaproveitado
   tal e qual, sem copiar a mecânica). "Salvar rascunho" grava uma versão nova; "Publicar" compila a versão
   escolhida em `plat.item.dados` da camada (`app/formulario/servico.py::versao_publicar`) — só DEPOIS de
   publicado o formulário passa a valer na edição web e no PWA de campo (o mesmo desenho, um só motor de
   renderização: `web/js/formulario/motor.js`). */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { anexar, h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { ligarOrigemPaleta, ligarAlvo, ligarOrigemNo } from '../editor/arrasto.js';
import { icone } from '../base/icones.js';

const camadaId = (/^\/camadas\/([0-9a-fA-F-]{36})\/formulario/.exec(location.pathname) || [])[1];
const WIDGETS = ['texto', 'area_texto', 'numero', 'inteiro', 'booleano', 'data', 'selecao'];
const WIDGET_PADRAO = { text: 'texto', integer: 'inteiro', bigint: 'inteiro', 'double precision': 'numero', real: 'numero', boolean: 'booleano' };

await carregar();
const usuario = await exigirSessao();
if (usuario && camadaId) iniciar();
else if (usuario) document.getElementById('aviso').mostrar('URL inválida: /camadas/{id}/formulario', 'erro');
pronto();

function novoId(prefixo) { return `${prefixo}_${Math.random().toString(36).slice(2, 10)}`; }

function desenhoVazio() {
  return { grupos: [{ id: novoId('g'), titulo: 'Grupo 1', campos: [] }] };
}

async function iniciar() {
  montarLayout({ usuario, ativo: null });
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');

  const rCampos = await obter(`/api/camadas/${camadaId}/campos`);
  if (rCampos.status !== 200) { aviso.mostrar(mensagemDe(rCampos), 'erro'); return; }
  const camposCamada = rCampos.json.campos; // [{nome, tipo, alias}]

  const rVersoes = await obter(`/api/camadas/${camadaId}/formulario/versoes`);
  if (rVersoes.status === 404) { aviso.mostrar(mensagemDe(rVersoes), 'erro'); return; }
  let desenho = desenhoVazio();
  let publicadoVersao = null;
  if (rVersoes.status === 200 && rVersoes.json.versoes.length) {
    publicadoVersao = rVersoes.json.formulario.publicado_versao || null;
    const ultima = rVersoes.json.versoes[0].versao; // ORDER BY versao DESC
    const rV = await obter(`/api/camadas/${camadaId}/formulario/versoes/${ultima}`);
    if (rV.status === 200) desenho = rV.json.desenho;
  }

  cabecalho(t('formulario.construtor.titulo') || 'Construtor de formulário');

  const paleta = h('div', { class: 'formulario-paleta' },
    h('h3', {}, t('formulario.construtor.paleta') || 'Atributos da camada'),
    ...camposCamada.map((c) => {
      const chip = h('div', { class: 'formulario-chip', tabindex: '0', dataset: { campo: c.nome } }, c.nome, h('span', { class: 'tipo' }, ` (${c.tipo})`));
      ligarOrigemPaleta(chip, c.nome);
      return chip;
    }));

  const tela = h('div', { class: 'formulario-tela' });
  const status = h('p', { class: 'formulario-status', 'aria-live': 'polite' },
    publicadoVersao ? `${t('formulario.construtor.publicado') || 'Publicado'}: v${publicadoVersao}`
      : (t('formulario.construtor.rascunho') || 'Rascunho, ainda não publicado'));

  function campoPorNome(nome) { return camposCamada.find((c) => c.nome === nome); }

  function removerCampo(grupo, campoId) {
    grupo.campos = grupo.campos.filter((c) => c.id !== campoId);
    redesenhar();
  }

  function campoLinha(grupo, campo) {
    const dominioCsv = (campo.dominio && Array.isArray(campo.dominio.valores)) ? campo.dominio.valores.join(', ') : '';
    const linha = h('div', { class: 'formulario-campo-editor', dataset: { id: campo.id, campo: campo.campo } },
      h('div', { class: 'linha-arraste' },
        h('strong', {}, campo.campo), ' ',
        h('button', { type: 'button', class: 'pequeno perigo', title: 'remover',
          onclick: () => removerCampo(grupo, campo.id) }, icone('fechar', { tamanho: 14 }))),
      h('label', {}, 'Rótulo', h('input', {
        type: 'text', value: campo.rotulo || campo.campo,
        onchange: (ev) => { campo.rotulo = ev.target.value; },
      })),
      h('label', {}, 'Widget', h('select', {
        onchange: (ev) => { campo.widget = ev.target.value; },
      }, ...WIDGETS.map((w) => h('option', { value: w, selected: w === campo.widget }, w)))),
      h('label', { class: 'inline' }, h('input', {
        type: 'checkbox', checked: !!campo.obrigatorio,
        onchange: (ev) => { campo.obrigatorio = ev.target.checked; },
      }), 'Obrigatório'),
      h('label', {}, 'Domínio (lista separada por vírgula)', h('input', {
        type: 'text', value: dominioCsv, placeholder: 'ex.: A, B, C',
        onchange: (ev) => {
          const vs = ev.target.value.split(',').map((v) => v.trim()).filter(Boolean);
          campo.dominio = vs.length ? { valores: vs } : null;
        },
      })),
      h('label', {}, 'Visível quando (expressão, ex.: $categoria == \'A\')', h('input', {
        type: 'text', value: campo.visivel_se || '',
        onchange: (ev) => { campo.visivel_se = ev.target.value || null; },
      })),
      h('label', {}, 'Obrigatório quando (expressão)', h('input', {
        type: 'text', value: campo.obrigatorio_se || '',
        onchange: (ev) => { campo.obrigatorio_se = ev.target.value || null; },
      })),
      h('label', {}, 'Cálculo (expressão sobre outros campos)', h('input', {
        type: 'text', value: campo.calculo || '',
        onchange: (ev) => { campo.calculo = ev.target.value || null; },
      })),
    );
    ligarOrigemNo(linha.querySelector('.linha-arraste'), campo.id);
    return linha;
  }

  function grupoBloco(grupo) {
    const corpo = h('div', { class: 'formulario-grupo-corpo' });
    for (const campo of grupo.campos) corpo.append(campoLinha(grupo, campo));
    const bloco = h('div', { class: 'formulario-grupo-editor', dataset: { grupo: grupo.id } },
      h('div', { class: 'formulario-grupo-cabecalho' },
        h('input', { type: 'text', value: grupo.titulo, class: 'titulo-grupo',
          onchange: (ev) => { grupo.titulo = ev.target.value; } }),
        h('button', { type: 'button', class: 'pequeno perigo', title: 'remover grupo',
          onclick: () => { desenho.grupos = desenho.grupos.filter((g) => g.id !== grupo.id); redesenhar(); } })),
      corpo);
    ligarAlvo(bloco, {
      aceita: (carga) => carga.tipo === 'novo' || carga.tipo === 'no',
      aoSoltar: (carga) => {
        if (carga.tipo === 'novo') {
          const c = campoPorNome(carga.valor);
          if (!c) return false;
          if (grupo.campos.some((x) => x.campo === c.nome)) { aviso.mostrar(`${c.nome} já está no formulário`, 'aviso'); return false; }
          grupo.campos.push({
            id: novoId('c'), campo: c.nome, rotulo: c.alias || c.nome,
            widget: WIDGET_PADRAO[c.tipo] || 'texto', obrigatorio: false, persistido: true,
            dominio: null, visivel_se: null, obrigatorio_se: null, calculo: null,
          });
        } else {
          // mover um campo já colocado (de outro grupo) para este
          for (const g of desenho.grupos) {
            const idx = g.campos.findIndex((c) => c.id === carga.valor);
            if (idx >= 0) { const [c] = g.campos.splice(idx, 1); grupo.campos.push(c); break; }
          }
        }
        redesenhar();
        return true;
      },
    });
    return bloco;
  }

  function redesenhar() {
    limpar(tela);
    anexar(tela, desenho.grupos.map(grupoBloco));
    tela.append(h('button', {
      type: 'button', class: 'pequeno',
      onclick: () => { desenho.grupos.push({ id: novoId('g'), titulo: `Grupo ${desenho.grupos.length + 1}`, campos: [] }); redesenhar(); },
    }, '+ grupo'));
  }
  redesenhar();

  const salvarBt = h('button', { type: 'button', class: 'botao' }, t('formulario.construtor.salvar') || 'Salvar rascunho');
  const publicarBt = h('button', { type: 'button', class: 'botao primario' }, t('formulario.construtor.publicar') || 'Publicar');

  async function salvar() {
    aviso.limpar?.();
    const r = await enviar(`/api/camadas/${camadaId}/formulario/versoes`, { desenho });
    if (r.status !== 201) { aviso.mostrar(mensagemDe(r), 'erro'); return null; }
    aviso.mostrar(`rascunho salvo: v${r.json.versao}`, 'ok');
    return r.json.versao;
  }

  salvarBt.addEventListener('click', () => salvar());
  publicarBt.addEventListener('click', async () => {
    const versao = await salvar();
    if (!versao) return;
    const r = await enviar(`/api/camadas/${camadaId}/formulario/versoes/${versao}/publicar`, {});
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    publicadoVersao = versao;
    limpar(status);
    status.append(`${t('formulario.construtor.publicado') || 'Publicado'}: v${versao}`);
    aviso.mostrar(t('formulario.construtor.publicado_ok') || 'formulário publicado — já vale na edição e no campo', 'ok');
  });

  anexar(principal, [
    status,
    h('div', { class: 'formulario-construtor' }, paleta, tela),
    h('div', { class: 'linha-botoes' }, salvarBt, publicarBt),
  ]);
}
