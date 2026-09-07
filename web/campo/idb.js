/* plat — IndexedDB do PWA de campo (item L2-07-a-pwa-instalavel-cache). Fonte de verdade offline: o service
   worker só cacheia o SHELL (HTML/CSS/JS/manifest/ícone); dado de negócio (token, mapas, fila) mora aqui,
   por banco isolado por origem — o mesmo navegador em outro inquilino não enxerga este banco (isolamento do
   próprio IndexedDB por origem; a chave do registro carrega o `tenant_slug` como cinto e suspensório, para o
   caso de dois logins em abas do MESMO inquilino nunca se confundirem entre si). Nunca loga o token: as
   funções abaixo devolvem/gravam o valor, e quem chama é responsável por não passá-lo a console/log. */

const NOME_BANCO = 'plat_campo';
const VERSAO_BANCO = 1;

function abrir() {
  return new Promise((resolve, reject) => {
    const pedido = indexedDB.open(NOME_BANCO, VERSAO_BANCO);
    pedido.onupgradeneeded = () => {
      const db = pedido.result;
      if (!db.objectStoreNames.contains('config')) db.createObjectStore('config', { keyPath: 'chave' });
      if (!db.objectStoreNames.contains('mapas')) db.createObjectStore('mapas', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('fila')) db.createObjectStore('fila', { keyPath: 'id', autoIncrement: true });
    };
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(pedido.error);
  });
}

async function transacao(nomeLoja, modo, fn) {
  const db = await abrir();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(nomeLoja, modo);
    const loja = tx.objectStore(nomeLoja);
    const saida = fn(loja);
    tx.oncomplete = () => resolve(saida);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export async function gravarConfig(chave, valor) {
  return transacao('config', 'readwrite', (loja) => loja.put({ chave, valor }));
}

export async function lerConfig(chave) {
  const db = await abrir();
  return new Promise((resolve, reject) => {
    const req = db.transaction('config', 'readonly').objectStore('config').get(chave);
    req.onsuccess = () => resolve(req.result ? req.result.valor : null);
    req.onerror = () => reject(req.error);
  });
}

export async function apagarConfig(chave) {
  return transacao('config', 'readwrite', (loja) => loja.delete(chave));
}

export async function gravarMapas(mapas) {
  return transacao('mapas', 'readwrite', (loja) => {
    for (const mapa of mapas) loja.put(mapa);
  });
}

export async function limparMapas() {
  return transacao('mapas', 'readwrite', (loja) => loja.clear());
}

export async function listarMapas() {
  const db = await abrir();
  return new Promise((resolve, reject) => {
    const req = db.transaction('mapas', 'readonly').objectStore('mapas').getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

export async function contarFila() {
  const db = await abrir();
  return new Promise((resolve, reject) => {
    const req = db.transaction('fila', 'readonly').objectStore('fila').count();
    req.onsuccess = () => resolve(req.result || 0);
    req.onerror = () => reject(req.error);
  });
}

export async function enfileirar(operacao) {
  return transacao('fila', 'readwrite', (loja) => loja.add(operacao));
}
