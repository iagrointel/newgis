/* plat — paleta da NARRATIVA (item L5-04-a-blocos-de-conteudo): os tipos de bloco que o editor de arrasto
   compartilhado (web/js/editor/editor.js, L5-08) sabe pôr na tela quando o item é do tipo `narrativa`.

   Uma narrativa é uma LISTA de blocos, na ordem de leitura, sem aninhamento (nenhum tipo aceita filhos) e cada
   bloco ocupa a largura toda (12 colunas): reordenar por arrasto ou por teclado é mover na lista, que é o que
   `documento.js` já faz. O editor não conhece nenhum destes tipos — recebe esta paleta e trabalha com ela; quem
   dá forma a cada bloco em leitura é `web/js/narrativa/leitor.js`, que lê o MESMO documento.

   Regras de segurança gravadas no esquema (o servidor valida o mesmo em `app/catalogo/narrativa.py` ao
   publicar): imagem/capa com imagem exigem texto alternativo; endereços de mídia só do próprio servidor
   (`/api/objetos/...`, `/static/...`) ou https; embed só https (o leitor põe o iframe em sandbox); texto é
   Markdown (D23) e passa pelo DOMPurify na leitura. */

import { montarMapa, vistaAtual } from '../narrativa/mapa_bloco.js';

const URL_PROPRIA_OU_HTTPS = '^(/(?!/)[A-Za-z0-9._~!$&()*+,;=:@%/-]*|https://[^\\s<>"\']+)$';
const URL_PROPRIA = '^/(?!/)[A-Za-z0-9._~!$&()*+,;=:@%/-]*$';
const UUID = '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

const alternativo = (title = 'Texto alternativo') => ({
  type: 'string', title, minLength: 1, maxLength: 250,
  description: 'obrigatório: descreve a imagem para quem não a vê; a publicação recusa imagem sem ele',
});
const legenda = { type: 'string', title: 'Legenda', maxLength: 400 };

function bloco(rotulo, propriedades_padrao, properties, required = [], extra = {}) {
  return {
    rotulo, aceita_filhos: false, largura_padrao: 12, propriedades_padrao,
    esquema: { type: 'object', additionalProperties: false, required, properties },
    ...extra,
  };
}

export const TIPOS_BLOCO = ['capa', 'texto', 'imagem', 'video', 'audio', 'mapa', 'tabela', 'botao', 'separador',
  'incorporar', 'aplicativo'];

export const PALETA_NARRATIVA = {
  nome: 'narrativa',
  ordem: TIPOS_BLOCO,
  tipos: {
    capa: bloco('Título e capa', { titulo: 'Título da narrativa', subtitulo: '' }, {
      titulo: { type: 'string', title: 'Título', minLength: 1, maxLength: 200 },
      subtitulo: { type: 'string', title: 'Subtítulo', maxLength: 400 },
      imagem: { type: 'string', title: 'Imagem de capa (endereço)', pattern: URL_PROPRIA_OU_HTTPS, maxLength: 800 },
      alternativo: { ...alternativo('Texto alternativo da capa'), minLength: 0 },
    }, ['titulo']),
    texto: bloco('Texto', { markdown: 'Escreva aqui. **Negrito**, *itálico*, [link](https://exemplo.org), listas e títulos com #.' }, {
      markdown: { type: 'string', title: 'Texto (Markdown)', minLength: 1, maxLength: 20000 },
      alinhamento: { type: 'string', title: 'Alinhamento', enum: ['esquerda', 'centro', 'justificado'], default: 'esquerda' },
    }, ['markdown']),
    imagem: bloco('Imagem', { url: '/static/favicon.svg', alternativo: '', legenda: '' }, {
      url: { type: 'string', title: 'Endereço', pattern: URL_PROPRIA_OU_HTTPS, maxLength: 800 },
      alternativo: { ...alternativo(), minLength: 0 },
      legenda,
      largura: { type: 'string', title: 'Largura', enum: ['coluna', 'larga', 'inteira'], default: 'coluna' },
    }, ['url', 'alternativo']),
    video: bloco('Vídeo', { url: '', legenda: '', descricao: '' }, {
      url: { type: 'string', title: 'Arquivo do inquilino (/api/objetos/...) ou endereço https (YouTube, Vimeo)',
        pattern: URL_PROPRIA_OU_HTTPS, maxLength: 800 },
      legenda,
      descricao: { type: 'string', title: 'Descrição acessível', maxLength: 400 },
    }, ['url']),
    audio: bloco('Áudio', { url: '', legenda: '' }, {
      url: { type: 'string', title: 'Arquivo do inquilino (/api/objetos/...)', pattern: URL_PROPRIA, maxLength: 800 },
      legenda,
      descricao: { type: 'string', title: 'Descrição acessível (transcrição curta)', maxLength: 1000 },
    }, ['url']),
    mapa: bloco('Mapa', { legenda: '', filtro: '' }, {
      mapa_id: { type: 'string', title: 'Item de mapa do catálogo (uuid)', pattern: UUID },
      legenda,
      filtro: { type: 'string', title: 'Filtro (campo = valor)', maxLength: 2000 },
      /* a vista salva é escrita pelo controle personalizado do painel (mapa interativo): caixa [oeste, sul,
         leste, norte], centro, zoom, rotação, proporção altura/largura e camadas visíveis — é a caixa que o
         leitor reabre, com a mesma proporção, para o bbox bater em qualquer viewport (portão: ± 1 %) */
      vista: {
        type: 'object', title: 'Vista salva', additionalProperties: false,
        required: ['bbox', 'centro', 'zoom', 'proporcao'],
        properties: {
          bbox: { type: 'array', minItems: 4, maxItems: 4, items: { type: 'number' } },
          centro: { type: 'array', minItems: 2, maxItems: 2, items: { type: 'number' } },
          zoom: { type: 'number', minimum: 0, maximum: 24 },
          rotacao: { type: 'number', minimum: -360, maximum: 360 },
          proporcao: { type: 'number', minimum: 0.2, maximum: 3 },
          camadas: { type: 'array', maxItems: 100, items: { type: 'string', pattern: UUID } },
        },
      },
    }, [], { personalizados: ['vista'], controle: controleDeVista, resumo: resumoDeMapa }),
    tabela: bloco('Tabela', { cabecalho: 'coluna A | coluna B', linhas: 'valor 1 | valor 2\nvalor 3 | valor 4', legenda: '' }, {
      cabecalho: { type: 'string', title: 'Cabeçalho (células separadas por |)', minLength: 1, maxLength: 2000 },
      linhas: { type: 'string', title: 'Linhas (uma por linha, células separadas por |)', maxLength: 20000 },
      legenda,
    }, ['cabecalho']),
    botao: bloco('Botão', { rotulo: 'Saiba mais', url: 'https://' }, {
      rotulo: { type: 'string', title: 'Rótulo', minLength: 1, maxLength: 120 },
      url: { type: 'string', title: 'Endereço', pattern: URL_PROPRIA_OU_HTTPS, maxLength: 800 },
      nova_aba: { type: 'boolean', title: 'Abrir em nova aba', default: true },
    }, ['rotulo', 'url']),
    separador: bloco('Separador', { estilo: 'linha' }, {
      estilo: { type: 'string', title: 'Estilo', enum: ['linha', 'espaco', 'pontos'], default: 'linha' },
    }),
    incorporar: bloco('Incorporar', { url: 'https://', altura: 400, titulo: 'conteúdo incorporado' }, {
      url: { type: 'string', title: 'Endereço https', pattern: '^https://[^\\s<>"\']+$', maxLength: 800 },
      titulo: { type: 'string', title: 'Título acessível do quadro', minLength: 1, maxLength: 200 },
      altura: { type: 'integer', title: 'Altura (px)', minimum: 100, maximum: 2000, default: 400 },
      permitir_scripts: { type: 'boolean', title: 'Permitir scripts no quadro (sandbox allow-scripts)', default: true },
    }, ['url', 'titulo']),
    aplicativo: bloco('Aplicativo ou painel da plataforma', { altura: 500 }, {
      item_id: { type: 'string', title: 'Item app/painel do catálogo (uuid)', pattern: UUID },
      altura: { type: 'integer', title: 'Altura (px)', minimum: 200, maximum: 2000, default: 500 },
      legenda,
    }, ['item_id']),
  },
};

/* ---------------------------------------------------------------- resumos na caixa do editor (o que o autor vê) */
function resumoDeMapa(no) {
  const v = (no.propriedades || {}).vista;
  if (!v || !Array.isArray(v.bbox)) return 'sem vista salva';
  return `vista salva · zoom ${Number(v.zoom).toFixed(1)} · ${(v.camadas || []).length} camada(s)`;
}
for (const [tipo, campo] of [['texto', 'markdown'], ['capa', 'titulo'], ['imagem', 'alternativo'], ['botao', 'rotulo'],
  ['incorporar', 'url'], ['video', 'url'], ['audio', 'url'], ['tabela', 'cabecalho'], ['aplicativo', 'item_id']]) {
  PALETA_NARRATIVA.tipos[tipo].resumo = (no) => {
    const v = String((no.propriedades || {})[campo] ?? '');
    return v.length > 60 ? `${v.slice(0, 59)}…` : v;
  };
}

/* ---------------------------------------------------------------- controle personalizado: a vista do mapa vem
   de um mapa interativo no painel de propriedades (o autor enquadra, liga camadas e clica "Usar esta vista");
   é a MESMA função de montar do leitor (mapa_bloco.js), para o que o autor vê ser o que o leitor reabre */
function controleDeVista(nome, { no, valor, gravar }) {
  const quadro = document.createElement('div');
  quadro.className = 'vista-quadro';
  quadro.dataset.vistaDe = no.id;
  const lista = document.createElement('ul');
  lista.className = 'vista-camadas';
  lista.setAttribute('aria-label', 'camadas visíveis na vista');
  const botao = document.createElement('button');
  botao.type = 'button';
  botao.className = 'pequeno';
  botao.dataset.usarVista = no.id;
  botao.textContent = 'Usar esta vista';
  const estado = document.createElement('p');
  estado.className = 'vista-estado';
  estado.dataset.vistaEstado = no.id;
  estado.textContent = valor && Array.isArray(valor.bbox)
    ? `vista salva: [${valor.bbox.map((x) => Number(x).toFixed(4)).join(', ')}], proporção ${valor.proporcao}`
    : 'sem vista salva: enquadre o mapa e clique em "Usar esta vista"';
  const caixa = document.createElement('div');
  caixa.className = 'vista-controle';
  caixa.append(quadro, lista, botao, estado);

  let montado = null;
  const camadasLigadas = new Set((valor && valor.camadas) || []);
  queueMicrotask(async () => {
    if (!quadro.isConnected) { await new Promise((r) => requestAnimationFrame(r)); }
    try {
      montado = montarMapa(quadro, { vista: valor || null, interativo: true, camadas: [...camadasLigadas] });
    } catch (e) {
      estado.textContent = `mapa indisponível: ${e.message}`;
      return;
    }
    quadro.platMapa = montado; // ponto de inspeção do e2e (enquadrar por script e conferir a vista gravada)
    await montado.pronto;
    quadro.dataset.pronto = '1';
    for (const f of montado.catalogo.disponiveis) {
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.checked = camadasLigadas.has(f.id);
      chk.dataset.camadaVista = f.id;
      chk.addEventListener('change', async () => {
        if (chk.checked) { camadasLigadas.add(f.id); try { await montado.catalogo.ligar(f.id); } catch { /* sem tile */ } }
        else { camadasLigadas.delete(f.id); montado.catalogo.desligar(f.id); }
      });
      const rot = document.createElement('label');
      rot.append(chk, ` ${f.titulo}`);
      const li = document.createElement('li');
      li.append(rot);
      lista.append(li);
    }
  });
  botao.addEventListener('click', () => {
    if (!montado) return;
    const v = vistaAtual(montado.map, [...camadasLigadas]);
    if (gravar(v)) estado.textContent = `vista salva: [${v.bbox.map((x) => x.toFixed(4)).join(', ')}], proporção ${v.proporcao}`;
  });
  return caixa;
}
