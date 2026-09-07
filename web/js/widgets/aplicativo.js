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
        configuracao: { rotulo: 'Filtrar linhas', placeholder: 'Digite um valor' },
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

function documentoDaPagina() {
  const incorporado = document.getElementById('documento-widgets');
  return incorporado ? JSON.parse(incorporado.textContent) : DEMONSTRACAO;
}

const motor = await montarWidgets(document.getElementById('aplicativo'), documentoDaPagina());
window.plat = { ...(window.plat || {}), widgets: motor };
document.body.dataset.pronto = '1';
