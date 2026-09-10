/* plat — tela /campo/filas/{id} (item L2-07-campo): alvos de uma fila (feição de camada + estado) e criação
   do roteiro do dia a partir dos alvos pendentes. */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { anexar, h } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const filaId = (/^\/campo\/filas\/([0-9a-fA-F-]{36})/.exec(location.pathname) || [])[1];

await carregar();
const usuario = await exigirSessao({ privilegio: 'campo.coletar' });
if (usuario) iniciar();
pronto();

function localizacaoAtual() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lon: pos.coords.longitude, lat: pos.coords.latitude }),
      () => resolve(null),
      { timeout: 5000 },
    );
  });
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/campo/filas' });
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  if (!filaId) { aviso.mostrar(t('erro.nao_encontrado') || 'fila inexistente', 'erro'); return; }

  const r = await obter(`/api/campo/filas/${filaId}`);
  if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
  const { fila, alvos, roteiros } = r.json;
  cabecalho(fila.titulo, { contagem: alvos.length });

  const pendentes = alvos.filter((a) => a.status === 'pendente');
  const lon = h('input', { id: 'origem-lon', type: 'number', step: 'any', style: 'width:9em' });
  const lat = h('input', { id: 'origem-lat', type: 'number', step: 'any', style: 'width:9em' });
  const btLocalizacao = h('button', { type: 'button', class: 'pequeno' }, t('campo.fila.usar_localizacao'));
  btLocalizacao.addEventListener('click', async () => {
    const p = await localizacaoAtual();
    if (p) { lon.value = String(p.lon); lat.value = String(p.lat); }
  });
  const btRoteiro = h('button', { id: 'criar-roteiro', class: 'primario', type: 'button',
    disabled: pendentes.length === 0 }, t('campo.fila.criar_roteiro'));
  btRoteiro.addEventListener('click', async () => {
    if (!lon.value || !lat.value) { aviso.mostrar(t('campo.fila.origem_ajuda'), 'erro'); return; }
    btRoteiro.disabled = true;
    const resp = await enviar('/api/campo/roteiros', {
      fila_id: filaId, origem: { lon: Number(lon.value), lat: Number(lat.value) },
    });
    btRoteiro.disabled = false;
    if (resp.status !== 201) { aviso.mostrar(mensagemDe(resp), 'erro'); return; }
    location.href = `/campo/roteiros/${resp.json.id}`;
  });

  const tabelaAlvos = alvos.length
    ? h('div', { class: 'tabela-rolagem' },
        h('table', { class: 'tabela' },
          h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'globalid'), h('th', {}, t('campo.visita.status')))),
          h('tbody', {}, ...alvos.map((a) => h('tr', {},
            h('td', { class: 'num' }, String(a.ordem)),
            h('td', { class: 'mono' }, a.globalid),
            h('td', {}, h('span', { class: `badge badge-${a.status}` }, a.status)))))))
    : h('p', { class: 'vazio' }, t('campo.fila.sem_pendente'));

  const listaRoteiros = roteiros.length
    ? h('ul', { class: 'lista-recentes' }, ...roteiros.map((rt) => h('li', {},
        h('a', { href: `/campo/roteiros/${rt.id}` }, rt.titulo || rt.id),
        h('span', { class: 'tipo' }, `${rt.n_paradas} · ${formatarData(rt.criado_em)}`))))
    : null;

  anexar(principal, [
    h('p', {}, h('a', { href: '/campo/filas' }, `← ${t('campo.fila.voltar')}`)),
    h('div', { class: 'cartao' },
      h('h2', {}, t('campo.fila.origem')),
      h('p', { class: 'ajuda' }, t('campo.fila.origem_ajuda')),
      h('div', { class: 'linha-botoes' },
        h('label', {}, 'lon ', lon), h('label', {}, 'lat ', lat), btLocalizacao),
      btRoteiro,
      listaRoteiros ? h('h2', {}, 'Roteiros') : null, listaRoteiros),
    h('div', { class: 'cartao' }, h('h2', {}, t('campo.fila.alvos')), tabelaAlvos),
  ]);
}
