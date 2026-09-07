/* plat — PWA de campo (item L2-07-a-pwa-instalavel-cache). Módulo ES sem build; cache resolvido por
   `no-store` na resposta de `/campo/app.js` (app/campo/rotas.py), então NUNCA `?v=` neste import — duas URLs
   do mesmo módulo seriam duas instâncias, e aqui uma delas ganharia o service worker e a outra não. */
import {
  gravarConfig, lerConfig, apagarConfig, gravarMapas, limparMapas, listarMapas, contarFila,
} from './idb.js';

const CHAVE_TOKEN = 'token_campo';
let promoverInstalacao = null;

function elemento(id) {
  return document.getElementById(id);
}

function mostrarAviso(texto) {
  const el = elemento('aviso-token');
  el.textContent = texto;
  el.hidden = !texto;
}

function atualizarEstadoRede() {
  const el = elemento('estado-rede');
  const online = navigator.onLine;
  el.dataset.estado = online ? 'online' : 'offline';
  el.textContent = online ? 'online' : 'offline — dados locais';
}

async function registrarServiceWorker() {
  if (!('serviceWorker' in navigator)) return null;
  try {
    const registro = await navigator.serviceWorker.register('/campo/sw.js', { scope: '/campo/' });
    // checagem de versão nova a cada abertura, EM SEGUNDO PLANO (nunca bloqueia a tela atual): é o que faz
    // uma troca de versão valer na PRÓXIMA recarga, e não na recarga-depois-da-recarga — o navegador só
    // troca o controlador de uma aba já aberta depois que install+activate terminam (skipWaiting +
    // clients.claim no sw.js), e isso não dá tempo de acontecer dentro da MESMA navegação que descobriu a
    // versão nova; abrir a checagem cedo (aqui, e não só quando o usuário recarrega) é o que garante que,
    // da PRÓXIMA vez que a pessoa abrir ou recarregar o app, o shell já esteja pronto.
    registro.update().catch(() => {});
    return registro;
  } catch {
    return null; // sem SW o app ainda funciona online; só perde o offline
  }
}

function capturarPromptDeInstalacao() {
  window.addEventListener('beforeinstallprompt', (evento) => {
    evento.preventDefault();
    promoverInstalacao = evento;
    elemento('secao-instalar').hidden = false;
  });
  elemento('botao-instalar').addEventListener('click', async () => {
    if (!promoverInstalacao) return;
    await promoverInstalacao.prompt();
    promoverInstalacao = null;
    elemento('secao-instalar').hidden = true;
  });
  window.addEventListener('appinstalled', () => {
    elemento('secao-instalar').hidden = true;
  });
}

function renderizarMapas(mapas) {
  const lista = elemento('lista-mapas');
  const semMapas = elemento('sem-mapas');
  lista.innerHTML = '';
  semMapas.hidden = mapas.length > 0;
  for (const mapa of mapas) {
    const li = document.createElement('li');
    const titulo = document.createElement('span');
    titulo.className = 'titulo';
    titulo.textContent = mapa.titulo;
    const meta = document.createElement('span');
    meta.className = 'meta';
    const camadas = Array.isArray(mapa.camadas) ? mapa.camadas.length : 0;
    meta.textContent = `${camadas} camada(s) · atualizado em ${new Date(mapa.modificado_em).toLocaleDateString('pt-BR')}`;
    li.append(titulo, meta);
    lista.append(li);
  }
}

async function renderizarFila() {
  const n = await contarFila();
  elemento('fila-contagem').textContent = n === 1 ? '1 pendente' : `${n} pendentes`;
}

async function medirArmazenamento() {
  const el = elemento('armazenamento-estimativa');
  if (!navigator.storage || !navigator.storage.estimate) {
    el.textContent = 'estimativa de armazenamento indisponível neste navegador';
    return;
  }
  const { usage, quota } = await navigator.storage.estimate();
  const mb = (n) => (n / (1024 * 1024)).toFixed(1);
  el.textContent = `${mb(usage || 0)} MB usados de ${mb(quota || 0)} MB disponíveis`;
}

async function configurarPersistencia() {
  const botao = elemento('pedir-persistencia');
  const estadoEl = elemento('persistencia-estado');
  if (!navigator.storage || !navigator.storage.persist) {
    botao.disabled = true;
    estadoEl.textContent = 'pedido de persistência indisponível neste navegador';
    return;
  }
  if (await navigator.storage.persisted()) {
    estadoEl.textContent = 'armazenamento já persistente: não é limpo sob pouco espaço';
  }
  botao.addEventListener('click', async () => {
    const concedida = await navigator.storage.persist();
    estadoEl.textContent = concedida
      ? 'concedida: os dados de campo não são limpos automaticamente sob pouco espaço'
      : 'negada pelo navegador (critério do próprio navegador, não da aplicação)';
  });
}

async function obterSessaoAtual() {
  // GET /api/eu pela sessão de cookie (se houver): usado só para conferir de QUAL inquilino é a sessão
  // ativa, nunca para autenticar chamada de negócio (essas sempre vão pelo token, credentials: 'omit').
  try {
    const resp = await fetch('/api/eu', { credentials: 'same-origin', cache: 'no-store' });
    if (resp.status !== 200) return null;
    const corpo = await resp.json();
    return { tenant_slug: corpo.inquilino && corpo.inquilino.slug };
  } catch {
    return null;
  }
}

async function obterTokenDeSessao() {
  // exige sessão de cookie (mesma origem): só funciona online e logado na app principal. Se não houver
  // sessão, a resposta é 401 e o campo segue sem token (usa o que já tiver em cache local, se houver).
  const resp = await fetch('/api/campo/sessao', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  if (resp.status !== 201) return null;
  const corpo = await resp.json();
  return corpo; // { token, id, escopos, expira_em, tenant_slug }
}

async function sincronizarMapas(config) {
  if (!config) return { ok: false, motivo: 'sem_token' };
  try {
    // credentials: 'omit' de propósito: o servidor rejeita cookie de sessão E cabeçalho Authorization juntos
    // na mesma chamada (400 autenticacao_ambigua, defesa contra confused-deputy) — o PWA de campo sempre fala
    // pelo token, nunca pelo cookie, mesmo quando o mesmo navegador também tem uma sessão da app principal.
    const resp = await fetch('/api/campo/mapas', {
      cache: 'no-store',
      credentials: 'omit',
      headers: { Authorization: `Bearer ${config.token}` },
    });
    if (resp.status === 401) {
      const corpo = await resp.json().catch(() => ({}));
      return { ok: false, motivo: corpo.erro || 'nao_autorizado' };
    }
    if (!resp.ok) return { ok: false, motivo: 'erro_servidor' };
    const corpo = await resp.json();
    await gravarMapas(corpo.mapas);
    return { ok: true, mapas: corpo.mapas };
  } catch {
    return { ok: false, motivo: 'sem_rede' };
  }
}

async function iniciar() {
  atualizarEstadoRede();
  window.addEventListener('online', atualizarEstadoRede);
  window.addEventListener('offline', atualizarEstadoRede);
  capturarPromptDeInstalacao();
  await registrarServiceWorker();
  await medirArmazenamento();
  await configurarPersistencia();

  // 1) mostra o que já está em cache local (funciona sem rede)
  renderizarMapas(await listarMapas());
  await renderizarFila();

  // 2) se online, garante/renova o token de campo e tenta sincronizar; nada disto bloqueia a renderização
  //    acima — o app já abriu com o que tinha, a sincronização só atualiza por cima.
  let config = await lerConfig(CHAVE_TOKEN);
  if (navigator.onLine) {
    // isolamento entre inquilinos no MESMO navegador: o IndexedDB é isolado por origem, não por inquilino
    // (dois logins diferentes no mesmo `plat_sessao` de cookie caem no mesmo banco). Se há sessão de cookie
    // ativa e o inquilino dela não bate com o `tenant_slug` salvo, o config e os mapas são de um login
    // ANTERIOR — descarta os dois antes de sincronizar, nunca mistura dado de dois inquilinos na tela.
    const sessaoAtual = await obterSessaoAtual();
    if (sessaoAtual && config && config.tenant_slug !== sessaoAtual.tenant_slug) {
      await apagarConfig(CHAVE_TOKEN);
      await limparMapas();
      config = null;
      renderizarMapas([]);
    }
    if (!config) {
      const nova = await obterTokenDeSessao();
      if (nova) {
        config = nova;
        await gravarConfig(CHAVE_TOKEN, config);
      }
    }
    const resultado = await sincronizarMapas(config);
    if (resultado.ok) {
      mostrarAviso('');
      renderizarMapas(resultado.mapas);
    } else if (resultado.motivo === 'token_revogado' || resultado.motivo === 'token_expirado') {
      // token bloqueado: aviso, mas o dado local (mapas e fila já em IndexedDB) continua intacto — não apaga
      mostrarAviso('sincronização bloqueada: o token de campo foi revogado ou expirou. Os dados já baixados '
        + 'continuam disponíveis; entre na aplicação principal para gerar um novo token de campo.');
      await apagarConfig(CHAVE_TOKEN);
    } else if (resultado.motivo === 'sem_token') {
      mostrarAviso('sem token de campo: entre na aplicação principal com rede pelo menos uma vez para '
        + 'baixar os mapas de campo.');
    }
  } else if (!config) {
    mostrarAviso('sem rede e sem token de campo salvo: entre com rede pelo menos uma vez antes de ir a campo.');
  }

  document.body.dataset.pronto = '1';
}

await iniciar();
