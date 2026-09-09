/* Widget de exemplo da casa (L5-36) — semáforo por seleção. Pacote em SANDBOX: corre num iframe de
   origem opaca, fala com a página só por window.plat (registrar/emitir) — sem rede, sem cookie, e o que
   chega da página são as ações que o manifesto declarou. Um clique da tabela com N ids pinta o nível:
   1 verde, 2 amarelo, 3 ou mais vermelho. */
const CORES = { verde: '#1a7f37', amarelo: '#9a6700', vermelho: '#c62828', cinza: '#57606a' };

window.plat.registrar({
  luz: null,

  montar(raiz) {
    raiz.replaceChildren();
    const rotulo = document.createElement('div');
    rotulo.textContent = window.plat.configuracao.rotulo || 'semáforo';
    this.luz = document.createElement('div');
    this.luz.style.cssText = 'width:56px;height:56px;border-radius:50%;margin-top:8px';
    raiz.append(rotulo, this.luz);
    this.pintar(window.plat.configuracao.nivel || 'cinza');
  },

  pintar(nivel) {
    if (!this.luz) return;
    this.luz.style.background = CORES[nivel] || CORES.cinza;
    this.luz.setAttribute('data-nivel', nivel);
    window.plat.emitir('semaforo.nivel', { nivel });
  },

  /* ação da página: a ligação do documento entrega o clique/seleção da tabela */
  acao(nome, detalhe) {
    if (nome === 'semaforo.nivel') return this.pintar(String(detalhe?.nivel || 'cinza'));
    if (nome === 'clique' || nome === 'selecao_mudou') {
      const n = (detalhe?.ids || []).length;
      this.pintar(n >= 3 ? 'vermelho' : n === 2 ? 'amarelo' : 'verde');
    }
  },
});
