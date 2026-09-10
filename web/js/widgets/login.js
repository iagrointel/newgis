import { PlatWidget, definir } from './base.js';
import { obter, enviar } from '../base/api.js';

export const contrato = Object.freeze({ eventos: ['login.mudou'], acoes: ['login.atualizar'] });

/* login: quem está autenticado (GET /api/eu) com botão sair, ou link para entrar */
class PlatLogin extends PlatWidget {
  renderizar() {
    const raiz = document.createElement('div'); raiz.className = 'plat-w-login';
    raiz.textContent = '…';
    this.replaceChildren(raiz);
    this.atualizar(raiz);
  }

  async atualizar(raiz) {
    const r = await obter('/api/eu');
    raiz.replaceChildren();
    if (r.status === 200) {
      const u = r.json;
      const nome = document.createElement('span'); nome.className = 'plat-login-nome';
      nome.textContent = `${u.nome || u.login}${u.inquilino && u.inquilino.nome ? ` · ${u.inquilino.nome}` : ''}`;
      const sair = document.createElement('button'); sair.type = 'button'; sair.textContent = 'Sair';
      sair.addEventListener('click', async () => { await enviar('/api/logout', {}); this.emitir('login.mudou', { autenticado: false }); this.renderizar(); });
      raiz.append(nome, sair);
      this.dataset.autenticado = '1';
      this.emitir('login.mudou', { autenticado: true, login: u.login });
      return;
    }
    const a = document.createElement('a'); a.className = 'botao';
    a.href = `/entrar?proximo=${encodeURIComponent(location.pathname + location.search)}`; a.textContent = 'Entrar';
    raiz.append(a);
    this.dataset.autenticado = '0';
    this.emitir('login.mudou', { autenticado: false });
  }

  acao_login_atualizar() { this.renderizar(); }
}

definir('plat-w-login', PlatLogin);
