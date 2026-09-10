/* plat — tela /redes/simples (item L4-18-rede-simples-trace-network): cria uma rede simples a partir de duas
   camadas do inquilino em TRÊS interações — escolher a camada de linhas, escolher a de pontos, clicar em
   criar. Tudo o mais tem valor padrão razoável e fica num bloco de ajuste opcional: o nome da rede sai do
   título da camada de linhas, a disciplina começa em `agua`, e o campo de direção de fluxo é oferecido a
   partir dos campos declarados da camada escolhida (sem campo, a rede inteira é lida como digitalizada).
   A criação é UMA chamada — POST /api/rede/simples — que faz rede, catálogo mínimo, feições e topologia. */
import { obter, enviar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const DISCIPLINAS = ['agua', 'eletrica', 'gas', 'esgoto', 'telecom', 'estrutura'];

await carregar();
const usuario = await exigirSessao({ privilegio: 'rede.editar' });
if (usuario) iniciar();
pronto();

// mesma aceitação do servidor (app/rede_utilidades/simples.py GEOMETRIA_ACEITA): "Geometry" (camada de
// geometria mista/indefinida) vale nos dois papéis; o resto é específico.
const GEOM_LINHA = new Set(['LineString', 'MultiLineString', 'Geometry']);
const GEOM_PONTO = new Set(['Point', 'MultiPoint', 'Geometry']);

/* GET /api/mapa/camadas (não /api/itens): já devolve `geometria` por camada servível e exclui apagados
   (a lixeira nunca aparece aqui — achado do dono 10/09, camada "original" apagada entrando na caixa de
   linhas). Com a geometria em mãos a TELA filtra por papel; o servidor continua sendo a última palavra
   (erro `geometria_incompativel`), mas a caixa nunca mais oferece o que ele vai recusar. */
async function camadas() {
  const r = await obter('/api/mapa/camadas');
  return r.status === 200 ? (r.json.camadas || []) : [];
}

async function camposDaCamada(id) {
  const r = await obter(`/api/itens/${id}`);
  if (r.status !== 200) return [];
  return ((r.json.dados || {}).campos || []).map((c) => c.nome);
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/simples' });
  cabecalho(t('redesimples.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const todas = await camadas();
  const linhas = todas.filter((i) => GEOM_LINHA.has(i.geometria));
  const pontos = todas.filter((i) => GEOM_PONTO.has(i.geometria));

  const selLinha = h('select', { id: 'camada-linha', 'aria-label': t('redesimples.camada_linha'), disabled: linhas.length === 0 },
    h('option', { value: '' }, t('redesimples.escolha')),
    ...linhas.map((i) => h('option', { value: i.id }, i.titulo)));
  const selPonto = h('select', { id: 'camada-ponto', 'aria-label': t('redesimples.camada_ponto'), disabled: pontos.length === 0 },
    h('option', { value: '' }, t('redesimples.sem_pontos')),
    ...pontos.map((i) => h('option', { value: i.id }, i.titulo)));
  // estado vazio honesto (nunca some em silêncio): link de verdade para /uploads, não só o nome da tela.
  const vazioLinha = linhas.length ? null
    : h('p', { id: 'vazio-camada-linha', class: 'vazio' },
      `${t('redesimples.vazio_linha')} `, h('a', { href: '/uploads' }, t('nav.uploads')), '.');
  const vazioPonto = pontos.length ? null
    : h('p', { id: 'vazio-camada-ponto', class: 'vazio' },
      `${t('redesimples.vazio_ponto')} `, h('a', { href: '/uploads' }, t('nav.uploads')), '.');
  const nome = h('input', { id: 'nome-rede', type: 'text', maxlength: '200' });
  const disciplina = h('select', { id: 'disciplina' },
    ...DISCIPLINAS.map((d) => h('option', { value: d }, d)));
  const selDirecao = h('select', { id: 'campo-direcao' },
    h('option', { value: '' }, t('redesimples.direcao_padrao')));
  // sem camada de linhas não há o que criar — o botão avisa antes do clique, não depois do erro do servidor.
  const botao = h('button', { id: 'criar', class: 'primario', type: 'button', disabled: linhas.length === 0 }, t('redesimples.criar'));
  const resultado = h('div', { id: 'resultado', class: 'resultado' });

  selLinha.addEventListener('change', async () => {
    const item = linhas.find((i) => i.id === selLinha.value);
    if (item && !nome.value) nome.value = item.titulo;
    limpar(selDirecao);
    selDirecao.append(h('option', { value: '' }, t('redesimples.direcao_padrao')));
    if (!selLinha.value) return;
    for (const c of await camposDaCamada(selLinha.value)) {
      selDirecao.append(h('option', { value: c }, c));
    }
  });

  botao.addEventListener('click', async () => {
    if (!selLinha.value) { aviso.mostrar(t('redesimples.sem_camada_linha'), 'erro'); return; }
    botao.disabled = true;
    const corpo = {
      nome: nome.value || (linhas.find((i) => i.id === selLinha.value) || {}).titulo || 'rede simples',
      disciplina: disciplina.value,
      camada_linha_id: selLinha.value,
    };
    if (selPonto.value) corpo.camada_ponto_id = selPonto.value;
    if (selDirecao.value) {
      corpo.campo_direcao = selDirecao.value;
      corpo.mapa_direcao = {
        digitalizada: 'digitalizada', contra: 'contra', indeterminada: 'indeterminada',
      };
    }
    const r = await enviar('/api/rede/simples', corpo);
    botao.disabled = false;
    if (r.status !== 201) { aviso.mostrar((r.json && r.json.mensagem) || t('redesimples.falhou'), 'erro'); return; }
    limpar(resultado);
    resultado.dataset.redeId = r.json.rede_id;
    resultado.append(
      h('p', { class: 'ok' }, t('redesimples.pronta')),
      h('dl', {},
        h('dt', {}, t('redesimples.trechos')), h('dd', { id: 'r-trechos' }, String(r.json.feicoes.trechos)),
        h('dt', {}, t('redesimples.juncoes')), h('dd', { id: 'r-juncoes' }, String(r.json.feicoes.juncoes)),
        h('dt', {}, t('redesimples.nos')), h('dd', { id: 'r-nos' }, String(r.json.topologia.nos)),
        h('dt', {}, t('redesimples.arestas')), h('dd', { id: 'r-arestas' }, String(r.json.topologia.arestas))),
    );
    aviso.mostrar(t('redesimples.pronta'), 'ok');
  });

  principal.append(
    h('p', { class: 'ajuda' }, t('redesimples.ajuda')),
    h('div', { class: 'formulario' },
      h('label', { for: 'camada-linha' }, t('redesimples.camada_linha')), selLinha, vazioLinha,
      h('label', { for: 'camada-ponto' }, t('redesimples.camada_ponto')), selPonto, vazioPonto,
      botao),
    h('details', { id: 'ajustes' },
      h('summary', {}, t('redesimples.ajustes')),
      h('label', { for: 'nome-rede' }, t('redesimples.nome')), nome,
      h('label', { for: 'disciplina' }, t('redesimples.disciplina')), disciplina,
      h('label', { for: 'campo-direcao' }, t('redesimples.campo_direcao')), selDirecao),
    resultado,
  );
}
