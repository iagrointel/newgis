/* plat — tela /construtor (item L5-08-editor-arrasto): abre um item de tipo `app` ou `painel` do catálogo,
   monta o editor de arrasto sobre o documento do item (L5-05) e grava com PATCH /api/itens/{id}; publica a
   versão gravada com POST /api/itens/{id}/versoes/{n}/publicar (mesma rota que /conteudo usa em Versões).

   A tela é fina de propósito: tudo o que edita documento está em web/js/editor/{documento,editor,arrasto,
   esquema,paleta}.js, que é o que os outros doze construtores da linha vão reusar. Aqui há: sessão, carregar,
   salvar, publicar, o aviso de conflito de versão (409, D12: versão otimista) e o seletor de idioma do
   construtor (item L5-12-acessibilidade-i18n-construtores).

   Idioma: o seletor troca só o dicionário desta aba, na hora, sem `location.reload()` — `carregar(idioma)`
   busca `/static/js/i18n/<idioma>.json` e dispara o evento que `aoTraduzir` escuta; a tela reaplica `[data-
   i18n]` sozinha (`aplicar()` de base/i18n.js) e o editor reconstrói seus rótulos dinâmicos por
   `editor.redesenharTudo()`. A escolha fica em `localStorage` só para esta tela — não é a preferência de
   conta do L7-10, que ainda não existe. */
import { obter, chamar, mensagemDe } from '../base/api.js';
import { h } from '../base/dom.js';
import { carregar, t, idiomaAtual, aoTraduzir } from '../base/i18n.js';
import * as api from '../catalogo/api.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { criarEditor } from './editor.js';
import { PALETA_LAYOUT } from './paleta.js';
import { novoDocumento } from './documento.js';

const IDIOMAS = ['pt-BR', 'en', 'es'];
const CHAVE_IDIOMA_LOCAL = 'plat.construtor.idioma';

function idiomaSalvo() {
  try { return localStorage.getItem(CHAVE_IDIOMA_LOCAL); } catch { return null; }
}
function salvarIdioma(idioma) {
  try { localStorage.setItem(CHAVE_IDIOMA_LOCAL, idioma); } catch { /* modo privado sem storage: segue sem lembrar */ }
}

await carregar(idiomaSalvo() || undefined);
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/construtor' });
  const principal = document.getElementById('principal');
  const id = new URLSearchParams(location.search).get('item');
  const aviso = document.getElementById('aviso');
  const h1 = document.querySelector('main > h1');
  h1.textContent = t('construtor.titulo');

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
    document.title = `${item.titulo} · ${t('construtor.titulo')} · ${t('app.nome')}`;
  }

  const alvo = h('div', { id: 'editor-raiz' });
  const btSalvar = h('button', { type: 'button', id: 'salvar', class: 'primario', disabled: !id }, t('construtor.salvar'));
  const btPublicar = h('button', { type: 'button', id: 'publicar', disabled: true }, t('construtor.publicar'));
  const estado = h('span', { id: 'estado-salvo', class: 'estado' }, id ? t('construtor.sem_alteracoes') : t('construtor.sem_item'));
  const seletorIdioma = h('select', { id: 'idioma-construtor', 'aria-label': t('construtor.idioma') },
    ...IDIOMAS.map((cod) => h('option', { value: cod }, t(`construtor.idioma_${cod === 'pt-BR' ? 'pt' : cod}`))));
  seletorIdioma.value = idiomaAtual();
  seletorIdioma.addEventListener('change', async () => {
    salvarIdioma(seletorIdioma.value);
    await carregar(seletorIdioma.value);
    /* carregar() já reaplica [data-i18n] no documento inteiro; falta só o que o editor desenha por t() direto */
    editor?.redesenharTudo();
    h1.textContent = item ? item.titulo : t('construtor.titulo');
    btSalvar.textContent = t('construtor.salvar');
    btPublicar.textContent = t('construtor.publicar');
    seletorIdioma.setAttribute('aria-label', t('construtor.idioma'));
    for (const [i, cod] of IDIOMAS.entries()) seletorIdioma.options[i].textContent = t(`construtor.idioma_${cod === 'pt-BR' ? 'pt' : cod}`);
    aviso.ok?.(t('construtor.idioma_trocado', { idioma: seletorIdioma.value }));
  });

  principal.append(
    h('div', { class: 'linha-ferramentas' }, btSalvar, btPublicar, estado, h('label', { class: 'campo-idioma' }, seletorIdioma)),
    alvo,
  );

  const editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: PALETA_LAYOUT,
    aoMudar: () => { estado.textContent = t('construtor.alteracoes_nao_gravadas'); },
  });
  /* troca de idioma que acontecer por outra via (nenhuma hoje, mas é o contrato do módulo) também redesenha */
  aoTraduzir(() => editor.redesenharTudo());

  btSalvar.addEventListener('click', async () => {
    if (!item) return;
    btSalvar.disabled = true;
    const d = editor.documento();
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: item.tipo, esquema_versao: d.esquema_versao, corpo: d.corpo },
      versao_atual: item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status !== 200) { estado.textContent = t('construtor.nao_gravado'); aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    aviso.limpar?.();
    estado.textContent = t('construtor.gravado', { n: item.versao_atual });
    btPublicar.disabled = false;
  });

  btPublicar.addEventListener('click', async () => {
    if (!item) return;
    btPublicar.disabled = true;
    try {
      const novo = await api.versaoPublicar(item.id, item.versao_atual);
      item.versao_publicada = novo.versao_publicada;
      aviso.ok?.(t('construtor.publicado', { n: item.versao_atual }));
    } catch (e) {
      aviso.mostrar?.(e.message || String(e), 'erro');
    } finally {
      btPublicar.disabled = false;
    }
  });
}
