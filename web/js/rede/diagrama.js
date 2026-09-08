/* plat — tela /redes/diagrama (item L4-04-d-diagrama-esquematico): o diagrama esquemático de um alimentador
   ao lado do mapa dele, com a seleção casada nos dois sentidos.

   Duas telas de MapLibre, lado a lado, sem mapa-base nenhuma das duas:
     * ESQUEMA — desenha o grafo no ESPAÇO DO DIAGRAMA. MapLibre só sabe trabalhar em longitude/latitude, e
       o diagrama não tem geografia; então as unidades x,y do diagrama passam por uma transformação LINEAR
       declarada (`paraGrau`) que as encaixa numa janela de graus em volta de 0,0. Não é geolocalizar o
       esquema: é usar a tela de mapa como plano cartesiano, e por isso este quadro não tem escala nem
       coordenada — o que ele mostra não é lugar, é ligação.
     * MAPA — desenha os MESMOS nós na coordenada de verdade deles (`lon`/`lat`, que vieram da topologia).
       Só nós: a linha do mapa é a geometria do trecho, que esta tela não pede ao servidor, e desenhar uma
       reta entre dois nós seria inventar traçado.

   Cada nó é um <button> de verdade nos dois quadros (marcador do MapLibre com DOM próprio): dá para chegar
   nele pelo teclado, o leitor de tela anuncia o rótulo, e clicar em um acende o outro. É isto que a cláusula
   de seleção bidirecional do portão pede. */
import { obter, enviar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const LAYOUTS = ['arvore_inteligente', 'radial', 'linha_principal', 'geografico', 'grade', 'forca_dirigida'];
/* teto de marcadores por quadro: cada marcador é um nó do DOM, e um alimentador inteiro tem milhares.
   Acima disto o desenho continua completo (as arestas são uma camada só), mas os nós saem da tela com o
   aviso ao lado — melhor um quadro honesto que um navegador travado. */
const MARCADORES_MAXIMO = 500;
const JANELA_GRAUS = 80; // o esquema inteiro cabe nesta janela de graus, em volta de 0,0

await carregar();
const usuario = await exigirSessao({ privilegio: 'rede.editar' });
if (usuario) iniciar();
pronto();

function estiloVazio(cor) {
  return { version: 8, name: 'plat-diagrama', sources: {}, layers: [
    { id: 'fundo', type: 'background', paint: { 'background-color': cor } }] };
}

/* x,y do diagrama -> longitude/latitude da tela do esquema. Transformação linear, mesma escala nos dois
   eixos (o desenho não pode ser esticado), centrada em 0,0. */
function transformacao(nos) {
  if (!nos.length) return () => [0, 0];
  const xs = nos.map((n) => n.x);
  const ys = nos.map((n) => n.y);
  const minX = Math.min(...xs); const maxX = Math.max(...xs);
  const minY = Math.min(...ys); const maxY = Math.max(...ys);
  const largura = Math.max(maxX - minX, 1e-9);
  const altura = Math.max(maxY - minY, 1e-9);
  const escala = JANELA_GRAUS / Math.max(largura, altura);
  return (x, y) => [(x - (minX + maxX) / 2) * escala, (y - (minY + maxY) / 2) * escala];
}

function botaoNo(no, classe, aoSelecionar) {
  const b = h('button', {
    type: 'button', class: `${classe} marcador-no`, 'data-chave': no.chave,
    'data-papel': no.papel, title: no.rotulo || no.chave,
    'aria-label': `${no.rotulo || no.chave} (${no.papel})`,
  }, '');
  b.addEventListener('click', (ev) => { ev.stopPropagation(); aoSelecionar(no.chave); });
  return b;
}

async function redes() {
  const r = await obter('/api/rede?limite=200');
  return r.status === 200 ? (r.json.itens || []) : [];
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/diagrama' });
  cabecalho(t('diagrama.titulo'));
  const aviso = document.getElementById('aviso');
  const controles = document.getElementById('controles');
  const ficha = document.getElementById('ficha');
  const maplibregl = window.maplibregl;
  if (!maplibregl) { aviso.mostrar(t('diagrama.erro_biblioteca'), 'erro'); return; }

  const lista = await redes();
  const selRede = h('select', { id: 'rede', 'aria-label': t('diagrama.rede') },
    h('option', { value: '' }, t('diagrama.escolha')),
    ...lista.map((i) => h('option', { value: i.id }, i.nome)));
  const selDiagrama = h('select', { id: 'diagrama-escolhido', 'aria-label': t('diagrama.diagrama') },
    h('option', { value: '' }, t('diagrama.escolha_diagrama')));
  const selLayout = h('select', { id: 'layout', 'aria-label': t('diagrama.layout') },
    ...LAYOUTS.map((l) => h('option', { value: l }, t(`diagrama.layout_${l}`))));
  const estado = h('span', { id: 'estado-diagrama', class: 'etiqueta' }, '');
  const contagem = h('span', { id: 'contagem-diagrama', class: 'ajuda' }, '');
  const exportarSvg = h('a', { id: 'exportar-svg', class: 'acao', href: '#' }, t('diagrama.exportar_svg'));
  const exportarPng = h('a', { id: 'exportar-png', class: 'acao', href: '#' }, t('diagrama.exportar_png'));

  controles.append(
    h('label', { for: 'rede' }, t('diagrama.rede')), selRede,
    h('label', { for: 'diagrama-escolhido' }, t('diagrama.diagrama')), selDiagrama,
    h('label', { for: 'layout' }, t('diagrama.layout')), selLayout,
    estado, contagem, exportarSvg, exportarPng);

  const mapaEsquema = new maplibregl.Map({
    container: 'diagrama', style: estiloVazio('#f7f8fa'), center: [0, 0], zoom: 1,
    attributionControl: false, renderWorldCopies: false,
  });
  const mapaGeo = new maplibregl.Map({
    container: 'mapa-rede', style: estiloVazio('#eef1f4'), center: [0, 0], zoom: 1,
    attributionControl: false,
  });
  mapaEsquema.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  mapaGeo.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

  let marcadores = [];
  let documento = null;

  function limparMarcadores() {
    marcadores.forEach((m) => m.remove());
    marcadores = [];
  }

  function selecionar(chave) {
    document.querySelectorAll('.marcador-no.selecionado').forEach((b) => b.classList.remove('selecionado'));
    document.querySelectorAll(`.marcador-no[data-chave="${CSS.escape(chave)}"]`)
      .forEach((b) => b.classList.add('selecionado'));
    const no = (documento.nos || []).find((n) => n.chave === chave);
    limpar(ficha);
    if (!no) { ficha.hidden = true; return; }
    ficha.dataset.chave = chave;
    const arestas = (documento.arestas || []).filter((a) => a.de === chave || a.para === chave);
    const feicoes = [...new Set(arestas.flatMap((a) => a.feicoes))];
    ficha.append(
      h('h2', { id: 'no-rotulo' }, no.rotulo || no.chave),
      h('dl', {},
        h('dt', {}, t('diagrama.papel')), h('dd', { id: 'no-papel' }, no.papel),
        h('dt', {}, t('diagrama.tipo')), h('dd', { id: 'no-tipo' }, no.tipo || '—'),
        h('dt', {}, t('diagrama.feicao')), h('dd', { id: 'no-feicao' }, no.feicao_id || t('diagrama.sem_feicao')),
        h('dt', {}, t('diagrama.terminal')), h('dd', { id: 'no-terminal' }, no.terminal === null ? '—' : String(no.terminal)),
        h('dt', {}, t('diagrama.coordenada')),
        h('dd', { id: 'no-coordenada' }, no.lon === null ? t('diagrama.sem_coordenada')
          : `${no.lon.toFixed(6)}, ${no.lat.toFixed(6)}`),
        h('dt', {}, t('diagrama.ligacoes')),
        h('dd', { id: 'no-ligacoes' }, `${arestas.length} (${feicoes.length} ${t('diagrama.feicoes')})`)));
    ficha.hidden = false;
  }

  function desenhar(doc) {
    documento = doc;
    limparMarcadores();
    const paraGrau = transformacao(doc.nos);
    const linhas = {
      type: 'FeatureCollection',
      features: doc.arestas.map((a) => ({
        type: 'Feature', properties: { chave: a.chave, origem: a.origem },
        geometry: { type: 'LineString', coordinates: [paraGrau(a.x1, a.y1), paraGrau(a.x2, a.y2)] },
      })),
    };
    if (mapaEsquema.getSource('arestas')) mapaEsquema.getSource('arestas').setData(linhas);
    else {
      mapaEsquema.addSource('arestas', { type: 'geojson', data: linhas });
      mapaEsquema.addLayer({
        id: 'arestas', type: 'line', source: 'arestas',
        paint: { 'line-color': '#3b4a5a', 'line-width': 1.6 },
      });
    }

    const desenhaveis = doc.nos.slice(0, MARCADORES_MAXIMO);
    desenhaveis.forEach((no) => {
      const alvo = paraGrau(no.x, no.y);
      marcadores.push(new maplibregl.Marker({ element: botaoNo(no, 'no-esquema', selecionar) })
        .setLngLat(alvo).addTo(mapaEsquema));
      if (no.lon !== null && no.lat !== null) {
        marcadores.push(new maplibregl.Marker({ element: botaoNo(no, 'no-mapa', selecionar) })
          .setLngLat([no.lon, no.lat]).addTo(mapaGeo));
      }
    });

    const xs = doc.nos.map((n) => paraGrau(n.x, n.y));
    if (xs.length) {
      mapaEsquema.fitBounds([
        [Math.min(...xs.map((p) => p[0])), Math.min(...xs.map((p) => p[1]))],
        [Math.max(...xs.map((p) => p[0])), Math.max(...xs.map((p) => p[1]))]], { padding: 40, duration: 0 });
    }
    const geo = doc.nos.filter((n) => n.lon !== null && n.lat !== null);
    if (geo.length) {
      mapaGeo.fitBounds([
        [Math.min(...geo.map((n) => n.lon)), Math.min(...geo.map((n) => n.lat))],
        [Math.max(...geo.map((n) => n.lon)), Math.max(...geo.map((n) => n.lat))]],
      { padding: 40, maxZoom: 17, duration: 0 });
    }

    estado.textContent = t(`diagrama.estado_${doc.estado}`);
    estado.className = `etiqueta estado-${doc.estado}`;
    contagem.textContent = t('diagrama.contagem')
      .replace('{nos}', String(doc.nos.length)).replace('{arestas}', String(doc.arestas.length));
    if (doc.nos.length > MARCADORES_MAXIMO) {
      aviso.mostrar(t('diagrama.muitos_nos').replace('{teto}', String(MARCADORES_MAXIMO)), 'aviso');
    }
    selLayout.value = doc.layout;
    const base = `/api/rede/${selRede.value}/diagrama/${doc.id}/exportar`;
    exportarSvg.href = `${base}?formato=svg`;
    exportarPng.href = `${base}?formato=png`;
    ficha.hidden = true;
  }

  async function abrir(id) {
    const r = await obter(`/api/rede/${selRede.value}/diagrama/${id}`);
    if (r.status !== 200) { aviso.mostrar(t('diagrama.falhou'), 'erro'); return; }
    desenhar(r.json);
  }

  async function listarDiagramas() {
    limpar(selDiagrama);
    selDiagrama.append(h('option', { value: '' }, t('diagrama.escolha_diagrama')));
    limparMarcadores();
    ficha.hidden = true;
    if (!selRede.value) return;
    const r = await obter(`/api/rede/${selRede.value}/diagramas`);
    if (r.status !== 200) { aviso.mostrar(t('diagrama.falhou'), 'erro'); return; }
    const itens = r.json.itens || [];
    selDiagrama.dataset.total = String(itens.length);
    itens.forEach((d) => selDiagrama.append(h('option', { value: d.id }, `${d.nome} (${d.estado})`)));
  }

  selRede.addEventListener('change', listarDiagramas);
  selDiagrama.addEventListener('change', () => { if (selDiagrama.value) abrir(selDiagrama.value); });
  selLayout.addEventListener('change', async () => {
    if (!selDiagrama.value) return;
    const r = await enviar(`/api/rede/${selRede.value}/diagrama/${selDiagrama.value}/layout`,
      { layout: selLayout.value });
    if (r.status !== 200) { aviso.mostrar((r.json && r.json.mensagem) || t('diagrama.falhou'), 'erro'); return; }
    aviso.mostrar(t('diagrama.layout_aplicado'), 'ok');
    await abrir(selDiagrama.value);
  });
}
