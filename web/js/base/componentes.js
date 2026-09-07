/* plat — registra todos os Custom Elements de base. Importar uma vez por tela. */
import './componentes/aviso.js';
import './componentes/busca.js';
import './componentes/paginacao.js';
import './componentes/tabela.js';
import './componentes/formulario.js';
import './componentes/dialogo.js';
import './componentes/estado.js';
import './componentes/toast.js';
import './componentes/painel.js';
import './componentes/tema.js';
import './componentes/idioma.js';
export { confirmar, pedir } from './componentes/dialogo.js';
export { notificar } from './componentes/toast.js';
export { aplicarTema, temaAtual } from './componentes/tema.js';
export { definirIdioma, idiomaAtual } from './i18n.js';
