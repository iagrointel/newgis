/* plat · painel — entrada da tela autenticada /paineis/{id} (item L2-06-a-modelo-painel-fontes). Lê o id do
   documento no path, carrega o item pela API normal (RLS de sessão, o mesmo mecanismo de /conteudo/{id}),
   migra o corpo para a versão vigente (a API já devolve migrado, ver GET /api/itens/{id}) e monta o painel
   com `web/js/paineis/render.js`, buscando dado por `api.painelDados` — sempre UM POST por FONTE por ciclo
   (nunca por elemento; ver a justificativa no topo de render.js). body[data-pronto="1"] só depois da PRIMEIRA
   carga de dado de toda fonte (não só do primeiro parágrafo desenhado) — o e2e espera por isso antes da
   captura e da medida de primeira pintura, que é lida de `performance`, não deste sinal. */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import * as api from '../catalogo/api.js';
import { montarBarraFiltros, montarPainel, parametrosUrlDaLocalizacao } from './render.js';

const el = (id) => document.getElementById(id);
const itemId = decodeURIComponent((/^\/paineis\/([^/]+)/.exec(location.pathname) || [])[1] || '');

async function iniciar() {
  if (!itemId) { el('aviso').erro(t('painel.id_ausente')); pronto(); return; }
  let it;
  try {
    it = await api.obter(itemId);
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
    return;
  }
  if (it.tipo !== 'painel') {
    el('aviso').erro(t('painel.nao_e_painel'));
    pronto();
    return;
  }
  document.title = `${it.titulo} · ${t('app.nome')}`;
  el('painel-titulo').textContent = it.titulo;
  const corpo = (it.dados && it.dados.corpo) || {};

  const iniciaisUrl = parametrosUrlDaLocalizacao(corpo.parametros_url);
  const buscarDados = (fonteId, pedidos, filtroExecucao) =>
    api.painelDados(itemId, fonteId, { pedidos, filtro_execucao: filtroExecucao });

  const instancia = montarPainel(el('painel-grade'), corpo, buscarDados, iniciaisUrl);
  montarBarraFiltros(el('painel-filtros'), corpo.filtros, iniciaisUrl, (campo, valor) => instancia.atualizarFiltro(campo, valor));

  window.addEventListener('pagehide', instancia.destruir, { once: true });
  await instancia.aguardarPrimeiraCarga;
  pronto();
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/paineis' });
  try {
    await iniciar();
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
