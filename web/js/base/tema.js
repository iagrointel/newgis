/* plat — tema e densidade (item L0-14-identidade-visual). Script CLÁSSICO (não módulo), carregado no <head> de
   toda tela ANTES da primeira pintura, para a escolha guardada valer sem piscar. Três estados de tema (regra da
   casa): "sistema" (nenhum atributo, prefers-color-scheme decide), "claro" e "escuro" (html[data-theme]).
   Três de densidade: compacta, normal, confortavel (html[data-densidade], muda só o passo da grade de
   espaçamento em tokens.css). Guarda em localStorage (plat_tema, plat_densidade); sem localStorage segue
   sem lembrar. Expõe window.platTema para a barra lateral e a página /estilo. */
(function () {
  const CHAVE_TEMA = 'plat_tema';
  const CHAVE_DENSIDADE = 'plat_densidade';
  const TEMAS = ['sistema', 'claro', 'escuro'];
  const DENSIDADES = ['compacta', 'normal', 'confortavel'];
  const raiz = document.documentElement;

  function ler(chave) { try { return localStorage.getItem(chave); } catch { return null; } }
  function guardar(chave, valor) { try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: segue sem lembrar */ } }

  function aplicarTema(tema) {
    if (tema === 'claro') raiz.setAttribute('data-theme', 'light');
    else if (tema === 'escuro') raiz.setAttribute('data-theme', 'dark');
    else raiz.removeAttribute('data-theme');
  }
  function aplicarDensidade(d) {
    if (d === 'compacta' || d === 'confortavel') raiz.setAttribute('data-densidade', d);
    else raiz.removeAttribute('data-densidade');
  }
  function temaAtual() { const v = ler(CHAVE_TEMA); return TEMAS.includes(v) ? v : 'sistema'; }
  function densidadeAtual() { const v = ler(CHAVE_DENSIDADE); return DENSIDADES.includes(v) ? v : 'normal'; }

  aplicarTema(temaAtual());
  aplicarDensidade(densidadeAtual());

  window.platTema = {
    TEMAS, DENSIDADES, temaAtual, densidadeAtual,
    definirTema(t) { if (!TEMAS.includes(t)) return; guardar(CHAVE_TEMA, t); aplicarTema(t); document.dispatchEvent(new CustomEvent('plat:tema', { detail: { tema: t } })); },
    definirDensidade(d) { if (!DENSIDADES.includes(d)) return; guardar(CHAVE_DENSIDADE, d); aplicarDensidade(d); document.dispatchEvent(new CustomEvent('plat:densidade', { detail: { densidade: d } })); },
    /* tema efetivo (o que o navegador pinta agora): 'claro' ou 'escuro' */
    efetivo() {
      const t = raiz.getAttribute('data-theme');
      if (t === 'light') return 'claro';
      if (t === 'dark') return 'escuro';
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'claro' : 'escuro';
    },
  };
})();
