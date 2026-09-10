/* plat — entrada. Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports
   (duas URLs do mesmo módulo = duas instâncias). Esta tela mostra versão e saúde lidas da API e, quando há
   sessão (marca local plat_sessao gravada no login), a barra lateral e os atalhos das telas. Sem a marca não
   chama /api/eu: a página inicial sem sessão não gera 401. */
import { obterJSON, formatarJSON, texto } from './js/core.js';
import { h, limpar } from './js/base/dom.js';
import { carregar, t } from './js/base/i18n.js';
import { montarLayout, telasVisiveis } from './js/base/layout.js';
import { icone } from './js/base/icones.js';
import { marcarRegua, reguaTela } from './js/base/regua.js';
import { sessaoProvavel, marcarSessao, urlLogin } from './js/auth/sessao.js';

/* RÉGUA (item L0-14): cada número desta tela carrega a procedência — rota, instante da resposta e o comando
   equivalente na linha de comando (o mesmo que o MANUAL.md manda usar para conferir). */
async function mostrarVersao() {
  const r = await obterJSON('/api/versao');
  texto('versao-numero', r.json.versao);
  texto('versao-git', r.json.git_sha);
  texto('versao-ambiente', r.json.ambiente);
  const proc = { origem: 'GET /api/versao', em: r.json.em, status: r.status, comando: 'curl -sS <url>/api/versao' };
  marcarRegua(document.getElementById('versao-numero'), { ...proc, comando: 'cat VERSAO' });
  marcarRegua(document.getElementById('versao-git'), { ...proc, comando: 'git rev-parse --short=12 HEAD' });
  marcarRegua(document.getElementById('versao-ambiente'), proc);
}

async function mostrarSaude() {
  const r = await obterJSON('/saude');
  const estado = document.getElementById('saude-estado');
  estado.textContent = r.status === 200 ? 'ok' : `${r.status} ${r.json.banco || ''}`.trim();
  estado.className = `estado ${r.status === 200 ? 'ok' : 'falha'}`;
  marcarRegua(estado, { origem: 'GET /saude', em: r.json.em, status: r.status, comando: 'curl -sS <url>/saude | python3 -m json.tool' });
  document.getElementById('saude-json').textContent = formatarJSON(r.json);
}

function mostrarLinkEntrar() {
  const sec = document.getElementById('entrada');
  const p = document.getElementById('entrada-texto');
  limpar(p);
  p.append(h('a', { class: 'botao primario', href: urlLogin('/') }, t('nav.entrar')));
  sec.hidden = false;
}

async function mostrarEntrada() {
  if (!sessaoProvavel()) { mostrarLinkEntrar(); return; }
  const r = await obterJSON('/api/eu');
  if (r.status !== 200) { marcarSessao(false); mostrarLinkEntrar(); return; }
  const usuario = r.json;
  montarLayout({ usuario, ativo: '/' });
  const sec = document.getElementById('entrada');
  document.getElementById('entrada-texto').textContent = t('inicio.ola', { nome: usuario.nome || usuario.login, inquilino: usuario.inquilino?.nome || '' });
  const grade = document.getElementById('atalhos');
  limpar(grade);
  for (const tela of telasVisiveis(usuario)) {
    if (tela.caminho === '/') continue;
    grade.append(h('a', { href: tela.caminho }, icone(tela.icone, { tamanho: 20 }), h('span', {}, t(tela.chave)), h('small', {}, t(`${tela.chave}_desc`))));
  }
  sec.hidden = false;
}

function mostrarReguaSemSessao() {
  if (!document.body.classList.contains('com-lateral')) reguaTela(document.getElementById('principal'));
}

await carregar();
await Promise.all([mostrarVersao(), mostrarSaude(), mostrarEntrada()]);
mostrarReguaSemSessao();
document.body.dataset.pronto = '1';
