/* plat — tela /videos (item L7-04-d-videos-por-tarefa): lista os vídeos gerados por `make videos`
   a partir do manifesto em GET /api/videos; cada cartão tem o player (com as 3 legendas) e a seção
   do manual a que o vídeo corresponde. Sessão de usuário; arquivo em /videos/arquivo/{nome}. */
import { obter, mensagemDe } from './base/api.js';
import { h } from './base/dom.js';
import { carregar } from './base/i18n.js';
import './base/componentes.js';
import { montarLayout, pronto } from './base/layout.js';
import { exigirSessao } from './auth/sessao.js';

const IDIOMAS = [['pt-BR', 'português'], ['en', 'inglês'], ['es', 'espanhol']];

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario });
  const r = await obter('/api/videos');
  if (r.status === 404) {
    document.getElementById('videos-vazio').hidden = false;
    document.getElementById('videos-total').textContent = '0';
    return;
  }
  if (r.status !== 200) {
    document.getElementById('aviso').mostrar(mensagemDe(r), 'falha');
    return;
  }
  const m = r.json;
  const ids = Object.keys(m.tarefas ?? {}).sort();
  document.getElementById('videos-total').textContent = String(ids.length);
  const lista = document.getElementById('videos-lista');
  for (const id of ids) {
    const v = m.tarefas[id];
    const cartao = h('article', { class: 'cartao video-cartao' },
      h('h3', {}, v.titulo),
      h('video', {
        controls: '', preload: 'metadata', width: 640, style: 'max-width: 100%; height: auto',
        src: `/videos/arquivo/${v.arquivo}`,
      }, ...IDIOMAS.map(([sigla, nome], i) => h('track', {
        kind: 'subtitles', srclang: sigla, label: nome,
        src: `/videos/arquivo/${id}.${sigla}.vtt`, default: i === 0 ? '' : undefined,
      }))),
      h('p', { class: 'ajuda' },
        `seção do manual: ${v.manual} · ${v.duracao_s} s · ${v.passos} passos · narração ${m.idioma_narracao}`),
    );
    lista.append(cartao);
  }
}
