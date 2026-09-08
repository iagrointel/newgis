/* plat — tela /admin/papeis: os 4 perfis (teto) e os papéis personalizados do inquilino (GET/POST/PUT/DELETE /api/papeis,
   GET /api/privilegios). Um papel é um subconjunto do teto do perfil mínimo; quem cria não dá o que não tem (privilégio
   ausente na sessão aparece desabilitado). Mensagens exatas da API (422 privilegio_fora_do_teto, 409 papel_em_uso). */
import { obter, enviar, alterar, apagar, mensagemDe } from '../base/api.js';
import { h } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { PERFIS, eventoRegistrado } from './comum.js';

let privilegios = [];
let dados = { perfis: [], personalizados: [] };

await carregar();
const usuario = await exigirSessao({ privilegio: 'papeis.gerir' });
if (usuario) await iniciar();
pronto();
async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/papeis' });
  const bt = h('button', { type: 'button', class: 'primario', id: 'novo' }, t('papeis.novo'));
  bt.addEventListener('click', () => abrirPainel(null));
  cabecalho(t('papeis.titulo'), { botoes: [bt] });
  const rp = await obter('/api/privilegios');
  privilegios = rp.status === 200 && Array.isArray(rp.json) ? rp.json : [];
  if (rp.status !== 200) document.getElementById('aviso').erro(`${t('erro.carregar')}: ${mensagemDe(rp)}`);
  montarTabelas();
  await carregarLista();
}

function montarTabelas() {
  const tp = document.getElementById('tabela-perfis');
  tp.chave = 'perfil';
  tp.colunas = [
    { chave: 'perfil', titulo: t('campo.perfil'), formatar: (v) => t(`perfil.${v}`) },
    { chave: 'privilegios', titulo: t('papeis.privilegios'), classe: 'num', formatar: (v) => String((v || []).length) },
    { chave: 'perfil', titulo: t('papeis.administrativos'), classe: 'num', formatar: (_, l) => String((l.privilegios || []).filter((p) => privilegios.find((x) => x.nome === p)?.administrativo).length) },
  ];
  tp.acoes = [{ id: 'ver', rotulo: t('acao.ver') }];
  tp.addEventListener('acao', (e) => verPerfil(e.detail.linha));
  const tab = document.getElementById('tabela');
  tab.colunas = [
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'descricao', titulo: t('campo.descricao') },
    { chave: 'perfil_minimo', titulo: t('papeis.perfil_minimo'), formatar: (v) => t(`perfil.${v}`) },
    { chave: 'privilegios', titulo: t('papeis.privilegios'), classe: 'num', formatar: (v) => String((v || []).length) },
    { chave: 'usuarios', titulo: t('papeis.usuarios'), classe: 'num', formatar: (v) => String(v ?? 0) },
  ];
  tab.acoes = () => (tem('papeis.gerir') ? [{ id: 'editar', rotulo: t('acao.editar') }, { id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' }] : [{ id: 'editar', rotulo: t('acao.ver') }]);
  tab.vazio = t('papeis.vazio');
  tab.addEventListener('acao', async (e) => {
    const p = e.detail.linha;
    document.getElementById('aviso').limpar();
    if (e.detail.id === 'editar') { abrirPainel(p); return; }
    if (!(await confirmar(t('acao.apagar'), t('papeis.apagar_confirma', { nome: p.nome }), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/papeis/${p.id}`);
    const aviso = document.getElementById('aviso');
    if (r.status === 204) { await carregarLista(); aviso.ok(t('papeis.apagado', { nome: p.nome })); eventoRegistrado(); return; }
    let m = mensagemDe(r);
    if (r.json.erro === 'papel_em_uso' && r.json.detalhe?.usuarios !== undefined) m += ` (${t('papeis.em_uso_por', { n: r.json.detalhe.usuarios })})`;
    aviso.erro(m);
  });
}

async function carregarLista() {
  const estado = document.getElementById('estado');
  if (!dados.perfis.length) estado.carregando();
  const r = await obter('/api/papeis');
  if (r.status !== 200) {
    estado.erro(r);
    estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') carregarLista(); }, { once: true });
    return;
  }
  estado.limpar();
  dados = { perfis: r.json.perfis || [], personalizados: r.json.personalizados || [] };
  const ordem = Object.fromEntries(PERFIS.map((p, i) => [p, i]));
  document.getElementById('tabela-perfis').linhas = [...dados.perfis].sort((a, b) => (ordem[a.perfil] ?? 9) - (ordem[b.perfil] ?? 9));
  document.getElementById('tabela').linhas = dados.personalizados;
}

function opcoesPrivilegio(marcados, somenteLeitura) {
  const meus = new Set(usuario.privilegios || []);
  return privilegios.map((p) => ({
    valor: p.nome, rotulo: `${p.nome} — ${p.descricao || ''}`, grupo: t(`privilegio_grupo.${p.grupo}`) === `privilegio_grupo.${p.grupo}` ? p.grupo : t(`privilegio_grupo.${p.grupo}`),
    marca: p.administrativo ? t('papeis.adm') : '', desabilitado: somenteLeitura || !meus.has(p.nome), titulo: meus.has(p.nome) ? p.descricao : t('papeis.nao_tem_privilegio'),
  }));
}

function verPerfil(perfil) {
  const painel = document.getElementById('painel');
  const f = h('plat-formulario');
  f.campos = [{ nome: 'privilegios', rotulo: t('papeis.privilegios'), tipo: 'caixas', padrao: perfil.privilegios || [], opcoes: opcoesPrivilegio(perfil.privilegios, true) }];
  painel.abrir({ titulo: `${t('campo.perfil')}: ${t(`perfil.${perfil.perfil}`)}`, corpo: h('div', {}, h('p', { class: 'fraco' }, t('papeis.perfil_texto')), f), botoes: [{ id: 'ok', rotulo: t('acao.fechar') }] }).then(() => {});
}

function abrirPainel(p) {
  const painel = document.getElementById('painel');
  document.getElementById('aviso').limpar();
  const novo = !p;
  const pode = tem('papeis.gerir');
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, padrao: p?.nome || '', atributos: { maxlength: 128 }, desabilitado: !pode },
    { nome: 'descricao', rotulo: t('campo.descricao'), tipo: 'texto', padrao: p?.descricao || '', atributos: { maxlength: 250 }, desabilitado: !pode },
    ...(novo ? [] : [{ nome: 'perfil_minimo', rotulo: t('papeis.perfil_minimo'), tipo: 'info', padrao: t(`perfil.${p.perfil_minimo}`) }]),
    { nome: 'privilegios', rotulo: t('papeis.privilegios'), tipo: 'caixas', padrao: p?.privilegios || [], opcoes: opcoesPrivilegio(p?.privilegios, !pode), ajuda: t('papeis.privilegios_ajuda') },
  ];
  f.botoes = pode ? [{ id: 'salvar', rotulo: novo ? t('acao.criar') : t('acao.salvar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }] : [{ id: 'cancelar', rotulo: t('acao.fechar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    document.getElementById('aviso').limpar();
    if (!v.privilegios.length) { f.erro('privilegios', t('papeis.escolha_um')); return; }
    f.ocupado = true;
    const corpo = { nome: v.nome, descricao: v.descricao || '', privilegios: v.privilegios };
    const r = novo ? await enviar('/api/papeis', corpo) : await alterar(`/api/papeis/${p.id}`, corpo);
    f.ocupado = false;
    if (r.status === 201 || r.status === 200) { painel.fechar('ok'); await carregarLista(); document.getElementById('aviso').ok(t(novo ? 'papeis.criado' : 'papeis.salvo', { nome: r.json.nome })); eventoRegistrado(); return; }
    let m = mensagemDe(r);
    if (Array.isArray(r.json.detalhe) && r.json.detalhe.every((x) => typeof x === 'string')) m += `: ${r.json.detalhe.join(', ')}`;
    if (r.json.erro === 'nome_existente') f.erro('nome', m);
    else if (r.json.erro === 'privilegio_fora_do_teto' || r.json.erro === 'privilegio_proprio_insuficiente') f.erro('privilegios', m);
    else f.mensagem(m, 'erro');
  });
  painel.abrir({ titulo: novo ? t('papeis.novo') : `${t('papeis.papel')}: ${p.nome} ${p.usuarios ? '' : ''}`.trim(), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

