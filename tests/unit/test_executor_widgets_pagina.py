"""Resto do item L5-01-d-widgets-pagina-menu (apontado pelo worker dos widgets em 15/09): os nove tipos de
`TIPOS_WIDGET_PAGINA` (`executor.js`) batem por nome com `widgets/registro.js` mas até aqui `desenharNo`
ainda caía no `default` (`exec-desconhecido`) para todos eles — só a DETECÇÃO de falha de carregamento no
preload (`prepararWidgets`) estava ligada. Este arquivo prova que `desenharNo` agora MONTA os nove pelo
motor de verdade: custom element certo (`plat-w-<tipo>`), conteúdo renderizado (não só o elemento vazio),
navegação de página por botão/cartão, controlador achando o alvo por `data-no-id`, e caixa de erro nomeada
(nunca um elemento morto) quando o módulo falhou no preload.

Roda em Node com um DOM SINTÉTICO (`tests/unit/apoio_dom_sintetico.mjs`) — esta máquina não tem navegador
headless (ver CLAUDE.md do laço), então é a prova possível aqui. O e2e de navegador que cobre o mesmo
contrato de ponta a ponta (`tests/e2e/test_widgets_pagina.py::test_doze_widgets_no_executor_sem_script_executado`)
fica PENDENTE de máquina com navegador — ele também cobre `texto`/`imagem`/`menu_widget` pelo motor, que
são escopo DIFERENTE (de propósito fora de `TIPOS_WIDGET_PAGINA`, ver comentário de `executor.js`) e não
fazem parte deste item."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

NOVE = ["botao", "cartao", "incorporar", "divisor", "controlador", "compartilhar", "login", "idioma", "tema"]


def executar_js(codigo: str, timeout=30):
    processo = subprocess.run(
        ["node", "--input-type=module", "-e", codigo], cwd=ROOT, text=True, capture_output=True, timeout=timeout,
    )
    assert processo.returncode == 0, processo.stderr
    return json.loads(processo.stdout)


CENARIO = """
  const { instalarDomSintetico, esvaziarMicrotarefas } = await import('./tests/unit/apoio_dom_sintetico.mjs');
  const document = instalarDomSintetico();
  const executor = await import('./web/js/executor/executor.js');

  const propriedadesPorTipo = {
    botao: { rotulo: 'Ir para Sobre', acao: { tipo: 'pagina', pagina: 'sobre' } },
    cartao: { titulo: 'Cartão de teste', texto: 'corpo', pagina: 'sobre', link_rotulo: 'abrir sobre' },
    incorporar: { titulo: 'embed', html: '<p>seguro</p>' },
    divisor: { estilo: 'tracejado' },
    controlador: { alvos: [{ id: 'n_cartao', rotulo: 'cartão' }] },
    compartilhar: { qr: false, incorporar: false },
    login: {},
    idioma: { idiomas: ['pt-BR'] },
    tema: {},
  };
  const pagina = { id: 'pg1', tipo: 'pagina', pai: null,
                   propriedades: { titulo: 'Início', caminho: 'inicio', tipo_pagina: 'rolavel' } };
  const nos = [pagina, ...Object.entries(propriedadesPorTipo).map(([tipo, propriedades]) => ({
    id: tipo === 'cartao' ? 'n_cartao' : `n_${tipo}`, tipo, pai: 'pg1', propriedades,
  }))];
  const documento = { corpo: { nos, ligacoes: [] } };

  // mesma ordem de `executar_tela.js`: preload primeiro (importa os módulos, detecta falha), desenho depois
  const falhas = await executor.prepararWidgets(documento);
  const ctx = executor.criarContextoWidgets(documento, new Map());
  const irParaChamadas = [];
  const irPara = (caminho) => irParaChamadas.push(caminho);
  const paleta = { tipos: {} };

  const localNames = {};
  for (const no of nos.filter((n) => n.tipo !== 'pagina')) {
    const el = executor.desenharNo(no, documento, paleta, irPara, ctx);
    document.appendChild(el);
    localNames[no.tipo] = el.localName;
  }
  await esvaziarMicrotarefas(3);

  const g = (id, sel) => document.querySelector(`[data-no-id="${id}"]`)?.querySelector(sel) ?? null;

  // navegação: clique no botão de página e no cartão devem chamar irPara com o caminho configurado
  g('n_botao', 'button').dispatchEvent(new Event('click'));
  g('n_cartao', 'button').dispatchEvent(new Event('click'));

  // controlador: alvo é o cartão (mesma página) — deve achar por `[data-no-id]` e alternar `hidden`
  const cartaoEl = document.querySelector('[data-no-id="n_cartao"]');
  const elControlador = document.querySelector('[data-no-id="n_controlador"]');
  const ctrlBotao = elControlador.querySelector('button[data-alvo="n_cartao"]');
  const hiddenAntes = cartaoEl.hidden;
  ctrlBotao.dispatchEvent(new Event('click'));
  const hiddenDepois = cartaoEl.hidden;

  // caminho de falha: módulo que não carregou vira caixa de erro nomeada, nunca um elemento morto
  const ctxComFalha = executor.criarContextoWidgets(documento, new Map([['botao', 'módulo não carregou (teste)']]));
  const noBotaoFalho = { id: 'n_botao_falho', tipo: 'botao', pai: 'pg1', propriedades: { rotulo: 'x' } };
  const elFalho = executor.desenharNo(noBotaoFalho, documento, paleta, irPara, ctxComFalha);

  console.log(JSON.stringify({
    falhasDoPreload: [...falhas.entries()],
    localNames,
    tiposDeWidget: executor.tiposDeWidget(documento),
    botaoTexto: g('n_botao', 'button')?.textContent,
    cartaoTitulo: g('n_cartao', 'h3')?.textContent,
    divisorClasse: g('n_divisor', 'hr')?.className,
    incorporarSrcdoc: g('n_incorporar', 'iframe')?.srcdoc,
    temaBotoes: document.querySelector('[data-no-id="n_tema"]').querySelectorAll('button').length,
    idiomaOpcoes: document.querySelector('[data-no-id="n_idioma"]').querySelectorAll('option').length,
    loginAutenticado: document.querySelector('[data-no-id="n_login"]').dataset.autenticado,
    compartilharInput: g('n_compartilhar', 'input')?.value,
    irParaChamadas,
    hiddenAntes, hiddenDepois,
    falhaElemento: { localName: elFalho.localName, role: elFalho.getAttribute('role'), texto: elFalho.textContent },
  }));
"""


def test_os_nove_widgets_de_pagina_montam_pelo_motor_sem_cair_em_desconhecido():
    r = executar_js(CENARIO)
    assert r["falhasDoPreload"] == [], r["falhasDoPreload"]
    # nenhum dos nove caiu na caixa genérica: o elemento é o custom element certo do manifesto
    for tipo in NOVE:
        assert r["localNames"][tipo] == f"plat-w-{tipo}", (tipo, r["localNames"][tipo])
    assert set(r["tiposDeWidget"]) == set(NOVE)


def test_widgets_renderizam_conteudo_de_verdade_no_documento_sintetico():
    r = executar_js(CENARIO)
    assert r["botaoTexto"] == "Ir para Sobre"
    assert r["cartaoTitulo"] == "Cartão de teste"
    assert r["divisorClasse"] == "plat-w-divisor plat-divisor-tracejado"
    assert "<p>seguro</p>" in r["incorporarSrcdoc"]
    assert r["temaBotoes"] == 3  # sistema/claro/escuro
    assert r["idiomaOpcoes"] == 1  # só pt-BR no documento de teste
    assert r["loginAutenticado"] == "0"  # fetch fica sem sessão (stub do DOM sintético) → link "Entrar"
    assert r["compartilharInput"] == "http://localhost/executar?item=teste"


def test_botao_e_cartao_de_pagina_chamam_ir_para_pela_mesma_rota_do_menu():
    r = executar_js(CENARIO)
    assert r["irParaChamadas"] == ["sobre", "sobre"]


def test_controlador_acha_o_alvo_por_data_no_id_e_alterna():
    r = executar_js(CENARIO)
    assert r["hiddenAntes"] is False
    assert r["hiddenDepois"] is True


def test_modulo_que_falhou_no_preload_vira_caixa_de_erro_nomeada_nunca_elemento_morto():
    r = executar_js(CENARIO)
    assert r["falhaElemento"]["localName"] != "plat-w-botao"
    assert r["falhaElemento"]["role"] == "alert"
    assert "módulo não carregou" in r["falhaElemento"]["texto"]
