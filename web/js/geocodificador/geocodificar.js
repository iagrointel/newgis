/* plat — tela /geocodificar (item UX-14-geocodificador-sem-tela): as duas rotas de escrita do grupo
   `geocodificador` ganham controle — `POST /api/geocodificar` (endereço em linha única e/ou campos estruturados,
   até 50 candidatos) e `POST /api/reverso` (lon/lat + raio, vizinho mais próximo). Estados do sistema de design
   (UX-01) por <plat-estado>: carregando, vazio com a resposta NOMEADA da API (422 sem_correspondencia /
   sem_dado_instalado: o motor respondeu, só não achou), erro com "tentar de novo" e referência, negado (403);
   422 de validação cai no campo (endereco_vazio no campo endereço; lista do pydantic campo a campo) — nunca o
   número cru, nunca tela quebrada (refutação do item). O GET /api/geocodificar continua sendo a porta da caixa de
   pesquisa do mapa (leitura); aqui é a tela de trabalho do geocodificador, que também mostra a pontuação e o tipo
   de acerto de cada candidato. */
import { enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const el = (id) => document.getElementById(id);
const CAMPOS_ENDERECO = ['endereco', 'logradouro', 'numero', 'bairro', 'municipio', 'uf', 'cep', 'max_locations'];
const CAMPOS_REVERSO = ['lon', 'lat', 'raio_m'];
const NUMERICOS = new Set(['numero', 'max_locations', 'lon', 'lat', 'raio_m']);
let ultimoEndereco = null;
let ultimoReverso = null;

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/geocodificar' });
  cabecalho(t('geocodificar.titulo'));
  montarFormularioEndereco();
  montarFormularioReverso();
  el('endereco-estado').addEventListener('acao', (e) => {
    if (e.detail.id === 'tentar' && ultimoEndereco) geocodificar(ultimoEndereco);
    if (e.detail.id === 'limpar') { el('form-endereco').limparErros(); el('endereco-estado').limpar(); el('form-endereco').focarPrimeiro(); }
  });
  el('reverso-estado').addEventListener('acao', (e) => {
    if (e.detail.id === 'tentar' && ultimoReverso) reverso(ultimoReverso);
    if (e.detail.id === 'limpar') { el('reverso-estado').limpar(); el('form-reverso').focarPrimeiro(); }
  });
}

function numero(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : v;
}

function corpoDe(valores, campos) {
  const corpo = {};
  for (const c of campos) {
    const v = valores[c];
    if (v === '' || v === null || v === undefined) continue;
    corpo[c] = NUMERICOS.has(c) ? numero(v) : String(v).trim();
  }
  return corpo;
}

function errosPorCampo(detalhe, campos) {
  const m = {};
  const junta = (campo, msg) => { m[campo] = m[campo] ? `${m[campo]}; ${msg}` : msg; };
  if (Array.isArray(detalhe)) {
    for (const d of detalhe) {
      const loc = Array.isArray(d.loc) ? d.loc.filter((x) => typeof x === 'string' && x !== 'body') : [];
      junta(campos.includes(loc[0]) ? loc[0] : '_', d.msg || JSON.stringify(d));
    }
  }
  return m;
}

function mostrarErros(form, erros) {
  form.limparErros();
  for (const [campo, msg] of Object.entries(erros)) {
    if (campo === '_') form.mensagem(msg, 'erro');
    else form.erro(campo, msg);
  }
  form.querySelector('[aria-invalid="true"]')?.focus();
}

/* ------------------------------------------------------------------ endereço → coordenada */
function montarFormularioEndereco() {
  const form = el('form-endereco');
  form.campos = [
    { nome: 'endereco', rotulo: t('geocodificar.campo_endereco'), tipo: 'texto', ajuda: t('geocodificar.campo_endereco_ajuda'),
      atributos: { maxlength: '300', autocomplete: 'off' } },
    { nome: 'logradouro', rotulo: t('geocodificar.campo_logradouro'), tipo: 'texto', atributos: { maxlength: '200' } },
    { nome: 'numero', rotulo: t('geocodificar.campo_numero'), tipo: 'numero', atributos: { min: '0', max: '999999' } },
    { nome: 'bairro', rotulo: t('geocodificar.campo_bairro'), tipo: 'texto', atributos: { maxlength: '120' } },
    { nome: 'municipio', rotulo: t('geocodificar.campo_municipio'), tipo: 'texto', atributos: { maxlength: '120' } },
    { nome: 'uf', rotulo: t('geocodificar.campo_uf'), tipo: 'texto', atributos: { maxlength: '2', size: '2' } },
    { nome: 'cep', rotulo: t('geocodificar.campo_cep'), tipo: 'texto', atributos: { maxlength: '9', inputmode: 'numeric' } },
    { nome: 'max_locations', rotulo: t('geocodificar.campo_max'), tipo: 'numero', padrao: '10', atributos: { min: '1', max: '50' } },
  ];
  form.botoes = [
    { id: 'geocodificar', rotulo: t('geocodificar.acao_geocodificar'), tipo: 'submit' },
    { id: 'limpar', rotulo: t('acao.limpar'), tipo: 'button' },
  ];
  form.addEventListener('enviar', (ev) => geocodificar(corpoDe(ev.detail.valores, CAMPOS_ENDERECO)));
  form.addEventListener('botao', (ev) => {
    if (ev.detail.id === 'limpar') { form.definir({ max_locations: '10' }); form.limparErros(); limparResultados(); }
  });
}

function limparResultados() {
  el('resultados').hidden = true;
  limpar(el('resultados-corpo'));
  el('resultados-contagem').textContent = '';
  el('endereco-estado').limpar();
}

async function geocodificar(corpo) {
  const form = el('form-endereco');
  const estado = el('endereco-estado');
  ultimoEndereco = corpo;
  form.limparErros();
  el('resultados').hidden = true;
  form.ocupado = true;
  estado.carregando(t('geocodificar.carregando'));
  const r = await enviar('/api/geocodificar', corpo);
  form.ocupado = false;
  if (r.status === 401) { location.href = '/entrar?proximo=/geocodificar'; return; }
  const j = r.json || {};
  if (r.status === 422 && (j.erro === 'sem_correspondencia' || j.erro === 'sem_dado_instalado')) {
    // o motor respondeu e não achou: estado vazio com a resposta nomeada da API, não um erro
    estado.mostrar({ tipo: 'vazio', titulo: t('geocodificar.vazio_titulo'), texto: `${j.erro}: ${j.mensagem}`,
      acoes: [{ id: 'limpar', rotulo: t('geocodificar.vazio_acao') }] });
    return;
  }
  if (r.status === 422) {
    estado.limpar();
    const m = j.erro === 'endereco_vazio' ? { endereco: j.mensagem } : errosPorCampo(j.detalhe, CAMPOS_ENDERECO);
    if (!Object.keys(m).length) m._ = `${j.erro || 'validacao'}: ${j.mensagem || mensagemDe(r)}`;
    mostrarErros(form, m);
    return;
  }
  if (r.status === 403) { estado.negado(j.mensagem); return; }
  if (r.status !== 200) { estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]); return; }
  estado.limpar();
  desenharCandidatos(j.candidatos || []);
}

function rotuloAcerto(tipo) {
  const chave = `geocodificar.acerto_${tipo}`;
  const s = t(chave);
  return s === chave ? String(tipo || '—') : s;
}

function desenharCandidatos(candidatos) {
  const corpo = el('resultados-corpo');
  limpar(corpo);
  el('resultados-contagem').textContent = t('geocodificar.contagem', { n: candidatos.length });
  for (const c of candidatos) {
    const coord = `${Number(c.lon).toFixed(6)}, ${Number(c.lat).toFixed(6)}`;
    corpo.append(h('tr', {},
      h('td', {}, h('span', { class: 'geo-score' }, formatarNumero(Math.round(c.score * 10) / 10))),
      h('td', {}, c.endereco || '—',
        c.avisos && c.avisos.length ? h('p', { class: 'geo-avisos' }, c.avisos.join('; ')) : null),
      h('td', {}, rotuloAcerto(c.tipo_acerto)),
      h('td', { class: 'geo-coordenada' }, coord),
      h('td', {}, h('a', { class: 'botao pequeno', href: `/mapa#lon=${c.lon}&lat=${c.lat}` }, t('geocodificar.ver_no_mapa'))),
    ));
  }
  el('resultados').hidden = false;
}

/* ------------------------------------------------------------------ coordenada → endereço */
function montarFormularioReverso() {
  const form = el('form-reverso');
  form.campos = [
    { nome: 'lon', rotulo: t('geocodificar.campo_lon'), tipo: 'numero', obrigatorio: true, atributos: { step: 'any', min: '-180', max: '180' } },
    { nome: 'lat', rotulo: t('geocodificar.campo_lat'), tipo: 'numero', obrigatorio: true, atributos: { step: 'any', min: '-90', max: '90' } },
    { nome: 'raio_m', rotulo: t('geocodificar.campo_raio'), tipo: 'numero', padrao: '2000', ajuda: t('geocodificar.campo_raio_ajuda'),
      atributos: { step: 'any', min: '1', max: '50000' } },
  ];
  form.botoes = [{ id: 'reverso', rotulo: t('geocodificar.acao_reverso'), tipo: 'submit' }];
  form.addEventListener('enviar', (ev) => reverso(corpoDe(ev.detail.valores, CAMPOS_REVERSO)));
}

async function reverso(corpo) {
  const form = el('form-reverso');
  const estado = el('reverso-estado');
  const saida = el('reverso-resultado');
  ultimoReverso = corpo;
  form.limparErros();
  saida.hidden = true;
  form.ocupado = true;
  estado.carregando(t('geocodificar.carregando'));
  const r = await enviar('/api/reverso', corpo);
  form.ocupado = false;
  if (r.status === 401) { location.href = '/entrar?proximo=/geocodificar'; return; }
  const j = r.json || {};
  if (r.status === 422 && j.erro === 'sem_dado_instalado') {
    estado.mostrar({ tipo: 'vazio', titulo: t('geocodificar.vazio_titulo'), texto: `${j.erro}: ${j.mensagem}`,
      acoes: [{ id: 'limpar', rotulo: t('geocodificar.vazio_acao') }] });
    return;
  }
  if (r.status === 422) {
    estado.limpar();
    const m = errosPorCampo(j.detalhe, CAMPOS_REVERSO);
    if (!Object.keys(m).length) m._ = `${j.erro || 'validacao'}: ${j.mensagem || mensagemDe(r)}`;
    mostrarErros(form, m);
    return;
  }
  if (r.status === 403) { estado.negado(j.mensagem); return; }
  if (r.status !== 200) { estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]); return; }
  estado.limpar();
  limpar(saida);
  const linha = (rotulo, valor) => h('div', { class: 'campo' }, h('strong', {}, rotulo), h('span', {}, valor ?? '—'));
  saida.append(
    linha(t('geocodificar.res_endereco'), j.endereco),
    linha(t('geocodificar.res_distancia'), `${formatarNumero(Math.round(j.distancia_m * 10) / 10)} m`),
    linha(t('geocodificar.res_cep'), j.cep),
    linha(t('geocodificar.res_municipio'), [j.municipio, j.uf].filter(Boolean).join(' - ')),
    j.fora_do_raio ? h('p', { class: 'geo-avisos', id: 'reverso-fora-do-raio' }, t('geocodificar.fora_do_raio', { raio: formatarNumero(corpo.raio_m || 2000) })) : null,
  );
  saida.hidden = false;
}
