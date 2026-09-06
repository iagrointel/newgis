/* plat · catálogo — diálogo Compartilhar (ADR 0004 seções 6 e 15.2): nível privado / inquilino / público (este só
   se o inquilino permite), grupos em que o ator contribui (os demais com aviso), links por token (criar com validade,
   copiar uma vez, revogar) e a árvore de dependências com o nível de cada uma. Dependência ABAIXO do nível escolhido
   (camada privada num mapa que vai ao inquilino, por exemplo) ganha o aviso #compartilhar-dependencias-aviso e a
   etiqueta "abaixo do nível" na linha; a caixa "elevar ao nível do mapa" (desabilitada onde pode_editar = false, com
   o motivo no title) é a ESCOLHA explícita — nada é rebaixado nem elevado em silêncio, e nada muda até "Aplicar". */
import { h, limpar, botaoCopiar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import * as api from './api.js';
import { rotuloTipo } from './contexto.js';
import { elipse, dataHora, LIMITES } from './formato.js';

function dialogo() { return document.getElementById('painel-compartilhar') || document.body.appendChild(h('plat-dialogo', { id: 'painel-compartilhar' })); }

export async function abrirCompartilhar(item, { aoMudar = () => {} } = {}) {
  const d = dialogo();
  const corpo = h('div', { class: 'compartilhar' });
  const aviso = h('plat-aviso', { id: 'compartilhar-aviso' });
  corpo.append(aviso, h('p', { class: 'fraco' }, t('catalogo.carregando')));
  const abertura = d.abrir({ titulo: t('catalogo.compartilhar_titulo', { titulo: elipse(item.titulo, 60) }), corpo, botoes: [{ id: 'fechar', rotulo: t('acao.fechar') }] });
  let estado; let grupos = [];
  try {
    [estado, grupos] = await Promise.all([api.compartilhamento(item.id), api.meusGrupos().then((r) => r.itens || []).catch(() => [])]);
  } catch (e) { limpar(corpo); corpo.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, e.message)); return abertura; }
  limpar(corpo);
  corpo.append(aviso);

  /* nível */
  const niveis = [['privado', true], ['inquilino', tem('compartilhar.inquilino')], ['publico', !!estado.publico_permitido && tem('compartilhar.publico')]];
  const fs = h('fieldset', { class: 'caixas' }, h('legend', { class: 'campo-rotulo' }, t('catalogo.nivel_acesso')));
  for (const [v, pode] of niveis) {
    const r = h('input', { type: 'radio', name: 'acesso', value: v, id: `acesso-${v}` });
    r.checked = estado.acesso === v;
    if (!pode && estado.acesso !== v) r.disabled = true;
    fs.append(h('div', { class: 'caixa' }, r, h('label', { for: `acesso-${v}`, title: pode ? '' : t('catalogo.nivel_sem_privilegio') }, t(`catalogo.acesso_${v}`), v === 'publico' && !estado.publico_permitido ? h('span', { class: 'fraco' }, ` · ${t('catalogo.publico_desligado')}`) : null)));
  }
  corpo.append(fs);

  /* grupos */
  const gruposFs = h('fieldset', { class: 'caixas' }, h('legend', { class: 'campo-rotulo' }, t('catalogo.grupos')));
  const marcados = new Set((estado.grupos || []).map((g) => g.id));
  const todosGrupos = [...grupos];
  for (const g of estado.grupos || []) if (!todosGrupos.some((x) => x.id === g.id)) todosGrupos.push({ ...g, meu_papel: null });
  if (!todosGrupos.length) gruposFs.append(h('p', { class: 'fraco' }, t('catalogo.sem_grupos')));
  for (const g of todosGrupos) {
    const contribui = g.contribuicao === 'todos' ? !!g.meu_papel : (g.meu_papel === 'dono' || g.meu_papel === 'gerente') || tem('grupos.gerir_todos');
    const cx = h('input', { type: 'checkbox', name: 'grupo', value: g.id, id: `grupo-${g.id}` });
    cx.checked = marcados.has(g.id);
    if (!contribui && !cx.checked) cx.disabled = true;
    if (!tem('compartilhar.grupo') && !cx.checked) cx.disabled = true;
    gruposFs.append(h('div', { class: 'caixa' }, cx, h('label', { for: `grupo-${g.id}`, title: contribui ? '' : t('catalogo.grupo_sem_contribuicao') }, g.nome, contribui ? null : h('span', { class: 'fraco' }, ` · ${t('catalogo.grupo_sem_contribuicao')}`))));
  }
  corpo.append(gruposFs);

  /* dependências: nível de cada uma; "abaixo" = quem recebe este item no nível escolhido não vê a dependência */
  const deps = estado.dependencias || [];
  const depCaixas = [];
  const depLinhas = [];
  const depAviso = h('p', { id: 'compartilhar-dependencias-aviso', class: 'aviso-pendencia', role: 'status', hidden: true });
  const ORDEM = { privado: 0, inquilino: 1, publico: 2 };
  const nivelEscolhido = () => fs.querySelector('input[name=acesso]:checked')?.value || estado.acesso;
  const gruposEscolhidos = () => gruposFs.querySelectorAll('input[name=grupo]:checked').length;
  const rotuloAcesso = (dp) => `${t(`catalogo.acesso_${dp.acesso}`)}${dp.grupos ? ` +${dp.grupos}` : ''}`;
  function abaixo(dp) {
    if (dp.oculto) return false;
    const n = nivelEscolhido();
    if ((ORDEM[dp.acesso] ?? 0) < (ORDEM[n] ?? 0)) return true;
    return n === 'privado' && gruposEscolhidos() > 0 && !dp.grupos;
  }
  function atualizarDependencias() {
    let n = 0; let editaveis = 0;
    for (const { dp, tr, marca } of depLinhas) {
      const ab = abaixo(dp);
      tr.classList.toggle('abaixo', ab);
      marca.hidden = !ab;
      if (ab) { n += 1; if (dp.pode_editar) editaveis += 1; }
    }
    depAviso.hidden = !n;
    if (n) depAviso.textContent = t('catalogo.dependencias_aviso', { n, nivel: t(`catalogo.acesso_${nivelEscolhido()}`), editaveis });
  }
  if (deps.length) {
    const tab = h('table', { id: 'compartilhar-dependencias' }, h('thead', {}, h('tr', {}, h('th', {}, t('catalogo.elevar_nivel')), h('th', {}, t('catalogo.col_titulo')), h('th', {}, t('catalogo.col_tipo')), h('th', {}, t('catalogo.col_acesso')))));
    const tb = h('tbody');
    for (const dp of deps) {
      if (dp.oculto) { tb.append(h('tr', { class: 'oculto', 'data-dependencia': dp.id }, h('td'), h('td', { colspan: 3, class: 'fraco' }, t('catalogo.dependencia_oculta')))); continue; }
      const cx = h('input', { type: 'checkbox', value: dp.id, 'aria-label': t('catalogo.elevar_nivel') });
      if (!dp.pode_editar) { cx.disabled = true; cx.title = t('catalogo.dependencia_sem_edicao'); }
      const marca = h('span', { class: 'marcador atencao', hidden: true }, t('catalogo.dependencia_abaixo'));
      const acessoCel = h('td', {}, h('span', { class: 'acesso' }, rotuloAcesso(dp)), ' ', marca);
      const tr = h('tr', { 'data-dependencia': dp.id }, h('td', {}, cx), h('td', {}, elipse(dp.titulo, 50)), h('td', {}, rotuloTipo(dp.tipo)), acessoCel);
      depCaixas.push(cx);
      depLinhas.push({ dp, tr, marca, cx, acessoCel });
      tb.append(tr);
    }
    tab.append(tb);
    const elevarTodas = h('button', { type: 'button', class: 'pequeno', id: 'compartilhar-elevar-todas' }, t('catalogo.elevar_todas'));
    elevarTodas.addEventListener('click', () => { for (const { dp, cx } of depLinhas) if (abaixo(dp) && dp.pode_editar) cx.checked = true; });
    corpo.append(h('section', { class: 'dependencias' }, h('h3', {}, t('catalogo.dependencias')), h('p', { class: 'fraco' }, t('catalogo.dependencias_texto')), depAviso, tab, h('div', { class: 'linha-ferramentas' }, h('div', { class: 'direita' }, elevarTodas))));
    fs.addEventListener('change', atualizarDependencias);
    gruposFs.addEventListener('change', atualizarDependencias);
    atualizarDependencias();
  }

  const aplicar = h('button', { type: 'button', class: 'primario', id: 'compartilhar-aplicar' }, t('catalogo.aplicar'));
  aplicar.addEventListener('click', async () => {
    aplicar.disabled = true;
    const acesso = fs.querySelector('input[name=acesso]:checked')?.value || estado.acesso;
    const gruposSel = [...gruposFs.querySelectorAll('input[name=grupo]:checked')].map((x) => x.value);
    const aplicarA = depCaixas.filter((x) => x.checked).map((x) => x.value);
    const corpoPut = { acesso, grupos: gruposSel };
    if (aplicarA.length) corpoPut.aplicar_a_dependencias = aplicarA;
    try {
      estado = await api.compartilhar(item.id, corpoPut);
      aviso.ok(t('catalogo.compartilhamento_salvo'));
      // a árvore reflete o nível novo das dependências elevadas; as caixas voltam a vazio (escolha é por vez)
      const novas = new Map((estado.dependencias || []).map((dp) => [dp.id, dp]));
      for (const linha of depLinhas) {
        Object.assign(linha.dp, novas.get(linha.dp.id) || {});
        linha.acessoCel.querySelector('.acesso').textContent = rotuloAcesso(linha.dp);
        linha.cx.checked = false;
      }
      atualizarDependencias();
      aoMudar({ acesso: estado.acesso, compartilhado_com_grupos: (estado.grupos || []).length });
    } catch (e) {
      const dt = e.detalhe || {};
      aviso.erro(e.codigo === 'sem_contribuicao_no_grupo' ? t('catalogo.erro_sem_contribuicao', { grupo: dt.grupo?.nome || dt.grupo || '' }) : e.codigo === 'publico_desligado' ? t('catalogo.publico_desligado') : e.message);
    } finally { aplicar.disabled = false; }
  });
  corpo.append(h('div', { class: 'botoes' }, aplicar));

  /* links por token */
  if (tem('compartilhar.link') && item.pode_editar) corpo.append(secaoLinks(item, estado, aviso, aoMudar));
  return abertura;
}

function secaoLinks(item, estado, aviso, aoMudar) {
  const sec = h('section', { class: 'links' }, h('h3', {}, t('catalogo.links')), h('p', { class: 'fraco' }, t('catalogo.links_texto')));
  const tab = h('plat-tabela', { id: 'links-tabela', legenda: t('catalogo.links') });
  tab.colunas = [
    { chave: 'prefixo', titulo: t('token.prefixo'), formatar: (v, l) => h('code', {}, `${v || ''}…`, l.nome ? ` ${l.nome}` : '') },
    { chave: 'expira_em', titulo: t('token.expira'), formatar: (v) => (v ? dataHora(v) : t('catalogo.sem_validade')) },
    { chave: 'acessos', titulo: t('token.acessos'), classe: 'num', formatar: (v) => String(v ?? 0) },
    { chave: 'revogado_em', titulo: t('campo.estado'), formatar: (v, l) => (v ? t('token.revogado') : (l.expira_em && new Date(l.expira_em) < new Date() ? t('token.expirado') : t('token.valido'))) },
  ];
  tab.acoes = (l) => (l.revogado_em ? [] : [{ id: 'revogar', rotulo: t('token.revogar'), classe: 'perigo' }]);
  tab.addEventListener('acao', async (e) => {
    try { await api.linkRevogar(item.id, e.detail.linha.id); aviso.ok(t('catalogo.link_revogado')); await carregar(); } catch (err) { aviso.erro(err.message); }
  });
  const novoArea = h('div', { id: 'link-novo-area' });
  const criarBt = h('button', { type: 'button', class: 'pequeno', id: 'link-novo' }, t('catalogo.link_novo'));
  const form = h('plat-formulario', { id: 'link-form' });
  form.campos = [
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', atributos: { maxlength: 100 } },
    { nome: 'dias', rotulo: t('token.validade_dias'), tipo: 'numero', padrao: 30, ajuda: t('token.validade_ajuda', { padrao: 30, max: LIMITES.linkDias }), atributos: { min: 1, max: LIMITES.linkDias } },
    { nome: 'permite_download', rotulo: t('catalogo.link_permite_download'), tipo: 'caixa' },
    ...((estado.dependencias || []).length ? [{ nome: 'itens_incluidos', rotulo: t('catalogo.link_incluir'), tipo: 'caixas', opcoes: estado.dependencias.map((dp) => ({ valor: dp.id, rotulo: elipse(dp.titulo, 50), desabilitado: !dp.pode_editar, titulo: dp.pode_editar ? '' : t('catalogo.dependencia_sem_edicao') })) }] : []),
  ];
  form.botoes = [{ id: 'ok', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  form.hidden = true;
  criarBt.addEventListener('click', () => { form.hidden = false; form.focarPrimeiro(); });
  form.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') form.hidden = true; });
  form.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    if (v.dias !== null && (v.dias < 1 || v.dias > LIMITES.linkDias)) { form.erro('dias', t('token.validade_fora', { max: LIMITES.linkDias })); return; }
    const corpo = { permite_download: !!v.permite_download };
    if (v.nome) corpo.nome = v.nome;
    if (v.dias) corpo.expira_em = new Date(Date.now() + v.dias * 86400000).toISOString();
    if (v.itens_incluidos && v.itens_incluidos.length) corpo.itens_incluidos = v.itens_incluidos;
    form.ocupado = true;
    try {
      const r = await api.linkCriar(item.id, corpo);
      form.hidden = true;
      const url = r.url || `${location.origin}/c/${r.token}`;
      const caixa = h('div', { class: 'link-token' }, h('strong', {}, t('catalogo.link_uma_vez')), h('code', { class: 'codigo', id: 'link-url' }, url), h('div', {}, botaoCopiar(url, null, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') })));
      limpar(novoArea); novoArea.append(caixa);
      await carregar();
      aoMudar({ links_ativos: (item.links_ativos || 0) + 1 });
    } catch (err) { form.mensagem(err.message, 'erro'); } finally { form.ocupado = false; }
  });
  async function carregar() {
    try { tab.linhas = await api.links(item.id); tab.vazio = t('catalogo.sem_links'); } catch (err) { aviso.erro(err.message); tab.linhas = []; }
  }
  sec.append(h('div', { class: 'linha-ferramentas' }, h('div', { class: 'direita' }, criarBt)), form, novoArea, tab);
  carregar();
  return sec;
}
