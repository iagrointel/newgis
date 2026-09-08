/* plat — aplica o tema escolhido ANTES da primeira pintura (script clássico, síncrono, no <head> de toda página).
   Lê localStorage plat_tema ('claro' | 'escuro'; ausente = sistema) e põe data-theme em <html>. Sem isto a página
   pinta no tema do sistema e troca um instante depois. Espelha ATRIBUTO de js/base/componentes/tema.js. */
(function () {
  try {
    var v = localStorage.getItem('plat_tema');
    if (v === 'claro') document.documentElement.setAttribute('data-theme', 'light');
    else if (v === 'escuro') document.documentElement.setAttribute('data-theme', 'dark');
  } catch (e) { /* sem armazenamento: fica o tema do sistema */ }
})();
