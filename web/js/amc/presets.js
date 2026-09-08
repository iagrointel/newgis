/* plat — presets do motor multicritério, tela /amc/presets (item L3-01-h-presets).
   Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports (duas URLs do
   mesmo módulo = duas instâncias, app morre — regra da casa).
   CRUD de presets (nome, descrição, escopo, conteúdo JSON de pesos e vetos), exportação e importação
   em JSON, e APLICAÇÃO SÍNCRONA: aplicar envia a matriz a /api/amc/presets/{id}/aplicar e recebe a
   nota recalculada na mesma resposta — a tela nunca chama /api/jobs (o portão do item é "sem job"). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

const ESQUELETO_CONTEUDO = {
  fatores: ['fator_a', 'fator_b'],
  pesos: { fator_a: 3.0, fator_b: 1.0 },
  vetos: {},
  combinador: 'soma_ponderada',
  politica_ausente: 'excluir',
};

const MATRIZ_EXEMPLO = {
  ids_fatores: ['fator_a', 'fator_b'],
  fatores: [[80.0, 40.0], [55.0, 60.0], [null, 90.0]],
};

let saindo = false;

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

function lerJson(entrada, avisoId, oQueE) {
  let valor;
  try {
    valor = JSON.parse(entrada.value);
  } catch (e) {
    aviso(avisoId, `${oQueE} não é JSON válido: ${e.message}`);
    return undefined;
  }
  aviso(avisoId, '');
  return valor;
}

/* ---------------- formulário de criar/editar (um diálogo só) */

function lerCampoJson(form, nome, oQueE) {
  const entrada = form.campo(nome);
  try {
    return { valor: JSON.parse(entrada.value) };
  } catch (e) {
    form.erro(nome, `${oQueE} não é JSON válido: ${e.message}`);
    return {};
  }
}

async function salvarPreset(preset) {
  const dialogo = porId('dialogo');
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'nome', rotulo: 'nome', tipo: 'texto', obrigatorio: true, padrao: preset?.nome || '' },
    { nome: 'descricao', rotulo: 'descrição', tipo: 'texto', padrao: preset?.descricao || '' },
    { nome: 'escopo', rotulo: 'escopo', tipo: 'select', padrao: preset?.escopo || 'usuario',
      opcoes: [{ valor: 'usuario', rotulo: 'meu usuário (só eu vejo)' },
               { valor: 'inquilino', rotulo: 'inquilino (todo mundo vê)' }] },
    { nome: 'conteudo', rotulo: 'pesos e vetos (JSON)', tipo: 'area', linhas: 14,
      padrao: JSON.stringify(preset?.conteudo || ESQUELETO_CONTEUDO, null, 2),
      ajuda: 'fatores, pesos, vetos, combinador e política de dado ausente do modelo' },
  ];
  f.botoes = [
    { id: 'salvar', rotulo: preset ? 'salvar alterações' : 'criar preset', tipo: 'submit' },
    { id: 'cancelar', rotulo: 'cancelar' },
  ];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') dialogo.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const lido = lerCampoJson(f, 'conteudo', 'pesos e vetos');
    if (lido.valor === undefined) return;
    const corpo = {
      nome: e.detail.valores.nome.trim(),
      descricao: (e.detail.valores.descricao || '').trim(),
      escopo: e.detail.valores.escopo,
      conteudo: lido.valor,
    };
    f.ocupado = true;
    const r = preset
      ? await api.chamar('PATCH', `/api/amc/presets/${encodeURIComponent(preset.id)}`, corpo)
      : await api.enviar('/api/amc/presets', corpo);
    f.ocupado = false;
    if (r.status !== (preset ? 200 : 201)) {
      f.mensagem(`recusado: ${api.mensagemDe(r)}`, 'erro');
      return;
    }
    dialogo.fechar('ok');
    aviso('lista-aviso', `preset "${corpo.nome}" ${preset ? 'atualizado' : 'criado'}`, 'ok');
    await carregar();
  });
  void dialogo.abrir({ titulo: preset ? `editar "${preset.nome}"` : 'novo preset', corpo: f });
  f.focarPrimeiro();
}

/* ---------------- aplicar (recalcula sem job) */

async function aplicarPreset(preset) {
  const dialogo = porId('dialogo');
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'explicacao', rotulo: 'matriz de fatores', tipo: 'info',
      padrao: `unidades × fatores, escala 0-100, null onde falta dado, na ordem de ids_fatores` },
    { nome: 'matriz', rotulo: 'matriz (JSON)', tipo: 'area', linhas: 12,
      padrao: JSON.stringify(MATRIZ_EXEMPLO, null, 2) },
  ];
  f.botoes = [
    { id: 'rodar', rotulo: 'aplicar agora', tipo: 'submit' },
    { id: 'cancelar', rotulo: 'cancelar' },
  ];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') dialogo.fechar(null); });
  f.addEventListener('enviar', async () => {
    const lido = lerCampoJson(f, 'matriz', 'matriz');
    if (lido.valor === undefined) return;
    f.ocupado = true;
    const r = await api.enviar(`/api/amc/presets/${encodeURIComponent(preset.id)}/aplicar`, lido.valor);
    f.ocupado = false;
    if (r.status !== 200) {
      f.mensagem(`recusado: ${api.mensagemDe(r)}`, 'erro');
      return;
    }
    const res = r.json.resultado || {};
    const notas = (res.fav || []).filter((v) => v !== null);
    const semNota = (res.fav || []).length - notas.length;
    dialogo.fechar('ok');
    const resumo = h('div', {},
      h('p', {}, `${(res.fav || []).length} unidades recalculadas na hora, SEM criar job `
        + `(a tela não chama /api/jobs).`),
      h('p', {}, notas.length
        ? `nota de favorabilidade: mínimo ${Math.min(...notas).toFixed(1)}, `
          + `máximo ${Math.max(...notas).toFixed(1)}; ${semNota} sem nota por falta de dado.`
        : 'nenhuma unidade com nota (falta de dado).'),
      res.vetado ? h('p', {}, `${res.vetado.filter(Boolean).length} unidade(s) vetada(s).`) : null,
      h('p', { class: 'ajuda' }, res.aviso_pesos || ''));
    aviso('lista-aviso', `"${preset.nome}" aplicado sobre ${(res.fav || []).length} unidades: recálculo `
      + 'na hora, sem job.', 'ok');
    void dialogo.abrir({ titulo: 'resultado do preset', corpo: resumo,
                         botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
  });
  void dialogo.abrir({ titulo: `aplicar "${preset.nome}"`, corpo: f });
  f.focarPrimeiro();
}

/* ---------------- exportar / importar */

async function exportarPreset(preset) {
  const dialogo = porId('dialogo');
  const r = await api.obter(`/api/amc/presets/${encodeURIComponent(preset.id)}/exportar`);
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível exportar "${preset.nome}": ${api.mensagemDe(r)}`);
    return;
  }
  const area = h('textarea', { rows: 14, readonly: true, spellcheck: 'false', 'aria-label': 'documento de exportação' });
  area.value = JSON.stringify(r.json, null, 2);
  const corpo = h('div', {},
    h('p', {}, 'documento de exportação: o mesmo JSON que a importação aceita.'), area);
  await dialogo.abrir({
    titulo: `exportar "${preset.nome}"`,
    corpo,
    botoes: [{ id: 'fechar', rotulo: 'fechar' }],
  });
}

async function importarPreset() {
  const dialogo = porId('dialogo');
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'documento', rotulo: 'documento exportado (JSON)', tipo: 'area', linhas: 14, obrigatorio: true },
    { nome: 'modelo', rotulo: 'fatores do modelo alvo (opcional, JSON: lista de nomes)',
      tipo: 'area', linhas: 3,
      ajuda: 'informando o modelo, preset com fator fora dele é recusado com a lista do que falta' },
  ];
  f.botoes = [
    { id: 'importar', rotulo: 'importar', tipo: 'submit' },
    { id: 'cancelar', rotulo: 'cancelar' },
  ];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') dialogo.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const lido = lerCampoJson(f, 'documento', 'documento');
    if (lido.valor === undefined) return;
    const documento = lido.valor;
    if ((e.detail.valores.modelo || '').trim()) {
      const m = lerCampoJson(f, 'modelo', 'lista de fatores do modelo');
      if (m.valor === undefined) return;
      documento.fatores_modelo = m.valor;
    }
    f.ocupado = true;
    const r = await api.enviar('/api/amc/presets/importar', documento);
    f.ocupado = false;
    if (r.status !== 201) {
      const detalhe = r.json && r.json.detalhe && r.json.detalhe.faltando
        ? ` — faltando no modelo: ${r.json.detalhe.faltando.join(', ')}` : '';
      f.mensagem(`recusado: ${api.mensagemDe(r)}${detalhe}`, 'erro');
      return;
    }
    dialogo.fechar('ok');
    aviso('lista-aviso', `preset "${r.json.nome}" importado`, 'ok');
    await carregar();
  });
  void dialogo.abrir({ titulo: 'importar preset (JSON)', corpo: f });
  f.focarPrimeiro();
}

/* ---------------- tabela */

function botaoAcao(rotulo, acao) {
  const b = h('button', { type: 'button', class: 'pequeno' }, rotulo);
  b.addEventListener('click', () => acao(b));
  return b;
}

function linha(p) {
  const tr = h('tr', { dataset: { id: p.id, escopo: p.escopo, integrado: String(p.integrado) } });
  const btAplicar = botaoAcao('aplicar', () => aplicarPreset(p));
  const btExportar = botaoAcao('exportar', () => exportarPreset(p));
  const acoes = [btAplicar, btExportar];
  if (!p.integrado) {
    acoes.push(botaoAcao('editar', () => salvarPreset(p)));
    acoes.push(botaoAcao('apagar', async () => {
      const r = await api.apagar(`/api/amc/presets/${encodeURIComponent(p.id)}`);
      if (r.status !== 204) {
        aviso('lista-aviso', `não foi possível apagar "${p.nome}": ${api.mensagemDe(r)}`);
        return;
      }
      aviso('lista-aviso', `preset "${p.nome}" apagado`, 'ok');
      await carregar();
    }));
  } else {
    acoes.push(botaoAcao('copiar para editar', () => salvarPreset({
      nome: `${p.nome} (cópia)`,
      descricao: p.descricao,
      escopo: 'usuario',
      conteudo: p.conteudo,
    })));
  }
  tr.append(
    h('td', {}, p.nome),
    h('td', {}, p.integrado ? h('span', { class: 'marcador info' }, 'integrado') : p.escopo),
    h('td', {}, p.conteudo && p.conteudo.pesos_iguais ? 'pesos iguais (qualquer modelo)'
      : String((p.conteudo && p.conteudo.fatores || []).length)),
    h('td', {}, p.descricao || ''),
    h('td', {}, p.dono_login || '—'),
    h('td', {}, ...acoes),
  );
  return tr;
}

async function carregar() {
  aviso('lista-aviso', '');
  const r = await api.obter('/api/amc/presets');
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('lista-aviso', `não foi possível carregar os presets (${api.mensagemDe(r)})`);
    return;
  }
  const itens = r.json.itens || [];
  porId('lista-total').textContent = `(${r.json.total})`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  if (!itens.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '6', class: 'ajuda' }, 'nenhum preset.')));
    return;
  }
  for (const p of itens) corpo.append(linha(p));
}

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/amc/presets' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Presets do motor');
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
    aviso('aviso', `dados da sessão indisponíveis (GET /api/eu devolveu ${r.status}); a tela segue com a API de presets`, 'atencao');
  }
  porId('preset-novo').addEventListener('click', () => salvarPreset(null));
  porId('preset-importar').addEventListener('click', () => importarPreset());
  layout(usuario);
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
