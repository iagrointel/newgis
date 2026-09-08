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
import { PALETA_PAGINAS } from './paleta_paginas.js';
import { novoDocumento } from './documento.js';
import { montarPainelDados } from '../app/painel_dados.js';
import { montarPainelAcoes } from '../app/painel_acoes.js';
import { REGISTRO as REGISTRO_WIDGETS } from '../widgets/registro.js';

/* item `app` ganha a paleta de PÁGINAS E LAYOUT (L5-01-a: página, cabeçalho, menu, janela, ...); os demais
   tipos de construtor continuam com a paleta de layout comum do L5-08, sem página nenhuma dentro deles. */
function paletaDoTipo(tipo) { return tipo === 'app' ? PALETA_PAGINAS : PALETA_LAYOUT; }

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
  const linkExecutar = documento.tipo === 'app' && id
    ? h('a', { id: 'executar', class: 'pequeno', href: `/executar?item=${id}`, target: '_blank', rel: 'noopener' }, 'Executar')
    : null;
  const linkPublicar = documento.tipo === 'app' && id
    ? h('a', { id: 'abrir-aplicativo', class: 'pequeno', href: `/aplicativo?item=${id}`, target: '_blank', rel: 'noopener' }, 'Abrir aplicativo')
    : null;
  principal.append(h('div', { class: 'linha-ferramentas' }, btSalvar, estado, linkExecutar, linkPublicar), alvo);

  /* item L5-07: painel de fontes, vistas e mensagens (só para `app`); as coleções vivem fora do editor de nós e
     entram no corpo na gravação; erro do modelo bloqueia o Salvar com a mensagem na tela */
  let painel = null;
  const colecoes = { fontes: documento.corpo.fontes || [], vistas: documento.corpo.vistas || [], mensagens: documento.corpo.mensagens || [] };
  let editor = null;
  editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: paletaDoTipo(documento.tipo),
    aoMudar: () => { estado.textContent = 'alterações não gravadas'; painel?.redesenhar(); },
    /* item L5-01-e: painel "Ações" no fim das propriedades de cada WIDGET do app (tipos do registro do motor) —
       gatilho → alvo → ação → parâmetros; escreve nas mesmas `colecoes.mensagens` do painel de dados */
    extensaoPropriedades: ({ no, raiz }) => {
      if (documento.tipo !== 'app' || !REGISTRO_WIDGETS.has(no.tipo)) return;
      montarPainelAcoes({
        raiz, no, colecoes, nosAtuais: () => editor.documento().corpo.nos,
        aoMudar: () => { estado.textContent = 'alterações não gravadas'; painel?.redesenhar(); },
      });
    },
  });
  if (documento.tipo === 'app') {
    // recolhido por padrão e dentro da coluna lateral do editor: a altura da página continua a da paleta (o
    // arrasto da paleta é medido por coordenadas e o navegador só rola a paleta para a vista quando nada abaixo
    // da grade alonga a página)
    const raizDados = h('details', { id: 'painel-dados', class: 'painel-dados' }, h('summary', {}, 'Dados e mensagens'));
    (alvo.querySelector('.editor-lado') || principal).append(raizDados);
    painel = montarPainelDados({
      raiz: raizDados, colecoes, nosAtuais: () => editor.documento().corpo.nos,
      aoMudar: ({ erros }) => { estado.textContent = erros.length ? 'alterações não gravadas (modelo com erro)' : 'alterações não gravadas'; },
    });
  }

  btSalvar.addEventListener('click', async () => {
    if (!item) return;
    const d = editor.documento();
    const corpo = painel ? { ...d.corpo, ...painel.colecoes() } : d.corpo;
    if (painel) {
      const { erros } = painel.validar();
      if (erros.length) { estado.textContent = 'não gravado: modelo com erro'; aviso.mostrar(`${erros.length} erro(s) em fontes/vistas/mensagens: ${erros[0].erro}`, 'erro'); return; }
    }
    btSalvar.disabled = true;
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: item.tipo, esquema_versao: painel ? Math.max(3, d.esquema_versao || 2) : d.esquema_versao, corpo },
      versao_atual: item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status !== 200) { estado.textContent = 'não gravado'; aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    aviso.limpar?.();
    estado.textContent = `gravado (versão ${item.versao_atual})`;
  });
}
