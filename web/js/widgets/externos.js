/* plat — carregador de widgets externos do inquilino (L5-36). GET /api/widgets/externos e, para cada
   pacote: validarManifesto com as MESMAS regras da casa, o texto do módulo é baixado same-origin e o
   sha256 é reconferido com crypto.subtle ANTES de o código correr — o blob importado pelo motor é o TEXTO
   verificado, nunca uma segunda descarga. Sandbox corre no <plat-widget-sandboxe> (origem opaca, sem
   rede). O i18n do pacote entra com prefixo obrigatório `manifesto.i18n.`; chave fora do namespace é
   descartada e acusada. Nada daqui derruba a página: quem recusa volta em `recusados`. */
import { REGISTRO, validarManifesto } from './registro.js';
import { acrescentar } from '../base/i18n.js';
import { modulosVerificados } from './sandboxe.js';

const hex = (buffer) => [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, '0')).join('');

/* Módulo de blob não tem base hierárquica: o especificador raiz-relativo `/static/…` (a base da casa que
   o MANUAL indica) não resolve dentro dele. A reescrita é mecânica e anterior ao blob; o sha256 conferido
   continua sendo o do TEXTO original descarregado. */
const absoluto = (texto) => texto
  .replaceAll(`'/static/`, `'${location.origin}/static/`)
  .replaceAll(`"/static/`, `"${location.origin}/static/`);

async function textoVerificado(item) {
  const url = `/api/widgets/externos/${encodeURIComponent(item.nome)}/modulo.js`;
  const resp = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
  if (!resp.ok) throw new Error(`módulo HTTP ${resp.status}`);
  if (resp.headers.get('X-Plat-Widget-Sha256') !== item.sha256) throw new Error('sha256 do cabeçalho difere do registro');
  const texto = await resp.text();
  const sha = hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto)));
  if (sha !== item.sha256) throw new Error(`conteúdo mudou (sha256 ${sha} ≠ ${item.sha256})`);
  return texto;
}

async function i18nDoPacote(item, manifesto, avisos) {
  const resp = await fetch(`/api/widgets/externos/${encodeURIComponent(item.nome)}/i18n.json`, { credentials: 'same-origin' });
  if (!resp.ok) return;
  const prefixo = `${manifesto.i18n}.`;
  const permitidos = {};
  const fora = [];
  for (const [chave, valor] of Object.entries(await resp.json().catch(() => ({})))) {
    if (chave.startsWith(prefixo)) permitidos[chave] = valor; else fora.push(chave);
  }
  if (fora.length) avisos.push({ nome: item.nome, motivo: `i18n fora do prefixo ${prefixo}: ${fora.join(', ')}` });
  if (Object.keys(permitidos).length) acrescentar(permitidos);
}

/* Devolve {registrados, recusados, avisos}. Chamar ANTES de montarWidgets (os nós de tipo externo só
   existem no documento depois de o REGISTRO saber o tipo). */
export async function carregarWidgetsExternos() {
  const registrados = [];
  const recusados = [];
  const avisos = [];
  const resp = await fetch('/api/widgets/externos', { credentials: 'same-origin' });
  if (!resp.ok) throw new Error(`lista de widgets externos HTTP ${resp.status}`);
  for (const item of (await resp.json()).itens || []) {
    try {
      const manifesto = validarManifesto({ ...item.manifesto });
      const texto = await textoVerificado(item);
      modulosVerificados.set(item.nome, texto);
      await i18nDoPacote(item, manifesto, avisos);
      const emSandbox = item.sandbox === true;
      REGISTRO.set(item.nome, Object.freeze({
        ...manifesto,
        // modo normal: o motor importa o TEXTO verificado (blob); sandbox: quem monta é o hospedeiro
        modulo: emSandbox
          ? `/api/widgets/externos/${encodeURIComponent(item.nome)}/modulo.js`
          : URL.createObjectURL(new Blob([absoluto(texto)], { type: 'text/javascript' })),
        sandbox: emSandbox,
        sha256: item.sha256,
      }));
      registrados.push(item.nome);
    } catch (erro) {
      recusados.push({ nome: item.nome, motivo: erro.message });
    }
  }
  return { registrados, recusados, avisos };
}
