/* plat — entrada. Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports
   (duas URLs do mesmo módulo = duas instâncias). Esta tela mostra versão e saúde lidas da API. */
import { obterJSON, formatarJSON, texto } from './js/core.js';

async function mostrarVersao() {
  const r = await obterJSON('/api/versao');
  texto('versao-numero', r.json.versao);
  texto('versao-git', r.json.git_sha);
  texto('versao-ambiente', r.json.ambiente);
}

async function mostrarSaude() {
  const r = await obterJSON('/saude');
  const estado = document.getElementById('saude-estado');
  estado.textContent = r.status === 200 ? 'ok' : `${r.status} ${r.json.banco || ''}`.trim();
  estado.className = `estado ${r.status === 200 ? 'ok' : 'falha'}`;
  document.getElementById('saude-json').textContent = formatarJSON(r.json);
}

await Promise.all([mostrarVersao(), mostrarSaude()]);
document.body.dataset.pronto = '1';
