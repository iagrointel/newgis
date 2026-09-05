/* plat — loja de estado própria (L5_CONCEITO D1: Custom Elements + loja de ≈ 3 kB, sem framework).
   Estado imutável por cópia rasa; assinantes por chave; EventTarget nativo como transporte (D5). */

export function criarLoja(inicial = {}) {
  let estado = { ...inicial };
  const alvo = new EventTarget();
  return {
    obter() { return estado; },
    ler(chave) { return estado[chave]; },
    definir(parcial) {
      const antes = estado;
      estado = { ...estado, ...parcial };
      alvo.dispatchEvent(new CustomEvent('mudou', { detail: { antes, agora: estado, chaves: Object.keys(parcial) } }));
    },
    atualizar(chave, fn) { this.definir({ [chave]: fn(estado[chave]) }); },
    assinar(fn, chaves) {
      const h = (e) => {
        if (!chaves || chaves.some((k) => e.detail.chaves.includes(k))) fn(e.detail.agora, e.detail);
      };
      alvo.addEventListener('mudou', h);
      return () => alvo.removeEventListener('mudou', h);
    },
  };
}

/* loja global das telas: usuário da sessão, tela ativa, ocupado (requisição em curso) */
export const loja = criarLoja({ usuario: null, tela: null, ocupado: false });

/* privilégio do usuário da sessão (ADR 0002 seção 3: a tela pergunta privilégio, nunca perfil) */
export function tem(privilegio, usuario = loja.ler('usuario')) {
  return !!usuario && Array.isArray(usuario.privilegios) && usuario.privilegios.includes(privilegio);
}
