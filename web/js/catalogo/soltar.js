/* plat · catálogo — arrastar e soltar arquivos sobre a lista para criar itens (UX-03). A área #lista-area recebe
   dragover/drop; cada arquivo solto sobe pelo MESMO caminho de "Novo item > Arquivo" (novo.js::enviarArquivoComoItem:
   upload retomável por partes, conferência de tipo no servidor, item 'arquivo' criado ao concluir). Um <plat-estado>
   de progresso mostra arquivo a arquivo; ao fim, a lista recarrega e o último item criado abre. Alternativa sem
   arrasto (WCAG 2.5.7): o botão "Novo item > Arquivo" continua fazendo o mesmo. Quem não tem conteudo.criar não vê
   a área ativa (o drop é ignorado com aviso de permissão). */
import { h } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import { bytes, LIMITES } from './formato.js';
import { enviarArquivoComoItem } from './novo.js';

const el = (id) => document.getElementById(id);
let aoCriados = () => {};
let ocupado = false;

export function iniciar({ criados }) {
  aoCriados = criados;
  const area = el('lista-area');
  const veu = h('div', { class: 'soltar-veu', id: 'soltar-veu', hidden: true, 'aria-hidden': 'true' },
    h('p', { class: 'soltar-titulo' }, t('catalogo.soltar_aqui')), h('p', { class: 'fraco' }, t('catalogo.soltar_ajuda', { max: bytes(LIMITES.uploadBytes) })));
  area.append(veu);
  let profundidade = 0;
  const temArquivo = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  area.addEventListener('dragenter', (e) => { if (!temArquivo(e)) return; e.preventDefault(); profundidade += 1; mostrar(true); });
  area.addEventListener('dragover', (e) => { if (!temArquivo(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = tem('conteudo.criar') ? 'copy' : 'none'; });
  area.addEventListener('dragleave', () => { profundidade = Math.max(0, profundidade - 1); if (!profundidade) mostrar(false); });
  area.addEventListener('drop', async (e) => {
    if (!temArquivo(e)) return;
    e.preventDefault();
    profundidade = 0;
    mostrar(false);
    await soltar([...e.dataTransfer.files]);
  });
}

function mostrar(sim) {
  el('lista-area').classList.toggle('sobre', sim);
  el('soltar-veu').hidden = !sim;
}

export async function soltar(arquivos) {
  const aviso = el('aviso');
  if (!arquivos.length) return;
  if (!tem('conteudo.criar')) { aviso.mostrar(t('erro.sem_permissao', { privilegio: 'conteudo.criar' }), 'atencao'); return; }
  if (ocupado) { aviso.mostrar(t('catalogo.soltar_ocupado'), 'atencao'); return; }
  ocupado = true;
  const estado = el('lista-estado');
  const criados = [];
  const falhas = [];
  try {
    for (const [i, f] of arquivos.entries()) {
      estado.mostrar({ tipo: 'carregando', titulo: t('catalogo.soltar_enviando', { n: i + 1, total: arquivos.length, nome: f.name }), texto: bytes(f.size) });
      try {
        const item = await enviarArquivoComoItem(f, { aoProgresso: (texto) => { const p = estado.querySelector('.estado-texto'); if (p) p.textContent = `${bytes(f.size)} · ${texto}`; } });
        if (item) criados.push(item);
      } catch (err) {
        falhas.push(`${f.name}: ${err.message}`);
      }
    }
  } finally {
    ocupado = false;
    estado.limpar();
  }
  if (criados.length) aviso.mostrar(t('catalogo.soltar_criados', { n: criados.length }), falhas.length ? 'atencao' : 'ok');
  if (falhas.length) aviso.mostrar(`${criados.length ? `${t('catalogo.soltar_criados', { n: criados.length })} · ` : ''}${t('catalogo.soltar_falhas', { n: falhas.length })}: ${falhas.join('; ')}`, 'erro');
  aoCriados(criados);
}
