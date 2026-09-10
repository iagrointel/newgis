/* Corredor comum dos 10 exemplos do SDK JavaScript (item L7-08-c-sdk-js). O MESMO código roda de dois jeitos:
   pelo formulário da página (quem abre /static/sdk/exemplos/NN_x.html à mão) e por `window.exemplo.main(url,
   inquilino, login, senha)` (o e2e em tests/e2e/test_sdk_js.py). Sem script inline, sem innerHTML: as páginas
   abrem com CSP estrita (default-src 'none'), e qualquer violação é erro no e2e. */
import { ErroPlataforma, Plataforma } from '/static/sdk/plat.js';

// `dados` mínimo válido para tipo_item "mapa" (esquema_versao e corpo obrigatórios; um mapa vazio é válido)
export const DADOS_MAPA = { esquema_versao: 1, corpo: {} };
export { ErroPlataforma, Plataforma };

export function preparar(nome, main) {
  const saida = document.getElementById('saida');
  const escrever = (linha) => { saida.append(document.createTextNode(`${linha}\n`)); };

  async function rodar(url, inquilino, login, senha) {
    document.body.dataset.resultado = 'rodando';
    saida.replaceChildren();
    try {
      const r = await main({ url: url.replace(/\/+$/, ''), inquilino, login, senha, escrever });
      document.body.dataset.resultado = 'ok';
      return r;
    } catch (e) {
      escrever(`ERRO ${e instanceof ErroPlataforma ? JSON.stringify(e.toProblemDetails()) : String(e)}`);
      document.body.dataset.resultado = 'erro';
      throw e;
    }
  }

  const form = document.getElementById('form');
  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    rodar(location.origin, form.inquilino.value, form.login.value, form.senha.value).catch(() => {});
  });
  // registro de violação de CSP na própria página: o e2e lê window.exemplo.violacoes (refutação do item)
  const violacoes = [];
  document.addEventListener('securitypolicyviolation', (ev) => {
    violacoes.push(`${ev.violatedDirective}: ${ev.blockedURI || ev.sourceFile || '?'}`);
  });
  window.exemplo = { nome, main: rodar, violacoes };
  document.body.dataset.pronto = '1';
}

export async function comSessao({ url, inquilino, login, senha, escrever }, nomeToken, corpo) {
  // entra, roda `corpo(p)` e SEMPRE revoga o token que criou (o limite de tokens ativos por usuário é real)
  const p = await Plataforma.entrar(url, inquilino, login, senha, { nomeToken });
  try {
    return await corpo(p);
  } finally {
    await p.sair();
    escrever(`token ${nomeToken} revogado; sessão encerrada`);
  }
}

export function esperarMapa(mapa) {
  return new Promise((resolve, reject) => {
    if (mapa.loaded()) { resolve(mapa); return; }
    mapa.once('load', () => resolve(mapa));
    mapa.once('error', (e) => reject(e && e.error ? e.error : new Error('erro do mapa')));
  });
}
