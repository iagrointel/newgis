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
import { assinarCamadas, horaCurta } from '../vivo/assinatura.js';

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

  // atualização viva (L2-06-d): o painel assina as camadas das suas fontes e refaz só a consulta afetada.
  // `porIntervalo` vira verdadeiro quando o fluxo não está disponível — o texto do cabeçalho diz qual dos
  // dois caminhos está em uso, para ninguém achar que a tela está viva quando está apenas repetindo.
  let porIntervalo = false;
  const marcador = el('painel-atualizado');
  const assinar = (camadas, aoMudar, op) => assinarCamadas(camadas, aoMudar, {
    aoIndisponivel: () => { porIntervalo = true; op.aoIndisponivel(); },
    // marca no DOM que o fluxo está de pé: quem dá suporte (e o teste de tela) consegue distinguir
    // "painel vivo" de "painel que só carregou uma vez"
    aoVivo: () => { marcador.dataset.vivo = '1'; },
  });
  const aoAtualizar = (data) => {
    marcador.hidden = false;
    const chave = porIntervalo ? 'painel.atualizado_intervalo' : 'painel.atualizado_as';
    marcador.textContent = t(chave).replace('{hora}', horaCurta(data));
  };

  const instancia = montarPainel(el('painel-grade'), corpo, buscarDados, iniciaisUrl, { assinar, aoAtualizar });
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
