/* plat — faixa do modo de manutenção (L7-33-modo-somente-leitura). Consulta GET /api/modo (público,
   sempre 200) e, quando ativo, fixa uma faixa no topo da tela com o MOTIVO gravado pelo operador —
   é o mesmo texto que a API devolve no detalhe do 503 de escrita, então o que o usuário lê na faixa
   é o que ele lê na mensagem de bloqueio. Chamada por exigirSessao (todas as telas com sessão) e
   pela tela /entrar (quem ainda não entrou também vê). Sem flag, nenhum elemento é criado. */
import { obter } from './api.js';
import { h } from './dom.js';
import { loja } from './estado.js';
import { t } from './i18n.js';

export async function aplicarFaixaModo() {
  const r = await obter('/api/modo');
  const modo = r.status === 200 && r.json && typeof r.json === 'object' ? r.json : { ativo: false };
  loja.definir({ modo });
  document.getElementById('faixa-modo')?.remove();
  document.body.classList.remove('em-manutencao');
  if (!modo.ativo) return modo;
  const faixa = h('div', { id: 'faixa-modo', class: 'faixa-modo', role: 'alert' },
    h('strong', {}, t('modo.faixa_rotulo')), ` ${modo.motivo || ''}`);
  document.body.prepend(faixa);
  document.body.classList.add('em-manutencao');
  return modo;
}
