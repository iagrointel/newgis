/* plat — motor de RENDERIZAÇÃO do formulário (item L5-03-form-builder): a metade do navegador do "um só
   motor" exigido pelo portão (cláusula 2). Chamado dos DOIS lugares que preenchem um formulário — a edição
   web (`web/js/mapa/edicao.js`) e o PWA de campo (`web/js/campo/roteiro.js`) — a partir do MESMO desenho
   (jsonb grupo->campo) que `GET /api/camadas/{id}/formulario` devolve. Condicional (`visivel_se`/
   `obrigatorio_se`) e cálculo (`calculo`) usam a linguagem de expressão do item L2-10-c-linguagem-expressao
   (`web/js/expressao/avaliador.js`), a MESMA que `app/formulario/motor.py` usa no servidor — o mesmo texto
   de expressão avalia IGUAL nos dois lados, byte a byte (ver docs/EXPRESSAO.md).

   O que este módulo NÃO faz: validar contra o servidor (o portão cláusula 4 é explícito — "o navegador não
   é a trava"; `validarLocal` aqui é só UX, a mesma checagem sempre roda de novo no servidor no `POST`). */
import { h } from '../base/dom.js';
import { analisar, avaliar } from '../expressao/avaliador.js';

function avaliarExpressao(texto, contexto) {
  if (!texto) return null;
  try {
    return avaliar(analisar(texto), contexto);
  } catch {
    return null; // mesma regra do servidor (app/formulario/motor.py): erro de avaliação não trava a tela
  }
}

export function estadoCampo(campo, contexto) {
  let visivel = true;
  if (campo.visivel_se) {
    const v = avaliarExpressao(campo.visivel_se, contexto);
    visivel = typeof v === 'boolean' ? v : true;
  }
  let obrigatorio = !!campo.obrigatorio && visivel;
  if (campo.obrigatorio_se) {
    const v = avaliarExpressao(campo.obrigatorio_se, contexto);
    obrigatorio = typeof v === 'boolean' ? v : false;
  } else if (!visivel) {
    obrigatorio = false;
  }
  return { visivel, obrigatorio };
}

export function camposDoDesenho(desenho) {
  const saida = [];
  for (const grupo of (desenho && desenho.grupos) || []) {
    for (const campo of grupo.campos || []) saida.push({ ...campo, grupoId: grupo.id, grupoTitulo: grupo.titulo });
  }
  return saida;
}

function contextoDe(valores, campos) {
  const c = {};
  for (const campo of campos) c[campo.campo] = valores[campo.campo] ?? null;
  return c;
}

function entradaDoWidget(campo, valorAtual, onInput) {
  if (campo.widget === 'booleano') {
    return h('input', {
      type: 'checkbox', name: campo.campo, checked: !!valorAtual,
      onchange: (ev) => onInput(ev.target.checked),
    });
  }
  if (campo.widget === 'selecao') {
    const valores = (campo.dominio && campo.dominio.valores) || [];
    return h('select', { name: campo.campo, onchange: (ev) => onInput(ev.target.value || null) },
      h('option', { value: '' }, '—'),
      ...valores.map((v) => h('option', { value: v, selected: String(v) === String(valorAtual ?? '') }, String(v))));
  }
  if (campo.widget === 'area_texto') {
    return h('textarea', {
      name: campo.campo, rows: '3', value: valorAtual ?? '',
      oninput: (ev) => onInput(ev.target.value === '' ? null : ev.target.value),
    });
  }
  const tipo = campo.widget === 'numero' || campo.widget === 'inteiro' ? 'number'
    : campo.widget === 'data' ? 'date' : 'text';
  return h('input', {
    type: tipo, name: campo.campo, value: valorAtual ?? '',
    step: campo.widget === 'inteiro' ? '1' : campo.widget === 'numero' ? 'any' : undefined,
    onchange: (ev) => {
      if (ev.target.value === '') { onInput(null); return; }
      onInput(tipo === 'number' ? Number(ev.target.value) : ev.target.value);
    },
  });
}

/* `container` recebe o formulário desenhado; `valores` é o objeto mutado em vivo (mesma referência usada
   pelo chamador); `aoMudar()` é chamado depois de qualquer alteração, inclusive as de CÁLCULO (o chamador
   não precisa saber a diferença entre "o usuário digitou" e "o motor recalculou"). Devolve `{ atualizar }`:
   o chamador chama de novo depois de qualquer edição SUA de `valores` de fora (ex.: carregar um rascunho). */
export function renderizar(container, desenho, { valores, aoMudar = () => {} } = {}) {
  const campos = camposDoDesenho(desenho);
  const porGrupoId = new Map();
  for (const grupo of (desenho && desenho.grupos) || []) porGrupoId.set(grupo.id, h('fieldset', { class: 'formulario-grupo' }, h('legend', {}, grupo.titulo || '')));
  const linhas = new Map(); // campo.campo -> {linha, entradaWrap, rotulo}

  function recalcular() {
    const contexto = contextoDe(valores, campos);
    for (const campo of campos) {
      if (campo.calculo) {
        const v = avaliarExpressao(campo.calculo, contexto);
        if (v !== null && v !== valores[campo.campo]) { valores[campo.campo] = v; contexto[campo.campo] = v; }
      }
    }
    for (const campo of campos) {
      const st = estadoCampo(campo, contexto);
      const registro = linhas.get(campo.campo);
      if (!registro) continue;
      registro.linha.hidden = !st.visivel;
      registro.rotuloTexto.textContent = (campo.rotulo || campo.campo) + (st.obrigatorio ? ' *' : '');
      registro.entrada.disabled = !!campo.calculo;
      if (campo.calculo) registro.atualizarValor(valores[campo.campo]);
    }
  }

  for (const campo of campos) {
    const entrada = entradaDoWidget(campo, valores[campo.campo], (v) => {
      valores[campo.campo] = v;
      recalcular();
      aoMudar(campo.campo, v);
    });
    const rotuloTexto = document.createTextNode(campo.rotulo || campo.campo);
    const linha = h('div', { class: 'campo', dataset: { campo: campo.campo } },
      h('label', {}, rotuloTexto), entrada,
      campo.ajuda ? h('p', { class: 'ajuda' }, campo.ajuda) : null);
    linhas.set(campo.campo, {
      linha, entrada, rotuloTexto,
      atualizarValor: (v) => {
        if (campo.widget === 'booleano') entrada.checked = !!v;
        else if (entrada.tagName === 'SELECT') entrada.value = v ?? '';
        else entrada.value = v ?? '';
      },
    });
    (porGrupoId.get(campo.grupoId) || container).append(linha);
  }
  for (const fieldset of porGrupoId.values()) container.append(fieldset);
  recalcular();
  return { atualizar: recalcular, campos };
}

/* checagem local (UX, não autoritativa — ver cabeçalho do módulo): [{campo, mensagem}] */
export function validarLocal(desenho, valores) {
  const campos = camposDoDesenho(desenho);
  const contexto = contextoDe(valores, campos);
  const erros = [];
  for (const campo of campos) {
    const st = estadoCampo(campo, contexto);
    const valor = valores[campo.campo];
    if (st.obrigatorio && (valor === null || valor === undefined || valor === '')) {
      erros.push({ campo: campo.campo, mensagem: 'campo obrigatório' });
      continue;
    }
    const dominio = campo.dominio || {};
    if (valor !== null && valor !== undefined && valor !== '') {
      if (Array.isArray(dominio.valores) && !dominio.valores.some((v) => String(v) === String(valor))) {
        erros.push({ campo: campo.campo, mensagem: 'valor fora do domínio' });
      }
      if (typeof valor === 'number') {
        if (dominio.min !== undefined && dominio.min !== null && valor < dominio.min) {
          erros.push({ campo: campo.campo, mensagem: 'abaixo do domínio' });
        }
        if (dominio.max !== undefined && dominio.max !== null && valor > dominio.max) {
          erros.push({ campo: campo.campo, mensagem: 'acima do domínio' });
        }
      }
    }
  }
  return erros;
}
