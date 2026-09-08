/* plat — autosave de rascunho + cópia local para queda de rede (item L5-09-desfazer-refazer-rascunho).

   Dois lugares gravam o MESMO documento por caminhos diferentes, e nenhum dos dois é a versão publicada:

   1. servidor: a cada `intervaloMs` (se o documento mudou desde o último autosave), `PATCH /api/itens/{id}
      ?rotulo=rascunho` grava uma versão nova em `plat.item_versao` com `rotulo='rascunho'` — a MESMA rota do
      botão Salvar, só com o rótulo trocado (`app/catalogo/rotas_itens.py::editar_parcial`). `versao_publicada`
      só muda em POST .../publicar (rota do L5-05), então o link público de quem já publicou continua servindo
      a versão antiga durante e depois do autosave — é o que a cláusula 4 do portão mede.
   2. navegador: TODA mudança (não só a cada N segundos) grava em `localStorage` sob
      `plat_rascunho_<idDoItem>` — para o caso de a rede cair NO MEIO da edição, antes do próximo autosave.
      Ao reabrir a mesma tela, se houver uma cópia local mais nova que a versão do servidor, `recuperar()`
      devolve os dados e QUEM CHAMA decide avisar e oferecer restaurar — este módulo nunca troca o documento
      sozinho. Envio ao servidor com sucesso limpa a cópia local (não há mais nada a recuperar).

   `armazenamento` é injetável (localStorage por padrão) para os testes de unidade rodarem em Node sem DOM. */

function chaveDe(idItem) { return `plat_rascunho_${idItem}`; }

function guardarLocal(armazenamento, chave, valor) {
  try { armazenamento.setItem(chave, JSON.stringify(valor)); return true; } catch { return false; }
}
function lerLocal(armazenamento, chave) {
  try {
    const bruto = armazenamento.getItem(chave);
    return bruto ? JSON.parse(bruto) : null;
  } catch { return null; }
}
function apagarLocal(armazenamento, chave) {
  try { armazenamento.removeItem(chave); } catch { /* sem armazenamento: segue */ }
}

export function criarAutosave({
  idItem,
  obterDocumento,
  obterVersaoBase,
  salvarNoServidor, // async (documento, versaoBase) => {ok, versao, erro}
  intervaloMs = 20000,
  armazenamento = (typeof localStorage !== 'undefined' ? localStorage : null),
  agora = () => Date.now(),
  aoCiclo = null, // (resultado de cicloDeSalvar) => void — só para a tela mostrar "rascunho salvo" ou o erro
}) {
  const chave = chaveDe(idItem);
  let ultimoEnviado = null; // json canônico do último documento que já está em algum lugar seguro (local ou servidor)
  let temporizador = null;
  let emVoo = false;

  /* grava a cópia local SEMPRE que o documento muda — não espera o intervalo do autosave de servidor.
     `pendente: true` marca que ainda não foi confirmada pelo servidor; ao confirmar, o chamador chama
     `confirmarServidor` e a cópia local não fica mais "pendente" (mas só é APAGADA de vez quando o
     documento local volta a bater com o que está gravado — ver `confirmarServidor`). */
  function registrarLocal(documento, { versaoBase = obterVersaoBase?.() ?? null } = {}) {
    if (!armazenamento) return false;
    return guardarLocal(armazenamento, chave, {
      documento, versao_base: versaoBase, salvo_em: agora(), pendente: true,
    });
  }

  function recuperar() {
    if (!armazenamento) return null;
    return lerLocal(armazenamento, chave);
  }

  function limparLocal() { if (armazenamento) apagarLocal(armazenamento, chave); }

  /* depois que o servidor confirma a versão de rascunho (ou o Salvar normal), a cópia local deste MESMO
     documento não protege mais nada — se ficasse, uma queda de rede LEGÍTIMA depois disso reapareceria como
     "recuperado do armazenamento local" para um documento que já está seguro. */
  function confirmarServidor(documento) {
    ultimoEnviado = JSON.stringify(documento);
    limparLocal();
  }

  async function cicloDeSalvar() {
    if (emVoo) return { pulado: true };
    const documento = obterDocumento();
    const texto = JSON.stringify(documento);
    if (texto === ultimoEnviado) return { inalterado: true };
    emVoo = true;
    try {
      const r = await salvarNoServidor(documento, obterVersaoBase?.() ?? null);
      if (r && r.ok) { confirmarServidor(documento); return { ok: true, versao: r.versao }; }
      // falhou (rede caiu, 5xx, conflito): a cópia local já tinha sido gravada por registrarLocal a cada
      // mudança — não perde nada; só marca a hora da última tentativa para quem monta o aviso na tela.
      return { ok: false, erro: r?.erro ?? 'falha_desconhecida' };
    } catch (e) {
      return { ok: false, erro: String(e) };
    } finally {
      emVoo = false;
    }
  }

  function iniciar() {
    parar();
    temporizador = setInterval(async () => { aoCiclo?.(await cicloDeSalvar()); }, intervaloMs);
    return temporizador;
  }
  function parar() { if (temporizador) { clearInterval(temporizador); temporizador = null; } }

  return {
    registrarLocal, recuperar, limparLocal, confirmarServidor, cicloDeSalvar, iniciar, parar,
    // exposto para teste: intervalo configurado e se há ciclo ativo
    ativo: () => temporizador !== null,
  };
}
