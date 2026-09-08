/* plat — utilidades dos widgets de dado (L5-01-c): download de texto gerado no navegador e carga do Chart.js
   (vendido em web/vendor, D21) só quando a tela tem gráfico. */
export function baixarTexto(nome, texto, tipo = 'text/plain;charset=utf-8') {
  const blob = new Blob([texto], { type: tipo });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = nome; a.rel = 'noopener'; a.hidden = true;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

let chartPromessa = null;
export function carregarChart() {
  if (globalThis.Chart) return Promise.resolve(globalThis.Chart);
  if (!chartPromessa) {
    chartPromessa = import('/static/vendor/chart-4.5.1.umd.min.js').then(() => globalThis.Chart || null).catch(() => null);
  }
  return chartPromessa;
}
