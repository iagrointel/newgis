/* plat · conexões — entrada da tela /conexoes (itens L6-02-l-saude e L6-05-proveniencia-camada-externa).
   Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports (duas URLs do mesmo
   módulo = duas instâncias, app morre — regra da casa).
   Lista as conexões do inquilino com estado agregado de saúde (ok/degradado/fora/nunca_testada, calculado por
   `plat.v_conexao_saude`), disponibilidade em 30 dias e ações por linha: testar agora, ver histórico (últimos
   10 testes) e publicar camada (cria um item de catálogo com a ficha de procedência lida do serviço). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma, formatarData } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

const ESTADO_ROTULO = { ok: 'ok', degradado: 'degradado', fora: 'fora', nunca_testada: 'nunca testada' };
const ESTADO_CLASSE = { ok: 'ok', degradado: 'atencao', fora: 'falha', nunca_testada: 'info' };

let saindo = false;
const s = { itens: [], usuario: null };

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(id, texto, tipo = 'erro') {
  const n = document.getElementById(id);
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

function badgeEstado(estado) {
  const classe = ESTADO_CLASSE[estado] || 'info';
  const rotulo = ESTADO_ROTULO[estado] || estado || 'nunca testada';
  return h('span', { class: `marcador ${classe}`, title: `estado de saúde: ${rotulo}` }, rotulo);
}

function celulaDisponibilidade(c) {
  if (c.disponibilidade_30d_total === 0 || c.disponibilidade_30d_pct === null || c.disponibilidade_30d_pct === undefined) {
    return h('span', { class: 'ajuda' }, 'sem verificação em 30 d');
  }
  return h('span', {}, `${c.disponibilidade_30d_pct}% (${c.disponibilidade_30d_total} verificações)`);
}

async function testarAgora(c, botao) {
  botao.disabled = true;
  aviso('lista-aviso', '');
  const r = await api.enviar(`/api/conexoes/${encodeURIComponent(c.id)}/testar`, {});
  botao.disabled = false;
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível testar ${c.nome}: ${api.mensagemDe(r)}`);
    return;
  }
  await carregar();
}

function linhaHistoricoTabela(item) {
  return h('tr', {},
    h('td', {}, formatarData(item.verificada_em)),
    h('td', {}, h('span', { class: `marcador ${item.ok ? 'ok' : 'falha'}` }, item.ok ? 'ok' : 'erro')),
    h('td', {}, item.status === null || item.status === undefined ? '—' : String(item.status)),
    h('td', {}, item.mensagem || '—'),
    h('td', {}, item.latencia_ms === null || item.latencia_ms === undefined ? '—' : `${item.latencia_ms} ms`));
}

async function verHistorico(c) {
  const dialogo = porId('dialogo');
  const r = await api.obter(`/api/conexoes/${encodeURIComponent(c.id)}/saude-historico?limite=10`);
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível ler o histórico de ${c.nome}: ${api.mensagemDe(r)}`);
    return;
  }
  const itens = r.json.itens || [];
  const corpo = h('div', {},
    h('p', {}, `${c.nome} — últimos ${itens.length} teste(s) de saúde`),
    itens.length
      ? h('table', { class: 'tabela' },
          h('thead', {}, h('tr', {}, h('th', {}, 'quando'), h('th', {}, 'resultado'), h('th', {}, 'status'),
            h('th', {}, 'mensagem'), h('th', {}, 'latência'))),
          h('tbody', {}, ...itens.map(linhaHistoricoTabela)))
      : h('p', { class: 'ajuda' }, 'nenhum teste registrado ainda — clique em "testar agora" ou aguarde o periódico (a cada 15 min).'));
  await dialogo.abrir({ titulo: 'histórico de saúde', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
}

function linhaProcedencia(rotulo, valor) {
  return h('div', { class: 'campo' },
    h('strong', {}, rotulo), ': ',
    valor === null || valor === undefined || valor === '' ? h('em', {}, 'não registrado') : h('span', {}, String(valor)));
}

async function publicarCamada(c) {
  const dialogo = porId('dialogo');
  const r = await api.enviar(`/api/conexoes/${encodeURIComponent(c.id)}/publicar`, {});
  if (r.status !== 201) {
    aviso('lista-aviso', `não foi possível publicar a camada de ${c.nome}: ${api.mensagemDe(r)}`);
    return;
  }
  const item = r.json;
  const proc = (item.dados && item.dados.procedencia) || {};
  const corpo = h('div', {},
    h('p', {}, h('a', { href: `/conteudo/${encodeURIComponent(item.id)}` }, `abrir "${item.titulo}" no catálogo →`)),
    linhaProcedencia('fonte', proc.fonte),
    linhaProcedencia('url', proc.url),
    linhaProcedencia('licença', proc.licenca),
    linhaProcedencia('data de acesso', proc.data_de_acesso),
    linhaProcedencia('método', proc.metodo),
    linhaProcedencia('confiança', proc.confianca),
    linhaProcedencia('frescor', proc.frescor),
    linhaProcedencia('sha256', proc.sha256),
    linhaProcedencia('comando de reexecução', proc.comando_reexecucao),
    linhaProcedencia('atribuição (créditos)', item.creditos),
    proc.limites && proc.limites.length ? h('p', { class: 'ajuda' }, `ressalvas: ${proc.limites.join('; ')}`) : null);
  await dialogo.abrir({ titulo: 'camada publicada com ficha de procedência', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
  aviso('lista-aviso', `camada publicada a partir de ${c.nome}`, 'ok');
}

function linha(c) {
  const tr = h('tr', { dataset: { id: c.id, estado: c.estado_saude } });
  const btTestar = h('button', { type: 'button', class: 'pequeno' }, 'testar agora');
  btTestar.addEventListener('click', () => testarAgora(c, btTestar));
  const btHistorico = h('button', { type: 'button', class: 'pequeno' }, 'histórico');
  btHistorico.addEventListener('click', () => verHistorico(c));
  const btPublicar = h('button', { type: 'button', class: 'pequeno' }, 'publicar camada');
  btPublicar.addEventListener('click', () => publicarCamada(c));
  tr.append(
    h('td', {}, c.nome),
    h('td', {}, c.tipo),
    h('td', {}, c.modo),
    h('td', {}, badgeEstado(c.estado_saude)),
    h('td', {}, celulaDisponibilidade(c)),
    h('td', {}, c.saude_verificada_em ? formatarData(c.saude_verificada_em) : h('span', { class: 'ajuda' }, 'nunca testada')),
    h('td', {}, btTestar, ' ', btHistorico, ' ', btPublicar),
  );
  return tr;
}

async function carregar() {
  aviso('lista-aviso', '');
  const r = await api.obter('/api/conexoes');
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('lista-aviso', `não foi possível carregar as conexões (${api.mensagemDe(r)})`);
    return;
  }
  s.itens = r.json.itens || [];
  porId('lista-total').textContent = `(${r.json.total})`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  if (!s.itens.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '7', class: 'ajuda' },
      'nenhuma conexão ainda — crie uma pela API (POST /api/conexoes) ou aguarde o conector por protocolo (L6-02-b em diante).')));
    return;
  }
  for (const c of s.itens) corpo.append(linha(c));
}

/* ---- descoberta por catálogo CSW 2.0.2 (item L6-06-descoberta-csw): POST /api/csw/buscar lista registros ISO
   19139 com os serviços WMS/WFS/WMTS que declaram COM endereço; POST /api/csw/conexoes cria as conexões num
   clique. Registro sem serviço ligado: a linha diz "sem serviço ligado" e o botão fica desativado — a API também
   recusa (422 sem_servico_ligado), a tela só não deixa o clique acontecer. */
const csw = { url: '', texto: '', bbox: null, inicio: 1, total: 0, proximo: null };

function bboxDoCampo(texto) {
  const t = (texto || '').trim();
  if (!t) return null;
  const partes = t.split(/[,;\s]+/).filter(Boolean).map(Number);
  if (partes.length !== 4 || partes.some((n) => Number.isNaN(n))) {
    throw new Error('extensão precisa ter 4 números: oeste, sul, leste, norte');
  }
  return partes;
}

function badgeServico(s) {
  return h('span', { class: 'marcador info', title: `${s.protocolo || 'service= na URL'} — ${s.url_declarada}` },
    `${s.tipo.toUpperCase()}${s.camada ? ` · ${s.camada}` : ''}`);
}

function celulaServicos(reg) {
  if (reg.sem_servico) {
    return h('span', { class: 'marcador atencao', title: (reg.avisos || []).join('; ') }, 'sem serviço ligado');
  }
  return h('span', {}, ...reg.servicos.flatMap((s, i) => (i ? [' ', badgeServico(s)] : [badgeServico(s)])));
}

function detalheRegistro(reg) {
  const dialogo = porId('dialogo');
  const corpo = h('div', {},
    linhaProcedencia('identificador', reg.identificador),
    linhaProcedencia('organização', reg.organizacao),
    linhaProcedencia('resumo', reg.resumo),
    linhaProcedencia('data do dado', reg.data_do_dado),
    linhaProcedencia('data do metadado', reg.data_metadado),
    linhaProcedencia('licença (texto declarado)', reg.licenca),
    linhaProcedencia('restrições (códigos)', (reg.restricoes || []).join(', ')),
    linhaProcedencia('palavras-chave', (reg.palavras_chave || []).join(', ')),
    linhaProcedencia('extensão', reg.bbox ? reg.bbox.join(', ') : null),
    h('p', {}, h('strong', {}, 'serviços declarados com endereço: '),
      reg.sem_servico ? h('em', {}, 'sem serviço ligado') : celulaServicos(reg)),
    reg.avisos && reg.avisos.length ? h('p', { class: 'ajuda' }, `ressalvas: ${reg.avisos.join('; ')}`) : null);
  dialogo.abrir({ titulo: reg.titulo || 'registro', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] }).then(() => {});
}

async function criarConexoesDoRegistro(reg, botao) {
  botao.disabled = true;
  aviso('csw-aviso', '');
  const r = await api.enviar('/api/csw/conexoes', { url: csw.url, identificador: reg.identificador });
  botao.disabled = false;
  if (r.status !== 201) {
    const erro = r.json && r.json.erro;
    aviso('csw-aviso', erro === 'sem_servico_ligado'
      ? `sem serviço ligado: o registro "${reg.titulo || reg.identificador}" não declara WMS/WFS/WMTS com endereço — nenhuma conexão criada`
      : `não foi possível criar as conexões de "${reg.titulo || reg.identificador}": ${api.mensagemDe(r)}`);
    return;
  }
  const criadas = r.json.conexoes.filter((c) => c.criada).length;
  const reaproveitadas = r.json.conexoes.length - criadas;
  aviso('csw-aviso',
    `${criadas} conexão(ões) criada(s)${reaproveitadas ? `, ${reaproveitadas} já existia(m)` : ''} a partir de "${reg.titulo || reg.identificador}"; a ficha de procedência veio do registro ISO`,
    'ok');
  await carregar();
}

function linhaRegistro(reg) {
  const btVer = h('button', { type: 'button', class: 'pequeno' }, 'ficha');
  btVer.addEventListener('click', () => detalheRegistro(reg));
  const btCriar = h('button', { type: 'button', class: 'pequeno primario', disabled: reg.sem_servico },
    reg.sem_servico ? 'sem serviço ligado' : `criar ${reg.servicos.length} conexão(ões)`);
  if (!reg.sem_servico) btCriar.addEventListener('click', () => criarConexoesDoRegistro(reg, btCriar));
  return h('tr', { dataset: { identificador: reg.identificador || '', semServico: String(reg.sem_servico) } },
    h('td', {}, reg.titulo || h('em', {}, 'sem título')),
    h('td', {}, reg.organizacao || h('em', {}, 'não registrado')),
    h('td', {}, reg.data_do_dado || h('em', {}, 'não registrado')),
    h('td', {}, celulaServicos(reg)),
    h('td', {}, btVer, ' ', btCriar));
}

async function buscarCsw(continuar) {
  aviso('csw-aviso', '');
  const form = porId('csw-form');
  if (!continuar) {
    csw.url = form.elements.url.value.trim();
    csw.texto = form.elements.texto.value.trim();
    try {
      csw.bbox = bboxDoCampo(form.elements.bbox.value);
    } catch (e) {
      aviso('csw-aviso', e.message);
      return;
    }
    csw.inicio = 1;
    limpar(porId('csw-corpo'));
  }
  if (!csw.texto && !csw.bbox) {
    aviso('csw-aviso', 'informe um texto e/ou uma extensão');
    return;
  }
  const btBuscar = porId('csw-buscar');
  btBuscar.disabled = true;
  const r = await api.enviar('/api/csw/buscar', {
    url: csw.url, texto: csw.texto || null, bbox: csw.bbox, inicio: csw.inicio, maximo: 10,
  });
  btBuscar.disabled = false;
  if (r.status !== 200) {
    aviso('csw-aviso', `o catálogo não respondeu de forma utilizável: ${api.mensagemDe(r)}`);
    return;
  }
  csw.total = r.json.total;
  csw.proximo = r.json.proximo;
  const corpo = porId('csw-corpo');
  for (const reg of r.json.registros) corpo.append(linhaRegistro(reg));
  porId('csw-lista').hidden = false;
  const mostrados = corpo.querySelectorAll('tr').length;
  porId('csw-resumo').textContent = csw.total
    ? `${mostrados} de ${csw.total} registro(s)`
    : 'nenhum registro encontrado';
  porId('csw-mais').hidden = !csw.proximo;
}

function ligarCsw() {
  const form = document.getElementById('csw-form');
  if (!form) return;
  form.addEventListener('submit', (e) => { e.preventDefault(); buscarCsw(false); });
  porId('csw-mais').addEventListener('click', () => { csw.inicio = csw.proximo || 1; buscarCsw(true); });
}

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/conexoes' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Conexões');
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { saindo = true; irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
    const destino = caminhoPendencia(usuario.pendencias);
    if (destino) { saindo = true; location.replace(destino); return; }
  } else {
    aviso('aviso', `dados da sessão indisponíveis (GET /api/eu devolveu ${r.status}); a tela segue com a API de conexões`, 'atencao');
  }
  s.usuario = usuario;
  layout(usuario);
  ligarCsw();
  await carregar();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
