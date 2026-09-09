/* plat · ferramentas — tela /ferramentas?item=<id> (item L2-16-c-script-vira-ferramenta).
   Renderiza o FORMULÁRIO da ferramenta de script gerado do cabeçalho (GET
   /api/ferramentas/script/{id}/formulario) e executa por job (POST /executar), acompanhando a
   fila até o estado final. Módulos ES sem build; o cache é resolvido por no-store no nginx:
   NUNCA ?v= nos imports (regra da casa). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

let saindo = false;

function aviso(texto, tipo = 'erro') {
  const n = document.getElementById('aviso');
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

function cartao() { return document.getElementById('ferramenta-cartao'); }

function campoDe(p) {
  const rotulo = `${p.rotulo}${p.obrigatorio ? ' *' : ''}`;
  const ajuda = [p.descricao, p.tipo_gp !== p.tipo ? `tipo GP: ${p.tipo_gp}` : ''].filter(Boolean).join(' — ');
  const comum = { name: p.nome, id: `f-${p.nome}`, label: rotulo, help: ajuda };
  if (p.tipo === 'booleano') {
    return { ...comum, tipo: 'caixa', padrao: !!p.padrao };
  }
  if (p.tipo === 'numero' || p.tipo === 'inteiro') {
    return { ...comum, tipo: 'numero', padrao: p.padrao ?? '',
             atributos: { min: p.minimo, max: p.maximo, step: p.tipo === 'inteiro' ? 1 : 'any' } };
  }
  return { ...comum, tipo: 'texto', padrao: p.padrao ?? '',
           atributos: p.tipo === 'item' ? { placeholder: 'id do item (uuid)', spellcheck: 'false' } : {} };
}

function linhaCampo(p) {
  const c = campoDe(p);
  const entrada = c.tipo === 'caixa'
    ? h('input', { type: 'checkbox', id: c.id, name: c.name })
    : h('input', { type: c.tipo === 'numero' ? 'number' : 'text', id: c.id, name: c.name,
                   ...c.atributos });
  if (c.padrao !== '' && c.padrao !== undefined && c.tipo !== 'caixa') entrada.value = c.padrao;
  const pedaco = [h('label', { for: c.id }, c.label), entrada];
  if (c.ajuda) pedaco.push(h('p', { class: 'ajuda' }, c.ajuda));
  return h('div', { class: 'campo' }, ...pedaco);
}

function valorDe(p) {
  const el = document.getElementById(`f-${p.nome}`);
  if (!el) return undefined;
  if (p.tipo === 'booleano') return el.checked;
  const bruto = el.value.trim();
  if (bruto === '') return p.obrigatorio ? null : (p.padrao ?? undefined);
  if (p.tipo === 'numero') return Number(bruto);
  if (p.tipo === 'inteiro') return Math.trunc(Number(bruto));
  return bruto;
}

function mostrarExecucao(saida) {
  const painel = document.getElementById('execucao');
  if (!painel) return;
  limpar(painel);
  painel.append(h('h2', {}, 'execução'),
                h('p', {}, h('a', { href: `/tarefas?job=${encodeURIComponent(saida.job_id)}` },
                             `job ${String(saida.job_id).slice(0, 8)}`),
                  ` — versão ${saida.versao} congelada no pedido`));
  const estado = h('p', { class: 'ajuda' }, 'pendente na fila…');
  painel.append(estado);
  const fim = Date.now() + 15 * 60 * 1000;
  const reler = async () => {
    const r = await api.obter(`/api/jobs/${encodeURIComponent(saida.job_id)}`);
    if (r.status !== 200) { estado.textContent = `fila indisponível (${r.status})`; return; }
    const j = r.json;
    estado.textContent = `estado: ${j.estado}${j.mensagem ? ` — ${j.mensagem}` : ''}`;
    if (['concluido', 'falhou', 'cancelado'].includes(j.estado) || Date.now() > fim) {
      if (j.estado === 'concluido' && j.resultado && j.resultado.item_id) {
        painel.append(h('p', {}, h('a', { href: `/conteudo/${encodeURIComponent(j.resultado.item_id)}` },
                                   'abrir o item de resultado')));
      }
      if (j.estado === 'falhou' && j.erro) {
        painel.append(h('p', { class: 'ajuda' }, `falha: ${j.erro}`));
      }
      return;
    }
    setTimeout(reler, 2000);
  };
  void reler();
}

async function executar(id, parametros) {
  aviso('');
  const r = await api.enviar(`/api/ferramentas/script/${encodeURIComponent(id)}/executar`,
                             { parametros });
  if (r.status === 422) {
    const d = (r.json && r.json.detalhe) || [];
    aviso(`parâmetros recusados antes de executar: ${d.map((x) => `${x.campo}: ${x.erro}`).join('; ')}`);
    return;
  }
  if (r.status !== 202) { aviso(`execução recusada (${r.status}): ${api.mensagemDe(r)}`); return; }
  mostrarExecucao(r.json);
}

async function montarFicha(id) {
  const r = await api.obter(`/api/ferramentas/script/${encodeURIComponent(id)}/formulario`);
  const raiz = cartao();
  limpar(raiz);
  if (r.status === 404) {
    raiz.append(h('p', { class: 'ajuda' }, 'ferramenta inexistente (ou de outro inquilino).'));
    return;
  }
  if (r.status !== 200) {
    raiz.append(h('p', { class: 'ajuda' }, `não foi possível carregar a ferramenta (${r.status}).`));
    return;
  }
  const f = r.json;
  document.querySelector('#cabecalho h1').textContent = f.titulo_item || f.titulo;
  const campos = h('form', { id: 'forma' }, ...(f.parametros || []).map(linhaCampo));
  raiz.append(
    h('h2', {}, f.titulo), f.descricao ? h('p', { class: 'ajuda' }, f.descricao) : '',
    h('p', { class: 'ajuda' },
      `versão ${f.versao} · sha256 ${String(f.sha256 || '').slice(0, 12)}… · ` +
      `saídas: ${(f.saidas || []).map((x) => x.nome).join(', ') || 'nenhuma'}`),
    campos,
    h('div', { class: 'linha-ferramentas' },
      h('button', { type: 'button', id: 'executar', class: 'primario' }, 'executar')),
    h('div', { id: 'execucao' }),
  );
  document.getElementById('executar').addEventListener('click', () => {
    const parametros = {};
    for (const p of f.parametros || []) {
      const v = valorDe(p);
      if (v !== undefined) parametros[p.nome] = v;
    }
    void executar(id, parametros);
  });
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
  }
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' },
                 ativo: '/conteudo' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Ferramenta');
  const id = new URLSearchParams(location.search).get('item');
  if (!id) {
    limpar(cartao());
    cartao().append(h('p', { class: 'ajuda' }, 'use /ferramentas?item=<id da ferramenta>.'));
    return;
  }
  await montarFicha(id);
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso(`não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
