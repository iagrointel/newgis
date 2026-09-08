import { montarWidgets } from './motor.js';
import { aplicarDaUrl, ligarUrl } from '../app/estado_url.js';

const DEMONSTRACAO = {
  tipo: 'app', esquema_versao: 2,
  corpo: {
    nos: [
      {
        id: '01K4KX2Q0S0000000000000001', tipo: 'texto', posicao: { coluna: 1, linha: 1, largura: 12, altura: 1 },
        configuracao: { texto: 'Aplicativo publicado', nivel: 1 },
      },
      {
        id: '01K4KX2Q0S0000000000000002', tipo: 'filtro', posicao: { coluna: 1, linha: 2, largura: 4, altura: 1 },
        configuracao: { rotulo: 'Filtrar linhas' },
      },
      {
        id: '01K4KX2Q0S0000000000000003', tipo: 'tabela', posicao: { coluna: 5, linha: 2, largura: 8, altura: 2 },
        configuracao: {
          colunas: [{ campo: 'nome', rotulo: 'Nome' }, { campo: 'tipo', rotulo: 'Tipo' }],
          linhas: [{ nome: 'Rios', tipo: 'linha' }, { nome: 'Municípios', tipo: 'polígono' }],
        },
      },
    ],
    ligacoes: [{
      origem: '01K4KX2Q0S0000000000000002', alvo: '01K4KX2Q0S0000000000000003',
      evento: 'filtro.alterado', acao: 'tabela.filtrar',
    }],
  },
};

/* item L5-07: `/aplicativo?item=<id>` publica o documento do item (GET /api/itens/{id}); sem `item`, o documento
   embutido na página ou a demonstração do L5-06. O estado de filtros e seleção vive na URL (`v.<vista>`):
   restaurado ANTES de as mensagens ouvirem e reescrito a cada mudança de vista. */
async function documentoDaPagina() {
  const itemId = new URL(location.href).searchParams.get('item');
  if (itemId) {
    const r = await fetch(`/api/itens/${encodeURIComponent(itemId)}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`item ${itemId}: HTTP ${r.status}`);
    const item = await r.json();
    if (!item.dados?.corpo?.nos) throw new Error(`item ${itemId} não é um documento de aplicativo`);
    document.title = `${item.titulo} · plat`;
    return item.dados;
  }
  const incorporado = document.getElementById('documento-widgets');
  return incorporado ? JSON.parse(incorporado.textContent) : DEMONSTRACAO;
}

// A página nunca fica em branco: documento ilegível ou motor que não sobe viram uma mensagem no <main>,
// e `data-pronto` é marcado de qualquer jeito para o e2e (e quem lê a tela) saber que terminou.
const principal = document.getElementById('aplicativo');
try {
  const documento = await documentoDaPagina();
  const motor = await montarWidgets(principal, documento, {
    antesDoBarramento: (vistas) => { aplicarDaUrl(vistas); ligarUrl(vistas); },
  });
  const avisos = document.createElement('div');
  avisos.id = 'avisos-barramento'; avisos.setAttribute('aria-live', 'polite'); avisos.className = 'plat-avisos';
  motor.barramentoApp.addEventListener('aviso', (e) => {
    const p = document.createElement('p'); p.dataset.tipo = e.detail.tipo; p.textContent = e.detail.mensagem;
    avisos.append(p);
  });
  principal.append(avisos);
  window.plat = { ...(window.plat || {}), widgets: motor };
} catch (erro) {
  const aviso = document.createElement('section');
  aviso.className = 'plat-widget-erro'; aviso.setAttribute('role', 'alert');
  aviso.textContent = `Aplicativo não pôde ser montado: ${erro.message}`;
  principal.replaceChildren(aviso);
}
document.body.dataset.pronto = '1';
