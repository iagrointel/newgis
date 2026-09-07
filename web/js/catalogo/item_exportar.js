/* plat · catálogo — diálogo Exportar (item L0-04-h-exportar): escolhe o formato, os campos, o filtro, o CRS de
   saída e a codificação; acompanha o job até o arquivo ficar pronto e mostra o link de download com a validade.
   Nada é enviado até o botão "Exportar"; enquanto a exportação roda, o diálogo consulta o estado a cada 1 s e
   nunca bloqueia a tela. Erro do servidor (400 de filtro inválido, 429 de exportações em curso, 403 de item de
   outro dono) aparece no aviso do próprio diálogo, com a mensagem que o servidor mandou — não uma inventada
   aqui. A caixa "permitir que outros exportem" só aparece para o DONO do item e grava em
   `dados.exportacao.permitir_outros` pelo PATCH do próprio item (nasce desligada, como na Esri). */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import * as api from './api.js';
import { elipse } from './formato.js';

const INTERVALO_MS = 1000;
let parar = false;

function dialogo() {
  return document.getElementById('painel-exportar')
    || document.body.appendChild(h('plat-dialogo', { id: 'painel-exportar' }));
}

function linhaCampo(rotulo, controle) {
  return h('label', { class: 'campo' }, h('span', { class: 'campo-rotulo' }, rotulo), controle);
}

export async function abrirExportar(item, { aoMudar = () => {} } = {}) {
  const d = dialogo();
  const corpo = h('div', { class: 'exportar' });
  const aviso = h('plat-aviso', { id: 'exportar-aviso' });
  corpo.append(aviso, h('p', { class: 'fraco' }, t('catalogo.carregando')));
  const abertura = d.abrir({
    titulo: t('exportar.titulo', { titulo: elipse(item.titulo, 60) }),
    corpo,
    botoes: [{ id: 'fechar', rotulo: t('acao.fechar') }],
  });
  parar = false;
  d.addEventListener('fechou', () => { parar = true; }, { once: true });

  let catalogo;
  try {
    catalogo = await api.exportacaoFormatos();
  } catch (e) {
    limpar(corpo);
    corpo.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, e.message));
    return abertura;
  }
  limpar(corpo);
  corpo.append(aviso);

  const formatos = catalogo.formatos || [];
  const campos = ((item.dados || {}).campos || []).map((c) => c.nome);

  const selFormato = h('select', { id: 'exportar-formato' },
    ...formatos.map((f) => h('option', { value: f.nome }, f.rotulo)));
  const observacao = h('p', { class: 'fraco', id: 'exportar-observacao' });
  const nome = h('input', { type: 'text', id: 'exportar-nome', maxlength: '120', value: '' });
  /* sem atributo de texto-fantasma no campo: o exemplo fica numa linha abaixo, visível o tempo todo (e a
     palavra em inglês desse atributo é justamente a que `make sem-marcador` proíbe na árvore) */
  const where = h('input', { type: 'text', id: 'exportar-where', maxlength: '4000' });
  const whereExemplo = h('p', { class: 'fraco', id: 'exportar-filtro-exemplo' }, t('exportar.filtro_exemplo'));
  const srid = h('input', { type: 'number', id: 'exportar-srid', min: '1', max: '999999' });
  const sridAtual = h('p', { class: 'fraco', id: 'exportar-srid-atual' },
    t('exportar.crs_atual', { srid: (item.dados || {}).srid || '?' }));
  const codificacao = h('select', { id: 'exportar-codificacao' },
    h('option', { value: 'UTF-8' }, 'UTF-8'), h('option', { value: 'ISO-8859-1' }, 'ISO-8859-1'));

  const camposCaixas = h('div', { class: 'caixas', id: 'exportar-campos' },
    ...campos.map((c) => {
      const cx = h('input', { type: 'checkbox', name: 'campo', value: c, id: `exportar-campo-${c}` });
      cx.checked = true;
      return h('div', { class: 'caixa' }, cx, h('label', { for: `exportar-campo-${c}` }, c));
    }));

  const csvSep = h('select', { id: 'exportar-csv-separador' },
    h('option', { value: ',' }, t('exportar.csv_virgula')), h('option', { value: ';' }, t('exportar.csv_ponto_virgula')),
    h('option', { value: '\t' }, t('exportar.csv_tab')), h('option', { value: '|' }, t('exportar.csv_barra')));
  const csvDec = h('select', { id: 'exportar-csv-decimal' },
    h('option', { value: '.' }, t('exportar.csv_decimal_ponto')),
    h('option', { value: ',' }, t('exportar.csv_decimal_virgula')));
  const csvX = h('input', { type: 'text', id: 'exportar-csv-x', maxlength: '63', value: 'X' });
  const csvY = h('input', { type: 'text', id: 'exportar-csv-y', maxlength: '63', value: 'Y' });
  const blocoCsv = h('fieldset', { id: 'exportar-csv', hidden: true },
    h('legend', { class: 'campo-rotulo' }, t('exportar.csv_opcoes')),
    linhaCampo(t('exportar.csv_separador'), csvSep), linhaCampo(t('exportar.csv_decimal'), csvDec),
    linhaCampo(t('exportar.csv_coluna_x'), csvX), linhaCampo(t('exportar.csv_coluna_y'), csvY));

  function aoTrocarFormato() {
    const f = formatos.find((x) => x.nome === selFormato.value) || {};
    observacao.textContent = f.observacao || '';
    blocoCsv.hidden = !f.opcoes_csv;
    codificacao.disabled = !(f.codificacoes || []).includes('ISO-8859-1');
    if (codificacao.disabled) codificacao.value = 'UTF-8';
  }
  selFormato.addEventListener('change', aoTrocarFormato);

  corpo.append(
    linhaCampo(t('exportar.formato'), selFormato), observacao,
    linhaCampo(t('exportar.nome_arquivo'), nome),
    h('details', { class: 'coluna' }, h('summary', {}, t('exportar.campos')), camposCaixas),
    linhaCampo(t('exportar.filtro'), where), whereExemplo,
    linhaCampo(t('exportar.crs_saida'), srid), sridAtual,
    linhaCampo(t('exportar.codificacao'), codificacao),
    blocoCsv,
  );

  if (item.pode_editar) {
    const permitir = h('input', { type: 'checkbox', id: 'exportar-permitir-outros' });
    permitir.checked = !!(((item.dados || {}).exportacao || {}).permitir_outros);
    permitir.addEventListener('change', async () => {
      const dados = { ...(item.dados || {}), exportacao: { permitir_outros: permitir.checked } };
      try {
        const novo = await api.editar(item.id, { dados });
        item = { ...item, dados: novo.dados || dados };
        aoMudar({ dados: item.dados });
        aviso.mostrar(t('exportar.permitir_salvo'), 'ok');
      } catch (e) { permitir.checked = !permitir.checked; aviso.erro(e.message); }
    });
    corpo.append(h('div', { class: 'caixa' }, permitir,
      h('label', { for: 'exportar-permitir-outros' }, t('exportar.permitir_outros'))));
  }

  const estado = h('div', { id: 'exportar-estado', class: 'fraco' });
  const botao = h('button', { type: 'button', class: 'primario', id: 'exportar-executar' }, t('exportar.executar'));
  corpo.append(h('div', { class: 'botoes' }, botao), estado);
  aoTrocarFormato();

  botao.addEventListener('click', async () => {
    botao.disabled = true;
    aviso.limpar?.();
    estado.textContent = t('exportar.enviando');
    const marcados = [...camposCaixas.querySelectorAll('input[name=campo]')].filter((c) => c.checked)
      .map((c) => c.value);
    const pedido = { item_id: item.id, formato: selFormato.value };
    if (nome.value.trim()) pedido.nome = nome.value.trim();
    if (marcados.length && marcados.length !== campos.length) pedido.campos = marcados;
    if (where.value.trim()) pedido.where = where.value.trim();
    if (srid.value) pedido.srid_saida = Number(srid.value);
    if (codificacao.value !== 'UTF-8') pedido.codificacao = codificacao.value;
    if (!blocoCsv.hidden) {
      pedido.csv = { separador: csvSep.value, decimal: csvDec.value };
      if (csvX.value.trim()) pedido.csv.coluna_x = csvX.value.trim();
      if (csvY.value.trim()) pedido.csv.coluna_y = csvY.value.trim();
    }
    let criada;
    try {
      criada = await api.exportacaoCriar(pedido);
    } catch (e) {
      botao.disabled = false;
      estado.textContent = '';
      aviso.erro(e.message);
      return;
    }
    estado.textContent = t('exportar.gerando');
    while (!parar) {
      await new Promise((r) => setTimeout(r, INTERVALO_MS));
      let atual;
      try { atual = await api.exportacaoObter(criada.exportacao_id); } catch (e) { aviso.erro(e.message); break; }
      if (atual.estado === 'pronta') {
        limpar(estado);
        estado.append(
          h('a', { href: atual.link, id: 'exportar-link', download: '' }, t('exportar.baixar')),
          h('span', { class: 'fraco' },
            ` · ${t('exportar.pronto', { feicoes: atual.feicoes ?? '?', kb: Math.round((atual.bytes || 0) / 1024) })}`),
          h('p', { class: 'fraco' }, t('exportar.validade', { dias: atual.validade_dias })),
        );
        botao.disabled = false;
        break;
      }
      if (['falhou', 'cancelada', 'expirada'].includes(atual.estado)) {
        estado.textContent = '';
        aviso.erro(atual.erro || t('exportar.falhou'));
        botao.disabled = false;
        break;
      }
    }
  });
  return abertura;
}
