/* plat — tela /construtor (item L5-08-editor-arrasto): abre um item de tipo `app` ou `painel` do catálogo,
   monta o editor de arrasto sobre o documento do item (L5-05) e grava com PATCH /api/itens/{id}.

   A tela é fina de propósito: tudo o que edita documento está em web/js/editor/{documento,editor,arrasto,
   esquema,paleta}.js, que é o que os outros doze construtores da linha vão reusar. Aqui só há: sessão,
   carregar, salvar e o aviso de conflito de versão (409, D12: versão otimista).
   Idioma: textos em português literal nesta tela; a passagem para o dicionário é o item
   L5-12-acessibilidade-i18n-construtores, que cobre os construtores todos de uma vez. */
import { obter, chamar, mensagemDe } from '../base/api.js';
import { h } from '../base/dom.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { criarEditor } from './editor.js';
import { PALETA_LAYOUT } from './paleta.js';
import { novoDocumento } from './documento.js';

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/construtor' });
  const principal = document.getElementById('principal');
  const id = new URLSearchParams(location.search).get('item');
  const aviso = document.getElementById('aviso');
  const h1 = document.querySelector('main > h1');

  let item = null;
  let documento = novoDocumento('app');
  if (id) {
    const r = await obter(`/api/itens/${id}`);
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    const dados = item.dados || {};
    if (dados.corpo) documento = { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } };
    else documento = novoDocumento(item.tipo);
    h1.textContent = item.titulo;
    document.title = `${item.titulo} · construtor · plat`;
  }

  const alvo = h('div', { id: 'editor-raiz' });
  const btSalvar = h('button', { type: 'button', id: 'salvar', class: 'primario', disabled: !id }, 'Salvar');
  const estado = h('span', { id: 'estado-salvo', class: 'estado' }, id ? 'sem alterações' : 'sem item: passe ?item=<id>');
  principal.append(h('div', { class: 'linha-ferramentas' }, btSalvar, estado), alvo);

  const editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: PALETA_LAYOUT,
    aoMudar: () => { estado.textContent = 'alterações não gravadas'; },
  });

  btSalvar.addEventListener('click', async () => {
    if (!item) return;
    btSalvar.disabled = true;
    const d = editor.documento();
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: item.tipo, esquema_versao: d.esquema_versao, corpo: d.corpo },
      versao_atual: item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status !== 200) { estado.textContent = 'não gravado'; aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    aviso.limpar?.();
    estado.textContent = `gravado (versão ${item.versao_atual})`;
  });
}
