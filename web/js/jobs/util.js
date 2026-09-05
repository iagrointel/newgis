/* plat · tarefas — utilidades que a base (js/base/dom.js) não tem: elemento obrigatório por id, download de texto
   gerado no navegador e preenchimento de <select>. Tudo o mais (h, limpar, marcador) vem da base. */
import { h, limpar } from '../base/dom.js';
import { loja } from '../base/estado.js';

/* modo só-leitura da tela Tarefas (T2, migração 015): com jobs.ver e sem jobs.executar a tela lista e não oferece
   cancelar, repetir nem agendas. A tela pergunta PRIVILÉGIO, nunca perfil (ADR 0002 seção 3). Sem usuário na loja
   (/api/eu ainda não publicada) assume-se que pode: quem decide de verdade é o servidor. */
export function podeExecutar() {
  const u = loja.ler('usuario');
  return !u || !Array.isArray(u.privilegios) || u.privilegios.includes('jobs.executar');
}

export function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

/* baixa um texto como arquivo (CSV da página, log do job); não há rota de arquivo para isto no item */
export function baixar(nome, conteudo, tipo = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([conteudo], { type: tipo }));
  const a = h('a', { href: url, download: nome });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* preenche um <select> com [{valor, texto}] mantendo a primeira opção ("todos") quando pedido */
export function opcoes(select, itens, { manterPrimeira = true } = {}) {
  const primeira = manterPrimeira ? select.firstElementChild : null;
  limpar(select);
  if (primeira) select.append(primeira);
  for (const { valor, texto } of itens) select.append(h('option', { value: valor }, texto));
}

/* mostra ou limpa um <plat-aviso> pelo id */
export function aviso(id, texto, tipo = 'erro') {
  const n = document.getElementById(id);
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}
