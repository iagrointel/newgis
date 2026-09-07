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

async function camadas() {
  const r = await obter('/api/itens?tipo=camada_vetorial&ordenar=criado_em&direcao=desc&limite=200');
  return r.status === 200 ? (r.json.itens || []) : [];
}

/* A lista de itens NÃO traz `dados` (o catálogo omite os campos pesados na listagem), então a tela não tem
   como filtrar por geometria aqui: as duas caixas oferecem as camadas vetoriais e é o servidor que recusa uma
   camada de geometria errada no papel escolhido (erro `geometria_incompativel`, mensagem na tela). Os campos
   da camada de linhas, para escolher o de direção, vêm de uma leitura do item — sem clique a mais. */
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
  const linhas = await camadas();
  const pontos = linhas;

  const selLinha = h('select', { id: 'camada-linha', 'aria-label': t('redesimples.camada_linha') },
    h('option', { value: '' }, t('redesimples.escolha')),
    ...linhas.map((i) => h('option', { value: i.id }, i.titulo)));
  const selPonto = h('select', { id: 'camada-ponto', 'aria-label': t('redesimples.camada_ponto') },
    h('option', { value: '' }, t('redesimples.sem_pontos')),
    ...pontos.map((i) => h('option', { value: i.id }, i.titulo)));
  const nome = h('input', { id: 'nome-rede', type: 'text', maxlength: '200' });
  const disciplina = h('select', { id: 'disciplina' },
    ...DISCIPLINAS.map((d) => h('option', { value: d }, d)));
  const selDirecao = h('select', { id: 'campo-direcao' },
    h('option', { value: '' }, t('redesimples.direcao_padrao')));
  const botao = h('button', { id: 'criar', class: 'primario', type: 'button' }, t('redesimples.criar'));
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
      h('label', { for: 'camada-linha' }, t('redesimples.camada_linha')), selLinha,
      h('label', { for: 'camada-ponto' }, t('redesimples.camada_ponto')), selPonto,
      botao),
    h('details', { id: 'ajustes' },
      h('summary', {}, t('redesimples.ajustes')),
      h('label', { for: 'nome-rede' }, t('redesimples.nome')), nome,
      h('label', { for: 'disciplina' }, t('redesimples.disciplina')), disciplina,
      h('label', { for: 'campo-direcao' }, t('redesimples.campo_direcao')), selDirecao),
    resultado,
  );
}
