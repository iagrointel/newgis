/* plat — página /aplicativo (item L5-06-motor-widgets; UX-07): monta um documento de WIDGETS pelo motor
   (`montarWidgets`), sem o chrome interno do produto — a página é dona do viewport.

   Três origens, nesta ordem:
     1. `?item=<id>`: o item do catálogo (sessão), `painel` ou `app`. O documento do editor (nós com `pai`,
        `largura_colunas`, `propriedades`) é traduzido para o documento de widgets do motor (nós com `posicao` e
        `configuracao`) por `paraWidgets()`; num `app` entram os nós da página inicial. É o "Executar" de um painel.
     2. `<script type="application/json" id="documento-widgets">` incorporado na página (publicação estática).
     3. sem nada: a demonstração fixa (três widgets ligados), que o e2e do L5-06 mede.
   Estados por <plat-estado>: carregando, vazio (documento sem widget), negado (403), inexistente (404) e erro.
   A página nunca fica em branco e `data-pronto` é marcado de qualquer jeito. */
import '../base/componentes.js';
import { obter } from '../base/api.js';
import { carregar, t } from '../base/i18n.js';
import { montarWidgets } from './motor.js';

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

const NIVEL_TEXTO = { titulo: 2, legenda: 6 };

/* configuração de widget a partir das propriedades do nó do editor (paleta de layout / de páginas) */
function configuracaoDe(no) {
  const p = { ...(no.propriedades || {}) };
  switch (no.tipo) {
    case 'texto': {
      const c = { texto: String(p.texto ?? '') };
      if (typeof p.nivel === 'string' && NIVEL_TEXTO[p.nivel]) c.nivel = NIVEL_TEXTO[p.nivel];
      if (typeof p.nivel === 'number') c.nivel = p.nivel;
      if (p.formato) c.formato = p.formato;
      return c;
    }
    case 'imagem': return { url: p.url || '', alternativo: p.alternativo || '' };
    case 'mapa': return { rotulo: p.rotulo || t('aplicativo.widget_mapa') };
    case 'tabela': return { colunas: Array.isArray(p.colunas) ? p.colunas : [], linhas: Array.isArray(p.linhas) ? p.linhas : [] };
    case 'menu_widget': return p;
    default: return p;
  }
}

/* documento do EDITOR (árvore com pai/largura_colunas) -> documento de WIDGETS (grade de 12 colunas, um nó por
   widget; contêineres de layout não viram widget: os filhos deles entram em sequência). Num `app`, só a página
   inicial (marcada `inicial`, senão a primeira). */
export function paraWidgets(documento) {
  const nos = Array.isArray(documento?.corpo?.nos) ? documento.corpo.nos : [];
  const filhos = (pai) => nos.filter((n) => (n.pai ?? null) === pai);
  let raiz = null;
  const paginas = filhos(null).filter((n) => n.tipo === 'pagina');
  if (paginas.length) raiz = (paginas.find((n) => n.propriedades?.inicial) || paginas[0]).id;
  const saida = [];
  let linha = 1;
  let coluna = 1;
  const visitar = (pai) => {
    for (const no of filhos(pai)) {
      if (no.tipo === 'pagina') continue;
      const largura = Math.min(12, Math.max(1, Number(no.largura_colunas) || 12));
      const temFilhos = filhos(no.id).length > 0;
      if (temFilhos || no.tipo === 'grupo' || ['linha', 'coluna', 'grade', 'acordeao', 'painel_fixo', 'painel_lateral', 'janela', 'secao_vistas', 'vista', 'cabecalho', 'rodape'].includes(no.tipo)) {
        visitar(no.id);
        continue;
      }
      if (coluna + largura - 1 > 12) { linha += 1; coluna = 1; }
      const tipo = no.tipo === 'menu_widget' ? 'menu' : no.tipo;
      saida.push({ id: no.id, tipo, posicao: { coluna, linha, largura, altura: 1 }, configuracao: configuracaoDe(no) });
      coluna += largura;
      if (coluna > 12) { linha += 1; coluna = 1; }
    }
  };
  visitar(raiz);
  return { tipo: documento?.tipo || 'painel', esquema_versao: 2, corpo: { nos: saida, ligacoes: Array.isArray(documento?.corpo?.ligacoes) ? documento.corpo.ligacoes : [] } };
}

function documentoIncorporado() {
  const incorporado = document.getElementById('documento-widgets');
  return incorporado ? JSON.parse(incorporado.textContent) : null;
}

const principal = document.getElementById('aplicativo');
const estado = document.getElementById('estado');
await carregar();
estado.addEventListener('acao', (ev) => {
  if (ev.detail.id === 'tentar') location.reload();
  if (ev.detail.id === 'construtor') location.href = '/construtor';
});
const id = new URLSearchParams(location.search).get('item');
try {
  let documento;
  if (id) {
    estado.carregando(t('executor.carregando'));
    const r = await obter(`/api/itens/${encodeURIComponent(id)}`);
    if (r.status === 401) { location.replace(`/entrar?proximo=${encodeURIComponent(location.pathname + location.search)}`); throw new Error('sessao'); }
    if (r.status === 404) {
      estado.mostrar({ tipo: 'vazio', titulo: t('executor.inexistente_titulo'), texto: t('executor.inexistente_texto'), acoes: [{ id: 'construtor', rotulo: t('executor.ir_construtor') }] });
      throw new Error('inexistente');
    }
    if (r.status !== 200) { estado.erro(r); throw new Error(`http ${r.status}`); }
    const item = r.json;
    document.title = `${item.titulo} · ${t('app.nome')}`;
    documento = paraWidgets({ tipo: item.tipo, ...(item.dados || {}) });
    if (!documento.corpo.nos.length) {
      estado.mostrar({ tipo: 'vazio', titulo: t('aplicativo.vazio_titulo'), texto: t('aplicativo.vazio_texto'), acoes: [{ id: 'construtor', rotulo: t('executor.ir_construtor') }] });
      throw new Error('vazio');
    }
    estado.limpar();
  } else {
    documento = documentoIncorporado() || DEMONSTRACAO;
  }
  const motor = await montarWidgets(principal, documento);
  window.plat = { ...(window.plat || {}), widgets: motor };
} catch (erro) {
  if (!['sessao', 'inexistente', 'vazio'].includes(erro.message) && !/^http /.test(erro.message)) {
    estado.mostrar({ tipo: 'erro', texto: t('aplicativo.erro_montar', { erro: erro.message }), acoes: [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
  }
}
document.body.dataset.pronto = '1';
