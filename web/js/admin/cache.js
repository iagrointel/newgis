/* plat — tela /admin/cache (item L1-02-d): taxa de acerto do cache de ladrilhos por dia
   (GET /api/imagens/cache/status?desde=-7d). O número vem do campo `cache` do log do nginx —
   um HIT é respondido pelo nginx e nunca chega à aplicação. Quando o log não traz o campo, a
   API responde sem_dado/sem_linhas com o porquê, e a tela mostra esse porquê em vez de 0 %. */
import { obter, mensagemDe } from '../base/api.js';
import { marcador } from '../base/dom.js';
import { carregar, t, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.configurar' });
if (usuario) await iniciar();
pronto();

function taxaFmt(v) {
  return v === null || v === undefined ? '' : `${(v * 100).toFixed(1)} %`;
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/cache' });
  cabecalho(t('cache.titulo'));
  const tb = document.getElementById('tabela-dias');
  tb.colunas = [
    { chave: 'dia', titulo: t('cache.dia'), classe: 'mono' },
    { chave: 'acertos', titulo: t('cache.acertos'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'erros', titulo: t('cache.erros'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'sem_cache', titulo: t('cache.sem_cache'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'taxa_de_acerto', titulo: t('cache.taxa'), classe: 'num', formatar: taxaFmt },
  ];
  tb.vazio = t('cache.sem_dias');

  const corpo = document.getElementById('resumo-corpo');
  const r = await obter('/api/imagens/cache/status?desde=-7d');
  if (r.status !== 200) {
    corpo.textContent = mensagemDe(r);
    return;
  }
  const j = r.json;
  tb.linhas = j.dias || [];
  const linhas = [
    marcador(j.estado, j.estado === 'ok' ? 'ok' : ''),
    document.createTextNode(` · ${t('cache.janela')}: ${j.janela?.desde || '-7d'}`
      + ` · ${t('cache.linhas_lidas')}: ${formatarNumero(j.linhas_lidas || 0)}`),
  ];
  if (j.por_que) linhas.push(document.createTextNode(` — ${j.por_que}`));
  corpo.replaceChildren(...linhas);
}
